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
