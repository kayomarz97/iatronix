"""Intent-framing for retrieval (fixes intent-mismatch).

The analyzer already classifies a 10-way clinical `intent` (treatment / diagnosis / drug_dosing /
guideline / side_effect / …) but it was computed and never threaded into retrieval, so a query like
"acute promyelocytic leukaemia — which translocation?" retrieves APL *treatment* papers, not the
*cytogenetics* the question asks for. `intent_terms()` appends intent-appropriate PubMed terms
(subheadings/qualifiers) to the fetch's expansion terms — the same plumbing as query_sense /
differential_dx. Pure, no LLM, no network. Returns [] when it has nothing useful to add.

Measured on the RAGnosis 50-batch: intent-mismatch was 18 of 40 retrieval failures (the largest bucket).
"""
from __future__ import annotations

# intent -> extra PubMed term templates. {e} is filled with the entity string.
#
# HIGH-PRECISION INTENTS ONLY. The RAGnosis 50-batch A/B showed intent-framing on precise intents
# (diagnosis, drug_dosing, side_effect, contraindication — each backed by a specific PubMed
# subheading/qualifier) flipped the targeted failures to correct (e.g. APL "which translocation" →
# t(15;17)), cutting intent-mismatch 18→7. But the BROAD intents (treatment, guideline, prognosis,
# drug_comparison, drug_safety) added generic terms that DILUTED retrieval and caused regressions
# (e.g. a pneumothorax management query drifting off the answer). So those are intentionally NOT
# framed — the analyzer's default entity+guideline retrieval already serves them, and the query_sense
# lever covers causation/adverse queries. Keeping this set tight is the whole point of Fix 1.
_INTENT_TEMPLATES: dict[str, list[str]] = {
    "diagnosis": [
        "{e} diagnosis",
        "{e}[Title/Abstract] AND (diagnosis OR diagnostic criteria OR investigation OR cytogenetics)",
    ],
    "drug_dosing": [
        "{e} dose",
        "{e}[Title/Abstract] AND (dose OR dosing OR \"administration and dosage\"[Subheading])",
    ],
    "side_effect": [
        "{e}[Title/Abstract] AND (adverse effect OR side effect OR \"adverse effects\"[Subheading])",
    ],
    "contraindication": [
        "{e}[Title/Abstract] AND (contraindication OR contraindicated)",
    ],
}


def intent_terms(intent: str | None, entities: list[str] | None) -> list[str]:
    """Extra PubMed terms that steer retrieval toward the query's clinical INTENT. [] if nothing to add."""
    templates = _INTENT_TEMPLATES.get((intent or "").strip().lower())
    if not templates:
        return []
    ents = [e.strip() for e in (entities or []) if e and e.strip()]
    if not ents:
        return []
    e = " ".join(ents[:2])
    if len(e) < 3:
        return []
    return [t.format(e=e) for t in templates]
