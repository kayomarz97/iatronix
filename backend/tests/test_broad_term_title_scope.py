"""Regression tests for the BROAD-term title scope lever (2026-08-02).

Defect it pins: every PubMed fetch pairs a STRICT term (filtered by [pt]) with a BROAD
free-text fallback carrying no publication-type filter. On `[Title/Abstract]` that broad term
matches a passing MENTION, so a CKD query returns the ACC/AHA HYPERTENSION guideline and a
pregnancy query returns an acne guideline. Probed live on 2026-08-02 — see
settings.broad_term_title_scope_enabled.

The load-bearing assertion is the NEGATIVE one: the strict [pt] terms and the journal terms
must keep [Title/Abstract]. Probing showed those are already clean, so narrowing them would
cost recall and buy nothing.
"""
import asyncio

import pytest

import app.services.data_fetcher as df
from app.config import settings


@pytest.fixture
def scope_on(monkeypatch):
    monkeypatch.setattr(settings, "broad_term_title_scope_enabled", True)


@pytest.fixture
def scope_off(monkeypatch):
    monkeypatch.setattr(settings, "broad_term_title_scope_enabled", False)


def test_helper_off_is_byte_identical(scope_off):
    assert df._broad_scope_field() == "[Title/Abstract]"


def test_helper_on_restricts_to_title(scope_on):
    assert df._broad_scope_field() == "[Title]"


def _capture_terms(monkeypatch):
    """Run fetch_disease_data with every network call stubbed, returning the esearch terms."""
    seen: list[str] = []

    async def fake_esearch_throttled(client, term, retmax, sort=None):
        seen.append(term)
        return []

    async def anoop(*a, **kw):
        return None

    async def alist(*a, **kw):
        return []

    async def atuple(*a, **kw):
        return ([], set())

    monkeypatch.setattr(df, "_pubmed_esearch_throttled", fake_esearch_throttled)
    monkeypatch.setattr(df, "_pubmed_esearch_recent_guidelines", alist)
    monkeypatch.setattr(df, "_fetch_nice", alist)
    monkeypatch.setattr(df, "_fetch_medlineplus", anoop)
    monkeypatch.setattr(df, "_fetch_semantic_scholar", alist)
    monkeypatch.setattr(df, "_fetch_clinicaltrials", alist)
    monkeypatch.setattr(df, "_fetch_book_monographs", alist)
    monkeypatch.setattr(df, "_pubmed_efetch", atuple)

    asyncio.run(df.fetch_disease_data("chronic kidney disease"))
    return seen


def _broad(terms):
    """The broad terms are exactly those with no [pt] publication-type filter."""
    return [t for t in terms if "[pt]" not in t]


def _strict(terms):
    return [t for t in terms if "[pt]" in t]


def test_broad_terms_are_title_scoped_when_on(monkeypatch, scope_on):
    terms = _capture_terms(monkeypatch)
    broad = _broad(terms)
    assert broad, "expected at least one broad free-text term"
    for t in broad:
        assert "chronic kidney disease[Title]" in t, t
        assert "[Title/Abstract]" not in t, t


def test_strict_pt_terms_are_never_narrowed(monkeypatch, scope_on):
    """The negative assertion: narrowing these would cost recall for no measured gain."""
    terms = _capture_terms(monkeypatch)
    strict = _strict(terms)
    assert strict, "expected at least one [pt]-filtered term"
    for t in strict:
        assert "chronic kidney disease[Title/Abstract]" in t, t


def test_flag_off_leaves_every_term_unchanged(monkeypatch, scope_off):
    for t in _capture_terms(monkeypatch):
        assert "chronic kidney disease[Title/Abstract]" in t, t


def test_lever_adds_no_esearch_calls(monkeypatch, scope_on, scope_off):
    """NCBI throttling has cost this repo weeks of empty data — the lever RE-SCOPES existing
    calls and must never add one. (.claude/rules/mistakes.md, 2026-07-28)"""
    monkeypatch.setattr(settings, "broad_term_title_scope_enabled", False)
    n_off = len(_capture_terms(monkeypatch))
    monkeypatch.setattr(settings, "broad_term_title_scope_enabled", True)
    n_on = len(_capture_terms(monkeypatch))
    assert n_on == n_off
