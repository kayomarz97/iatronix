"""
source_router.py — Rule-based query routing.
Zero AI tokens. Extracts entity names and chooses the preferred model tier.
"""

import re
from dataclasses import dataclass

from app.config import settings

_DRUG_STRIP = re.compile(
    r"\b(?:what|is|are|the|dose|dosage|dosing|of|for|drug|medication|tell|me|about|"
    r"side|effects|interactions|contraindications|pharmacokinetics|mechanism|action|"
    r"how|does|work|info|on|regarding|uses|use|used|indication|indications|"
    r"give|i|need|information|please|provide|describe|explain|and|in|its|with|"
    r"adverse|reaction|reactions|profile|safety|efficacy|review|its|a|an)\b",
    re.IGNORECASE,
)

_DISEASE_STRIP = re.compile(
    r"\b(?:what|is|are|the|tell|me|about|how|to|treat|treatment|of|management|"
    r"manage|for|regarding|guidelines|guideline|etiology|aetiology|pathophysiology|"
    r"diagnosis|diagnose|signs|symptoms|presentation|clinical|features|prognosis|"
    r"complication|complications|epidemiology|give|i|need|information|please|"
    r"provide|describe|explain|and|in|its|with|a|an)\b",
    re.IGNORECASE,
)

_COMPARATIVE_SPLIT = re.compile(
    r"\s+(?:vs\.?|versus|compared?\s+to|and)\s+",
    re.IGNORECASE,
)

_COMPARATIVE_PREFIX = re.compile(
    r"^(?:compare(?:\s+and\s+contrast)?|what(?:\s+is|\s+are)?\s+(?:the\s+)?"
    r"(?:difference|differences|comparison)\s+(?:between|of)|"
    r"difference\s+between|comparison\s+(?:of|between))\s+",
    re.IGNORECASE,
)

_PROCEDURE_STRIP = re.compile(
    r"\b(?:what|is|are|the|when|do|you|how|to|should|we|change|replace|insert|"
    r"remove|perform|place|steps|for|a|an|in|indication|indications|protocol|"
    r"guideline|guidelines|procedure|checklist|algorithm)\b",
    re.IGNORECASE,
)

_EVIDENCE_STRIP = re.compile(
    r"\b(?:is|can|should|be|given|used|prescribed|recommended|safe|effective|"
    r"in|for|the|a|an|role|of|evidence|studies|trial|benefit|efficacy|safety)\b",
    re.IGNORECASE,
)


@dataclass
class RoutingDecision:
    query_type: str
    entities: list
    fetch_enabled: bool
    preferred_model: str
    fallback_model: str


def extract_entities(query: str, query_type: str) -> list:
    """Extract drug/disease entity names from a query using regex stripping.
    No AI tokens used.
    """
    _TRAILING_NOISE = re.compile(
        r"\s+(?:comparison|compare|versus|vs\.?|and|or|difference|between|"
        r"info|information|dosage|dose|side|effects|uses|review)\s*$",
        re.IGNORECASE,
    )

    if query_type == "comparative":
        cleaned = _COMPARATIVE_PREFIX.sub("", query).strip()
        parts = _COMPARATIVE_SPLIT.split(cleaned)
        return [
            _clean_entity(_TRAILING_NOISE.sub("", p)) for p in parts[:2] if p.strip()
        ]

    if query_type == "drug":
        stripped = _DRUG_STRIP.sub(" ", query)
        entity = _clean_entity(stripped)
        return [entity] if entity else []

    if query_type == "disease":
        stripped = _DISEASE_STRIP.sub(" ", query)
        entity = _clean_entity(stripped)
        return [entity] if entity else []

    if query_type == "procedure":
        stripped = _PROCEDURE_STRIP.sub(" ", query)
        entity = _clean_entity(stripped)
        return [entity] if entity else []

    if query_type == "evidence":
        stripped = _EVIDENCE_STRIP.sub(" ", query)
        entity = _clean_entity(stripped)
        # Evidence queries often have multiple terms (drug + condition)
        # Return the full stripped string as a single entity
        return [entity] if entity else []

    return []


def _clean_entity(text: str) -> str:
    """Remove punctuation, collapse whitespace, strip."""
    text = re.sub(r"[^\w\s\-]", "", text).strip()
    return re.sub(r"\s+", " ", text).strip()


def route_query(query: str, query_type: str) -> RoutingDecision:
    """Produce a RoutingDecision from classified query type.

    Model selection logic:
    - drug → Haiku (FDA label is structured; LLM just formats)
    - disease → Sonnet (PubMed abstracts require synthesis from multiple societies)
    - comparative drug-vs-drug → Haiku
    - comparative disease-vs-disease → Sonnet
    - general → Sonnet (pure generation, no API data)
    """
    entities = extract_entities(query, query_type)
    fetch_enabled = query_type in (
        "drug",
        "disease",
        "comparative",
        "procedure",
        "evidence",
    ) and bool(entities)

    if query_type == "drug":
        preferred = settings.model_haiku
        fallback = settings.model_sonnet
    elif query_type == "comparative":
        # Single-word entities are likely drug names; multi-word = likely diseases
        likely_drugs = sum(1 for e in entities if len(e.split()) == 1)
        preferred = settings.model_haiku if likely_drugs >= 1 else settings.model_sonnet
        fallback = settings.model_sonnet
    else:
        # disease and general both use Sonnet
        preferred = settings.model_sonnet
        fallback = settings.model_sonnet

    return RoutingDecision(
        query_type=query_type,
        entities=entities,
        fetch_enabled=fetch_enabled,
        preferred_model=preferred,
        fallback_model=fallback,
    )
