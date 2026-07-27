"""Regression tests for the 2026-07-27 non-disease chapter-coverage lever.

`_fetch_book_monographs` (whole chapter, concept-gated title match, citable NBK URL) ran only
inside fetch_disease_data. Procedure/drug queries fell back to `_fetch_pmc_statpearls`, whose
string result is truncated to 600 chars and stored with `pmid: ""` — neither groundable nor
citable. Correctness is ~60% with a chapter vs ~9% without (RAGNOSIS_FINDINGS.md), so this was
the largest remaining coverage gap.

Offline/no-network: the fetch itself is covered by test/ab_chapter_coverage.py (live A/B,
0% -> 100% chapter rate on 6 non-disease queries, disease controls unchanged).
"""
import pytest

from app.config import settings
from app.services.data_fetcher import (
    DrugFetchResult,
    EvidenceFetchResult,
    ProcedureFetchResult,
    _book_term_for_drug,
)
from app.services.prompt_engine import _build_adaptive_data_block

pytestmark = pytest.mark.citation


# ── Salt-form stripping ───────────────────────────────────────────────────────

@pytest.mark.parametrize("resolved,expected", [
    ("AMIODARONE HYDROCHLORIDE", "AMIODARONE"),
    ("WARFARIN SODIUM", "WARFARIN"),
    ("METOPROLOL TARTRATE", "METOPROLOL"),
    ("DILTIAZEM HCL", "DILTIAZEM"),
    ("empagliflozin", "empagliflozin"),          # already a base ingredient
    ("HYDROCORTISONE SODIUM SUCCINATE", "HYDROCORTISONE"),
])
def test_book_term_strips_salt_forms(resolved, expected):
    """_resolve_drug_name_online returns the FDA salt form, which is correct for a label
    lookup and never matches a StatPearls chapter title — so the concept gate rejected it and
    every salt-formulated drug silently lost its chapter."""
    assert _book_term_for_drug(resolved, "") == expected


def test_book_term_falls_back_when_all_tokens_are_salts():
    """Never return an empty search term."""
    assert _book_term_for_drug("SODIUM CHLORIDE", "saline") == "saline"


# ── A retrieved chapter counts as evidence ────────────────────────────────────

def test_procedure_chapter_alone_is_sufficient_evidence():
    """PubMed is intermittently empty for procedure terms. Without counting chapters,
    fetch_success goes False -> fallback_to_llm -> the data block (and a 42k-char chapter)
    is discarded and the answer degrades to a no-evidence card. The disease path has always
    counted `or result.book_monographs`; procedure now matches it."""
    r = ProcedureFetchResult()
    r.book_monographs = [{"title": "Central Venous Catheter Insertion",
                          "url": "https://www.ncbi.nlm.nih.gov/books/NBK557798/",
                          "nbk_id": "NBK557798", "source": "StatPearls", "text": "x" * 42000}]
    # Mirror the final expression in fetch_procedure_data.
    assert bool(r.guideline_abstracts or r.practice_guideline_abstracts or r.book_monographs)


def test_result_classes_carry_book_monographs():
    """Procedure/drug/evidence results must expose the SAME field name the registry and
    prompt engine read (`book_monographs`) — a mismatched name is exactly the defect that
    kept chapters out of the reference list entirely."""
    for cls in (ProcedureFetchResult, DrugFetchResult, EvidenceFetchResult):
        assert hasattr(cls(), "book_monographs"), cls.__name__


# ── The chapter must reach the prompt, whole ──────────────────────────────────

class _Fetched:
    fallback_to_llm = False
    drug_data = None
    disease_data = None
    condition_data = None
    procedure_data = None
    evidence_data = None
    comparative_evidence = None
    comparative_drug_data = []
    comorbidity_data = []
    images = []
    data_sources = []


def _chapter(n_chars: int) -> dict:
    # Distinctive tail so truncation anywhere in the path is detectable.
    body = "CHAPTER-BODY " * (n_chars // 13)
    return {"title": "Central Venous Catheter Insertion",
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK557798/",
            "nbk_id": "NBK557798", "source": "StatPearls",
            "text": body + "DISTINCTIVE-TAIL-MARKER"}


def test_procedure_chapter_reaches_prompt_untruncated(monkeypatch):
    monkeypatch.setattr(settings, "citation_ref_tokens_enabled", True)
    f = _Fetched()
    f.procedure_data = ProcedureFetchResult(fetch_success=True)
    f.procedure_data.book_monographs = [_chapter(40000)]
    block = _build_adaptive_data_block("procedure", f)
    assert "TEXTBOOK / OVERVIEW" in block
    assert "DISTINCTIVE-TAIL-MARKER" in block, (
        "chapter tail missing — something in the prompt path truncated it. Never truncate "
        "chapter text at ANY stage (project CLAUDE.md, ledger: seen 2x)."
    )


def test_drug_chapter_reaches_prompt_untruncated(monkeypatch):
    monkeypatch.setattr(settings, "citation_ref_tokens_enabled", True)
    f = _Fetched()
    f.drug_data = DrugFetchResult(fetch_success=True, indications_raw="indicated for X")
    f.drug_data.book_monographs = [_chapter(32000)]
    block = _build_adaptive_data_block("drug", f)
    assert "TEXTBOOK / OVERVIEW" in block
    assert "DISTINCTIVE-TAIL-MARKER" in block


def test_chapter_absent_from_prompt_when_no_monographs(monkeypatch):
    """Flag-off / no-chapter path must not emit an empty TEXTBOOK header."""
    monkeypatch.setattr(settings, "citation_ref_tokens_enabled", True)
    f = _Fetched()
    f.procedure_data = ProcedureFetchResult(fetch_success=True)
    f.procedure_data.guideline_abstracts = [
        {"pmid": "30000001", "title": "A guideline", "abstract": "text", "journal": "J", "year": 2021}]
    block = _build_adaptive_data_block("procedure", f)
    assert "TEXTBOOK / OVERVIEW" not in block
