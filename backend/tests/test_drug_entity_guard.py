"""Regression tests for the 2026-07-27 drug-entity guard.

The `complex`/`general` fetch branch takes entities[0] as the drug, but the extractor often
puts a CONDITION first ("drug of choice for CKD with T2DM and heart failure"). RxNorm's
approximateTerm never signals "not a drug": BOTH "chronic kidney disease" and "acute kidney
injury" resolve to rxcui 891637, "kidney bean allergenic extract" — a real allergenic-extract
ingredient. The pipeline then fetched that product's FDA label, adverse-event profile and
textbook chapter straight into the prompt.

Why the guard sits on the INPUT, not the output:
  - RxNorm's own score cannot discriminate (CKD 12.34 > metformin 11.21).
  - Output-side type checks fail because the resolved concept IS a genuine drug.
  - Lexical similarity fails because legitimate brand->generic resolution has zero overlap
    (jardiance -> empagliflozin).

FALSE POSITIVES are the dangerous direction (a real drug skipped), so the drug list below is
the important half of this file.
"""
import pytest

from app.services.data_fetcher import _looks_like_condition

pytestmark = pytest.mark.citation


CONDITIONS = [
    "chronic kidney disease", "acute kidney injury", "heart failure", "cirrhosis",
    "type 2 diabetes", "nephropathy", "anemia", "anaemia", "pneumonitis",
    "thrombocytopenia", "hematuria", "osteoarthritis", "lymphoma", "sarcoidosis",
    "diabetic ketoacidosis", "myocardial infarction", "sepsis", "septic shock",
]

# Includes salt forms, two-word ingredients and short names — the shapes most likely to trip
# a suffix heuristic.
DRUGS = [
    "metformin", "empagliflozin", "warfarin", "amiodarone", "apixaban", "lithium",
    "vancomycin", "ibuprofen", "labetalol", "atorvastatin", "levodopa", "heparin",
    "morphine", "codeine", "dopamine", "ketamine", "ferrous fumarate",
    "insulin glargine", "sodium bicarbonate", "amoxicillin", "furosemide", "digoxin",
    "soma", "paracetamol", "hydrocortisone sodium succinate",
]


@pytest.mark.parametrize("name", CONDITIONS)
def test_conditions_are_detected(name):
    assert _looks_like_condition(name) is True, f"{name!r} should not reach the drug resolver"


@pytest.mark.parametrize("name", DRUGS)
def test_drugs_are_not_flagged(name):
    """A false positive silently drops a real drug fetch — the dangerous direction."""
    assert _looks_like_condition(name) is False, f"{name!r} wrongly treated as a condition"


def test_empty_input_is_not_a_condition():
    assert _looks_like_condition("") is False
    assert _looks_like_condition(None) is False


def test_suffix_rule_applies_to_head_noun_only():
    """'Ferrous fumarate' must survive even though other tokens could look condition-ish."""
    assert _looks_like_condition("ferrous fumarate") is False
