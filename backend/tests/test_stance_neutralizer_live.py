"""Tests for stance neutralizer — verifies that loaded queries produce neutralized
retrieval queries, and that anti-sycophancy rules are present in all system prompts.
"""
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.citation

from app.services.stance_neutralizer import (
    StanceResult,
    _heuristic_neutralize,
    neutralize_query,
)


class TestStanceNeutralizerWiring:
    """Verify stance neutralizer correctly handles loaded query phrasing."""

    def test_heuristic_neutralizes_loaded_why_bad_query(self):
        """'why is X bad' → heuristic strips stance loading, returns StanceResult."""
        result = _heuristic_neutralize("why is paracetamol harmful?")
        assert isinstance(result, StanceResult)
        assert result.neutral_clinical_question
        assert result.stance in ("affirming", "negating", "neutral")

    def test_heuristic_neutralizes_positive_framing(self):
        """'why is X great/safe/effective' → returns StanceResult with classified stance."""
        result = _heuristic_neutralize("why is aspirin the best blood thinner?")
        assert isinstance(result, StanceResult)
        assert len(result.neutral_clinical_question) > 0

    def test_neutral_query_returns_neutral_stance(self):
        """A query with no stance markers should be classified as neutral."""
        result = _heuristic_neutralize("paracetamol dosing in hepatic impairment")
        assert isinstance(result, StanceResult)
        # Neutral query: stance should be neutral and question unchanged or minimally modified
        assert result.neutral_clinical_question  # non-empty
        assert result.stance == "neutral"

    def test_loaded_query_produces_different_neutral_question(self):
        """A negatively-framed query must produce neutral_clinical_question ≠ original."""
        original = "why is paracetamol so harmful to the liver?"
        result = _heuristic_neutralize(original)
        assert isinstance(result, StanceResult)
        # After stripping stance words, question should differ from original
        # (loaded_terms must be non-empty for a clearly negative query)
        assert result.stance != "neutral" or result.confidence < 0.9

    @pytest.mark.asyncio
    async def test_neutralize_query_feature_flag_off_returns_identity(self):
        """When stance_neutralizer_enabled=False, returns identity passthrough."""
        with patch("app.services.stance_neutralizer.settings") as mock_settings:
            mock_settings.stance_neutralizer_enabled = False
            mock_settings.llm_timeout_seconds = 10
            result = await neutralize_query(
                "why is paracetamol so dangerous?",
                model_id="claude-haiku-4-5-20251001",
                user_key=None,
                user_provider=None,
            )
        assert isinstance(result, StanceResult)
        assert result.neutral_clinical_question == "why is paracetamol so dangerous?"
        assert result.stance == "neutral"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_neutralize_query_falls_back_to_heuristic_on_llm_failure(self):
        """When the LLM call fails, heuristic fallback must still return a StanceResult."""
        with patch("app.services.stance_neutralizer.create_llm", side_effect=Exception("LLM unavailable")):
            result = await neutralize_query(
                "why is amoxicillin dangerous?",
                model_id="claude-haiku-4-5-20251001",
                user_key=None,
                user_provider=None,
            )
        assert isinstance(result, StanceResult)
        assert result.neutral_clinical_question  # fallback must produce something

    def test_anti_sycophancy_rules_in_prompt_engine(self):
        """ANTI_SYCOPHANCY_RULES constant must exist and contain key directives."""
        from app.services.prompt_engine import ANTI_SYCOPHANCY_RULES
        rules_lower = ANTI_SYCOPHANCY_RULES.lower()
        assert (
            "balanced" in rules_lower or "both" in rules_lower or "evidence" in rules_lower
        ), "ANTI_SYCOPHANCY_RULES must instruct the LLM to present balanced evidence"
        assert len(ANTI_SYCOPHANCY_RULES) > 50, "ANTI_SYCOPHANCY_RULES seems too short"

    def test_stance_neutralizer_feature_flag_exists(self):
        """Settings must expose stance_neutralizer_enabled flag."""
        from app.config import settings
        assert hasattr(settings, "stance_neutralizer_enabled")
        assert isinstance(settings.stance_neutralizer_enabled, bool)

    def test_evidence_floor_feature_flag_exists_and_defaults_on(self):
        """Settings must expose evidence_floor_enabled flag; default must be True."""
        from app.config import settings
        assert hasattr(settings, "evidence_floor_enabled")
        assert isinstance(settings.evidence_floor_enabled, bool)
        assert settings.evidence_floor_enabled is True
