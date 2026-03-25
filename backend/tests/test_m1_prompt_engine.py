"""
M1 tests: BLUF schema fields + hardened JSON prompts.

Run: pytest tests/test_m1_prompt_engine.py -v
"""
import json
import re

import pytest
from pydantic import ValidationError

# ──────────────────────────────────────────────
# Schema tests
# ──────────────────────────────────────────────


class TestDiseaseResponseSchema:
    def test_bluf_field_exists_and_defaults_none(self):
        from app.schemas.query import DiseaseResponse, TreatmentSection

        d = DiseaseResponse(
            disease_name="Test",
            treatment=TreatmentSection(),
        )
        assert hasattr(d, "bluf")
        assert d.bluf is None

    def test_additional_clinical_context_field_exists_and_defaults_none(self):
        from app.schemas.query import DiseaseResponse, TreatmentSection

        d = DiseaseResponse(
            disease_name="Test",
            treatment=TreatmentSection(),
        )
        assert hasattr(d, "additional_clinical_context")
        assert d.additional_clinical_context is None

    def test_bluf_accepts_string(self):
        from app.schemas.query import DiseaseResponse, TreatmentSection

        d = DiseaseResponse(
            disease_name="Hypertension",
            bluf="First-line: ACE inhibitor or ARB + thiazide diuretic per JNC 8.",
            treatment=TreatmentSection(),
        )
        assert d.bluf == "First-line: ACE inhibitor or ARB + thiazide diuretic per JNC 8."

    def test_additional_clinical_context_accepts_string(self):
        from app.schemas.query import DiseaseResponse, TreatmentSection

        d = DiseaseResponse(
            disease_name="Hypertension",
            additional_clinical_context="Consider SGLT2i if concurrent diabetes.",
            treatment=TreatmentSection(),
        )
        assert d.additional_clinical_context == "Consider SGLT2i if concurrent diabetes."

    def test_backward_compat_no_new_fields(self):
        """Existing payloads without bluf/additional_clinical_context still parse."""
        from app.schemas.query import DiseaseResponse

        payload = {
            "disease_name": "Sepsis",
            "treatment": {
                "first_line": [],
                "second_line": [],
                "adjunctive": [],
                "non_pharmacological": [],
            },
        }
        d = DiseaseResponse(**payload)
        assert d.bluf is None
        assert d.additional_clinical_context is None

    def test_other_response_types_unchanged(self):
        """GeneralResponse does not have bluf; DrugResponse now has it (added in M3a BLUF)."""
        from app.schemas.query import DrugResponse, GeneralResponse

        # DrugResponse gained bluf in the drug BLUF feature
        dr = DrugResponse(drug_name="Metformin")
        assert hasattr(dr, "bluf")
        assert dr.bluf is None

        gr = GeneralResponse(summary="test", confidence="high")
        assert not hasattr(gr, "bluf")


# ──────────────────────────────────────────────
# Prompt hardening tests
# ──────────────────────────────────────────────

SHORTHAND_PATTERNS = [
    r"\[same format\]",
    r"\[same EvidencedClaim format\]",
    r"\[EvidencedClaim format\]",
]

ALL_PROMPT_NAMES = [
    "DRUG_PROMPT",
    "DISEASE_PROMPT",
    "COMPARATIVE_PROMPT",
    "PROCEDURE_PROMPT",
    "EVIDENCE_PROMPT",
    "GENERAL_PROMPT",
    "DRUG_FORMAT_PROMPT",
    "DISEASE_FORMAT_PROMPT",
    "COMPARATIVE_FORMAT_PROMPT",
    "PROCEDURE_FORMAT_PROMPT",
    "EVIDENCE_FORMAT_PROMPT",
]


def get_prompt(name: str) -> str:
    import app.services.prompt_engine as pe
    return getattr(pe, name)


class TestNoShorthands:
    @pytest.mark.parametrize("prompt_name", ALL_PROMPT_NAMES)
    @pytest.mark.parametrize("pattern", SHORTHAND_PATTERNS)
    def test_no_shorthand_in_prompt(self, prompt_name, pattern):
        prompt = get_prompt(prompt_name)
        assert not re.search(pattern, prompt, re.I), (
            f"{prompt_name} still contains shorthand '{pattern}' — "
            "expand to explicit field spec"
        )


def _rendered(name: str) -> str:
    """Return the prompt with json_contract_rules injected (simulates runtime render)."""
    import app.services.prompt_engine as pe
    raw = getattr(pe, name)
    if "{json_contract_rules}" in raw:
        return raw.replace("{json_contract_rules}", pe.JSON_CONTRACT_RULES)
    return raw


class TestJsonContractRules:
    """Every prompt must contain the JSON CONTRACT RULES block (after render)."""

    @pytest.mark.parametrize("prompt_name", ALL_PROMPT_NAMES)
    def test_json_contract_rules_present(self, prompt_name):
        prompt = _rendered(prompt_name)
        assert "JSON CONTRACT RULES" in prompt, (
            f"{prompt_name} is missing the JSON CONTRACT RULES block"
        )

    @pytest.mark.parametrize("prompt_name", ALL_PROMPT_NAMES)
    def test_no_na_string_rule_present(self, prompt_name):
        prompt = _rendered(prompt_name)
        assert '"N/A"' in prompt or "N/A" in prompt, (
            f"{prompt_name} should mention N/A prohibition"
        )


class TestDiseaseBLUF:
    def test_disease_prompt_contains_bluf_field(self):
        import app.services.prompt_engine as pe
        assert '"bluf"' in pe.DISEASE_PROMPT

    def test_disease_format_prompt_contains_bluf_field(self):
        import app.services.prompt_engine as pe
        assert '"bluf"' in pe.DISEASE_FORMAT_PROMPT

    def test_disease_prompt_contains_additional_clinical_context(self):
        import app.services.prompt_engine as pe
        assert '"additional_clinical_context"' in pe.DISEASE_PROMPT

    def test_disease_format_prompt_contains_additional_clinical_context(self):
        import app.services.prompt_engine as pe
        assert '"additional_clinical_context"' in pe.DISEASE_FORMAT_PROMPT

    def test_disease_prompt_no_mandatory_order(self):
        import app.services.prompt_engine as pe
        assert "MANDATORY CLINICAL ORDER" not in pe.DISEASE_PROMPT

    def test_disease_format_prompt_no_mandatory_order(self):
        import app.services.prompt_engine as pe
        assert "MANDATORY CLINICAL ORDER" not in pe.DISEASE_FORMAT_PROMPT


class TestEvidencePromptConstraints:
    def test_guideline_status_templates_in_evidence_prompt(self):
        import app.services.prompt_engine as pe
        # Must hint at constrained templates
        assert "No formal guideline" in pe.EVIDENCE_PROMPT

    def test_guideline_status_templates_in_evidence_format_prompt(self):
        import app.services.prompt_engine as pe
        assert "No formal guideline" in pe.EVIDENCE_FORMAT_PROMPT

    def test_pmid_numeric_rule_in_evidence_prompt(self):
        import app.services.prompt_engine as pe
        assert "numeric" in pe.EVIDENCE_PROMPT.lower() or "PMID:" in pe.EVIDENCE_PROMPT

    def test_pmid_numeric_rule_in_evidence_format_prompt(self):
        import app.services.prompt_engine as pe
        assert "numeric" in pe.EVIDENCE_FORMAT_PROMPT.lower() or "PMID:" in pe.EVIDENCE_FORMAT_PROMPT


class TestProcedureStepsConstraints:
    def test_procedure_steps_sequential_rule(self):
        import app.services.prompt_engine as pe
        assert "step_number" in pe.PROCEDURE_PROMPT
        assert "step_number" in pe.PROCEDURE_FORMAT_PROMPT

    def test_procedure_steps_start_at_1(self):
        import app.services.prompt_engine as pe
        # The prompt must instruct steps start at 1
        assert "start at 1" in pe.PROCEDURE_PROMPT or "step_number\": 1" in pe.PROCEDURE_PROMPT


class TestGeneralPromptConstraints:
    def test_key_points_no_markdown_rule(self):
        import app.services.prompt_engine as pe
        # key_points rule: no markdown bullets
        assert "key_points" in pe.GENERAL_PROMPT
        assert "bullet" in pe.GENERAL_PROMPT.lower() or "prefix" in pe.GENERAL_PROMPT.lower() or "markdown" in pe.GENERAL_PROMPT.lower()

    def test_related_drugs_generic_names_rule(self):
        import app.services.prompt_engine as pe
        assert "generic" in pe.GENERAL_PROMPT.lower() or "brand" in pe.GENERAL_PROMPT.lower()


class TestBuildPromptIntegration:
    """build_prompt returns a non-empty string for all query types."""

    @pytest.mark.parametrize("query_type", ["drug", "disease", "comparative", "procedure", "evidence", "general"])
    def test_build_prompt_generate_mode(self, query_type):
        from app.services.prompt_engine import build_prompt

        result = build_prompt(
            query="test query about hypertension",
            query_type=query_type,
            fetched_data=None,
            vector_results=None,
        )
        assert isinstance(result, str)
        assert len(result) > 100

    def test_build_prompt_highlights_mode(self):
        from app.services.prompt_engine import build_prompt

        result = build_prompt(
            query="sepsis management",
            query_type="disease",
            intent="highlights",
        )
        assert isinstance(result, str)
        assert "sepsis management" in result.lower() or "sepsis" in result.lower()
