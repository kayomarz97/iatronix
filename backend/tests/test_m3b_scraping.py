"""
M3b tests: scraping mode pipeline + MedIndia URL safety.

Run: pytest tests/test_m3b_scraping.py -v
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ──────────────────────────────────────────────
# MedIndia URL encoding safety
# ──────────────────────────────────────────────


class TestMedindiaUrlEncoding:
    def test_drug_name_with_special_chars_is_encoded(self):
        """Drug names with &, =, # etc. must not break the URL."""
        from app.services.data_fetcher import _build_medindia_url

        url = _build_medindia_url("co-amoxiclav & clavulanate")
        assert "&" not in url.split("?", 1)[-1].replace("drug_name=", "").split("=")[0]
        assert url.startswith("https://www.medindia.net/")

    def test_drug_name_spaces_encoded(self):
        from app.services.data_fetcher import _build_medindia_url

        url = _build_medindia_url("amoxicillin clavulanate")
        # Spaces should be percent-encoded or plus-encoded in the query string
        assert " " not in url

    def test_normal_drug_name(self):
        from app.services.data_fetcher import _build_medindia_url

        url = _build_medindia_url("metformin")
        assert "metformin" in url
        assert url.startswith("https://www.medindia.net/")


# ──────────────────────────────────────────────
# Raw scraping response builder
# ──────────────────────────────────────────────


class TestBuildScrapingResponse:
    def _make_drug_fetched(self):
        from app.services.data_fetcher import DrugFetchResult, FetchedData

        d = DrugFetchResult(
            generic_name="metformin",
            brand_name="Glucophage",
            drug_class="Biguanide",
            data_source="fda",
            fetch_success=True,
            indications_raw="Type 2 diabetes mellitus in adults.",
            dosing_raw="Initial: 500 mg twice daily with meals.",
            contraindications_raw="eGFR < 30 mL/min/1.73m2.",
            adverse_reactions_raw="GI upset, lactic acidosis (rare).",
            mechanism_raw="Reduces hepatic glucose production.",
        )
        fd = FetchedData(query_type="drug")
        fd.drug_data = d
        return fd

    def _make_disease_fetched(self):
        from app.services.data_fetcher import DiseaseFetchResult, FetchedData

        d = DiseaseFetchResult(fetch_success=True)
        d.guideline_abstracts = [
            {"title": "AHA/ACC Hypertension Guidelines 2023", "abstract": "BP < 130/80 mmHg target.", "year": 2023},
        ]
        d.medlineplus_summary = "Hypertension is elevated blood pressure ≥ 130/80 mmHg."
        fd = FetchedData(query_type="disease")
        fd.disease_data = d
        return fd

    def test_drug_scraping_response_returns_general_response(self):
        from app.services.scraping_response import _build_scraping_response
        from app.schemas.query import GeneralResponse

        result = _build_scraping_response("metformin", "drug", self._make_drug_fetched())
        assert isinstance(result, GeneralResponse)

    def test_drug_scraping_response_has_summary(self):
        from app.services.scraping_response import _build_scraping_response

        result = _build_scraping_response("metformin", "drug", self._make_drug_fetched())
        assert result.summary
        assert len(result.summary) > 10

    def test_drug_scraping_response_has_key_points(self):
        from app.services.scraping_response import _build_scraping_response

        result = _build_scraping_response("metformin", "drug", self._make_drug_fetched())
        assert len(result.key_points) > 0

    def test_disease_scraping_response_has_guideline_info(self):
        from app.services.scraping_response import _build_scraping_response

        result = _build_scraping_response("hypertension", "disease", self._make_disease_fetched())
        assert result.summary
        # Should include guideline or summary content
        combined = result.summary + " ".join(result.key_points)
        assert "hypertension" in combined.lower() or "blood pressure" in combined.lower() or "AHA" in combined

    def test_no_fetched_data_returns_none(self):
        from app.services.scraping_response import _build_scraping_response

        result = _build_scraping_response("query", "general", None)
        assert result is None

    def test_failed_fetch_returns_none(self):
        from app.services.data_fetcher import DrugFetchResult, FetchedData
        from app.services.scraping_response import _build_scraping_response

        fd = FetchedData(query_type="drug", fallback_to_llm=True)
        fd.drug_data = DrugFetchResult(fetch_success=False)
        result = _build_scraping_response("unknown drug", "drug", fd)
        assert result is None

    def test_references_include_data_source(self):
        from app.services.scraping_response import _build_scraping_response

        result = _build_scraping_response("metformin", "drug", self._make_drug_fetched())
        assert len(result.references) > 0
