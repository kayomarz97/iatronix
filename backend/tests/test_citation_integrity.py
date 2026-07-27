"""Regression tests for the 2026-07-27 citation-integrity fixes.

Each test pins one defect that let a CITED source disappear from the reference list —
the "references are broken" class of bug. Full deterministic harness (provider-realistic
model outputs, 14 cases) lives in test/citation_integrity.py; these are the pytest locks.

All are provider-agnostic: they exercise post-processing, which runs after any model's JSON.
"""
import pytest

from app.config import settings
from app.services.article_registry import build_article_registry
from app.services.rag_pipeline import _quarantine_sourceless_items, _resolve_ref_tokens

pytestmark = pytest.mark.citation


class _Obj:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture
def fix_on(monkeypatch):
    monkeypatch.setattr(settings, "citation_integrity_fix_enabled", True)


@pytest.fixture
def fix_off(monkeypatch):
    monkeypatch.setattr(settings, "citation_integrity_fix_enabled", False)


def _fetched_with_chapter():
    """A disease result carrying a StatPearls full chapter (field: book_monographs)."""
    return _Obj(
        disease_data=_Obj(
            guideline_abstracts=[],
            systematic_review_abstracts=[],
            clinical_trial_abstracts=[],
            practice_guideline_abstracts=[],
            book_monographs=[{
                "title": "Laboratory Evaluation of Hereditary Hemochromatosis",
                "url": "https://www.ncbi.nlm.nih.gov/books/NBK594250/",
                "nbk_id": "NBK594250",
                "source": "StatPearls",
                "text": "HFE C282Y homozygosity accounts for most cases.",
            }],
        ),
        drug_data=None, procedure_data=None, evidence_data=None, condition_data=None,
        comparative_evidence=None, comorbidity_data=[], comparative_drug_data=[],
    )


# ── Defect (a): StatPearls chapters never entered the registry ────────────────

def test_book_monographs_enter_registry(fix_on):
    """The real field is `book_monographs`; the registry used to walk `ncbi_books`/`books`,
    which exist on no object — so chapters never reached the reference list at all."""
    reg = build_article_registry(_fetched_with_chapter())
    urls = [a.url for a in reg.items]
    assert any("/books/NBK594250" in u for u in urls), (
        "StatPearls chapter missing from registry — chapters carry 79% of this app's "
        "correct answers but would be invisible in the reference list"
    )
    assert all(a.url for a in reg.items), "registry must guarantee an article-level URL"


def test_book_monographs_absent_when_flag_off(fix_off):
    """Flag OFF must reproduce the old behaviour exactly (clean rollback path)."""
    reg = build_article_registry(_fetched_with_chapter())
    assert not any("/books/" in a.url for a in reg.items)


# ── Defect (b): inline [REF_N] never marked used_inline ───────────────────────

def _ref_map():
    return {"REF_1": {"title": "Real Trial", "source": "PubMed", "pmid": "30000001",
                      "url": "https://pubmed.ncbi.nlm.nih.gov/30000001/"}}


def _parsed(source_value):
    return {"sections": [{"title": "Evidence",
                          "content_items": [{"text": "A claim.", "source": source_value}]}],
            "references": []}


@pytest.mark.parametrize("emitted", [
    "[REF_1]",      # Anthropic: the instructed format
    "REF_1",        # Cerebras: brackets dropped
    "REF 1",        # Cerebras: space for underscore
    "[REF_1].",     # OpenAI: trailing punctuation
    "(REF_1)",      # OpenAI: parenthesised
])
def test_inline_token_marks_used_inline(fix_on, emitted):
    """The inline branch resolved the article but never marked it used_inline — only the
    _TOKEN_FULL fallback did. So the INSTRUCTED format left its article unmarked, which
    (1) filed it under "Additional sources retrieved" and (2) stripped its exemption from
    the to_reference_list(max_uncited=...) cap."""
    reg = build_article_registry(_Obj(
        disease_data=_Obj(guideline_abstracts=[], practice_guideline_abstracts=[],
                          clinical_trial_abstracts=[],
                          systematic_review_abstracts=[{
                              "pmid": "30000001", "title": "Real Trial",
                              "source": "PubMed", "journal": "Lancet", "year": 2021}]),
        drug_data=None, procedure_data=None, evidence_data=None, condition_data=None,
        comparative_evidence=None, comorbidity_data=[], comparative_drug_data=[],
    ))
    parsed = _parsed(emitted)
    _resolve_ref_tokens(parsed, _ref_map(), reg)
    assert any(a.used_inline for a in reg.items), f"{emitted!r} did not mark its article cited"


def test_cited_reference_survives_uncited_cap(fix_on):
    """A cited reference must never be evicted by max_uncited — otherwise a claim points at
    a source the user cannot see."""
    arts = [{"pmid": str(30000000 + i), "title": f"Trial {i}", "source": "PubMed",
             "journal": "Lancet", "year": 2020} for i in range(1, 61)]
    reg = build_article_registry(_Obj(
        disease_data=_Obj(guideline_abstracts=[], practice_guideline_abstracts=[],
                          clinical_trial_abstracts=[], systematic_review_abstracts=arts),
        drug_data=None, procedure_data=None, evidence_data=None, condition_data=None,
        comparative_evidence=None, comorbidity_data=[], comparative_drug_data=[],
    ))
    target = reg.items[-1]
    target.used_inline = True
    out = reg.to_reference_list(max_uncited=40)
    assert any(r["title"] == target.title and r["used_inline"] for r in out), (
        "cited reference was evicted by the uncited cap"
    )


# ── Defect (c): additional_sources dropped by the response schema ─────────────

def test_additional_sources_survive_schema():
    """_resolve_ref_tokens has always built additional_sources for '[REF_3, REF_4]', but
    AdaptiveContentItem had no such field, so pydantic silently discarded it and a claim
    citing two articles rendered as citing one."""
    from app.schemas.query import AdaptiveContentItem
    item = AdaptiveContentItem(
        text="A claim.", source="Real Trial",
        additional_sources=[{"title": "Second Trial", "source": "PubMed",
                             "pmid": "30000002",
                             "url": "https://pubmed.ncbi.nlm.nih.gov/30000002/"}],
    )
    assert len(item.model_dump()["additional_sources"]) == 1


# ── Defect (e): the __UNRESOLVED_TOKEN__ sentinel rendered to the user ────────

def test_unresolved_sentinel_is_demoted_not_rendered(fix_on):
    """'__UNRESOLVED_TOKEN__' is a sentinel meaning "backfill me", not a source. The old
    truthiness check treated it as a real source, so when backfill also failed it reached
    the clinician verbatim as the claim's source."""
    parsed = {"sections": [{"content_items": [
        {"text": "Orphan claim.", "source": "__UNRESOLVED_TOKEN__", "url": None, "pmid": None}
    ]}], "references": []}
    _quarantine_sourceless_items(parsed, fetched_data=_fetched_with_chapter(), registry=None)
    src = parsed["sections"][0]["content_items"][0]["source"]
    assert src != "__UNRESOLVED_TOKEN__", "sentinel leaked into rendered output"
    assert src == "Expert opinion"


def test_unresolved_sentinel_unchanged_when_flag_off(fix_off):
    parsed = {"sections": [{"content_items": [
        {"text": "Orphan claim.", "source": "__UNRESOLVED_TOKEN__", "url": None, "pmid": None}
    ]}], "references": []}
    _quarantine_sourceless_items(parsed, fetched_data=_fetched_with_chapter(), registry=None)
    assert parsed["sections"][0]["content_items"][0]["source"] == "__UNRESOLVED_TOKEN__"


# ── Defect (d): dead helper referencing a deleted table ───────────────────────

def test_dead_source_pattern_helper_removed():
    """_match_source_pattern iterated _SOURCE_URL_MAP, deleted in the May 2026 homepage
    cleanup — any call would have raised NameError."""
    import app.services.url_builder as ub
    assert not hasattr(ub, "_match_source_pattern")
    assert not hasattr(ub, "_SOURCE_URL_MAP")
