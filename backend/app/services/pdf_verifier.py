"""Auto-verify uploaded PDFs against known medical publishers.

Checks PDF metadata, DOI, ISBN, and publisher patterns.
Verified PDFs become searchable by all users.
"""

import io
import logging
import re
from typing import Optional

import httpx
import pdfplumber

logger = logging.getLogger(__name__)

KNOWN_PUBLISHERS = [
    "elsevier", "springer", "wiley", "wolters kluwer", "lippincott",
    "mcgraw-hill", "mcgraw hill", "oxford university press", "cambridge university press",
    "nature", "bmj", "lancet", "nejm", "new england journal",
    "aha", "american heart association", "acc", "american college of cardiology",
    "esc", "european society of cardiology",
    "who", "world health organization",
    "nice", "national institute for health",
    "fda", "food and drug administration",
    "acp", "american college of physicians",
    "idsa", "infectious diseases society",
    "acog", "american college of obstetricians",
    "acs", "american chemical society",
    "thieme", "karger", "taylor & francis", "sage publications",
    "jama", "annals of internal medicine", "chest journal",
    "cochrane", "uptodate",
]

DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s,;\"')\]]+")
ISBN_PATTERN = re.compile(r"(?:ISBN[-\s]?(?:13|10)?[-:\s]?)?(97[89][-\s]?\d{1,5}[-\s]?\d{1,7}[-\s]?\d{1,7}[-\s]?\d)")


def verify_pdf(file_bytes: bytes) -> tuple[bool, Optional[str]]:
    """Check if a PDF is from a known medical publisher.

    Returns (is_verified, publisher_name).
    """
    try:
        publisher = _check_metadata(file_bytes)
        if publisher:
            return True, publisher

        first_pages_text = _extract_first_pages(file_bytes, max_pages=3)

        publisher = _check_doi(first_pages_text)
        if publisher:
            return True, publisher

        publisher = _check_publisher_patterns(first_pages_text)
        if publisher:
            return True, publisher

        if _check_isbn(first_pages_text):
            return True, "Published book (ISBN verified)"

    except Exception:
        logger.debug("PDF verification failed", exc_info=True)

    return False, None


def _check_metadata(file_bytes: bytes) -> Optional[str]:
    """Check PDF metadata fields for known publishers."""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            meta = pdf.metadata or {}
            for field in ["Producer", "Creator", "Author"]:
                value = (meta.get(field) or "").lower()
                for pub in KNOWN_PUBLISHERS:
                    if pub in value:
                        return pub.title()
    except Exception:
        pass
    return None


def _extract_first_pages(file_bytes: bytes, max_pages: int = 3) -> str:
    """Extract text from the first N pages of the PDF."""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            texts = []
            for page in pdf.pages[:max_pages]:
                text = page.extract_text() or ""
                texts.append(text)
            return "\n".join(texts)
    except Exception:
        return ""


def _check_doi(text: str) -> Optional[str]:
    """Extract DOI and validate via doi.org API."""
    match = DOI_PATTERN.search(text)
    if not match:
        return None

    doi = match.group(0).rstrip(".")
    try:
        resp = httpx.get(
            f"https://doi.org/api/handles/{doi}",
            timeout=5.0,
            follow_redirects=False,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("responseCode") == 1:
                return f"DOI verified ({doi})"
    except Exception:
        logger.debug("DOI validation failed for %s", doi)

    return None


def _check_publisher_patterns(text: str) -> Optional[str]:
    """Search first pages text for known publisher names."""
    text_lower = text.lower()
    for pub in KNOWN_PUBLISHERS:
        if pub in text_lower:
            return pub.title()
    return None


def _check_isbn(text: str) -> bool:
    """Check if text contains a valid ISBN."""
    match = ISBN_PATTERN.search(text)
    return match is not None
