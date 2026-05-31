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

from app.services.deep_search import ChasedArticle

logger = logging.getLogger(__name__)

ICITE_URL = "https://icite.od.nih.gov/api/pubs"
NEIGHBOR_CAP = 20  # cap per-branch fanout (depth bound also applies)
_REQUEST_TIMEOUT = 8.0


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
