"""Tests for the deep-search citation fetcher's pure parse helpers (Phase 5b)."""

import asyncio
import types

from app.services.deep_search import ChasedArticle, DeepSearchResult
from app.services.deep_search_sources import (
    _articles_from_icite_meta,
    _collect_seed_pmids,
    _neighbor_pmids,
    deepen_fetched_data,
    NEIGHBOR_CAP,
    SEED_CAP,
)


def test_neighbor_pmids_merges_forward_and_backward_deduped():
    rec = {"cited_by": [1, 2, 3], "references": [3, 4]}
    assert _neighbor_pmids(rec) == ["1", "2", "3", "4"]


def test_neighbor_pmids_capped():
    rec = {"cited_by": list(range(100)), "references": []}
    assert len(_neighbor_pmids(rec)) == NEIGHBOR_CAP


def test_neighbor_pmids_empty():
    assert _neighbor_pmids({}) == []


def test_articles_have_resolvable_pubmed_urls():
    meta = [
        {"pmid": 12345, "title": "Statins in primary prevention", "doi": "10.1/x"},
        {"pmid": 999, "title": "No DOI study"},
    ]
    arts = _articles_from_icite_meta(meta)
    assert len(arts) == 2
    assert arts[0].url == "https://pubmed.ncbi.nlm.nih.gov/12345/"
    assert arts[0].doi == "10.1/x"
    assert arts[0].source == "PubMed (iCite)"
    assert all(a.url for a in arts)  # every chased article is citable


def test_articles_skip_records_missing_pmid_or_title():
    meta = [
        {"pmid": "", "title": "no pmid"},
        {"pmid": 7, "title": ""},
        {"title": "no pmid key"},
        {"pmid": 8, "title": "good"},
    ]
    arts = _articles_from_icite_meta(meta)
    assert [a.pmid for a in arts] == ["8"]


# ── pipeline integration helper ──────────────────────────────────────────────

def _fake_fetched(seed_pmids, *, with_evidence=True):
    drug = types.SimpleNamespace(
        guideline_abstracts=[{"pmid": p, "title": "seed"} for p in seed_pmids],
        systematic_review_abstracts=[],
        clinical_trial_abstracts=[],
    )
    ev = types.SimpleNamespace(guideline_abstracts=[], data_sources=[]) if with_evidence else None
    return types.SimpleNamespace(
        drug_data=drug, disease_data=None, condition_data=None, procedure_data=None,
        evidence_data=ev, comparative_evidence=None, comparative_drug_data=[], comorbidity_data=[],
    )


def test_collect_seed_pmids_dedups_and_caps():
    fd = _fake_fetched([str(i) for i in range(50)] + ["7", "7"])
    seeds = _collect_seed_pmids(fd)
    assert len(seeds) == SEED_CAP
    assert seeds == seeds[: SEED_CAP]  # order preserved


def test_collect_seed_pmids_empty_when_no_articles():
    fd = _fake_fetched([])
    assert _collect_seed_pmids(fd) == []


def test_deepen_merges_chased_articles(monkeypatch):
    async def fake_deep_search(seeds, fetcher, **kw):
        return DeepSearchResult(articles=[
            ChasedArticle(title="Chased A", source="PubMed (iCite)", pmid="111", url="https://pubmed.ncbi.nlm.nih.gov/111/"),
            ChasedArticle(title="No URL", source="x", pmid="222", url=None),  # excluded (not citable)
        ])
    monkeypatch.setattr("app.services.deep_search_sources.deep_search", fake_deep_search)

    fd = _fake_fetched(["999"])  # one seed -> triggers chase
    added = asyncio.run(deepen_fetched_data(fd))
    assert added == 1
    assert fd.evidence_data.guideline_abstracts[0]["pmid"] == "111"
    assert "PubMed (iCite)" in fd.evidence_data.data_sources


def test_deepen_noop_without_seeds(monkeypatch):
    called = {"n": 0}
    async def fake_deep_search(*a, **k):
        called["n"] += 1
        return DeepSearchResult()
    monkeypatch.setattr("app.services.deep_search_sources.deep_search", fake_deep_search)
    fd = _fake_fetched([])  # no PMIDs
    added = asyncio.run(deepen_fetched_data(fd))
    assert added == 0
    assert called["n"] == 0  # never even calls deep_search without seeds
