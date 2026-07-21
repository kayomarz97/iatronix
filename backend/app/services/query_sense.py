"""Query-sense framing for causation / adverse-effect questions.

"does paracetamol cause fever" is an ADVERSE/causation question, but a naive "paracetamol fever"
search is dominated by "paracetamol FOR fever" (indication) literature — the opposite sense. When
enabled, `sense_terms()` returns extra PubMed terms that target the adverse sense (drug-induced /
side effect), fed into the fetch's extra_pubmed_terms. Returns [] for non-causation queries.
"""
from __future__ import annotations

import re

_CAUSE_RE = re.compile(
    r"\b(cause[sd]?|causing|induce[sd]?|inducing|lead(?:s|ing)?\s+to|side[-\s]?effects?|"
    r"adverse|provoke[sd]?|trigger[sd]?|result\s+in)\b",
    re.IGNORECASE,
)
_LEAD_INTERROGATIVE_RE = re.compile(r"^(does|do|can|could|will|is|are|why|how|what)\b", re.IGNORECASE)


def is_adverse_query(query: str) -> bool:
    """True when the query asks whether something CAUSES an effect (vs. treats it)."""
    return bool(_CAUSE_RE.search(query or ""))


def sense_terms(query: str) -> list[str]:
    """Extra PubMed terms targeting the adverse/causation sense. [] if not a causation query."""
    if not is_adverse_query(query):
        return []
    core = _LEAD_INTERROGATIVE_RE.sub("", (query or "").strip()).strip()
    core = _CAUSE_RE.sub(" ", core)                 # drop the causation verb/phrase
    core = re.sub(r"\s+", " ", core).strip(" ?.")
    if len(core) < 3:
        return []
    terms = [
        f"{core} adverse effect",
        f"{core} drug induced",
        f"{core} side effect",
    ]
    return [t for t in terms if len(t) > 12]
