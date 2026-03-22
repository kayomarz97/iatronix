from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from app.services.data_fetcher import FetchedData

APPROVED_SOURCES = """
APPROVED CITATION SOURCES (you MUST only cite from this list):
- Guidelines: NICE, AHA/ACC, ESC, WHO, IDSA, NCCN, ACOG, GOLD, KDIGO, ADA
- Regulatory: FDA, EMA, MHRA, CDSCO
- Databases: UpToDate, BMJ Best Practice, Cochrane Library, PubMed (systematic reviews/meta-analyses only)
- Pharmacology: FDA drug labels, BNF, Micromedex, Indian Pharmacopoeia
"""

EVIDENCE_RULES = """
CRITICAL: Every factual claim must include:
- loe: Level of Evidence (I, II-1, II-2, II-3, III per USPSTF)
- cor: Class of Recommendation (I, IIa, IIb, III-no-benefit, III-harm per AHA/ACC)
- source: Name of guideline/database (MUST be from approved sources list)
- source_year: Year of the cited guideline/edition
- confidence: "high", "moderate", or "low"
If you cannot cite an approved source for a claim, you MUST set confidence to "low"
and prepend the claim with "[Unverified]".

IMPORTANT: Do NOT include LOE, COR, source names, or evidence markers inline in
"value" text fields. The "value" field should contain ONLY the clinical content.
Put evidence metadata ONLY in the dedicated JSON fields. For example:
  WRONG: {{"value": "Reduces HbA1c by 1-1.5% (LOE I, ADA 2024)", ...}}
  RIGHT: {{"value": "Reduces HbA1c by 1-1.5%", "loe": "I", "source": "ADA", "source_year": 2024, ...}}

When evidence is insufficient or absent:
- Set confidence to "low"
- Do NOT fabricate data, statistics, or trial names
"""

# ──────────────────────────────────────────────
# GENERATE-mode prompts (existing, unchanged)
# ──────────────────────────────────────────────

DRUG_PROMPT = """You are a clinical pharmacology reference assistant.
{approved_sources}
{evidence_rules}

Be COMPREHENSIVE. Cover ALL of the following thoroughly:
- Mechanism of action: full pharmacodynamic detail
- ALL approved indications (FDA and major international), including off-label uses with evidence
- ALL dosing routes, forms, and regimens (oral, IV, SC, etc.) with dose ranges for each indication
- ALL significant contraindications (absolute and relative)
- ALL common AND serious side effects with approximate incidence rates
- ALL clinically significant drug interactions (aim for at least 8-10 major ones)
- Full pharmacokinetics (absorption, distribution, metabolism, excretion, half-life)
- ALL special populations (renal impairment, hepatic impairment, pediatric, geriatric, pregnancy, lactation)
- ALL recommended monitoring parameters
Do NOT omit sections. Populate every array with multiple entries where applicable.

Respond with a JSON object matching this EXACT structure:
{{
  "drug_name": "string",
  "drug_class": "string or null",
  "mechanism_of_action": {{"value": "string", "loe": "string", "cor": "string", "source": "string", "source_year": int_or_null, "confidence": "string"}} or null,
  "indications": [{{"value": "string", "loe": "string", "cor": "string", "source": "string", "source_year": int_or_null, "confidence": "string"}}],
  "dosing": [{{"value": "string", "loe": "string", "cor": "string", "source": "string", "source_year": int_or_null, "confidence": "string", "route": "string or null", "frequency": "string or null"}}],
  "contraindications": [{{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "..."}}],
  "side_effects": [{{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "..."}}],
  "interactions": [{{"drug": "string", "severity": "major|moderate|minor", "description": "string", "evidence": {{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "..."}} or null}}],
  "pharmacokinetics": {{"value": "...", ...}} or null,
  "special_populations": [{{"value": "...", ...}}],
  "monitoring": [{{"value": "...", ...}}],
  "references": [{{"source": "string", "title": "string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

DISEASE_PROMPT = """You are a senior clinician writing a comprehensive disease reference for medical trainees.
{approved_sources}
{evidence_rules}

MANDATORY CLINICAL ORDER: etiology → clinical_features → pathophysiology → diagnostic_criteria → treatment → complications → prognosis

DEPTH REQUIREMENTS — every section MUST be fully populated:
- etiology: 4-8 entries covering ALL causes (genetic, autoimmune, infectious, structural, toxic, idiopathic, risk factors)
- pathophysiology: detailed mechanistic explanation (≥150 words) — vasoconstriction, inflammation, fibrosis, remodeling, hemodynamic changes, cellular/molecular mechanisms
- clinical_features: 6-10 entries — ALL symptoms and signs PLUS if this disease has a CLASSIFICATION SYSTEM (WHO groups, NYHA classes, Child-Pugh, GOLD stages, etc.) include EVERY CLASS/STAGE with its specific criteria as separate entries
- diagnostic_criteria: 5-8 entries with SPECIFIC threshold values (e.g., "mPAP ≥ 25 mmHg at rest on right heart catheterization", NOT just "elevated pressures")
- treatment.first_line: 3-6 entries with SPECIFIC drug name + dose + route + frequency (NOT drug class names)
  Example RIGHT: "Ambrisentan (ERA) 5-10 mg orally once daily, or Bosentan 62.5 mg BD × 4 weeks then 125 mg BD"
  Example WRONG: "Endothelin receptor antagonists are used"
- treatment.second_line: 2-4 specific drugs with doses
- treatment.non_pharmacological: 3+ entries (oxygen therapy, exercise, anticoagulation, transplant criteria, etc.)
- complications: 4-6 entries
- CLASSIFICATION SYSTEMS: if this disease has WHO/staging/functional class criteria, list each class explicitly in clinical_features

Do NOT omit any section. If evidence is limited, use loe="III", confidence="moderate", source="Clinical consensus".

Respond with a JSON object matching this EXACT structure:
{{
  "disease_name": "string",
  "icd_10": "string or null",
  "etiology": [{{"value": "string", "loe": "string", "cor": "string", "source": "string", "source_year": int_or_null, "confidence": "string"}}],
  "pathophysiology": {{"value": "string", "loe": "string", "cor": "string", "source": "string", "source_year": int_or_null, "confidence": "string"}} or null,
  "epidemiology": {{"value": "...", ...}} or null,
  "clinical_features": [{{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "..."}}],
  "diagnostic_criteria": [{{"value": "...", ...}}],
  "treatment": {{
    "first_line": [{{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "...", "drug_names": ["string"]}}],
    "second_line": [{{"value": "...", ..., "drug_names": ["string"]}}],
    "adjunctive": [{{"value": "...", ..., "drug_names": ["string"]}}],
    "non_pharmacological": [{{"value": "...", ...}}]
  }},
  "complications": [{{"value": "...", ...}}],
  "prognosis": {{"value": "...", ...}} or null,
  "references": [{{"source": "string", "title": "string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

COMPARATIVE_PROMPT = """You are a clinical comparison assistant.
{approved_sources}
{evidence_rules}

Be COMPREHENSIVE. Compare the entities thoroughly across ALL of the following dimensions:
- Efficacy (primary outcomes, NNT where available)
- Safety profile (side effects, black box warnings, serious adverse events)
- Dosing convenience (frequency, route, titration complexity)
- Drug interactions
- Contraindications
- Cost and availability
- Special populations (renal/hepatic impairment, elderly, pediatric, pregnancy)
- Onset of action and pharmacokinetics
- Guideline positioning and recommendations
- Patient adherence and tolerability
Provide a thorough clinical preference summary with supporting rationale.
Do NOT omit dimensions. Include as many comparison dimensions as clinically relevant.

Respond with a JSON object matching this EXACT structure:
{{
  "entities_compared": ["string", "string"],
  "comparison_type": "string or null",
  "summary": {{"value": "string", "loe": "string", "cor": "string", "source": "string", "source_year": int_or_null, "confidence": "string"}} or null,
  "detailed_comparison": [
    {{
      "dimension": "string (e.g., efficacy, safety, cost)",
      "values": {{
        "entity_name_1": {{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "..."}},
        "entity_name_2": {{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "..."}}
      }}
    }}
  ],
  "clinical_preference": {{"value": "...", ...}} or null,
  "references": [{{"source": "string", "title": "string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

GENERAL_PROMPT = """You are a medical knowledge assistant.
{approved_sources}
{evidence_rules}

This query does not fit a specific drug/disease/comparative pattern. Provide a structured response.

Respond with a JSON object matching this EXACT structure:
{{
  "summary": "markdown string with your main answer",
  "key_points": ["bullet point 1", "bullet point 2"],
  "related_drugs": ["drug_name_1", "drug_name_2"],
  "related_conditions": ["condition_1", "condition_2"],
  "confidence": "high|moderate|low",
  "references": [{{"source": "string", "title": "string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

PROMPTS = {
    "drug": DRUG_PROMPT,
    "disease": DISEASE_PROMPT,
    "comparative": COMPARATIVE_PROMPT,
    "general": GENERAL_PROMPT,
}

# ──────────────────────────────────────────────
# FORMAT-mode prompts (used when API data fetched)
# ──────────────────────────────────────────────

DRUG_FORMAT_PROMPT = """You are a medical JSON formatter. Raw data from authoritative sources is provided below.
Your ONLY job: extract and format this data into the required JSON schema.
- Do NOT add facts not present in the source data
- Do NOT fabricate drug names, doses, trial names, or statistics
- For fields where source data is absent, use [] or null
- Set source="FDA drug label", source_year={fda_label_source_year} for FDA-derived claims
- Set loe="I" and cor="I" for FDA-approved indications; loe="II-2" for adverse event frequency data
- For claims from PubMed guidelines, set source=the society name (e.g., "AHA/ACC", "ADA", "ESC") and source_year from the abstract year

{evidence_rules}

=== DRUG DATA SOURCE: {data_source} ===
Drug Name: {generic_name} ({brand_name})
Drug Class: {drug_class}
Mechanism of Action: {mechanism_raw}
Indications and Usage: {indications_raw}
Dosage and Administration: {dosing_raw}
Contraindications: {contraindications_raw}
Warnings / Adverse Reactions: {adverse_reactions_raw}
Top Reported Adverse Events (FAERS): {top_adverse_events}
Drug Interactions: {drug_interactions_raw}
Pharmacokinetics: {pharmacokinetics_raw}
Special Populations: {special_populations_raw}
FDA Label Year: {fda_label_source_year}

=== PUBLISHED GUIDELINES MENTIONING THIS DRUG (PubMed) ===
{guideline_abstracts_formatted}

Respond ONLY with a JSON object matching this EXACT structure:
{{
  "drug_name": "string",
  "drug_class": "string or null",
  "mechanism_of_action": {{"value": "string", "loe": "string", "cor": "string", "source": "string", "source_year": int_or_null, "confidence": "string"}} or null,
  "indications": [{{"value": "string", "loe": "string", "cor": "string", "source": "string", "source_year": int_or_null, "confidence": "string"}}],
  "dosing": [{{"value": "string", "loe": "string", "cor": "string", "source": "string", "source_year": int_or_null, "confidence": "string", "route": "string or null", "frequency": "string or null"}}],
  "contraindications": [{{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "..."}}],
  "side_effects": [{{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "..."}}],
  "interactions": [{{"drug": "string", "severity": "major|moderate|minor", "description": "string", "evidence": {{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "..."}} or null}}],
  "pharmacokinetics": {{"value": "...", ...}} or null,
  "special_populations": [{{"value": "...", ...}}],
  "monitoring": [{{"value": "...", ...}}],
  "references": [{{"source": "string", "title": "string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

DISEASE_FORMAT_PROMPT = """You are a senior clinician creating a comprehensive disease reference card.

Your sources are below. Use them as PRIMARY evidence (cite with society + year). Where the abstracts are incomplete, supplement with your medical knowledge — especially for classification systems, pathophysiology mechanisms, and specific drug doses. Mark supplemented content with source="Clinical consensus", loe="III", confidence="moderate".

MANDATORY CLINICAL ORDER: etiology → clinical_features → pathophysiology → diagnostic_criteria → treatment → complications → prognosis

DEPTH REQUIREMENTS — every section MUST be fully populated:
- etiology: 4-8 entries covering ALL causes (genetic, autoimmune, infectious, structural, toxic, idiopathic, risk factors)
- pathophysiology: detailed mechanistic explanation (≥150 words) — vasoconstriction, inflammation, fibrosis, remodeling, hemodynamic changes; PRIORITISE data from retrieved guidelines
- clinical_features: 6-10 entries — ALL symptoms/signs PLUS if this disease has a CLASSIFICATION SYSTEM (WHO groups, NYHA classes, Child-Pugh, GOLD stages, ERS/ESC risk strata etc.) include EVERY CLASS with its specific criteria as separate entries
- diagnostic_criteria: 5-8 entries with SPECIFIC threshold values (e.g., "mPAP ≥ 25 mmHg at rest on RHC" NOT just "elevated pressures")
- treatment.first_line: 3-6 entries — SPECIFIC drug name + dose + route + frequency, NOT drug class names
  RIGHT: "Ambrisentan (ERA): 5–10 mg orally once daily; or Macitentan 10 mg once daily"
  WRONG: "Endothelin receptor antagonists are recommended"
- treatment.second_line: 2-4 specific drugs with doses and combination regimens
- treatment.non_pharmacological: 3+ entries (O2 therapy, cardiac rehab, anticoagulation, transplant criteria)
- complications: 4-6 entries
- NEVER leave etiology, pathophysiology, clinical_features, diagnostic_criteria, or treatment empty

{evidence_rules}

=== RETRIEVED GUIDELINE DATA (ACC/AHA/ESC/ERS/NICE/WHO/ADA/IDSA etc. via PubMed) ===
{guideline_abstracts_formatted}

=== SYSTEMATIC REVIEWS / META-ANALYSES ===
{systematic_review_abstracts_formatted}

=== NICE RECOMMENDATIONS ===
{nice_recommendations_formatted}

=== MEDLINEPLUS / CLASSIFICATION DATA ===
{medlineplus_summary}

Respond ONLY with a JSON object matching this EXACT structure:
{{
  "disease_name": "string",
  "icd_10": "string or null",
  "etiology": [{{"value": "string", "loe": "string", "cor": "string", "source": "string", "source_year": int_or_null, "confidence": "string"}}],
  "pathophysiology": {{"value": "string", "loe": "string", "cor": "string", "source": "string", "source_year": int_or_null, "confidence": "string"}} or null,
  "epidemiology": {{"value": "...", ...}} or null,
  "clinical_features": [{{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "..."}}],
  "diagnostic_criteria": [{{"value": "...", ...}}],
  "treatment": {{
    "first_line": [{{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "...", "drug_names": ["string"]}}],
    "second_line": [{{"value": "...", ..., "drug_names": ["string"]}}],
    "adjunctive": [{{"value": "...", ..., "drug_names": ["string"]}}],
    "non_pharmacological": [{{"value": "...", ...}}]
  }},
  "complications": [{{"value": "...", ...}}],
  "prognosis": {{"value": "...", ...}} or null,
  "references": [{{"source": "string", "title": "string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

COMPARATIVE_FORMAT_PROMPT = """You are a medical JSON formatter comparing two entities using retrieved source data.
Compare them accurately. Do NOT invent efficacy statistics not present in the source data.

{evidence_rules}

=== {entity1} SOURCE DATA ===
{drug1_data_block}

=== {entity2} SOURCE DATA ===
{drug2_data_block}

Respond ONLY with a JSON object comparing "{entity1}" vs "{entity2}":
{{
  "entities_compared": ["{entity1}", "{entity2}"],
  "comparison_type": "string or null",
  "summary": {{"value": "string", "loe": "string", "cor": "string", "source": "string", "source_year": int_or_null, "confidence": "string"}} or null,
  "detailed_comparison": [
    {{
      "dimension": "string",
      "values": {{
        "{entity1}": {{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "..."}},
        "{entity2}": {{"value": "...", "loe": "...", "cor": "...", "source": "...", "source_year": null, "confidence": "..."}}
      }}
    }}
  ],
  "clinical_preference": {{"value": "...", ...}} or null,
  "references": [{{"source": "string", "title": "string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""


# ──────────────────────────────────────────────
# Formatting helpers for injecting fetched data
# ──────────────────────────────────────────────


def _format_abstracts(abstracts: list) -> str:
    if not abstracts:
        return "None retrieved."
    lines = []
    for i, a in enumerate(abstracts, 1):
        society = a.get("collective_name") or a.get("journal") or "Unknown Society"
        year = a.get("year", "")
        pmid = a.get("pmid", "")
        title = a.get("title", "No title")
        abstract = a.get("abstract", "")
        lines.append(f"[{i}] {title}")
        lines.append(f"    Source: {society} {year}  PMID:{pmid}")
        lines.append(f"    {abstract}")
    return "\n".join(lines)


def _format_nice_recs(recs: list) -> str:
    if not recs:
        return "Not available (NICE API key not configured or no results)."
    lines = []
    for r in recs:
        title = r.get("title", "")
        text = r.get("text", "")
        year = r.get("year", "")
        lines.append(f"- [{title} {year}]: {text}")
    return "\n".join(lines)


def _format_drug_block(d) -> str:
    if d is None:
        return "No data retrieved."
    return (
        f"Drug: {d.generic_name or 'Unknown'} ({d.brand_name or '-'})\n"
        f"Class: {d.drug_class or d.drug_class_rxnorm or 'Not specified'}\n"
        f"Source: {d.data_source.upper()}  Year: {d.fda_label_source_year or 'Unknown'}\n"
        f"Mechanism: {d.mechanism_raw or 'Not available'}\n"
        f"Indications: {d.indications_raw or 'Not available'}\n"
        f"Dosing: {d.dosing_raw or 'Not available'}\n"
        f"Contraindications: {d.contraindications_raw or 'Not available'}\n"
        f"Adverse Reactions: {d.adverse_reactions_raw or 'Not available'}\n"
        f"Top FAERS Events: {', '.join(d.top_adverse_events[:6]) if d.top_adverse_events else 'Not available'}\n"
        f"Drug Interactions: {d.drug_interactions_raw or 'Not available'}\n"
        f"Pharmacokinetics: {d.pharmacokinetics_raw or 'Not available'}\n"
        f"Special Populations: {d.special_populations_raw or 'Not available'}\n"
        f"Guidelines: {_format_abstracts(d.guideline_abstracts[:3])}"
    )


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────


def build_prompt(
    query: str, query_type: str, fetched_data: "FetchedData | None" = None
) -> str:
    """Build a prompt for the LLM.

    If fetched_data is provided and fetch succeeded → format-mode prompt (shorter, cheaper).
    Otherwise → generate-mode prompt (existing behaviour, full knowledge generation).
    """
    if fetched_data is not None and not fetched_data.fallback_to_llm:
        result = _build_format_prompt(query, query_type, fetched_data)
        if result is not None:
            return result

    return _build_generate_prompt(query, query_type)


def _build_generate_prompt(query: str, query_type: str) -> str:
    template = PROMPTS[query_type]
    return template.format(
        query=query,
        approved_sources=APPROVED_SOURCES,
        evidence_rules=EVIDENCE_RULES,
    )


def _build_format_prompt(
    query: str, query_type: str, fetched_data: "FetchedData"
) -> str | None:
    """Build a format-mode prompt. Returns None if the data is insufficient."""
    if (
        query_type == "drug"
        and fetched_data.drug_data
        and fetched_data.drug_data.fetch_success
    ):
        d = fetched_data.drug_data
        return DRUG_FORMAT_PROMPT.format(
            query=query,
            evidence_rules=EVIDENCE_RULES,
            data_source=d.data_source.upper(),
            generic_name=d.generic_name or "Unknown",
            brand_name=d.brand_name or "Unknown",
            drug_class=d.drug_class or d.drug_class_rxnorm or "Not specified",
            mechanism_raw=d.mechanism_raw or "Not available in source",
            indications_raw=d.indications_raw or "Not available",
            dosing_raw=d.dosing_raw or "Not available",
            contraindications_raw=d.contraindications_raw or "Not available",
            adverse_reactions_raw=d.adverse_reactions_raw or "Not available",
            top_adverse_events=", ".join(d.top_adverse_events[:8])
            if d.top_adverse_events
            else "Not available",
            drug_interactions_raw=d.drug_interactions_raw or "Not available",
            pharmacokinetics_raw=d.pharmacokinetics_raw or "Not available",
            special_populations_raw=d.special_populations_raw or "Not available",
            fda_label_source_year=d.fda_label_source_year or "Unknown",
            guideline_abstracts_formatted=_format_abstracts(d.guideline_abstracts),
        )

    if (
        query_type == "disease"
        and fetched_data.disease_data
        and fetched_data.disease_data.fetch_success
    ):
        d = fetched_data.disease_data
        return DISEASE_FORMAT_PROMPT.format(
            query=query,
            evidence_rules=EVIDENCE_RULES,
            guideline_abstracts_formatted=_format_abstracts(d.guideline_abstracts),
            systematic_review_abstracts_formatted=_format_abstracts(
                d.systematic_review_abstracts
            ),
            nice_recommendations_formatted=_format_nice_recs(d.nice_recommendations),
            medlineplus_summary=d.medlineplus_summary or "Not available",
        )

    if query_type == "comparative" and fetched_data.comparative_drug_data:
        drugs = fetched_data.comparative_drug_data
        d1 = drugs[0] if len(drugs) > 0 else None
        d2 = drugs[1] if len(drugs) > 1 else None
        entity1 = (d1.generic_name or "Drug 1") if d1 else "Drug 1"
        entity2 = (d2.generic_name or "Drug 2") if d2 else "Drug 2"
        return COMPARATIVE_FORMAT_PROMPT.format(
            query=query,
            evidence_rules=EVIDENCE_RULES,
            entity1=entity1,
            entity2=entity2,
            drug1_data_block=_format_drug_block(d1),
            drug2_data_block=_format_drug_block(d2),
        )

    return None


def get_prompt_version() -> int:
    return settings.prompt_version
