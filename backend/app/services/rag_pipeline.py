import asyncio
import json
import logging
import re
import time

import anthropic
import openai
import orjson
import pybreaker
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.config import settings
from app.db.session import async_session
from app.models.query_log import QueryLog
from app.schemas.query import (
    AdaptiveBLUF,
    AdaptiveReference,
    AdaptiveResponse,
    AdaptiveSection,
    ComparativeResponse,
    DegradedResponse,
    DiseaseResponse,
    DrugResponse,
    EvidenceResponse,
    GeneralResponse,
    ModelCost,
    ProcedureResponse,
    QueryRequest,
    QueryResponse,
    TokenUsage,
)
from app.services.cache import cache_get, cache_get_any_version, cache_set
from app.services.circuit_breaker import get_breaker, is_provider_available
from app.services.citation_validator import validate_citations
from app.services.data_fetcher import (
    DiseaseFetchResult,
    EvidenceFetchResult,
    FetchedData,
    ProcedureFetchResult,
    fetch_data_for_query,
    fetch_disease_data,
    fetch_evidence_data,
    fetch_procedure_data,
)
from app.services.scraping_response import _build_scraping_response
from app.services.semantic_cache import (
    is_stale,
    semantic_cache_get,
    semantic_cache_revalidate,
    semantic_cache_set,
)
from app.services.drug_linker import process_text_nodes
from app.services.json_repair import parse_llm_json
from app.services.llm_factory import create_llm, get_provider
from app.services.prompt_engine import build_adaptive_messages
from app.services.query_classifier import classify_query, classify_query_llm, detect_intent
from app.services.safety_checker import check_safety
from app.services.url_builder import enrich_references
from app.services.source_router import route_query
from app.services.vector_search import search as vector_search

# PMID/DOI hyperlinking patterns


logger = logging.getLogger(__name__)
_INSUFFICIENT_DATA_RE = re.compile(
    r"\binsufficient data\b|\bno data available\b|\bnot available from available sources\b",
    re.IGNORECASE,
)


def _summarize_fetched(
    fetched_data: "FetchedData",
    *,
    query_type: str | None = None,
    condition_context: str | None = None,
) -> str:
    """Summarize fetched API data for DSPy input with enough depth for adaptive output."""
    parts = []
    if fetched_data.condition_data:
        dd = fetched_data.condition_data
        if dd.medlineplus_summary:
            parts.append(
                f"[SOURCE: MedlinePlus][condition_summary]: {dd.medlineplus_summary[:900]}"
            )
        for rec in (dd.nice_recommendations or [])[:5]:
            text = str(rec.get("text", "") or "")[:420]
            if text:
                parts.append(f"[SOURCE: NICE][condition_recommendation]: {text}")
        for ab in (dd.guideline_abstracts or [])[:6]:
            title = ab.get("title", "")
            content = ab.get("full_text") or ab.get("abstract", "")
            content = content[:1500] if ab.get("full_text") else content[:500]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            if title or content:
                parts.append(
                    f"[SOURCE: PubMed{_pmid_str}][condition_guideline]: {title} — {content}"
                )
        for ab in (dd.systematic_review_abstracts or [])[:4]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:500]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            if title or abstract:
                parts.append(
                    f"[SOURCE: PubMed{_pmid_str}][condition_review]: {title} — {abstract}"
                )
    if fetched_data.drug_data:
        d = fetched_data.drug_data
        raw_fields = [
            ("drug", d.generic_name or ""),
            ("indications", d.indications_raw or ""),
            ("dosing", d.dosing_raw or ""),
            ("contraindications", d.contraindications_raw or ""),
            ("warnings", d.warnings_raw or ""),
            ("adverse_reactions", d.adverse_reactions_raw or ""),
            ("special_populations", d.special_populations_raw or ""),
            ("mechanism", d.mechanism_raw or ""),
            ("pharmacokinetics", d.pharmacokinetics_raw or ""),
            ("interactions", d.drug_interactions_raw or ""),
        ]
        _drug_source = d.data_source or "FDA label"
        for label, val in raw_fields:
            if val:
                parts.append(f"[SOURCE: {_drug_source}][{label}]: {val[:900]}")
        for ab in (d.guideline_abstracts or [])[:6]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:500]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            if title or abstract:
                parts.append(
                    f"[SOURCE: PubMed{_pmid_str}][drug_guideline]: {title} — {abstract}"
                )
        for ab in (d.systematic_review_abstracts or [])[:5]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:500]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            if title or abstract:
                parts.append(
                    f"[SOURCE: PubMed{_pmid_str}][drug_systematic_review]: {title} — {abstract}"
                )
        for ab in (d.clinical_trial_abstracts or [])[:5]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:500]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            if title or abstract:
                parts.append(
                    f"[SOURCE: PubMed{_pmid_str}][drug_clinical_trial]: {title} — {abstract}"
                )
    if fetched_data.disease_data:
        dd = fetched_data.disease_data
        if dd.medlineplus_summary:
            parts.append(
                f"[SOURCE: MedlinePlus][medlineplus]: {dd.medlineplus_summary[:1000]}"
            )
        for rec in (dd.nice_recommendations or [])[:4]:
            text = str(rec.get("text", "") or "")[:350]
            if text:
                parts.append(f"[SOURCE: NICE][recommendation]: {text}")
        for paper in (dd.semantic_papers or [])[:4]:
            title = str(paper.get("title", "") or "")
            abstract = str(paper.get("abstract", "") or "")[:350]
            if title or abstract:
                parts.append(
                    f"[SOURCE: Semantic Scholar][paper]: {title} — {abstract}"
                )
        for ab in (dd.guideline_abstracts or [])[:8]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:500]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            if title or abstract:
                parts.append(
                    f"[SOURCE: PubMed{_pmid_str}][guideline]: {title} — {abstract}"
                )
        for ab in (dd.systematic_review_abstracts or [])[:6]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:500]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            if title or abstract:
                parts.append(
                    f"[SOURCE: PubMed{_pmid_str}][systematic_review]: {title} — {abstract}"
                )
    if fetched_data.procedure_data:
        pd = fetched_data.procedure_data
        for ab in (pd.guideline_abstracts or [])[:6]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:450]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            if title or abstract:
                parts.append(
                    f"[SOURCE: PubMed{_pmid_str}][procedure_guideline]: {title} — {abstract}"
                )
    if fetched_data.comparative_drug_data:
        for idx, d in enumerate(fetched_data.comparative_drug_data[:2], start=1):
            source_name = d.data_source or f"comparison_drug_{idx}"
            name = d.generic_name or d.brand_name or f"drug_{idx}"
            parts.append(f"[SOURCE: {source_name}][comparison_drug]: {name}")
            for label, val in [
                ("indications", d.indications_raw or ""),
                ("dosing", d.dosing_raw or ""),
                ("contraindications", d.contraindications_raw or ""),
                ("adverse_reactions", d.adverse_reactions_raw or ""),
                ("interactions", d.drug_interactions_raw or ""),
            ]:
                if val:
                    parts.append(
                        f"[SOURCE: {source_name}][{name}:{label}]: {val[:750]}"
                    )
    if fetched_data.comparative_evidence:
        ce = fetched_data.comparative_evidence
        for ab in (ce.guideline_abstracts or [])[:4]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:450]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            parts.append(
                f"[SOURCE: PubMed{_pmid_str}][comparison_guideline]: {title} — {abstract}"
            )
        for ab in (ce.systematic_review_abstracts or [])[:4]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:450]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            parts.append(
                f"[SOURCE: PubMed{_pmid_str}][comparison_review]: {title} — {abstract}"
            )
        for ab in (ce.clinical_trial_abstracts or [])[:4]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:450]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            parts.append(
                f"[SOURCE: PubMed{_pmid_str}][comparison_trial]: {title} — {abstract}"
            )
    if fetched_data.evidence_data:
        ed = fetched_data.evidence_data
        for ab in (ed.systematic_review_abstracts or [])[:4]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:450]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            if title or abstract:
                parts.append(
                    f"[SOURCE: PubMed{_pmid_str}][systematic_review]: {title} — {abstract}"
                )
        for ab in (ed.clinical_trial_abstracts or [])[:5]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:450]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            if title or abstract:
                parts.append(
                    f"[SOURCE: PubMed{_pmid_str}][clinical_trial]: {title} — {abstract}"
                )
        for ab in (ed.guideline_abstracts or [])[:4]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:450]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            if title or abstract:
                parts.append(
                    f"[SOURCE: PubMed{_pmid_str}][guideline]: {title} — {abstract}"
                )
    max_chars = 32000 if query_type in {"drug", "disease", "comparative"} else 26000
    return "\n".join(parts)[:max_chars] if parts else ""


def _summarize_vectors(vector_results: list) -> str:
    """Summarize vector search results for DSPy input."""
    if not vector_results:
        return ""
    return "\n".join(str(r)[:300] for r in vector_results[:5])


def _describe_data(fetched_data: "FetchedData") -> str:
    """Describe what data sources were fetched."""
    sources = []
    if fetched_data.drug_data:
        sources.append(fetched_data.drug_data.data_source or "FDA label")
    if fetched_data.disease_data and fetched_data.disease_data.guideline_abstracts:
        sources.append("PubMed guidelines")
    if fetched_data.condition_data and fetched_data.condition_data.guideline_abstracts:
        sources.append("Condition guidelines")
    if fetched_data.procedure_data and fetched_data.procedure_data.guideline_abstracts:
        sources.append("Procedure guidelines")
    if fetched_data.evidence_data and (
        fetched_data.evidence_data.clinical_trial_abstracts
        or fetched_data.evidence_data.systematic_review_abstracts
    ):
        sources.append("Evidence studies")
    if fetched_data.comparative_evidence and (
        fetched_data.comparative_evidence.clinical_trial_abstracts
        or fetched_data.comparative_evidence.systematic_review_abstracts
    ):
        sources.append("Comparative evidence")
    return ", ".join(sources) if sources else "none"


def _merge_abstracts(existing: list, incoming: list, *, max_total_chars: int) -> list:
    merged: list[dict] = []
    seen: set[str] = set()
    for item in (existing or []) + (incoming or []):
        if not isinstance(item, dict):
            continue
        key = str(item.get("pmid") or item.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    merged.sort(key=lambda x: x.get("year") or 0, reverse=True)
    kept: list[dict] = []
    total = 0
    for item in merged:
        abstract = str(item.get("abstract") or "")
        if kept and total + len(abstract) > max_total_chars:
            break
        kept.append(item)
        total += len(abstract)
    return kept


def _merge_text(existing: str | None, incoming: str | None, *, max_chars: int) -> str | None:
    if incoming and not existing:
        return incoming[:max_chars]
    if not incoming or not existing:
        return existing[:max_chars] if existing else None
    if incoming.strip() in existing:
        return existing[:max_chars]
    if existing.strip() in incoming:
        return incoming[:max_chars]
    return f"{existing}\n\n{incoming}"[:max_chars]


def _enrich_disease_result(base: DiseaseFetchResult | None, extra: DiseaseFetchResult | None) -> DiseaseFetchResult | None:
    if extra is None:
        return base
    if base is None:
        return extra
    base.guideline_abstracts = _merge_abstracts(
        base.guideline_abstracts,
        extra.guideline_abstracts,
        max_total_chars=16000,
    )
    base.systematic_review_abstracts = _merge_abstracts(
        base.systematic_review_abstracts,
        extra.systematic_review_abstracts,
        max_total_chars=12000,
    )
    base.nice_recommendations = list(base.nice_recommendations or []) + [
        rec for rec in (extra.nice_recommendations or []) if rec not in (base.nice_recommendations or [])
    ]
    base.semantic_papers = list(base.semantic_papers or []) + [
        paper for paper in (extra.semantic_papers or []) if paper not in (base.semantic_papers or [])
    ]
    base.medlineplus_summary = _merge_text(
        base.medlineplus_summary,
        extra.medlineplus_summary,
        max_chars=1500,
    )
    base.fetch_success = bool(
        base.guideline_abstracts or base.systematic_review_abstracts or base.medlineplus_summary
    )
    return base


def _enrich_evidence_result(base: EvidenceFetchResult | None, extra: EvidenceFetchResult | None) -> EvidenceFetchResult | None:
    if extra is None:
        return base
    if base is None:
        return extra
    base.clinical_trial_abstracts = _merge_abstracts(
        base.clinical_trial_abstracts,
        extra.clinical_trial_abstracts,
        max_total_chars=9000,
    )
    base.systematic_review_abstracts = _merge_abstracts(
        base.systematic_review_abstracts,
        extra.systematic_review_abstracts,
        max_total_chars=8000,
    )
    base.guideline_abstracts = _merge_abstracts(
        base.guideline_abstracts,
        extra.guideline_abstracts,
        max_total_chars=8000,
    )
    base.fetch_success = bool(
        base.clinical_trial_abstracts or base.systematic_review_abstracts or base.guideline_abstracts
    )
    return base


def _enrich_procedure_result(base: ProcedureFetchResult | None, extra: ProcedureFetchResult | None) -> ProcedureFetchResult | None:
    if extra is None:
        return base
    if base is None:
        return extra
    base.guideline_abstracts = _merge_abstracts(
        base.guideline_abstracts,
        extra.guideline_abstracts,
        max_total_chars=12000,
    )
    base.practice_guideline_abstracts = _merge_abstracts(
        base.practice_guideline_abstracts,
        extra.practice_guideline_abstracts,
        max_total_chars=6000,
    )
    base.fetch_success = bool(base.guideline_abstracts or base.practice_guideline_abstracts)
    return base


def _retrieval_assessment(
    fetched_data: FetchedData | None, query_type: str
) -> tuple[int, bool, list[str]]:
    if not fetched_data:
        return 0, False, ["no data fetched"]

    reasons: list[str] = []
    score = 0

    if query_type == "drug":
        if not fetched_data.drug_data:
            return 0, False, ["data fetch timed out — no drug data retrieved"]
        d = fetched_data.drug_data
        core_fields = sum(
            1 for value in [
                d.indications_raw,
                d.dosing_raw,
                d.contraindications_raw,
                d.adverse_reactions_raw,
                d.drug_interactions_raw,
                d.mechanism_raw,
                d.special_populations_raw,
            ] if value
        )
        evidence_hits = len(d.guideline_abstracts or []) + len(d.systematic_review_abstracts or []) + len(d.clinical_trial_abstracts or [])
        score = core_fields * 2 + min(evidence_hits, 6)
        if core_fields < 3:
            reasons.append("too few populated drug fields")
        if evidence_hits < 2 and not fetched_data.condition_data:
            reasons.append("limited drug evidence")
        return score, score >= 8, reasons

    if query_type == "disease":
        if not fetched_data.disease_data:
            return 0, False, ["data fetch timed out — no disease data retrieved"]
        d = fetched_data.disease_data
        guideline_hits = len(d.guideline_abstracts or [])
        review_hits = len(d.systematic_review_abstracts or [])
        score = guideline_hits * 2 + review_hits * 2
        if d.medlineplus_summary:
            score += 1
        if d.nice_recommendations:
            score += 2
        if guideline_hits + review_hits < 3:
            reasons.append("too few disease abstracts")
        return score, score >= 8, reasons

    if query_type == "procedure":
        if not fetched_data.procedure_data:
            return 0, False, ["data fetch timed out — no procedure data retrieved"]
        d = fetched_data.procedure_data
        hits = len(d.guideline_abstracts or []) + len(d.practice_guideline_abstracts or [])
        score = hits * 2
        if hits < 2:
            reasons.append("too few procedure guidelines")
        return score, score >= 4, reasons

    if query_type == "evidence":
        if not fetched_data.evidence_data:
            return 0, False, ["data fetch timed out — no evidence data retrieved"]
        d = fetched_data.evidence_data
        trials = len(d.clinical_trial_abstracts or [])
        reviews = len(d.systematic_review_abstracts or [])
        guidelines = len(d.guideline_abstracts or [])
        score = trials * 2 + reviews * 2 + guidelines
        if trials + reviews + guidelines < 3:
            reasons.append("too few evidence studies")
        return score, score >= 7, reasons

    if query_type == "comparative":
        drug_hits = 0
        for d in fetched_data.comparative_drug_data or []:
            if d.fetch_success:
                drug_hits += sum(1 for value in [d.indications_raw, d.dosing_raw, d.contraindications_raw, d.adverse_reactions_raw] if value)
        evidence = fetched_data.comparative_evidence
        evidence_hits = 0
        if evidence:
            evidence_hits = len(evidence.clinical_trial_abstracts or []) + len(evidence.systematic_review_abstracts or []) + len(evidence.guideline_abstracts or [])
        score = drug_hits + min(evidence_hits * 2, 8)
        if len(fetched_data.comparative_drug_data or []) < 2:
            reasons.append("comparison entities not fully resolved")
        if evidence_hits < 2:
            reasons.append("limited comparative evidence")
        return score, score >= 8, reasons

    if query_type in {"drug", "disease", "procedure", "evidence", "comparative"}:
        return 0, False, ["data fetch timed out — no retrieval data available"]
    return 0, False, ["unsupported query type"]


async def _expand_retrieval_if_needed(
    *,
    query: str,
    query_type: str,
    fetched_data: FetchedData | None,
    entities: list[str],
    condition_context: str | None,
    response_focus: str | None,
) -> tuple[FetchedData | None, list[str]]:
    if not settings.adaptive_second_pass_enabled or not fetched_data:
        return fetched_data, []

    score, sufficient, reasons = _retrieval_assessment(fetched_data, query_type)
    if sufficient:
        return fetched_data, []

    notes = [f"initial retrieval score={score}", *reasons]
    follow_up_terms: list[str] = []
    for term in [response_focus, query]:
        value = re.sub(r"\s+", " ", str(term or "")).strip()
        if value and value.lower() not in {t.lower() for t in follow_up_terms}:
            follow_up_terms.append(value)

    try:
        if query_type == "disease" and follow_up_terms:
            extras = await asyncio.gather(
                *(fetch_disease_data(term) for term in follow_up_terms[:2]),
                return_exceptions=True,
            )
            for extra in extras:
                if isinstance(extra, DiseaseFetchResult) and extra.fetch_success:
                    fetched_data.disease_data = _enrich_disease_result(
                        fetched_data.disease_data, extra
                    )
        elif query_type == "procedure" and follow_up_terms:
            extras = await asyncio.gather(
                *(fetch_procedure_data(term) for term in follow_up_terms[:2]),
                return_exceptions=True,
            )
            for extra in extras:
                if isinstance(extra, ProcedureFetchResult) and extra.fetch_success:
                    fetched_data.procedure_data = _enrich_procedure_result(
                        fetched_data.procedure_data, extra
                    )
        elif query_type == "evidence":
            extras = await asyncio.gather(
                fetch_evidence_data(query),
                *(fetch_evidence_data(term) for term in follow_up_terms[:1]),
                return_exceptions=True,
            )
            for extra in extras:
                if isinstance(extra, EvidenceFetchResult) and extra.fetch_success:
                    fetched_data.evidence_data = _enrich_evidence_result(
                        fetched_data.evidence_data, extra
                    )
        elif query_type == "comparative":
            extras = await asyncio.gather(
                fetch_evidence_data(query),
                return_exceptions=True,
            )
            for extra in extras:
                if isinstance(extra, EvidenceFetchResult) and extra.fetch_success:
                    fetched_data.comparative_evidence = _enrich_evidence_result(
                        fetched_data.comparative_evidence, extra
                    )
        elif query_type == "drug":
            tasks = [fetch_evidence_data(query)]
            if condition_context:
                tasks.append(fetch_disease_data(condition_context))
            extras = await asyncio.gather(*tasks, return_exceptions=True)
            evidence_extra = extras[0] if extras else None
            if (
                fetched_data.drug_data
                and isinstance(evidence_extra, EvidenceFetchResult)
                and evidence_extra.fetch_success
            ):
                fetched_data.drug_data.guideline_abstracts = _merge_abstracts(
                    fetched_data.drug_data.guideline_abstracts,
                    evidence_extra.guideline_abstracts,
                    max_total_chars=7000,
                )
                fetched_data.drug_data.systematic_review_abstracts = _merge_abstracts(
                    fetched_data.drug_data.systematic_review_abstracts,
                    evidence_extra.systematic_review_abstracts,
                    max_total_chars=7000,
                )
                fetched_data.drug_data.clinical_trial_abstracts = _merge_abstracts(
                    fetched_data.drug_data.clinical_trial_abstracts,
                    evidence_extra.clinical_trial_abstracts,
                    max_total_chars=7000,
                )
            if condition_context and len(extras) > 1:
                condition_extra = extras[1]
                if isinstance(condition_extra, DiseaseFetchResult) and condition_extra.fetch_success:
                    fetched_data.condition_data = _enrich_disease_result(
                        fetched_data.condition_data, condition_extra
                    )
    except Exception:
        logger.warning("Second-pass retrieval expansion failed", exc_info=True)

    score2, sufficient2, reasons2 = _retrieval_assessment(fetched_data, query_type)
    notes.append(f"post-expansion retrieval score={score2}")
    notes.extend(reasons2)
    if not sufficient2:
        fetched_data.fallback_to_llm = True
    return fetched_data, notes


def _adaptive_sparse_reasons(response_dict: dict, query_type: str) -> list[str]:
    reasons: list[str] = []
    sections = response_dict.get("sections", [])
    references = response_dict.get("references", [])
    if len(sections) < 2:
        reasons.append("too few sections")
    placeholder_items = 0
    total_items = 0
    for section in sections:
        items = section.get("content_items", []) or []
        total_items += len(items)
        if len(items) < 1:
            reasons.append(f"section '{section.get('title', 'unknown')}' is empty")
        for item in items:
            text = str(item.get("text") or "")
            if _INSUFFICIENT_DATA_RE.search(text):
                placeholder_items += 1
    if total_items and placeholder_items >= max(2, total_items // 2):
        reasons.append("too many insufficient-data placeholders")
    if query_type in {"disease", "comparative", "evidence"} and len(references) < 2:
        reasons.append("too few references")
    if query_type in {"drug", "procedure"} and len(references) < 1:
        reasons.append("missing references")
    return list(dict.fromkeys(reasons))


DISCLAIMER = (
    "This information is generated by AI for educational and clinical decision support purposes only. "
    "It does not replace professional medical judgment. Always verify with current clinical guidelines "
    "and consult appropriate specialists. Patient-specific factors must be considered."
)

RESPONSE_MODELS = {
    "drug": DrugResponse,
    "disease": DiseaseResponse,
    "comparative": ComparativeResponse,
    "procedure": ProcedureResponse,
    "evidence": EvidenceResponse,
    "general": GeneralResponse,
}

def _is_critically_sparse(data: dict, query_type: str) -> tuple[bool, list[str]]:
    """Detect if an LLM response is critically sparse and needs a retry.

    Returns (is_sparse, list_of_reasons).
    """
    reasons: list[str] = []
    if query_type == "disease":
        if len(data.get("clinical_features", [])) < 4:
            reasons.append(
                f"clinical_features only {len(data.get('clinical_features', []))} entries (need 8+)"
            )
        if not data.get("treatment", {}).get("first_line"):
            reasons.append("treatment.first_line empty")
        if len(data.get("diagnostic_criteria", [])) < 3:
            reasons.append(
                f"diagnostic_criteria only {len(data.get('diagnostic_criteria', []))} entries (need 6+)"
            )
        if not data.get("etiology"):
            reasons.append("etiology empty")
        if not data.get("prognosis"):
            reasons.append("prognosis missing")
        return len(reasons) >= 2, reasons
    elif query_type == "drug":
        if not data.get("dosing") and not data.get("indications"):
            reasons.append("dosing and indications both empty")
            return True, reasons
        if (
            len(data.get("side_effects", [])) < 3
            and len(data.get("interactions", [])) < 3
        ):
            reasons.append(
                f"side_effects={len(data.get('side_effects', []))} and interactions={len(data.get('interactions', []))} both < 3"
            )
            return True, reasons
    elif query_type == "comparative":
        n_dims = len(data.get("detailed_comparison", []))
        if n_dims < 6:
            reasons.append(f"detailed_comparison only {n_dims} dimensions (need 8+)")
            return True, reasons
    elif query_type == "evidence":
        n_supporting = len(data.get("supporting_studies", []))
        if n_supporting < 2:
            reasons.append(f"supporting_studies only {n_supporting} (need 3+)")
            return True, reasons
        summary = data.get("summary", "")
        if not summary or len(summary) < 100:
            reasons.append("summary too short (need 4-6 sentences)")
            return True, reasons
    elif query_type == "procedure":
        n_steps = len(data.get("technique_steps", []))
        if n_steps < 3:
            reasons.append(f"technique_steps only {n_steps} (need 5+)")
            return True, reasons
    return False, []


# Model tier ranking — higher number = more capable
# Used to ensure user's model choice is never downgraded by routing
def _model_tier(model_id: str) -> int:
    """Return a tier number for a model — higher = more capable."""
    m = model_id.lower()
    if "opus" in m:
        return 3
    if "sonnet" in m:
        return 2
    if "haiku" in m:
        return 1
    # Unknown models (e.g. OpenRouter) — treat as mid-tier
    return 2


# Async log queue
_log_queue: asyncio.Queue | None = None
_log_task: asyncio.Task | None = None


async def init_log_queue():
    """Initialize the async logging queue and consumer."""
    global _log_queue, _log_task
    _log_queue = asyncio.Queue(maxsize=settings.log_queue_max_size)
    _log_task = asyncio.create_task(_log_consumer())


async def shutdown_log_queue():
    """Shutdown the async logging queue."""
    global _log_task
    if _log_task:
        _log_task.cancel()
        try:
            await _log_task
        except asyncio.CancelledError:
            pass


async def _log_consumer():
    """Drain the log queue and write to DB."""
    while True:
        try:
            entry = await _log_queue.get()
            await _write_log_entry(entry)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.error("Log consumer error", exc_info=True)


async def _write_log_entry(entry: dict):
    """Write a log entry to DB with retry and file fallback."""
    for attempt in range(settings.log_db_retry_max + 1):
        try:
            async with async_session() as session:
                # Truncate oversized response
                response_json = entry.get("response_json", {})
                response_str = json.dumps(response_json)
                truncated = False
                if len(response_str.encode()) > settings.max_response_jsonb_bytes:
                    response_str = response_str[: settings.truncated_response_bytes]
                    response_json = json.loads(response_str + "}")  # best effort
                    truncated = True

                log = QueryLog(
                    query=entry["query"],
                    query_type=entry["query_type"],
                    model_used=entry["model_used"],
                    response_json=response_json,
                    latency_ms=entry["latency_ms"],
                    cached=entry.get("cached", False),
                    truncated=truncated,
                    user_key_id=entry.get("user_key_id"),
                )
                session.add(log)
                await session.commit()
                return
        except Exception:
            if attempt < settings.log_db_retry_max:
                await asyncio.sleep(settings.log_db_retry_backoff)
            else:
                # File fallback
                logger.error(
                    "DB log write failed after retries, writing to file", exc_info=True
                )
                try:
                    import aiofiles

                    async with aiofiles.open(
                        "/app/logs/query_log_fallback.jsonl", "a"
                    ) as f:
                        await f.write(json.dumps(entry, default=str) + "\n")
                except Exception:
                    # Last resort: structured log
                    logger.error(f"FALLBACK_LOG: {json.dumps(entry, default=str)}")


async def _enqueue_log(entry: dict):
    """Add a log entry to the async queue."""
    if _log_queue is None:
        return
    try:
        _log_queue.put_nowait(entry)
    except asyncio.QueueFull:
        logger.warning("Log queue full, dropping oldest entry")
        try:
            _log_queue.get_nowait()
            _log_queue.put_nowait(entry)
        except Exception:
            pass


async def _call_llm(
    model_id: str,
    prompt: str,
    max_tokens: int | None = None,
    user_key: str | None = None,
    user_provider: str | None = None,
) -> str | None:
    """Call LLM with circuit breaker protection (BYOK — user key required)."""
    provider = user_provider or get_provider(model_id)
    breaker = get_breaker(provider)

    # Raises HTTP 402 if no key — let it propagate up to process_query
    llm = create_llm(
        model_id, max_tokens=max_tokens, user_key=user_key, user_provider=user_provider
    )

    try:

        @breaker
        async def _invoke():
            if provider == "anthropic":
                # Split at the last "Query: " line so the large system instructions
                # (context + data) get cached and only the query is sent as a
                # human turn. Falls back to full-prompt human message if no split found.
                split_marker = "\nQuery: "
                split_idx = prompt.rfind(split_marker)
                if split_idx != -1:
                    system_text = prompt[:split_idx]
                    human_text = prompt[split_idx + 1:]  # strip leading \n
                else:
                    system_text = prompt
                    human_text = "Generate the response now."
                messages = [
                    SystemMessage(content=[
                        {"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}
                    ]),
                    HumanMessage(content=human_text),
                ]
                response = await llm.ainvoke(messages)
            else:
                response = await llm.ainvoke(prompt)
            return response.content

        return await _invoke()
    except pybreaker.CircuitBreakerError:
        logger.warning(f"Circuit breaker open for {provider}")
        raise HTTPException(
            status_code=503,
            detail="LLM service temporarily unavailable — please try again in a few seconds.",
        )
    except HTTPException:
        raise
    except openai.RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="OpenRouter rate limit exceeded. Free models have limited throughput — wait a few seconds and retry.",
        )
    except (openai.AuthenticationError, openai.PermissionDeniedError):
        raise HTTPException(
            status_code=401,
            detail="LLM API key rejected — please verify your key is valid in Settings.",
        )
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        raise HTTPException(
            status_code=401,
            detail="Anthropic API key rejected — please verify your key is valid in Settings.",
        )
    except anthropic.RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="Anthropic rate limit exceeded — please wait a moment and retry.",
        )
    except anthropic.BadRequestError as e:
        msg = str(e)
        if "credit balance is too low" in msg or "billing" in msg.lower():
            raise HTTPException(
                status_code=402,
                detail="Your Anthropic account has insufficient credits. Please top up at console.anthropic.com → Plans & Billing.",
            )
        raise HTTPException(status_code=400, detail=f"Anthropic rejected the request: {msg}")
    except anthropic.APIConnectionError:
        logger.error(f"Anthropic connection error for {model_id}", exc_info=True)
        return None
    except Exception:
        logger.error(f"LLM call failed for {model_id}", exc_info=True)
        return None


async def _rewrite_query(
    query: str,
    model_id: str,
    user_key: str | None = None,
    user_provider: str | None = None,
) -> str:
    """Rewrite the raw user query for better API matching and vector recall.

    Fixes typos, expands abbreviations, and sharpens clinical intent.
    Returns the original query on any error (fire-and-forget fallback).
    """
    _rewrite_prompt = (
        "You are a medical query pre-processor. Rewrite the following query to be clear, "
        "correctly spelled, and unambiguous for a clinical reference system.\n"
        "- Fix all spelling and typo errors\n"
        "- Expand common medical abbreviations\n"
        "- Keep the clinical intent exactly the same\n"
        "- Return ONLY the rewritten query, nothing else\n\n"
        f"Query: {query}"
    )
    try:
        result = await _call_llm(
            model_id,
            _rewrite_prompt,
            max_tokens=64,
            user_key=user_key,
            user_provider=user_provider,
        )
        if result and result.strip():
            return result.strip()
    except Exception:
        pass
    return query


_CLAIM_FIELDS = {"loe", "cor", "source", "confidence", "value"}
_VALID_LOE = {"I", "II-1", "II-2", "II-3", "III"}
_VALID_COR = {"I", "IIa", "IIb", "III-no-benefit", "III-harm"}

_PRICING = {
    "claude-haiku-4-5-20251001": {"in": 0.80, "out": 4.00},
    "claude-sonnet-4-20250514": {"in": 3.00, "out": 15.00},
}


def _model_cost(model_id: str, inp: int, out: int) -> ModelCost:
    key = next((k for k in _PRICING if k in model_id), None)
    rates = _PRICING.get(key, {"in": 3.00, "out": 15.00})
    in_cost = round(inp / 1_000_000 * rates["in"], 6)
    out_cost = round(out / 1_000_000 * rates["out"], 6)
    return ModelCost(
        model_id=model_id,
        input_tokens=inp,
        output_tokens=out,
        input_cost_usd=in_cost,
        output_cost_usd=out_cost,
        subtotal_usd=round(in_cost + out_cost, 6),
    )


def _coerce_evidenced_claims(obj: object) -> None:
    """Recursively fill missing/invalid required EvidencedClaim fields with safe defaults.

    Safety rule: claims with no source get LOE III + COR IIb + low confidence
    to prevent unsourced claims from appearing authoritative.
    """
    if isinstance(obj, dict):
        if "value" in obj or (_CLAIM_FIELDS & obj.keys()):
            has_source = bool(
                obj.get("source")
                and obj["source"] not in ("Clinical guidelines", "Expert opinion")
            )

            loe = obj.get("loe") or ""
            if isinstance(loe, str):
                loe = loe.strip()
            if not loe or loe not in _VALID_LOE:
                obj["loe"] = "III"

            cor = obj.get("cor") or ""
            if isinstance(cor, str):
                cor = cor.strip()
            if not cor or cor not in _VALID_COR:
                final_loe_check = obj.get("loe") or "III"
                if final_loe_check == "III" or not has_source:
                    obj["cor"] = None
                else:
                    obj["cor"] = "IIa"

            # LOE↔COR consistency enforcement (patient safety)
            final_loe = obj["loe"]
            final_cor = obj.get("cor")
            if final_cor is not None:
                if final_loe == "III" and final_cor == "I":
                    obj["cor"] = None
                elif final_loe == "I" and final_cor == "IIb":
                    obj["cor"] = "IIa"

            if not obj.get("source"):
                obj["source"] = "Expert opinion"

            # Normalize confidence to lowercase (LLM may return "MODERATE")
            conf = obj.get("confidence") or ""
            if isinstance(conf, str):
                conf = conf.strip().lower()
            if conf not in ("high", "moderate", "low"):
                obj["confidence"] = "low" if not has_source else "moderate"
            else:
                obj["confidence"] = conf
        for v in obj.values():
            _coerce_evidenced_claims(v)
    elif isinstance(obj, list):
        for item in obj:
            _coerce_evidenced_claims(item)


def _validate_evidence_consistency(data: dict, query_type: str) -> list[str]:
    """Item 9: catch logically impossible LOE/COR/confidence combinations."""
    warnings: list[str] = []
    field_map = {
        "disease": ["etiology", "clinical_features", "diagnostic_criteria", "complications"],
        "drug": ["indications", "dosing", "contraindications", "side_effects"],
        "procedure": ["indications", "complications"],
        "evidence": ["supporting_studies"],
    }
    for field in field_map.get(query_type, []):
        items = data.get(field)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            loe = item.get("loe", "")
            cor = item.get("cor", "")
            conf = item.get("confidence", "")
            if loe == "I" and cor in ("III-no-benefit", "III-harm"):
                warnings.append(f"Inconsistent LOE I + {cor} in '{field}'")
            if loe == "III" and cor == "I":
                warnings.append(f"Inconsistent LOE III + COR I in '{field}'")
            if conf == "high" and loe == "III":
                warnings.append(f"Inconsistent confidence=high + LOE III in '{field}'")
            if conf == "low" and loe in ("I", "II-1"):
                warnings.append(f"Inconsistent confidence=low + LOE {loe} in '{field}'")
    return warnings


def _validate_response(data: dict, query_type: str) -> tuple[dict | None, list[str]]:
    """Validate response structurally (Pydantic) and semantically."""
    warnings = []
    model_cls = RESPONSE_MODELS.get(query_type)
    if not model_cls:
        return data, ["Unknown query type"]

    # Fill in missing required EvidencedClaim fields before validation
    _coerce_evidenced_claims(data)

    try:
        validated = model_cls.model_validate(data)
        data = validated.model_dump()
    except ValidationError as e:
        logger.warning(f"Pydantic validation failed: {e}")
        return None, [f"Structural validation failed: {str(e)[:200]}"]

    # Semantic validation
    if query_type == "drug":
        if not data.get("drug_name"):
            warnings.append("Missing drug_name in response")
        if not data.get("dosing"):
            warnings.append("No dosing information provided")
        # Check duplicate interactions
        interactions = data.get("interactions", [])
        seen_drugs = set()
        for ix in interactions:
            drug = ix.get("drug", "").lower()
            if drug in seen_drugs:
                warnings.append(f"Duplicate interaction entry: {drug}")
            seen_drugs.add(drug)

    elif query_type == "disease":
        if not data.get("disease_name"):
            warnings.append("Missing disease_name in response")
        treatment = data.get("treatment", {})
        if not treatment.get("first_line"):
            warnings.append("No first-line treatment provided")
        if not data.get("diagnostic_criteria"):
            warnings.append("No diagnostic criteria provided")
        if (
            not data.get("clinical_features")
            or len(data.get("clinical_features", [])) < 3
        ):
            warnings.append("Insufficient clinical features — expected 6+ entries")
        if not data.get("etiology"):
            warnings.append("No etiology provided")
        if not data.get("prognosis"):
            warnings.append("No prognosis provided")
        if not data.get("pathophysiology"):
            warnings.append("No pathophysiology provided")
        if not treatment.get("non_pharmacological"):
            warnings.append("No non-pharmacological treatment provided")

    elif query_type == "comparative":
        compared = data.get("entities_compared", [])
        if len(compared) < 2:
            warnings.append("Fewer than 2 entities compared")
        if not data.get("detailed_comparison"):
            warnings.append("No detailed comparison provided")

    # Item 9: evidence consistency check (appended as warnings, not blocking)
    consistency_warnings = _validate_evidence_consistency(data, query_type)
    warnings.extend(consistency_warnings)

    return data, warnings


async def _log_search_history(
    user_id: int, query_text: str, query_type: str, result: dict
):
    """Fire-and-forget: persist a search history entry for the user."""
    try:
        from app.db.session import async_session as session_factory
        from app.models.search_history import SearchHistory
        from sqlalchemy import select, func

        async with session_factory() as session:
            # Enforce max 100 entries per user
            count_result = await session.execute(
                select(func.count())
                .select_from(SearchHistory)
                .where(SearchHistory.user_id == user_id)
            )
            count = count_result.scalar() or 0
            if count >= 100:
                oldest = await session.execute(
                    select(SearchHistory)
                    .where(SearchHistory.user_id == user_id)
                    .order_by(SearchHistory.created_at.asc())
                    .limit(1)
                )
                old = oldest.scalar_one_or_none()
                if old:
                    await session.delete(old)
            summary = str(result)[:300] if result else ""
            session.add(
                SearchHistory(
                    user_id=user_id,
                    query_text=query_text,
                    query_type=query_type,
                    response_summary=summary,
                )
            )
            await session.commit()
    except Exception as e:
        logger.debug(f"Search history logging failed: {e}")


def _default_model_for_provider(provider: str | None) -> str:
    if provider == "openrouter":
        return settings.openrouter_default_model
    if provider == "openai":
        return settings.openai_default_model
    return settings.model_sonnet


def _normalize_model_for_provider(
    model_id: str,
    provider: str | None,
    model_explicit: bool,
) -> str:
    if provider == "openrouter":
        return model_id if "/" in model_id else settings.openrouter_default_model
    if provider == "openai":
        return model_id if "/" not in model_id else settings.openai_default_model
    if provider == "anthropic":
        return model_id if "/" not in model_id else settings.model_sonnet
    if model_explicit:
        return model_id
    return model_id or settings.model_sonnet


def _sanitize_entities(entities: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for entity in entities or []:
        value = re.sub(r"\s+", " ", str(entity or "")).strip(" ,.-")
        if len(value) < 2:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(value)
    return cleaned[:4]


async def _analyze_query_with_dspy(
    query: str,
    *,
    model_id: str,
    user_key: str | None,
    user_provider: str | None,
) -> dict | None:
    if not settings.dspy_enabled or not user_key:
        return None

    try:
        import dspy as _dspy

        from app.services.dspy_lm import get_dspy_lm
        from app.services.dspy_signatures import MedicalQueryAnalysis

        lm = get_dspy_lm(
            model_id,
            user_key,
            user_provider or "anthropic",
            depth="quick",
        )
        with _dspy.context(lm=lm):
            analyzer = _dspy.ChainOfThought(MedicalQueryAnalysis)
            analysis = analyzer(query=query, available_data_types="none yet")

        entities = _sanitize_entities(list(getattr(analysis, "entities", []) or []))
        condition_context = getattr(analysis, "condition_context", None)
        if isinstance(condition_context, str):
            condition_context = condition_context.strip() or None
        else:
            condition_context = None

        query_type = str(getattr(analysis, "query_type", "general") or "general")
        if query_type not in RESPONSE_MODELS and query_type != "general":
            query_type = "general"

        return {
            "query_type": query_type,
            "entities": entities,
            "condition_context": condition_context,
            "response_focus": str(getattr(analysis, "response_focus", "") or ""),
            "depth": str(getattr(analysis, "depth", "standard") or "standard"),
            "related_topics": list(getattr(analysis, "related_topics", []) or []),
        }
    except Exception:
        logger.warning("DSPy query analysis failed; falling back", exc_info=True)
        return None


async def process_query(
    request: QueryRequest,
    redis_client=None,
    user_key_id: str | None = None,
    user=None,
) -> QueryResponse:
    """Main RAG pipeline orchestrator."""
    start_time = time.time()
    validation_warnings: list[str] = []

    # Resolve user's BYOK key (only user-supplied key is used — no server .env fallback)
    user_llm_key: str | None = None
    user_llm_provider: str | None = None
    if user and user.encrypted_llm_key:
        from app.services.byok import decrypt_key

        user_llm_key = decrypt_key(user.encrypted_llm_key)
        user_llm_provider = user.llm_provider
        if user_llm_key is None:
            # Decryption failed (e.g. ENCRYPTION_KEY changed after restart)
            latency_ms = int((time.time() - start_time) * 1000)
            return QueryResponse(
                query_type="general",
                model_used=request.model_id,
                response=DegradedResponse(
                    message="Your API key could not be retrieved — please re-enter it in Settings.",
                    suggestion="Go to Settings → LLM API Key and save your key again. This happens when the server restarts without a stable ENCRYPTION_KEY.",
                ),
                disclaimer=DISCLAIMER,
                latency_ms=latency_ms,
            )

    # Fetch voyage API key (for Anthropic users who want vector search),
    # NCBI API key (for PubMed rate limit increase), and user email (for Unpaywall)
    user_voyage_key: str | None = None
    user_ncbi_key: str | None = None
    user_email: str | None = getattr(user, "email", None)
    if user and user.id:
        try:
            from app.models.service_key import ServiceKey
            from app.services.byok import decrypt_key as _dk
            async with async_session() as _sk_session:
                from sqlalchemy import select as _sel
                _sk_rows = (await _sk_session.execute(
                    _sel(ServiceKey).where(
                        ServiceKey.user_id == user.id,
                        ServiceKey.service_name.in_(["voyageai", "ncbi"]),
                    )
                )).scalars().all()
                for _sk_row in _sk_rows:
                    if _sk_row.service_name == "voyageai" and user_llm_provider == "anthropic":
                        user_voyage_key = _dk(_sk_row.encrypted_key)
                    elif _sk_row.service_name == "ncbi":
                        user_ncbi_key = _dk(_sk_row.encrypted_key)
        except Exception:
            pass  # non-critical

    provider_for_request = user_llm_provider or get_provider(request.model_id)
    normalized_request_model = _normalize_model_for_provider(
        request.model_id or _default_model_for_provider(provider_for_request),
        provider_for_request,
        request.model_explicit,
    )

    query_intent = detect_intent(request.query)

    # Speculative type via rule-based classifier (sync, ~1ms) — used for parallel cache check
    speculative_type, _ = classify_query(request.query)

    # Run DSPy analysis, Redis cache check, and query rewriter in parallel
    _dspy_result, _cache_prefetch, _rewritten = await asyncio.gather(
        _analyze_query_with_dspy(
            request.query,
            model_id=normalized_request_model,
            user_key=user_llm_key,
            user_provider=user_llm_provider,
        ),
        cache_get(redis_client, request.query, speculative_type, normalized_request_model),
        _rewrite_query(
            request.query,
            model_id=normalized_request_model,
            user_key=user_llm_key,
            user_provider=user_llm_provider,
        ),
        return_exceptions=True,
    )
    query_analysis = _dspy_result if not isinstance(_dspy_result, Exception) else None
    _speculative_cache = _cache_prefetch if not isinstance(_cache_prefetch, Exception) else None
    rewritten_query = (
        _rewritten
        if isinstance(_rewritten, str) and _rewritten.strip()
        else request.query
    )
    if rewritten_query != request.query:
        logger.info("Query rewritten: %r → %r", request.query, rewritten_query)

    if request.query_type:
        query_type, confidence = request.query_type, 0.99
    elif query_analysis:
        query_type, confidence = query_analysis["query_type"], 0.95
    else:
        query_type, confidence = await classify_query_llm(
            request.query,
            user_key=user_llm_key,
            user_provider=user_llm_provider,
            model_id=normalized_request_model,
        )

    # Item 18: confidence fallback — use rule-based classifier when LLM confidence is low
    if confidence < settings.classifier_confidence_threshold:
        fallback_type, fallback_conf = classify_query(request.query)
        if fallback_conf >= confidence:
            logger.info(
                "Classifier confidence %.2f below threshold %.2f — using rule-based: %s→%s",
                confidence,
                settings.classifier_confidence_threshold,
                query_type,
                fallback_type,
            )
            query_type, confidence = fallback_type, fallback_conf

    if query_intent == "highlights" and query_type not in (
        "drug",
        "disease",
        "comparative",
        "procedure",
        "evidence",
    ):
        query_type = "general"

    analysis_entities = _sanitize_entities(query_analysis["entities"]) if query_analysis else []
    condition_context = query_analysis.get("condition_context") if query_analysis else None

    # Track query frequency for self-improvement (fire-and-forget)
    if redis_client:
        try:
            normalized = request.query.strip().lower()
            await redis_client.zincrby(
                "iatronix:query_freq", 1, f"{query_type}:{normalized}"
            )
            await redis_client.zincrby("iatronix:type_freq", 1, query_type)
        except Exception:
            pass  # non-critical

    # Use pre-fetched cache result if speculative type matched; otherwise re-check
    if speculative_type == query_type:
        cached_data = _speculative_cache
    else:
        cached_data = await cache_get(
            redis_client, request.query, query_type, normalized_request_model
        )
    if cached_data:
        latency_ms = int((time.time() - start_time) * 1000)
        cached_data["cached"] = True
        cached_data["latency_ms"] = latency_ms
        response = QueryResponse(**cached_data)
        await _enqueue_log(
            {
                "query": request.query,
                "query_type": query_type,
                "model_used": normalized_request_model,
                "response_json": cached_data,
                "latency_ms": latency_ms,
                "cached": True,
                "user_key_id": user_key_id,
            }
        )
        if user and user.id:
            asyncio.create_task(
                _log_search_history(user.id, request.query, query_type, cached_data)
            )
        return response

    # Circuit breaker check
    provider = user_llm_provider or get_provider(normalized_request_model)
    if not is_provider_available(provider):
        # Try cached response (any version)
        any_cached = await cache_get_any_version(
            redis_client, request.query, query_type, normalized_request_model
        )
        if any_cached:
            latency_ms = int((time.time() - start_time) * 1000)
            return QueryResponse(**any_cached, cached=True, latency_ms=latency_ms)

        # Degraded response — circuit is open, no fallback provider in BYOK mode
        latency_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            query_type=query_type,
            model_used=normalized_request_model,
            response=DegradedResponse(),
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
        )

    # Route and fetch external data + vector search in parallel
    # source_mode: "ai" = full pipeline, "scraping" = API only (no vector)
    source_mode = getattr(request, "source_mode", "ai")
    use_api_fetch = settings.api_fetch_enabled
    use_vector = settings.vector_search_enabled and source_mode != "scraping"

    fetched_data: FetchedData | None = None
    vector_results = []
    routing = None
    retrieval_notes: list[str] = []

    tasks = {}
    if use_api_fetch:
        routing = route_query(
            rewritten_query,
            query_type,
            entities=analysis_entities or None,
            requested_model=normalized_request_model,
            user_provider=user_llm_provider,
            model_explicit=request.model_explicit,
            condition_context=condition_context,
        )
        if routing.fetch_enabled:
            tasks["api"] = asyncio.wait_for(
                fetch_data_for_query(
                    query_type,
                    routing.entities,
                    condition_context=routing.condition_context,
                    user_email=user_email,
                    ncbi_api_key=user_ncbi_key,
                ),
                timeout=settings.api_fetch_timeout_seconds + 1.0,
            )

    if use_vector:
        tasks["vector"] = vector_search(
            rewritten_query,
            user_key=user_llm_key,
            user_provider=user_llm_provider,
            voyage_api_key=user_voyage_key,
        )

    # Semantic cache check runs in parallel with API fetch and vector search
    tasks["sem"] = semantic_cache_get(request.query, query_type, normalized_request_model)

    _fetch_t0 = time.perf_counter()
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    _sem_result = None
    for key, result in zip(tasks.keys(), results):
        if key == "api":
            if isinstance(result, asyncio.TimeoutError):
                logger.warning("API fetch timed out — using generate mode")
                fetched_data = FetchedData(
                    query_type=query_type, fallback_to_llm=True
                )
            elif isinstance(result, Exception):
                logger.warning("API fetch error: %s", result)
            else:
                fetched_data = result
        elif key == "vector":
            if isinstance(result, Exception):
                logger.warning("Vector search error: %s", result)
            else:
                vector_results = result
        elif key == "sem":
            if not isinstance(result, Exception):
                _sem_result = result
    logger.info(
        "pipeline.data_fetch",
        extra={
            "stage": "data_fetch",
            "query_type": query_type,
            "duration_ms": round((time.perf_counter() - _fetch_t0) * 1000),
            "fetch_success": fetched_data.fetch_success if hasattr(fetched_data, "fetch_success") else False,
            "vector_hits": len(vector_results),
        },
    )

    # Handle semantic cache hit (checked in parallel above)
    if _sem_result is not None:
        sem_response, sem_cache_id = _sem_result if isinstance(_sem_result, tuple) else (None, None)
        if sem_response:
            latency_ms = int((time.time() - start_time) * 1000)
            sem_response["cached"] = True
            sem_response["latency_ms"] = latency_ms
            try:
                _sem_hit_resp = QueryResponse(**sem_response)
            except Exception:
                _sem_hit_resp = None
            if _sem_hit_resp:
                _sem_stale = is_stale(
                    sem_response.get("_last_verified_at"),
                    settings.semantic_cache_swr_ttl_seconds,
                )
                if _sem_stale and sem_cache_id:
                    asyncio.create_task(
                        _revalidate_semantic_cache(
                            request,
                            query_type,
                            sem_cache_id,
                            redis_client,
                            user_key_id,
                            user_llm_key,
                            user_llm_provider,
                            user=user,
                        )
                    )
                if user and user.id:
                    asyncio.create_task(
                        _log_search_history(user.id, request.query, query_type, sem_response)
                    )
                return _sem_hit_resp

    if use_api_fetch and fetched_data is not None and not fetched_data.fallback_to_llm:
        fetched_data, retrieval_notes = await _expand_retrieval_if_needed(
            query=request.query,
            query_type=query_type,
            fetched_data=fetched_data,
            entities=routing.entities if routing else (analysis_entities or []),
            condition_context=condition_context,
            response_focus=(query_analysis or {}).get("response_focus") if query_analysis else None,
        )

    prompt_mode = (
        "format" if (fetched_data and not fetched_data.fallback_to_llm) else "generate"
    )
    fetch_latency_ms = fetched_data.total_fetch_time_ms if fetched_data else 0

    # Scraping-only mode: skip LLM and return raw API data directly
    if source_mode == "scraping":
        raw_resp = _build_scraping_response(request.query, query_type, fetched_data)
        if raw_resp is not None:
            latency_ms = int((time.time() - start_time) * 1000)
            return QueryResponse(
                query_type=query_type,
                model_used="none",
                response=raw_resp,
                disclaimer=(
                    "Raw data from medical databases (OpenFDA, PubMed, RxNorm). "
                    "Not AI-formatted or verified. Use clinical judgment."
                ),
                latency_ms=latency_ms,
                validation_warnings=retrieval_notes,
            )

    # Only fail-closed if fetch succeeded but data quality was insufficient.
    # If fetch timed out, let LLM generate from training knowledge (that's what "generate" mode is for).
    fetch_timed_out = (
        fetched_data is not None
        and fetched_data.fallback_to_llm
        and fetched_data.drug_data is None
        and fetched_data.disease_data is None
        and fetched_data.procedure_data is None
        and fetched_data.evidence_data is None
    )

    if settings.fail_closed_evidence_only and prompt_mode == "generate" and not fetch_timed_out:
        latency_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            query_type=query_type,
            model_used=normalized_request_model,
            response=DegradedResponse(
                message="The system could not retrieve enough evidence to produce a supported answer.",
                suggestion="Try a more specific query, or rephrase with the exact drug, disease, procedure, or comparison you want.",
            ),
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
            validation_warnings=retrieval_notes
            + [
                "Fail-closed mode blocked an evidence-insufficient response to reduce hallucination risk."
            ],
        )

    # Model and token budget selection
    # If user explicitly chose a model, respect it unconditionally.
    # Routing only applies when user is on the default (auto) model.
    effective_model = normalized_request_model
    max_tokens = settings.llm_max_tokens_generate
    if (
        settings.model_routing_enabled
        and not request.model_explicit
        and routing is not None
        and fetched_data is not None
        and not fetched_data.fallback_to_llm
        and user_llm_provider == "anthropic"
    ):
        effective_model = routing.preferred_model
        if query_type == "disease":
            max_tokens = settings.llm_max_tokens_format_disease
        elif query_type == "evidence":
            max_tokens = settings.llm_max_tokens_format_evidence
        elif query_type == "procedure":
            max_tokens = settings.llm_max_tokens_format_procedure
        elif query_type == "drug" and condition_context:
            max_tokens = settings.llm_max_tokens_format_drug_context
            if not request.model_explicit and user_llm_provider == "anthropic":
                effective_model = settings.model_sonnet
        else:
            max_tokens = settings.llm_max_tokens_format
    elif query_type == "disease":
        max_tokens = settings.llm_max_tokens_format_disease
        if not request.model_explicit and user_llm_provider == "anthropic":
            effective_model = settings.model_sonnet
    elif query_type == "evidence":
        max_tokens = settings.llm_max_tokens_format_evidence
    elif query_type == "procedure":
        max_tokens = settings.llm_max_tokens_format_procedure
    elif query_type == "drug" and condition_context:
        max_tokens = settings.llm_max_tokens_format_drug_context
        if not request.model_explicit and user_llm_provider == "anthropic":
            effective_model = settings.model_sonnet

    # ── Unified Adaptive Generation ───────────────────────────────────────────
    # All query types use a single adaptive prompt. DSPy is kept only for
    # classification (query_type, required_sections, related_topics).
    required_sections: list[str] = (
        list(query_analysis.get("required_sections", [])) if query_analysis else []
    )

    system_text, user_text = build_adaptive_messages(
        rewritten_query,
        query_type,
        fetched_data=fetched_data,
        vector_results=vector_results,
        required_sections=required_sections or None,
        condition_context=condition_context,
    )

    _llm_t0 = time.perf_counter()
    raw_response: str | None = None
    _gen_usage: dict = {}
    try:
        _gen_llm = create_llm(
            effective_model,
            max_tokens=max_tokens,
            user_key=user_llm_key,
            user_provider=user_llm_provider,
        )
        _gen_provider = user_llm_provider or get_provider(effective_model)
        _gen_breaker = get_breaker(_gen_provider)

        @_gen_breaker
        async def _invoke_adaptive():
            nonlocal _gen_usage
            if _gen_provider == "anthropic":
                _msgs = [
                    SystemMessage(content=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}]),
                    HumanMessage(content=user_text),
                ]
            else:
                _msgs = [SystemMessage(content=system_text), HumanMessage(content=user_text)]
            _llm_msg = await _gen_llm.ainvoke(_msgs)
            _usage = getattr(_llm_msg, "usage_metadata", None) or {}
            _gen_usage = {
                "input_tokens": _usage.get("input_tokens", _usage.get("prompt_tokens", 0)) or 0,
                "output_tokens": _usage.get("output_tokens", _usage.get("completion_tokens", 0)) or 0,
            }
            return _llm_msg.content

        raw_response = await _invoke_adaptive()
    except pybreaker.CircuitBreakerError:
        raise HTTPException(
            status_code=503,
            detail="LLM service temporarily unavailable — please try again in a few seconds.",
        )
    except HTTPException as e:
        if e.status_code in (401, 429):
            latency_ms = int((time.time() - start_time) * 1000)
            return QueryResponse(
                query_type=query_type,
                model_used=effective_model,
                response=DegradedResponse(
                    message=e.detail,
                    suggestion=(
                        "Wait a few seconds and retry."
                        if e.status_code == 429
                        else "Go to Settings → LLM API Key and re-enter your key."
                    ),
                ),
                disclaimer=DISCLAIMER,
                latency_ms=latency_ms,
            )
        if e.status_code == 402:
            latency_ms = int((time.time() - start_time) * 1000)
            no_key = isinstance(e.detail, dict) and e.detail.get("error") == "no_api_key"
            if no_key:
                deg_msg = "AI formatting is unavailable — no API key configured. Please add your API key in Settings."
                deg_sug = "Add your Anthropic, OpenAI, or OpenRouter API key in Settings to enable AI-formatted responses."
            else:
                deg_msg = e.detail if isinstance(e.detail, str) else "Billing error — the LLM provider rejected the request."
                deg_sug = "Check your account billing at console.anthropic.com → Plans & Billing, then retry."
            if user and user.id:
                asyncio.create_task(_log_search_history(user.id, request.query, query_type, {}))
            latency_ms = int((time.time() - start_time) * 1000)
            return QueryResponse(
                query_type=query_type,
                model_used=effective_model,
                response=DegradedResponse(message=deg_msg, suggestion=deg_sug),
                disclaimer=DISCLAIMER,
                latency_ms=latency_ms,
            )
        raise
    except openai.RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded — wait a few seconds and retry.",
        )
    except (openai.AuthenticationError, openai.PermissionDeniedError):
        raise HTTPException(
            status_code=401,
            detail="LLM API key rejected — please verify your key in Settings.",
        )
    except anthropic.RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="Anthropic rate limit exceeded — wait a moment and retry.",
        )
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        raise HTTPException(
            status_code=401,
            detail="Anthropic API key rejected — please verify your key in Settings.",
        )
    except anthropic.BadRequestError as _e:
        _msg = str(_e)
        if "credit balance is too low" in _msg or "billing" in _msg.lower():
            raise HTTPException(
                status_code=402,
                detail="Your Anthropic account has insufficient credits.",
            )
        raise HTTPException(status_code=400, detail=f"Anthropic rejected the request: {_msg}")

    # Parse the adaptive JSON
    parsed = parse_llm_json(raw_response) if raw_response else None

    # Retry once with a stricter suffix if parse failed
    if parsed is None:
        logger.info("Adaptive LLM call failed or unparseable, retrying...")
        await asyncio.sleep(settings.llm_retry_backoff_seconds)
        retry_system = (
            system_text
            + "\n\nCRITICAL: Return ONLY the JSON object described above. "
            "No markdown fences, no prose, no preamble."
        )
        try:
            @_gen_breaker
            async def _retry_adaptive():
                if _gen_provider == "anthropic":
                    _msgs = [
                        SystemMessage(content=[{"type": "text", "text": retry_system, "cache_control": {"type": "ephemeral"}}]),
                        HumanMessage(content=user_text),
                    ]
                else:
                    _msgs = [SystemMessage(content=retry_system), HumanMessage(content=user_text)]
                return (await _gen_llm.ainvoke(_msgs)).content

            raw_retry = await _retry_adaptive()
            if raw_retry:
                parsed = parse_llm_json(raw_retry)
        except Exception:
            pass

    logger.info(
        "pipeline.llm_call",
        extra={
            "stage": "llm_call",
            "query_type": query_type,
            "model": effective_model,
            "prompt_mode": prompt_mode,
            "duration_ms": round((time.perf_counter() - _llm_t0) * 1000),
            "parsed": parsed is not None,
        },
    )

    if parsed is None:
        latency_ms = int((time.time() - start_time) * 1000)
        msg = (
            "LLM service did not respond — this may be a network issue."
            if raw_response is None
            else "Failed to parse AI response. The model returned an unexpected format."
        )
        return QueryResponse(
            query_type=query_type,
            model_used=effective_model,
            response=DegradedResponse(
                message=msg,
                suggestion="Try rephrasing your query or retry in a moment.",
            ),
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
        )

    # Build AdaptiveResponse from parsed dict
    try:
        _raw_refs = parsed.get("references", [])
        enrich_references({"references": _raw_refs}, fetched_data)
        _references = [
            AdaptiveReference(**r) if isinstance(r, dict) else AdaptiveReference(title=str(r))
            for r in _raw_refs
        ]

        _bluf_data = parsed.get("bluf", {})
        _bluf = (
            AdaptiveBLUF(**_bluf_data)
            if isinstance(_bluf_data, dict)
            else AdaptiveBLUF(headline=str(_bluf_data))
        )

        _sections = [
            AdaptiveSection(**s) if isinstance(s, dict) else AdaptiveSection(title=str(s), content_items=[])
            for s in parsed.get("sections", [])
        ]

        adaptive_response = AdaptiveResponse(
            query_type=query_type,
            bluf=_bluf,
            sections=_sections,
            references=_references,
            response_focus=str((query_analysis or {}).get("response_focus", query_type)),
            depth="comprehensive",
            related_topics=list((query_analysis or {}).get("related_topics", [])),
        )
    except Exception as _ve:
        logger.warning("AdaptiveResponse construction failed: %s", _ve)
        latency_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            query_type=query_type,
            model_used=effective_model,
            response=DegradedResponse(
                message="Response validation failed",
                suggestion="Try rephrasing your query.",
            ),
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
        )

    validated_dict = adaptive_response.model_dump()

    # Citation validation
    citation_warnings = validate_citations(validated_dict, query_type, fetched_data)
    validation_warnings.extend(citation_warnings)

    # Safety check
    safety_warnings = check_safety(request.query, validated_dict, query_type)

    # Drug linker
    text_nodes = await process_text_nodes(validated_dict, query_type)

    latency_ms = int((time.time() - start_time) * 1000)

    # Collect data sources used
    fetch_sources = list(fetched_data.data_sources) if fetched_data else []
    if vector_results:
        fetch_sources.append("Vector DB (your PDFs)")

    if prompt_mode == "generate":
        validation_warnings.append(
            "This response was generated by AI without data from medical databases. "
            "Verify claims against authoritative sources before clinical use."
        )

    # Audit log
    audit_id: int | None = None
    try:
        from app.models.query_audit import QueryAudit
        async with async_session() as _audit_session:
            _audit = QueryAudit(
                user_id=user.id if user else None,
                query=request.query,
                retrieved_passages={"count": len(vector_results)} if vector_results else None,
                llm_output=validated_dict,
                verification_passed=len(citation_warnings) == 0,
            )
            _audit_session.add(_audit)
            await _audit_session.commit()
            await _audit_session.refresh(_audit)
            audit_id = _audit.id
    except Exception:
        logger.warning("Audit log write failed", exc_info=True)

    # Build token usage if we have usage data
    token_usage = None
    if _gen_usage:
        models_cost = []
        if _gen_usage:
            gen_cost = _model_cost(
                effective_model,
                _gen_usage.get("input_tokens", 0),
                _gen_usage.get("output_tokens", 0),
            )
            models_cost.append(gen_cost)
        if models_cost:
            total_in = sum(m.input_tokens for m in models_cost)
            total_out = sum(m.output_tokens for m in models_cost)
            total_cost = sum(m.subtotal_usd for m in models_cost)
            token_usage = TokenUsage(
                models=models_cost,
                total_input_tokens=total_in,
                total_output_tokens=total_out,
                total_cost_usd=total_cost,
            )

    response = QueryResponse(
        query_type="adaptive",
        model_used=effective_model,
        response=adaptive_response,
        text_nodes=text_nodes,
        safety_warnings=safety_warnings,
        validation_warnings=validation_warnings,
        disclaimer=DISCLAIMER,
        cached=False,
        truncated=False,
        latency_ms=latency_ms,
        audit_id=audit_id,
        rewritten_query=rewritten_query if rewritten_query != request.query else None,
        fetch_sources=fetch_sources,
        token_usage=token_usage,
    )

    cache_data = response.model_dump()
    asyncio.create_task(
        cache_set(redis_client, request.query, query_type, effective_model, cache_data)
    )
    asyncio.create_task(
        semantic_cache_set(request.query, query_type, effective_model, cache_data)
    )

    await _enqueue_log(
        {
            "query": request.query,
            "query_type": query_type,
            "model_used": effective_model,
            "effective_model": effective_model,
            "prompt_mode": prompt_mode,
            "fetch_latency_ms": fetch_latency_ms,
            "response_json": cache_data,
            "latency_ms": latency_ms,
            "cached": False,
            "user_key_id": user_key_id,
        }
    )

    if user and user.id:
        asyncio.create_task(
            _log_search_history(user.id, request.query, query_type, cache_data)
        )

    return response


async def _revalidate_semantic_cache(
    request,
    query_type: str,
    cache_id: int,
    redis_client,
    user_key_id,
    user_llm_key,
    user_llm_provider,
    user=None,
) -> None:
    """
    Background SWR revalidation: re-run the pipeline for a stale cache entry
    and update the semantic cache entry with the fresh response.
    Runs as a fire-and-forget asyncio task.
    """
    try:
        fresh_response = await process_query(
            request,
            redis_client=redis_client,
            user_key_id=user_key_id,
            user=user,
        )
        await semantic_cache_revalidate(cache_id, fresh_response.model_dump())
        logger.debug("SWR revalidation complete for semantic cache id=%d", cache_id)
    except Exception:
        logger.debug("SWR revalidation failed for cache id=%d", cache_id, exc_info=True)
