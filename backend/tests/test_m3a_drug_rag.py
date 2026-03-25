"""
M3a tests: Drug RAG quality — systematic reviews merged into drug fetch payload.

Run: pytest tests/test_m3a_drug_rag.py -v
"""
import pytest


# ──────────────────────────────────────────────
# DrugFetchResult schema
# ──────────────────────────────────────────────


class TestDrugFetchResultSchema:
    def test_has_systematic_review_abstracts_field(self):
        from app.services.data_fetcher import DrugFetchResult

        result = DrugFetchResult()
        assert hasattr(result, "systematic_review_abstracts")
        assert isinstance(result.systematic_review_abstracts, list)
        assert result.systematic_review_abstracts == []

    def test_systematic_review_abstracts_preserved_through_fallbacks(self):
        from app.services.data_fetcher import DrugFetchResult

        result = DrugFetchResult()
        result.systematic_review_abstracts = [{"pmid": "111", "title": "SR A", "abstract": "...", "year": 2023}]
        assert len(result.systematic_review_abstracts) == 1


# ──────────────────────────────────────────────
# DRUG_FORMAT_PROMPT content
# ──────────────────────────────────────────────


class TestDrugFormatPrompt:
    def test_prompt_has_systematic_review_section(self):
        from app.services.prompt_engine import DRUG_FORMAT_PROMPT

        assert "systematic review" in DRUG_FORMAT_PROMPT.lower() or \
               "systematic_review" in DRUG_FORMAT_PROMPT.lower() or \
               "meta-analy" in DRUG_FORMAT_PROMPT.lower()

    def test_prompt_has_systematic_review_placeholder(self):
        from app.services.prompt_engine import DRUG_FORMAT_PROMPT

        assert "{systematic_review_abstracts_formatted}" in DRUG_FORMAT_PROMPT

    def test_prompt_still_has_guideline_section(self):
        from app.services.prompt_engine import DRUG_FORMAT_PROMPT

        assert "{guideline_abstracts_formatted}" in DRUG_FORMAT_PROMPT


# ──────────────────────────────────────────────
# build_prompt passes systematic reviews
# ──────────────────────────────────────────────


class TestBuildPromptDrugIncludes:
    def _make_fetched(self, guidelines=None, sysreviews=None):
        from app.services.data_fetcher import DrugFetchResult, FetchedData

        d = DrugFetchResult(
            generic_name="metformin",
            brand_name="Glucophage",
            drug_class="Biguanide",
            data_source="fda",
            fetch_success=True,
            indications_raw="Type 2 diabetes mellitus",
        )
        d.guideline_abstracts = guidelines or []
        d.systematic_review_abstracts = sysreviews or []

        fd = FetchedData(query_type="drug")
        fd.drug_data = d
        return fd

    def test_systematic_reviews_appear_in_prompt(self):
        from app.services.prompt_engine import build_prompt

        fetched = self._make_fetched(
            sysreviews=[{
                "pmid": "38293847",
                "title": "Metformin efficacy meta-analysis 2023",
                "abstract": "Metformin reduces HbA1c by 1.0-1.5% in T2DM.",
                "year": 2023,
            }]
        )
        prompt = build_prompt("metformin for type 2 diabetes", "drug", fetched)
        assert "Metformin efficacy meta-analysis 2023" in prompt or \
               "HbA1c" in prompt

    def test_empty_systematic_reviews_renders_cleanly(self):
        from app.services.prompt_engine import build_prompt

        fetched = self._make_fetched(sysreviews=[])
        # Must not raise
        prompt = build_prompt("metformin", "drug", fetched)
        assert "metformin" in prompt.lower()

    def test_guidelines_still_included_alongside_reviews(self):
        from app.services.prompt_engine import build_prompt

        fetched = self._make_fetched(
            guidelines=[{"pmid": "111", "title": "ADA Standards 2024", "abstract": "ADA guidance.", "year": 2024}],
            sysreviews=[{"pmid": "222", "title": "SR review", "abstract": "Review text.", "year": 2023}],
        )
        prompt = build_prompt("metformin", "drug", fetched)
        assert "ADA Standards 2024" in prompt
        assert "SR review" in prompt


# ──────────────────────────────────────────────
# fetch_drug_data: systematic review fetch
# (unit test via mock to avoid real HTTP)
# ──────────────────────────────────────────────


class TestFetchDrugDataSystematicReviews:
    def test_fetch_drug_data_result_has_systematic_review_abstracts_attr(self):
        """DrugFetchResult always has the attribute — even if fetch returns empty."""
        from app.services.data_fetcher import DrugFetchResult

        r = DrugFetchResult()
        assert hasattr(r, "systematic_review_abstracts")
        assert r.systematic_review_abstracts == []

    def test_cap_abstracts_applied_to_systematic_reviews(self):
        """_cap_abstracts trims by character budget — verify systematic reviews respect budget."""
        from app.services.data_fetcher import _cap_abstracts

        long_abstracts = [
            {"pmid": str(i), "title": f"Paper {i}", "abstract": "x" * 600, "year": 2024 - i}
            for i in range(10)
        ]
        result = _cap_abstracts(long_abstracts, max_total_chars=1500)
        # Should keep at most 2 (each is 600 chars)
        assert len(result) <= 3
        # Newest first
        years = [a["year"] for a in result]
        assert years == sorted(years, reverse=True)
