import json
import logging
import re

from pydantic import BaseModel, field_validator

from app.config import settings

logger = logging.getLogger(__name__)

_VALID_TYPES = {"drug", "disease", "comparative", "procedure", "evidence", "complex"}


def normalize_query_type(raw: object) -> str:
    """Coerce any model-emitted value to a valid query_type, defaulting to 'complex'.

    Provider-neutral: works identically for Anthropic/Cerebras/OpenAI output. Legacy 'general'
    and anything unrecognized collapse to 'complex' (the safe catch-all).
    """
    qt = str(raw or "").strip().lower()
    return qt if qt in _VALID_TYPES else "complex"


class ClassificationResult(BaseModel):
    """Validated classifier output (R2). Structured-output guarantee WITHOUT provider-specific
    tool-use — the model still returns JSON, but every field is coerced/clamped here so a stray
    type or an out-of-range confidence can never propagate downstream."""

    query_type: str = "complex"
    confidence: float = 0.6

    @field_validator("query_type", mode="before")
    @classmethod
    def _valid_type(cls, v: object) -> str:
        return normalize_query_type(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_conf(cls, v: object) -> float:
        try:
            return min(max(float(v), 0.0), 1.0)
        except (TypeError, ValueError):
            return 0.6

_HIGHLIGHTS_RE = re.compile(
    r"\b(?:surviving|approach to|initial management of|quick|highlights?|"
    r"key points?|overview of|summary of|pearls?|mnemonic|criteria for|"
    r"emergency management|acute management|first approach)\b",
    re.IGNORECASE,
)

LLM_CLASSIFY_PROMPT = (
    "You are a clinical query router. Return exactly one classification type for the medical query below.\n"
    "Output ONLY valid JSON with no markdown, no explanation: {\"type\": \"...\", \"confidence\": 0.0}\n"
    "\n"
    "CLASSIFICATION RULES — read all rules before deciding, then apply the FIRST that matches:\n"
    "\n"
    "1. comparative — the query EXPLICITLY names exactly two specific entities "
    "(two drugs, two diseases, or two treatment strategies) and asks for a direct comparison, "
    "difference, or choice between them. Both entities must be clearly stated. "
    "Do NOT use this type for: one entity with many properties, vague multi-entity questions, "
    "implicit comparisons, or more than two entities.\n"
    "\n"
    "2. procedure — the query is SOLELY about the step-by-step technique of performing "
    "a specific clinical procedure. There must be no management context, timing question, "
    "outcome question, or post-procedure concern. If anything beyond pure technique is present "
    "(including when/how long/whether to do something) → use evidence instead.\n"
    "\n"
    "3. drug — the query is about a SINGLE pharmaceutical agent with NO clinical condition "
    "or patient context. Asks about mechanism, pharmacology, dosing range, interactions, "
    "side effects, or monitoring of that one drug in isolation.\n"
    "\n"
    "4. disease — the query is about a SINGLE disease, condition, syndrome, or symptom with "
    "NO drug or treatment agent named. Asks about pathophysiology, diagnosis, staging, prognosis, "
    "or overview of that one condition. Medical abbreviations that expand to a single disease name "
    "count as one disease entity.\n"
    "\n"
    "5. evidence — the query involves a drug or intervention in the context of a disease or "
    "patient situation; OR asks when/whether/how long to use something; OR asks about "
    "postoperative or post-procedure management; OR asks about safety or efficacy of "
    "a specific intervention for a specific population; OR asks for the preferred/first-line/"
    "drug of choice for a SINGLE named disease or condition.\n"
    "\n"
    "6. complex — use for EVERYTHING ELSE: multiple entities of mixed types, comorbidities, "
    "broad clinical questions, unclear queries, multi-drug or multi-disease scenarios, general "
    "medical questions without a precise single focus. This is the DEFAULT. When uncertain, "
    "always prefer complex over any other type. NEVER output 'general'.\n"
    "\n"
    "Confidence guide: 0.9+ for unambiguous match, 0.7–0.89 for clear match, "
    "0.5–0.69 for uncertain. Never output confidence below 0.4.\n"
    "\n"
    "EXAMPLES (apply these to calibrate):\n"
    "- 'SGLT2 inhibitors mechanism' → drug (single agent, no condition)\n"
    "- 'SGLT2 inhibitors in CKD' → evidence (drug in condition)\n"
    "- 'drug of choice for CKD' → evidence (first-line query, single condition)\n"
    "- 'drug of choice for CKD with T2DM' → complex (two conditions, no named drug)\n"
    "- 'metformin dose in CKD' → evidence (drug + condition)\n"
    "- 'CKD management' → disease (single condition, no drug named)\n"
    "\n"
    "Query: {query}"
)


def detect_intent(query: str) -> str:
    """Return 'highlights' for quick-reference style prompts, else 'full'."""
    if _HIGHLIGHTS_RE.search(query):
        return "highlights"
    return "full"


def count_named_conditions(condition_context: str | None) -> int:
    """Count DISTINCT clinical conditions recorded in ``condition_context``.

    ``condition_context`` is a comma / 'and' / 'with' / '+' / ';' / '/' joined string (e.g.
    "chronic kidney disease, hypertension"). Deterministic and LLM-agnostic — a conservative
    comorbidity signal for the classifier backstop only, never used for retrieval.
    """
    if not condition_context:
        return 0
    parts = re.split(r",|\band\b|\bwith\b|\+|;|/", condition_context, flags=re.IGNORECASE)
    seen = {p.strip().lower() for p in parts if p and p.strip()}
    return len(seen)


def apply_classifier_backstop(
    query_type: str,
    condition_context: str | None,
    user_forced_type: bool,
) -> tuple[str, bool]:
    """Deterministic tie-breaker for the ambiguous evidence/complex boundary.

    A multi-condition (comorbidity) question such as "CKD and hypertension — which drugs?"
    routinely gets mislabelled 'evidence' or 'drug' by the LLM, which then runs the single-focus
    fetch/prompt path and under-serves the answer. When the analyzer recorded
    ≥ ``classify_backstop_min_conditions`` distinct conditions we nudge those single-focus types
    to 'complex'. Never touches 'comparative' (a legitimate two-entity compare) and never
    overrides a user-forced type. Returns (query_type, changed). No-op unless the flag is on.
    """
    if user_forced_type or not settings.classify_heuristic_backstop_enabled:
        return query_type, False
    if query_type not in ("drug", "evidence", "disease"):
        return query_type, False
    if count_named_conditions(condition_context) >= settings.classify_backstop_min_conditions:
        return "complex", True
    return query_type, False


def _no_llm_fallback(query: str, user_hint: str | None = None) -> tuple[str, float]:
    """Emergency fallback when no LLM key is available.

    Returns 'complex' so the comprehensive fetcher runs — better than no fetch.
    This is used only when both user key and system LLM are unavailable.
    """
    if user_hint and user_hint in _VALID_TYPES:
        return user_hint, 0.99
    return "complex", 0.4


async def classify_query_llm(
    query: str,
    user_key: str | None = None,
    user_provider: str | None = None,
    model_id: str | None = None,
) -> tuple[str, float]:
    """LLM classifier — primary standalone classifier when _analyze_and_expand_query() is unavailable."""
    if not user_key:
        return _no_llm_fallback(query)

    try:
        from app.services.llm_factory import create_llm

        llm = create_llm(
            model_id or settings.model_haiku,
            max_tokens=80,
            user_key=user_key,
            user_provider=user_provider,
        )
        prompt = LLM_CLASSIFY_PROMPT.format(query=query)
        response = await llm.ainvoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        qtype, conf = _parse_classification(text)
        if qtype not in _VALID_TYPES:
            return _no_llm_fallback(query)
        return qtype, min(max(conf, 0.0), 1.0)
    except Exception:
        logger.debug("LLM query classification failed", exc_info=True)
        return _no_llm_fallback(query)


def _parse_classification(text: str) -> tuple[str, float]:
    """Robustly extract (type, confidence) from a model response.

    Tiered recovery so a stray fence, prose wrapper, or trailing comma does NOT collapse a
    valid classification to the expensive 'complex' default:
      1. strip fences → json.loads
      2. regex-extract the first {...} object → json.loads
      3. regex-pull a bare "type": "<valid>" (and optional confidence) from anywhere in the text
    Returns ('complex', 0.4) only when all three fail.
    """
    raw = (text or "").strip()
    clean = raw.strip("`").strip()
    if clean[:4].lower() == "json":
        clean = clean[4:].strip()

    for candidate in (clean, _first_json_object(raw)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            qtype = str(data.get("type", "")).strip().lower()
            if qtype in _VALID_TYPES:
                # Route through the validated model so confidence is clamped consistently.
                r = ClassificationResult(query_type=qtype, confidence=data.get("confidence", 0.6))
                return r.query_type, r.confidence
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Last resort: pull "type": "<valid>" out of free text.
    m = re.search(r'"?type"?\s*[:=]\s*"?(' + "|".join(_VALID_TYPES) + r')"?', raw, re.IGNORECASE)
    if m:
        qtype = m.group(1).lower()
        cm = re.search(r'"?confidence"?\s*[:=]\s*([01]?\.?\d+)', raw)
        conf = float(cm.group(1)) if cm else 0.55
        return qtype, conf
    return "complex", 0.4


def _first_json_object(text: str) -> str | None:
    """Return the first balanced {...} substring, or None."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
