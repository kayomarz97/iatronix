"""Tests for evidence_floor.py — EvidenceFloorError, has_minimum_evidence, ensure_evidence."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.citation

from app.services.evidence_floor import (
    EvidenceFloorError,
    has_minimum_evidence,
    ensure_evidence,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _empty_fetched_data(query_type: str = "evidence") -> MagicMock:
    fd = MagicMock()
    fd.query_type = query_type
    fd.fallback_to_llm = False
    fd.drug_data = None
    fd.disease_data = None
    fd.condition_data = None
    fd.procedure_data = None
    fd.evidence_data = None
    fd.comparative_evidence = None
    fd.comparative_drug_data = []
    fd.comorbidity_data = []
    return fd


def _fetched_data_with_pmid(pmid: str = "12345678") -> MagicMock:
    fd = _empty_fetched_data()
    ev = MagicMock()
    ev.clinical_trial_abstracts = [{"pmid": pmid, "title": "Test trial", "abstract": "Test"}]
    ev.systematic_review_abstracts = []
    ev.guideline_abstracts = []
    fd.evidence_data = ev
    return fd


def _fetched_data_with_nice_url() -> MagicMock:
    fd = _empty_fetched_data(query_type="disease")
    disease = MagicMock()
    disease.guideline_abstracts = []
    disease.systematic_review_abstracts = []
    disease.nice_recommendations = [{"url": "https://www.nice.org.uk/guidance/ng136", "title": "Hypertension guideline"}]
    fd.disease_data = disease
    return fd


# ── has_minimum_evidence ──────────────────────────────────────────────────────


class TestHasMinimumEvidence:
    def test_none_input_returns_false(self):
        assert has_minimum_evidence(None) is False

    def test_empty_fetched_data_returns_false(self):
        assert has_minimum_evidence(_empty_fetched_data()) is False

    def test_evidence_with_pmid_returns_true(self):
        assert has_minimum_evidence(_fetched_data_with_pmid()) is True

    def test_evidence_with_nct_id_returns_true(self):
        fd = _empty_fetched_data()
        ev = MagicMock()
        ev.clinical_trial_abstracts = [{"nct_id": "NCT00000001", "title": "Trial"}]
        ev.systematic_review_abstracts = []
        ev.guideline_abstracts = []
        fd.evidence_data = ev
        assert has_minimum_evidence(fd) is True

    def test_nice_recommendation_url_returns_true(self):
        assert has_minimum_evidence(_fetched_data_with_nice_url()) is True

    def test_drug_label_url_returns_true(self):
        fd = _empty_fetched_data(query_type="drug")
        drug = MagicMock()
        drug.guideline_abstracts = []
        drug.systematic_review_abstracts = []
        drug.clinical_trial_abstracts = []
        drug.label_url = "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=abc123"
        fd.drug_data = drug
        assert has_minimum_evidence(fd) is True

    def test_abstract_list_without_pmid_returns_false(self):
        fd = _empty_fetched_data()
        ev = MagicMock()
        ev.clinical_trial_abstracts = [{"title": "No ID", "abstract": "no identifier here"}]
        ev.systematic_review_abstracts = []
        ev.guideline_abstracts = []
        fd.evidence_data = ev
        assert has_minimum_evidence(fd) is False


# ── ensure_evidence ───────────────────────────────────────────────────────────


class TestEnsureEvidence:
    @pytest.mark.asyncio
    async def test_returns_immediately_if_already_has_evidence(self):
        fd = _fetched_data_with_pmid()
        result = await ensure_evidence(fd, "paracetamol toxicity", "drug")
        assert result.fallback_to_llm is False

    @pytest.mark.asyncio
    async def test_raises_evidence_floor_error_when_all_strategies_fail(self):
        fd = _empty_fetched_data()
        failing_result = MagicMock()
        failing_result.fetch_success = False
        failing_result.label_url = None

        with (
            patch(
                "app.services.evidence_floor.asyncio.wait_for",
                new=AsyncMock(return_value=failing_result),
            ),
        ):
            with pytest.raises(EvidenceFloorError):
                await ensure_evidence(fd, "flibbertigibbet syndrome unknown", "evidence")

    @pytest.mark.asyncio
    async def test_succeeds_on_strategy_1_broad_evidence(self):
        fd = _empty_fetched_data()
        good_ev = MagicMock()
        good_ev.fetch_success = True
        good_ev.clinical_trial_abstracts = [{"pmid": "99999999", "title": "Good trial"}]
        good_ev.systematic_review_abstracts = []
        good_ev.guideline_abstracts = []

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return good_ev

        with patch("app.services.evidence_floor.asyncio.wait_for", side_effect=side_effect):
            result = await ensure_evidence(fd, "hypertension treatment", "disease")

        assert result.fallback_to_llm is False
        assert call_count == 1  # succeeds on first strategy

    @pytest.mark.asyncio
    async def test_feature_flag_off_clears_fallback_without_retry(self):
        fd = _empty_fetched_data()
        fd.fallback_to_llm = True
        with patch("app.services.evidence_floor.asyncio.wait_for", new=AsyncMock()) as mock_wf:
            with patch("app.config.settings") as mock_settings:
                mock_settings.evidence_floor_enabled = False
                result = await ensure_evidence(fd, "anything", "general")
        assert result.fallback_to_llm is False
        mock_wf.assert_not_called()

    @pytest.mark.asyncio
    async def test_timeout_on_strategy_falls_through_to_next(self):
        """A timeout on strategy 1 must fall through to strategy 2 and succeed there."""
        fd = _empty_fetched_data()
        good_ev = MagicMock()
        good_ev.fetch_success = True
        good_ev.clinical_trial_abstracts = [{"pmid": "11111111", "title": "Disease trial"}]
        good_ev.systematic_review_abstracts = []
        good_ev.guideline_abstracts = []
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            return good_ev

        # Use a longer query so simplified (first 3 tokens) != original (7 tokens),
        # ensuring strategy 2 is attempted and succeeds at call_count==2.
        long_query = "hypertension treatment guidelines first line therapy review"
        with patch("app.services.evidence_floor.asyncio.wait_for", side_effect=side_effect):
            result = await ensure_evidence(fd, long_query, "disease")

        assert result.fallback_to_llm is False
        assert call_count == 2  # strategy 1 timed out; strategy 2 succeeded
