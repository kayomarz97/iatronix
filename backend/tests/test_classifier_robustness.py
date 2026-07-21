"""Guardrail tests for the classifier + complex-drug crash fix.

Covers three regressions found 2026-07-21:
  1. `DrugFetchResult` has no `drug_name` — the complex-branch drug resolution must use
     generic_name/brand_name safely (AttributeError crash on "CKD hypertension which drugs").
  2. The deterministic comorbidity backstop nudges single-focus types to 'complex'.
  3. `_parse_classification` recovers a valid type from fenced / prose-wrapped model output
     instead of collapsing to 'complex'.

Pure-function tests — no network, no LLM, no DB.
"""

from app.services.data_fetcher import DrugFetchResult, FetchedData
from app.services.query_classifier import (
    _parse_classification,
    apply_classifier_backstop,
    count_named_conditions,
)


# ── 1. Crash fix: DrugFetchResult exposes generic_name/brand_name, never drug_name ──

def test_drugfetchresult_has_no_drug_name_but_has_generic():
    d = DrugFetchResult(generic_name="lisinopril")
    assert not hasattr(d, "drug_name")
    # The safe accessor the complex branch now uses:
    resolved = getattr(d, "generic_name", None) or getattr(d, "brand_name", None) or ""
    assert resolved == "lisinopril"


def test_complex_drug_resolution_pattern_does_not_raise():
    # Mirrors rag_pipeline.py complex-branch resolution — must not raise AttributeError.
    fetched = FetchedData(query_type="complex")
    fetched.drug_data = DrugFetchResult(brand_name="Zestril")
    drug = ""
    if fetched and fetched.drug_data:
        drug = (
            getattr(fetched.drug_data, "generic_name", None)
            or getattr(fetched.drug_data, "brand_name", None)
            or ""
        )
    assert drug == "Zestril"


# ── 2. Comorbidity backstop ──

def test_count_named_conditions():
    assert count_named_conditions("chronic kidney disease, hypertension") == 2
    assert count_named_conditions("chronic kidney disease and hypertension") == 2
    assert count_named_conditions("chronic kidney disease") == 1
    assert count_named_conditions(None) == 0
    assert count_named_conditions("") == 0


def test_backstop_forces_complex_on_two_conditions(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "classify_heuristic_backstop_enabled", True)
    monkeypatch.setattr(settings, "classify_backstop_min_conditions", 2)

    qt, changed = apply_classifier_backstop(
        "evidence", "chronic kidney disease, hypertension", user_forced_type=False
    )
    assert qt == "complex" and changed is True


def test_backstop_noop_on_single_condition(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "classify_heuristic_backstop_enabled", True)
    qt, changed = apply_classifier_backstop(
        "evidence", "chronic kidney disease", user_forced_type=False
    )
    assert qt == "evidence" and changed is False


def test_backstop_respects_user_forced_and_comparative(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "classify_heuristic_backstop_enabled", True)
    # user-forced type is never overridden
    qt, changed = apply_classifier_backstop("drug", "ckd, htn", user_forced_type=True)
    assert qt == "drug" and changed is False
    # comparative (legitimate two-entity compare) is never touched
    qt, changed = apply_classifier_backstop("comparative", "ckd, htn", user_forced_type=False)
    assert qt == "comparative" and changed is False


def test_backstop_disabled_is_noop(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "classify_heuristic_backstop_enabled", False)
    qt, changed = apply_classifier_backstop("evidence", "ckd, htn", user_forced_type=False)
    assert qt == "evidence" and changed is False


# ── 3. Robust classification parsing ──

def test_parse_plain_json():
    assert _parse_classification('{"type": "drug", "confidence": 0.9}')[0] == "drug"


def test_parse_fenced_json():
    assert _parse_classification('```json\n{"type": "evidence", "confidence": 0.8}\n```')[0] == "evidence"


def test_parse_prose_wrapped_object():
    txt = 'Sure! Here is the classification: {"type": "disease", "confidence": 0.7} — hope that helps.'
    assert _parse_classification(txt)[0] == "disease"


def test_parse_bare_type_in_freetext():
    # Realistic malformed output: key/value present but not a valid JSON object.
    qt, conf = _parse_classification('type: comparative, confidence: 0.85')
    assert qt == "comparative"


def test_parse_garbage_falls_back_to_complex():
    qt, conf = _parse_classification("I cannot determine this.")
    assert qt == "complex" and conf == 0.4


def test_parse_invalid_type_falls_back():
    qt, _ = _parse_classification('{"type": "general", "confidence": 0.9}')
    assert qt == "complex"


# ── R2: structured validation (provider-neutral) ──

def test_normalize_query_type():
    from app.services.query_classifier import normalize_query_type
    assert normalize_query_type("DRUG") == "drug"
    assert normalize_query_type("  evidence ") == "evidence"
    assert normalize_query_type("general") == "complex"   # legacy → complex
    assert normalize_query_type("nonsense") == "complex"
    assert normalize_query_type(None) == "complex"


def test_classification_result_coerces_and_clamps():
    from app.services.query_classifier import ClassificationResult
    r = ClassificationResult(query_type="GENERAL", confidence=9.9)
    assert r.query_type == "complex" and r.confidence == 1.0
    r2 = ClassificationResult(query_type="drug", confidence=-2)
    assert r2.query_type == "drug" and r2.confidence == 0.0
    r3 = ClassificationResult(query_type="evidence", confidence="not-a-number")
    assert r3.query_type == "evidence" and r3.confidence == 0.6


# ── R6: analysis cache key ──

def test_analysis_cache_key_normalizes():
    from app.services.cache import _analysis_cache_key
    # Same query, different punctuation/case/whitespace → same key.
    a = _analysis_cache_key("CKD hypertension which drugs to use?")
    b = _analysis_cache_key("ckd  hypertension which drugs to use")
    assert a == b
    assert a.startswith("analysis:v")
