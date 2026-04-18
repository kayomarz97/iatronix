import logging
import re

from Levenshtein import distance as levenshtein_distance
from metaphone import doublemetaphone

from app.config import settings
from app.schemas.query import TextNode

logger = logging.getLogger(__name__)

# Drug name registry — populated at runtime from RxNorm API (Phase 4).
# Empty set is safe: exact/fuzzy match simply never fires, text nodes pass through unlinked.
_drug_names_lower: set[str] = set()
_brand_to_generic: dict[str, str] = {}
_abbreviation_to_generic: dict[str, str] = {}
_rxnorm_loaded: bool = False

import httpx
import json
import asyncio

async def _fetch_rxnorm_names(drug_name: str) -> list[str]:
    """Fetch alternative drug names for a specific drug (4.1)."""
    try:
        import redis.asyncio as aioredis
        _r = aioredis.from_url(settings.redis_url, decode_responses=True)
        cache_key = f"rxnorm:drugnames:{drug_name.lower().strip()}"
        cached = await _r.get(cache_key)
        if cached:
            await _r.aclose()
            return json.loads(cached)
    except Exception:
        _r = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://rxnav.nlm.nih.gov/REST/drugs.json",
                params={"name": drug_name}
            )
            data = resp.json()
            names = []
            if data.get("drugGroup", {}).get("conceptGroup"):
                for cg in data["drugGroup"]["conceptGroup"]:
                    for cp in cg.get("conceptProperties", []):
                        if cp.get("name"):
                            names.append(cp["name"])
            
            if _r and names:
                await _r.setex(cache_key, 604800, json.dumps(names))
            if _r:
                await _r.aclose()
            return names
    except Exception:
        if _r:
            await _r.aclose()
        return []

async def _init_rxnorm_registry():
    global _drug_names_lower, _rxnorm_loaded
    if _rxnorm_loaded:
        return

    _rxnorm_loaded = True
    try:
        import redis.asyncio as aioredis
        _r = aioredis.from_url(settings.redis_url, decode_responses=True)
        cached = await _r.get("rxnorm:displaynames")
        if cached:
            _drug_names_lower = set(json.loads(cached))
            await _r.aclose()
            return
    except Exception:
        _r = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://rxnav.nlm.nih.gov/REST/displaynames.json")
            if resp.status_code == 200:
                data = resp.json()
                terms = data.get("displayTermsList", {}).get("term", [])
                if terms:
                    _drug_names_lower = {t.lower() for t in terms}
                    if _r:
                        await _r.setex("rxnorm:displaynames", 604800, json.dumps(list(_drug_names_lower)))
    except Exception:
        pass
    finally:
        if _r:
            await _r.aclose()


def _exact_match(word: str) -> str | None:
    """Exact word-boundary match against runtime-populated drug registry."""
    w = word.lower()
    if w in _drug_names_lower:
        return w
    if w in _brand_to_generic:
        return _brand_to_generic[w]
    if w in _abbreviation_to_generic:
        return _abbreviation_to_generic[w]
    return None


def _fuzzy_match(word: str) -> tuple[str, float] | None:
    """Fuzzy match using Levenshtein + metaphone tiebreaker. Only for drug_names fields."""
    if not _drug_names_lower:
        return None

    w = word.lower()
    w_len = len(w)

    if w_len < 5:
        return None

    max_dist = (
        settings.fuzzy_max_distance_short
        if w_len <= 8
        else settings.fuzzy_max_distance_long
    )

    best_match = None
    best_score = 0.0

    for drug_name in _drug_names_lower:
        if abs(len(drug_name) - w_len) > max_dist:
            continue
        dist = levenshtein_distance(w, drug_name)
        if dist <= max_dist:
            score = 1.0 - (dist / max(w_len, len(drug_name)))
            if score > best_score:
                best_score = score
                best_match = drug_name

    if best_match and best_score >= settings.drug_link_min_score:
        # Use metaphone as tiebreaker
        w_meta = doublemetaphone(w)
        m_meta = doublemetaphone(best_match)
        if w_meta[0] == m_meta[0]:
            best_score = min(best_score + 0.05, 1.0)
        return best_match, best_score

    return None


# Fields where fuzzy matching is allowed
FUZZY_ALLOWED_FIELDS = {"drug_names", "drug", "drug_name", "related_drugs"}


async def process_text_nodes(response_data: dict, query_type: str) -> list[TextNode]:
    """
    Process response into TextNodes with drug links.
    Exact matching on all text, fuzzy only on designated drug fields.
    When _drug_names_lower is empty (RxNorm not yet loaded), returns plain text nodes.
    """
    await _init_rxnorm_registry()
    
    text_nodes = []
    all_text = _extract_all_text(response_data)
    drug_field_words = _extract_drug_field_words(response_data)

    # Process combined text
    for segment in all_text:
        words = re.split(r"(\s+)", segment)
        current_text = ""

        for word in words:
            if not word.strip():
                current_text += word
                continue

            clean_word = re.sub(r"[^\w-]", "", word)
            if not clean_word:
                current_text += word
                continue

            exact = _exact_match(clean_word)
            if exact:
                if current_text:
                    text_nodes.append(TextNode(type="text", content=current_text))
                    current_text = ""
                text_nodes.append(
                    TextNode(
                        type="drug_link",
                        content=word,
                        drug_query=exact,
                        match_score=1.0,
                    )
                )
                continue

            # Fuzzy only for words from drug fields
            if clean_word.lower() in drug_field_words:
                fuzzy = _fuzzy_match(clean_word)
                if fuzzy:
                    if current_text:
                        text_nodes.append(TextNode(type="text", content=current_text))
                        current_text = ""
                    text_nodes.append(
                        TextNode(
                            type="drug_link",
                            content=word,
                            drug_query=fuzzy[0],
                            match_score=fuzzy[1],
                        )
                    )
                    continue

            current_text += word

        if current_text:
            text_nodes.append(TextNode(type="text", content=current_text))

    return text_nodes


def _extract_all_text(data, depth: int = 0) -> list[str]:
    """Extract all string values from response for text node processing."""
    texts = []
    if depth > 10:
        return texts
    if isinstance(data, str):
        if len(data) > 3:
            texts.append(data)
    elif isinstance(data, dict):
        for v in data.values():
            texts.extend(_extract_all_text(v, depth + 1))
    elif isinstance(data, list):
        for item in data:
            texts.extend(_extract_all_text(item, depth + 1))
    return texts


def _extract_drug_field_words(data, depth: int = 0) -> set[str]:
    """Extract words from designated drug fields for fuzzy matching scope."""
    words = set()
    if depth > 10:
        return words
    if isinstance(data, dict):
        for k, v in data.items():
            if k in FUZZY_ALLOWED_FIELDS:
                if isinstance(v, str):
                    words.update(w.lower() for w in re.findall(r"\w+", v))
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str):
                            words.update(w.lower() for w in re.findall(r"\w+", item))
            words.update(_extract_drug_field_words(v, depth + 1))
    elif isinstance(data, list):
        for item in data:
            words.update(_extract_drug_field_words(item, depth + 1))
    return words
