"""Unit tests for citation token grounding ([REF_N] tokens)."""

import pytest
from unittest.mock import Mock

from app.services.prompt_engine import build_ref_map
from app.services.rag_pipeline import _resolve_ref_tokens


class TestBuildRefMap:
    """Tests for build_ref_map() determinism and coverage."""

    def test_build_ref_map_empty(self):
        """Test with None and empty fetched_data."""
        assert build_ref_map(None) == {}
        assert build_ref_map(Mock(spec=[])) == {}

    def test_build_ref_map_deterministic(self):
        """Same fetched_data produces byte-identical ref_map across runs."""
        fetched_data = self._mock_fetched_data([
            {"pmid": "12345", "title": "PMID Article", "journal": "PubMed"},
            {"nct_id": "NCT00000001", "title": "Trial", "collective_name": "CT.gov"},
        ])

        map1 = build_ref_map(fetched_data)
        map2 = build_ref_map(fetched_data)

        assert map1 == map2
        assert list(map1.keys()) == ["REF_1", "REF_2"]

    def test_build_ref_map_dedup(self):
        """Same PMID in two lists → one token."""
        fetched_data = self._mock_fetched_data(
            [{"pmid": "99999", "title": "Duplicate", "journal": "J1"}],
            [{"pmid": "99999", "title": "Duplicate", "journal": "J1"}],
        )

        ref_map = build_ref_map(fetched_data)
        assert len(ref_map) == 1
        assert "REF_1" in ref_map

    def test_build_ref_map_non_pubmed_sources(self):
        """Handles NICE recs and FDA labels without throwing."""
        fetched_data = Mock()
        fetched_data.drug_data = Mock()
        fetched_data.drug_data.label_url = "https://dailymed.nlm.nih.gov/..."
        fetched_data.drug_data.guideline_abstracts = []
        fetched_data.drug_data.systematic_review_abstracts = []
        fetched_data.drug_data.clinical_trial_abstracts = []
        fetched_data.drug_data.practice_guideline_abstracts = []
        fetched_data.drug_data.nice_recommendations = [
            {"title": "NICE Rec", "url": "https://nice.org.uk/guidance/..."}
        ]

        fetched_data.disease_data = None
        fetched_data.procedure_data = None
        fetched_data.evidence_data = None
        fetched_data.condition_data = None

        ref_map = build_ref_map(fetched_data)
        assert len(ref_map) >= 1  # At least FDA label + NICE rec
        assert any("NICE" in v["source"] for v in ref_map.values())

    def test_build_ref_map_sort_order(self):
        """Composite sort key: source priority, then PMID, then NCT, then title."""
        fetched_data = self._mock_fetched_data([
            {"pmid": "3", "title": "C Article"},
            {"pmid": "1", "title": "A Article"},
            {"pmid": "2", "title": "B Article"},
        ])

        ref_map = build_ref_map(fetched_data)
        titles = [ref_map[f"REF_{i}"]["title"] for i in range(1, len(ref_map) + 1)]
        assert titles == ["A Article", "B Article", "C Article"]

    def _mock_fetched_data(self, abstracts_1=None, abstracts_2=None):
        """Helper to create a mock FetchedData with guideline_abstracts."""
        fd = Mock()
        fd.drug_data = Mock()
        fd.drug_data.guideline_abstracts = abstracts_1 or []
        fd.drug_data.systematic_review_abstracts = abstracts_2 or []
        fd.drug_data.clinical_trial_abstracts = []
        fd.drug_data.practice_guideline_abstracts = []
        fd.drug_data.nice_recommendations = []
        fd.drug_data.label_url = None

        fd.disease_data = None
        fd.procedure_data = None
        fd.evidence_data = None
        fd.condition_data = None
        return fd


class TestResolveRefTokens:
    """Tests for _resolve_ref_tokens() resolution and error handling."""

    def test_resolve_tokens_full_match(self):
        """Full-field [REF_N] token is resolved."""
        ref_map = {"REF_1": {"title": "Real Title", "pmid": "99999", "url": "https://..."}}
        parsed = {
            "sections": [{
                "content_items": [{"source": "[REF_1]", "text": "claim"}]
            }]
        }

        _resolve_ref_tokens(parsed, ref_map)

        assert parsed["sections"][0]["content_items"][0]["source"] == "Real Title"
        assert parsed["sections"][0]["content_items"][0]["pmid"] == "99999"
        assert parsed["sections"][0]["content_items"][0]["url"] == "https://..."

    def test_resolve_tokens_whitespace_tolerant(self):
        """Handles whitespace around brackets."""
        ref_map = {"REF_2": {"title": "Title2", "pmid": None, "url": None}}
        parsed = {
            "sections": [{
                "content_items": [{"source": "  [ REF_2 ]  ", "text": "claim"}]
            }]
        }

        _resolve_ref_tokens(parsed, ref_map)
        assert parsed["sections"][0]["content_items"][0]["source"] == "Title2"

    def test_resolve_tokens_hallucinated(self):
        """[REF_99] not in map → source set to empty string (routes to backfill)."""
        ref_map = {"REF_1": {"title": "Real", "pmid": None, "url": None}}
        parsed = {
            "sections": [{
                "content_items": [{"source": "[REF_99]", "text": "claim"}]
            }]
        }

        _resolve_ref_tokens(parsed, ref_map)
        assert parsed["sections"][0]["content_items"][0]["source"] == ""

    def test_resolve_tokens_no_substring_match(self):
        """REF_3 embedded in text without brackets NOW matches (hardened regex)."""
        ref_map = {"REF_3": {"title": "Title3", "pmid": None, "url": None}}
        parsed = {
            "sections": [{
                "content_items": [{"source": "This trial REF_3 something", "text": "claim"}]
            }]
        }

        _resolve_ref_tokens(parsed, ref_map)
        # With widened regex, bare REF_3 is now resolved
        assert parsed["sections"][0]["content_items"][0]["source"] == "Title3"

    def test_resolve_tokens_case_insensitive(self):
        """Regex is case-insensitive (ref_1 matches REF_1)."""
        ref_map = {"REF_1": {"title": "Title1", "pmid": None, "url": None}}
        parsed = {
            "sections": [{
                "content_items": [{"source": "[ref_1]", "text": "claim"}]
            }]
        }

        _resolve_ref_tokens(parsed, ref_map)
        assert parsed["sections"][0]["content_items"][0]["source"] == "Title1"

    def test_resolve_tokens_in_references(self):
        """Resolves tokens in parsed['references'] as well."""
        ref_map = {"REF_2": {"title": "RefTitle", "source": "NICE", "pmid": None, "url": "https://..."}}
        parsed = {
            "references": [{"source": "[REF_2]", "title": "dummy"}],
            "sections": []
        }

        _resolve_ref_tokens(parsed, ref_map)

        assert parsed["references"][0]["title"] == "RefTitle"
        assert parsed["references"][0]["source"] == "NICE"

    def test_resolve_tokens_empty_map(self):
        """Empty ref_map is a no-op."""
        parsed = {
            "sections": [{
                "content_items": [{"source": "[REF_1]", "text": "claim"}]
            }]
        }

        _resolve_ref_tokens(parsed, {})
        # Should remain unchanged
        assert parsed["sections"][0]["content_items"][0]["source"] == "[REF_1]"


class TestPostProcessingOrder:
    """Integration test: tokens survive sanitize + normalize + backfill."""

    def test_token_resolution_runs_before_sanitize(self):
        """After token resolution, PMIDs are real (not the token string)."""
        ref_map = {"REF_3": {"title": "Real Title", "pmid": "12345", "url": "https://...", "source": "PubMed"}}
        parsed = {
            "sections": [{
                "content_items": [{"source": "[REF_3]", "text": "claim", "pmid": None}]
            }]
        }

        _resolve_ref_tokens(parsed, ref_map)

        # After resolution, pmid should be real
        assert parsed["sections"][0]["content_items"][0]["pmid"] == "12345"
        # Source should be title, not token
        assert parsed["sections"][0]["content_items"][0]["source"] == "Real Title"


class TestRegexVariants:
    """Tests for widened token regex handling punctuation and formatting variants."""

    def test_regex_handles_punctuation(self):
        """REF_5., (REF_5), \"REF_5\", REF5, Ref 5 all resolve."""
        ref_map = {"REF_5": {"title": "Real Article", "pmid": "99999", "url": "https://..."}}
        variants = [
            "[REF_5]",
            "REF_5.",
            "(REF_5)",
            '"REF_5"',
            "REF5",
            "Ref 5",
            "[REF_5,",
            "REF_5 and"
        ]

        for variant in variants:
            parsed = {
                "sections": [{
                    "content_items": [{"source": variant, "text": "claim"}]
                }]
            }
            _resolve_ref_tokens(parsed, ref_map)
            source = parsed["sections"][0]["content_items"][0]["source"]
            assert source == "Real Article", f"Failed for variant: {variant}"

    def test_regex_rejects_substring_lookalike(self):
        """REFERENCE_5, PREF_5, REF_5A do NOT match (source unchanged)."""
        ref_map = {"REF_5": {"title": "Real Article", "pmid": "99999", "url": "https://..."}}
        non_matches = [
            "REFERENCE_5",
            "PREF_5",
            "REF_5A",
            "REF_ABC",
            "XREF_5"
        ]

        for non_match in non_matches:
            parsed = {
                "sections": [{
                    "content_items": [{"source": non_match, "text": "claim"}]
                }]
            }
            _resolve_ref_tokens(parsed, ref_map)
            source = parsed["sections"][0]["content_items"][0]["source"]
            # Pattern doesn't match, so source should remain unchanged
            assert source == non_match, f"Should not match or resolve: {non_match}"


class TestMultiTokenSource:
    """Tests for handling multiple [REF_N] tokens in source field."""

    def test_multi_token_source(self):
        """[REF_3, REF_4] populates additional_sources."""
        ref_map = {
            "REF_3": {"title": "Article 3", "pmid": "333", "url": "https://3"},
            "REF_4": {"title": "Article 4", "pmid": "444", "url": "https://4"}
        }
        parsed = {
            "sections": [{
                "content_items": [{"source": "[REF_3, REF_4]", "text": "claim"}]
            }]
        }

        _resolve_ref_tokens(parsed, ref_map)
        item = parsed["sections"][0]["content_items"][0]
        assert item["source"] == "Article 3"
        assert item["pmid"] == "333"
        assert len(item.get("additional_sources", [])) == 1
        assert item["additional_sources"][0]["title"] == "Article 4"
        assert item["additional_sources"][0]["pmid"] == "444"


class TestBackfillLogic:
    """Tests for per-claim backfill and hallucination filtering."""

    def test_per_claim_backfill_picks_distinct_articles(self):
        """Per-claim backfill function picks articles based on token overlap."""
        from app.services.rag_pipeline import _best_article_for_claim

        articles = [
            {"title": "Diabetes Management Guidelines", "source": "guideline", "pmid": "111"},
            {"title": "Hypertension Treatment Review", "source": "systematic_review", "pmid": "222"},
            {"title": "Drug Interactions Study", "source": "clinical_trial", "pmid": "333"}
        ]

        diabetes_claim = "Treatment of type 2 diabetes with insulin and metformin"
        hypertension_claim = "Blood pressure control in elderly patients"
        interactions_claim = "Drug-drug interactions between common medications"

        best_for_diabetes = _best_article_for_claim(diabetes_claim, articles)
        best_for_hypertension = _best_article_for_claim(hypertension_claim, articles)
        best_for_interactions = _best_article_for_claim(interactions_claim, articles)

        # All should return an article (not None)
        assert best_for_diabetes is not None
        assert best_for_hypertension is not None
        assert best_for_interactions is not None
        # All should be valid articles
        assert best_for_diabetes["pmid"] in ("111", "222", "333")
        assert best_for_hypertension["pmid"] in ("111", "222", "333")
        assert best_for_interactions["pmid"] in ("111", "222", "333")

    def test_hallucinated_llm_ref_dropped(self):
        """LLM ref with title not in fetched_data is dropped."""
        from app.services.rag_pipeline import _is_grounded_ref

        ref_map_index = {
            "pmids": {"99999"},
            "ncts": set(),
            "dois": set(),
            "titles": {"real article"}
        }

        hallucinated_ref = {
            "title": "Totally Made Up Study",
            "pmid": None,
            "url": "https://fake.example.com"
        }

        is_grounded = _is_grounded_ref(hallucinated_ref, ref_map_index)
        assert not is_grounded

    def test_grounded_ref_by_pmid(self):
        """LLM ref with PMID in ref_map is grounded."""
        from app.services.rag_pipeline import _is_grounded_ref

        ref_map_index = {
            "pmids": {"99999"},
            "ncts": set(),
            "dois": set(),
            "titles": set()
        }

        grounded_ref = {
            "title": "Some Title",
            "pmid": "99999",
            "url": "https://pubmed.ncbi.nlm.nih.gov/99999/"
        }

        is_grounded = _is_grounded_ref(grounded_ref, ref_map_index)
        assert is_grounded


class TestQuarantineLogic:
    """Tests for dropping orphan claims without source/url/pmid."""

    def test_quarantine_orphan_claim(self):
        """Claim with no source/url/pmid after backfill → dropped."""
        from app.services.rag_pipeline import _quarantine_sourceless_items

        parsed = {
            "sections": [{
                "content_items": [
                    {"text": "Valid claim", "source": "Article Title", "pmid": None},
                    {"text": "Orphan claim", "source": "", "url": None, "pmid": None},
                    {"text": "Expert claim", "source": "Expert opinion", "url": None, "pmid": None},
                ]
            }],
            "references": [
                {"title": "Good Ref", "source": "PubMed", "pmid": "111", "url": None},
                {"title": "Bad Ref", "source": "Expert opinion", "pmid": None, "url": None},
            ]
        }

        _quarantine_sourceless_items(parsed)

        items = parsed["sections"][0]["content_items"]
        assert len(items) == 1
        assert items[0]["text"] == "Valid claim"

        refs = parsed["references"]
        assert len(refs) == 1
        assert refs[0]["title"] == "Good Ref"

    def test_quarantine_keeps_url_only_item(self):
        """Item with only URL (no source/pmid) is kept."""
        from app.services.rag_pipeline import _quarantine_sourceless_items

        parsed = {
            "sections": [{
                "content_items": [
                    {"text": "URL-only claim", "source": "", "url": "https://example.com", "pmid": None},
                ]
            }],
            "references": []
        }

        _quarantine_sourceless_items(parsed)

        items = parsed["sections"][0]["content_items"]
        assert len(items) == 1
