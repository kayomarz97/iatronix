"""
data_fetcher.py — Parallel API fetching from free medical databases.

Fetches authoritative raw data (FDA labels, PubMed guidelines, MedlinePlus, etc.)
so the LLM only needs to FORMAT, not generate knowledge from scratch.
All API calls are async, fire-and-forget, and silent on failure.
"""

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Journal registry (loaded once at import time)
# ------------------------------------------------------------------

_JOURNAL_REGISTRY: dict = {}


def _load_journal_registry() -> None:
    global _JOURNAL_REGISTRY
    try:
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "medical_journals.json"
        )
        path = os.path.normpath(path)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                _JOURNAL_REGISTRY = json.load(f)
    except Exception:
        logger.warning("Failed to load medical_journals.json", exc_info=True)


_load_journal_registry()


# Mapping from query specialty keywords to journal registry keys
_SPECIALTY_MAP: dict[str, list[str]] = {
    "heart": ["cardiology"],
    "cardiac": ["cardiology"],
    "cardio": ["cardiology"],
    "hypertension": ["cardiology"],
    "arrhythmia": ["cardiology"],
    "cancer": ["oncology"],
    "tumor": ["oncology"],
    "neoplasm": ["oncology"],
    "lymphoma": ["oncology", "hematology"],
    "leukemia": ["oncology", "hematology"],
    "brain": ["neurology"],
    "neuro": ["neurology"],
    "stroke": ["neurology"],
    "epilepsy": ["neurology"],
    "seizure": ["neurology"],
    "diabetes": ["endocrinology"],
    "thyroid": ["endocrinology"],
    "insulin": ["endocrinology"],
    "lung": ["pulmonology"],
    "asthma": ["pulmonology"],
    "copd": ["pulmonology"],
    "pneumonia": ["pulmonology", "infectious_disease"],
    "infection": ["infectious_disease"],
    "antibiotic": ["infectious_disease"],
    "hiv": ["infectious_disease"],
    "tuberculosis": ["infectious_disease", "tropical_medicine"],
    "malaria": ["tropical_medicine", "infectious_disease"],
    "liver": ["gastroenterology"],
    "hepatitis": ["gastroenterology", "infectious_disease"],
    "gastric": ["gastroenterology"],
    "bowel": ["gastroenterology"],
    "kidney": ["nephrology"],
    "renal": ["nephrology"],
    "dialysis": ["nephrology"],
    "arthritis": ["rheumatology"],
    "lupus": ["rheumatology"],
    "autoimmune": ["rheumatology"],
    "depression": ["psychiatry"],
    "anxiety": ["psychiatry"],
    "schizophrenia": ["psychiatry"],
    "bipolar": ["psychiatry"],
    "child": ["pediatrics"],
    "neonatal": ["pediatrics"],
    "pediatric": ["pediatrics"],
    "surgery": ["surgery"],
    "surgical": ["surgery"],
    "fracture": ["orthopedics"],
    "joint": ["orthopedics"],
    "spine": ["orthopedics"],
    "pregnancy": ["obstetrics_gynecology"],
    "obstetric": ["obstetrics_gynecology"],
    "gynecol": ["obstetrics_gynecology"],
    "skin": ["dermatology"],
    "dermat": ["dermatology"],
    "psoriasis": ["dermatology"],
    "eye": ["ophthalmology"],
    "retina": ["ophthalmology"],
    "glaucoma": ["ophthalmology"],
    "icu": ["critical_care"],
    "sepsis": ["critical_care", "infectious_disease"],
    "ventilat": ["critical_care"],
    "anesthes": ["anesthesiology"],
    "pain": ["anesthesiology"],
    "blood": ["hematology"],
    "anemia": ["hematology"],
    "coagul": ["hematology"],
    "thrombosis": ["hematology"],
    "pulmonary": ["pulmonology", "cardiology"],
    "pah": ["pulmonology", "cardiology"],
    "pulmonary hypertension": ["pulmonology", "cardiology"],
    "right heart": ["cardiology", "pulmonology"],
    "prostate": ["urology"],
    "bladder": ["urology"],
    "urinary": ["urology"],
}


def _get_journal_filter(entity: str) -> str:
    """Build a PubMed journal filter string (TA field) for the entity's specialty.

    Returns top-5 ranked journal abbreviations as OR-joined TA filters,
    or empty string if no specialty match.
    """
    entity_lower = entity.lower()
    matched_specialties: set[str] = set()

    for keyword, specialties in _SPECIALTY_MAP.items():
        if keyword in entity_lower:
            matched_specialties.update(specialties)

    if not matched_specialties:
        return ""

    abbrevs: list[str] = []
    for spec in matched_specialties:
        journals = _JOURNAL_REGISTRY.get(spec, [])
        for j in journals[:5]:  # top 5 per specialty
            abbr = j.get("abbrev")
            if abbr and j.get("pubmed"):
                abbrevs.append(abbr)

    if not abbrevs:
        return ""

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for a in abbrevs:
        if a not in seen:
            seen.add(a)
            unique.append(a)

    # Limit to 8 journals to keep query reasonable
    ta_parts = [f'"{a}"[TA]' for a in unique[:8]]
    return "(" + " OR ".join(ta_parts) + ")"


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


@dataclass
class DrugFetchResult:
    generic_name: Optional[str] = None
    brand_name: Optional[str] = None
    drug_class: Optional[str] = None
    drug_class_rxnorm: Optional[str] = None
    indications_raw: Optional[str] = None
    dosing_raw: Optional[str] = None
    contraindications_raw: Optional[str] = None
    warnings_raw: Optional[str] = None
    adverse_reactions_raw: Optional[str] = None
    drug_interactions_raw: Optional[str] = None
    pharmacokinetics_raw: Optional[str] = None
    special_populations_raw: Optional[str] = None
    mechanism_raw: Optional[str] = None
    fda_label_source_year: Optional[int] = None
    top_adverse_events: list = field(default_factory=list)
    rxcui: Optional[str] = None
    chembl_mechanism: Optional[str] = None
    chembl_atc_class: Optional[str] = None
    drug_interaction_pairs: list = field(default_factory=list)  # RxNorm DDI pairs
    guideline_abstracts: list = field(default_factory=list)
    systematic_review_abstracts: list = field(default_factory=list)
    clinical_trial_abstracts: list = field(default_factory=list)
    data_source: str = "unknown"
    fetch_success: bool = False


@dataclass
class DiseaseFetchResult:
    guideline_abstracts: list = field(default_factory=list)
    systematic_review_abstracts: list = field(default_factory=list)
    nice_recommendations: list = field(default_factory=list)
    medlineplus_summary: Optional[str] = None
    semantic_papers: list = field(default_factory=list)
    fetch_success: bool = False


@dataclass
class ProcedureFetchResult:
    guideline_abstracts: list = field(default_factory=list)
    practice_guideline_abstracts: list = field(default_factory=list)
    fetch_success: bool = False


@dataclass
class EvidenceFetchResult:
    clinical_trial_abstracts: list = field(default_factory=list)
    systematic_review_abstracts: list = field(default_factory=list)
    guideline_abstracts: list = field(default_factory=list)
    fetch_success: bool = False


@dataclass
class FetchedData:
    query_type: str
    drug_data: Optional[DrugFetchResult] = None
    disease_data: Optional[DiseaseFetchResult] = None
    condition_data: Optional[DiseaseFetchResult] = (
        None  # disease guidelines for drug-in-condition queries
    )
    procedure_data: Optional[ProcedureFetchResult] = None
    evidence_data: Optional[EvidenceFetchResult] = None
    comparative_evidence: Optional[EvidenceFetchResult] = None
    comparative_drug_data: list = field(default_factory=list)
    drug_interactions: list = field(default_factory=list)  # RxNorm DDI pairs for 2-drug queries
    total_fetch_time_ms: int = 0
    fallback_to_llm: bool = False


# Local Indian drug repositories were intentionally removed.
# Drug-brand resolution must happen against live online sources.


# ------------------------------------------------------------------
# HTTP helpers
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Persistent HTTP client — shared across all requests for connection reuse
# ------------------------------------------------------------------

_HTTP_CLIENT: httpx.AsyncClient | None = None


async def init_http_client() -> None:
    """Initialize the shared HTTP client at application startup."""
    global _HTTP_CLIENT
    _HTTP_CLIENT = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=3.0),
        follow_redirects=True,
        limits=httpx.Limits(
            max_connections=30,
            max_keepalive_connections=15,
            keepalive_expiry=60,
        ),
    )


async def shutdown_http_client() -> None:
    """Close the shared HTTP client at application shutdown."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is not None:
        await _HTTP_CLIENT.aclose()
        _HTTP_CLIENT = None


def _get_client() -> httpx.AsyncClient:
    """Return the shared HTTP client. Falls back to creating a temporary client if not initialized."""
    if _HTTP_CLIENT is not None:
        return _HTTP_CLIENT
    # Fallback for tests or early startup — create a one-off client
    return httpx.AsyncClient(
        timeout=settings.api_fetch_timeout_seconds,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


@contextlib.asynccontextmanager
async def _make_client():  # type: ignore[return]
    """Async context manager for HTTP client access.

    When the persistent client is initialized (production), yields it WITHOUT closing on exit.
    Falls back to creating a temporary client (tests / early startup) that IS closed on exit.
    """
    if _HTTP_CLIENT is not None:
        yield _HTTP_CLIENT
    else:
        async with httpx.AsyncClient(
            timeout=settings.api_fetch_timeout_seconds,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        ) as client:
            yield client


async def _safe_get(
    client: httpx.AsyncClient,
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
) -> dict | None:
    """GET → JSON. Returns None on any failure."""
    try:
        resp = await client.get(url, params=params, headers=headers)
        if resp.status_code == 200:
            return resp.json()
    except httpx.TimeoutException:
        logger.debug("API timeout: %s", url)
    except httpx.HTTPStatusError as e:
        logger.debug("API HTTP %s: %s", e.response.status_code, url)
    except Exception:
        logger.debug("API fetch failed: %s", url, exc_info=True)
    return None


async def _safe_get_text(
    client: httpx.AsyncClient, url: str, params: dict | None = None
) -> str | None:
    """GET → plain text. Returns None on any failure."""
    try:
        resp = await client.get(url, params=params)
        if resp.status_code == 200:
            return resp.text
    except httpx.TimeoutException:
        logger.debug("API timeout (text): %s", url)
    except httpx.HTTPStatusError as e:
        logger.debug("API HTTP %s (text): %s", e.response.status_code, url)
    except Exception:
        logger.debug("API text fetch failed: %s", url, exc_info=True)
    return None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _first(lst: list | None) -> Optional[str]:
    if lst and isinstance(lst, list) and lst:
        return str(lst[0])
    return None


def _truncate(text: Optional[str], max_chars: int) -> Optional[str]:
    if not text:
        return None
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def _cap_abstracts(abstracts: list, max_total_chars: int = 3000) -> list:
    """Keep as many abstracts as fit within the total character budget (newest first)."""
    sorted_abs = sorted(abstracts, key=lambda x: x.get("year") or 0, reverse=True)
    result, total = [], 0
    for a in sorted_abs:
        text = a.get("abstract", "") or ""
        if total + len(text) > max_total_chars:
            break
        result.append(a)
        total += len(text)
    return result


# ------------------------------------------------------------------
# OpenFDA drug label
# ------------------------------------------------------------------


async def _fetch_fda_label(client: httpx.AsyncClient, drug_name: str) -> dict | None:
    base_url = "https://api.fda.gov/drug/label.json"
    extra = {"api_key": settings.openfda_api_key} if settings.openfda_api_key else {}
    name_lower = drug_name.lower().strip()

    def _best_result(data: dict | None) -> dict | None:
        """Return a synthetic single-result dict preferring exact single-ingredient matches."""
        if not data or not data.get("results"):
            return None
        results = data["results"]
        ranked: list[tuple[int, dict]] = []
        for r in results:
            names = [n.lower().strip() for n in r.get("openfda", {}).get("generic_name", [])]
            brands = [n.lower().strip() for n in r.get("openfda", {}).get("brand_name", [])]
            score = 0
            for n in names:
                if n == name_lower:
                    score = max(score, 100)
                elif any(part.strip() == name_lower for part in re.split(r"\s*(?:/|,| and )\s*", n)):
                    score = max(score, 85)
                elif n.startswith(name_lower + " "):
                    score = max(score, 70)
            if any(b == name_lower for b in brands):
                score = max(score, 90)
            ingredient_penalty = 0
            if names:
                min_parts = min(
                    len([part for part in re.split(r"\s*(?:/|,| and )\s*", n) if part.strip()])
                    for n in names
                )
                ingredient_penalty = max(0, min_parts - 1) * 10
            ranked.append((score - ingredient_penalty, r))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if ranked and ranked[0][0] > 0:
            return {"results": [ranked[0][1]]}
        return {"results": [results[0]]}

    # Try generic name search first (fetch 3 to find best match)
    data = await _safe_get(
        client,
        base_url,
        params={
            "search": f'openfda.generic_name:"{drug_name}"',
            "limit": 10,
            **extra,
        },
    )
    best = _best_result(data)
    if best:
        return best

    # Fallback: brand name
    data = await _safe_get(
        client,
        base_url,
        params={
            "search": f'openfda.brand_name:"{drug_name}"',
            "limit": 1,
            **extra,
        },
    )
    if data and data.get("results"):
        return data

    # Fallback: free text
    data = await _safe_get(
        client,
        base_url,
        params={
            "search": f'"{drug_name}"',
            "limit": 1,
            **extra,
        },
    )
    return data


def _merge_fda_label(result: DrugFetchResult, data: dict | None) -> None:
    if not data or not data.get("results"):
        return
    r = data["results"][0]
    openfda = r.get("openfda", {})

    result.generic_name = _first(openfda.get("generic_name")) or result.generic_name
    result.brand_name = _first(openfda.get("brand_name")) or result.brand_name
    result.drug_class = _first(openfda.get("pharm_class_epc")) or result.drug_class

    result.mechanism_raw = _truncate(_first(r.get("mechanism_of_action")), 400)
    result.indications_raw = _truncate(_first(r.get("indications_and_usage")), 800)
    result.dosing_raw = _truncate(_first(r.get("dosage_and_administration")), 800)
    result.contraindications_raw = _truncate(_first(r.get("contraindications")), 600)

    warnings = (
        r.get("warnings_and_cautions") or r.get("warnings") or r.get("boxed_warning")
    )
    result.warnings_raw = _truncate(_first(warnings), 500)

    result.adverse_reactions_raw = _truncate(_first(r.get("adverse_reactions")), 600)
    result.drug_interactions_raw = _truncate(_first(r.get("drug_interactions")), 600)

    # Pharmacokinetics is often inside clinical_pharmacology
    clin_pharm = r.get("clinical_pharmacology")
    result.pharmacokinetics_raw = _truncate(_first(clin_pharm), 400)
    if not result.mechanism_raw:
        result.mechanism_raw = _truncate(_first(clin_pharm), 400)

    result.special_populations_raw = _truncate(
        _first(r.get("use_in_specific_populations")), 400
    )

    effective_time = r.get("effective_time", "")
    if effective_time and len(str(effective_time)) >= 4:
        try:
            result.fda_label_source_year = int(str(effective_time)[:4])
        except (ValueError, TypeError):
            pass

    result.data_source = "fda"
    result.fetch_success = bool(result.indications_raw or result.dosing_raw)


# ------------------------------------------------------------------
# OpenFDA adverse events (FAERS)
# ------------------------------------------------------------------


async def _fetch_fda_events(client: httpx.AsyncClient, drug_name: str) -> list:
    extra = {"api_key": settings.openfda_api_key} if settings.openfda_api_key else {}
    data = await _safe_get(
        client,
        "https://api.fda.gov/drug/event.json",
        params={
            "search": f'patient.drug.medicinalproduct:"{drug_name}"',
            "count": "patient.reaction.reactionmeddrapt.exact",
            "limit": 10,
            **extra,
        },
    )
    if not data or not data.get("results"):
        return []
    return [item["term"].title() for item in data["results"][:8]]


# ------------------------------------------------------------------
# RxNorm
# ------------------------------------------------------------------


async def _fetch_rxnorm_cui(client: httpx.AsyncClient, drug_name: str) -> Optional[str]:
    data = await _safe_get(
        client,
        "https://rxnav.nlm.nih.gov/REST/rxcui.json",
        params={
            "name": drug_name,
            "search": 1,
        },
    )
    if not data:
        return None
    ids = data.get("idGroup", {}).get("rxnormId", [])
    return ids[0] if ids else None


async def _fetch_rxnorm_class(client: httpx.AsyncClient, rxcui: str) -> Optional[str]:
    data = await _safe_get(
        client,
        "https://rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json",
        params={
            "rxcui": rxcui,
            "relaSource": "ATC",
        },
    )
    if not data:
        return None
    concepts = data.get("rxclassMinConceptList", {}).get("rxclassMinConcept", [])
    return concepts[0].get("className") if concepts else None


async def _fetch_rxnorm_class_chain(
    client: httpx.AsyncClient, drug_name: str
) -> Optional[str]:
    """Chain CUI lookup → class lookup in a single coroutine for parallel execution.

    Replaces the sequential post-Phase-1 RxNorm class call with one that can run
    alongside FDA/PubMed calls in the Phase 1 gather.
    """
    rxcui = await _fetch_rxnorm_cui(client, drug_name)
    if not rxcui:
        return None
    return await _fetch_rxnorm_class(client, rxcui)


async def _fetch_rxnorm_approximate_rxcui(
    client: httpx.AsyncClient, drug_name: str
) -> Optional[str]:
    data = await _safe_get(
        client,
        "https://rxnav.nlm.nih.gov/REST/approximateTerm.json",
        params={
            "term": drug_name,
            "maxEntries": 1,
        },
    )
    candidates = data.get("approximateGroup", {}).get("candidate", []) if data else []
    if not candidates:
        return None
    return candidates[0].get("rxcui")


async def _fetch_rxnorm_name(client: httpx.AsyncClient, rxcui: str) -> Optional[str]:
    data = await _safe_get(
        client,
        f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json",
    )
    props = data.get("properties") if data else None
    if not props:
        return None
    return props.get("name")


async def _fetch_rxnorm_ingredient(client: httpx.AsyncClient, rxcui: str) -> Optional[str]:
    """Resolve a brand RxCUI to its ingredient (salt) RxCUI.

    Uses /related.json?tty=IN — returns the active ingredient rxcui for brand names.
    Example: Lipitor rxcui → atorvastatin rxcui.
    """
    data = await _safe_get(
        client,
        f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/related.json",
        params={"tty": "IN"},
    )
    if not data:
        return None
    concept_group = data.get("relatedGroup", {}).get("conceptGroup", [])
    for group in concept_group:
        if group.get("tty") == "IN":
            props = group.get("conceptProperties", [])
            if props:
                return props[0].get("rxcui")
    return None


async def _resolve_drug_name_online(client: httpx.AsyncClient, drug_name: str) -> dict:
    """Resolve a brand or misspelled drug name to its generic (salt) name.

    Resolution order:
    1. RxNorm exact match → follow /related?tty=IN to get ingredient rxcui
    2. RxNorm approximate match → same ingredient lookup
    3. OpenFDA brand search → extract openfda.generic_name directly
    4. Fallback to original name
    """
    exact_rxcui, approx_rxcui = await asyncio.gather(
        _fetch_rxnorm_cui(client, drug_name),
        _fetch_rxnorm_approximate_rxcui(client, drug_name),
        return_exceptions=True,
    )
    exact_rxcui = exact_rxcui if not isinstance(exact_rxcui, Exception) else None
    approx_rxcui = approx_rxcui if not isinstance(approx_rxcui, Exception) else None
    rxcui = exact_rxcui or approx_rxcui

    # Try to resolve to ingredient (salt) rxcui — this converts brand → generic
    ingredient_rxcui = None
    if rxcui:
        ingredient_rxcui = await _fetch_rxnorm_ingredient(client, rxcui)

    final_rxcui = ingredient_rxcui or rxcui
    resolved_name = await _fetch_rxnorm_name(client, final_rxcui) if final_rxcui else None

    # Fallback: OpenFDA brand search → extract generic_name directly
    if not resolved_name or resolved_name.lower() == drug_name.lower():
        fda_data = await _safe_get(
            client,
            "https://api.fda.gov/drug/label.json",
            params={
                "search": f'openfda.brand_name:"{drug_name}"',
                "limit": 1,
                **({"api_key": settings.openfda_api_key} if settings.openfda_api_key else {}),
            },
        )
        if fda_data and fda_data.get("results"):
            generic = _first(
                fda_data["results"][0].get("openfda", {}).get("generic_name")
            )
            if generic and generic.lower() != drug_name.lower():
                resolved_name = generic

    if resolved_name and resolved_name.lower() != drug_name.lower():
        return {
            "query_name": drug_name,
            "resolved_name": resolved_name,
            "rxcui": final_rxcui,
            "confidence": 0.95 if exact_rxcui else 0.75,
        }
    return {
        "query_name": drug_name,
        "resolved_name": drug_name,
        "rxcui": rxcui,
        "confidence": 0.0,
    }


# ------------------------------------------------------------------
# PubMed Entrez (guidelines + systematic reviews)
# ------------------------------------------------------------------


async def _fetch_pubmed_abstracts(
    client: httpx.AsyncClient, entity: str, pub_type: str = "guideline"
) -> list:
    """Fetch PubMed guideline or systematic review abstracts for an entity.

    Searches the broad PubMed corpus first. Journal registry is used only to boost
    priority sources, never to restrict the evidence base.
    """
    if pub_type == "guideline":
        pt_filter = "(Practice Guideline[pt] OR Guideline[pt])"
        retmax = 16
        broad_fallback = (
            f"{entity}[Title/Abstract] AND (guideline OR consensus OR recommendation) "
            "AND 2010:2026[dp]"
        )
    else:
        pt_filter = "(Systematic Review[pt] OR Meta-Analysis[pt])"
        retmax = 12
        broad_fallback = (
            f"{entity}[Title/Abstract] AND (systematic review OR meta-analysis OR review) "
            "AND 2010:2026[dp]"
        )

    term = f"{entity}[Title/Abstract] AND {pt_filter} AND 2010:2026[dp]"
    journal_filter = _get_journal_filter(entity)
    journal_term = (
        f"{entity}[Title/Abstract] AND {journal_filter} AND 2010:2026[dp]"
        if journal_filter
        else None
    )
    search_tasks = [
        _pubmed_esearch(client, term, retmax),
        _pubmed_esearch(client, broad_fallback, max(retmax // 2, 6)),
    ]
    if journal_term:
        search_tasks.append(_pubmed_esearch(client, journal_term, 6))

    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    all_ids: list[str] = []
    seen_ids: set[str] = set()
    for result in search_results:
        if isinstance(result, Exception) or not result:
            continue
        for pid in result:
            if pid not in seen_ids:
                seen_ids.add(pid)
                all_ids.append(pid)

    if not all_ids:
        return []

    return await _pubmed_efetch(client, all_ids)


async def _pubmed_esearch(
    client: httpx.AsyncClient, term: str, retmax: int
) -> list[str]:
    """PubMed esearch → list of PMID strings with exponential-backoff retry."""
    params: dict = {
        "db": "pubmed",
        "term": term,
        "retmax": retmax,
        "retmode": "json",
        "sort": "relevance",
    }
    if settings.pubmed_api_key:
        params["api_key"] = settings.pubmed_api_key

    for attempt in range(3):
        search_data = await _safe_get(
            client,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params=params,
        )
        if search_data:
            return search_data.get("esearchresult", {}).get("idlist", [])
        if attempt < 2:
            await asyncio.sleep(2 ** attempt)  # 1s, 2s
    logger.warning("PubMed esearch failed after 3 attempts: %s", term[:80])
    return []


async def _pubmed_efetch(client: httpx.AsyncClient, ids: list[str]) -> list:
    """PubMed efetch → parsed abstract list."""
    if not ids:
        return []
    fetch_params: dict = {
        "db": "pubmed",
        "id": ",".join(ids),
        "rettype": "abstract",
        "retmode": "xml",
    }
    if settings.pubmed_api_key:
        fetch_params["api_key"] = settings.pubmed_api_key

    xml_text = await _safe_get_text(
        client,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
        params=fetch_params,
    )
    if not xml_text:
        return []
    return _parse_pubmed_xml(xml_text)


async def _fetch_pubmed_classification(client: httpx.AsyncClient, entity: str) -> list:
    """Fetch PubMed abstracts for classification/staging systems (e.g. WHO groups, NYHA)."""
    term = f"{entity} classification[Title/Abstract] AND 2010:2026[dp]"
    ids = await _pubmed_esearch(client, term, 4)
    return await _pubmed_efetch(client, ids)


def _parse_pubmed_xml(xml_text: str) -> list:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.debug("PubMed XML parse error")
        return []

    results = []
    for article in root.findall(".//PubmedArticle"):
        try:
            pmid_el = article.find(".//PMID")
            pmid = pmid_el.text if pmid_el is not None else None

            title_el = article.find(".//ArticleTitle")
            title = "".join(title_el.itertext()) if title_el is not None else ""

            # Structured abstracts have multiple AbstractText elements
            abstract_parts = article.findall(".//AbstractText")
            abstract = " ".join("".join(p.itertext()) for p in abstract_parts).strip()

            year = None
            for year_xpath in (
                ".//ArticleDate/Year",
                ".//PubDate/Year",
                ".//PubDate/MedlineDate",
            ):
                year_el = article.find(year_xpath)
                if year_el is not None and year_el.text:
                    try:
                        year = int(year_el.text[:4])
                        break
                    except (ValueError, TypeError):
                        pass

            collective_el = article.find(".//CollectiveName")
            collective = collective_el.text if collective_el is not None else None

            journal_el = article.find(".//Journal/Title")
            journal = journal_el.text if journal_el is not None else None

            if title:
                results.append(
                    {
                        "pmid": pmid,
                        "title": title,
                        "abstract": abstract[:650],
                        "year": year,
                        "collective_name": collective,
                        "journal": journal,
                    }
                )
        except Exception:
            continue

    return results


# ------------------------------------------------------------------
# NICE API (optional — skipped if no key)
# ------------------------------------------------------------------


async def _fetch_nice(client: httpx.AsyncClient, entity: str) -> list:
    if not settings.nice_api_key:
        return []

    headers = {"apikey": settings.nice_api_key}
    search_data = await _safe_get(
        client,
        "https://api.nice.org.uk/v1/search",
        params={"q": entity, "type": "guidance", "size": 3},
        headers=headers,
    )
    if not search_data:
        return []

    items = search_data.get("items") or search_data.get("results") or []
    recommendations = []

    for item in items[:2]:
        item_id = item.get("id") or item.get("guidanceId")
        if not item_id:
            continue
        rec_data = await _safe_get(
            client,
            f"https://api.nice.org.uk/v1/guidance/{item_id}/recommendations",
            headers=headers,
        )
        if not rec_data:
            continue
        for r in (rec_data.get("recommendations") or [])[:5]:
            text = r.get("text") or r.get("recommendationText") or ""
            if text:
                pub_date = item.get("publicationDate") or ""
                recommendations.append(
                    {
                        "title": item.get("title", ""),
                        "text": text[:400],
                        "year": pub_date[:4] if pub_date else None,
                    }
                )

    return recommendations


# ------------------------------------------------------------------
# MedlinePlus Connect
# ------------------------------------------------------------------


async def _fetch_medlineplus(client: httpx.AsyncClient, entity: str) -> Optional[str]:
    data = await _safe_get(
        client,
        "https://connect.medlineplus.gov/service",
        params={
            "mainSearchCriteria.v.dn": entity,
            "knowledgeResponseType": "application/json",
        },
    )
    if not data:
        return None
    try:
        entries = data.get("feed", {}).get("entry", [])
        if entries:
            summary = entries[0].get("summary", {})
            if isinstance(summary, dict):
                return (summary.get("$") or "")[:500]
            if isinstance(summary, str):
                return summary[:500]
    except Exception:
        pass
    return None


# ------------------------------------------------------------------
# Semantic Scholar (open-access papers)
# ------------------------------------------------------------------


async def _fetch_semantic_scholar(client: httpx.AsyncClient, entity: str) -> list:
    data = await _safe_get(
        client,
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={
            "query": f"{entity} clinical guideline",
            "fields": "title,abstract,year,openAccessPdf,publicationTypes",
            "limit": 5,
        },
    )
    if not data:
        return []

    papers = []
    for p in data.get("data", []):
        if p.get("openAccessPdf") and p.get("abstract"):
            papers.append(
                {
                    "title": p.get("title", ""),
                    "abstract": (p.get("abstract") or "")[:400],
                    "year": p.get("year"),
                }
            )
    return papers[:3]


# ------------------------------------------------------------------
# DailyMed (fallback for drugs not in OpenFDA)
# ------------------------------------------------------------------


async def _fetch_dailymed(
    client: httpx.AsyncClient, drug_name: str
) -> Optional[DrugFetchResult]:
    search = await _safe_get(
        client,
        "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json",
        params={"drug_name": drug_name, "pagesize": 1},
    )
    if not search or not search.get("data"):
        return None

    setid = search["data"][0].get("setid")
    if not setid:
        return None

    spl = await _safe_get(
        client,
        f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{setid}.json",
    )
    if not spl:
        return None

    result = DrugFetchResult(generic_name=drug_name, data_source="dailymed")

    # DailyMed SPL sections are keyed by LOINC code
    SECTION_MAP = {
        "34067-9": "indications_raw",
        "34068-7": "dosing_raw",
        "34070-3": "contraindications_raw",
        "34071-1": "warnings_raw",
        "34084-4": "adverse_reactions_raw",
        "34073-7": "drug_interactions_raw",
        "43679-0": "mechanism_raw",
        "34090-1": "pharmacokinetics_raw",
        "43684-0": "special_populations_raw",
    }
    MAX_CHARS = {
        "indications_raw": 800,
        "dosing_raw": 800,
        "contraindications_raw": 600,
        "warnings_raw": 500,
        "adverse_reactions_raw": 600,
        "drug_interactions_raw": 600,
        "mechanism_raw": 400,
        "pharmacokinetics_raw": 400,
        "special_populations_raw": 400,
    }

    for section in (spl.get("data") or {}).get("sections") or []:
        code = section.get("code", "")
        field_name = SECTION_MAP.get(code)
        if field_name and section.get("text"):
            setattr(
                result,
                field_name,
                _truncate(section["text"], MAX_CHARS.get(field_name, 500)),
            )

    result.fetch_success = bool(result.indications_raw or result.dosing_raw)
    return result


# ------------------------------------------------------------------
# MedIndia HTML fallback
# ------------------------------------------------------------------


def _build_medindia_url(drug_name: str) -> str:
    """Build a safe MedIndia URL with proper percent-encoding."""
    return f"https://www.medindia.net/drugs/drug_info.asp?drug_name={quote_plus(drug_name)}"


async def _fetch_medindia(
    client: httpx.AsyncClient, drug_name: str
) -> Optional[DrugFetchResult]:
    url = _build_medindia_url(drug_name)
    text = await _safe_get_text(client, url)
    if not text:
        return None

    result = DrugFetchResult(generic_name=drug_name, data_source="medindia")

    # Extract drug class
    class_match = re.search(
        r"(?:Drug Class|Pharmacological Class)[^>]*>.*?([A-Za-z][^<]{10,100})",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if class_match:
        result.drug_class = class_match.group(1).strip()[:100]

    # Extract uses/indications
    uses_match = re.search(
        r"(?:Uses|Indications).*?<p[^>]*>\s*([^<]{50,600})",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if uses_match:
        result.indications_raw = uses_match.group(1).strip()[:600]

    # Extract side effects
    se_match = re.search(
        r"(?:Side Effect|Adverse).*?<[pu][^>]*>\s*([^<]{30,500})",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if se_match:
        result.adverse_reactions_raw = se_match.group(1).strip()[:400]

    result.fetch_success = bool(result.indications_raw or result.drug_class)
    return result


# ------------------------------------------------------------------
# PMC / StatPearls
# ------------------------------------------------------------------


async def _fetch_pmc_statpearls(client: httpx.AsyncClient, entity: str) -> Optional[str]:
    """Fetch StatPearls content from PMC for detailed clinical pharmacology."""
    # Search PMC for StatPearls articles about this entity
    search_data = await _safe_get(
        client,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={
            "db": "pmc",
            "term": f"{entity}[Title] AND StatPearls[journal]",
            "retmax": 3,
            "retmode": "json",
            **({"api_key": settings.pubmed_api_key} if settings.pubmed_api_key else {}),
        },
    )
    if not search_data:
        return None
    ids = search_data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        # Fallback: broader search
        search_data = await _safe_get(
            client,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={
                "db": "pmc",
                "term": f"{entity} dosing pharmacology[Title/Abstract] AND StatPearls[journal]",
                "retmax": 2,
                "retmode": "json",
                **({"api_key": settings.pubmed_api_key} if settings.pubmed_api_key else {}),
            },
        )
        if search_data:
            ids = search_data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return None
    # Fetch abstract/summary from PMC
    fetch_data = await _safe_get_text(
        client,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
        params={
            "db": "pmc",
            "id": ",".join(ids[:2]),
            "rettype": "abstract",
            "retmode": "text",
            **({"api_key": settings.pubmed_api_key} if settings.pubmed_api_key else {}),
        },
    )
    if fetch_data:
        return fetch_data[:1200]
    return None


# ------------------------------------------------------------------
# ChEMBL — additional drug pharmacology source
# ------------------------------------------------------------------


async def _fetch_chembl(client: httpx.AsyncClient, drug_name: str) -> Optional[dict]:
    """Fetch drug mechanism, drug class, and targets from ChEMBL. Redis-cached for 7 days."""
    # Check Redis cache first
    try:
        import redis.asyncio as aioredis
        _r = aioredis.from_url(settings.redis_url, decode_responses=True)
        cache_key = f"chembl:{drug_name.lower().strip()}"
        cached = await _r.get(cache_key)
        await _r.aclose()
        if cached is not None:
            return json.loads(cached) if cached != "null" else None
    except Exception:
        _r = None

    result = await _fetch_chembl_remote(client, drug_name)

    # Store in Redis (7 days TTL — ChEMBL data rarely changes)
    try:
        _r2 = aioredis.from_url(settings.redis_url, decode_responses=True)
        await _r2.setex(cache_key, 604800, json.dumps(result))
        await _r2.aclose()
    except Exception:
        pass

    return result


async def _fetch_chembl_remote(client: httpx.AsyncClient, drug_name: str) -> Optional[dict]:
    """Internal: actually fetch from ChEMBL API."""
    search = await _safe_get(
        client,
        "https://www.ebi.ac.uk/chembl/api/data/molecule.json",
        params={"pref_name__iexact": drug_name, "format": "json", "limit": 1},
    )
    if not search or not search.get("molecules"):
        # Fallback: case-insensitive contains search
        search = await _safe_get(
            client,
            "https://www.ebi.ac.uk/chembl/api/data/molecule.json",
            params={"pref_name__icontains": drug_name, "format": "json", "limit": 1},
        )
    if not search or not search.get("molecules"):
        return None

    mol = search["molecules"][0]
    chembl_id = mol.get("molecule_chembl_id")
    if not chembl_id:
        return None

    # Fetch mechanism of action
    mech_data = await _safe_get(
        client,
        f"https://www.ebi.ac.uk/chembl/api/data/mechanism.json",
        params={"molecule_chembl_id": chembl_id, "format": "json", "limit": 5},
    )
    mechanisms = []
    if mech_data and mech_data.get("mechanisms"):
        for m in mech_data["mechanisms"][:3]:
            mech_str = m.get("mechanism_of_action") or ""
            target = m.get("target_chembl_id") or ""
            if mech_str:
                mechanisms.append(mech_str)

    drug_class = None
    if mol.get("molecule_properties"):
        # ChEMBL stores therapeutic flags
        pass
    atc = mol.get("atc_classifications", [])
    if atc:
        drug_class = atc[0]  # ATC code

    if not mechanisms and not drug_class:
        return None

    return {
        "chembl_id": chembl_id,
        "mechanism": "; ".join(mechanisms[:2]) if mechanisms else None,
        "atc_class": drug_class,
    }


# ------------------------------------------------------------------
# RxNorm Drug-Drug Interaction API
# ------------------------------------------------------------------


async def _fetch_rxnorm_interactions(
    client: httpx.AsyncClient, rxcui1: str, rxcui2: str
) -> list[dict]:
    """Fetch drug-drug interactions between two drugs using RxNav interaction API.

    Returns a list of interaction dicts with severity, description, drugs involved.
    Endpoint: rxnav.nlm.nih.gov/REST/interaction/list.json?rxcuis=rxcui1+rxcui2
    """
    data = await _safe_get(
        client,
        "https://rxnav.nlm.nih.gov/REST/interaction/list.json",
        params={"rxcuis": f"{rxcui1} {rxcui2}"},
    )
    if not data:
        return []

    interactions = []
    full_interaction_type_group = data.get("fullInteractionTypeGroup", [])
    for group in full_interaction_type_group:
        source = group.get("sourceName", "RxNorm")
        for fit in group.get("fullInteractionType", []):
            for pair in fit.get("interactionPair", []):
                severity = pair.get("severity", "").lower()
                description = pair.get("description", "")
                drugs = [
                    c.get("minConceptItem", {}).get("name", "")
                    for c in pair.get("interactionConcept", [])
                    if c.get("minConceptItem")
                ]
                if description:
                    interactions.append({
                        "severity": severity or "moderate",
                        "description": description[:500],
                        "drugs": [d for d in drugs if d],
                        "source": source,
                    })
    return interactions[:10]


# ------------------------------------------------------------------
# High-level fetch orchestrators
# ------------------------------------------------------------------


async def fetch_drug_data(drug_name: str) -> DrugFetchResult:
    """Fetch drug data using live online resolution rather than local repositories."""
    result = DrugFetchResult()

    async with _make_client() as client:
        resolution = await _resolve_drug_name_online(client, drug_name)
        search_name = resolution.get("resolved_name") or drug_name
        result.generic_name = search_name
        if search_name.lower() != drug_name.lower():
            result.brand_name = drug_name
        if resolution.get("rxcui"):
            result.rxcui = resolution["rxcui"]

        (
            fda_label,
            fda_events,
            rxnorm_class,
            guidelines,
            sysreviews,
            dailymed_result,
            medlineplus_drug,
            statpearls_text,
            chembl_data,
        ) = await asyncio.gather(
            _fetch_fda_label(client, search_name),
            _fetch_fda_events(client, search_name),
            _fetch_rxnorm_class_chain(client, search_name),
            _fetch_pubmed_abstracts(client, search_name, "guideline"),
            _fetch_pubmed_abstracts(client, search_name, "systematic_review"),
            _fetch_dailymed(client, search_name),
            _fetch_medlineplus(client, search_name),
            _fetch_pmc_statpearls(client, search_name),
            _fetch_chembl(client, search_name),
            return_exceptions=True,
        )

        _merge_fda_label(
            result, fda_label if not isinstance(fda_label, Exception) else None
        )
        result.top_adverse_events = fda_events if isinstance(fda_events, list) else []
        result.guideline_abstracts = _cap_abstracts(
            guidelines if isinstance(guidelines, list) else [], 3000
        )
        result.systematic_review_abstracts = _cap_abstracts(
            sysreviews if isinstance(sysreviews, list) else [], 3000
        )
        # Apply RxNorm class from chain result (no sequential round-trip needed)
        if (
            isinstance(rxnorm_class, str)
            and rxnorm_class
            and not result.drug_class_rxnorm
        ):
            result.drug_class_rxnorm = rxnorm_class

        if isinstance(medlineplus_drug, str) and medlineplus_drug:
            if result.indications_raw:
                result.indications_raw = result.indications_raw + f"\n[MedlinePlus]: {medlineplus_drug[:300]}"
            else:
                result.indications_raw = medlineplus_drug[:400]

        if isinstance(statpearls_text, str) and statpearls_text:
            if result.dosing_raw:
                result.dosing_raw = result.dosing_raw + f"\n[StatPearls]: {statpearls_text[:400]}"
            else:
                result.dosing_raw = statpearls_text[:600]

        # ChEMBL: enrich mechanism and drug class
        if isinstance(chembl_data, dict) and chembl_data:
            if chembl_data.get("mechanism") and not result.mechanism_raw:
                result.mechanism_raw = f"[ChEMBL]: {chembl_data['mechanism']}"
            elif chembl_data.get("mechanism"):
                result.mechanism_raw += f"\n[ChEMBL]: {chembl_data['mechanism']}"
            if chembl_data.get("atc_class") and not result.drug_class:
                result.drug_class = chembl_data["atc_class"]
            result.chembl_mechanism = chembl_data.get("mechanism")
            result.chembl_atc_class = chembl_data.get("atc_class")

        # OpenFDA→RxNorm fallback (item 20): if no indications, try DailyMed before giving up
        if not result.indications_raw and not result.dosing_raw:
            logger.info(
                "OpenFDA returned no label for '%s' — trying DailyMed fallback", search_name
            )

        if result.fetch_success:
            return result

        dm = dailymed_result if not isinstance(dailymed_result, Exception) else None
        if dm and dm.fetch_success:
            if search_name.lower() != drug_name.lower():
                dm.brand_name = drug_name
                dm.generic_name = search_name
            dm.rxcui = result.rxcui
            dm.guideline_abstracts = result.guideline_abstracts
            dm.systematic_review_abstracts = result.systematic_review_abstracts
            dm.top_adverse_events = result.top_adverse_events
            return dm

        mi = await _fetch_medindia(client, drug_name)
        if (not mi or not mi.fetch_success) and search_name.lower() != drug_name.lower():
            mi = await _fetch_medindia(client, search_name)
        if mi and mi.fetch_success:
            if search_name.lower() != drug_name.lower():
                mi.brand_name = drug_name
                mi.generic_name = search_name
            mi.rxcui = result.rxcui
            mi.guideline_abstracts = result.guideline_abstracts
            mi.systematic_review_abstracts = result.systematic_review_abstracts
            mi.top_adverse_events = result.top_adverse_events
            return mi

    return result


async def fetch_disease_data(disease_name: str) -> DiseaseFetchResult:
    """Fetch disease data from PubMed (guidelines + reviews + classification), NICE,
    MedlinePlus, and Semantic Scholar — all in parallel.

    Speed optimization: runs all PubMed esearch + non-PubMed sources in parallel
    (Phase 1), then batches all PMIDs into a single efetch call (Phase 2).
    This cuts 3 sequential efetch calls down to 1.
    """
    result = DiseaseFetchResult()

    journal_filter = _get_journal_filter(disease_name)

    # Build PubMed search terms
    guideline_term = f"{disease_name}[Title/Abstract] AND (Practice Guideline[pt] OR Guideline[pt]) AND 2010:2026[dp]"
    review_term = f"{disease_name}[Title/Abstract] AND (Systematic Review[pt] OR Meta-Analysis[pt]) AND 2010:2026[dp]"
    classification_term = (
        f"{disease_name} classification[Title/Abstract] AND 2010:2026[dp]"
    )
    broad_guideline_term = (
        f"{disease_name}[Title/Abstract] AND (guideline OR consensus OR recommendation) AND 2010:2026[dp]"
    )
    broad_review_term = (
        f"{disease_name}[Title/Abstract] AND (systematic review OR meta-analysis OR review) AND 2010:2026[dp]"
    )
    journal_term = (
        f"{disease_name}[Title/Abstract] AND {journal_filter} AND 2010:2026[dp]"
        if journal_filter
        else None
    )

    async with _make_client() as client:
        # Phase 1: ALL esearch calls + non-PubMed sources in parallel
        tasks: list = [
            _pubmed_esearch(client, guideline_term, 16),
            _pubmed_esearch(client, review_term, 12),
            _pubmed_esearch(client, classification_term, 6),
            _pubmed_esearch(client, broad_guideline_term, 8),
            _pubmed_esearch(client, broad_review_term, 8),
            _fetch_nice(client, disease_name),
            _fetch_medlineplus(client, disease_name),
            _fetch_semantic_scholar(client, disease_name),
        ]
        if journal_term:
            tasks.append(_pubmed_esearch(client, journal_term, 4))

        # Use asyncio.wait so partial results are recovered if some calls time out
        task_objs = [asyncio.ensure_future(coro) for coro in tasks]
        done, pending = await asyncio.wait(
            task_objs, timeout=settings.api_fetch_timeout_seconds
        )
        for t in pending:
            t.cancel()
        results = []
        for t in task_objs:
            if t.done() and not t.cancelled():
                try:
                    results.append(t.result())
                except Exception as e:
                    results.append(e)
            else:
                results.append(None)

        guideline_ids = results[0] if isinstance(results[0], list) else []
        review_ids = results[1] if isinstance(results[1], list) else []
        classification_ids = results[2] if isinstance(results[2], list) else []
        broad_guideline_ids = results[3] if isinstance(results[3], list) else []
        broad_review_ids = results[4] if isinstance(results[4], list) else []
        nice_recs = results[5] if isinstance(results[5], list) else []
        medlineplus = results[6] if isinstance(results[6], str) else None
        semantic = results[7] if isinstance(results[7], list) else []
        journal_ids = (
            results[8] if len(results) > 8 and isinstance(results[8], list) else []
        )

        all_guideline_ids = (
            guideline_ids + broad_guideline_ids + classification_ids + journal_ids
        )
        # Deduplicate while keeping order
        seen: set[str] = set()
        unique_guideline_ids = [
            pid for pid in all_guideline_ids if pid not in seen and not seen.add(pid)
        ]

        all_review_ids = review_ids + broad_review_ids
        all_ids = list(set(unique_guideline_ids + all_review_ids))
        all_abstracts = await _pubmed_efetch(client, all_ids) if all_ids else []

        # Tag abstracts by which search found them (by PMID membership)
        guideline_set = set(unique_guideline_ids)
        review_set = set(all_review_ids)
        guideline_abstracts = []
        review_abstracts = []
        for a in all_abstracts:
            pmid = a.get("pmid")
            if pmid in guideline_set:
                guideline_abstracts.append(a)
            if pmid in review_set:
                review_abstracts.append(a)

        result.guideline_abstracts = _cap_abstracts(guideline_abstracts, 12000)
        result.systematic_review_abstracts = _cap_abstracts(review_abstracts, 7000)
        result.nice_recommendations = nice_recs
        result.medlineplus_summary = medlineplus
        result.semantic_papers = semantic

    result.fetch_success = bool(
        result.guideline_abstracts
        or result.systematic_review_abstracts
        or result.medlineplus_summary
    )

    # Fallback: if no PubMed results, retry without [pt] filter
    if not result.guideline_abstracts and not result.systematic_review_abstracts:
        fallback_term = f"{disease_name}[Title/Abstract] AND (guideline OR consensus OR recommendation) AND 2015:2026[dp]"
        async with _make_client() as client:
            fallback_ids = await _pubmed_esearch(client, fallback_term, 8)
            if fallback_ids:
                fallback_abstracts = await _pubmed_efetch(client, fallback_ids)
                result.guideline_abstracts = _cap_abstracts(fallback_abstracts, 8000)
                result.fetch_success = bool(result.guideline_abstracts)

    return result


async def fetch_procedure_data(procedure_name: str) -> ProcedureFetchResult:
    """Fetch procedure/guideline data from PubMed practice guidelines."""
    result = ProcedureFetchResult()

    async with _make_client() as client:
        guidelines, practice, reviews, statpearls = await asyncio.gather(
            _fetch_pubmed_abstracts(client, procedure_name, "guideline"),
            _fetch_pubmed_procedure_guidelines(client, procedure_name),
            _fetch_pubmed_abstracts(client, procedure_name, "systematic_review"),
            _fetch_pmc_statpearls(client, procedure_name),
            return_exceptions=True,
        )

        result.guideline_abstracts = _cap_abstracts(
            (guidelines if isinstance(guidelines, list) else []) +
            (practice if isinstance(practice, list) else []) +
            (reviews if isinstance(reviews, list) else []),
            6000
        )
        result.practice_guideline_abstracts = []  # merged above
        if isinstance(statpearls, str) and statpearls:
            # Add StatPearls as a synthetic abstract entry
            result.guideline_abstracts.insert(0, {
                "pmid": "",
                "title": f"StatPearls: {procedure_name}",
                "abstract": statpearls[:600],
                "year": 2024,
                "journal": "StatPearls",
            })

    result.fetch_success = bool(
        result.guideline_abstracts or result.practice_guideline_abstracts
    )
    return result


async def _fetch_pubmed_procedure_guidelines(
    client: httpx.AsyncClient, entity: str
) -> list:
    """Fetch PubMed practice guidelines specifically for procedures."""
    term = (
        f"{entity}[Title/Abstract] AND "
        "(Practice Guideline[pt] OR Consensus Development Conference[pt]) "
        "AND 2015:2025[dp]"
    )
    ids = await _pubmed_esearch(client, term, 5)
    return await _pubmed_efetch(client, ids)


async def fetch_evidence_data(query: str) -> EvidenceFetchResult:
    """Fetch evidence for drug+condition questions (clinical trials + reviews).

    Speed optimization: parallel esearch → single batch efetch.
    """
    result = EvidenceFetchResult()

    trial_term = (
        f"{query}[Title/Abstract] AND "
        "(Clinical Trial[pt] OR Randomized Controlled Trial[pt]) "
        "AND 2010:2026[dp]"
    )
    review_term = f"{query}[Title/Abstract] AND (Systematic Review[pt] OR Meta-Analysis[pt]) AND 2010:2026[dp]"
    guideline_term = f"{query}[Title/Abstract] AND (Practice Guideline[pt] OR Guideline[pt]) AND 2010:2026[dp]"
    broad_evidence_term = (
        f"{query}[Title/Abstract] AND (guideline OR review OR trial OR consensus OR recommendation) AND 2010:2026[dp]"
    )

    async with _make_client() as client:
        # Phase 1: all esearch in parallel
        trial_ids, review_ids, guideline_ids, broad_ids = await asyncio.gather(
            _pubmed_esearch(client, trial_term, 12),
            _pubmed_esearch(client, review_term, 8),
            _pubmed_esearch(client, guideline_term, 10),
            _pubmed_esearch(client, broad_evidence_term, 12),
            return_exceptions=True,
        )
        trial_ids = trial_ids if isinstance(trial_ids, list) else []
        review_ids = review_ids if isinstance(review_ids, list) else []
        guideline_ids = guideline_ids if isinstance(guideline_ids, list) else []
        broad_ids = broad_ids if isinstance(broad_ids, list) else []

        # Phase 2: single batch efetch
        all_ids = list(set(trial_ids + review_ids + guideline_ids + broad_ids))
        all_abstracts = await _pubmed_efetch(client, all_ids) if all_ids else []

        trial_set = set(trial_ids)
        review_set = set(review_ids)
        guideline_set = set(guideline_ids)
        broad_set = set(broad_ids)
        for a in all_abstracts:
            pmid = a.get("pmid")
            if pmid in trial_set:
                result.clinical_trial_abstracts.append(a)
            if pmid in review_set:
                result.systematic_review_abstracts.append(a)
            if pmid in guideline_set:
                result.guideline_abstracts.append(a)
            elif pmid in broad_set:
                result.guideline_abstracts.append(a)

        result.clinical_trial_abstracts = _cap_abstracts(
            result.clinical_trial_abstracts, 6000
        )
        result.systematic_review_abstracts = _cap_abstracts(
            result.systematic_review_abstracts, 5000
        )
        result.guideline_abstracts = _cap_abstracts(result.guideline_abstracts, 4000)

    result.fetch_success = bool(
        result.clinical_trial_abstracts
        or result.systematic_review_abstracts
        or result.guideline_abstracts
    )
    return result


async def _fetch_pubmed_clinical_trials(client: httpx.AsyncClient, query: str) -> list:
    """Fetch clinical trial and RCT abstracts from PubMed."""
    term = (
        f"{query}[Title/Abstract] AND "
        "(Clinical Trial[pt] OR Randomized Controlled Trial[pt]) "
        "AND 2010:2026[dp]"
    )
    ids = await _pubmed_esearch(client, term, 8)
    return await _pubmed_efetch(client, ids)


def _fire_and_forget_index(abstracts: list) -> None:
    """Schedule fire-and-forget indexing of PubMed abstracts into pgvector."""
    if not abstracts or not settings.vector_search_enabled:
        return
    try:
        from app.services.ingestion import ingest_pubmed_abstracts

        asyncio.create_task(ingest_pubmed_abstracts(abstracts))
    except Exception:
        logger.debug("Fire-and-forget indexing skipped", exc_info=True)


async def fetch_data_for_query(
    query_type: str, entities: list, condition_context: Optional[str] = None
) -> FetchedData:
    """Top-level orchestrator called by the pipeline.

    Args:
        query_type: Classified query type (drug, disease, comparative, procedure, evidence).
        entities: Extracted entity names (drug names, disease names, etc.).
        condition_context: For drug-in-condition queries, the condition name to fetch
            management guidelines for in parallel (e.g., "atrial fibrillation" for "digoxin in AF").
    """
    start = time.time()
    fetched = FetchedData(query_type=query_type)

    try:
        if query_type == "drug" and entities:
            if condition_context:
                # Fetch drug data AND condition management guidelines in parallel (B6)
                drug_result, condition_result, evidence_result = await asyncio.gather(
                    fetch_drug_data(entities[0]),
                    fetch_disease_data(condition_context),
                    fetch_evidence_data(f"{entities[0]} {condition_context}"),
                    return_exceptions=True,
                )
                fetched.drug_data = (
                    drug_result
                    if not isinstance(drug_result, Exception)
                    else DrugFetchResult()
                )
                fetched.condition_data = (
                    condition_result
                    if not isinstance(condition_result, Exception)
                    else None
                )
                if (
                    fetched.drug_data
                    and isinstance(evidence_result, EvidenceFetchResult)
                    and evidence_result.fetch_success
                ):
                    fetched.drug_data.clinical_trial_abstracts = _cap_abstracts(
                        evidence_result.clinical_trial_abstracts, 5000
                    )
                    fetched.drug_data.systematic_review_abstracts = _cap_abstracts(
                        (fetched.drug_data.systematic_review_abstracts or [])
                        + evidence_result.systematic_review_abstracts,
                        5000,
                    )
                    fetched.drug_data.guideline_abstracts = _cap_abstracts(
                        (fetched.drug_data.guideline_abstracts or [])
                        + evidence_result.guideline_abstracts,
                        5000,
                    )
                fetched.fallback_to_llm = not fetched.drug_data.fetch_success
                _fire_and_forget_index(fetched.drug_data.guideline_abstracts)
                _fire_and_forget_index(fetched.drug_data.clinical_trial_abstracts)
                if fetched.condition_data:
                    _fire_and_forget_index(fetched.condition_data.guideline_abstracts)
            else:
                fetched.drug_data = await fetch_drug_data(entities[0])
                fetched.fallback_to_llm = not fetched.drug_data.fetch_success
                _fire_and_forget_index(fetched.drug_data.guideline_abstracts)
                _fire_and_forget_index(fetched.drug_data.clinical_trial_abstracts)

        elif query_type == "disease" and entities:
            fetched.disease_data = await fetch_disease_data(entities[0])
            fetched.fallback_to_llm = not fetched.disease_data.fetch_success
            _fire_and_forget_index(fetched.disease_data.guideline_abstracts)
            _fire_and_forget_index(fetched.disease_data.systematic_review_abstracts)

        elif query_type == "comparative" and len(entities) >= 2:
            drug_results = await asyncio.gather(
                fetch_drug_data(entities[0]),
                fetch_drug_data(entities[1]),
                fetch_evidence_data(" vs ".join(entities[:2])),
                return_exceptions=True,
            )
            for r in drug_results[:2]:
                if not isinstance(r, Exception):
                    fetched.comparative_drug_data.append(r)
            comp_evidence = drug_results[2]
            if isinstance(comp_evidence, EvidenceFetchResult) and comp_evidence.fetch_success:
                fetched.comparative_evidence = comp_evidence
                _fire_and_forget_index(comp_evidence.clinical_trial_abstracts)
                _fire_and_forget_index(comp_evidence.systematic_review_abstracts)

            # Fetch drug-drug interaction data when both drugs have rxcui
            rxcui1 = fetched.comparative_drug_data[0].rxcui if len(fetched.comparative_drug_data) > 0 else None
            rxcui2 = fetched.comparative_drug_data[1].rxcui if len(fetched.comparative_drug_data) > 1 else None
            if rxcui1 and rxcui2:
                async with _make_client() as client:
                    ddi = await _fetch_rxnorm_interactions(client, rxcui1, rxcui2)
                    if ddi:
                        fetched.drug_interactions = ddi

            fetched.fallback_to_llm = not any(
                r.fetch_success for r in fetched.comparative_drug_data
            ) and not (
                fetched.comparative_evidence and fetched.comparative_evidence.fetch_success
            )

        elif query_type == "procedure" and entities:
            fetched.procedure_data = await fetch_procedure_data(entities[0])
            fetched.fallback_to_llm = not fetched.procedure_data.fetch_success
            _fire_and_forget_index(fetched.procedure_data.guideline_abstracts)

        elif query_type == "evidence" and entities:
            fetched.evidence_data = await fetch_evidence_data(" ".join(entities))
            fetched.fallback_to_llm = not fetched.evidence_data.fetch_success
            _fire_and_forget_index(fetched.evidence_data.clinical_trial_abstracts)

        else:
            fetched.fallback_to_llm = True

    except Exception:
        logger.error("Data fetch orchestration failed", exc_info=True)
        fetched.fallback_to_llm = True

    fetched.total_fetch_time_ms = int((time.time() - start) * 1000)
    return fetched
