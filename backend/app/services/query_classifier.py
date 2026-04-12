import json
import logging
import re

from app.config import settings

logger = logging.getLogger(__name__)

_VALID_TYPES = {"drug", "disease", "comparative", "procedure", "evidence", "general"}

_HIGHLIGHTS_RE = re.compile(
    r"\b(?:surviving|approach to|initial management of|quick|highlights?|"
    r"key points?|overview of|summary of|pearls?|mnemonic|criteria for|"
    r"emergency management|acute management|first approach)\b",
    re.IGNORECASE,
)

_COMPARATIVE_RE = re.compile(
    r"\b(?:vs\.?|versus|compare|comparison|difference between|compared to|compared with)\b",
    re.IGNORECASE,
)
_PROCEDURE_RE = re.compile(
    r"\b(?:how to|steps for|procedure for|when to insert|when to remove|"
    r"perform|insert|remove|intubation|extubation|lumbar puncture|thoracentesis|"
    r"central line|arterial line|catheter|drain|checklist|algorithm)\b",
    re.IGNORECASE,
)
_EVIDENCE_RE = re.compile(
    r"\b(?:safe in|effective in|effective for|can .* be used|off[- ]label|"
    r"evidence for|evidence of|trial|clinical evidence|benefit of|safety of)\b",
    re.IGNORECASE,
)
_DISEASE_RE = re.compile(
    r"\b(?:management|treatment|diagnosis|workup|approach to|evaluation of|"
    r"guideline|guidelines|staging|classification|prognosis|complications?|"
    r"acute|chronic|syndrome|disease|failure|embolism|hypertension|pancreatitis)\b",
    re.IGNORECASE,
)
_DRUG_IN_CONDITION_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9\-]{2,40}(?:\s+[A-Za-z][A-Za-z0-9\-]{2,40}){0,2})\s+(?:in|for)\s+([A-Za-z].{2,120})$",
    re.IGNORECASE,
)

LLM_CLASSIFY_PROMPT = """Classify this medical query into exactly one type.
Return ONLY valid JSON with no extra text: {{"type": "...", "confidence": 0.0}}

Types:
- drug = drug or molecule lookup, dosing, mechanism, side effects, monitoring, interactions
- disease = disease/condition overview, diagnosis, criteria, treatment, prognosis
- comparative = explicit comparison between drugs, diseases, or management options
- procedure = how to perform, stepwise technique, insertion/removal, protocols
- evidence = whether an intervention is safe/effective/appropriate in a condition, or evidence synthesis
- general = broad clinical summary, quick pearls, or anything not clearly above

Query: {query}"""


def detect_intent(query: str) -> str:
    """Return 'highlights' for quick-reference style prompts, else 'full'."""
    if _HIGHLIGHTS_RE.search(query):
        return "highlights"
    return "full"


def classify_query(query: str, user_hint: str | None = None) -> tuple[str, float]:
    """Minimal structural fallback classifier.

    This is intentionally not a medical-routing engine. The primary path is LLM/DSPy
    analysis. These checks only catch obvious structure when that path is unavailable.
    """
    if user_hint:
        return user_hint, 0.99

    normalized = re.sub(r"\s+", " ", query.strip())
    token_count = len(re.findall(r"[A-Za-z0-9\-]+", normalized))

    if _COMPARATIVE_RE.search(query):
        return "comparative", 0.9
    if _PROCEDURE_RE.search(query):
        return "procedure", 0.85
    if _EVIDENCE_RE.search(query):
        return "evidence", 0.8
    drug_in_condition = _DRUG_IN_CONDITION_RE.match(normalized)
    if drug_in_condition and token_count <= 10:
        left = drug_in_condition.group(1)
        if len(left.split()) <= 3:
            return "drug", 0.75
    if _DISEASE_RE.search(query):
        return "disease", 0.75
    if token_count <= 4 and not detect_intent(query) == "highlights":
        return "disease", 0.6
    if detect_intent(query) == "highlights":
        if token_count <= 6:
            return "disease", 0.6
        return "general", 0.7
    return "general", 0.4


async def classify_query_llm(
    query: str,
    user_key: str | None = None,
    user_provider: str | None = None,
    model_id: str | None = None,
) -> tuple[str, float]:
    """LLM classifier used as the primary route when a user key is available."""
    if not user_key:
        return classify_query(query)

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
        qtype = data.get("type", "general")
        conf = float(data.get("confidence", 0.6))
        if qtype not in _VALID_TYPES:
            return classify_query(query)
        return qtype, min(max(conf, 0.0), 1.0)
    except Exception:
        logger.debug("LLM query classification failed", exc_info=True)
        return classify_query(query)
