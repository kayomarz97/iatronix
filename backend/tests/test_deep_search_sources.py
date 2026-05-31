"""Tests for the deep-search citation fetcher's pure parse helpers (Phase 5b)."""

from app.services.deep_search_sources import (
    _articles_from_icite_meta,
    _neighbor_pmids,
    NEIGHBOR_CAP,
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
