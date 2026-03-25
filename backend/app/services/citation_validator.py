import logging
from datetime import datetime

from app.services.url_builder import is_safe_url

logger = logging.getLogger(__name__)

APPROVED_SOURCES = {
    # Guidelines
    "nice",
    "aha",
    "acc",
    "aha/acc",
    "esc",
    "who",
    "idsa",
    "nccn",
    "acog",
    "gold",
    "kdigo",
    "ada",
    # Regulatory
    "fda",
    "ema",
    "mhra",
    # Databases
    "uptodate",
    "bmj best practice",
    "cochrane library",
    "cochrane",
    "pubmed",
    # Pharmacology
    "fda drug labels",
    "fda drug label",
    "bnf",
    "micromedex",
    # Indian regulatory
    "cdsco",
    "indian pharmacopoeia",
    "indian local",
    "medindia",
    "schedule h",
    # Critical care / infectious disease societies
    "isid",
    "ssc",
    "sccm",
    "ats",
    "ers",
    "asm",
    "aasld",
    "easl",
    "esh",
    "isth",
    # Other
    "clinical guidelines",
    "clinical consensus",
}

CURRENT_YEAR = datetime.now().year
MIN_SOURCE_YEAR = 1990

LOE_VALUES = {"I", "II-1", "II-2", "II-3", "III"}
COR_VALUES = {"I", "IIa", "IIb", "III-no-benefit", "III-harm"}


def _is_approved_source(source: str) -> bool:
    """Check if source matches approved list (case-insensitive fuzzy)."""
    source_lower = source.lower().strip()
    for approved in APPROVED_SOURCES:
        if approved in source_lower or source_lower in approved:
            return True
    return False


def validate_citations(response_data: dict, query_type: str) -> list[str]:
    """
    Validate citations in a response. Returns list of validation warnings.
    Non-blocking — warnings are informational, response is still returned.
    """
    warnings = []
    claims = _extract_claims(response_data, query_type)

    low_confidence_count = 0
    missing_citation_count = 0
    total_claims = len(claims)
    seen_unverified: set = set()

    for claim in claims:
        source = claim.get("source", "")
        source_year = claim.get("source_year")
        confidence = claim.get("confidence", "")
        loe = claim.get("loe", "")
        cor = claim.get("cor", "")

        if not source:
            missing_citation_count += 1
            warnings.append(
                f"Missing citation for claim: '{_truncate(claim.get('value', ''))}'"
            )
            continue

        if not _is_approved_source(source) and source not in seen_unverified:
            seen_unverified.add(source)
            warnings.append(f"Unverified source: {source}")

        if source_year is not None:
            if source_year > CURRENT_YEAR:
                warnings.append(f"Future source year: {source_year} for '{source}'")
            elif source_year < MIN_SOURCE_YEAR:
                warnings.append(f"Very old source: {source} ({source_year})")

        if loe and loe not in LOE_VALUES:
            warnings.append(f"Invalid LOE value: '{loe}'")

        if cor and cor not in COR_VALUES:
            warnings.append(f"Invalid COR value: '{cor}'")

        if confidence == "low":
            low_confidence_count += 1

    # Evidence confidence check
    if total_claims > 0:
        low_ratio = (low_confidence_count + missing_citation_count) / total_claims
        if low_ratio > 0.5:
            warnings.insert(
                0,
                "This response has limited evidence support. "
                "Please verify with primary sources.",
            )

    # Reference URL validation — null unsafe URLs and warn (defense-in-depth after url_builder)
    for ref in response_data.get("references", []):
        url = ref.get("url")
        if url is None:
            continue
        if not url.startswith("https://"):
            ref["url"] = None
            warnings.append(
                f"Reference URL uses non-HTTPS scheme (insecure) — removed: '{url[:80]}'"
            )
        elif not is_safe_url(url):
            from urllib.parse import urlparse

            try:
                domain = urlparse(url).netloc
            except Exception:
                domain = url[:40]
            ref["url"] = None
            warnings.append(
                f"Reference URL domain not in approved list — removed: '{domain}'"
            )

    return warnings


def _extract_claims(data: dict, query_type: str) -> list[dict]:
    """Extract all evidenced claim objects from response data."""
    claims = []

    def _walk(obj):
        if isinstance(obj, dict):
            if "loe" in obj and "value" in obj:
                claims.append(obj)
            elif "evidence" in obj and isinstance(obj["evidence"], dict):
                claims.append(obj["evidence"])
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data)
    return claims


def _truncate(text: str, max_len: int = 80) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
