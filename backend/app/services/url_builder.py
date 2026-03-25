"""
Deterministic URL enrichment for Reference objects.

All URLs are generated from structured metadata already fetched from authoritative
sources (PMIDs, DOIs, source names). The LLM is never trusted to produce URLs.
"""

from __future__ import annotations

import re
from urllib.parse import quote, urlparse

# Safe chars for percent-encoding DOI path segments (RFC 3986 unreserved + DOI-allowed)
_DOI_SAFE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~/"

# ── Patterns (same as rag_pipeline, kept local to avoid circular import) ──────
_PMID_RE = re.compile(r"PMID[:\s]*(\d{6,9})", re.I)
_DOI_RE = re.compile(r'(10\.\d{4,9}/[^\s,;"\'\)\]]+)')

MAX_URL_LENGTH = 500

# ── Domain allowlist ──────────────────────────────────────────────────────────
ALLOWED_DOMAINS: frozenset[str] = frozenset(
    {
        "pubmed.ncbi.nlm.nih.gov",
        "doi.org",
        "www.nice.org.uk",
        "www.fda.gov",
        "www.accessdata.fda.gov",
        "www.cochranelibrary.com",
        "www.who.int",
        "www.escardio.org",
        "www.ahajournals.org",
        "www.acc.org",
        "www.idsociety.org",
        "www.nccn.org",
        "www.ema.europa.eu",
        "www.bmj.com",
        "www.nejm.org",
        "www.thelancet.com",
        "jamanetwork.com",
        "www.goldcopd.org",
        "kdigo.org",
        "www.diabetes.org",
        "www.acog.org",
    }
)

# ── Source-name → base URL (matched case-insensitively) ──────────────────────
_SOURCE_URL_MAP: list[tuple[str, str]] = [
    # Order matters — more specific first
    ("fda drug label", "https://www.accessdata.fda.gov/scripts/cder/daf/"),
    ("fda", "https://www.accessdata.fda.gov/scripts/cder/daf/"),
    ("nice", "https://www.nice.org.uk/guidance"),
    ("cochrane", "https://www.cochranelibrary.com/search"),
    ("pubmed", "https://pubmed.ncbi.nlm.nih.gov/"),
    ("esc", "https://www.escardio.org/Guidelines"),
    ("who", "https://www.who.int/publications/"),
    ("aha/acc", "https://www.ahajournals.org/"),
    ("aha", "https://www.ahajournals.org/"),
    ("acc", "https://www.acc.org/guidelines"),
    ("idsa", "https://www.idsociety.org/practice-guideline/"),
    ("nccn", "https://www.nccn.org/guidelines/"),
    ("gold", "https://www.goldcopd.org/gold-reports/"),
    ("kdigo", "https://kdigo.org/guidelines/"),
    ("ada", "https://www.diabetes.org/"),
    ("acog", "https://www.acog.org/clinical/"),
    ("ema", "https://www.ema.europa.eu/"),
    ("bmj", "https://www.bmj.com/"),
]


# ── Public API ────────────────────────────────────────────────────────────────


def is_safe_url(url: str | None) -> bool:
    """Return True only if the URL is https:// and from an allowed domain."""
    if not url or not isinstance(url, str):
        return False
    if len(url) > MAX_URL_LENGTH:
        return False
    if not url.startswith("https://"):
        return False
    try:
        parsed = urlparse(url)
        # Exact frozenset membership — do NOT change to substring/endswith;
        # that would allow subdomain confusion (e.g. "evil.pubmed.ncbi.nlm.nih.gov").
        return parsed.netloc in ALLOWED_DOMAINS
    except Exception:
        return False


def build_pmid_index(fetched_data) -> dict[str, str]:
    """Build a normalised-title → PMID mapping from all abstract lists in fetched_data."""
    index: dict[str, str] = {}
    if fetched_data is None:
        return index

    abstract_lists: list[list] = []
    for attr in (
        "drug_data",
        "disease_data",
        "procedure_data",
        "evidence_data",
    ):
        obj = getattr(fetched_data, attr, None)
        if obj is None:
            continue
        for list_attr in (
            "guideline_abstracts",
            "systematic_review_abstracts",
            "clinical_trial_abstracts",
            "practice_guideline_abstracts",
        ):
            lst = getattr(obj, list_attr, None)
            if lst:
                abstract_lists.append(lst)

    for lst in abstract_lists:
        for abstract in lst:
            if not isinstance(abstract, dict):
                continue
            pmid = abstract.get("pmid")
            title = abstract.get("title", "")
            if pmid and title:
                index[title.strip().lower()] = str(pmid)

    return index


def enrich_references(data: dict, fetched_data=None) -> None:
    """
    Mutate data in-place: fill Reference.url using deterministic rules only.

    Priority order:
      1. Existing url — validated; nulled if unsafe.
      2. PMID lookup from fetched_data abstracts (title match).
      3. PMID inline in source/title text.
      4. DOI inline in source/title text.
      5. Source-name pattern → known base URL.
      6. null (no invented URLs).
    """
    pmid_index = build_pmid_index(fetched_data)
    refs = data.get("references")
    if not refs:
        return

    for ref in refs:
        existing = ref.get("url")

        # Step 1: validate existing URL
        if existing:
            ref["url"] = existing if is_safe_url(existing) else None
            if ref["url"]:
                continue

        title = (ref.get("title") or "").strip()
        source = (ref.get("source") or "").strip()
        combined = f"{source} {title}".strip()

        # Step 2: title match against fetched PMID index
        if title:
            pmid = pmid_index.get(title.lower())
            if pmid:
                candidate = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                ref["url"] = candidate if is_safe_url(candidate) else None
                if ref["url"]:
                    continue

        # Step 3: PMID inline in source/title text
        pmid_match = _PMID_RE.search(combined)
        if pmid_match:
            candidate = f"https://pubmed.ncbi.nlm.nih.gov/{pmid_match.group(1)}/"
            ref["url"] = candidate if is_safe_url(candidate) else None
            if ref["url"]:
                continue

        # Step 4: DOI inline — percent-encode the path to prevent CRLF/fragment injection
        doi_match = _DOI_RE.search(combined)
        if doi_match:
            safe_doi = quote(doi_match.group(1), safe=_DOI_SAFE_CHARS)
            candidate = f"https://doi.org/{safe_doi}"
            ref["url"] = candidate if is_safe_url(candidate) else None
            if ref["url"]:
                continue

        # Step 5: source-name pattern — validate before accepting
        source_lower = source.lower()
        matched_url = _match_source_pattern(source_lower, title)
        if matched_url and is_safe_url(matched_url):
            ref["url"] = matched_url
            continue

        # Step 6: leave null
        ref["url"] = None


# ── Internal helpers ──────────────────────────────────────────────────────────


def _match_source_pattern(source_lower: str, title: str) -> str | None:
    for keyword, base_url in _SOURCE_URL_MAP:
        if keyword in source_lower:
            if title and base_url.endswith(("/", "search", "guidance", "Guidelines")):
                # Append a search query for sources that support it
                if (
                    "search" in base_url
                    or "nice.org.uk" in base_url
                    or "cochrane" in base_url
                ):
                    return f"{base_url}?q={quote(title)}"
            return base_url
    return None
