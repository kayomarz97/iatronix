import asyncio
import json
import logging
import re
import time
from collections.abc import Callable, Awaitable

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
from app.services.provider_registry import get_registry
from app.services.providers import get_adapter
from app.services.keystore import get_keystore
from app.services.langgraph_search import run_search_graph
from app.services.article_registry import ArticleRegistry, build_article_registry
from app.services.evidence_floor import EvidenceFloorError, ensure_evidence, has_minimum_evidence
from app.services.stance_neutralizer import neutralize_query, StanceResult
from app.services.prompt_engine import (
    build_adaptive_messages,
    build_bluf_only_messages,
    build_section_messages,
)
from app.services.query_classifier import classify_query_llm, detect_intent
from app.services.safety_checker import check_safety
from app.services.url_builder import enrich_references, sanitize_response_pmids, is_safe_url
from app.services.source_router import route_query
from app.services.ranking import rank_article_list

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


def _extract_fetch_articles(fetched_data: "FetchedData") -> list:
    """Collect real article titles from fetched data to stream to the UI."""
    seen: set = set()
    out: list = []
    data_objects = [
        fetched_data.drug_data,
        fetched_data.disease_data,
        fetched_data.condition_data,
        fetched_data.procedure_data,
        fetched_data.evidence_data,
        fetched_data.comparative_evidence,
    ]
    if fetched_data.comparative_drug_data:
        data_objects.extend(fetched_data.comparative_drug_data)
    for obj in data_objects:
        if obj is None:
            continue
        for ab in (
            getattr(obj, "guideline_abstracts", None) or []
            + (getattr(obj, "systematic_review_abstracts", None) or [])
            + (getattr(obj, "clinical_trial_abstracts", None) or [])
        ):
            title = (ab.get("title") or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            out.append({
                "title": title,
                "journal": ab.get("journal") or "",
                "year": ab.get("year"),
                "pmid": ab.get("pmid") or "",
            })
            if len(out) >= 20:
                break
        if len(out) >= 20:
            break
    return out


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
        # Any populated field or evidence hit is sufficient — LLM notes quality
        return score, score >= 2, reasons

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
        # Any guideline/review/summary is sufficient
        return score, score >= 1, reasons

    if query_type == "procedure":
        if not fetched_data.procedure_data:
            return 0, False, ["data fetch timed out — no procedure data retrieved"]
        d = fetched_data.procedure_data
        hits = len(d.guideline_abstracts or []) + len(d.practice_guideline_abstracts or [])
        score = hits * 2
        # Any guideline hit is sufficient
        return score, score >= 1, reasons

    if query_type == "evidence":
        if not fetched_data.evidence_data:
            return 0, False, ["data fetch timed out — no evidence data retrieved"]
        d = fetched_data.evidence_data
        trials = len(d.clinical_trial_abstracts or [])
        reviews = len(d.systematic_review_abstracts or [])
        guidelines = len(d.guideline_abstracts or [])
        score = trials * 2 + reviews * 2 + guidelines
        # Even a single case report or trial is sufficient — LLM notes evidence quality
        return score, score >= 1, reasons

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
        # Any drug data or evidence hit is sufficient
        return score, score >= 2, reasons

    if query_type in ("complex", "general"):
        # Aggregate evidence across all sub-fetch results for complex queries
        total = 0
        d = fetched_data.drug_data
        if d and d.fetch_success:
            total += sum(1 for v in [d.indications_raw, d.dosing_raw, d.mechanism_raw] if v)
            total += len(d.guideline_abstracts or []) + len(d.systematic_review_abstracts or []) + len(d.clinical_trial_abstracts or [])
        c = fetched_data.condition_data
        if c and c.fetch_success:
            total += len(c.guideline_abstracts or []) + len(c.systematic_review_abstracts or [])
        e = fetched_data.evidence_data
        if e and e.fetch_success:
            total += len(e.clinical_trial_abstracts or []) + len(e.systematic_review_abstracts or []) + len(e.guideline_abstracts or [])
        for comorbid in (fetched_data.comorbidity_data or []):
            if comorbid and comorbid.fetch_success:
                total += len(comorbid.guideline_abstracts or []) + len(comorbid.systematic_review_abstracts or [])
        score = total
        if score < 1:
            reasons.append("no evidence retrieved for complex query")
        return score, score >= 1, reasons

    if query_type in {"drug", "disease", "procedure", "evidence", "comparative"}:
        return 0, False, ["data fetch timed out — no retrieval data available"]
    return 0, False, ["unsupported query type"]


def compute_evidence_confidence(
    fetched_data: "FetchedData | None",
    query_type: str,
) -> dict:
    """Return structured confidence level replacing binary 'insufficient evidence'.

    Returns dict with keys: confidence_level, evidence_count,
    top_study_types (list[str]), explanation (str).
    """
    if not fetched_data:
        return {
            "confidence_level": "low",
            "evidence_count": 0,
            "top_study_types": [],
            "explanation": "No data was retrieved for this query.",
        }

    def _count_study_types(abstracts: list) -> tuple[int, int, int, int]:
        """Return (guideline_count, review_count, rct_count, other_count)."""
        g = r = rc = other = 0
        for a in (abstracts or []):
            if not isinstance(a, dict):
                continue
            types_joined = " ".join(
                str(pt).lower()
                for pt in (a.get("pub_types") or a.get("publication_types") or [])
            )
            title_lower = (a.get("title") or "").lower()
            combined = types_joined + " " + title_lower
            if "guideline" in combined:
                g += 1
            elif "systematic review" in combined or "meta-analysis" in combined:
                r += 1
            elif "randomized controlled trial" in combined or " rct" in combined:
                rc += 1
            else:
                other += 1
        return g, r, rc, other

    g = r = rc = other = 0

    if query_type == "drug" and fetched_data.drug_data:
        d = fetched_data.drug_data
        all_abs = (d.guideline_abstracts or []) + (d.systematic_review_abstracts or []) + (d.clinical_trial_abstracts or [])
        g, r, rc, other = _count_study_types(all_abs)
    elif query_type == "disease" and fetched_data.disease_data:
        d = fetched_data.disease_data
        all_abs = (d.guideline_abstracts or []) + (d.systematic_review_abstracts or [])
        g, r, rc, other = _count_study_types(all_abs)
    elif query_type in {"evidence", "comparative"}:
        ev = fetched_data.evidence_data or fetched_data.comparative_evidence
        if ev:
            all_abs = (ev.guideline_abstracts or []) + (ev.systematic_review_abstracts or []) + (ev.clinical_trial_abstracts or [])
            g, r, rc, other = _count_study_types(all_abs)
    elif query_type == "procedure" and fetched_data.procedure_data:
        d = fetched_data.procedure_data
        all_abs = (d.guideline_abstracts or []) + (d.practice_guideline_abstracts or [])
        g, r, rc, other = _count_study_types(all_abs)

    total = g + r + rc + other
    strong = g + r + rc

    top_study_types: list[str] = []
    if g:
        top_study_types.append(f"{g} guideline(s)")
    if r:
        top_study_types.append(f"{r} systematic review(s)/meta-analysis")
    if rc:
        top_study_types.append(f"{rc} RCT(s)")
    if other:
        top_study_types.append(f"{other} other study(ies)")

    if total == 0:
        level = "low"
        explanation = "No relevant studies were retrieved for this query."
    elif total <= 2 and strong == 0:
        level = "low"
        explanation = f"Only {total} weak or non-specific study(ies) found."
    elif g >= 1 and strong >= 3:
        level = "strong"
        explanation = f"Supported by {', '.join(top_study_types)}."
    elif strong >= 1 and total >= 3:
        level = "high"
        explanation = f"Good evidence base: {', '.join(top_study_types)}."
    else:
        level = "moderate"
        explanation = f"Moderate evidence from {', '.join(top_study_types) or str(total) + ' studies'}."

    return {
        "confidence_level": level,
        "evidence_count": total,
        "top_study_types": top_study_types,
        "explanation": explanation,
    }


def _rank_fetched_abstracts(
    fetched_data: "FetchedData",
    entities: list[str],
    query_text: str,
) -> None:
    """Re-order all abstract lists in FetchedData by evidence quality score.

    Mutates fetched_data in-place. Called after fetch, before LLM synthesis.
    Ranking happens before _cap_abstracts budget limits, so best articles survive.
    Silent on any failure — pipeline continues with original ordering.
    """
    def _rerank(lst: list | None) -> list:
        if not lst:
            return lst or []
        try:
            return rank_article_list(lst, entities, query_text)
        except Exception:
            return lst

    try:
        if fetched_data.drug_data:
            d = fetched_data.drug_data
            d.guideline_abstracts = _rerank(d.guideline_abstracts)
            d.systematic_review_abstracts = _rerank(d.systematic_review_abstracts)
            d.clinical_trial_abstracts = _rerank(d.clinical_trial_abstracts)
        if fetched_data.disease_data:
            d = fetched_data.disease_data
            d.guideline_abstracts = _rerank(d.guideline_abstracts)
            d.systematic_review_abstracts = _rerank(d.systematic_review_abstracts)
        if fetched_data.condition_data:
            d = fetched_data.condition_data
            d.guideline_abstracts = _rerank(d.guideline_abstracts)
            d.systematic_review_abstracts = _rerank(d.systematic_review_abstracts)
        if fetched_data.evidence_data:
            ev = fetched_data.evidence_data
            ev.guideline_abstracts = _rerank(ev.guideline_abstracts)
            ev.systematic_review_abstracts = _rerank(ev.systematic_review_abstracts)
            ev.clinical_trial_abstracts = _rerank(ev.clinical_trial_abstracts)
        if fetched_data.comparative_evidence:
            ev = fetched_data.comparative_evidence
            ev.guideline_abstracts = _rerank(ev.guideline_abstracts)
            ev.systematic_review_abstracts = _rerank(ev.systematic_review_abstracts)
            ev.clinical_trial_abstracts = _rerank(ev.clinical_trial_abstracts)
        if fetched_data.procedure_data:
            d = fetched_data.procedure_data
            d.guideline_abstracts = _rerank(d.guideline_abstracts)
            d.practice_guideline_abstracts = _rerank(d.practice_guideline_abstracts)
    except Exception:
        logger.warning("_rank_fetched_abstracts failed", exc_info=True)


async def _expand_retrieval_if_needed(
    *,
    query: str,
    query_type: str,
    fetched_data: FetchedData | None,
    entities: list[str],
    condition_context: str | None,
    response_focus: str | None,
    rewritten_query: str | None = None,
    answer_entities: list[str] | None = None,
) -> tuple[FetchedData | None, list[str]]:
    if not settings.adaptive_second_pass_enabled or not fetched_data:
        return fetched_data, []

    score, sufficient, reasons = _retrieval_assessment(fetched_data, query_type)
    # complex and evidence always benefit from a second pass — bypass early exit
    if sufficient and query_type not in ("complex", "evidence"):
        return fetched_data, []

    notes = [f"initial retrieval score={score}", *reasons]
    follow_up_terms: list[str] = []
    _primary = rewritten_query or query
    for term in [_primary, response_focus]:
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
            _primary_term = rewritten_query or query
            evidence_tasks: list = [fetch_evidence_data(_primary_term)]
            # Secondary: resolved answer entities in context
            for ae in (answer_entities or [])[:1]:
                ae_clean = ae.strip()
                if ae_clean:
                    _ctx = condition_context or _primary_term
                    evidence_tasks.append(fetch_evidence_data(f"{ae_clean} {_ctx}"))
            extras = await asyncio.gather(*evidence_tasks, return_exceptions=True)
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
        elif query_type == "complex":
            # Always run for complex: fetch clinical scenario + answer-entity evidence in parallel
            _primary_term = rewritten_query or query
            tasks: list = [fetch_evidence_data(_primary_term)]
            # Fetch resolved answer entities (drug/procedure/concept) in clinical context
            for ae in (answer_entities or [])[:2]:
                ae_clean = ae.strip()
                if ae_clean:
                    # Combine answer entity + condition context for relevance (not isolated drug lookup)
                    _ctx = condition_context or _primary_term
                    tasks.append(fetch_evidence_data(f"{ae_clean} {_ctx}"))
            # Fetch disease/comorbidity data for each condition entity
            for ent in (entities or [])[:2]:
                if ent:
                    tasks.append(fetch_disease_data(ent))
            extras = await asyncio.gather(*tasks, return_exceptions=True)
            for extra in extras:
                if isinstance(extra, EvidenceFetchResult) and extra.fetch_success:
                    fetched_data.evidence_data = _enrich_evidence_result(
                        fetched_data.evidence_data, extra
                    )
                elif isinstance(extra, DiseaseFetchResult) and extra.fetch_success:
                    if not fetched_data.condition_data:
                        fetched_data.condition_data = extra
                    else:
                        fetched_data.comorbidity_data = [
                            *fetched_data.comorbidity_data,
                            extra,
                        ]
    except Exception:
        logger.warning("Second-pass retrieval expansion failed", exc_info=True)

    score2, sufficient2, reasons2 = _retrieval_assessment(fetched_data, query_type)
    notes.append(f"post-expansion retrieval score={score2}")
    notes.extend(reasons2)
    if not sufficient2:
        # Third-pass+: evidence floor tries progressive broadening (NCBI Bookshelf, MedlinePlus,
        # openFDA, broad PubMed) before giving up. Raises EvidenceFloorError if exhausted,
        # which propagates to process_query() for the structured no_evidence response.
        logger.info(
            "retrieval insufficient after second-pass (score=%d) — invoking evidence floor",
            score2,
        )
        notes.append("evidence floor invoked for additional broadening")
        fetched_data = await ensure_evidence(fetched_data, query, query_type)
        notes.append("evidence floor succeeded — proceeding in format mode")
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
    """Return a tier number for a model — higher = more capable.

    Registry-first (each model carries a `tier`); falls back to the legacy
    substring heuristic for model ids not present in the registry.
    """
    meta = get_registry().model_meta(model_id or "")
    if meta and meta.get("tier") is not None:
        return int(meta["tier"])
    m = (model_id or "").lower()
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
                use_cache_control = (provider == "anthropic")
                messages = [
                    SystemMessage(content=[
                        {
                            "type": "text",
                            "text": system_text,
                            **({"cache_control": {"type": "ephemeral"}} if use_cache_control else {}),
                        }
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

def _model_cost(model_id: str, inp: int, out: int) -> ModelCost:
    if "/" in model_id:
        # OpenRouter model — user's own credits, cost is opaque to us
        return ModelCost(
            model_id=model_id,
            input_tokens=inp,
            output_tokens=out,
            input_cost_usd=0.0,
            output_cost_usd=0.0,
            subtotal_usd=0.0,
        )
    from app.services.model_registry import pricing as _registry_pricing
    in_rate, out_rate = _registry_pricing(model_id)
    in_cost = round(inp / 1_000_000 * in_rate, 6)
    out_cost = round(out / 1_000_000 * out_rate, 6)
    return ModelCost(
        model_id=model_id,
        input_tokens=inp,
        output_tokens=out,
        input_cost_usd=in_cost,
        output_cost_usd=out_cost,
        subtotal_usd=round(in_cost + out_cost, 6),
    )


def _backfill_expert_opinion(section_data: dict) -> None:
    """When a claim has source='Expert opinion' but the section has real references,
    backfill the claim with the first reference's title and PMID to provide actual attribution.
    """
    content_items = section_data.get("content_items", [])
    references = section_data.get("references", [])

    if not references or not content_items:
        return

    first_ref = references[0]
    backfill_title = first_ref.get("title")
    backfill_pmid = first_ref.get("pmid")

    if not backfill_title:
        return

    for item in content_items:
        if isinstance(item, dict) and item.get("source") == "Expert opinion" and not item.get("pmid"):
            item["source"] = backfill_title
            if backfill_pmid:
                item["pmid"] = backfill_pmid


_EXPERT_SOURCE_KEYWORDS = frozenset(["expert", "consensus", "clinical opinion", "clinical consensus"])


def _is_expert_source(s: str) -> bool:
    """True if source string is any variant of expert opinion / consensus."""
    s_low = (s or "").lower()
    return any(k in s_low for k in _EXPERT_SOURCE_KEYWORDS)


def _normalize_consensus_sources(parsed: dict) -> None:
    """Normalize all expert/consensus source variants to canonical 'Expert opinion'.

    Must run before backfill so that _backfill_expert_opinion_global() can match them.
    Affects: references[].source, references[].title, content_items[].source
    """
    canonical = "Expert opinion"
    for ref in parsed.get("references", []):
        if isinstance(ref, dict):
            if _is_expert_source(ref.get("source", "")):
                ref["source"] = canonical
            if _is_expert_source(ref.get("title", "")):
                ref["title"] = canonical
    for section in parsed.get("sections", []):
        if not isinstance(section, dict):
            continue
        for item in section.get("content_items", []):
            if isinstance(item, dict) and _is_expert_source(item.get("source", "")):
                item["source"] = canonical


def _filter_expert_references(refs: list) -> list:
    """Drop Expert opinion refs with no URL when real linked refs exist."""
    real = [
        r for r in refs
        if isinstance(r, dict)
        and not _is_expert_source(r.get("source", "") or r.get("title", ""))
        and r.get("url")
    ]
    if not real:
        return refs  # nothing to replace with — keep as-is
    return [
        r for r in refs
        if not (
            isinstance(r, dict)
            and _is_expert_source(r.get("source", "") or r.get("title", ""))
            and not r.get("url")
        )
    ]


def _resolve_ref_tokens(parsed: dict, ref_map: dict, registry: "ArticleRegistry | None" = None) -> None:
    """Replace [REF_N] tokens with real article metadata. Must run BEFORE sanitize_response_pmids.

    Matches tokens in content_items.source and references.source/title fields.
    Hallucinated tokens ([REF_99] not in map) fall through to backfill.
    Marks registry articles used_inline=True when their token is consumed.
    """
    if not ref_map:
        return

    _TOKEN_FULL = re.compile(r'^\s*[\[\("]?\s*REF[\s_]?(\d+)\s*[\]\)"]?\s*[.;,]?\s*$', re.IGNORECASE)
    _TOKEN_INLINE = re.compile(r'\b\[?\(?"?\s*REF[\s_]?(\d+)(?![A-Za-z0-9])\s*"?\)?\]?', re.IGNORECASE)

    def _mark(key: str) -> None:
        if registry is not None:
            ra = registry.lookup_token(key)
            if ra is not None:
                ra.used_inline = True

    for section in parsed.get("sections", []):
        if not isinstance(section, dict):
            continue
        for item in section.get("content_items", []):
            if not isinstance(item, dict):
                continue
            src = (item.get("source") or "").strip()

            resolved_articles = []
            for m in _TOKEN_INLINE.finditer(src):
                key = f"REF_{m.group(1)}"
                art = ref_map.get(key)
                if art:
                    resolved_articles.append(art)

            if not resolved_articles:
                m_full = _TOKEN_FULL.match(src)
                if m_full:
                    key = f"REF_{m_full.group(1)}"
                    art = ref_map.get(key)
                    if art:
                        resolved_articles.append(art)
                        _mark(key)

            if resolved_articles:
                primary = resolved_articles[0]
                item["source"] = primary["title"]
                if primary.get("pmid"):
                    item["pmid"] = primary["pmid"]
                if primary.get("url"):
                    item["url"] = primary["url"]
                if len(resolved_articles) > 1:
                    item["additional_sources"] = [
                        {
                            "title": art["title"],
                            "source": art.get("source"),
                            "pmid": art.get("pmid"),
                            "url": art.get("url")
                        }
                        for art in resolved_articles[1:]
                    ]
                else:
                    item["additional_sources"] = []
            elif _TOKEN_INLINE.search(src) or _TOKEN_FULL.match(src):
                item["source"] = "__UNRESOLVED_TOKEN__"
                item["additional_sources"] = []

    # Resolve tokens in parsed["references"]
    for ref in parsed.get("references", []):
        if not isinstance(ref, dict):
            continue
        resolved_articles = []
        for field in ("source", "title"):
            val = (ref.get(field) or "").strip()
            for m in _TOKEN_INLINE.finditer(val):
                key = f"REF_{m.group(1)}"
                art = ref_map.get(key)
                if art and art not in resolved_articles:
                    resolved_articles.append(art)
            m_full = _TOKEN_FULL.match(val)
            if m_full:
                key = f"REF_{m_full.group(1)}"
                art = ref_map.get(key)
                if art and art not in resolved_articles:
                    resolved_articles.append(art)

        if resolved_articles:
            primary = resolved_articles[0]
            ref["title"] = primary["title"]
            ref["source"] = primary["source"]
            ref["pmid"] = primary.get("pmid")
            ref["url"] = primary.get("url")


def _best_article_for_claim(claim_text: str, articles: list[dict]) -> dict | None:
    """Score articles by token overlap with claim text (title + abstract prefix).

    Cheap O(n_articles × n_tokens) scoring. Tie-break by source priority.
    Returns the best-matching article, or None if no articles.
    """
    if not articles:
        return None

    SOURCE_PRIORITY = {
        "clinical_trial": 5,
        "systematic_review": 4,
        "guideline": 3,
        "rct": 5,
        "FDA": 2,
        "DailyMed": 2,
    }

    claim_tokens = set(re.findall(r'\b\w+\b', claim_text.lower()))
    if not claim_tokens:
        return articles[0]

    best_article = None
    best_score = -1

    for article in articles:
        article_text = f"{article.get('title', '')} {article.get('abstract', '')[:200]}".lower()
        article_tokens = set(re.findall(r'\b\w+\b', article_text))
        overlap = len(claim_tokens & article_tokens)
        source = article.get("source", "").lower()
        priority = next((p for label, p in SOURCE_PRIORITY.items() if label.lower() in source), 0)
        score = overlap * 10 + priority
        if score > best_score:
            best_score = score
            best_article = article

    return best_article or articles[0]


def _quarantine_sourceless_items(
    parsed: dict,
    fetched_data: "FetchedData | None" = None,
    registry: "ArticleRegistry | None" = None,
) -> None:
    """Demote (not drop) content_items lacking real grounding after backfill.

    For references without any ID (pmid/nct_id/doi/url), require a registry match
    (title-token Jaccard >= 0.5) to survive — this blocks hallucinated refs.
    If fetched_data is available (no live API failure), demote ungrounded claims to "Expert opinion"
    with low confidence. If no fetched_data, skip quarantine entirely to preserve training knowledge.
    """
    if not fetched_data:
        # No live API data; keep all content without aggressive filtering
        return

    for section in parsed.get("sections", []):
        if not isinstance(section, dict):
            continue
        items = section.get("content_items", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            has_real_source = bool((item.get("source") or "").strip()) and item.get("source") != "Expert opinion"
            has_url = bool(item.get("url"))
            has_pmid = bool(item.get("pmid"))
            if not (has_real_source or has_url or has_pmid):
                # Demote: set to expert opinion with low confidence
                item["source"] = "Expert opinion"
                item["confidence"] = "low"

    # Updated reference filter (v2): registry-anchored
    refs = parsed.get("references", [])
    filtered_refs = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        has_id = any(ref.get(k) for k in ("url", "pmid", "nct_id", "doi"))
        if has_id:
            # Has identifier — keep it
            filtered_refs.append(ref)
            continue
        # No identifier — require registry match (Jaccard >= 0.5) to survive
        if registry:
            ref_text = (ref.get("title") or "") + " " + (ref.get("source") or "")
            if registry.best_match_min_jaccard(ref_text, min_jaccard=0.5):
                filtered_refs.append(ref)
        # Else: drop ref (hallucinated without identifier AND no registry match)
    parsed["references"] = filtered_refs


def _backfill_expert_opinion_global(parsed: dict, fetched_data: "FetchedData | None" = None) -> None:
    """Replace 'Expert opinion' and empty sources in content_items + references with per-claim backfill.

    Per-claim resolution uses title similarity. Section-level keyword preference is kept as tie-breaker.
    Call AFTER _resolve_ref_tokens and sanitize_response_pmids.
    """
    from app.services.prompt_engine import build_ref_map

    ref_map = build_ref_map(fetched_data) if fetched_data else {}
    all_articles = list(ref_map.values())
    if not all_articles:
        return

    # Process content_items
    for section in parsed.get("sections", []):
        if not isinstance(section, dict):
            continue

        for item in section.get("content_items", []):
            if not isinstance(item, dict):
                continue
            src = (item.get("source") or "").strip()
            if src in ("", "Expert opinion", "__UNRESOLVED_TOKEN__") and not item.get("pmid"):
                claim_text = item.get("text", "")
                best = _best_article_for_claim(claim_text, all_articles)
                if best:
                    item["source"] = best["title"]
                    if best.get("pmid"):
                        item["pmid"] = best["pmid"]
                    if best.get("url"):
                        item["url"] = best["url"]

    # Extended: Process references — replace "Expert opinion" sources with real article data if available
    for ref in parsed.get("references", []):
        if not isinstance(ref, dict):
            continue
        src = (ref.get("source") or "").strip()
        if src == "Expert opinion" and not ref.get("pmid") and not ref.get("nct_id"):
            ref_text = (ref.get("title") or "") + " " + (ref.get("source") or "")
            best = _best_article_for_claim(ref_text, all_articles)
            if best:
                ref["source"] = best["title"]
                if best.get("pmid"):
                    ref["pmid"] = best["pmid"]
                if best.get("url"):
                    ref["url"] = best["url"]


def _title_rescue_pass(parsed: dict, registry: "ArticleRegistry") -> None:
    """Recover free-form titles emitted by non-Anthropic models.

    For each content_item whose source is non-empty, not a real authority,
    and has no PMID/url, attempt registry.best_match. Only mutates when a
    match is found. Marks the matched article used_inline=True.
    """
    if not registry or not registry.items:
        return
    for section in parsed.get("sections", []):
        if not isinstance(section, dict):
            continue
        for item in section.get("content_items", []):
            if not isinstance(item, dict):
                continue
            src = (item.get("source") or "").strip()
            if not src:
                continue
            if src in ("Expert opinion", "__UNRESOLVED_TOKEN__"):
                continue
            if item.get("pmid") or item.get("url"):
                continue
            ra = registry.lookup_id(title=src)
            if ra is None:
                ra = registry.best_match(item.get("text", "") + " " + src, source_hint=src)
            if ra is not None:
                item["source"] = ra.title
                if ra.pmid:
                    item["pmid"] = ra.pmid
                item["url"] = ra.url
                ra.used_inline = True


def _backfill_from_registry(parsed: dict, registry: "ArticleRegistry") -> None:
    """Replace empty / Expert-opinion / unresolved-token sources via registry.best_match."""
    if not registry or not registry.items:
        return
    for section in parsed.get("sections", []):
        if not isinstance(section, dict):
            continue
        for item in section.get("content_items", []):
            if not isinstance(item, dict):
                continue
            src = (item.get("source") or "").strip()
            if src not in ("", "Expert opinion", "__UNRESOLVED_TOKEN__"):
                continue
            if item.get("pmid"):
                continue
            ra = registry.best_match(item.get("text", ""), source_hint=src)
            if ra is not None:
                item["source"] = ra.title
                if ra.pmid:
                    item["pmid"] = ra.pmid
                item["url"] = ra.url
                ra.used_inline = True


def _inject_fetched_refs(fetched_data) -> list[dict]:
    """Build reference dicts from ALL fetched article data (no cap).

    Ensures complete reference list (LLM-cited + all fetched articles).
    Guaranteed real PMIDs/URLs — no hallucination possible.
    """
    refs: list[dict] = []
    if fetched_data is None:
        return refs

    for data_attr in ("drug_data", "disease_data", "procedure_data", "evidence_data", "condition_data"):
        obj = getattr(fetched_data, data_attr, None)
        if obj is None:
            continue
        for list_attr in ("guideline_abstracts", "systematic_review_abstracts",
                           "clinical_trial_abstracts", "practice_guideline_abstracts"):
            for abstract in getattr(obj, list_attr, None) or []:
                if not isinstance(abstract, dict):
                    continue
                title = abstract.get("title", "").strip()
                pmid = abstract.get("pmid")
                nct_id = abstract.get("nct_id")
                if not title:
                    continue
                refs.append({
                    "title": title,
                    "source": abstract.get("journal") or abstract.get("collective_name") or "PubMed",
                    "pmid": str(pmid) if pmid else None,
                    "nct_id": nct_id,
                    "year": abstract.get("year"),
                    "url": (
                        f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                        if pmid else
                        f"https://clinicaltrials.gov/study/{nct_id}"
                        if nct_id else None
                    ),
                })
    return refs


def _is_grounded_ref(llm_ref: dict, ref_map_index: dict, fetched_articles: list[dict] | None = None) -> bool:
    """Check if LLM-supplied ref has evidence of grounding in fetched data.

    Tiered check:
    1. PMID/NCT/DOI exact match → grounded
    2. Title token overlap >= 0.5 → grounded
    3. Source authority match with fetched articles present → grounded by association
    4. Otherwise → not grounded (but claim text may still be backfilled)
    """
    pmid = str(llm_ref.get("pmid") or "").strip()
    nct = (llm_ref.get("nct_id") or "").strip().upper()
    doi = (llm_ref.get("doi") or "").strip().lower()
    title = (llm_ref.get("title") or "").strip()
    title_norm = re.sub(r'\W+', ' ', title).strip().lower()
    source = (llm_ref.get("source") or "").strip().lower()

    # Tier 1: ID exact match
    if pmid and pmid in ref_map_index["pmids"]:
        return True
    if nct and nct in ref_map_index["ncts"]:
        return True
    if doi and doi in ref_map_index["dois"]:
        return True

    # Tier 2: Title token overlap >= 0.5
    if title_norm and fetched_articles:
        ref_tokens = set(re.findall(r'\b\w+\b', title_norm))
        if ref_tokens:
            for article in fetched_articles:
                art_text = f"{article.get('title', '')} {article.get('abstract', '')[:200]}".lower()
                art_tokens = set(re.findall(r'\b\w+\b', art_text))
                if art_tokens:
                    overlap = len(ref_tokens & art_tokens) / len(ref_tokens | art_tokens)
                    if overlap >= 0.30:
                        return True

    # Tier 3: Authority source with fetched articles present
    if source and fetched_articles:
        known_authorities = {"pubmed", "nice", "fda", "dailymed", "clinicaltrials", "rxnorm", "medlineplus"}
        for authority in known_authorities:
            if authority in source:
                return True

    return False


def _build_complete_references(llm_refs: list, fetched_data) -> list:
    """Merge LLM-cited refs with ALL fetched articles + NICE + FDA, deduped by PMID/title.

    LLM refs are validated against fetched_data; hallucinations are dropped.
    Ensures the response shows every source consulted, not just what the LLM chose to mention.
    """
    from app.services.prompt_engine import build_ref_map

    seen_pmids: set[str] = set()
    seen_titles: set[str] = set()
    result: list[dict] = []

    # Build ref_map_index for grounding validation
    ref_map_index = {"pmids": set(), "ncts": set(), "dois": set(), "titles": set()}
    fetched_articles_list: list[dict] = []
    if fetched_data:
        ref_map = build_ref_map(fetched_data)
        fetched_articles_list = list(ref_map.values())
        for art in fetched_articles_list:
            pmid = str(art.get("pmid") or "").strip()
            if pmid:
                ref_map_index["pmids"].add(pmid)
            nct = (art.get("nct_id") or "").strip().upper()
            if nct:
                ref_map_index["ncts"].add(nct)
            doi = (art.get("doi") or "").strip().lower()
            if doi:
                ref_map_index["dois"].add(doi)
            title_norm = re.sub(r'\W+', ' ', (art.get("title") or "")).strip().lower()
            if title_norm:
                ref_map_index["titles"].add(title_norm)

    # Phase 1: keep grounded LLM-cited refs, build URL from PMID/NCT if missing
    for r in llm_refs:
        if not isinstance(r, dict):
            continue
        if fetched_data and not _is_grounded_ref(r, ref_map_index, fetched_articles_list):
            continue
        pmid = str(r.get("pmid") or "").strip()
        nct_id = str(r.get("nct_id") or "").strip()
        title = (r.get("title") or "").strip().lower()
        if pmid:
            seen_pmids.add(pmid)
        if title:
            seen_titles.add(title)
        if not r.get("url"):
            if pmid and pmid.isdigit():
                r["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            elif nct_id and nct_id.isdigit():
                r["url"] = f"https://clinicaltrials.gov/study/{nct_id}"
        result.append(r)

    if fetched_data is None:
        return result

    # Phase 2: append ALL fetched abstracts not already cited
    for data_attr in ("drug_data", "disease_data", "procedure_data", "evidence_data", "condition_data"):
        obj = getattr(fetched_data, data_attr, None)
        if obj is None:
            continue
        for list_attr in ("guideline_abstracts", "systematic_review_abstracts",
                          "clinical_trial_abstracts", "practice_guideline_abstracts"):
            for abstract in getattr(obj, list_attr, None) or []:
                if not isinstance(abstract, dict):
                    continue
                pmid = (abstract.get("pmid") or "").strip()
                if pmid:
                    pmid = str(pmid)
                title = (abstract.get("title") or "").strip()
                if not title:
                    continue
                title_lower = title.lower()
                # Skip if already in LLM refs
                if (pmid and pmid in seen_pmids) or (title_lower in seen_titles):
                    continue
                if pmid:
                    seen_pmids.add(pmid)
                seen_titles.add(title_lower)
                nct_id = abstract.get("nct_id")
                result.append({
                    "title": title,
                    "source": abstract.get("journal") or abstract.get("collective_name") or "PubMed",
                    "pmid": pmid or None,
                    "nct_id": nct_id,
                    "year": abstract.get("year"),
                    "url": (
                        f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                        if pmid else
                        f"https://clinicaltrials.gov/study/{nct_id}"
                        if nct_id else None
                    ),
                })

    # Phase 3: append NICE recommendations from all data objects
    for data_attr in ("drug_data", "disease_data", "evidence_data", "condition_data"):
        obj = getattr(fetched_data, data_attr, None)
        if obj is None:
            continue
        for rec in getattr(obj, "nice_recommendations", None) or []:
            if not isinstance(rec, dict):
                continue
            title = (rec.get("title") or "").strip()
            url = rec.get("url", "")
            if not title or title.lower() in seen_titles:
                continue
            seen_titles.add(title.lower())
            result.append({
                "title": title,
                "source": "NICE",
                "pmid": None,
                "year": rec.get("year"),
                "url": url if is_safe_url(url) else None,
            })

    # Phase 4: append FDA/DailyMed label as a single reference
    drug_obj = getattr(fetched_data, "drug_data", None)
    if drug_obj:
        label_url = getattr(drug_obj, "label_url", None)
        drug_name = getattr(drug_obj, "brand_name", None) or getattr(drug_obj, "generic_name", None)
        if label_url and drug_name:
            title = f"{drug_name} — FDA Label"
            if title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                result.append({
                    "title": title,
                    "source": "FDA / DailyMed",
                    "pmid": None,
                    "year": None,
                    "url": label_url if is_safe_url(label_url) else None,
                })

    return result


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


def _extract_history_summary(result: dict, query_type: str) -> str:
    """Extract a readable summary from the full response for search history."""
    try:
        response = result.get("response", {})
        if isinstance(response, dict):
            bluf = response.get("bluf", {})
            if isinstance(bluf, dict) and bluf.get("headline"):
                return f"[{query_type}] {bluf['headline'][:400]}"
            msg = response.get("message", "")
            if msg:
                return f"[{query_type}] {msg[:400]}"
        return f"[{query_type}] Query processed"
    except Exception:
        return f"[{query_type}] Query processed"


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
            summary = _extract_history_summary(result, query_type) if result else ""
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
    """Provider's default model from the registry (anthropic/Haiku as last resort)."""
    reg = get_registry()
    dm = reg.default_model(provider) if provider else None
    return dm or reg.default_model("anthropic") or settings.model_haiku


def _normalize_model_for_provider(
    model_id: str,
    provider: str | None,
    model_explicit: bool,
) -> str:
    """Resolve the effective model id for a provider.

    Delegates to the adapter's registry-driven ``resolve_model`` (which replaces
    the old per-provider ``"/"`` heuristics with a single ownership rule and
    preserves BYOK passthrough for unknown model ids).
    """
    reg = get_registry()
    if provider and provider in reg.allowed_providers():
        return get_adapter(provider).resolve_model(model_id)
    if model_explicit:
        return model_id
    return model_id or reg.default_model("anthropic") or settings.model_haiku


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


async def _analyze_and_expand_query(
    query: str,
    *,
    model_id: str,
    user_key: str | None,
    user_provider: str | None,
) -> dict | None:
    """Single Haiku call: rewrites query + entity extraction + PubMed MeSH term generation.

    Replaces _analyze_query_with_dspy() + _rewrite_query() with one call.
    Returns None on ANY failure — caller falls back to the legacy individual calls.
    Never raises; all exceptions are caught and logged.
    """
    if not settings.pubmed_expansion_enabled:
        return None
    import json as _json

    _prompt = (
        "You are a medical search specialist and clinical query analyst. "
        "Return ONLY valid JSON — no markdown fences, no explanation.\n"
        "\n"
        "EXAMPLE INPUT: metformin ckd dose\n"
        "EXAMPLE OUTPUT:\n"
        "{\n"
        '  "rewritten_query": "metformin chronic kidney disease dosing",\n'
        '  "query_type": "evidence",\n'
        '  "intent": "drug_dosing",\n'
        '  "entities": ["metformin", "chronic kidney disease"],\n'
        '  "condition_context": "chronic kidney disease",\n'
        '  "response_focus": "metformin dosing adjustments and safety in chronic kidney disease",\n'
        '  "related_topics": ["GFR thresholds", "lactic acidosis risk", "KDIGO guidelines", "renal dose adjustment"],\n'
        '  "answer_entities": ["metformin", "renal dose adjustment"],\n'
        '  "search_variants": [\n'
        '    "metformin chronic kidney disease dosing",\n'
        '    "metformin CKD renal dose adjustment",\n'
        '    "metformin kidney disease"\n'
        '  ],\n'
        '  "pubmed_terms": {\n'
        '    "guideline": [\n'
        '      "Metformin[MeSH] AND Renal Insufficiency, Chronic[MeSH] AND (Practice Guideline[pt] OR Guideline[pt])",\n'
        '      "metformin[Title/Abstract] AND chronic kidney disease[Title/Abstract] AND (guideline OR recommendation)"\n'
        '    ],\n'
        '    "review": [\n'
        '      "Metformin[MeSH] AND Renal Insufficiency, Chronic[MeSH] AND (Systematic Review[pt] OR Meta-Analysis[pt])",\n'
        '      "metformin[Title/Abstract] AND CKD[Title/Abstract] AND (systematic review OR meta-analysis)"\n'
        '    ],\n'
        '    "trial": [\n'
        '      "Metformin[MeSH] AND Renal Insufficiency, Chronic[MeSH] AND (Randomized Controlled Trial[pt])",\n'
        '      "metformin[Title/Abstract] AND kidney disease[Title/Abstract] AND (dose OR dosing OR safety)"\n'
        '    ],\n'
        '    "journal_filter": "\\"Kidney International\\"[Journal] OR \\"American Journal of Kidney Diseases\\"[Journal] OR \\"Clinical Journal of the American Society of Nephrology\\"[Journal]"\n'
        '  }\n'
        "}\n"
        "\n"
        "EXAMPLE INPUT: drug of choice for CKD with T2DM to reduce blood sugar\n"
        "EXAMPLE OUTPUT:\n"
        "{\n"
        '  "rewritten_query": "drug of choice for chronic kidney disease with type 2 diabetes mellitus to reduce blood glucose",\n'
        '  "query_type": "complex",\n'
        '  "intent": "treatment",\n'
        '  "entities": ["chronic kidney disease", "type 2 diabetes mellitus"],\n'
        '  "condition_context": "chronic kidney disease, type 2 diabetes mellitus",\n'
        '  "response_focus": "SGLT2 inhibitors such as empagliflozin are preferred in CKD with T2DM due to renoprotective and glycemic benefits per KDIGO 2022 and ADA guidelines.",\n'
        '  "related_topics": ["eGFR thresholds", "CREDENCE trial", "DAPA-CKD trial", "KDIGO 2022", "renoprotection", "HbA1c targets in CKD"],\n'
        '  "answer_entities": ["SGLT2 inhibitors", "empagliflozin", "dapagliflozin"],\n'
        '  "patient_context": {\n'
        '    "age": null,\n'
        '    "renal": "eGFR 30 (CKD stage 3b)",\n'
        '    "hepatic": null,\n'
        '    "weight": null,\n'
        '    "pregnancy": null,\n'
        '    "concurrent_drugs": [],\n'
        '    "other_factors": []\n'
        '  },\n'
        '  "search_variants": [\n'
        '    "chronic kidney disease type 2 diabetes mellitus glycemic management drug choice",\n'
        '    "CKD T2DM antidiabetic therapy guidelines",\n'
        '    "diabetes kidney disease treatment"\n'
        '  ],\n'
        '  "pubmed_terms": {\n'
        '    "guideline": [\n'
        '      "Renal Insufficiency, Chronic[MeSH] AND Diabetes Mellitus, Type 2[MeSH] AND (Practice Guideline[pt] OR Guideline[pt])",\n'
        '      "Renal Insufficiency, Chronic[MeSH] AND Diabetes Mellitus, Type 2[MeSH] AND Sodium-Glucose Transporter 2 Inhibitors[MeSH] AND (Practice Guideline[pt] OR Guideline[pt])"\n'
        '    ],\n'
        '    "review": [\n'
        '      "Renal Insufficiency, Chronic[MeSH] AND Diabetes Mellitus, Type 2[MeSH] AND (Systematic Review[pt] OR Meta-Analysis[pt])",\n'
        '      "Renal Insufficiency, Chronic[MeSH] AND Diabetes Mellitus, Type 2[MeSH] AND Sodium-Glucose Transporter 2 Inhibitors[MeSH] AND (Systematic Review[pt] OR Meta-Analysis[pt])"\n'
        '    ],\n'
        '    "trial": [\n'
        '      "Renal Insufficiency, Chronic[MeSH] AND Diabetes Mellitus, Type 2[MeSH] AND (Randomized Controlled Trial[pt])",\n'
        '      "Renal Insufficiency, Chronic[MeSH] AND Diabetes Mellitus, Type 2[MeSH] AND Sodium-Glucose Transporter 2 Inhibitors[MeSH] AND (Randomized Controlled Trial[pt])"\n'
        '    ],\n'
        '    "journal_filter": "\\"Kidney International\\"[Journal] OR \\"Journal of the American Society of Nephrology\\"[Journal] OR \\"Diabetes Care\\"[Journal]"\n'
        '  }\n'
        "}\n"
        "\n"
        "RULES (follow exactly):\n"
        "1. rewritten_query: Fix all typos, expand all medical abbreviations (CKD→chronic kidney disease, "
        "HTN→hypertension, HF→heart failure, MI→myocardial infarction, T2DM→type 2 diabetes mellitus, "
        "COPD→chronic obstructive pulmonary disease, SGLT2→sodium-glucose cotransporter-2, "
        "ALL→acute lymphoblastic leukemia, AML→acute myeloid leukemia, CLL→chronic lymphocytic leukemia, "
        "CML→chronic myeloid leukemia, NHL→non-Hodgkin lymphoma, HL→Hodgkin lymphoma, "
        "MM→multiple myeloma, HCC→hepatocellular carcinoma, GBM→glioblastoma multiforme, "
        "NSCLC→non-small cell lung cancer, SCLC→small cell lung cancer, RCC→renal cell carcinoma, etc.), "
        "keep clinical intent exactly the same.\n"
        "2. intent: classify as ONE of: treatment | diagnosis | drug_dosing | drug_safety | "
        "drug_comparison | guideline | side_effect | contraindication | prognosis | general. "
        "Use drug_dosing when dose/dosing/mg is mentioned. Use drug_comparison for vs/versus/compare. "
        "Use guideline when guidelines/recommendations/protocol is mentioned. Default to treatment.\n"
        "3. entities: SHORT CLINICAL TERMS ONLY — e.g. [\"metformin\", \"chronic kidney disease\"], never a full sentence.\n"
        "4. search_variants: exactly 3 strings — [full rewritten query, abbreviated keyword form, condition-focused short form]. "
        "All three variants MUST preserve every disease/condition named in the query. "
        "NEVER replace disease/condition context with the resolved drug or therapy name.\n"
        "5. pubmed_terms strings: valid PubMed queries using [MeSH], [Title/Abstract], AND/OR, [pt] filters. "
        "CRITICAL: every pubmed_terms string MUST include ALL named diseases and clinical conditions from the query as MeSH or Title/Abstract anchors. "
        "NEVER build pubmed_terms solely around a resolved drug/therapy name — always anchor to the clinical scenario. "
        "Include the resolved answer (drug, procedure, or medical concept) as a second string in ALL three categories (guideline, review, trial) alongside the condition-anchored first string.\n"
        "6. journal_filter: 2-4 top peer-reviewed journals for this topic joined with OR.\n"
        "7. Do NOT include date ranges in pubmed_terms (added automatically).\n"
        "8. query_type: classify using these rules in order:\n"
        "   - 'comparative': ONLY when exactly two entities are explicitly being compared.\n"
        "   - 'procedure': ONLY for pure step-by-step technique queries with no other clinical context.\n"
        "   - 'drug': ONLY for a single pharmaceutical agent with no disease/condition context.\n"
        "   - 'disease': ONLY for a single disease/condition with no drug or treatment named.\n"
        "   - 'evidence': drug-in-condition queries, timing/management decisions, postoperative care, safety/efficacy questions.\n"
        "   - 'complex': everything else — multiple entities, comorbidities, broad questions, unclear queries.\n"
        "   NEVER output 'general'. Default to 'complex' when uncertain.\n"
        "9. response_focus: Write a direct clinical answer to the user's question in 1-2 sentences. "
        "This is used as the BLUF (Bottom Line Up Front). Start with the answer (e.g., 'Metformin should be "
        "dose-reduced when eGFR is 30-45 mL/min'), not background information.\n"
        "10. answer_entities: list of 1-3 short medical terms that ARE the answer to the query "
        "(the resolved drug, procedure, diagnostic test, or medical concept). Empty list [] if the answer "
        "cannot be resolved to a specific entity (e.g., 'management of CKD' has no single answer entity). "
        "These are used to fetch specific evidence on the resolved answer, separate from the clinical scenario search.\n"
        "11. patient_context: for complex queries, extract ALL clinical modifiers from the query that affect dosing or drug choice:\n"
        "    - age: numerical age or population (pediatric <18, elderly ≥65)\n"
        "    - renal: any CrCl/GFR/creatinine value, dialysis, ESRD, CKD stage\n"
        "    - hepatic: Child-Pugh class, cirrhosis, liver failure grade\n"
        "    - weight: body weight in kg or BMI if mentioned\n"
        "    - pregnancy: pregnant/lactating/trimester if mentioned\n"
        "    - concurrent_drugs: ALL named medications other than the primary drug (not diseases)\n"
        "    - other_factors: any other population modifiers (transplant, immunocompromised, ICU)\n"
        "    Leave null/empty-list if not mentioned. For non-complex queries, output {}.\n"
        "12. Output ONLY JSON — no markdown, no backticks, no explanation.\n"
        "\n"
        f"Query: {query}"
    )
    # NOTE: _call_llm splits on "\nQuery: " — static instruction above gets cached, query does not.
    try:
        raw = await _call_llm(
            model_id, _prompt, max_tokens=512,
            user_key=user_key, user_provider=user_provider,
        )
        if not raw:
            return None

        # Strip markdown fences — some models wrap JSON despite instructions
        clean = raw.strip()
        if clean.startswith("```"):
            parts = clean.split("```")
            # parts[0]="" parts[1]="json\n{...}" parts[2]=""  OR  parts[1]="{...}"
            inner = parts[1] if len(parts) >= 2 else clean
            clean = inner.lstrip("json").lstrip("JSON").strip()

        data = _json.loads(clean)

        # Validate required keys exist before trusting the response
        # pubmed_terms excluded — it's search enrichment, not classification
        required_keys = {"rewritten_query", "query_type", "entities"}
        if not required_keys.issubset(data.keys()):
            logger.warning(
                "_analyze_and_expand_query: missing keys %s — falling back",
                required_keys - data.keys(),
            )
            return None

        # pubmed_terms: use LLM-provided value if valid, else construct minimal fallback
        pt = data.get("pubmed_terms", {})
        if not isinstance(pt, dict) or not any(pt.get(k) for k in ("guideline", "review", "trial")):
            rq = (data.get("rewritten_query") or query).strip()
            data["pubmed_terms"] = {
                "guideline": [
                    f"{rq}[Title/Abstract] AND (Practice Guideline[pt] OR Guideline[pt])"
                ],
                "review": [
                    f"{rq}[Title/Abstract] AND (Systematic Review[pt] OR Meta-Analysis[pt])"
                ],
                "trial": [
                    f"{rq}[Title/Abstract] AND (Randomized Controlled Trial[pt])"
                ],
                "journal_filter": "",
            }

        # Sanitize entities using existing helper
        data["entities"] = _sanitize_entities(data.get("entities") or [])
        # Normalize condition_context: empty string → None
        data["condition_context"] = (data.get("condition_context") or "").strip() or None

        # New fields — safe defaults if LLM omits them
        valid_intents = {
            "treatment", "diagnosis", "drug_dosing", "drug_safety", "drug_comparison",
            "guideline", "side_effect", "contraindication", "prognosis", "general",
        }
        raw_intent = str(data.get("intent") or "general").strip().lower()
        data["intent"] = raw_intent if raw_intent in valid_intents else "general"

        raw_variants = data.get("search_variants")
        if isinstance(raw_variants, list) and raw_variants:
            data["search_variants"] = [str(v).strip() for v in raw_variants if str(v).strip()][:4]
        else:
            # Safe fallback: use rewritten_query as only variant
            data["search_variants"] = [data["rewritten_query"]]

        return data

    except _json.JSONDecodeError as e:
        logger.warning("_analyze_and_expand_query: JSON parse failed (%s) — falling back", e)
        return None
    except Exception as e:
        logger.warning("_analyze_and_expand_query: unexpected error (%s) — falling back", e)
        return None


def _dedup_references(refs: list) -> list:
    """Deduplicate reference dicts by title+pmid key."""
    seen: set[str] = set()
    out = []
    for r in refs:
        if not isinstance(r, dict):
            continue
        key = f"{r.get('title', '')}|{r.get('pmid', '')}"
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


async def _call_llm_simple(
    llm,
    provider: str,
    static_system: str,
    data_block: str,
    user_text: str,
    dynamic_system: str = "",
    model_id: str | None = None,
) -> tuple[str | None, dict]:
    """Non-streaming single LLM call. Returns (raw text or None, usage dict).

    Accepts either the old 3-part (static_system, data_block, user_text) or new 4-part
    (static_system, dynamic_system, data_block, user_text) interface — dynamic_system defaults
    to "" for backward-compat callers.

    Anthropic: cache_control on static_system (1h TTL) + data_block (5min ephemeral);
               dynamic_system (varies per call) follows without cache_control.
    Cerebras/others: concatenate in stable order (static → data → dynamic) for auto-cache prefix match.
    """
    from app.services.providers import get_adapter, PromptBlocks

    try:
        blocks = PromptBlocks(
            static_system=static_system,
            dynamic_system=dynamic_system,
            data_block=data_block,
            user_text=user_text,
        )
        # Caching is encapsulated per provider: Anthropic emits cache_control blocks
        # (gated on the model token-floor); auto-prefix providers concat static->data->
        # dynamic. The pipeline no longer branches on provider name here.
        msgs = get_adapter(provider).assemble_messages(blocks, model_id=model_id)

        result = await llm.ainvoke(msgs)
        usage = getattr(result, "usage_metadata", None) or {}
        if not usage:
            raw = getattr(result, "usage", None) or {}
            usage = {
                "input_tokens": raw.get("prompt_tokens", 0),
                "output_tokens": raw.get("completion_tokens", 0),
            }
        _token_details = usage.get("input_token_details") or {}
        cache_read = _token_details.get("cache_read", 0)
        cache_write = _token_details.get("cache_creation", 0)
        # Also check Cerebras-style cached_tokens
        _prompt_details = {}
        if hasattr(result, "response_metadata"):
            _prompt_details = (result.response_metadata or {}).get("usage", {}).get("prompt_tokens_details", {}) or {}
        cerebras_cached = _prompt_details.get("cached_tokens", 0)
        if cache_read or cerebras_cached:
            logger.info("[cache] read=%d cerebras_cached=%d", cache_read, cerebras_cached)
        elif cache_write:
            logger.info("[cache] write=%d", cache_write)
        return (
            result.content if isinstance(result.content, str) else None,
            {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_creation_input_tokens": cache_write,
                "cache_read_input_tokens": cache_read,
            },
        )
    except Exception as exc:
        logger.warning("_call_llm_simple failed: %s", exc)
        return None, {}


async def _run_parallel_pipeline(
    *,
    query: str,
    query_type: str,
    fetched_data,
    vector_results,
    effective_model: str,
    user_llm_key,
    user_llm_provider,
    condition_context: str | None,
    comparative_is_drug: bool,
    structured_callback,
    use_chat_service: bool = False,
) -> dict | None:
    """Two-phase parallel generation. Returns parsed dict compatible with AdaptiveResponse or None."""
    provider = user_llm_provider or get_provider(effective_model)

    if query_type == "complex":
        from app.services.prompt_engine import (
            build_complex_bluf_messages,
            build_complex_section_messages,
        )
        # Resolve drug + primary disease from fetched_data (set by source_router).
        drug = (fetched_data.drug_data.drug_name if fetched_data and fetched_data.drug_data else "")
        primary_disease = (
            fetched_data.condition_data.disease_name
            if fetched_data and fetched_data.condition_data
            else (condition_context or "")
        )
        comorbidity_list = [
            getattr(c, "disease_name", "") for c in (getattr(fetched_data, "comorbidity_data", []) or [])
            if getattr(c, "disease_name", "")
        ]
        bluf_static, bluf_dynamic, bluf_data, bluf_user = build_complex_bluf_messages(
            query=query,
            drug=drug,
            primary_disease=primary_disease,
            comorbidity_list=comorbidity_list,
            patient_context=getattr(fetched_data, "patient_context", {}) if fetched_data else {},
            fetched_data=fetched_data,
            vector_results=vector_results,
        )
    else:
        bluf_static, bluf_dynamic, bluf_data, bluf_user = build_bluf_only_messages(
            query=query,
            query_type=query_type,
            fetched_data=fetched_data,
            vector_results=vector_results,
            condition_context=condition_context,
            comparative_is_drug=comparative_is_drug,
        )
    _is_fallback = False
    if use_chat_service and user_llm_provider == "openrouter":
        from app.services.chat_service import chat_with_fallback
        from langchain_core.messages import HumanMessage, SystemMessage as _SM

        _combined_bluf_sys = bluf_static + ("\n\n" + bluf_data if bluf_data else "") + ("\n\n" + bluf_dynamic if bluf_dynamic else "")
        _bluf_msgs = [
            _SM(content=_combined_bluf_sys),
            HumanMessage(content=bluf_user),
        ]
        _bluf_result, _is_fallback, _used_model = await chat_with_fallback(
            _bluf_msgs, user_llm_key, settings.parallel_bluf_max_tokens, effective_model
        )
        bluf_raw = _bluf_result.content if isinstance(_bluf_result.content, str) else None
        bluf_usage = {}
        if _is_fallback and structured_callback:
            try:
                await structured_callback("model_info", {
                    "is_fallback": True,
                    "model": _used_model,
                })
            except Exception:
                pass
    else:
        bluf_llm = create_llm(effective_model, max_tokens=settings.parallel_bluf_max_tokens,
                              user_key=user_llm_key, user_provider=user_llm_provider)
        bluf_raw, bluf_usage = await _call_llm_simple(bluf_llm, provider, bluf_static, bluf_data, bluf_user, bluf_dynamic, model_id=effective_model)
    bluf_parsed = parse_llm_json(bluf_raw) if bluf_raw else None
    if not bluf_parsed:
        logger.warning("parallel_pipeline: BLUF call failed or unparseable")
        return None

    section_titles: list[str] = bluf_parsed.get("section_titles", [])
    if not section_titles:
        logger.warning("parallel_pipeline: no section_titles returned")
        return None

    if structured_callback:
        try:
            await structured_callback("bluf", {
                **bluf_parsed.get("bluf", {}),
                "section_titles": section_titles,
                "flowcharts": bluf_parsed.get("flowcharts", []),
                "tables": bluf_parsed.get("tables", []),
            })
        except Exception:
            pass

    bluf_text: str = (
        bluf_parsed.get("bluf", {}).get("body", "")
        or bluf_parsed.get("bluf", {}).get("headline", "")
        or query
    )

    _section_sem = asyncio.Semaphore(settings.parallel_sections_max_concurrent)

    async def _gen_one_section(title: str, idx: int) -> tuple[dict | None, dict]:
        if query_type == "complex":
            sec_static, sec_dynamic, sec_data, sec_user = build_complex_section_messages(
                section_title=title,
                all_section_titles=section_titles,
                bluf_text=bluf_text,
                query=query,
                drug=drug,
                primary_disease=primary_disease,
                comorbidity_list=comorbidity_list,
                patient_context=getattr(fetched_data, "patient_context", {}) if fetched_data else {},
                fetched_data=fetched_data,
                vector_results=vector_results,
            )
        else:
            sec_static, sec_dynamic, sec_data, sec_user = build_section_messages(
                section_title=title,
                all_section_titles=section_titles,
                bluf_text=bluf_text,
                query=query,
                query_type=query_type,
                fetched_data=fetched_data,
                vector_results=vector_results,
            )
        sec_llm = create_llm(effective_model, max_tokens=settings.parallel_sections_max_tokens,
                             user_key=user_llm_key, user_provider=user_llm_provider)
        # Semaphore limits concurrent LLM calls to stay under token-per-minute limits.
        # Quality is unaffected — each section still gets its full prompt and token budget.
        async with _section_sem:
            raw, usage = await _call_llm_simple(sec_llm, provider, sec_static, sec_data, sec_user, sec_dynamic, model_id=effective_model)
        sec = parse_llm_json(raw) if raw else None
        # Emit as soon as this section is ready — don't wait for all sections to finish
        if sec is not None and structured_callback:
            section_dict = {
                "title": sec.get("title", title),
                "content_items": sec.get("content_items", []),
            }
            try:
                await structured_callback("section_complete", {**section_dict, "index": idx})
            except Exception:
                pass
        return sec, usage

    raw_sections = await asyncio.gather(
        *[_gen_one_section(t, i) for i, t in enumerate(section_titles)],
        return_exceptions=True,
    )

    all_sections: list[dict] = []
    all_refs: list[dict] = list(bluf_parsed.get("references", []))
    total_in = bluf_usage.get("input_tokens", 0)
    total_out = bluf_usage.get("output_tokens", 0)

    for idx, (title, result) in enumerate(zip(section_titles, raw_sections)):
        if isinstance(result, Exception):
            logger.warning("parallel_pipeline: section '%s' failed: %s", title, result)
            continue
        sec, sec_usage = result
        if sec is None:
            logger.warning("parallel_pipeline: section '%s' returned None", title)
            continue
        total_in += sec_usage.get("input_tokens", 0)
        total_out += sec_usage.get("output_tokens", 0)
        section_dict = {
            "title": sec.get("title", title),
            "content_items": sec.get("content_items", []),
        }
        all_sections.append(section_dict)
        all_refs.extend(r for r in sec.get("references", []) if isinstance(r, dict))

    if not all_sections:
        logger.warning("parallel_pipeline: all section calls failed")
        return None

    return {
        "_parallel_usage": {"input_tokens": total_in, "output_tokens": total_out},
        "bluf": bluf_parsed.get("bluf", {}),
        "sections": all_sections,
        "references": _dedup_references(all_refs),
        "tables": bluf_parsed.get("tables", []),
        "flowcharts": bluf_parsed.get("flowcharts", []),
        "response_focus": bluf_parsed.get("response_focus", query_type),
        "related_topics": bluf_parsed.get("related_topics", []),
    }


async def process_query(
    request: QueryRequest,
    redis_client=None,
    user_key_id: str | None = None,
    user=None,
    token_callback: Callable[[str], Awaitable[None]] | None = None,
    structured_callback: Callable[[str, object], Awaitable[None]] | None = None,
) -> QueryResponse:
    """Main RAG pipeline orchestrator."""
    start_time = time.time()
    validation_warnings: list[str] = []

    # Resolve user's BYOK key (only user-supplied key is used — no server .env fallback)
    user_llm_key: str | None = None
    user_llm_provider: str | None = None

    # Determine intent from the requested model — a "/" in the model ID means OpenRouter.
    # This lets users with both a BYOK key and an OAuth OpenRouter key pick either engine.
    _wants_openrouter = bool(request.model_id and "/" in request.model_id)

    # If request targets an OpenRouter model AND the user has an OAuth key, prefer it.
    use_chat_service = False
    if _wants_openrouter and user and getattr(user, "openrouter_key", None):
        from app.services.byok import decrypt_key as _decrypt_or_key
        _or_key = _decrypt_or_key(user.openrouter_key)
        if _or_key:
            user_llm_key = _or_key
            user_llm_provider = "openrouter"
            use_chat_service = True

    # Fall back to per-provider BYOK keys via the KeyStore (preferred path going forward).
    if user_llm_key is None and user:
        from app.services.byok import decrypt_key  # for the legacy encrypted_llm_key fallback below
        keystore = get_keystore()
        # Honor engine_pref first, then a fixed priority order.
        _pref_provider = (getattr(user, "preferences", {}) or {}).get("engine_pref") or user.llm_provider
        _provider_priority = [_pref_provider] if _pref_provider else []
        for _p in ("cerebras", "anthropic", "openai"):
            if _p not in _provider_priority:
                _provider_priority.append(_p)
        for _try_provider in _provider_priority:
            if not _try_provider:
                continue
            _decrypted = keystore.get(user, _try_provider)
            if _decrypted:
                user_llm_key = _decrypted
                user_llm_provider = _try_provider
                break

        # Final fallback: legacy encrypted_llm_key (backward compat for users not yet migrated)
        if user_llm_key is None and user.encrypted_llm_key:
            user_llm_key = decrypt_key(user.encrypted_llm_key)
            user_llm_provider = user.llm_provider
            if user_llm_key is None:
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

    # If no BYOK key either, check for OAuth OpenRouter key as a final fallback
    # (handles case where user only has OAuth key and didn't send an OpenRouter model_id)
    if user_llm_key is None and user and getattr(user, "openrouter_key", None):
        from app.services.byok import decrypt_key as _decrypt_or_key
        _or_key = _decrypt_or_key(user.openrouter_key)
        if _or_key:
            user_llm_key = _or_key
            user_llm_provider = "openrouter"
            use_chat_service = True
            # Default to Gemma 4 primary if request doesn't specify a model
            if not request.model_id or "/" not in request.model_id:
                request = request.model_copy(
                    update={"model_id": settings.openrouter_gemma_primary}
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

    # Speculative type — default to complex (catch-all) for parallel cache prefetch
    # Used only for cache hint before real LLM classification; doesn't affect final result
    speculative_type = "complex"

    # Anthropic classifies with its cheap classify-role model (Haiku); every other
    # provider uses the user's own model. Registry-driven (settings.model_classify is
    # the Anthropic Haiku id and matches the registry's anthropic classify role).
    if provider_for_request == "anthropic":
        _dspy_classify_model = (
            get_registry().default_model_for_role("anthropic", "classify")
            or settings.model_classify
        )
    else:
        _dspy_classify_model = normalized_request_model

    # Run merged analysis+expansion, Redis cache check, and stance neutralization in parallel
    _combined, _cache_prefetch, _stance_result = await asyncio.gather(
        _analyze_and_expand_query(
            request.query,
            model_id=_dspy_classify_model,
            user_key=user_llm_key,
            user_provider=user_llm_provider,
        ),
        cache_get(redis_client, request.query, speculative_type, normalized_request_model),
        neutralize_query(
            request.query,
            model_id=_dspy_classify_model,
            user_key=user_llm_key,
            user_provider=user_llm_provider,
        ),
        return_exceptions=True,
    )
    combined = _combined if not isinstance(_combined, Exception) else None
    _speculative_cache = _cache_prefetch if not isinstance(_cache_prefetch, Exception) else None
    stance_result = _stance_result if isinstance(_stance_result, StanceResult) else None
    pubmed_expansion_terms: dict | None = None

    # Extract neutral query for retrieval
    retrieval_query = stance_result.neutral_clinical_question if stance_result else request.query
    stance_meta = {"stance": stance_result.stance, "loaded_terms": stance_result.loaded_terms} if stance_result else None

    if combined:
        # New merged path: 1 Haiku call instead of 2
        rewritten_query = combined.get("rewritten_query") or request.query
        query_analysis = combined  # contains entities, condition_context, query_type etc.
        pubmed_expansion_terms = combined.get("pubmed_terms")
        _query_intent = combined.get("intent") or "general"
        _search_variants = combined.get("search_variants") or []
        # Store patient_context extracted from query (for complex queries)
        _patient_context = combined.get("patient_context", {}) or {}
        if rewritten_query != request.query:
            logger.info("Query rewritten: %r → %r", request.query, rewritten_query)
    else:
        # Legacy fallback — exact same behaviour as before this change
        logger.info("_analyze_and_expand_query failed — falling back to legacy DSPy + rewrite")
        _query_intent = "general"
        _search_variants = []
        _patient_context = {}
        _dspy_result, _rewritten = await asyncio.gather(
            _analyze_query_with_dspy(
                request.query,
                model_id=_dspy_classify_model,
                user_key=user_llm_key,
                user_provider=user_llm_provider,
            ),
            _rewrite_query(
                request.query,
                model_id=normalized_request_model,
                user_key=user_llm_key,
                user_provider=user_llm_provider,
            ),
            return_exceptions=True,
        )
        query_analysis = _dspy_result if not isinstance(_dspy_result, Exception) else None
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

    # Normalize query type for highlights intent — don't use complex/procedure/etc
    if query_intent == "highlights" and query_type not in (
        "drug",
        "disease",
        "comparative",
        "procedure",
        "evidence",
    ):
        query_type = "complex"

    analysis_entities = _sanitize_entities(query_analysis["entities"]) if query_analysis else []
    condition_context = query_analysis.get("condition_context") if query_analysis else None

    # Safety net: normalize any unrecognized type (including legacy "general") to "complex"
    _CURRENT_VALID_TYPES = {"drug", "disease", "comparative", "procedure", "evidence", "complex"}
    if query_type not in _CURRENT_VALID_TYPES:
        logger.info(
            "query_type normalized to 'complex': unrecognized value %r (query: %r)",
            query_type, request.query[:60],
        )
        query_type = "complex"

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

    if use_api_fetch:
        routing = route_query(
            rewritten_query,
            query_type,
            entities=analysis_entities or None,
            requested_model=normalized_request_model,
            user_provider=user_llm_provider,
            model_explicit=request.model_explicit,
            condition_context=condition_context,
            intent=_query_intent,
        )

    # Parallel fetch: data API + vector search + semantic cache via LangGraph
    # Use neutral query for retrieval to avoid stance-biased fetching
    _fetch_t0 = time.perf_counter()
    fetched_data, vector_results, _sem_result = await run_search_graph(
        query=retrieval_query,
        original_query=request.query,
        query_type=query_type,
        routing=routing,
        normalized_model=normalized_request_model,
        api_fetch_timeout=settings.api_fetch_timeout_seconds + 1.0,
        use_api_fetch=use_api_fetch,
        use_vector=use_vector,
        user_llm_key=user_llm_key,
        user_llm_provider=user_llm_provider,
        user_voyage_key=user_voyage_key,
        user_email=user_email,
        user_ncbi_key=user_ncbi_key,
        pubmed_expansion_terms=pubmed_expansion_terms,
        force_refresh=request.force_refresh,
    )
    # Store patient context extracted from query (for complex queries)
    if fetched_data:
        fetched_data.patient_context = _patient_context
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

    # Emit real article titles to the frontend as soon as fetch completes
    if structured_callback and fetched_data:
        try:
            await structured_callback("fetch_articles", {"titles": _extract_fetch_articles(fetched_data)})
        except Exception:
            pass

    # Handle semantic cache hit (checked in parallel above)
    if _sem_result is not None:
        if isinstance(_sem_result, tuple) and len(_sem_result) == 3:
            sem_response, sem_cache_id, sem_verified_at = _sem_result
        else:
            sem_response, sem_cache_id, sem_verified_at = None, None, None
        if sem_response:
            # Check if cache is fresh (not stale)
            _sem_stale = is_stale(
                sem_verified_at,
                settings.semantic_cache_swr_ttl_seconds,
            )
            # For medical safety: only return cached result if it's fresh (not stale)
            # If stale, skip cache and continue to run fresh pipeline
            if not _sem_stale:
                latency_ms = int((time.time() - start_time) * 1000)
                sem_response["cached"] = True
                if sem_verified_at:
                    from datetime import datetime
                    sem_response["cached_at"] = sem_verified_at.isoformat() if hasattr(sem_verified_at, 'isoformat') else str(sem_verified_at)
                sem_response["latency_ms"] = latency_ms
                try:
                    _sem_hit_resp = QueryResponse(**sem_response)
                except Exception:
                    _sem_hit_resp = None
                if _sem_hit_resp:
                    if user and user.id:
                        asyncio.create_task(
                            _log_search_history(user.id, request.query, query_type, sem_response)
                        )
                    return _sem_hit_resp

    # Initialize evidence confidence with default value
    _evidence_confidence = compute_evidence_confidence(fetched_data, query_type)

    try:
        if use_api_fetch and fetched_data is not None and not fetched_data.fallback_to_llm:
            fetched_data, retrieval_notes = await _expand_retrieval_if_needed(
                query=request.query,
                query_type=query_type,
                fetched_data=fetched_data,
                entities=routing.entities if routing else (analysis_entities or []),
                condition_context=condition_context,
                response_focus=(query_analysis or {}).get("response_focus") if query_analysis else None,
                rewritten_query=rewritten_query,
                answer_entities=(query_analysis or {}).get("answer_entities") if query_analysis else None,
            )

            # Rank retrieved articles by evidence quality before LLM synthesis
            if fetched_data and not fetched_data.fallback_to_llm:
                _rank_fetched_abstracts(
                    fetched_data,
                    entities=routing.entities if routing else (analysis_entities or []),
                    query_text=rewritten_query,
                )
                # Update evidence confidence after ranking
                _evidence_confidence = compute_evidence_confidence(fetched_data, query_type)

    except EvidenceFloorError:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "process_query: evidence floor exhausted for query=%r — returning no_evidence",
            request.query[:80],
        )
        return QueryResponse(
            query_type=query_type,
            model_used=normalized_request_model,
            response=DegradedResponse(
                message=(
                    "No citable sources found for this query across PubMed, NCBI Bookshelf, "
                    "MedlinePlus, openFDA, and NICE. Please rephrase or add a more specific "
                    "clinical term."
                ),
                suggestion=(
                    "Try adding the specific drug name, disease, or procedure. "
                    "You can also upload a relevant PDF for document-based answers."
                ),
                error_code="no_evidence",
            ),
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
            validation_warnings=retrieval_notes + ["evidence_floor: all strategies exhausted"],
        )

    # Evidence floor guarantees ≥1 citable source — always use format mode.
    prompt_mode = "format"
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

    # Targeted hallucination guard — fires when fail_closed_evidence_only is OFF,
    # query is a medical type, no vector results exist, and fetch returned nothing usable.
    _MEDICAL_QUERY_TYPES = {"drug", "disease", "comparative", "procedure", "evidence", "complex"}
    if (
        prompt_mode == "generate"
        and query_type in _MEDICAL_QUERY_TYPES
        and not vector_results
        and not fetch_timed_out
        and not settings.fail_closed_evidence_only  # avoid double-firing when flag is on
    ):
        logger.warning(
            "Hallucination guard triggered: generate mode for medical query_type=%s with no evidence",
            query_type,
        )
        latency_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            query_type=query_type,
            model_used=normalized_request_model,
            response=DegradedResponse(
                message=(
                    "Not enough medical evidence was retrieved to answer this query safely. "
                    "The system does not generate answers from training knowledge for clinical questions."
                ),
                suggestion=(
                    "Try rephrasing with the specific drug name, disease, procedure, or evidence "
                    "question. You can also upload relevant PDFs to enable document-based answers."
                ),
            ),
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
            validation_warnings=retrieval_notes + [
                "Hallucination guard: medical query with no retrieved evidence was blocked."
            ],
        )

    # Model and token budget selection
    # If user explicitly chose a model, respect it unconditionally.
    # Otherwise use the two-model strategy: classify with Sonnet, generate with configurable model.
    effective_model = normalized_request_model
    if request.model_explicit:
        effective_model = normalized_request_model
    elif user_llm_provider == "anthropic":
        effective_model = settings.model_generate
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
        else:
            max_tokens = settings.llm_max_tokens_format
    elif query_type == "disease":
        max_tokens = settings.llm_max_tokens_format_disease
    elif query_type == "evidence":
        max_tokens = settings.llm_max_tokens_format_evidence
    elif query_type == "procedure":
        max_tokens = settings.llm_max_tokens_format_procedure
    elif query_type == "drug" and condition_context:
        max_tokens = settings.llm_max_tokens_format_drug_context

    # ── Unified Adaptive Generation ───────────────────────────────────────────
    # All query types use a single adaptive prompt. DSPy is kept only for
    # classification (query_type, required_sections, related_topics).
    required_sections: list[str] = (
        list(query_analysis.get("required_sections", [])) if query_analysis else []
    )

    comparative_is_drug = (
        query_type == "comparative"
        and fetched_data is not None
        and len(fetched_data.comparative_drug_data or []) >= 2
    )

    system_text, data_block, user_text = build_adaptive_messages(
        rewritten_query,
        query_type,
        fetched_data=fetched_data,
        vector_results=vector_results,
        required_sections=required_sections or None,
        condition_context=condition_context,
        comparative_is_drug=comparative_is_drug,
    )

    # Initialise variables shared by both pipeline paths
    parsed: dict | None = None
    raw_response: str | None = None
    _gen_usage: dict = {}
    _llm_t0 = time.perf_counter()

    # ── Parallel section agents (when enabled) ────────────────────────────────
    # OpenRouter OAuth users (use_chat_service=True) run single-call mode to conserve
    # free-tier daily limits (~20 req/day per model; parallel mode burns 6-8 calls/query).
    if settings.parallel_sections_enabled and structured_callback is not None and not use_chat_service:
        _llm_t0 = time.perf_counter()
        parallel_parsed = await _run_parallel_pipeline(
            query=rewritten_query,
            query_type=query_type,
            fetched_data=fetched_data,
            vector_results=vector_results,
            effective_model=effective_model,
            user_llm_key=user_llm_key,
            user_llm_provider=user_llm_provider,
            condition_context=condition_context,
            comparative_is_drug=comparative_is_drug,
            structured_callback=structured_callback,
            use_chat_service=use_chat_service,
        )
        if parallel_parsed is not None:
            _gen_usage = parallel_parsed.pop("_parallel_usage", {})
            parsed = parallel_parsed
            logger.info(
                "pipeline.parallel_sections",
                extra={
                    "stage": "parallel_sections",
                    "query_type": query_type,
                    "sections": len(parsed.get("sections", [])),
                    "duration_ms": round((time.perf_counter() - _llm_t0) * 1000),
                },
            )
            raw_response = "__parallel__"  # sentinel — skip single-call block
        else:
            logger.warning("parallel_pipeline failed; falling back to single call")
            raw_response = None
            parsed = None

    _single_call_needed = raw_response != "__parallel__"
    _gen_llm = None  # only set by the non-chat-service path; guards the retry block
    if _single_call_needed and use_chat_service:
        # OpenRouter OAuth path: single call via chat_with_fallback (3-model chain)
        _llm_t0 = time.perf_counter()
        raw_response = None
        _gen_usage = {}
        try:
            from app.services.chat_service import chat_with_fallback as _cwf
            from langchain_core.messages import SystemMessage as _SM2, HumanMessage as _HM2
            _combined = system_text + ("\n\n" + data_block if data_block else "")
            _cs_msgs = [_SM2(content=_combined), _HM2(content=user_text)]
            _cs_result, _cs_is_fallback, _cs_used_model = await _cwf(
                _cs_msgs, user_llm_key, max_tokens, effective_model
            )
            raw_response = _cs_result.content if isinstance(_cs_result.content, str) else None
            _cs_usage = getattr(_cs_result, "usage_metadata", None) or {}
            _gen_usage = {
                "input_tokens": _cs_usage.get("input_tokens", 0) or 0,
                "output_tokens": _cs_usage.get("output_tokens", 0) or 0,
            }
            if _cs_is_fallback and structured_callback:
                try:
                    await structured_callback("model_info", {
                        "is_fallback": True,
                        "model": _cs_used_model,
                    })
                except Exception:
                    pass
            parsed = parse_llm_json(raw_response) if raw_response else None
        except HTTPException:
            raise
        except Exception:
            logger.error("chat_with_fallback single-call failed", exc_info=True)
            raw_response = None
            parsed = None

    if _single_call_needed and not use_chat_service:
        _llm_t0 = time.perf_counter()
        raw_response = None
        _gen_usage = {}
        _gen_llm = None
        _gen_provider = user_llm_provider or get_provider(effective_model)
        _gen_breaker = get_breaker(_gen_provider)
        try:
            _gen_llm = create_llm(
                effective_model,
                max_tokens=max_tokens,
                user_key=user_llm_key,
                user_provider=user_llm_provider,
            )

            @_gen_breaker
            async def _invoke_adaptive():
                nonlocal _gen_usage
                if _gen_provider == "anthropic":
                    use_cache_control = (_gen_provider == "anthropic")
                    _sys_content = [
                        {
                            "type": "text",
                            "text": system_text,
                            **({"cache_control": {"type": "ephemeral"}} if use_cache_control else {}),
                        },
                    ]
                    if data_block:
                        if len(data_block) > 4096:
                            _sys_content.append({
                                "type": "text",
                                "text": data_block,
                                **({"cache_control": {"type": "ephemeral"}} if use_cache_control else {}),
                            })
                        else:
                            _sys_content.append({"type": "text", "text": data_block})
                    _msgs = [
                        SystemMessage(content=_sys_content),
                        HumanMessage(content=user_text),
                    ]
                else:
                    combined = system_text + ("\n\n" + data_block if data_block else "")
                    _msgs = [SystemMessage(content=combined), HumanMessage(content=user_text)]

                if token_callback is not None:
                    _chunks = []
                    _last_chunk = None
                    async for _chunk in _gen_llm.astream(_msgs):
                        _text = _chunk.content if isinstance(_chunk.content, str) else ""
                        if _text:
                            _chunks.append(_text)
                            await token_callback(_text)
                        _last_chunk = _chunk
                    _usage = getattr(_last_chunk, "usage_metadata", None) or {} if _last_chunk else {}
                    _gen_usage = {
                        "input_tokens": _usage.get("input_tokens", _usage.get("prompt_tokens", 0)) or 0,
                        "output_tokens": _usage.get("output_tokens", _usage.get("completion_tokens", 0)) or 0,
                    }
                    return "".join(_chunks)

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

        # Parse the adaptive JSON (single-call path only)
        parsed = parse_llm_json(raw_response) if raw_response else None

    # Retry once (single-call path only) with a stricter suffix if parse failed
    if _single_call_needed and parsed is None and _gen_llm is not None:
        logger.info("Adaptive LLM call failed or unparseable, retrying...")
        await asyncio.sleep(settings.llm_retry_backoff_seconds)
        retry_static = (
            system_text
            + "\n\nCRITICAL: Return ONLY the JSON object described above. "
            "No markdown fences, no prose, no preamble."
        )
        try:
            @_gen_breaker
            async def _retry_adaptive():
                if _gen_provider == "anthropic":
                    use_cache_control = (_gen_provider == "anthropic")
                    _sys_content = [
                        {
                            "type": "text",
                            "text": retry_static,
                            **({"cache_control": {"type": "ephemeral"}} if use_cache_control else {}),
                        },
                    ]
                    if data_block:
                        if len(data_block) > 4096:
                            _sys_content.append({
                                "type": "text",
                                "text": data_block,
                                **({"cache_control": {"type": "ephemeral"}} if use_cache_control else {}),
                            })
                        else:
                            _sys_content.append({"type": "text", "text": data_block})
                    _msgs = [
                        SystemMessage(content=_sys_content),
                        HumanMessage(content=user_text),
                    ]
                else:
                    combined = retry_static + ("\n\n" + data_block if data_block else "")
                    _msgs = [SystemMessage(content=combined), HumanMessage(content=user_text)]
                return (await _gen_llm.ainvoke(_msgs)).content

            raw_retry = await _retry_adaptive()
            if raw_retry:
                parsed = parse_llm_json(raw_retry)
        except Exception:
            pass

    logger.info(
        "pipeline.llm_call",
        extra={
            "stage": "parallel" if not _single_call_needed else "llm_call",
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
        # Post-processing chain — order is load-bearing for source attribution
        from app.services.prompt_engine import build_ref_map

        ref_map = build_ref_map(fetched_data) if (fetched_data and settings.citation_ref_tokens_enabled) else {}
        registry = build_article_registry(fetched_data) if (fetched_data and settings.citation_ref_tokens_enabled) else ArticleRegistry()

        _resolve_ref_tokens(parsed, ref_map, registry)    # 1. Resolve [REF_N] tokens; mark registry used_inline
        _title_rescue_pass(parsed, registry)              # 1b. Rescue free-form titles (Cerebras etc.)
        sanitize_response_pmids(parsed, fetched_data)     # 2. Validate PMIDs
        _normalize_consensus_sources(parsed)              # 3. Normalize consensus sources
        _backfill_from_registry(parsed, registry)         # 4. Per-claim backfill via registry.best_match
        # 4b. Orphan rescue — attach fetched articles not yet in reference list
        if settings.reference_filter_v2_enabled and registry:
            registry.attach_orphans_to_references(parsed)
        _quarantine_sourceless_items(parsed, fetched_data, registry)  # 5. Demote ungrounded + filter v2
        # 6. Final reference list = registry.to_reference_list() (cited first, then retrieved)
        _raw_refs = registry.to_reference_list() if registry.items else []
        # If registry empty (no fetched_data), preserve any LLM-supplied refs that pass safety
        if not _raw_refs:
            _raw_refs = parsed.get("references", []) or []
        parsed["references"] = _raw_refs
        enrich_references({"references": _raw_refs}, fetched_data)  # validator pass-through
        _raw_refs = _filter_expert_references(_raw_refs)
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

        _response_focus = (
            parsed.get("response_focus")
            or str((query_analysis or {}).get("response_focus", query_type))
        )
        _related_topics = (
            parsed.get("related_topics")
            or list((query_analysis or {}).get("related_topics", []))
        )
        adaptive_response = AdaptiveResponse(
            query_type=query_type,
            bluf=_bluf,
            sections=_sections,
            references=_references,
            response_focus=_response_focus,
            depth="comprehensive",
            related_topics=_related_topics,
            tables=parsed.get("tables", []),
            flowcharts=parsed.get("flowcharts", []),
            images=getattr(fetched_data, "images", []) if fetched_data else [],
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
    fetched_source_labels = set(fetched_data.data_sources) if fetched_data and fetched_data.data_sources else set()
    citation_warnings = validate_citations(validated_dict, query_type, fetched_data, fetched_source_labels)
    validation_warnings.extend(citation_warnings)

    # Remove claims marked with __drop__ flag from strict-mode validation
    if query_type == "complex" and "sections" in validated_dict:
        for section in validated_dict["sections"]:
            section["content_items"] = [
                item for item in section.get("content_items", [])
                if not item.get("__drop__", False)
            ]

    # Safety check
    safety_warnings = check_safety(request.query, validated_dict, query_type)

    # Drug linker
    text_nodes = await process_text_nodes(validated_dict, query_type)

    latency_ms = int((time.time() - start_time) * 1000)

    # Collect data sources used
    fetch_sources = list(fetched_data.data_sources) if fetched_data else []
    if vector_results:
        fetch_sources.append("Vector DB (your PDFs)")

    # Fill null/NA sources in adaptive content_items — source must always be attributed with real value
    if "sections" in validated_dict:
        _source_fallback = fetch_sources[0] if fetch_sources else "Medical literature"
        _na_literals = {"na", "n/a", "n.a.", "not available", "unknown", "none"}
        for _sec in validated_dict.get("sections", []):
            for _item in _sec.get("content_items", []):
                source_val = _item.get("source", "")
                if not source_val or (isinstance(source_val, str) and source_val.strip().lower() in _na_literals):
                    _item["source"] = _source_fallback

    # Keep returned response aligned with strict-mode citation drops and URL sanitization.
    try:
        adaptive_response = AdaptiveResponse(**validated_dict)
    except Exception as _ve:
        logger.warning("AdaptiveResponse rebuild failed after validation: %s", _ve)

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
            _usage_note = (
                "* DSPy classification tokens not included (tracked separately by DSPy LM)."
                if settings.dspy_enabled
                else ""
            )
            token_usage = TokenUsage(
                models=models_cost,
                total_input_tokens=total_in,
                total_output_tokens=total_out,
                total_cost_usd=total_cost,
                note=_usage_note,
            )

    response = QueryResponse(
        query_type=query_type,
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
        semantic_cache_set(
            request.query,
            query_type,
            effective_model,
            cache_data,
            provider=user_llm_provider,
            api_key=user_llm_key,
            voyage_api_key=user_voyage_key,
        )
    )

    await _enqueue_log(
        {
            "query": request.query,
            "original_query": request.query,
            "rewritten_query": rewritten_query,
            "intent": _query_intent,
            "search_variants": _search_variants,
            "query_type": query_type,
            "model_used": effective_model,
            "effective_model": effective_model,
            "prompt_mode": prompt_mode,
            "evidence_confidence": _evidence_confidence.get("confidence_level", "unknown"),
            "evidence_count": _evidence_confidence.get("evidence_count", 0),
            "top_study_types": _evidence_confidence.get("top_study_types", []),
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

