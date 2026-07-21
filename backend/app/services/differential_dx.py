"""Differential-diagnosis query reframing (F3).

"abdominal mass with mets to spleen differential diagnosis" is a DIAGNOSTIC-REASONING question:
the user hands over a *finding* and wants the *ranked list of candidate diagnoses* that could
explain it. A naive search on the entities drifts toward single-disease TREATMENT literature
(e.g. a pancreatic-cancer drug trial that happens to mention "abdominal mass"), which is the
wrong sense — the same failure `query_sense` fixes for causation queries.

When enabled, `differential_terms()` returns extra PubMed terms that target the ETIOLOGY /
DIFFERENTIAL sense (causes / differential diagnosis / workup of the finding), fed into the fetch's
extra_pubmed_terms exactly like `query_sense.sense_terms()`. Returns [] for non-differential queries.

Pure functions, no LLM, no network — safe on the critical path and unit-testable offline.
"""
from __future__ import annotations

import re

# Explicit differential-diagnosis intent.
_DDX_RE = re.compile(
    r"\b(differential\s+diagnos[ei]s|differentials?|ddx|d/dx)\b",
    re.IGNORECASE,
)
# "what could this be / which malignancy / what is causing" style diagnostic questions.
_WHATIS_RE = re.compile(
    r"\b(what|which)\b.{0,40}\b(could|might|cause[sd]?|causing|malignanc|cancer|tumou?r|"
    r"diagnos[ei]s|conditions?|etiolog|aetiolog)\b",
    re.IGNORECASE,
)
# "causes of / etiology of / workup of / evaluation of / approach to <finding>".
_ETIO_RE = re.compile(
    r"\b(causes?\s+of|etiolog\w*\s+of|aetiolog\w*\s+of|work[-\s]?up\s+(of|for)|"
    r"evaluation\s+of|approach\s+to)\b",
    re.IGNORECASE,
)

# Boilerplate stripped to recover the underlying finding, so terms anchor on the FINDING.
_STRIP_RES = [
    re.compile(r"\b(differential\s+diagnos[ei]s|differentials?|ddx|d/dx)\b", re.IGNORECASE),
    re.compile(r"\b(that\s+is\s+)?which\s+(malignanc\w*|cancer|tumou?r|condition|disease)"
               r"(\s+could\s+it\s+be)?\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(could|might)\s+it\s+be\b", re.IGNORECASE),
    re.compile(r"\b(causes?\s+of|etiolog\w*\s+of|aetiolog\w*\s+of|work[-\s]?up\s+(of|for)|"
               r"evaluation\s+of|approach\s+to)\b", re.IGNORECASE),
    re.compile(r"^\s*(what|which|does|do|can|could|is|are)\b", re.IGNORECASE),
]


def is_differential_query(query: str) -> bool:
    """True when the query asks 'what could this finding be?' rather than how to treat a known disease."""
    q = query or ""
    return bool(_DDX_RE.search(q) or _WHATIS_RE.search(q) or _ETIO_RE.search(q))


def extract_finding(query: str) -> str:
    """Recover the clinical FINDING from the query by stripping differential-question boilerplate.
    'abdominal mass with mets to spleen differential diagnosis' -> 'abdominal mass with mets to spleen'."""
    core = query or ""
    for rx in _STRIP_RES:
        core = rx.sub(" ", core)
    core = re.sub(r"\s+", " ", core).strip(" ?.,")
    return core


def differential_terms(query: str) -> list[str]:
    """Extra PubMed terms targeting the etiology/differential sense of the FINDING.
    [] when the query is not a differential-diagnosis question."""
    if not is_differential_query(query):
        return []
    finding = extract_finding(query)
    if len(finding) < 4:
        return []
    terms = [
        f"{finding} differential diagnosis",
        f"{finding} etiology causes",
        f"{finding}[Title/Abstract] AND (differential diagnosis OR etiology OR causes)",
    ]
    return [t for t in terms if len(t) > 12]
