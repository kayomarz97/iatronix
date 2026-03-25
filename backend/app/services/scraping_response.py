"""
scraping_response.py — Build a GeneralResponse from raw fetched API data without LLM.

Used by source_mode="scraping" to deliver results when no LLM key is configured.
No fastapi / pybreaker imports — safe to test in isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.schemas.query import GeneralResponse, Reference

if TYPE_CHECKING:
    from app.services.data_fetcher import FetchedData


def _build_scraping_response(
    query: str, query_type: str, fetched_data: "FetchedData | None"
) -> GeneralResponse | None:
    """
    Build a GeneralResponse directly from raw fetched API data — no LLM involved.
    Returns None if fetch failed or no useful data is available.
    """
    if not fetched_data or fetched_data.fallback_to_llm:
        return None

    key_points: list[str] = []
    summary = ""
    references: list[dict] = []

    if query_type == "drug" and fetched_data.drug_data:
        d = fetched_data.drug_data
        if not d.fetch_success:
            return None
        name = d.generic_name or query
        brand = f" ({d.brand_name})" if d.brand_name else ""
        drug_class = (
            f" [{d.drug_class or d.drug_class_rxnorm}]"
            if (d.drug_class or d.drug_class_rxnorm)
            else ""
        )
        summary = f"{name}{brand}{drug_class} — raw data from {d.data_source.upper()}."
        if d.mechanism_raw:
            key_points.append(f"Mechanism: {d.mechanism_raw[:200]}")
        if d.indications_raw:
            key_points.append(f"Indications: {d.indications_raw[:300]}")
        if d.dosing_raw:
            key_points.append(f"Dosing: {d.dosing_raw[:300]}")
        if d.contraindications_raw:
            key_points.append(f"Contraindications: {d.contraindications_raw[:200]}")
        if d.adverse_reactions_raw:
            key_points.append(f"Adverse reactions: {d.adverse_reactions_raw[:200]}")
        if d.top_adverse_events:
            key_points.append(
                f"Top reported events (FAERS): {', '.join(d.top_adverse_events[:6])}"
            )
        if d.drug_interactions_raw:
            key_points.append(f"Interactions: {d.drug_interactions_raw[:200]}")
        for ab in d.guideline_abstracts[:2]:
            key_points.append(
                f"Guideline ({ab.get('year', '')}): {ab.get('title', '')}"
            )
        for ab in d.systematic_review_abstracts[:2]:
            key_points.append(
                f"Systematic review ({ab.get('year', '')}): {ab.get('title', '')}"
            )
        references.append(
            {
                "source": d.data_source.upper(),
                "title": name,
                "year": d.fda_label_source_year,
                "url": None,
            }
        )

    elif query_type == "disease" and fetched_data.disease_data:
        d = fetched_data.disease_data
        if not d.fetch_success:
            return None
        summary = (
            d.medlineplus_summary
            or f"Retrieved {len(d.guideline_abstracts)} guidelines and "
            f"{len(d.systematic_review_abstracts)} systematic reviews for {query}."
        )
        for ab in d.guideline_abstracts[:5]:
            key_points.append(
                f"Guideline ({ab.get('year', '')}): {ab.get('title', '')} — "
                f"{ab.get('abstract', '')[:150]}"
            )
        for ab in d.systematic_review_abstracts[:3]:
            key_points.append(
                f"SR ({ab.get('year', '')}): {ab.get('title', '')} — "
                f"{ab.get('abstract', '')[:120]}"
            )
        for rec in d.nice_recommendations[:2]:
            key_points.append(f"NICE: {rec.get('text', '')[:200]}")
        for p in d.semantic_papers[:2]:
            key_points.append(f"Paper ({p.get('year', '')}): {p.get('title', '')}")
        if d.guideline_abstracts:
            references.append(
                {"source": "PubMed", "title": "Guidelines", "year": None, "url": None}
            )

    elif query_type == "comparative" and fetched_data.comparative_drug_data:
        drugs = [d for d in fetched_data.comparative_drug_data if d.fetch_success]
        if not drugs:
            return None
        names = [d.generic_name or "Unknown" for d in drugs]
        summary = f"Raw comparison data for: {', '.join(names)}."
        for d in drugs:
            pts = []
            if d.indications_raw:
                pts.append(f"indications: {d.indications_raw[:150]}")
            if d.dosing_raw:
                pts.append(f"dosing: {d.dosing_raw[:100]}")
            key_points.append(f"{d.generic_name}: " + "; ".join(pts))
            references.append(
                {
                    "source": d.data_source.upper(),
                    "title": d.generic_name,
                    "year": d.fda_label_source_year,
                    "url": None,
                }
            )

    else:
        return None

    if not summary and not key_points:
        return None

    return GeneralResponse(
        summary=summary or f"Raw data retrieved for: {query}",
        key_points=[p for p in key_points if p.strip()],
        related_drugs=[],
        related_conditions=[],
        confidence="moderate",
        references=[
            Reference(
                source=r["source"], title=r.get("title"), year=r.get("year"), url=None
            )
            for r in references
        ],
    )
