import logging
import re

logger = logging.getLogger(__name__)

# Dangerous drug/dose combinations that warrant warnings
HIGH_RISK_DRUGS = {
    "warfarin",
    "heparin",
    "enoxaparin",
    "methotrexate",
    "lithium",
    "digoxin",
    "theophylline",
    "phenytoin",
    "carbamazepine",
    "valproic acid",
    "cyclosporine",
    "tacrolimus",
    "colchicine",
    "opioid",
    "morphine",
    "fentanyl",
    "hydromorphone",
    "insulin",
}

CONTRAINDICATION_PAIRS = [
    ({"methotrexate"}, {"trimethoprim", "nsaid"}),
    ({"warfarin"}, {"aspirin", "nsaid", "ibuprofen"}),
    (
        {"ace inhibitor", "lisinopril", "enalapril", "ramipril"},
        {"potassium", "spironolactone"},
    ),
    (
        {"maoi", "phenelzine", "tranylcypromine"},
        {"ssri", "snri", "meperidine", "tramadol"},
    ),
    ({"lithium"}, {"nsaid", "ibuprofen", "ace inhibitor", "thiazide"}),
]

RED_FLAG_PATTERNS = [
    r"\b(?:suicid|self.?harm|overdose)\b",
    r"\b(?:anaphyla|angioedema)\b",
    r"\b(?:serotonin syndrome|neuroleptic malignant)\b",
    r"\b(?:torsades|qt prolong)\b",
    r"\b(?:stevens.johnson|toxic epidermal)\b",
]


def check_safety(query: str, response_data: dict, query_type: str) -> list[str]:
    """Run safety checks on query and response. Returns list of warnings."""
    warnings = []
    query_lower = query.lower()
    response_text = str(response_data).lower()

    # Red flag patterns in query
    for pattern in RED_FLAG_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            warnings.append(
                "This query involves a potentially life-threatening condition. "
                "Seek immediate medical attention if applicable."
            )
            break

    # Red flag patterns in response
    for pattern in RED_FLAG_PATTERNS:
        if re.search(pattern, response_text, re.IGNORECASE):
            warnings.append(
                "This response mentions a serious adverse event. "
                "Clinical correlation and monitoring are essential."
            )
            break

    # High-risk drug mentions
    for drug in HIGH_RISK_DRUGS:
        if drug in query_lower:
            warnings.append(
                f"'{drug}' has a narrow therapeutic index. "
                "Dosing should be verified with current guidelines and individualized."
            )
            break

    # Check contraindication pairs
    combined_text = f"{query_lower} {response_text}"
    for group_a, group_b in CONTRAINDICATION_PAIRS:
        a_found = any(d in combined_text for d in group_a)
        b_found = any(d in combined_text for d in group_b)
        if a_found and b_found:
            warnings.append(
                f"Potential drug interaction detected between "
                f"{group_a & set(combined_text.split())} and "
                f"{group_b & set(combined_text.split())}. "
                "Verify clinical significance."
            )

    return warnings
