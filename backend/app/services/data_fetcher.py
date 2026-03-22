"""
data_fetcher.py — Parallel API fetching from free medical databases.

Fetches authoritative raw data (FDA labels, PubMed guidelines, MedlinePlus, etc.)
so the LLM only needs to FORMAT, not generate knowledge from scratch.
All API calls are async, fire-and-forget, and silent on failure.
"""

import asyncio
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

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
    guideline_abstracts: list = field(default_factory=list)
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
class FetchedData:
    query_type: str
    drug_data: Optional[DrugFetchResult] = None
    disease_data: Optional[DiseaseFetchResult] = None
    comparative_drug_data: list = field(default_factory=list)
    total_fetch_time_ms: int = 0
    fallback_to_llm: bool = False


# ------------------------------------------------------------------
# Indian drugs local database
# ------------------------------------------------------------------

_INDIAN_DRUGS: dict = {}


def _load_indian_drugs() -> None:
    global _INDIAN_DRUGS
    try:
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "indian_drugs.json"
        )
        path = os.path.normpath(path)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                drugs = json.load(f)
            for d in drugs:
                key = d.get("generic_name", "").lower().strip()
                if key:
                    _INDIAN_DRUGS[key] = d
                for bn in d.get("brand_names_india", []):
                    _INDIAN_DRUGS[bn.lower().strip()] = d
    except Exception:
        logger.warning("Failed to load indian_drugs.json", exc_info=True)


_load_indian_drugs()


# ------------------------------------------------------------------
# HTTP helpers
# ------------------------------------------------------------------


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings.api_fetch_timeout_seconds,
        follow_redirects=True,
    )


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
        """Return a synthetic single-result dict preferring exact generic_name matches."""
        if not data or not data.get("results"):
            return None
        results = data["results"]
        # Prefer result whose generic_name is exactly (or starts with) the query drug
        for r in results:
            names = [n.lower() for n in r.get("openfda", {}).get("generic_name", [])]
            if any(n == name_lower or n.startswith(name_lower + " ") for n in names):
                return {"results": [r]}
        # Fall back to first result
        return {"results": [results[0]]}

    # Try generic name search first (fetch 3 to find best match)
    data = await _safe_get(
        client,
        base_url,
        params={
            "search": f'openfda.generic_name:"{drug_name}"',
            "limit": 3,
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


# ------------------------------------------------------------------
# PubMed Entrez (guidelines + systematic reviews)
# ------------------------------------------------------------------


async def _fetch_pubmed_abstracts(
    client: httpx.AsyncClient, entity: str, pub_type: str = "guideline"
) -> list:
    """Fetch PubMed guideline or systematic review abstracts for an entity."""
    if pub_type == "guideline":
        pt_filter = "(Practice Guideline[pt] OR Guideline[pt])"
        retmax = 5  # 3 for drugs (caller caps), 5 for diseases
    else:
        pt_filter = "(Systematic Review[pt] OR Meta-Analysis[pt])"
        retmax = 4

    term = f"{entity}[Title/Abstract] AND {pt_filter} AND 2018:2025[dp]"
    params: dict = {
        "db": "pubmed",
        "term": term,
        "retmax": retmax,
        "retmode": "json",
        "sort": "relevance",
    }
    if settings.pubmed_api_key:
        params["api_key"] = settings.pubmed_api_key

    search_data = await _safe_get(
        client,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params=params,
    )
    if not search_data:
        return []

    ids = search_data.get("esearchresult", {}).get("idlist", [])
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
    term = f"{entity} classification[Title/Abstract] AND 2010:2025[dp]"
    params: dict = {
        "db": "pubmed",
        "term": term,
        "retmax": 4,
        "retmode": "json",
        "sort": "relevance",
    }
    if settings.pubmed_api_key:
        params["api_key"] = settings.pubmed_api_key

    search_data = await _safe_get(
        client,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params=params,
    )
    if not search_data:
        return []

    ids = search_data.get("esearchresult", {}).get("idlist", [])
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

            if title and abstract:
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
# Indian drugs local lookup
# ------------------------------------------------------------------


def _check_indian_drugs(drug_name: str) -> Optional[dict]:
    key = drug_name.lower().strip()
    return _INDIAN_DRUGS.get(key)


def _merge_indian_drug(result: DrugFetchResult, entry: dict) -> None:
    result.generic_name = entry.get("generic_name", result.generic_name)
    result.drug_class = entry.get("drug_class", result.drug_class)
    result.indications_raw = _truncate(entry.get("indications"), 800)
    result.dosing_raw = _truncate(entry.get("dosing_india"), 800)
    result.contraindications_raw = _truncate(entry.get("contraindications"), 600)
    result.warnings_raw = _truncate(entry.get("warnings"), 500)
    result.adverse_reactions_raw = _truncate(entry.get("adverse_reactions"), 600)
    result.pharmacokinetics_raw = _truncate(entry.get("pharmacokinetics"), 400)
    result.data_source = "indian_local"
    result.fetch_success = bool(result.indications_raw)


# ------------------------------------------------------------------
# MedIndia HTML fallback
# ------------------------------------------------------------------


async def _fetch_medindia(
    client: httpx.AsyncClient, drug_name: str
) -> Optional[DrugFetchResult]:
    url = f"https://www.medindia.net/drugs/drug_info.asp?drug_name={drug_name.replace(' ', '+')}"
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
# High-level fetch orchestrators
# ------------------------------------------------------------------


async def fetch_drug_data(drug_name: str) -> DrugFetchResult:
    """Fetch drug data: OpenFDA (primary) → DailyMed → Indian local → MedIndia."""
    result = DrugFetchResult()

    async with _make_client() as client:
        # Phase 1: all parallel primary sources
        fda_label, fda_events, rxcui_raw, guidelines = await asyncio.gather(
            _fetch_fda_label(client, drug_name),
            _fetch_fda_events(client, drug_name),
            _fetch_rxnorm_cui(client, drug_name),
            _fetch_pubmed_abstracts(client, drug_name, "guideline"),
            return_exceptions=True,
        )

        _merge_fda_label(
            result, fda_label if not isinstance(fda_label, Exception) else None
        )
        result.top_adverse_events = fda_events if isinstance(fda_events, list) else []
        result.guideline_abstracts = _cap_abstracts(
            guidelines if isinstance(guidelines, list) else [], 1500
        )

        rxcui = rxcui_raw if isinstance(rxcui_raw, str) else None
        if rxcui:
            result.rxcui = rxcui
            drug_class = await _fetch_rxnorm_class(client, rxcui)
            if drug_class and not result.drug_class_rxnorm:
                result.drug_class_rxnorm = drug_class

        if result.fetch_success:
            return result

        # Phase 2: DailyMed fallback
        dm = await _fetch_dailymed(client, drug_name)
        if dm and dm.fetch_success:
            dm.guideline_abstracts = result.guideline_abstracts
            dm.top_adverse_events = result.top_adverse_events
            return dm

        # Phase 3: Indian drugs local lookup
        indian = _check_indian_drugs(drug_name)
        if indian:
            _merge_indian_drug(result, indian)
            if result.fetch_success:
                return result

        # Phase 4: MedIndia HTML fallback
        mi = await _fetch_medindia(client, drug_name)
        if mi and mi.fetch_success:
            mi.guideline_abstracts = result.guideline_abstracts
            mi.top_adverse_events = result.top_adverse_events
            return mi

    return result


async def fetch_disease_data(disease_name: str) -> DiseaseFetchResult:
    """Fetch disease data from PubMed (guidelines + reviews + classification), NICE,
    MedlinePlus, and Semantic Scholar — all in parallel."""
    result = DiseaseFetchResult()

    async with _make_client() as client:
        (
            guidelines,
            sysreviews,
            classification,
            nice_recs,
            medlineplus,
            semantic,
        ) = await asyncio.gather(
            _fetch_pubmed_abstracts(client, disease_name, "guideline"),
            _fetch_pubmed_abstracts(client, disease_name, "systematic_review"),
            _fetch_pubmed_classification(client, disease_name),
            _fetch_nice(client, disease_name),
            _fetch_medlineplus(client, disease_name),
            _fetch_semantic_scholar(client, disease_name),
            return_exceptions=True,
        )

        # Merge classification abstracts into guidelines — they describe staging systems
        all_guidelines = (guidelines if isinstance(guidelines, list) else []) + (
            classification if isinstance(classification, list) else []
        )
        result.guideline_abstracts = _cap_abstracts(all_guidelines, 5000)
        result.systematic_review_abstracts = _cap_abstracts(
            sysreviews if isinstance(sysreviews, list) else [], 3000
        )
        result.nice_recommendations = nice_recs if isinstance(nice_recs, list) else []
        result.medlineplus_summary = (
            medlineplus if isinstance(medlineplus, str) else None
        )
        result.semantic_papers = semantic if isinstance(semantic, list) else []

    result.fetch_success = bool(
        result.guideline_abstracts
        or result.systematic_review_abstracts
        or result.medlineplus_summary
    )
    return result


async def fetch_data_for_query(query_type: str, entities: list) -> FetchedData:
    """Top-level orchestrator called by the pipeline."""
    start = time.time()
    fetched = FetchedData(query_type=query_type)

    try:
        if query_type == "drug" and entities:
            fetched.drug_data = await fetch_drug_data(entities[0])
            fetched.fallback_to_llm = not fetched.drug_data.fetch_success

        elif query_type == "disease" and entities:
            fetched.disease_data = await fetch_disease_data(entities[0])
            fetched.fallback_to_llm = not fetched.disease_data.fetch_success

        elif query_type == "comparative" and len(entities) >= 2:
            drug_results = await asyncio.gather(
                fetch_drug_data(entities[0]),
                fetch_drug_data(entities[1]),
                return_exceptions=True,
            )
            for r in drug_results:
                if not isinstance(r, Exception):
                    fetched.comparative_drug_data.append(r)
            fetched.fallback_to_llm = not any(
                r.fetch_success for r in fetched.comparative_drug_data
            )

        else:
            fetched.fallback_to_llm = True

    except Exception:
        logger.error("Data fetch orchestration failed", exc_info=True)
        fetched.fallback_to_llm = True

    fetched.total_fetch_time_ms = int((time.time() - start) * 1000)
    return fetched
