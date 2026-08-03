"""Regression tests for per-claim INLINE citations (2026-08-02, INLINE_CITATIONS_ENABLED).

Defect they pin: `_resolve_ref_tokens` matched [REF_N] in `content_items.source` and
`references.source/title` ONLY. A token written inside `content_items.text` was never
resolved, so it reached the clinician as the literal string "[REF_3]" — there was no working
channel for citing a sentence. Combined with a schema giving each 100-200-word item a single
`source`, and a grounding gate that DELETES an item whose one source failed to resolve, the
result was answers that were both under-cited and visibly thin.

Three properties make the change safe, and all three are locked here:
  * a token absent from ref_map is STRIPPED, never rendered and never minting a citation
    (model output had not been forgery-hardened before — 3d55a89 covers user input only);
  * an item with >=1 resolved inline citation survives the grounding gate even when its
    item-level `source` is generic — a miss demotes instead of deleting;
  * flag OFF is byte-identical to the previous behaviour.

Per .claude/rules/mistakes.md (2026-08-02, "a harness can silently not exercise the thing you
believe it measures"), `test_flag_off_and_on_differ` REQUIRES the two arms to produce different
output — if the flag ever stops reaching the code under test, that test fails rather than
quietly passing.
"""
import copy

import pytest

from app.config import settings
from app.services.grounding_gate import grounding_stats, strip_ungrounded
from app.services.rag_pipeline import _resolve_inline_citations, _quarantine_sourceless_items

pytestmark = pytest.mark.citation


REF_MAP = {
    "REF_1": {"title": "KDIGO 2024 Guideline for CKD", "pmid": "111",
              "url": "https://pubmed.ncbi.nlm.nih.gov/111/", "source": "PubMed"},
    "REF_2": {"title": "EMPA-REG OUTCOME trial", "pmid": "222",
              "url": "https://pubmed.ncbi.nlm.nih.gov/222/", "source": "PubMed"},
    "REF_3": {"title": "StatPearls: Metformin", "pmid": None,
              "url": "https://www.ncbi.nlm.nih.gov/books/NBK518983/", "source": "StatPearls"},
}


@pytest.fixture
def inline_on(monkeypatch):
    monkeypatch.setattr(settings, "inline_citations_enabled", True)


@pytest.fixture
def inline_off(monkeypatch):
    monkeypatch.setattr(settings, "inline_citations_enabled", False)


def _resp(*texts, source="[REF_1]"):
    return {
        "sections": [
            {"title": "Treatment",
             "content_items": [{"text": t, "source": source} for t in texts]}
        ]
    }


def _items(parsed):
    return parsed["sections"][0]["content_items"]


# ── Resolution ───────────────────────────────────────────────────────────────

def test_valid_token_resolves_and_marker_is_kept(inline_on):
    parsed = _resp("Metformin remains first line [REF_1]. It is renally cleared [REF_3].")
    resolved, stripped = _resolve_inline_citations(parsed, REF_MAP)

    assert (resolved, stripped) == (2, 0)
    item = _items(parsed)[0]
    # Canonical markers survive in the text so the renderer can locate them.
    assert "[REF_1]" in item["text"] and "[REF_3]" in item["text"]
    cites = item["citations"]
    assert [c["token"] for c in cites] == ["[REF_1]", "[REF_3]"]
    assert [c["index"] for c in cites] == [1, 2]
    assert cites[0]["title"] == "KDIGO 2024 Guideline for CKD"
    assert cites[0]["pmid"] == "111"
    assert cites[1]["url"] == "https://www.ncbi.nlm.nih.gov/books/NBK518983/"


def test_multi_token_form_expands_to_two_citations(inline_on):
    parsed = _resp("Both trials agree [REF_1, REF_2].")
    resolved, _ = _resolve_inline_citations(parsed, REF_MAP)

    assert resolved == 2
    item = _items(parsed)[0]
    assert "[REF_1][REF_2]" in item["text"]
    assert len(item["citations"]) == 2


def test_numbering_is_document_global_and_stable(inline_on):
    """The same source cited twice keeps ONE number; a new source gets the next."""
    parsed = {
        "sections": [
            {"title": "A", "content_items": [{"text": "First [REF_2].", "source": "x"}]},
            {"title": "B", "content_items": [
                {"text": "Again [REF_2], plus new [REF_1].", "source": "x"}]},
        ]
    }
    _resolve_inline_citations(parsed, REF_MAP)

    a = parsed["sections"][0]["content_items"][0]["citations"]
    b = parsed["sections"][1]["content_items"][0]["citations"]
    assert [c["index"] for c in a] == [1]                 # REF_2 seen first → 1
    assert [(c["token"], c["index"]) for c in b] == [("[REF_2]", 1), ("[REF_1]", 2)]


def test_repeated_token_in_one_item_yields_one_citation_entry(inline_on):
    parsed = _resp("Dose is 500 mg [REF_1]. Titrate weekly [REF_1].")
    resolved, _ = _resolve_inline_citations(parsed, REF_MAP)

    item = _items(parsed)[0]
    assert resolved == 2                    # both markers render
    assert len(item["citations"]) == 1      # but one source behind them
    assert item["text"].count("[REF_1]") == 2


# ── Forgery hardening (model output) ─────────────────────────────────────────

def test_forged_token_is_stripped_and_mints_no_citation(inline_on):
    parsed = _resp("Empagliflozin cuts mortality by 38% [REF_99].")
    resolved, stripped = _resolve_inline_citations(parsed, REF_MAP)

    assert (resolved, stripped) == (0, 1)
    item = _items(parsed)[0]
    assert "REF_99" not in item["text"]
    assert "[" not in item["text"]
    assert item.get("citations", []) == []
    # Whitespace left behind is tidied, not left as "38%  ."
    assert item["text"] == "Empagliflozin cuts mortality by 38%."


def test_mixed_valid_and_forged_keeps_only_the_valid_one(inline_on):
    parsed = _resp("Real [REF_1] and fake [REF_42] claims.")
    resolved, stripped = _resolve_inline_citations(parsed, REF_MAP)

    assert (resolved, stripped) == (1, 1)
    item = _items(parsed)[0]
    assert "[REF_1]" in item["text"] and "REF_42" not in item["text"]
    assert len(item["citations"]) == 1


def test_ordinary_clinical_text_is_untouched(inline_on):
    """Brackets are required, so prose and chemistry notation survive intact."""
    original = "Serum [Na+] was 128 mmol/L; see REF 3 below, and [sic] the 2019 cohort [1]."
    parsed = _resp(original)
    resolved, stripped = _resolve_inline_citations(parsed, REF_MAP)

    assert (resolved, stripped) == (0, 0)
    assert _items(parsed)[0]["text"] == original


# ── The gate: demote, don't delete ───────────────────────────────────────────

def test_inline_cited_claim_survives_the_grounding_gate(inline_on):
    """The core W2 property: a generic item-level source no longer costs the reader the prose."""
    parsed = _resp("Metformin is continued down to eGFR 30 [REF_1].", source="Expert opinion")
    _resolve_inline_citations(parsed, REF_MAP)

    removed = strip_ungrounded(parsed)
    grounded, total = grounding_stats(parsed)

    assert removed == 0
    assert (grounded, total) == (1, 1)
    assert len(parsed["sections"]) == 1


def test_claim_with_no_citation_at_all_is_still_removed(inline_on):
    """Demotion is not a licence for ungrounded content — zero citations still deletes."""
    parsed = _resp("Metformin is safe in all patients.", source="Expert opinion")
    _resolve_inline_citations(parsed, REF_MAP)

    assert strip_ungrounded(parsed) == 1
    assert parsed["sections"] == []          # section emptied → dropped, unchanged behaviour


def test_forged_only_claim_does_not_survive_the_gate(inline_on):
    """A forged token must not buy a claim past the gate."""
    parsed = _resp("Invented finding [REF_99].", source="Expert opinion")
    _resolve_inline_citations(parsed, REF_MAP)

    assert strip_ungrounded(parsed) == 1


def test_quarantine_adopts_first_inline_citation_instead_of_demoting(inline_on):
    parsed = _resp("Renal dosing applies [REF_2].", source="")
    _resolve_inline_citations(parsed, REF_MAP)
    _quarantine_sourceless_items(parsed, fetched_data=object())

    item = _items(parsed)[0]
    assert item["source"] == "EMPA-REG OUTCOME trial"
    assert item["pmid"] == "222"
    assert item.get("confidence") != "low"


# ── used_inline marking ──────────────────────────────────────────────────────

def test_inline_citation_marks_the_registry_article_used(inline_on):
    class _RA:
        used_inline = False

    class _Registry:
        def __init__(self):
            self.seen = {}

        def lookup_token(self, key):
            return self.seen.setdefault(key, _RA())

    reg = _Registry()
    parsed = _resp("Claim [REF_1].")
    _resolve_inline_citations(parsed, REF_MAP, reg)

    assert reg.seen["REF_1"].used_inline is True


# ── Flag discipline ──────────────────────────────────────────────────────────

def test_flag_off_is_a_no_op(inline_off):
    parsed = _resp("Metformin remains first line [REF_1].")
    before = copy.deepcopy(parsed)

    assert _resolve_inline_citations(parsed, REF_MAP) == (0, 0)
    assert parsed == before


def test_flag_off_and_on_differ(monkeypatch):
    """Guards against the ledger's 2026-08-02 trap: a harness that never runs the code
    under test. If the flag stops reaching _resolve_inline_citations, this FAILS."""
    text = "Metformin remains first line [REF_1], unlike [REF_99]."

    monkeypatch.setattr(settings, "inline_citations_enabled", False)
    off = _resp(text)
    _resolve_inline_citations(off, REF_MAP)

    monkeypatch.setattr(settings, "inline_citations_enabled", True)
    on = _resp(text)
    _resolve_inline_citations(on, REF_MAP)

    assert off != on, "flag had no observable effect — the lever is not wired"
    assert _items(off)[0].get("citations", []) == []
    assert len(_items(on)[0]["citations"]) == 1


def test_empty_ref_map_is_a_no_op(inline_on):
    parsed = _resp("Claim [REF_1].")
    before = copy.deepcopy(parsed)

    assert _resolve_inline_citations(parsed, {}) == (0, 0)
    assert parsed == before


# ── Citation density (the W4 metric) ─────────────────────────────────────────

def _citation_density(parsed) -> float:
    """Resolved inline citations per 100 words of claim text."""
    cites = 0
    words = 0
    for sec in parsed.get("sections", []):
        for item in sec.get("content_items", []):
            cites += len(item.get("citations") or [])
            words += len(item.get("text", "").split())
    return (100.0 * cites / words) if words else 0.0


def test_citation_density_rises_with_the_flag(monkeypatch):
    """The headline metric, measured on one fixture both ways. Offline, no BYOK spend."""
    texts = (
        "Metformin remains first-line therapy in type 2 diabetes [REF_1]. "
        "It is renally cleared and should be reduced below eGFR 45 [REF_3].",
        "Empagliflozin reduced cardiovascular death in EMPA-REG OUTCOME [REF_2].",
    )

    monkeypatch.setattr(settings, "inline_citations_enabled", False)
    off = _resp(*texts)
    _resolve_inline_citations(off, REF_MAP)

    monkeypatch.setattr(settings, "inline_citations_enabled", True)
    on = _resp(*texts)
    _resolve_inline_citations(on, REF_MAP)

    assert _citation_density(off) == 0.0
    assert _citation_density(on) > 5.0


# ── Prompt wiring ────────────────────────────────────────────────────────────

def _section_prompt():
    from app.services.prompt_engine import build_section_messages
    static, dynamic, _data, _user = build_section_messages(
        section_title="Treatment",
        all_section_titles=["Treatment", "Monitoring"],
        bluf_text="Metformin remains first line.",
        query="metformin in CKD",
        query_type="drug",
    )
    return static, dynamic


def test_rule_is_injected_only_when_the_flag_is_on(monkeypatch):
    monkeypatch.setattr(settings, "inline_citations_enabled", False)
    static_off, dynamic_off = _section_prompt()

    monkeypatch.setattr(settings, "inline_citations_enabled", True)
    static_on, dynamic_on = _section_prompt()

    assert "PER-CLAIM CITATIONS" not in dynamic_off
    assert "PER-CLAIM CITATIONS" in dynamic_on
    assert "SUPERSEDES" in dynamic_on          # must override the static FORMATTING_RULES
    # The cached static prefix is byte-identical either way — the rule lives in the
    # dynamic block precisely so Cerebras prefix caching is unaffected.
    assert static_off == static_on
