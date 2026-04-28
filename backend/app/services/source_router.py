"""Lightweight routing helpers.

The primary medical analysis path is DSPy/LLM-driven. This module only handles:
- minimal fallback entity extraction for obvious structural cases
- model preference selection
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings

_COMPARATIVE_SPLIT = re.compile(
    r"\s+(?:vs\.?|versus|compared?\s+to|compared?\s+with|rather\s+than|instead\s+of)\s+",
    re.IGNORECASE,
)
_STOPWORDS = re.compile(
    r"\b(?:what|is|are|the|about|tell|me|please|explain|give|information|"
    r"management|treatment|guidelines|guideline|dose|dosing|for|of|in|to|a|an|"
    r"approach|workup|evaluation|overview|summary|diagnosis|diagnostic|initial)\b",
    re.IGNORECASE,
)
_CONDITION_RE = re.compile(
    r"\b(?:in|for)\s+([A-Za-z][A-Za-z0-9\s\-/]{2,80}?)(?:\s*[,?.]|$)",
    re.IGNORECASE,
)
_DISEASE_PREFIX_RE = re.compile(
    r"^\s*(?:approach to|management of|treatment of|diagnosis of|workup of|evaluation of|overview of|summary of|initial management of)\s+",
    re.IGNORECASE,
)
_EVIDENCE_ENTITY_RE = re.compile(
    r"^\s*(?:is\s+)?(.+?)\s+(?:safe|effective|beneficial|appropriate|useful)\s+(?:in|for)\s+(.+?)\s*$",
    re.IGNORECASE,
)


def _normalize_entity_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" ,.-")
    return value


def _strip_condition_suffix(value: str) -> str:
    return _normalize_entity_text(_CONDITION_RE.sub("", value, count=1))


@dataclass
class RoutingDecision:
    query_type: str
    entities: list[str]
    fetch_enabled: bool
    preferred_model: str
    fallback_model: str
    condition_context: str | None = None


def extract_entities(query: str, query_type: str) -> list[str]:
    """Fallback-only entity extraction.

    This intentionally avoids medical dictionaries and only does generic cleanup.
    """
    cleaned = re.sub(r"[^\w\s\-/]", " ", query)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if query_type == "comparative":
        parts = [_strip_condition_suffix(p) for p in _COMPARATIVE_SPLIT.split(cleaned) if p.strip()]
        return parts[:2]

    if query_type == "drug":
        condition_match = _CONDITION_RE.search(cleaned)
        if condition_match:
            left = cleaned[: condition_match.start()].strip()
            if left:
                return [left]

    if query_type == "evidence":
        match = _EVIDENCE_ENTITY_RE.match(cleaned)
        if match:
            left = _normalize_entity_text(match.group(1))
            right = _normalize_entity_text(match.group(2))
            return [left, right] if left and right else ([left] if left else [])

    if query_type == "disease":
        cleaned = _DISEASE_PREFIX_RE.sub("", cleaned).strip()

    if query_type == "complex":
        # Anchor: drug name (or procedure / management noun) + primary disease.
        # The remaining qualifiers go into condition_context / comorbidity_list (via DSPy).
        condition_match = _CONDITION_RE.search(cleaned)
        if condition_match:
            left = cleaned[: condition_match.start()].strip()
            right = condition_match.group(1).strip()
            # `left` = the drug or intervention; `right` = primary disease (we keep both).
            if left and right:
                return [_normalize_entity_text(left), _normalize_entity_text(right)]
        # Fall through to default cleanup below.

    collapsed = _STOPWORDS.sub(" ", cleaned)
    collapsed = re.sub(r"\s+", " ", collapsed).strip()
    return [collapsed] if collapsed else []


def extract_condition_context(query: str, query_type: str) -> str | None:
    if query_type not in {"drug", "comparative"}:
        return None
    match = _CONDITION_RE.search(query)
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip()
    return value or None


def route_query(
    query: str,
    query_type: str,
    *,
    entities: list[str] | None = None,
    requested_model: str | None = None,
    user_provider: str | None = None,
    model_explicit: bool = False,
    condition_context: str | None = None,
) -> RoutingDecision:
    entities = entities if entities is not None else extract_entities(query, query_type)
    condition_context = condition_context or extract_condition_context(query, query_type)
    fetch_enabled = query_type in {
        "drug",
        "disease",
        "comparative",
        "procedure",
        "evidence",
        "complex",
    } and bool(entities)

    requested_model = requested_model or settings.model_generate
    preferred = requested_model
    fallback = requested_model

    if user_provider == "anthropic" and not model_explicit:
        # Haiku is the primary model for all query types; Sonnet is the last-resort fallback
        preferred = settings.model_generate
        fallback = settings.model_sonnet

    return RoutingDecision(
        query_type=query_type,
        entities=entities,
        fetch_enabled=fetch_enabled,
        preferred_model=preferred,
        fallback_model=fallback,
        condition_context=condition_context,
    )
