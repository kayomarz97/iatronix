"""Regression tests for the 2026-07-28 evidence-tier answer-shape lever.

The data block handed the model every source FLAT — title, journal, year, abstract — so a
Cochrane meta-analysis, a practice guideline, a trial REGISTRATION and a single case report
were indistinguishable. ranking.py already computed study-type/recency scores for ORDERING and
discarded them before prompt assembly, so the model had no way to weight evidence. That is what
made prose read like a literature summary rather than a specialist's answer.

A WRONG tier label is worse than none — it actively misleads the model — so classification
correctness is the core of this file.
"""
import pytest

from app.config import settings
from app.services.ranking import evidence_tier, evidence_tier_line

pytestmark = pytest.mark.citation


@pytest.fixture
def tiers_on(monkeypatch):
    monkeypatch.setattr(settings, "evidence_tier_labels_enabled", True)


# ── Classification correctness ────────────────────────────────────────────────

@pytest.mark.parametrize("article,source_type,expected", [
    ({"title": "2023 ACC/AHA practice guideline for AF", "year": 2023}, None, "A"),
    ({"title": "Systematic review and meta-analysis of SGLT2 inhibitors", "year": 2022}, None, "A"),
    ({"title": "A randomized controlled trial of empagliflozin", "year": 2021}, None, "B"),
    ({"title": "Retrospective cohort study of warfarin outcomes", "year": 2019}, None, "C"),
    ({"title": "Case report: amiodarone-induced thyrotoxicosis", "year": 1996}, None, "D"),
    ({"title": "Effect of X on Y", "nct_id": "NCT01234567"}, "clinical_trial", "R"),
    ({"title": "Effect of X", "nct_id": "NCT01", "has_results": True}, "clinical_trial", "B"),
    ({"title": "Central Venous Catheter Insertion"}, "ncbi_books", "T"),
    ({"title": "Metformin label"}, "fda_label", "A"),
])
def test_tier_classification(article, source_type, expected):
    assert evidence_tier(article, source_type)[0] == expected


def test_publication_types_drive_classification():
    """PubMed's own PublicationType list is authoritative and beats title text.

    `pub_types` was NEVER extracted from the efetch XML, so _score_study_type had only
    title/abstract text to sniff and mislabelled real RCTs — a trial titled "COmbinatioN
    effect of FInerenone anD EmpaglifloziN..." scored as a case report. That degraded
    evidence RANKING app-wide, not just these labels.
    """
    rct = {"title": "COmbinatioN effect of FInerenone anD EmpaglifloziN in CKD",
           "pub_types": ["Journal Article", "Randomized Controlled Trial"], "year": 2024}
    assert evidence_tier(rct)[0] == "B"

    meta = {"title": "Comparative efficacy of SGLT2 inhibitor class members",
            "pub_types": ["Journal Article", "Network Meta-Analysis"], "year": 2023}
    assert evidence_tier(meta)[0] == "A"


def test_registration_is_marked_not_evidence():
    """A registration is a protocol. It must never read as evidence that something works."""
    tier, label = evidence_tier({"title": "T", "nct_id": "NCT01234567"}, "clinical_trial")
    assert tier == "R"
    assert "no posted results" in label.lower()


def test_old_source_is_flagged_for_currency():
    line = evidence_tier_line({"title": "Case report: X", "year": 1996})
    assert "verify still current" in line


def test_recent_source_marked_recent():
    from datetime import datetime
    line = evidence_tier_line({"title": "A guideline for X", "year": datetime.now().year})
    assert "recent" in line


# ── Prompt wiring ─────────────────────────────────────────────────────────────

def test_rule_absent_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "evidence_tier_labels_enabled", False)
    from app.services.prompt_engine import _maybe_evidence_tier_rule
    assert _maybe_evidence_tier_rule() == ""


def test_rule_present_and_explains_every_tier(tiers_on):
    """The rule must define every tier letter the data block can emit, or the model is told
    to weight by a scale it was never given."""
    from app.services.prompt_engine import _maybe_evidence_tier_rule
    rule = _maybe_evidence_tier_rule()
    assert "EVIDENCE WEIGHTING" in rule
    for letter in ("A", "B", "C", "D", "R", "T"):
        assert f"{letter} =" in rule or f"Tier {letter}" in rule, f"tier {letter} unexplained"


def test_rule_forbids_registration_as_evidence(tiers_on):
    from app.services.prompt_engine import _maybe_evidence_tier_rule
    assert "REGISTRATION" in _maybe_evidence_tier_rule()


# ── Provider context guard ────────────────────────────────────────────────────

def test_data_block_bounded_for_cerebras_context(monkeypatch):
    """Cerebras gpt-oss-120b (the DEFAULT provider) has a 32,768-token context.
    book_monograph_char_budget alone allows ~22.5k tokens of chapter text, and once chapters
    started appearing on procedure/drug/evidence queries too, large blocks became the norm.
    The block must stay inside prompt_data_block_char_budget so system prompt + output fit."""
    from app.services.prompt_engine import _monograph_budget
    monkeypatch.setattr(settings, "prompt_data_block_char_budget", 88000)
    monkeypatch.setattr(settings, "book_monograph_char_budget", 90000)
    parts = ["x" * 30000]
    assert _monograph_budget(parts) == 58000            # only the room that is left
    assert _monograph_budget(["x" * 95000]) == 0        # never negative
    assert _monograph_budget([]) == 88000               # capped by the overall budget


def test_monograph_budget_never_exceeds_static_cap(monkeypatch):
    from app.services.prompt_engine import _monograph_budget
    monkeypatch.setattr(settings, "prompt_data_block_char_budget", 200000)
    monkeypatch.setattr(settings, "book_monograph_char_budget", 90000)
    assert _monograph_budget([]) == 90000


def test_top_chapter_survives_whole_under_budget(monkeypatch):
    """Chapters arrive ranked best-first; only the LAST, least-relevant overflow chapter may be
    head-truncated. Truncating the TOP chapter is what the never-truncate rule forbids
    (project CLAUDE.md, ledger seen 2x)."""
    from app.services.prompt_engine import _format_monographs
    top = {"title": "Top", "url": "https://www.ncbi.nlm.nih.gov/books/NBK1/",
           "nbk_id": "NBK1", "source": "StatPearls", "text": "A" * 40000 + "TOP-TAIL"}
    tail = {"title": "Overflow", "url": "https://www.ncbi.nlm.nih.gov/books/NBK2/",
            "nbk_id": "NBK2", "source": "StatPearls", "text": "B" * 40000 + "OVERFLOW-TAIL"}
    out = _format_monographs([top, tail], None, budget=50000)
    assert "TOP-TAIL" in out, "top chapter was truncated"
    assert "OVERFLOW-TAIL" not in out, "overflow chapter should be trimmed, not the top one"


def test_rule_states_an_loe_for_every_tier(monkeypatch):
    """Every tier the data block can emit must have an explicit loe mapping in the rule.

    Found 2026-07-28 by a blind multi-query generation run: the rule said
    "Tier A/B -> I, Tier C -> II, Tier D/R -> III" and said NOTHING about Tier T, so the
    generator guessed III for a textbook chapter while the rubric expects II. An unstated
    mapping produces inconsistent loe on chapter-grounded answers — which, since the
    2026-07-27 coverage levers, is most of them.
    """
    monkeypatch.setattr(settings, "evidence_tier_labels_enabled", True)
    from app.services.prompt_engine import _maybe_evidence_tier_rule
    rule = _maybe_evidence_tier_rule()
    assert "Tier T -> II" in rule, "Tier T has no stated loe — the model will guess"
    assert "Tier R -> III" in rule
    assert "Tier A/B -> I" in rule and "Tier C -> II" in rule and "Tier D -> III" in rule


# ── Tier-aware abstract capping ───────────────────────────────────────────────

def _abs(title, pts, year, n=900):
    return {"title": title, "pub_types": pts, "year": year, "abstract": "x" * n}


ABSTRACTS = [
    _abs("Case report of X", ["Case Reports"], 2024),
    _abs("Systematic review of X", ["Systematic Review"], 2021),
    _abs("RCT of X", ["Randomized Controlled Trial"], 2020),
    _abs("Narrative review", ["Review"], 2025),
]


def test_capping_prefers_stronger_designs_over_mere_recency(monkeypatch):
    """_cap_abstracts sorted by RECENCY ONLY, so a 2024 case report displaced a 2021 systematic
    review from the prompt budget — the composition problem behind "~half the retrieved evidence
    is Tier D/R". Only meaningful because pub_types is now parsed from the efetch XML."""
    monkeypatch.setattr(settings, "evidence_tier_labels_enabled", True)
    from app.services.data_fetcher import _cap_abstracts
    kept = {a["title"] for a in _cap_abstracts(ABSTRACTS, 1900)}
    assert kept == {"Systematic review of X", "RCT of X"}, kept


def test_capping_falls_back_to_recency_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "evidence_tier_labels_enabled", False)
    from app.services.data_fetcher import _cap_abstracts
    kept = {a["title"] for a in _cap_abstracts(ABSTRACTS, 1900)}
    assert kept == {"Narrative review", "Case report of X"}, kept


def test_capping_is_a_pure_reordering_no_articles_lost(monkeypatch):
    """Recall must be untouched BY CONSTRUCTION — this is why tier-aware capping was chosen over
    adding a [pt]-filtered esearch (which would breach the documented 4-call NCBI bound)."""
    monkeypatch.setattr(settings, "evidence_tier_labels_enabled", True)
    from app.services.data_fetcher import _cap_abstracts
    out = _cap_abstracts(ABSTRACTS, 99999)
    assert len(out) == len(ABSTRACTS)
    assert {a["title"] for a in out} == {a["title"] for a in ABSTRACTS}


def test_capping_survives_missing_pub_types(monkeypatch):
    """Older cached articles predate the pub_types fix and have no such key."""
    monkeypatch.setattr(settings, "evidence_tier_labels_enabled", True)
    from app.services.data_fetcher import _cap_abstracts
    legacy = [{"title": "No metadata", "year": 2022, "abstract": "y" * 100}]
    assert _cap_abstracts(legacy, 9999)[0]["title"] == "No metadata"
