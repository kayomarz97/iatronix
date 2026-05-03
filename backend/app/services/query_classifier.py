import json
import logging
import re

from app.config import settings

logger = logging.getLogger(__name__)

_VALID_TYPES = {"drug", "disease", "comparative", "procedure", "evidence", "complex"}

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
    "a specific intervention for a specific population.\n"
    "\n"
    "6. complex — use for EVERYTHING ELSE: multiple entities of mixed types, comorbidities, "
    "broad clinical questions, unclear queries, multi-drug or multi-disease scenarios, general "
    "medical questions without a precise single focus. This is the DEFAULT. When uncertain, "
    "always prefer complex over any other type. NEVER output 'general'.\n"
    "\n"
    "Confidence guide: 0.9+ for unambiguous match, 0.7–0.89 for clear match, "
    "0.5–0.69 for uncertain. Never output confidence below 0.4.\n"
    "\n"
    "Query: {query}"
)


def detect_intent(query: str) -> str:
    """Return 'highlights' for quick-reference style prompts, else 'full'."""
    if _HIGHLIGHTS_RE.search(query):
        return "highlights"
    return "full"


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
        text = text.strip().strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
        data = json.loads(text)
        qtype = data.get("type", "complex")
        conf = float(data.get("confidence", 0.6))
        if qtype not in _VALID_TYPES:
            return _no_llm_fallback(query)
        return qtype, min(max(conf, 0.0), 1.0)
    except Exception:
        logger.debug("LLM query classification failed", exc_info=True)
        return _no_llm_fallback(query)
