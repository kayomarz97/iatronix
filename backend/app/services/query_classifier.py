import logging
import re

from app.config import settings

logger = logging.getLogger(__name__)

DRUG_PATTERNS = [
    r"\b(?:dose|dosage|dosing|mg|mcg|drug|medication|pill|tablet|capsule|injection)\b",
    r"\b(?:side effect|adverse|contraindication|interaction|pharmacol|prescri)\b",
    r"\b(?:metformin|lisinopril|amlodipine|atorvastatin|omeprazole|amoxicillin)\b",
    r"\b(?:warfarin|heparin|insulin|prednisone|ibuprofen|acetaminophen)\b",
    r"\b(?:losartan|simvastatin|levothyroxine|gabapentin|hydrochlorothiazide|sertraline|fluoxetine|clopidogrel|pantoprazole|escitalopram)\b",
    r"\b(?:montelukast|rosuvastatin|tramadol|duloxetine|tamsulosin|alprazolam|furosemide|carvedilol|cephalexin|azithromycin)\b",
]

DISEASE_PATTERNS = [
    r"\b(?:disease|syndrome|disorder|condition|diagnosis|diagnos|pathophys)\b",
    r"\b(?:symptom|sign|manifestation|presentation|prognosis|epidemiol)\b",
    r"\b(?:treatment of|management of|therapy for|guidelines for)\b",
    r"\b(?:hypertension|diabetes|asthma|COPD|pneumonia|heart failure)\b",
    r"\b(?:stroke|myocardial infarction|atrial fibrillation|chronic kidney disease|cirrhosis|hepatitis|tuberculosis|HIV|sepsis|meningitis)\b",
    r"\b(?:epilepsy|migraine|Parkinson|Alzheimer|multiple sclerosis|lupus|rheumatoid arthritis|osteoporosis|gout|anemia)\b",
    r"\b(?:depression|anxiety|bipolar|schizophrenia|cancer|lymphoma|leukemia|melanoma|pancreatitis|appendicitis)\b",
]

COMPARATIVE_PATTERNS = [
    r"\b(?:vs\.?|versus|compared?\s+to|differ(?:ence)?s?\s+between|comparison)\b",
    r"\b(?:better|worse|superior|inferior|prefer|advantage|disadvantage)\b",
    r"\b(?:which is|what is the difference|how does .+ compare)\b",
    r"\bcompare\b",
]


def _score_patterns(query: str, patterns: list[str]) -> float:
    """Score query against pattern list. Returns 0.0-1.0.

    Matching ANY single pattern gives at least 0.75 to ensure that
    a bare drug/disease name clears the confidence threshold.
    Additional matches scale linearly from 0.75 up to 1.0.
    """
    matches = sum(1 for p in patterns if re.search(p, query, re.IGNORECASE))
    if matches == 0:
        return 0.0
    if matches == 1:
        return 0.75
    # 2+ matches: scale from 0.75 toward 1.0
    return min(0.75 + 0.25 * (matches - 1) / max(len(patterns) - 1, 1), 1.0)


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

    # Comparative is the most specific type — if vs/versus/compare detected, always prefer it
    _HARD_COMPARATIVE = re.compile(
        r"\b(?:vs\.?|versus|compared?\s+to|compared?\s+with|compare\b|"
        r"difference\s+between|comparison\s+(?:of|between))\b",
        re.IGNORECASE,
    )
    if _HARD_COMPARATIVE.search(query) and scores["comparative"] > 0:
        best_type, best_score = "comparative", max(scores["comparative"], 0.80)
    else:
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

    if best_score < settings.classifier_confidence_threshold:
        return "general", best_score

    return best_type, best_score
