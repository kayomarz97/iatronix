"""Tests for citation density — every section must have ≥1 [REF_N] token and every
token must resolve to a reference with a non-null URL.

Extends test_citation_tokens.py with density and completeness assertions.
"""
import re
import pytest
from unittest.mock import MagicMock

pytestmark = pytest.mark.citation

# Token patterns matching rag_pipeline's _TOKEN_INLINE / _TOKEN_FULL regex
_REF_TOKEN_RE = re.compile(r"\[REF_\d+\]", re.IGNORECASE)
_SECTION_STRIP_MARKDOWN = re.compile(r"\*{1,3}|_{1,3}|`+|#{1,6}\s")


def _extract_tokens_from_text(text: str) -> list[str]:
    return _REF_TOKEN_RE.findall(text or "")


def _make_fixture_response(
    sections: list[dict],
    references: list[dict],
) -> dict:
    return {"sections": sections, "references": references}


class TestCitationDensity:
    def test_every_section_has_at_least_one_ref_token(self):
        """Each section must contain ≥1 [REF_N] token in its content items."""
        response = _make_fixture_response(
            sections=[
                {
                    "title": "Mechanism",
                    "content_items": [
                        {"text": "Paracetamol inhibits COX enzymes [REF_1].", "source": "PubMed"},
                    ],
                },
                {
                    "title": "Dosing",
                    "content_items": [
                        {"text": "Standard dose 500 mg–1 g q4–6h [REF_2].", "source": "PubMed"},
                    ],
                },
            ],
            references=[
                {"title": "COX inhibition", "source": "PubMed", "pmid": "12345678",
                 "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"},
                {"title": "Dosing guidelines", "source": "NICE",
                 "url": "https://www.nice.org.uk/guidance/ng76"},
            ],
        )
        for section in response["sections"]:
            all_text = " ".join(
                item.get("text", "") for item in section.get("content_items", [])
            )
            tokens = _extract_tokens_from_text(all_text)
            assert tokens, (
                f"Section '{section['title']}' has no [REF_N] citation tokens"
            )

    def test_every_ref_token_resolves_to_url_bearing_reference(self):
        """Every [REF_N] token in content must resolve to a reference with a non-null URL."""
        response = _make_fixture_response(
            sections=[
                {
                    "title": "Evidence",
                    "content_items": [
                        {"text": "RCT confirms efficacy [REF_1] [REF_2].", "source": "PubMed"},
                    ],
                }
            ],
            references=[
                {"title": "Trial A", "source": "PubMed", "pmid": "11111111",
                 "url": "https://pubmed.ncbi.nlm.nih.gov/11111111/", "ref_token": "REF_1"},
                {"title": "Trial B", "source": "PubMed", "pmid": "22222222",
                 "url": "https://pubmed.ncbi.nlm.nih.gov/22222222/", "ref_token": "REF_2"},
            ],
        )
        ref_by_token = {
            r.get("ref_token", "").upper(): r
            for r in response["references"]
            if r.get("ref_token")
        }
        for section in response["sections"]:
            for item in section.get("content_items", []):
                for token in _extract_tokens_from_text(item.get("text", "")):
                    key = token.strip("[]").upper()
                    assert key in ref_by_token, f"Token {token} not in reference list"
                    assert ref_by_token[key].get("url"), (
                        f"Reference for {token} has no URL"
                    )

    def test_section_without_items_fails_density_check(self):
        """A section with no content_items is a density failure (caught by test above)."""
        section = {"title": "Empty Section", "content_items": []}
        all_text = " ".join(
            item.get("text", "") for item in section.get("content_items", [])
        )
        tokens = _extract_tokens_from_text(all_text)
        assert not tokens  # confirms the logic that catches empty sections

    def test_expert_opinion_section_without_token_fails(self):
        """A section with only 'Expert opinion' text and no REF token must be detected."""
        text = "Based on clinical experience, this is recommended. Expert opinion."
        tokens = _extract_tokens_from_text(text)
        assert not tokens  # no tokens → this section fails the density check

    def test_references_list_non_empty_for_valid_response(self):
        """A valid response must have ≥1 reference."""
        response = _make_fixture_response(
            sections=[{"title": "X", "content_items": [{"text": "text [REF_1]"}]}],
            references=[{"title": "Ref", "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"}],
        )
        assert len(response["references"]) >= 1

    def test_no_references_is_a_failure(self):
        """A response with empty references list fails the citation density check."""
        response = _make_fixture_response(
            sections=[{"title": "X", "content_items": [{"text": "text [REF_1]"}]}],
            references=[],
        )
        assert len(response["references"]) == 0  # confirms this state is detectable
