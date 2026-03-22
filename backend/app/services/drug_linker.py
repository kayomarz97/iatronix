import json
import logging
import os
import re

from Levenshtein import distance as levenshtein_distance
from metaphone import doublemetaphone

from app.config import settings
from app.schemas.query import TextNode

logger = logging.getLogger(__name__)

# Drug dictionary loaded at module level
_drug_dict: dict = {}
_drug_names_lower: set[str] = set()
_brand_to_generic: dict[str, str] = {}
_abbreviation_to_generic: dict[str, str] = {}


def load_drug_dictionary(path: str | None = None):
    """Load the drug dictionary from JSON file."""
    global _drug_dict, _drug_names_lower, _brand_to_generic, _abbreviation_to_generic

    if path is None:
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "drug_dictionary.json"
        )

    try:
        with open(path) as f:
            _drug_dict = json.load(f)
    except FileNotFoundError:
        logger.warning(f"Drug dictionary not found at {path}")
        return

    _drug_names_lower = set()
    _brand_to_generic = {}
    _abbreviation_to_generic = {}

    for entry in _drug_dict.get("drugs", []):
        generic = entry["generic_name"].lower()
        _drug_names_lower.add(generic)
        for brand in entry.get("brand_names", []):
            _brand_to_generic[brand.lower()] = generic
            _drug_names_lower.add(brand.lower())
        for abbrev in entry.get("abbreviations", []):
            _abbreviation_to_generic[abbrev.lower()] = generic
            _drug_names_lower.add(abbrev.lower())
        for synonym in entry.get("synonyms", []):
            _drug_names_lower.add(synonym.lower())

    logger.info(f"Loaded {len(_drug_dict.get('drugs', []))} drugs into dictionary")


def _exact_match(word: str) -> str | None:
    """Exact word-boundary match against dictionary."""
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


def process_text_nodes(response_data: dict, query_type: str) -> list[TextNode]:
    """
    Process response into TextNodes with drug links.
    Exact matching on all text, fuzzy only on designated drug fields.
    """
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
