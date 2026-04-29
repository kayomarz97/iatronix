"""Iatronix clinical reference engine for LLM prompting.

Builds system, data, and user prompts for various medical query types.
Handles both synchronous and async LLM invocation via LangChain.
"""

from __future__ import annotations

import html
import json
import logging
import re
from typing import TYPE_CHECKING, Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from app.schemas.internal import FetchedData, SearchResult

logger = logging.getLogger(__name__)

# ====================================================================
# Constants
# ====================================================================

APPROVED_SOURCES = """
APPROVED INFORMATION SOURCES (for clinical validity):
- PubMed (NCBI) — peer-reviewed journal articles, trials, reviews, guidelines
- FDA Drug Labels (FDA.gov, DailyMed) — approved uses, warnings, dosing
- NICE Guidelines (NICE.org.uk) — UK evidence-based recommendations
- RxNorm (NCBI) — standardized drug metadata and classifications
- WHO Essential Medicines Lists and ICD-10 classifications
- Major medical societies (ESC, ACC, AHA, ASCP, etc.)
- StatPearls / MedlinePlus — educational medical summaries
"""

EVIDENCE_RULES = """
EVIDENCE-BASED CLAIMS:
- Every claim must cite a source: [SOURCE: ...] from the provided data.
- Assign Level of Evidence (LOE): I (RCT/meta-analysis), II (observational), III (expert/case reports), or null.
- Use Confidence: high (guideline/RCT), moderate (observational/review), low (case reports/expert).
- Never contradict fetched data. If no data exists, state "limited evidence" and explain what's known from your training (with caveats).
- Avoid speculative claims about off-label use without citing trial data or expert guidance.
"""

FORMATTING_RULES = """
FORMATTING RULES — write the `text` field of every content_item as Markdown:
- Use bullet lists (`- `) when listing more than 2 items (doses, adverse effects, criteria).
- Use **bold** for drug names, dose values, and red-flag warnings.
- Use `>` blockquote for direct guideline excerpts.
- Use sub-headings (`#### `) when a single content_item naturally contains multiple sub-topics.
- Numbered lists (`1.`) only for stepwise procedures.
- Keep paragraphs to 3 sentences or fewer. Break long prose into bullets.
"""

_SECTION_GUIDANCE: dict[str, str] = {
    "drug": (
        "Mechanism of Action · Indications · Dosing (all routes/regimens) · "
        "Contraindications · Side Effects (common AND serious) · Drug Interactions · "
        "Pharmacokinetics · Monitoring Parameters · Special Populations"
    ),
    "disease": (
        "Overview & Aetiology · Pathophysiology · Epidemiology · Clinical Features · "
        "Diagnostic Criteria · Treatment (first-line, second-line, non-pharmacological) · "
        "Complications · Prognosis"
    ),
    "comparative": (
        "Summary · [One dedicated section per entity being compared] · "
        "Head-to-Head Comparison · Clinical Preference & Guideline Positioning"
    ),
    "comparative_drug": (
        "Summary · [One dedicated section per drug being compared] · "
        "Head-to-Head Comparison · Clinical Preference & Guideline Positioning · "
        "Drug Interactions Between Compared Agents (list every clinically significant "
        "interaction between any two agents in the comparison — severity: major/moderate/minor, "
        "mechanism, clinical consequences, and management)"
    ),
    "procedure": (
        "Overview & Indications · Contraindications · Step-by-Step Technique · "
        "Complications & Incidence · Post-procedure Care · Guideline Recommendations"
    ),
    "evidence": (
        "Clinical Summary · Supporting Studies (with sample size, LOE) · "
        "Opposing / Conflicting Evidence · Clinical Recommendation · Guideline Status"
    ),
    "general": "Summary · Key Points · Clinical Context · Related Considerations",
    "complex": (
        "Baseline Rule (drug × primary disease) · "
        "[ONE SECTION PER COMORBIDITY: 'Conflict with <comorbidity>' — covering interaction mechanism, dose adjustment, monitoring] · "
        "Synthesised Recommendation · Monitoring & Red Flags"
    ),
}

_ADAPTIVE_SYSTEM_TEMPLATE = """\
You are a clinical reference assistant for medical professionals.
{approved_sources}
{evidence_rules}
{json_contract_rules}

QUERY TYPE: {query_type}
REQUIRED SECTION AREAS: {section_guidance}
{condition_block}{hint_section}
---
{data_block}
"""

_BLUF_ONLY_SCHEMA = """\

RESPOND WITH A SINGLE JSON OBJECT — no markdown fences, no prose outside the JSON:
{
  "bluf": {
    "headline": "One sentence that names the specific topic/drug/condition being asked about AND directly answers the question. Format: '[Topic] — [Answer]'. Example: 'Metformin in Type 2 Diabetes — first-line agent that lowers HbA1c by ~1–1.5% with cardiovascular benefit and low hypoglycemia risk.'",
    "body": "2-5 sentences directly answering the query. May use Markdown bullets (`- `) or **bold** when listing items or highlighting key values. Do NOT restate the headline.",
    "key_points": ["Actionable bullet 1", "Actionable bullet 2", "Actionable bullet 3"],
    "caveats": ["Safety or evidence caveat 1"]
  },
  "section_titles": [
    "Section heading 1",
    "Section heading 2"
  ],
  "references": [
    {
      "title": "Top-level article/guideline title from the data block",
      "source": "PubMed | NICE | FDA | etc.",
      "pmid": "12345678 or null",
      "year": "2024 or null"
    }
  ],
  "response_focus": "Brief description of what this response focuses on",
  "related_topics": ["Related query 1", "Related query 2"],
  "flowcharts": [
    {
      "title": "Clinical pathway title",
      "steps": [
        { "text": "Action step text", "label": "Phase label" },
        {
          "text": "Decision question?",
          "label": "Decision label",
          "is_decision": true,
          "branches": [
            { "condition": "Branch condition A", "outcome": "Resulting action A" },
            { "condition": "Branch condition B", "outcome": "Resulting action B" }
          ]
        }
      ]
    }
  ],
  "tables": [
    {
      "title": "Table title",
      "headers": ["Col A", "Col B", "LOE", "COR"],
      "rows": [["val", "val", "I", "I"]]
    }
  ]
}

Generate 5-10 section_titles that cover the REQUIRED SECTIONS for this query type.
Each title must be a short, clear heading (3-6 words).
Do NOT generate section content — section_titles are plain strings only.
references: list the key sources from the data block that best support this BLUF. Maximum 5.

FLOWCHARTS: Include ONLY for clinical decision algorithms (e.g. PE workup, sepsis, ACLS, anaphylaxis, HF escalation). Build rich decision trees — decision nodes (is_decision: true) must list all clinically distinct branches (2–4 per node). Label every node. Include ≥6 steps for applicable pathways. Never produce a purely linear list when decision points exist. Use "steps": [] when no pathway applies.
TABLES: Include ONLY for structured comparisons, diagnostic scoring, or drug dosing tables. Use "tables": [] if none apply."""

_SECTION_AGENT_SCHEMA = """\

RESPOND WITH A SINGLE JSON OBJECT — no markdown fences, no prose outside the JSON:
{{
  "title": "{section_title}",
  "content_items": [
    {{
      "text": "Evidence-based claim in GFM markdown. Use **bold** for key terms, tables for structured data, bullets for multi-part claims.",
      "loe": "I | II | III | null",
      "cor": "I | IIa | IIb | III-no-benefit | III-harm | null",
      "source": "[SOURCE: label from the data block — MUST match exactly]",
      "pmid": "12345678 or null"
    }}
  ],
  "references": [
    {{
      "title": "Exact article or guideline title from the data block",
      "source": "PubMed | NICE | FDA OpenFDA | MedlinePlus | Clinical Consensus | etc.",
      "pmid": "12345678 or null",
      "year": "2024 or null"
    }}
  ]
}}

EVERY content_item.source MUST cite a [SOURCE: ...] label from the fetched data block. Sources outside the block are FORBIDDEN.
If loe and cor are both null (evidence not gradeable), source is EVEN MORE critical — it is the only attribution the reader has. Never leave source null or empty.
references: List ALL sources from the data block that informed this section. Include a reference for every [SOURCE: ...] label cited in content_items. If fetched data was provided, there MUST be at least 1 reference. Only omit if the data block contained no relevant entries for this section.
Keep text length 100–200 words per item.
"""

# Static schema without any format placeholders — used as the caching-stable system prefix.
_STATIC_SECTION_SCHEMA = """\

RESPOND WITH A SINGLE JSON OBJECT — no markdown fences, no prose outside the JSON:
{
  "title": "<the section title stated in your instructions>",
  "content_items": [
    {
      "text": "Evidence-based claim in GFM markdown. Use **bold** for key terms, tables for structured data, bullets for multi-part claims.",
      "loe": "I | II | III | null",
      "cor": "I | IIa | IIb | III-no-benefit | III-harm | null",
      "source": "[SOURCE: label from the data block — MUST match exactly]",
      "pmid": "12345678 or null"
    }
  ],
  "references": [
    {
      "title": "Exact article or guideline title from the data block",
      "source": "PubMed | NICE | FDA OpenFDA | MedlinePlus | Clinical Consensus | etc.",
      "pmid": "12345678 or null",
      "year": "2024 or null"
    }
  ]
}

EVERY content_item.source MUST cite a [SOURCE: ...] label from the fetched data block. Sources outside the block are FORBIDDEN.
If loe and cor are both null (evidence not gradeable), source is EVEN MORE critical — it is the only attribution the reader has. Never leave source null or empty.
references: List ALL sources from the data block that informed this section. Include a reference for every [SOURCE: ...] label cited in content_items. If fetched data was provided, there MUST be at least 1 reference. Only omit if the data block contained no relevant entries for this section.
Keep text length 100–200 words per item.
"""

# Byte-identical static prefix for all section agent calls — used for prompt cache hits.
_STATIC_SECTION_SYSTEM = (
    "You are a clinical reference assistant generating one section of a structured medical response.\n"
    + APPROVED_SOURCES
    + "\n"
    + EVIDENCE_RULES
    + FORMATTING_RULES
    + _STATIC_SECTION_SCHEMA
)


def _format_drug_block(drug_result: Any) -> str:
    """Format a drug result object into a readable text block.

    Supports both legacy response objects and current DrugFetchResult shapes.
    """
    lines: list[str] = []

    drug_name = (
        getattr(drug_result, "drug_name", None)
        or getattr(drug_result, "generic_name", None)
        or getattr(drug_result, "brand_name", None)
    )
    if drug_name:
        lines.append(f"Drug: {drug_name}")

    drug_class = getattr(drug_result, "drug_class", None)
    if drug_class:
        lines.append(f"Class: {drug_class}")

    mechanism = None
    mechanism_obj = getattr(drug_result, "mechanism_of_action", None)
    if mechanism_obj is not None and hasattr(mechanism_obj, "value"):
        mechanism = mechanism_obj.value
    mechanism = mechanism or getattr(drug_result, "mechanism_raw", None)
    if mechanism:
        lines.append(f"Mechanism: {mechanism}")

    indications = getattr(drug_result, "indications", None)
    if indications:
        lines.append("Indications:")
        for ind in indications[:3]:
            value = getattr(ind, "value", None) or str(ind)
            if value:
                lines.append(f"  - {value}")
    else:
        indications_raw = getattr(drug_result, "indications_raw", None)
        if indications_raw:
            lines.append(f"Indications: {indications_raw}")

    dosing = getattr(drug_result, "dosing", None)
    if dosing:
        lines.append("Dosing:")
        for dose in dosing[:3]:
            value = getattr(dose, "value", None) or str(dose)
            if value:
                lines.append(f"  - {value}")
    else:
        dosing_raw = getattr(drug_result, "dosing_raw", None)
        if dosing_raw:
            lines.append(f"Dosing: {dosing_raw}")

    contraindications = getattr(drug_result, "contraindications", None)
    if contraindications:
        lines.append("Contraindications:")
        for contra in contraindications[:2]:
            value = getattr(contra, "value", None) or str(contra)
            if value:
                lines.append(f"  - {value}")
    else:
        contraindications_raw = getattr(drug_result, "contraindications_raw", None)
        if contraindications_raw:
            lines.append(f"Contraindications: {contraindications_raw}")

    side_effects = getattr(drug_result, "side_effects", None)
    if side_effects:
        lines.append("Side Effects:")
        for se in side_effects[:4]:
            value = getattr(se, "value", None) or str(se)
            if value:
                lines.append(f"  - {value}")
    else:
        adverse_raw = getattr(drug_result, "adverse_reactions_raw", None)
        if adverse_raw:
            lines.append(f"Adverse reactions: {adverse_raw}")

    interactions = getattr(drug_result, "interactions", None)
    if interactions:
        lines.append("Interactions:")
        for inter in interactions[:3]:
            drug = getattr(inter, "drug", None) or "Drug"
            description = getattr(inter, "description", None) or str(inter)
            lines.append(f"  - {drug}: {description}")
    else:
        interactions_raw = getattr(drug_result, "drug_interactions_raw", None)
        if interactions_raw:
            lines.append(f"Interactions: {interactions_raw}")

    return "\n".join(lines)


def _format_abstracts(abstracts: list[dict | str]) -> str:
    """Format PubMed abstracts into a readable block. Sorted by PMID for cache-key stability."""
    def _sort_key(a: dict | str) -> str:
        if isinstance(a, dict):
            return str(a.get("pmid") or a.get("title") or "")
        return str(a)

    sorted_abstracts = sorted(abstracts, key=_sort_key)
    formatted = []
    for a in sorted_abstracts:
        if isinstance(a, dict):
            title = a.get("title", "No Title")
            text = a.get("abstract", "")
            if isinstance(text, (dict, list)):
                text = str(text)
            text = text or ""
            source = a.get("journal") or a.get("collective_name") or "PubMed"
            year = a.get("year", "n.d.")
            pmid = a.get("pmid", "")
            label = f"[SOURCE: {title}]"
            formatted.append(f"{label}\nTitle: {title}\nSource: {source} ({year})\nPMID: {pmid}\nAbstract: {text}")
        else:
            formatted.append(str(a))
    return "\n\n".join(formatted)


def _format_nice_recs(recs: list[dict]) -> str:
    """Format NICE recommendations."""
    lines = []
    for rec in recs[:5]:
        lines.append(f"- {rec.get('recommendation', '')}")
    return "\n".join(lines)


def _format_vector_context(results: list[SearchResult]) -> str:
    """Format vector search results."""
    if not results:
        return ""
    parts = ["=== INDEXED DOCUMENT EXCERPTS ==="]
    for result in results[:5]:
        parts.append(f"[{result.source}] {result.text}")
    return "\n\n".join(parts)


def _cap_abstracts(abstracts: list[str], max_chars: int = 5000) -> list[str]:
    """Cap total abstract length to avoid token overflow."""
    total = 0
    capped = []
    for abstract in abstracts:
        if total + len(abstract) > max_chars:
            break
        capped.append(abstract)
        total += len(abstract)
    return capped


def _escape_json_string(value: str) -> str:
    """Escape a string for safe JSON embedding."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def build_prompt(
    query: str,
    query_type: str,
    entities: list[str],
    fetched_data: Optional[Any] = None,
    vector_results: Optional[list[SearchResult]] = None,
    condition_context: Optional[str] = None,
    depth: str = "standard",
    response_focus: str = "",
    required_sections: Optional[list[str]] = None,
) -> str:
    """Legacy prompt builder (synchronous path)."""
    guidance_key = query_type
    section_guidance = _SECTION_GUIDANCE.get(guidance_key, "")

    # Format fetched data into a readable block
    data_block = ""
    if fetched_data:
        if hasattr(fetched_data, "drug_data") and fetched_data.drug_data:
            data_block += "=== DRUG DATA ===\n" + _format_drug_block(fetched_data.drug_data) + "\n\n"

    if vector_results:
        data_block += _format_vector_context(vector_results) + "\n\n"

    if not data_block:
        data_block = "(No external data fetched; use training knowledge with caution.)"

    # Assemble the prompt
    condition_block = (
        f"CONDITION CONTEXT: {condition_context}\n\n" if condition_context else ""
    )

    prompt = (
        f"You are a clinical reference assistant.\n"
        f"{APPROVED_SOURCES}\n"
        f"{EVIDENCE_RULES}\n\n"
        f"Query type: {query_type}\n"
        f"Required sections: {', '.join(required_sections or [section_guidance])}\n"
        f"Depth: {depth}\n"
        f"Response focus: {response_focus}\n"
        f"{condition_block}\n"
        f"---\n"
        f"{data_block}\n"
        f"---\n"
        f"Query: {query}\n"
        f"Entities: {', '.join(entities)}\n"
        f"\nRespond in markdown with evidence-based claims supported by the provided data."
    )
    return prompt


def _build_adaptive_data_block(
    query_type: str,
    fetched_data: "FetchedData | None",
    vector_results: "list[SearchResult] | None" = None,
) -> str:
    """Build a formatted data block from fetched API data for injection into the adaptive prompt."""
    parts: list[str] = []

    if fetched_data and not fetched_data.fallback_to_llm:
        if query_type == "drug" and fetched_data.drug_data and fetched_data.drug_data.fetch_success:
            parts.append("=== DRUG DATA (FDA/RxNorm) ===\n" + _format_drug_block(fetched_data.drug_data))
            if fetched_data.condition_data:
                cd = fetched_data.condition_data
                if hasattr(cd, "guideline_abstracts") and cd.guideline_abstracts:
                    parts.append(
                        "=== CONDITION MANAGEMENT GUIDELINES ===\n"
                        + _format_abstracts(cd.guideline_abstracts[:6])
                    )

        elif query_type == "disease" and fetched_data.disease_data and fetched_data.disease_data.fetch_success:
            d = fetched_data.disease_data
            if d.guideline_abstracts:
                parts.append("=== DISEASE GUIDELINES ===\n" + _format_abstracts(d.guideline_abstracts))
            if d.systematic_review_abstracts:
                parts.append("=== SYSTEMATIC REVIEWS ===\n" + _format_abstracts(d.systematic_review_abstracts))
            if d.medlineplus_summary:
                parts.append(f"=== MEDLINEPLUS SUMMARY ===\n{d.medlineplus_summary}")
            if d.nice_recommendations:
                parts.append("=== NICE RECOMMENDATIONS ===\n" + _format_nice_recs(d.nice_recommendations))

        elif query_type == "comparative" and fetched_data.comparative_drug_data:
            for i, drug in enumerate(fetched_data.comparative_drug_data[:3], 1):
                parts.append(f"=== DRUG {i} DATA ===\n" + _format_drug_block(drug))

        elif query_type == "procedure" and fetched_data.procedure_data and fetched_data.procedure_data.fetch_success:
            d = fetched_data.procedure_data
            if d.guideline_abstracts:
                parts.append("=== PROCEDURE GUIDELINES ===\n" + _format_abstracts(d.guideline_abstracts))
            if d.practice_guideline_abstracts:
                parts.append("=== PRACTICE GUIDELINES ===\n" + _format_abstracts(d.practice_guideline_abstracts))

        elif query_type == "evidence" and fetched_data.evidence_data and fetched_data.evidence_data.fetch_success:
            d = fetched_data.evidence_data
            if d.clinical_trial_abstracts:
                parts.append("=== CLINICAL TRIALS / RCTs ===\n" + _format_abstracts(d.clinical_trial_abstracts))
            if d.systematic_review_abstracts:
                parts.append("=== SYSTEMATIC REVIEWS ===\n" + _format_abstracts(d.systematic_review_abstracts))
            if d.guideline_abstracts:
                parts.append("=== GUIDELINES ===\n" + _format_abstracts(d.guideline_abstracts))

        elif query_type == "complex":
            # Complex multi-condition queries: drug data, primary disease, per-comorbidity data
            if fetched_data.drug_data and fetched_data.drug_data.fetch_success:
                parts.append("=== DRUG DATA (FDA/RxNorm) ===\n" + _format_drug_block(fetched_data.drug_data))
            if fetched_data.condition_data and fetched_data.condition_data.fetch_success:
                cd = fetched_data.condition_data
                if getattr(cd, "guideline_abstracts", None):
                    primary_name = getattr(cd, "disease_name", None) or "Primary disease"
                    parts.append(
                        f"=== PRIMARY DISEASE GUIDELINES — {primary_name} ===\n"
                        + _format_abstracts(cd.guideline_abstracts[:3])
                    )
            if getattr(fetched_data, "comorbidity_data", None):
                for cd in fetched_data.comorbidity_data:
                    if cd and cd.fetch_success:
                        comorbidity_name = getattr(cd, "disease_name", None) or "Comorbidity"
                        summary = (getattr(cd, "guideline_summary", None) or "").strip()
                        abstracts = getattr(cd, "guideline_abstracts", None) or []
                        abstract_block = _format_abstracts(abstracts[:3]) if abstracts else ""
                        combined = "\n\n".join(x for x in (summary, abstract_block) if x)
                        parts.append(
                            f"[SOURCE: COMORBIDITY GUIDELINES — {comorbidity_name}]\n"
                            + (combined or "No comorbidity guideline abstract available.")
                        )
            # Evidence tier hint for the LLM to set confidence appropriately
            tier = getattr(fetched_data, "evidence_tier", None)
            if tier and tier != "unknown":
                parts.append(f"[SOURCE: EVIDENCE TIER]\nCascade tier reached: {tier}")

        # Cross-type PubMed pull — collect abstracts from whichever sub-result has them
        _cross_abs: list = []
        for _sub in (fetched_data.drug_data, fetched_data.disease_data, fetched_data.condition_data,
                     fetched_data.procedure_data, fetched_data.evidence_data):
            if _sub and getattr(_sub, "pubmed_abstracts", None):
                _cross_abs.extend(_sub.pubmed_abstracts)  # type: ignore[attr-defined]
        if _cross_abs:
            parts.append("=== PUBMED ARTICLES ===\n" + _format_abstracts(_cross_abs[:15]))

    if not parts:
        parts.append(
            "=== NO EXTERNAL DATA RETRIEVED ===\n"
            "Use your training knowledge. Apply extra caution and set confidence 'low' for claims without a citable source."
        )

    if vector_results:
        parts.append(_format_vector_context(vector_results))

    return "\n\n".join(parts)


def build_adaptive_messages(
    query: str,
    query_type: str,
    fetched_data: "FetchedData | None" = None,
    vector_results: "list[SearchResult] | None" = None,
    required_sections: "list[str] | None" = None,
    condition_context: "str | None" = None,
    comparative_is_drug: bool = False,
) -> tuple[str, str, str]:
    """Build full adaptive-prompt system/data/user triple (legacy + DSPy codepath)."""
    guidance_key = "comparative_drug" if (query_type == "comparative" and comparative_is_drug) else query_type
    section_guidance = _SECTION_GUIDANCE.get(guidance_key, "")

    condition_block = f"CONDITION CONTEXT: {condition_context}\n\n" if condition_context else ""

    required_sections = required_sections or []
    sections_str = " · ".join(required_sections) if required_sections else section_guidance

    hint_section = f"Required sections: {sections_str}\n\n" if required_sections else ""

    system = (
        f"You are a clinical reference assistant.\n"
        f"{APPROVED_SOURCES}\n"
        f"{EVIDENCE_RULES}\n\n"
        f"QUERY TYPE: {query_type}\n"
        f"REQUIRED SECTION AREAS: {section_guidance}\n"
        f"{condition_block}{hint_section}"
        f"Return a JSON object with: bluf (headline, body, key_points, caveats), "
        f"sections (list of section titles), related_topics (5-8 queries), response_focus, tables, flowcharts, "
        f"references (list of sources cited — each with title, source, pmid or null, year or null)."
    )
    data_block = _build_adaptive_data_block(query_type, fetched_data, vector_results)
    user_text = f"Query: {query}"
    return system, data_block, user_text


_STATIC_BLUF_SYSTEM = (
    "You are a clinical reference assistant.\n"
    + APPROVED_SOURCES
    + "\n"
    + EVIDENCE_RULES
    + FORMATTING_RULES
    + "Generate a concise BLUF (bottom-line up front) and a list of section titles "
    + "that a comprehensive answer to this query should contain."
    + _BLUF_ONLY_SCHEMA
)


def build_bluf_only_messages(
    query: str,
    query_type: str,
    fetched_data: "FetchedData | None" = None,
    vector_results: "list[SearchResult] | None" = None,
    condition_context: "str | None" = None,
    comparative_is_drug: bool = False,
) -> tuple[str, str, str, str]:
    """Return (static_system, dynamic_system, data_block, user_text) for the Phase-1 BLUF+titles call."""
    guidance_key = "comparative_drug" if (query_type == "comparative" and comparative_is_drug) else query_type
    section_guidance = _SECTION_GUIDANCE.get(guidance_key, _SECTION_GUIDANCE.get(query_type, ""))

    condition_block = ""
    if condition_context:
        condition_block = (
            f"CONDITION CONTEXT: This is a drug-in-disease query for "
            f'"{condition_context}".\n\n'
        )

    dynamic_system = (
        f"QUERY TYPE: {query_type}\n"
        f"REQUIRED SECTION AREAS: {section_guidance}\n"
        f"{condition_block}"
    )

    data_block = _build_adaptive_data_block(query_type, fetched_data, vector_results)
    user_text = f"Query: {query}"
    return _STATIC_BLUF_SYSTEM, dynamic_system, data_block, user_text


def build_section_messages(
    section_title: str,
    all_section_titles: "list[str]",
    bluf_text: str,
    query: str,
    query_type: str,
    fetched_data: "FetchedData | None" = None,
    vector_results: "list[SearchResult] | None" = None,
) -> tuple[str, str, str, str]:
    """Return (static_system, dynamic_system, data_block, user_text) for one Phase-2 section agent call."""
    other_titles = [t for t in all_section_titles if t != section_title]
    other_str = ", ".join(f'"{t}"' for t in other_titles) if other_titles else "none"

    dynamic_system = (
        f"QUERY TYPE: {query_type}\n"
        f"SECTION TO GENERATE: \"{section_title}\"\n"
        f"OTHER SECTIONS IN THIS RESPONSE (do NOT duplicate their content): {other_str}\n"
        f"ALIGNMENT — keep content consistent with this clinical summary: {bluf_text}\n\n"
        f"Generate ONLY the content for the section \"{section_title}\"."
    )

    data_block = _build_adaptive_data_block(query_type, fetched_data, vector_results)
    user_text = f"Query: {query}\nSection to generate: {section_title}"
    return _STATIC_SECTION_SYSTEM, dynamic_system, data_block, user_text


_STATIC_COMPLEX_BLUF_SYSTEM = (
    "You are a clinical reference assistant for complex multi-condition medical queries.\n"
    + APPROVED_SOURCES
    + "\n"
    + EVIDENCE_RULES
    + FORMATTING_RULES
    + "HARD RULES — read carefully:\n"
    "  1. EVERY claim must trace to a [SOURCE: ...] block in the user-provided data.\n"
    "  2. NEVER write 'no evidence found', 'insufficient evidence', or any equivalent.\n"
    "     If retrieved data is sparse for a comorbidity, write a SHORT BLUF that says\n"
    "     'Limited to case reports / drug-class data — see Conflict section for details'\n"
    "     and let the per-section agent expand.\n"
    "  4. Output JSON only — schema below."
    + _BLUF_ONLY_SCHEMA
)


def build_complex_bluf_messages(
    query: str,
    drug: str,
    primary_disease: str,
    comorbidity_list: list[str],
    fetched_data: "FetchedData | None" = None,
    vector_results: "list[SearchResult] | None" = None,
) -> tuple[str, str, str, str]:
    """Phase-1 BLUF for complex multi-condition queries. Returns (static_system, dynamic_system, data_block, user_text)."""
    section_guidance = _SECTION_GUIDANCE["complex"]
    co_capped = (comorbidity_list or [])[:4]
    forced_titles = (
        [f"Baseline Rule for {drug} in {primary_disease}"]
        + [f"Conflict with {c}" for c in co_capped]
        + ["Synthesised Recommendation", "Monitoring & Red Flags"]
    )
    forced_block = "REQUIRED section_titles (return EXACTLY these, in this order): " + " | ".join(forced_titles)

    dynamic_system = (
        f"QUERY TYPE: complex\n"
        f"REQUIRED SECTION AREAS: {section_guidance}\n"
        f"{forced_block}\n\n"
        f"  3. Comorbidities to address: {co_capped}.\n"
    )
    data_block = _build_adaptive_data_block("complex", fetched_data, vector_results)
    user_text = f"Query: {query}\nPrimary drug/intervention: {drug}\nPrimary disease: {primary_disease}\nComorbidities: {co_capped}"
    return _STATIC_COMPLEX_BLUF_SYSTEM, dynamic_system, data_block, user_text


_STATIC_COMPLEX_SECTION_SYSTEM = (
    "You are a clinical reference assistant generating ONE section of a complex multi-condition response.\n"
    + APPROVED_SOURCES
    + "\n"
    + EVIDENCE_RULES
    + FORMATTING_RULES
    + "\nHARD RULES:\n"
    "  1. EVERY content_item.source MUST match a [SOURCE: ...] label in the data block. "
    "     Sources outside the data block are FORBIDDEN.\n"
    "  2. content_item.confidence MUST be one of high|moderate|low, assigned based on SOURCE QUALITY:\n"
    "     - 'high' for guideline/clinical practice standard sources\n"
    "     - 'moderate' for RCTs, systematic reviews, meta-analyses\n"
    "     - 'low' for case reports, observational studies, animal studies, extrapolation\n"
    "  4. NEVER write 'no evidence' or 'insufficient evidence'. If fetched data is thin, cite the "
    "     drug class entry (RxNorm) or generic FDA label warnings — never invent.\n"
    "  5. Output JSON only."
    + _STATIC_SECTION_SCHEMA
)


def build_complex_section_messages(
    section_title: str,
    all_section_titles: list[str],
    bluf_text: str,
    query: str,
    drug: str,
    primary_disease: str,
    comorbidity_list: list[str],
    fetched_data: "FetchedData | None" = None,
    vector_results: "list[SearchResult] | None" = None,
) -> tuple[str, str, str, str]:
    """Phase-2 section agent for complex queries. Returns (static_system, dynamic_system, data_block, user_text)."""
    other_titles = [t for t in all_section_titles if t != section_title]
    other_str = ", ".join(f'"{t}"' for t in other_titles) if other_titles else "none"
    tier = getattr(fetched_data, "evidence_tier", "unknown") if fetched_data else "unknown"

    tier_description = {
        "guideline": "guidelines and clinical practice standards",
        "rct": "randomized controlled trials and systematic reviews",
        "review": "systematic reviews and meta-analyses",
        "case_report": "case reports and observational studies",
        "drug_class": "drug class data (RxNorm, FDA labels)",
        "unknown": "unverified sources",
    }.get(tier, "limited sources")

    target_comorbidity = None
    for c in comorbidity_list or []:
        if c.lower() in section_title.lower():
            target_comorbidity = c
            break

    dynamic_system = (
        f"QUERY TYPE: complex\n"
        f"SECTION TO GENERATE: \"{section_title}\"\n"
        f"OTHER SECTIONS (do NOT duplicate): {other_str}\n"
        f"ALIGNMENT — keep consistent with this BLUF: {bluf_text}\n"
        f"AVAILABLE EVIDENCE: {tier_description}\n"
        + (f"FOCUS COMORBIDITY: {target_comorbidity}\n" if target_comorbidity else "")
        + (f"  3. If evidence is from lower tiers (case_report/drug_class), note it in the text:\n"
           f"     'Based on limited evidence from {tier.replace('_', ' ')}. Verify against local guidelines.'\n"
           if tier in ("case_report", "drug_class") else "")
    )

    data_block = _build_adaptive_data_block("complex", fetched_data, vector_results)
    user_text = f"Query: {query}\nSection to generate: {section_title}"
    return _STATIC_COMPLEX_SECTION_SYSTEM, dynamic_system, data_block, user_text
