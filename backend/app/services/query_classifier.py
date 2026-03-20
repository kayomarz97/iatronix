import logging
import re

from app.config import settings

logger = logging.getLogger(__name__)

DRUG_PATTERNS = [
    r"\b(?:dose|dosage|dosing|mg|mcg|drug|medication|pill|tablet|capsule|injection)\b",
    r"\b(?:side effect|adverse|contraindication|interaction|pharmacol|prescri)\b",
    r"\b(?:metformin|lisinopril|amlodipine|atorvastatin|omeprazole|amoxicillin)\b",
    r"\b(?:warfarin|heparin|insulin|prednisone|ibuprofen|acetaminophen)\b",
]

DISEASE_PATTERNS = [
    r"\b(?:disease|syndrome|disorder|condition|diagnosis|diagnos|pathophys)\b",
    r"\b(?:symptom|sign|manifestation|presentation|prognosis|epidemiol)\b",
    r"\b(?:treatment of|management of|therapy for|guidelines for)\b",
    r"\b(?:hypertension|diabetes|asthma|COPD|pneumonia|heart failure)\b",
]

COMPARATIVE_PATTERNS = [
    r"\b(?:vs\.?|versus|compared? to|differ(?:ence)?s? between|comparison)\b",
    r"\b(?:better|worse|superior|inferior|prefer|advantage|disadvantage)\b",
    r"\b(?:which is|what is the difference|how does .+ compare)\b",
]


def _score_patterns(query: str, patterns: list[str]) -> float:
    """Score query against pattern list. Returns 0.0-1.0."""
    matches = sum(1 for p in patterns if re.search(p, query, re.IGNORECASE))
    return min(matches / max(len(patterns) * 0.4, 1), 1.0)


def classify_query(query: str, user_hint: str | None = None) -> tuple[str, float]:
    """
    Classify a medical query. Returns (query_type, confidence).
    If user provides a hint (explicit type), use it with high confidence.
    """
    if user_hint:
        return user_hint, 0.95

    scores = {
        "drug": _score_patterns(query, DRUG_PATTERNS),
        "disease": _score_patterns(query, DISEASE_PATTERNS),
        "comparative": _score_patterns(query, COMPARATIVE_PATTERNS),
    }

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score < settings.classifier_confidence_threshold:
        return "general", best_score

    return best_type, best_score
