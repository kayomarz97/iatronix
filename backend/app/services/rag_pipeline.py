import asyncio
import json
import logging
import re
import time

import openai
import orjson
import pybreaker
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import settings
from app.db.session import async_session
from app.models.query_log import QueryLog
from app.schemas.query import (
    ComparativeResponse,
    DegradedResponse,
    DiseaseResponse,
    DrugResponse,
    EvidenceResponse,
    GeneralResponse,
    ProcedureResponse,
    QueryRequest,
    QueryResponse,
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
from app.services.prompt_engine import build_prompt
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
            abstract = ab.get("abstract", "")[:500]
            _pmid = ab.get("pmid", "")
            _pmid_str = f" PMID {_pmid}" if _pmid else ""
            if title or abstract:
                parts.append(
                    f"[SOURCE: PubMed{_pmid_str}][condition_guideline]: {title} — {abstract}"
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

    if query_type == "drug" and fetched_data.drug_data:
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

    if query_type == "disease" and fetched_data.disease_data:
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

    if query_type == "procedure" and fetched_data.procedure_data:
        d = fetched_data.procedure_data
        hits = len(d.guideline_abstracts or []) + len(d.practice_guideline_abstracts or [])
        score = hits * 2
        if hits < 2:
            reasons.append("too few procedure guidelines")
        return score, score >= 4, reasons

    if query_type == "evidence" and fetched_data.evidence_data:
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

    return 0, False, ["unsupported query type or no fetched data"]


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
            response = await llm.ainvoke(prompt)
            return response.content

        return await _invoke()
    except pybreaker.CircuitBreakerError:
        logger.warning(f"Circuit breaker open for {provider}")
        return None
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
    except Exception:
        logger.error(f"LLM call failed for {model_id}", exc_info=True)
        return None


_CLAIM_FIELDS = {"loe", "cor", "source", "confidence", "value"}
_VALID_LOE = {"I", "II-1", "II-2", "II-3", "III"}
_VALID_COR = {"I", "IIa", "IIb", "III-no-benefit", "III-harm"}


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
                # Unsourced claims must NOT get Class I (strongest recommendation)
                obj["cor"] = "IIb" if not has_source else "IIa"

            # LOE↔COR consistency enforcement (patient safety)
            final_loe = obj["loe"]
            final_cor = obj.get("cor", "IIb")
            if final_loe == "III" and final_cor == "I":
                # LOE III (expert opinion) must never claim COR I (strongest)
                obj["cor"] = "IIb"
            elif final_loe == "I" and final_cor == "IIb":
                # LOE I (RCT) shouldn't be downgraded to IIb
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

    provider_for_request = user_llm_provider or get_provider(request.model_id)
    normalized_request_model = _normalize_model_for_provider(
        request.model_id or _default_model_for_provider(provider_for_request),
        provider_for_request,
        request.model_explicit,
    )

    query_intent = detect_intent(request.query)

    # Speculative type via rule-based classifier (sync, ~1ms) — used for parallel cache check
    speculative_type, _ = classify_query(request.query)

    # Run DSPy analysis and Redis cache check in parallel
    _dspy_result, _cache_prefetch = await asyncio.gather(
        _analyze_query_with_dspy(
            request.query,
            model_id=normalized_request_model,
            user_key=user_llm_key,
            user_provider=user_llm_provider,
        ),
        cache_get(redis_client, request.query, speculative_type, normalized_request_model),
        return_exceptions=True,
    )
    query_analysis = _dspy_result if not isinstance(_dspy_result, Exception) else None
    _speculative_cache = _cache_prefetch if not isinstance(_cache_prefetch, Exception) else None

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
    # source_mode: "ai" = full pipeline, "scraping" = API only (no vector), "pdfs" = vector only
    source_mode = getattr(request, "source_mode", "ai")
    use_api_fetch = settings.api_fetch_enabled and source_mode != "pdfs"
    use_vector = settings.vector_search_enabled and source_mode != "scraping"

    fetched_data: FetchedData | None = None
    vector_results = []
    routing = None
    retrieval_notes: list[str] = []

    tasks = {}
    if use_api_fetch:
        routing = route_query(
            request.query,
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
                ),
                timeout=settings.api_fetch_timeout_seconds + 1.0,
            )

    if use_vector:
        tasks["vector"] = vector_search(request.query)

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

    if use_api_fetch and fetched_data is not None:
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

    if settings.fail_closed_evidence_only and prompt_mode == "generate":
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

    # DSPy adaptive path
    dspy_error_message: str | None = None
    if settings.dspy_enabled and user_llm_key:
        try:
            import dspy as _dspy
            from app.services.dspy_lm import get_dspy_lm
            from app.services.dspy_modules import AdaptiveMedicalPipeline
            from app.schemas.query import (
                AdaptiveSection,
                AdaptiveResponse,
                AdaptiveBLUF,
            )

            for attempt in range(2):
                _lm = get_dspy_lm(
                    effective_model,
                    user_llm_key,
                    user_llm_provider or "anthropic",
                    depth="comprehensive",
                )
                with _dspy.context(lm=_lm):
                    _pipeline = AdaptiveMedicalPipeline()
                    _analysis, _dspy_resp = _pipeline(
                        query=request.query,
                        fetched_data=_summarize_fetched(
                            fetched_data,
                            query_type=query_type,
                            condition_context=condition_context,
                        )
                        if fetched_data
                        else "",
                        vector_results=_summarize_vectors(vector_results),
                        available_data_types=_describe_data(fetched_data)
                        if fetched_data
                        else "none",
                        query_type_hint=query_type,
                        condition_context_hint=condition_context or "",
                        pre_analysis=query_analysis,
                    )
                _resp_dict = orjson.loads(_dspy_resp.response_json)
                _adaptive_sparse = _adaptive_sparse_reasons(_resp_dict, query_type)
                if _adaptive_sparse and attempt == 0:
                    fetched_data, extra_notes = await _expand_retrieval_if_needed(
                        query=request.query,
                        query_type=query_type,
                        fetched_data=fetched_data,
                        entities=routing.entities if routing else (analysis_entities or []),
                        condition_context=condition_context,
                        response_focus=str(getattr(_analysis, "response_focus", "") or ""),
                    )
                    retrieval_notes.extend(
                        [f"DSPy sparse retry: {reason}" for reason in _adaptive_sparse]
                    )
                    retrieval_notes.extend(extra_notes)
                    continue
                if _adaptive_sparse:
                    raise ValueError(
                        "Adaptive response remained too sparse: "
                        + "; ".join(_adaptive_sparse)
                    )

                _sections = [AdaptiveSection(**s) for s in _resp_dict.get("sections", [])]
                # Enrich references: build AdaptiveReference objects and fill URLs from PMIDs
                _raw_refs = _resp_dict.get("references", [])
                from app.schemas.query import AdaptiveReference as _AdaptiveReference

                if _raw_refs and isinstance(_raw_refs[0], dict):
                    enrich_references({"references": _raw_refs}, fetched_data)
                    _references = [_AdaptiveReference(**r) for r in _raw_refs]
                else:
                    _references = [_AdaptiveReference(title=str(r)) for r in _raw_refs]
                try:
                    _bluf_data = orjson.loads(_dspy_resp.bluf_json)
                    _bluf = AdaptiveBLUF(**_bluf_data)
                except Exception:
                    _bluf = AdaptiveBLUF(headline=str(_dspy_resp.bluf_json))
                _adaptive = AdaptiveResponse(
                    query_type=query_type,
                    bluf=_bluf,
                    sections=_sections,
                    references=_references,
                    response_focus=_analysis.response_focus,
                    depth=_analysis.depth,
                    related_topics=list(_analysis.related_topics or []),
                )
                latency_ms = int((time.time() - start_time) * 1000)
                return QueryResponse(
                    query_type="adaptive",
                    model_used=effective_model,
                    response=_adaptive,
                    latency_ms=latency_ms,
                    disclaimer=DISCLAIMER,
                    validation_warnings=retrieval_notes,
                )
        except Exception as _dspy_err:
            dspy_error_message = str(_dspy_err)
            logger.warning(
                "DSPy path failed: %s", _dspy_err
            )

    if (
        settings.fail_closed_evidence_only
        and settings.dspy_enabled
        and user_llm_key
        and prompt_mode == "generate"
    ):
        latency_ms = int((time.time() - start_time) * 1000)
        warnings = list(retrieval_notes)
        if dspy_error_message:
            warnings.append(f"DSPy generation failed: {dspy_error_message}")
        warnings.append(
            "Fail-closed mode blocked fallback generation because it could rely on model knowledge beyond retrieved evidence."
        )
        return QueryResponse(
            query_type=query_type,
            model_used=effective_model,
            response=DegradedResponse(
                message="The adaptive evidence-only answer could not be generated safely.",
                suggestion="Try a narrower query with an exact entity name, or retry after reviewing the retrieved evidence sources.",
            ),
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
            validation_warnings=warnings,
        )

    # Build prompt (format-mode if API data available, generate-mode otherwise)
    prompt = build_prompt(
        request.query,
        query_type,
        fetched_data,
        vector_results,
        intent=query_intent,
        condition_context=condition_context,
    )

    # LLM call with retry
    _llm_t0 = time.perf_counter()
    try:
        raw_response = await _call_llm(
            effective_model,
            prompt,
            max_tokens=max_tokens,
            user_key=user_llm_key,
            user_provider=user_llm_provider,
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
            # Graceful degradation: no API key — return raw scraped data with warning
            latency_ms = int((time.time() - start_time) * 1000)
            raw_sources = {}
            if fetched_data:
                if fetched_data.drug_data:
                    d = fetched_data.drug_data
                    raw_sources["drug"] = {
                        "name": d.generic_name,
                        "brand": d.brand_name,
                        "source": d.data_source,
                        "indications": d.indications_raw,
                        "dosing": d.dosing_raw,
                        "contraindications": d.contraindications_raw,
                        "adverse_reactions": d.adverse_reactions_raw,
                    }
                if fetched_data.disease_data:
                    raw_sources["guidelines_count"] = len(
                        fetched_data.disease_data.guideline_abstracts or []
                    )
            resp = QueryResponse(
                query_type=query_type,
                model_used=effective_model,
                response=DegradedResponse(
                    message="AI formatting is unavailable — no API key configured. Showing raw data from medical databases. Please add your API key in Settings.",
                    suggestion="Add your Anthropic, OpenAI, or OpenRouter API key in Settings to enable AI-formatted responses.",
                ),
                disclaimer=(
                    "This is unformatted data from external medical databases. "
                    "It has not been reviewed or formatted by AI. Use clinical judgment."
                ),
                latency_ms=latency_ms,
            )
            # Log to search history even for degraded responses
            if user and user.id:
                asyncio.create_task(
                    _log_search_history(user.id, request.query, query_type, {})
                )
            return resp
        raise

    raw_response2: str | None = None
    if raw_response:
        parsed = parse_llm_json(raw_response)
    else:
        parsed = None

    # Retry once if call failed or response unparseable
    if parsed is None:
        logger.info("First LLM call failed or unparseable, retrying...")
        await asyncio.sleep(settings.llm_retry_backoff_seconds)
        try:
            raw_response2 = await _call_llm(
                effective_model,
                prompt,
                max_tokens=max_tokens,
                user_key=user_llm_key,
                user_provider=user_llm_provider,
            )
        except HTTPException as _retry_exc:
            if _retry_exc.status_code in (401, 429):
                raise
            raw_response2 = None
        if raw_response2:
            parsed = parse_llm_json(raw_response2)

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
        # Distinguish: LLM never responded vs responded but JSON unparseable
        llm_never_responded = raw_response is None and raw_response2 is None
        if llm_never_responded:
            msg = "LLM call failed — please verify your API key is valid in Settings."
            sug = "Go to Settings → LLM API Key and check that your key is saved correctly."
        else:
            msg = (
                "Failed to parse AI response. The model returned an unexpected format."
            )
            sug = "Try rephrasing your query. If the problem persists, try a different query type."
        return QueryResponse(
            query_type=query_type,
            model_used=effective_model,
            response=DegradedResponse(message=msg, suggestion=sug),
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
        )

    # Pydantic + semantic validation
    validated_data, validation_warnings = _validate_response(parsed, query_type)
    if validated_data is None:
        latency_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            query_type=query_type,
            model_used=effective_model,
            response=DegradedResponse(
                message="Response validation failed",
                suggestion="Try rephrasing your query",
            ),
            validation_warnings=validation_warnings,
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
        )

    # Sparse response retry — if LLM returned critically sparse content, retry once with
    # an expansion instruction. Only for disease/drug/comparative types.
    if settings.retry_on_sparse_enabled and query_type in (
        "disease",
        "drug",
        "comparative",
        "evidence",
        "procedure",
    ):
        is_sparse, sparse_reasons = _is_critically_sparse(validated_data, query_type)
        if is_sparse:
            logger.info(
                "Response critically sparse (%s) — retrying with expansion instruction",
                sparse_reasons,
            )
            expansion_suffix = (
                "\n\nIMPORTANT: Your previous response was critically sparse. "
                "You MUST expand these sections: " + ", ".join(sparse_reasons) + ". "
                "Meet ALL minimum entry counts. Use the FULL token budget. Do NOT truncate."
            )
            try:
                raw_expansion = await _call_llm(
                    effective_model,
                    prompt + expansion_suffix,
                    max_tokens=max_tokens,
                    user_key=user_llm_key,
                    user_provider=user_llm_provider,
                )
                if raw_expansion:
                    parsed_expansion = parse_llm_json(raw_expansion)
                    if parsed_expansion:
                        v2, _ = _validate_response(parsed_expansion, query_type)
                        if v2 is not None:
                            validated_data = v2
            except Exception:
                logger.debug(
                    "Sparse retry failed — keeping original response", exc_info=True
                )

    # Enrich references with deterministic URLs (no LLM guessing)
    # Must run BEFORE citation validation so URL warnings reflect final values
    try:
        enrich_references(validated_data, fetched_data)
    except Exception:
        logger.warning(
            "URL enrichment failed — references will have no URLs", exc_info=True
        )

    # Citation validation
    citation_warnings = validate_citations(validated_data, query_type)
    validation_warnings.extend(citation_warnings)

    # Safety check
    safety_warnings = check_safety(request.query, validated_data, query_type)

    # Drug linker
    text_nodes = process_text_nodes(validated_data, query_type)

    # Build typed response
    model_cls = RESPONSE_MODELS[query_type]
    typed_response = model_cls.model_validate(validated_data)

    latency_ms = int((time.time() - start_time) * 1000)

    # Warn user when response is AI-generated rather than sourced from databases
    if prompt_mode == "generate":
        validation_warnings.append(
            "This response was generated by AI without data from medical databases. "
            "Verify claims against authoritative sources before clinical use."
        )

    response = QueryResponse(
        query_type=query_type,
        model_used=effective_model,
        response=typed_response,
        text_nodes=text_nodes,
        safety_warnings=safety_warnings,
        validation_warnings=validation_warnings,
        disclaimer=DISCLAIMER,
        cached=False,
        truncated=False,
        latency_ms=latency_ms,
    )

    # Cache write (Redis exact + semantic pgvector — both fire-and-forget, B4)
    cache_data = response.model_dump()
    asyncio.create_task(
        cache_set(
            redis_client,
            request.query,
            query_type,
            effective_model,
            cache_data,
        )
    )
    asyncio.create_task(
        semantic_cache_set(request.query, query_type, effective_model, cache_data)
    )

    # Async log
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

    # Search history logging (fire-and-forget, non-blocking)
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
