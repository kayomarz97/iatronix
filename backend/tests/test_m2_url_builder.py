"""
M2 tests: deterministic URL enrichment + citation URL validation.

Run: pytest tests/test_m2_url_builder.py -v
"""
import pytest


# ──────────────────────────────────────────────
# url_builder tests
# ──────────────────────────────────────────────


class TestBuildPmidIndex:
    def test_extracts_pmid_from_guideline_abstracts(self):
        from app.services.url_builder import build_pmid_index

        fetched_data = _fake_fetched(
            guideline_abstracts=[
                {"pmid": "12345678", "title": "Management of Hypertension AHA 2023"},
            ]
        )
        index = build_pmid_index(fetched_data)
        assert "management of hypertension aha 2023" in index
        assert index["management of hypertension aha 2023"] == "12345678"

    def test_skips_abstracts_without_pmid(self):
        from app.services.url_builder import build_pmid_index

        fetched_data = _fake_fetched(
            guideline_abstracts=[{"title": "Some paper", "pmid": None}]
        )
        index = build_pmid_index(fetched_data)
        assert len(index) == 0

    def test_collects_from_multiple_abstract_lists(self):
        from app.services.url_builder import build_pmid_index

        fetched_data = _fake_fetched(
            guideline_abstracts=[{"pmid": "11111111", "title": "Guideline A"}],
            systematic_review_abstracts=[{"pmid": "22222222", "title": "SR B"}],
        )
        index = build_pmid_index(fetched_data)
        assert "guideline a" in index
        assert "sr b" in index

    def test_empty_fetched_data_returns_empty_index(self):
        from app.services.url_builder import build_pmid_index

        index = build_pmid_index(None)
        assert index == {}


class TestEnrichReferences:
    def test_pmid_in_title_matched_from_fetched(self):
        from app.services.url_builder import enrich_references

        data = {
            "references": [
                {"source": "AHA", "title": "Management of Hypertension AHA 2023", "year": 2023, "url": None}
            ]
        }
        fetched = _fake_fetched(
            guideline_abstracts=[{"pmid": "12345678", "title": "Management of Hypertension AHA 2023"}]
        )
        enrich_references(data, fetched)
        assert data["references"][0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/12345678/"

    def test_pmid_inline_in_source_field(self):
        from app.services.url_builder import enrich_references

        data = {
            "references": [
                {"source": "PubMed PMID:38293847", "title": None, "year": 2024, "url": None}
            ]
        }
        enrich_references(data, None)
        assert data["references"][0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/38293847/"

    def test_doi_inline_produces_doi_url(self):
        from app.services.url_builder import enrich_references

        data = {
            "references": [
                {"source": "NEJM 10.1056/NEJMoa2023", "title": None, "year": 2023, "url": None}
            ]
        }
        enrich_references(data, None)
        assert data["references"][0]["url"] == "https://doi.org/10.1056/NEJMoa2023"

    def test_fda_source_gets_fda_url(self):
        from app.services.url_builder import enrich_references

        data = {"references": [{"source": "FDA drug label", "title": "Metformin label", "year": 2022, "url": None}]}
        enrich_references(data, None)
        assert data["references"][0]["url"] is not None
        assert "fda.gov" in data["references"][0]["url"]

    def test_nice_source_gets_nice_url(self):
        from app.services.url_builder import enrich_references

        data = {"references": [{"source": "NICE", "title": "Hypertension NG136", "year": 2023, "url": None}]}
        enrich_references(data, None)
        assert data["references"][0]["url"] is not None
        assert "nice.org.uk" in data["references"][0]["url"]

    def test_cochrane_source_gets_cochrane_url(self):
        from app.services.url_builder import enrich_references

        data = {"references": [{"source": "Cochrane Library", "title": "Beta blockers SR", "year": 2021, "url": None}]}
        enrich_references(data, None)
        assert "cochranelibrary.com" in data["references"][0]["url"]

    def test_unknown_source_stays_null(self):
        from app.services.url_builder import enrich_references

        data = {"references": [{"source": "Some Unknown Journal", "title": None, "year": 2020, "url": None}]}
        enrich_references(data, None)
        assert data["references"][0]["url"] is None

    def test_existing_valid_url_preserved(self):
        from app.services.url_builder import enrich_references

        original_url = "https://pubmed.ncbi.nlm.nih.gov/99999999/"
        data = {"references": [{"source": "PubMed", "title": "Some paper", "year": 2023, "url": original_url}]}
        enrich_references(data, None)
        assert data["references"][0]["url"] == original_url

    def test_http_url_nulled(self):
        from app.services.url_builder import enrich_references

        data = {"references": [{"source": "Some", "title": None, "year": 2020, "url": "http://pubmed.ncbi.nlm.nih.gov/123/"}]}
        enrich_references(data, None)
        assert data["references"][0]["url"] is None

    def test_unknown_domain_url_nulled(self):
        from app.services.url_builder import enrich_references

        data = {"references": [{"source": "Sketchy", "title": None, "year": 2020, "url": "https://evil.example.com/fake"}]}
        enrich_references(data, None)
        assert data["references"][0]["url"] is None

    def test_no_references_key_no_crash(self):
        from app.services.url_builder import enrich_references

        data = {"disease_name": "Hypertension"}
        enrich_references(data, None)  # must not raise

    def test_empty_references_list_no_crash(self):
        from app.services.url_builder import enrich_references

        data = {"references": []}
        enrich_references(data, None)

    def test_esc_source_gets_esc_url(self):
        from app.services.url_builder import enrich_references

        data = {"references": [{"source": "ESC", "title": "PAH Guidelines 2022", "year": 2022, "url": None}]}
        enrich_references(data, None)
        assert data["references"][0]["url"] is not None
        assert "escardio.org" in data["references"][0]["url"]

    def test_who_source_gets_who_url(self):
        from app.services.url_builder import enrich_references

        data = {"references": [{"source": "WHO", "title": "TB Guidelines", "year": 2022, "url": None}]}
        enrich_references(data, None)
        assert "who.int" in data["references"][0]["url"]


class TestIsSafeUrl:
    def test_valid_pubmed_url_safe(self):
        from app.services.url_builder import is_safe_url
        assert is_safe_url("https://pubmed.ncbi.nlm.nih.gov/12345678/") is True

    def test_valid_doi_url_safe(self):
        from app.services.url_builder import is_safe_url
        assert is_safe_url("https://doi.org/10.1056/NEJMoa2023") is True

    def test_http_not_safe(self):
        from app.services.url_builder import is_safe_url
        assert is_safe_url("http://pubmed.ncbi.nlm.nih.gov/123/") is False

    def test_unknown_domain_not_safe(self):
        from app.services.url_builder import is_safe_url
        assert is_safe_url("https://malicious.example.com/data") is False

    def test_empty_string_not_safe(self):
        from app.services.url_builder import is_safe_url
        assert is_safe_url("") is False

    def test_none_not_safe(self):
        from app.services.url_builder import is_safe_url
        assert is_safe_url(None) is False

    def test_too_long_url_not_safe(self):
        from app.services.url_builder import is_safe_url
        assert is_safe_url("https://pubmed.ncbi.nlm.nih.gov/" + "a" * 500) is False


# ──────────────────────────────────────────────
# citation_validator URL validation tests
# ──────────────────────────────────────────────


class TestCitationValidatorUrlWarnings:
    def test_http_url_generates_warning(self):
        from app.services.citation_validator import validate_citations

        data = {
            "references": [
                {"source": "PubMed", "title": "Test", "year": 2023, "url": "http://pubmed.ncbi.nlm.nih.gov/123"}
            ]
        }
        warnings = validate_citations(data, "general")
        assert any("http://" in w or "non-HTTPS" in w or "insecure" in w.lower() for w in warnings)

    def test_unknown_domain_url_generates_warning(self):
        from app.services.citation_validator import validate_citations

        data = {
            "references": [
                {"source": "AHA", "title": "Test", "year": 2023, "url": "https://sketchy.xyz/paper"}
            ]
        }
        warnings = validate_citations(data, "general")
        assert any("domain" in w.lower() or "url" in w.lower() for w in warnings)

    def test_valid_pubmed_url_no_warning(self):
        from app.services.citation_validator import validate_citations

        data = {
            "references": [
                {"source": "PubMed", "title": "Test", "year": 2023, "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"}
            ]
        }
        warnings = validate_citations(data, "general")
        url_warnings = [w for w in warnings if "url" in w.lower() or "domain" in w.lower() or "http" in w.lower()]
        assert len(url_warnings) == 0

    def test_null_url_no_warning(self):
        from app.services.citation_validator import validate_citations

        data = {
            "references": [{"source": "FDA", "title": "Test", "year": 2022, "url": None}]
        }
        warnings = validate_citations(data, "drug")
        url_warnings = [w for w in warnings if "url" in w.lower()]
        assert len(url_warnings) == 0


# ──────────────────────────────────────────────
# prompt_engine contract rule check
# ──────────────────────────────────────────────


class TestPromptUrlRule:
    def test_json_contract_rules_contains_url_null_instruction(self):
        from app.services.prompt_engine import JSON_CONTRACT_RULES

        lower = JSON_CONTRACT_RULES.lower()
        assert "url" in lower and ("null" in lower or "backend" in lower)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _fake_fetched(
    guideline_abstracts=None,
    systematic_review_abstracts=None,
    clinical_trial_abstracts=None,
):
    """Minimal FetchedData-like object for testing."""

    class _FakeData:
        pass

    class _Fake:
        drug_data = None
        disease_data = None
        procedure_data = None
        evidence_data = None
        comparative_drug_data = None

        def __init__(self):
            self.disease_data = _FakeData()
            self.disease_data.guideline_abstracts = guideline_abstracts or []
            self.disease_data.systematic_review_abstracts = systematic_review_abstracts or []
            self.evidence_data = _FakeData()
            self.evidence_data.guideline_abstracts = []
            self.evidence_data.clinical_trial_abstracts = clinical_trial_abstracts or []
            self.evidence_data.systematic_review_abstracts = systematic_review_abstracts or []
            self.drug_data = _FakeData()
            self.drug_data.guideline_abstracts = guideline_abstracts or []

    return _Fake()
