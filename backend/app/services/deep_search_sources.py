"""Real citation fetchers for the deep-search engine (Phase 5b).

Primary source: NIH iCite / NIH-OCC (``/api/pubs?pmids=...&fl=cited_by,references``)
— the best single call for a forward+backward citation graph (INTEGRATION_NOTES §E).
Every neighbour PMID gets a guaranteed-resolvable PubMed article URL, so chased
articles are citable (URL-bearing) and survive the "no evidence" gate.

Defensive: any network/parse error yields an empty list so a single branch
failure never aborts the search. Live-verified at the Phase 10 dev rebuild.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.deep_search import ChasedArticle, deep_search

logger = logging.getLogger(__name__)

ICITE_URL = "https://icite.od.nih.gov/api/pubs"
NEIGHBOR_CAP = 20  # cap per-branch fanout (depth bound also applies)
SEED_CAP = 8       # chase from at most N already-found articles
_REQUEST_TIMEOUT = 8.0

# abstract-list attributes carried by the various FetchResult dataclasses
_ABSTRACT_ATTRS = (
    "guideline_abstracts",
    "systematic_review_abstracts",
    "clinical_trial_abstracts",
    "practice_guideline_abstracts",
)


def _pubmed_url(pmid: str) -> str:
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"


def _articles_from_icite_meta(meta: list[dict[str, Any]]) -> list[ChasedArticle]:
    """Pure: build URL-bearing ChasedArticles from iCite /api/pubs metadata records."""
    out: list[ChasedArticle] = []
    for m in meta or []:
        pmid = str(m.get("pmid") or "").strip()
        title = (m.get("title") or "").strip()
        if not pmid or not title:
            continue
        doi = m.get("doi") or None
        out.append(
            ChasedArticle(
                title=title,
                source="PubMed (iCite)",
                pmid=pmid,
                doi=doi,
                url=_pubmed_url(pmid),
            )
        )
    return out


def _neighbor_pmids(seed_record: dict[str, Any]) -> list[str]:
    """Pure: forward (cited_by) + backward (references) PMIDs from an iCite record."""
    pmids: list[str] = []
    for key in ("cited_by", "references"):
        for x in seed_record.get(key) or []:
            pmids.append(str(x))
    # de-dup preserving order, then cap
    return list(dict.fromkeys(pmids))[:NEIGHBOR_CAP]


async def _icite_pubs(client, pmids: list[str], fl: str) -> list[dict]:
    resp = await client.get(ICITE_URL, params={"pmids": ",".join(pmids), "fl": fl})
    resp.raise_for_status()
    return (resp.json() or {}).get("data", []) or []


async def icite_fetcher(seed: ChasedArticle) -> list[ChasedArticle]:
    """Forward+backward citation neighbours for a PMID seed, hydrated to articles."""
    if not seed.pmid:
        return []
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT, headers={"User-Agent": "iatronix-deepsearch"}
        ) as client:
            recs = await _icite_pubs(client, [seed.pmid], "pmid,cited_by,references")
            if not recs:
                return []
            neighbors = _neighbor_pmids(recs[0])
            if not neighbors:
                return []
            meta = await _icite_pubs(client, neighbors, "pmid,title,doi,year")
    except Exception as exc:
        logger.debug("icite_fetcher failed for PMID %s: %s", seed.pmid, exc)
        return []
    return _articles_from_icite_meta(meta)


# ── Pipeline integration: deepen thin-but-nonzero evidence ────────────────────


def _collect_seed_pmids(fetched_data) -> list[str]:
    """Pure: gather PMIDs from every abstract list on a FetchedData (dedup, capped)."""
    if fetched_data is None:
        return []
    pmids: list[str] = []

    def _scan(obj) -> None:
        if obj is None:
            return
        for attr in _ABSTRACT_ATTRS:
            for a in getattr(obj, attr, []) or []:
                if isinstance(a, dict) and a.get("pmid"):
                    pmids.append(str(a["pmid"]))

    for obj in (
        getattr(fetched_data, "drug_data", None),
        getattr(fetched_data, "disease_data", None),
        getattr(fetched_data, "condition_data", None),
        getattr(fetched_data, "procedure_data", None),
        getattr(fetched_data, "evidence_data", None),
        getattr(fetched_data, "comparative_evidence", None),
    ):
        _scan(obj)
    for lst in (
        getattr(fetched_data, "comparative_drug_data", None) or [],
        getattr(fetched_data, "comorbidity_data", None) or [],
    ):
        for obj in lst:
            _scan(obj)

    return list(dict.fromkeys(pmids))[:SEED_CAP]


async def deepen_fetched_data(fetched_data, *, on_progress=None) -> int:
    """Chase citations from already-found PMIDs and merge URL-bearing results into
    ``fetched_data.evidence_data``. Returns the number of grounded articles added.

    Safe no-op when there are no PMID seeds (deep-search chases FROM found articles,
    never fabricates). Defensive against any failure.
    """
    seed_pmids = _collect_seed_pmids(fetched_data)
    if not seed_pmids:
        return 0
    seeds = [ChasedArticle(title="", source="seed", pmid=p) for p in seed_pmids]
    try:
        res = await deep_search(seeds, icite_fetcher, on_progress=on_progress)
    except Exception as exc:
        logger.debug("deepen_fetched_data: deep_search failed: %s", exc)
        return 0

    abstracts = [
        {"title": a.title, "pmid": a.pmid, "doi": a.doi, "url": a.url, "source": a.source}
        for a in res.articles
        if a.url
    ]
    if not abstracts:
        return 0

    try:
        ev = getattr(fetched_data, "evidence_data", None)
        if ev is None:
            from app.services.data_fetcher import EvidenceFetchResult

            ev = EvidenceFetchResult(fetch_success=True, data_sources=["PubMed (iCite)"])
            fetched_data.evidence_data = ev
        ev.guideline_abstracts = (ev.guideline_abstracts or []) + abstracts
        if "PubMed (iCite)" not in (ev.data_sources or []):
            ev.data_sources = (ev.data_sources or []) + ["PubMed (iCite)"]
    except Exception as exc:
        logger.warning("deepen_fetched_data: merge failed: %s", exc)
        return 0
    return len(abstracts)
