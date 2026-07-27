"""The specialist-answer rubric, and proof that it discriminates.

Answer SHAPE was the one dimension the retrieval/citation harnesses could not see. This locks
the rubric that measures it. The scorer is deterministic ON PURPOSE: the generated answer is the
variable under test, so the scoring must not also be a matter of opinion.

The two fixture arms are a model's output WITHOUT evidence-tier labels (flat sources) and WITH
them. A rubric that cannot separate those two is not measuring anything.
"""
import json
from pathlib import Path

import pytest

from app.services.answer_judge import judge

pytestmark = pytest.mark.citation

FIXTURES = Path(__file__).parent / "fixtures" / "answer_quality_arms.json"


@pytest.fixture(scope="module")
def arms():
    return json.loads(FIXTURES.read_text())


def test_rubric_separates_tier_aware_from_flat_answer(arms):
    tiers = arms["tier_by_token"]
    off = judge(arms["off"], tiers, arms["expected_sections"])
    on = judge(arms["on"], tiers, arms["expected_sections"])
    assert on["overall"] > off["overall"], "rubric cannot tell a specialist answer from a flat one"
    assert on["overall"] >= 0.95 and off["overall"] <= 0.75


def test_flat_answer_fails_the_specialist_rules(arms):
    off = judge(arms["off"], arms["tier_by_token"], arms["expected_sections"])
    assert off["scores"]["R1_evidence_weighting"] == 0.0
    assert off["scores"]["R2_loe_correct"] == 0.0
    assert off["scores"]["R3_no_registration_as_evidence"] == 0.0


def test_tier_aware_answer_passes_all(arms):
    on = judge(arms["on"], arms["tier_by_token"], arms["expected_sections"])
    for rule in ("R1_evidence_weighting", "R2_loe_correct",
                 "R3_no_registration_as_evidence", "R6_no_filler"):
        assert on["scores"][rule] == 1.0, rule


def test_registration_backing_an_efficacy_claim_is_caught():
    """The single most dangerous failure: citing a trial that never reported as if it were
    evidence the drug works."""
    answer = {"bluf": {"headline": "X reduces mortality (guideline-level, randomised)."},
              "sections": [{"title": "Efficacy", "content_items": [
                  {"text": "X reduces mortality in advanced disease.",
                   "source": "NCT01", "ref_token": "REF_9", "loe": "III"}]}]}
    res = judge(answer, {"REF_9": "R"}, expected_sections=1)
    assert res["scores"]["R3_no_registration_as_evidence"] == 0.0


def test_low_tier_only_answer_must_state_the_limitation():
    base = {"sections": [{"title": "Evidence", "content_items": [
        {"text": "Y may help.", "source": "Case report", "ref_token": "REF_1", "loe": "III"}]}]}
    silent = {**base, "bluf": {"headline": "Y is effective.", "body": "Y works well."}}
    honest = {**base, "bluf": {"headline": "Evidence for Y is limited to case reports.",
                               "body": "Only low-quality evidence is available; efficacy is uncertain."}}
    assert judge(silent, {"REF_1": "D"}, 1)["scores"]["R4_calibrated_hedging"] == 0.0
    assert judge(honest, {"REF_1": "D"}, 1)["scores"]["R4_calibrated_hedging"] == 1.0


def test_filler_is_penalised():
    a = {"bluf": {"headline": "Great question! Z is effective (randomised evidence)."},
         "sections": [{"title": "S", "content_items": [
             {"text": "Z works.", "source": "RCT", "ref_token": "REF_1", "loe": "I"}]}]}
    assert judge(a, {"REF_1": "B"}, 1)["scores"]["R6_no_filler"] == 0.0


# ── Independent-generator arms (2026-07-28) ──────────────────────────────────

INDEPENDENT = Path(__file__).parent / "fixtures" / "answer_quality_arms_independent.json"


@pytest.fixture(scope="module")
def indep():
    return json.loads(INDEPENDENT.read_text())


def test_independent_generation_still_favours_tier_labels(indep):
    """Arms generated BLIND by a separate agent (it never saw the rubric).

    This is the honest measurement. The hand-written arms scored 0.50 -> 1.00; independently
    generated ones score 0.83 -> 1.00, because a competent model already uses strength words
    when the source TITLES contain them ("randomised controlled trial", "meta-analysis").
    The real, reproducible gain is LOE calibration (R2), not prose vocabulary.
    """
    tiers = indep["tier_by_token"]
    off = judge(indep["off"], tiers, indep["expected_sections"])
    on = judge(indep["on"], tiers, indep["expected_sections"])
    assert on["overall"] > off["overall"]
    assert off["scores"]["R2_loe_correct"] == 0.0   # registration + case report given LOE II
    assert on["scores"]["R2_loe_correct"] == 1.0


def test_disclaiming_a_registration_is_not_an_r3_violation():
    """A claim that explicitly REFUSES to treat a registration as evidence is correct
    specialist behaviour. The first version of R3 matched 'is effective' inside
    '...is NOT evidence that X is effective' and penalised the ideal sentence."""
    answer = {"bluf": {"headline": "Guideline-level evidence supports X (randomised)."},
              "sections": [{"title": "Evidence gaps", "content_items": [
                  {"text": "NCT01 registers a trial with no posted results. It is not evidence "
                           "that X is effective in this population.",
                   "source": "NCT01", "ref_token": "REF_1", "loe": "III"}]}]}
    res = judge(answer, {"REF_1": "R"}, expected_sections=1)
    assert res["scores"]["R3_no_registration_as_evidence"] == 1.0


def test_asserted_efficacy_from_registration_still_caught():
    answer = {"bluf": {"headline": "X works (randomised)."},
              "sections": [{"title": "Efficacy", "content_items": [
                  {"text": "X reduces mortality in advanced disease.",
                   "source": "NCT01", "ref_token": "REF_1", "loe": "III"}]}]}
    res = judge(answer, {"REF_1": "R"}, expected_sections=1)
    assert res["scores"]["R3_no_registration_as_evidence"] == 0.0
