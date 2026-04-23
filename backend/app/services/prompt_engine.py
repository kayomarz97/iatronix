from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.config import settings

# ──────────────────────────────────────────────
# Drug query focus-hint helper
# ──────────────────────────────────────────────

_CONVERSION_RE = re.compile(
    r"\b(?:convert|conversion|equianalges|opioid\s+rotation|switching\s+(?:from|to)|opioid\s+switch|steroid\s+equivalent|morphine\s+equivalent)\b",
    re.IGNORECASE,
)
_MAX_DOSE_RE = re.compile(
    r"\b(?:max(?:imum)?\s+dose|highest\s+dose|dose\s+limit|ceiling\s+dose|max\s+daily)\b",
    re.IGNORECASE,
)
_RENAL_RE = re.compile(
    r"\b(?:renal|kidney|CKD|GFR|creatinine|dialysis|eGFR)\b",
    re.IGNORECASE,
)
_INTERACTION_RE = re.compile(
    r"\b(?:interaction|combination|together|with\s+\w+|serotonin\s+syndrome|QT)\b",
    re.IGNORECASE,
)


def _drug_focus_hint(query: str) -> str:
    """Return a focus instruction based on drug query intent keywords."""
    if _CONVERSION_RE.search(query):
        return (
            "FOCUS: The user is asking about DOSE CONVERSION / EQUIANALGESIC equivalency. "
            "Prioritise the dosing section with a clear conversion table or ratio. "
            "Include equianalgesic dose, conversion factor, and any dose-reduction safety margins. "
            "Other sections can be brief."
        )
    if _MAX_DOSE_RE.search(query):
        return (
            "FOCUS: The user is asking about MAXIMUM DOSE. "
            "Prioritise the dosing section with explicit maximum daily dose, route-specific limits, "
            "and toxicity thresholds. Include pediatric and adult limits if available."
        )
    if _RENAL_RE.search(query):
        return (
            "FOCUS: The user is asking about RENAL DOSING ADJUSTMENT. "
            "Prioritise the dosing section with GFR-based dose adjustments and special_populations "
            "with renal impairment guidance. Other sections can be brief."
        )
    if _INTERACTION_RE.search(query):
        return (
            "FOCUS: The user is asking about DRUG INTERACTIONS. "
            "Prioritise the interactions section with specific interacting drugs, mechanisms, "
            "and clinical management. Other sections can be brief."
        )
    return ""


_DX_RE = re.compile(
    r"\b(?:diagnosis|dx|workup|evaluation|initial|approach|criteria|investigation|test)\b",
    re.IGNORECASE,
)
_TX_RE = re.compile(
    r"\b(?:treatment|management|therapy|tx|manage|treat)\b",
    re.IGNORECASE,
)
_PROGNOSIS_RE = re.compile(
    r"\b(?:prognosis|outcome|survival|course|mortality|morbidity)\b",
    re.IGNORECASE,
)
_COMPLICATION_RE = re.compile(
    r"\b(?:complication|risk|adverse|sequelae|sequalae)\b",
    re.IGNORECASE,
)


def _disease_focus_hint(query: str) -> str:
    """Return a focus instruction based on disease query intent keywords."""
    if _DX_RE.search(query):
        return (
            "FOCUS: The user is asking about DIAGNOSIS. "
            "Prioritise diagnostic_criteria and clinical_features sections with specific thresholds, "
            "test sensitivity/specificity, and red flags. Keep treatment and prognosis brief."
        )
    if _TX_RE.search(query):
        return (
            "FOCUS: The user is asking about TREATMENT/MANAGEMENT. "
            "Prioritise treatment sections (first_line, second_line, adjunctive) with specific drugs, "
            "doses, routes, and durations. Keep etiology and pathophysiology brief."
        )
    if _PROGNOSIS_RE.search(query):
        return (
            "FOCUS: The user is asking about PROGNOSIS. "
            "Prioritise prognosis section with specific mortality rates, recurrence rates, "
            "and prognostic scoring systems. Keep other sections concise."
        )
    if _COMPLICATION_RE.search(query):
        return (
            "FOCUS: The user is asking about COMPLICATIONS. "
            "Prioritise complications section with incidence rates, risk factors, and management. "
            "Keep etiology and pathophysiology brief."
        )
    return ""


if TYPE_CHECKING:
    from app.services.data_fetcher import DiseaseFetchResult, FetchedData
    from app.services.vector_search import SearchResult

APPROVED_SOURCES = """
APPROVED CITATION SOURCES (you MUST only cite from this list):
- Guidelines: NICE, AHA/ACC, ESC, WHO, IDSA, NCCN, ACOG, GOLD, KDIGO, ADA
- Regulatory: FDA, EMA, MHRA, CDSCO
- Databases: UpToDate, BMJ Best Practice, Cochrane Library, PubMed (systematic reviews/meta-analyses only)
- Pharmacology: FDA drug labels, BNF, Micromedex, Indian Pharmacopoeia
"""

EVIDENCE_RULES = """
CRITICAL: Every factual claim must include loe, cor, source, source_year, confidence.

LOE (Level of Evidence — USPSTF):
- "I"    = RCTs, systematic reviews, meta-analyses (e.g. DAPA-HF trial, Cochrane review)
- "II-1" = Well-designed controlled trials without randomization
- "II-2" = Cohort or case-control studies
- "II-3" = Case series, uncontrolled studies
- "III"  = Expert opinion, physiologic rationale, consensus statements

COR (Class of Recommendation — AHA/ACC):
- "I"             = Strong evidence of benefit — ONLY use when ≥1 large RCT or meta-analysis supports the claim
- "IIa"           = Weight of evidence favors benefit — use when multiple observational studies or smaller RCTs support
- "IIb"           = Benefit uncertain — use when evidence is limited, conflicting, or from expert opinion only
- "III-no-benefit" = Not useful — evidence shows no benefit
- "III-harm"       = Harmful — evidence shows risk outweighs benefit

MATCHING RULES:
- LOE I claims → COR I or IIa (never IIb)
- LOE III claims → COR should be null (do not assign class of recommendation for expert opinion)
- LOE II-1 or II-2 claims → COR IIa or IIb depending on strength of evidence
- If you cannot name a specific RCT/guideline → LOE III, COR null, confidence "low"
- When evidence is LOE III or observational without guideline assignment: set cor = null.
- Only assign COR when a named guideline explicitly assigns it or LOE is I or II-1.

source: Name the SPECIFIC guideline (e.g. "AHA/ACC 2022 Heart Failure Guideline", "NICE CG181")
source_year: Year of the cited guideline/edition

confidence:
- "high"     = Claim backed by LOE I or II-1 evidence from a named source
- "moderate" = Claim backed by LOE II-2/II-3 or well-established clinical practice
- "low"      = Expert opinion, limited evidence, or no specific source

IMPORTANT: Do NOT include LOE, COR, source names, or evidence markers inline in
"value" text fields. Put evidence metadata ONLY in the dedicated JSON fields:
  WRONG: {{"value": "Reduces HbA1c by 1-1.5% (LOE I, ADA 2024)", ...}}
  RIGHT: {{"value": "Reduces HbA1c by 1-1.5%", "loe": "I", "source": "ADA", "source_year": 2024, ...}}

When evidence is insufficient: set confidence "low", loe "III", cor "IIb".
Do NOT fabricate trial names, statistics, or sources.

RECENCY RULE: If you have a guideline published within the last 2 years from AHA, ADA, ESC,
NICE, WHO, IDSA, NCCN, GOLD, or ACS — cite it preferentially over older guidelines even if
the older one has more citations. Always state the publication year. If two organizations have
conflicting guidelines, cite both and note the difference. Do NOT cite a guideline unless
its abstract appears in the data block above.
"""

JSON_CONTRACT_RULES = """
JSON CONTRACT RULES — apply to every field in your response:
- String fields: output the clinical value ONLY — no inline LOE markers, no citation suffixes, no parenthetical evidence in the value string
- Array fields: output [] when no data is available — NEVER output ["None"], ["N/A"], ["Unknown"], or ["Not applicable"]
- Nullable fields (marked "or null"): output null — NEVER output "", "N/A", "none", or "not available"
- Enum fields: output ONLY the exact enum value — e.g. "high" not "High", "I" not "Level I"
- drug_names arrays: generic names only, no doses, no brand names (e.g. ["metformin"] not ["Metformin 500mg (Glucophage)"])
- related_drugs arrays: generic INN names only — no brand names, no dosing
- pmid fields: numeric string only, no "PMID:" prefix (e.g. "38293847") — output null if unavailable
- url fields in references: always output null — the backend generates all URLs from verified metadata; do NOT invent or guess URLs
- Do NOT add keys not listed in the schema below
- Do NOT reorder top-level keys
- Output raw JSON only — no markdown fences, no explanatory prose before or after the JSON object
"""

# ──────────────────────────────────────────────
# GENERATE-mode prompts (existing, unchanged)
# ──────────────────────────────────────────────

DRUG_PROMPT = """You are a clinical pharmacology reference assistant.
{approved_sources}
{evidence_rules}
{json_contract_rules}

{condition_context_block}

MANDATORY DRUG IDENTITY RULE: drug_class and mechanism_of_action MUST always be populated — never null.
- drug_class: state the pharmacological group (e.g. "HMG-CoA reductase inhibitor (statin)", "ACE inhibitor", "Beta-1 selective blocker")
- mechanism_of_action: include specific receptor/enzyme target + physiological effect (e.g. "Competitively inhibits HMG-CoA reductase, reducing hepatic cholesterol synthesis and upregulating LDL receptors")

Ensure all arrays have sufficient entries to fully answer the query. Sparse or incomplete responses will be rejected.

ANSWER STRATEGY — Read the query carefully and follow these steps:
1. BLUF FIRST: Write "bluf" as 1-3 sentences that DIRECTLY answer the specific question asked.
   Example — "metformin for diabetes": "Metformin is first-line for type 2 diabetes (ADA 2024): 500 mg BD, titrate to 1000 mg BD; reduces HbA1c 1.0-1.5%."
   Example — "warfarin interactions": "Warfarin has narrow therapeutic index with major interactions with NSAIDs, antibiotics (fluoroquinolones, metronidazole), and amiodarone — all precipitate bleeding."

2. EXPAND on the SPECIFIC AREA the user asked about — give it the MOST detail:
   - If they asked about dosing → dosing array should have 6+ entries with every route/regimen
   - If they asked about interactions → interactions array should have 10+ entries
   - If they asked about side effects → side_effects array should be exhaustive
   - If they asked about a specific indication → indications should detail that indication first, then list others

3. COMPLETE the remaining sections with standard coverage (3-5 entries each).

4. "additional_clinical_context": Add query-specific nuance not captured by schema fields (off-label context, monitoring pearls, clinical tips). null if nothing to add.

Sections to populate:
- Mechanism of action, indications, dosing (routes/forms/regimens), contraindications
- Side effects (common AND serious with approximate incidence), interactions
- Pharmacokinetics, special populations, monitoring parameters
Populate every array — but give MORE depth to sections the user specifically asked about.

Respond with a JSON object matching this EXACT structure:
{{
  "drug_name": "string",
  "bluf": "string — 1-3 sentences directly answering what the user asked (or null)",
  "additional_clinical_context": "string — query-specific nuance not captured above (or null)",
  "drug_class": "string or null",
  "mechanism_of_action": {{"value": "string", "loe": "string", "cor": "string", "source": "string", "source_year": int_or_null, "confidence": "string"}} or null,
  "indications": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "dosing": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low", "route": "string or null", "frequency": "string or null"}}],
  "contraindications": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "side_effects": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "interactions": [{{"drug": "string", "severity": "major|moderate|minor", "description": "string", "evidence": {{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null}}],
  "pharmacokinetics": {{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null,
  "special_populations": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "monitoring": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "references": [{{"source": "string", "title": "string or null", "pmid": "numeric string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

DISEASE_PROMPT = """You are a senior clinician writing a comprehensive disease reference equivalent to a Harrison's chapter summary for medical trainees and practicing physicians.
{approved_sources}
{evidence_rules}
{json_contract_rules}

ANSWER STRATEGY — Read the query carefully and follow these steps:
1. BLUF FIRST: Write "bluf" as 2-4 sentences that DIRECTLY answer the specific question with SPECIFIC clinical numbers.
   Example — "pulmonary embolism": "PE is an occlusion of pulmonary arteries by thrombus, most commonly from DVT (>90%). First-line: anticoagulation with rivaroxaban (15mg BD ×21d, then 20mg OD) or LMWH bridged to warfarin (INR 2-3). Massive PE (sBP <90): thrombolysis with alteplase 100mg IV/2h. Mortality: 1-3% low-risk, 3-15% submassive, 25-65% massive."
   Example — "aortic aneurysm surgical management": "Surgical repair indicated when AAA ≥5.5cm (men) or ≥5.0cm (women), or growth >1cm/year: EVAR preferred if anatomy suitable (60-70% of cases), open repair for younger/complex cases. Perioperative mortality: EVAR 1-2%, open 4-5%."

2. EXPAND on the SPECIFIC AREA the user asked about — give it the MOST detail:
   - "medical management" → treatment.first_line and treatment.second_line should have 6+ entries each with specific drugs/doses
   - "surgical management" → treatment.non_pharmacological should detail EVERY surgical approach with indications and criteria
   - "diagnosis" → diagnostic_criteria should have 8+ entries with specific threshold values and test characteristics
   - "pathophysiology" → pathophysiology should be ≥250 words with cellular/molecular detail
   - If the query is just the disease name → give EQUAL depth to ALL sections

3. COMPLETE remaining sections thoroughly (NOT sparsely). Every section should have the MINIMUM entries listed below.

4. "additional_clinical_context": Query-specific nuance (surveillance intervals, emerging therapies, bedside tips, scoring systems, risk stratification). null if nothing.

Sections to populate — MINIMUM entry counts are MANDATORY:
- etiology: 5-8 entries (all causes — be SPECIFIC: name the genes, organisms, risk factors with incidence data)
- pathophysiology: detailed mechanism (≥200 words with specific physiological numbers)
- epidemiology: incidence, prevalence, age/sex distribution, geographic variation
- clinical_features: 8-12 entries — include FREQUENCY data (e.g. "Dyspnea (73%)"), CLASSIFICATION/SEVERITY SYSTEMS with each class as separate entry (e.g. Wells score, NYHA, Child-Pugh, CURB-65)
- diagnostic_criteria: 6-10 entries with SPECIFIC threshold values AND test characteristics (sensitivity/specificity):
  RIGHT: "CT pulmonary angiography: sensitivity 83-100%, specificity 89-97%"  WRONG: "Imaging is useful"
  RIGHT: "D-dimer ELISA: sensitivity >95%; age-adjusted cutoff (age × 10 µg/L) for patients >50"  WRONG: "Blood tests may help"
- treatment.first_line: 4-8 entries — MANDATORY FORMAT for every drug entry: [Drug class (MOA)] Drug dose route frequency duration
  MANDATORY: Every pharmacological treatment entry MUST include:
    1. Drug group/class in square brackets with MOA in one clause
    2. Specific dose + route + frequency + duration
  RIGHT: "[Factor Xa inhibitor; directly blocks free and clot-bound factor Xa] Rivaroxaban 15 mg PO BD ×21 days then 20 mg OD"
  RIGHT: "[LMWH; inhibits factor Xa and IIa via antithrombin] Enoxaparin 1 mg/kg SC BD, bridge to warfarin INR 2.0-3.0"
  RIGHT: "[Biguanide; inhibits hepatic gluconeogenesis and increases insulin sensitivity] Metformin 500 mg PO BD with meals, titrate to 1000 mg BD"
  WRONG: "Rivaroxaban 15mg BD" (missing class and MOA)
  WRONG: "Anticoagulation is recommended" (no drug, no class, no dose)
- treatment.second_line: 3-5 specific drugs with class [MOA] + doses and criteria for use
- treatment.adjunctive: 2-4 entries with class [MOA] + doses where pharmacological
- treatment.non_pharmacological: 3-5 entries (interventions, surgery, lifestyle, transplant criteria with specific indications)
- complications: 5-8 entries with incidence rates where known
- prognosis: mortality rates, recurrence rates, prognostic factors
If a section has fewer than the minimum entries above, you have NOT met the depth requirement.

Respond with a JSON object matching this EXACT structure:
{{
  "disease_name": "string",
  "bluf": "string — 1-3 sentences directly answering what the user asked (or null)",
  "additional_clinical_context": "string — query-specific nuance not captured above (or null)",
  "icd_10": "string or null",
  "etiology": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "pathophysiology": {{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null,
  "epidemiology": {{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null,
  "clinical_features": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "diagnostic_criteria": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "treatment": {{
    "first_line": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low", "drug_names": ["generic_name_only"]}}],
    "second_line": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low", "drug_names": ["generic_name_only"]}}],
    "adjunctive": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low", "drug_names": ["generic_name_only"]}}],
    "non_pharmacological": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}]
  }},
  "complications": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "prognosis": {{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null,
  "references": [{{"source": "string", "title": "string or null", "pmid": "numeric string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

COMPARATIVE_PROMPT = """You are a clinical comparison assistant.
{approved_sources}
{evidence_rules}
{json_contract_rules}

MINIMUM COMPARISON DIMENSIONS (mandatory — you MUST include ALL of these):
1. Efficacy (primary outcomes, NNT where available)
2. Safety / adverse effects (including black box warnings)
3. Contraindications
4. Drug interactions
5. Dosing convenience (route, frequency, titration complexity)
6. Special populations (renal impairment, hepatic impairment, elderly, pregnancy)
7. Cost / availability
8. Guideline positioning (which is first-line per major guidelines?)
Fewer than 8 dimensions is a FAILED response. Include additional dimensions when clinically relevant.
Provide a thorough clinical preference summary with supporting rationale.

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
  "clinical_preference": {{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null,
  "references": [{{"source": "string", "title": "string or null", "pmid": "numeric string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

GENERAL_PROMPT = """You are a medical knowledge assistant.
{approved_sources}
{evidence_rules}
{json_contract_rules}

This query does not fit a specific drug/disease/comparative pattern. Provide a structured response.

DEPTH REQUIREMENTS for medical topics:
- summary: minimum 3 substantive paragraphs: (1) definition/background and clinical significance, (2) mechanism, pathophysiology, or underlying principle if applicable, (3) clinical relevance, key considerations, and practical application
- key_points: 5-8 specific, actionable, clinically useful statements — not generic observations. Include specific values, thresholds, or clinical pearls where applicable.
- For medical queries, provide clinical-grade depth equivalent to a brief UpToDate overview.

key_points rules: plain strings only — no leading markdown bullet prefix ("- "), no numbered prefix ("1."). Each entry is a complete sentence or actionable statement.
related_drugs rules: generic INN names only — no brand names, no dosing information.
related_conditions rules: condition names only — no descriptions.

Respond with a JSON object matching this EXACT structure:
{{
  "summary": "markdown string with your main answer",
  "key_points": ["actionable clinical statement without bullet prefix", "..."],
  "related_drugs": ["generic_name_only"],
  "related_conditions": ["condition_name_only"],
  "confidence": "high|moderate|low",
  "references": [{{"source": "string", "title": "string or null", "pmid": "numeric string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

PROCEDURE_PROMPT = """You are a clinical procedure reference assistant.
{approved_sources}
{evidence_rules}
{json_contract_rules}

{focus_instruction}

Ensure all arrays have sufficient entries to fully answer the query. Sparse or incomplete responses will be rejected.

HALLUCINATION PREVENTION: For "indications", "contraindications", and "complications", prefer items supported by approved sources — but when source data is absent for a well-established procedure, include standard clinical consensus entries rather than outputting empty arrays. "technique_steps" and "guidelines" may use established clinical consensus for well-known procedural steps.

technique_steps rules: steps MUST be sequential; step_number starts at 1 and increments by 1 with no gaps. "notes" is null if not applicable — never output "".

Respond with a JSON object for the procedure "{query}":
{{
  "procedure_name": "string",
  "indications": [{{"value": "string describing when to perform", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "contraindications": [{{"value": "string describing contraindication", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "technique_steps": [{{"step_number": 1, "description": "string", "notes": "string or null"}}],
  "complications": [{{"value": "string describing complication", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "guidelines": [{{"value": "recommendation text", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low", "society": "e.g. SSC, AHA/ACC, NICE, WHO, ACLS — null if unknown"}}],
  "references": [{{"source": "string", "title": "string or null", "pmid": "numeric string or null", "year": int_or_null, "url": null}}]
}}

{vector_context}

Query: {query}"""

EVIDENCE_PROMPT = """You are a clinical evidence synthesizer.
{approved_sources}
{evidence_rules}
{json_contract_rules}

{focus_instruction}

Ensure all arrays have sufficient entries to fully answer the query. Sparse or incomplete responses will be rejected.

The user is asking about evidence for a clinical question that may not have formal guidelines.
Your job is to summarize the available studies and provide a balanced recommendation.

pmid rule: numeric string only, no "PMID:" prefix (e.g. "38293847") — output null if unavailable.
guideline_status rule: output EXACTLY one of these three templates (fill in the blanks):
  "No formal guideline exists"
  "Mentioned in [Society] [year] guidelines"
  "Formal recommendation in [Society] [year] guidelines"

Respond with a JSON object:
{{
  "query_topic": "concise topic string",
  "summary": "4-6 sentence overview: rationale/mechanism, evidence quality, key findings, clinical context, residual uncertainty",
  "supporting_studies": [{{
    "title": "study title",
    "pmid": "numeric string or null",
    "year": int_or_null,
    "finding": "key finding in 1-2 sentences",
    "sample_size": "e.g. n=500 or null",
    "loe": "I|II-1|II-2|II-3|III"
  }}],
  "opposing_studies": [{{
    "title": "study title",
    "pmid": "numeric string or null",
    "year": int_or_null,
    "finding": "key finding in 1-2 sentences",
    "sample_size": "e.g. n=500 or null",
    "loe": "I|II-1|II-2|II-3|III"
  }}],
  "clinical_recommendation": {{"value": "recommendation", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null,
  "guideline_status": "No formal guideline exists",
  "references": [{{"source": "string", "title": "string or null", "pmid": "numeric string or null", "year": int_or_null, "url": null}}]
}}

{vector_context}

Query: {query}"""

HIGHLIGHTS_PROMPT = """You are a senior clinician writing a rapid clinical reference card.
{approved_sources}
{json_contract_rules}

The user asked: "{query}"

Give a SMART, FOCUSED answer — NOT a textbook. Think: what would a consultant say in 90 seconds?
Rules:
- DO NOT follow a fixed disease template (no mandatory etiology/pathophysiology/complications headings)
- LEAD with what the user actually needs (e.g., "Surviving Sepsis" → Sepsis-3 criteria + 1-hour bundle + antibiotic choice + vasopressor threshold)
- Use clinical pearl style: concise, actionable, memorable
- Include specific numbers/thresholds where they matter (e.g., MAP ≥65, lactate >2, fluid 30 mL/kg)
- 5-8 key points maximum — quality over exhaustive coverage (do NOT add a literal "max 8 total" string to the array)
- Flag any mnemonics or bedside tools if clinically useful
- Cite society guidelines where directly applicable (e.g., SSC 2021, AHA 2022)
- key_points: plain strings, no leading bullet or numbered prefix, max 8 entries
- related_drugs: generic INN names only — no brand names

Respond with a JSON object:
{{
  "summary": "1-2 sentence overview of what this is clinically",
  "key_points": ["actionable clinical pearl with specific numbers/doses"],
  "related_drugs": ["generic_name_only"],
  "related_conditions": ["condition_name_only"],
  "confidence": "high|moderate|low",
  "references": [{{"source": "string", "title": "string or null", "pmid": "numeric string or null", "year": int_or_null, "url": null}}]
}}

{vector_context}

Query: {query}"""

PROMPTS = {
    "drug": DRUG_PROMPT,
    "disease": DISEASE_PROMPT,
    "comparative": COMPARATIVE_PROMPT,
    "procedure": PROCEDURE_PROMPT,
    "evidence": EVIDENCE_PROMPT,
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

{condition_context_block}

Ensure all arrays have sufficient entries to fully answer the query. Sparse or incomplete responses will be rejected.

ANSWER STRATEGY — Read the query carefully:
1. BLUF: Write 1-3 sentences DIRECTLY answering the specific clinical question from source data.
2. If condition context is present, treat this as a drug-in-disease question first, not a generic label summary.
   Lead with guideline positioning, role of the drug in that condition, practical dosing and monitoring in that condition, and key safety caveats in that condition.
   Use generic FDA label facts as supporting detail after the condition-specific answer.
3. EXPAND: Give most detail to the section the user asked about (dosing/interactions/side effects/guideline role/monitoring/etc.)
4. COMPLETE: Fill remaining sections with standard coverage from source data.
"additional_clinical_context": query-specific nuance from source data (monitoring pearls, off-label, special populations). null if nothing.
Use tables and flowcharts in response generation where applicable.

{evidence_rules}
{json_contract_rules}

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

=== SYSTEMATIC REVIEWS / META-ANALYSES (PubMed) ===
{systematic_review_abstracts_formatted}

Respond ONLY with a JSON object matching this EXACT structure:
{{
  "drug_name": "string",
  "bluf": "string — 1-3 sentences directly answering what the user asked (or null)",
  "additional_clinical_context": "string — query-specific nuance not captured above (or null)",
  "drug_class": "string or null",
  "mechanism_of_action": {{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null,
  "indications": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "dosing": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low", "route": "string or null", "frequency": "string or null"}}],
  "contraindications": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "side_effects": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "interactions": [{{"drug": "string", "severity": "major|moderate|minor", "description": "string", "evidence": {{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null}}],
  "pharmacokinetics": {{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null,
  "special_populations": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "monitoring": [{{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "tables": [{{"title": "string", "headers": ["string"], "rows": [["string"]]}}],
  "flowcharts": [{{"title": "string", "steps": ["string"]}}],
  "references": [{{"source": "string", "title": "string or null", "pmid": "numeric string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

DISEASE_FORMAT_PROMPT = """You are a senior clinician creating a comprehensive disease reference card equivalent to a Harrison's chapter summary.

Your sources are below. Use them as PRIMARY evidence (cite with society + year). Where source data is absent or incomplete for a specific field, you MUST supplement with established medical knowledge — this is EXPECTED for a complete reference card. Use well-known sources: "Harrison's Principles of Internal Medicine", "Robbins Pathology", "Braunwald's Heart Disease", "Goldman-Cecil Medicine", or the appropriate specialty textbook. Mark supplemented content with loe="III", cor="IIb", confidence="moderate" when from a named textbook, or confidence="low" if purely from clinical reasoning. The goal is a COMPLETE, CLINICALLY USEFUL reference — NOT a sparse list of only what PubMed returned.

ANSWER STRATEGY — Read the query carefully:
1. BLUF: Write 2-4 sentences DIRECTLY answering the specific question with SPECIFIC numbers.
   "pulmonary embolism" → "PE is an occlusion of pulmonary arteries by thrombus, most commonly from DVT (>90%). Acute massive PE (systolic BP <90 mmHg) carries 25-65% mortality. First-line: anticoagulation with LMWH/UFH bridged to warfarin (INR 2-3) or DOAC monotherapy (rivaroxaban 15mg BD x21d then 20mg OD). Thrombolysis (alteplase 100mg IV/2h) for massive PE with hemodynamic instability."
   "medical management" → lead with drugs, doses, BP targets, lifestyle
   "surgical management" → lead with surgical indications, approaches, techniques
   "diagnosis" → lead with diagnostic criteria, investigations, classification
2. The first half of the answer must focus on the user's actual clinical need, not generic background. Do not spend the opening on definition-only material.
3. EXPAND: Give most detail to the section the user asked about.
   "medical management" → treatment arrays should have 6+ entries with specific drugs/doses
   "surgical management" → non_pharmacological should detail every surgical approach with indications
   If the query is just the disease name (e.g. "pulmonary embolism") → give EQUAL depth to ALL sections.
4. COMPLETE: Fill ALL remaining sections thoroughly. Do NOT leave ANY section sparse.
"additional_clinical_context": Query-specific nuance from source data. null if nothing.
Use tables and flowcharts in response structuring where applicable.

DEPTH REQUIREMENTS — CRITICAL — every section MUST be fully populated with clinically actionable detail:
- etiology: 5-8 entries covering ALL causes and risk factors — be SPECIFIC (e.g., "Virchow's triad: venous stasis (immobilization >3 days, long-haul flights >4h), endothelial injury (surgery, trauma, central lines), hypercoagulability (Factor V Leiden, protein C/S deficiency, antiphospholipid syndrome, malignancy, OCP use)")
- pathophysiology: detailed mechanistic explanation (≥200 words) covering the complete pathological cascade — thrombus formation, hemodynamic effects, gas exchange impairment, RV failure mechanism, inflammatory response; include SPECIFIC numbers (e.g., dead space ventilation, V/Q mismatch ratios, PA pressure thresholds)
- clinical_features: 8-12 entries — ALL symptoms/signs with FREQUENCY data where known (e.g., "Dyspnea (73%)", "Pleuritic chest pain (44%)", "Tachycardia >100bpm (24%)"). MUST include CLASSIFICATION/SEVERITY SYSTEMS as separate entries (e.g., PE severity: massive/submassive/low-risk with criteria for each; Wells score criteria; Geneva score criteria)
- diagnostic_criteria: 6-10 entries with SPECIFIC threshold values and test characteristics (sensitivity/specificity where known):
  RIGHT: "CT pulmonary angiography (CTPA): sensitivity 83-100%, specificity 89-97%; first-line imaging for suspected PE"
  RIGHT: "D-dimer (ELISA): sensitivity >95%, NPV >99% when pre-test probability low; age-adjusted cutoff = age × 10 µg/L for patients >50"
  WRONG: "Imaging studies are helpful" or "Blood tests may be ordered"
- treatment.first_line: 4-8 entries — MANDATORY FORMAT: [Drug class; MOA] Drug dose route frequency duration
  Every pharmacological treatment entry MUST include drug group + MOA + specific dose:
  RIGHT: "[Factor Xa inhibitor; directly blocks free and clot-bound Xa] Rivaroxaban 15 mg PO BD ×21 days then 20 mg OD"
  RIGHT: "[UFH; potentiates antithrombin III to inhibit thrombin and factor Xa] Unfractionated heparin 80 units/kg IV bolus then 18 units/kg/h, titrate aPTT 1.5-2.5×"
  WRONG: "Rivaroxaban 15mg BD" (no class, no MOA)
  WRONG: "Anticoagulation is recommended" (no drug, no class, no dose)
- treatment.second_line: 3-5 specific entries with [class; MOA] + doses and criteria for use
- treatment.adjunctive: 2-4 entries with [class; MOA] + dose where pharmacological
- treatment.non_pharmacological: 3-5 entries (surgical embolectomy indications, catheter-directed therapy, compression stockings, early mobilization, long-term prevention)
- complications: 5-8 entries with specific incidence rates where known
- prognosis: Include mortality rates, recurrence rates, and factors affecting prognosis
- NEVER leave etiology, pathophysiology, clinical_features, diagnostic_criteria, or treatment empty or sparse
- If a section has fewer than the minimum entries listed above, you have NOT met the depth requirement

{evidence_rules}
{json_contract_rules}

=== RETRIEVED GUIDELINE DATA (ACC/AHA/ESC/ERS/NICE/WHO/ADA/IDSA etc. via PubMed) ===
{guideline_abstracts_formatted}

=== SYSTEMATIC REVIEWS / META-ANALYSES ===
{systematic_review_abstracts_formatted}

=== NICE RECOMMENDATIONS ===
{nice_recommendations_formatted}

=== MEDLINEPLUS / CLASSIFICATION DATA ===
{medlineplus_summary}

IMPORTANT: Produce a LONG, DETAILED response. Use the FULL token budget. Every array should have the MINIMUM number of entries specified in the depth requirements above. Short, sparse responses are NOT acceptable.

COMPLETION RULE — MANDATORY: You MUST complete ALL sections. Do NOT stop after complications.
treatment (all 4 sub-sections), complications, AND prognosis are ALL MANDATORY.
An incomplete response is a FAILED response.

SECTION ORDER: disease_name → bluf → icd_10 → etiology → pathophysiology → epidemiology →
clinical_features → diagnostic_criteria → treatment → complications → prognosis → references.
Do NOT skip any section.

Respond ONLY with a JSON object matching this EXACT structure:
{{
  "disease_name": "string",
  "bluf": "string — 2-4 sentences directly answering what the user asked with specific clinical numbers (or null)",
  "additional_clinical_context": "string — query-specific nuance: scoring systems, risk stratification, emerging therapies, clinical pearls (or null)",
  "icd_10": "string or null",
  "etiology": [{{"value": "string — be SPECIFIC: name genes, organisms, risk factors with incidence", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "pathophysiology": {{"value": "string — MUST be ≥200 words with specific physiological numbers and complete pathological cascade", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null,
  "epidemiology": {{"value": "string — incidence, prevalence, demographics, geographic variation", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null,
  "clinical_features": [{{"value": "string — include symptom FREQUENCY (e.g., 'Dyspnea (73%)') and severity classification entries", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "diagnostic_criteria": [{{"value": "string — include test sensitivity/specificity and specific threshold values", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "treatment": {{
    "first_line": [{{"value": "string — SPECIFIC drug+dose+route+frequency+duration", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low", "drug_names": ["generic_name_only"]}}],
    "second_line": [{{"value": "string — SPECIFIC drug+dose with criteria for use", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low", "drug_names": ["generic_name_only"]}}],
    "adjunctive": [{{"value": "string — supportive interventions with specific indications", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low", "drug_names": ["generic_name_only"]}}],
    "non_pharmacological": [{{"value": "string — surgical/interventional with specific indications and criteria", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}]
  }},
  "complications": [{{"value": "string — include incidence rate where known", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "prognosis": {{"value": "string — include mortality rates, recurrence rates, prognostic factors", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null,
  "tables": [{{"title": "string", "headers": ["string"], "rows": [["string"]]}}],
  "flowcharts": [{{"title": "string", "steps": ["string"]}}],
  "references": [{{"source": "string", "title": "string or null", "pmid": "numeric string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

COMPARATIVE_FORMAT_PROMPT = """You are a medical JSON formatter comparing two entities using retrieved source data.
Compare them accurately. Do NOT invent efficacy statistics not present in the source data.

MINIMUM COMPARISON DIMENSIONS (mandatory — you MUST include ALL of these):
1. Efficacy (primary outcomes, NNT where available)
2. Safety / adverse effects (including black box warnings)
3. Contraindications
4. Drug interactions
5. Dosing convenience (route, frequency, titration complexity)
6. Special populations (renal impairment, hepatic impairment, elderly, pregnancy)
7. Cost / availability
8. Guideline positioning (which is first-line per major guidelines?)
Fewer than 8 dimensions is a FAILED response.

ANSWER STRATEGY:
1. Summary first: the summary and clinical_preference must directly answer which option is preferable for the user's exact question and in what scenario.
2. Guideline positioning and real clinical tradeoffs must appear before generic catalog-style differences.
3. If the query names a condition or population, compare both entities in that condition or population first, then give broader comparison detail.

{evidence_rules}
{json_contract_rules}

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
  "clinical_preference": {{"value": "string", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null,
  "references": [{{"source": "string", "title": "string or null", "pmid": "numeric string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

PROCEDURE_FORMAT_PROMPT = """You are a clinical procedure reference formatter. Use the retrieved guideline data to create a structured procedure reference.

{evidence_rules}
{json_contract_rules}

{focus_instruction}

Ensure all arrays have sufficient entries to fully answer the query. Sparse or incomplete responses will be rejected.

HALLUCINATION PREVENTION: Prefer items supported by the retrieved data below for indications/contraindications/complications. For technique_steps and guidelines, clinical consensus is acceptable when retrieved data is insufficient. Do NOT output empty arrays for a well-known procedure — provide standard consensus entries.

technique_steps rules: steps MUST be sequential; step_number starts at 1 and increments by 1 with no gaps. "notes" is null if not applicable — never output "".

=== PRACTICE GUIDELINES ===
{guideline_abstracts_formatted}

=== PROCEDURE-SPECIFIC GUIDELINES ===
{practice_guideline_abstracts_formatted}

Respond ONLY with a JSON object for the procedure "{query}":
{{
  "procedure_name": "string",
  "indications": [{{"value": "string describing when to perform", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "contraindications": [{{"value": "string describing contraindication", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "technique_steps": [{{"step_number": 1, "description": "string", "notes": "string or null"}}],
  "complications": [{{"value": "string describing complication", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}}],
  "guidelines": [{{"value": "recommendation text", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low", "society": "e.g. SSC, AHA/ACC, NICE, WHO — null if unknown"}}],
  "references": [{{"source": "string", "title": "string or null", "pmid": "numeric string or null", "year": int_or_null, "url": null}}]
}}

Query: {query}"""

EVIDENCE_FORMAT_PROMPT = """You are a clinical evidence synthesizer. Use the retrieved study data to provide a balanced evidence summary.

{evidence_rules}
{json_contract_rules}

{focus_instruction}

Ensure all arrays have sufficient entries to fully answer the query. Sparse or incomplete responses will be rejected.

pmid rule: numeric string only, no "PMID:" prefix (e.g. "38293847") — output null if unavailable.
guideline_status rule: output EXACTLY one of these three templates (fill in the blanks):
  "No formal guideline exists"
  "Mentioned in [Society] [year] guidelines"
  "Formal recommendation in [Society] [year] guidelines"

ANSWER STRATEGY:
1. The opening summary sentence must answer the user's actual question directly.
2. State the practical clinical bottom line before unpacking supporting and opposing studies.
3. Keep residual uncertainty, subgroup limitations, and applicability explicit instead of burying them at the end.

=== CLINICAL TRIALS / RCTs ===
{clinical_trial_abstracts_formatted}

=== SYSTEMATIC REVIEWS / META-ANALYSES ===
{systematic_review_abstracts_formatted}

=== GUIDELINE MENTIONS ===
{guideline_abstracts_formatted}

Respond ONLY with a JSON object:
{{
  "query_topic": "concise topic string",
  "summary": "4-6 sentence overview: rationale/mechanism, evidence quality, key findings, clinical context, residual uncertainty",
  "supporting_studies": [{{
    "title": "study title",
    "pmid": "numeric string or null",
    "year": int_or_null,
    "finding": "key finding in 1-2 sentences",
    "sample_size": "e.g. n=500 or null",
    "loe": "I|II-1|II-2|II-3|III"
  }}],
  "opposing_studies": [{{
    "title": "study title",
    "pmid": "numeric string or null",
    "year": int_or_null,
    "finding": "key finding in 1-2 sentences",
    "sample_size": "e.g. n=500 or null",
    "loe": "I|II-1|II-2|II-3|III"
  }}],
  "clinical_recommendation": {{"value": "recommendation", "loe": "I|II-1|II-2|II-3|III", "cor": "I|IIa|IIb|III-no-benefit|III-harm", "source": "string", "source_year": int_or_null, "confidence": "high|moderate|low"}} or null,
  "guideline_status": "No formal guideline exists",
  "references": [{{"source": "string", "title": "string or null", "pmid": "numeric string or null", "year": int_or_null, "url": null}}]
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
        # Prefer full article text (PMC/Unpaywall) over truncated abstract
        text = a.get("full_text") or a.get("abstract", "")
        lines.append(f"[{i}] {title}")
        lines.append(f"    Source: {society} {year}  PMID:{pmid}")
        lines.append(f"    {text}")
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
    query: str,
    query_type: str,
    fetched_data: "FetchedData | None" = None,
    vector_results: "list[SearchResult] | None" = None,
    intent: str = "full",
    condition_context: "str | None" = None,
) -> str:
    """Build a prompt for the LLM.

    If intent='highlights' AND query_type='general' → compact highlights response.
    If intent='highlights' AND query_type is structured → keep structured prompt with summary modifier.
    If fetched_data is provided and fetch succeeded → format-mode prompt (shorter, cheaper).
    Otherwise → generate-mode prompt (full knowledge generation).
    Vector results are injected into both modes when available.
    """
    if intent == "highlights" and query_type == "general":
        vector_context = (
            _format_vector_context(vector_results) if vector_results else ""
        )
        return HIGHLIGHTS_PROMPT.format(
            query=query,
            approved_sources=APPROVED_SOURCES,
            json_contract_rules=JSON_CONTRACT_RULES,
            vector_context=vector_context,
        )

    if fetched_data is not None and not fetched_data.fallback_to_llm:
        result = _build_format_prompt(
            query, query_type, fetched_data, vector_results, condition_context
        )
        if result is not None:
            return result

    return _build_generate_prompt(query, query_type, vector_results, condition_context)


def _build_generate_prompt(
    query: str,
    query_type: str,
    vector_results: "list[SearchResult] | None" = None,
    condition_context: "str | None" = None,
) -> str:
    template = PROMPTS[query_type]
    vector_context = _format_vector_context(vector_results) if vector_results else ""
    focus_instruction = _detect_focus_instruction(query)
    condition_context_block = _build_condition_context_block(condition_context)

    # Templates that support vector_context and focus_instruction
    if query_type in ("procedure", "evidence"):
        return template.format(
            query=query,
            approved_sources=APPROVED_SOURCES,
            evidence_rules=EVIDENCE_RULES,
            json_contract_rules=JSON_CONTRACT_RULES,
            vector_context=vector_context,
            focus_instruction=focus_instruction,
        )

    # Drug template supports condition_context_block
    if query_type == "drug":
        prompt = template.format(
            query=query,
            approved_sources=APPROVED_SOURCES,
            evidence_rules=EVIDENCE_RULES,
            json_contract_rules=JSON_CONTRACT_RULES,
            condition_context_block=condition_context_block,
        )
        if vector_context:
            prompt = prompt.rstrip() + "\n\n" + vector_context
        focus = _drug_focus_hint(query)
        if focus:
            prompt = focus + "\n\n" + prompt
        return prompt

    # Other templates — append vector context at the end
    prompt = template.format(
        query=query,
        approved_sources=APPROVED_SOURCES,
        evidence_rules=EVIDENCE_RULES,
        json_contract_rules=JSON_CONTRACT_RULES,
    )
    if vector_context:
        prompt = prompt.rstrip() + "\n\n" + vector_context
    # Disease-specific focus hint (item 4)
    if query_type == "disease":
        focus = _disease_focus_hint(query)
        if focus:
            prompt = focus + "\n\n" + prompt
    elif focus_instruction:
        prompt = focus_instruction + "\n\n" + prompt
    return prompt


# ──────────────────────────────────────────────
# Condition context block for drug queries
# ──────────────────────────────────────────────


def _build_condition_context_block(condition_context: "str | None") -> str:
    """Build a condition context instruction block for drug prompts."""
    if not condition_context:
        return ""
    return (
        f'CONDITION CONTEXT: This drug is being queried in the context of "{condition_context}".\n'
        f"Prioritize: dosing for this condition, indications relevant to this condition, "
        f"contraindications in this condition, monitoring specific to this condition."
    )


def _build_condition_data_block(
    condition_context: "str | None",
    condition_data: "DiseaseFetchResult | None" = None,
) -> str:
    """Build a condition context block for drug-in-condition queries.

    If condition_data has guideline abstracts, injects them as a richer data block
    so the LLM can cite condition management guidelines alongside the drug data.
    Falls back to the simple text instruction when no data is available.
    """
    if not condition_context:
        return ""
    if (
        condition_data
        and condition_data.fetch_success
        and (
            condition_data.guideline_abstracts
            or condition_data.systematic_review_abstracts
        )
    ):
        abstracts = (condition_data.guideline_abstracts or []) + (
            condition_data.systematic_review_abstracts or []
        )
        abstracts_text = _format_abstracts(
            abstracts[:6]
        )  # cap at 6 to control token use
        return (
            f"=== CONDITION MANAGEMENT GUIDELINES ({condition_context.upper()}) ===\n"
            f"{abstracts_text}\n\n"
            f"Prioritize: drug's specific role in managing {condition_context}, citing these "
            f"condition-management guidelines. Include guideline-recommended targets, "
            f"rate/rhythm control context if applicable, and monitoring in this condition."
        )
    return _build_condition_context_block(condition_context)


# Vector context formatting
# ──────────────────────────────────────────────


def _format_vector_context(results: "list[SearchResult]") -> str:
    """Format vector search results as context for the LLM prompt."""
    if not results:
        return ""

    lines = ["=== RETRIEVED DOCUMENT CONTEXT (from indexed knowledge base) ==="]
    for i, r in enumerate(results, 1):
        source_info = r.title
        if r.publisher:
            source_info = f"{r.publisher} — {r.title}"
        if r.page_number:
            source_info += f" (page {r.page_number})"
        if r.pmid:
            source_info += f" [PMID:{r.pmid}]"
        if r.section:
            source_info += f" [{r.section}]"

        lines.append(f"\n[{i}] Source: {source_info}")
        lines.append(f"    Relevance: {r.similarity:.2f}")
        lines.append(f"    Content: {r.content[:1500]}")

    lines.append(
        "\nUse the above context as evidence where relevant. "
        "Cite the source document title and page number. "
        "Do NOT reveal who uploaded any document."
    )
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Intent detection for focused answers
# ──────────────────────────────────────────────

_MANAGEMENT_KEYWORDS = {
    "manage",
    "management",
    "treat",
    "treatment",
    "therapy",
    "therapies",
    "regimen",
    "protocol",
    "guideline",
    "guidelines",
    "first-line",
    "second-line",
}
_DOSING_KEYWORDS = {
    "dose",
    "dosing",
    "dosage",
    "mg",
    "mcg",
    "ug",
    "titrat",
    "prescri",
    "prescrib",
}
_MECHANISM_KEYWORDS = {
    "mechanism",
    "moa",
    "how does",
    "pharmacology",
    "pharmacokinetic",
    "pharmacodynamic",
    "action",
    "work",
}
_DIAGNOSIS_KEYWORDS = {
    "diagnos",
    "diagnosis",
    "workup",
    "investigation",
    "test",
    "criteria",
    "differential",
    "ddx",
}

_FOCUS_INSTRUCTIONS = {
    "management": (
        "PRIORITY: Lead your response with treatment and management. "
        "Put treatment lines, regimens, drug choices, and protocols FIRST — "
        "before etiology, pathophysiology, or background. "
        "The user primarily wants to know how to treat/manage."
    ),
    "dosing": (
        "PRIORITY: Lead with dosing information. "
        "Put specific doses, dosing regimens, titration schedules, and formulations FIRST — "
        "before mechanism or background."
    ),
    "mechanism": (
        "PRIORITY: Lead with mechanism of action and pharmacology. "
        "Put MOA, pharmacokinetics, and pharmacodynamics FIRST."
    ),
    "diagnosis": (
        "PRIORITY: Lead with diagnostic criteria and workup. "
        "Put diagnostic criteria, investigations, and differential diagnosis FIRST."
    ),
    "overview": "",
}


def detect_query_focus(query: str, query_type: str = "") -> str:
    """Detect what aspect the user is primarily asking about.

    Returns one of: 'management', 'dosing', 'mechanism', 'diagnosis', 'overview'.
    """
    q = query.lower()
    if any(kw in q for kw in _MANAGEMENT_KEYWORDS):
        return "management"
    if any(kw in q for kw in _DOSING_KEYWORDS):
        return "dosing"
    if any(kw in q for kw in _MECHANISM_KEYWORDS):
        return "mechanism"
    if any(kw in q for kw in _DIAGNOSIS_KEYWORDS):
        return "diagnosis"
    return "overview"


_INTENT_PATTERNS = {
    "management": re.compile(
        r"\b(?:management|treatment|therapy|therapeutic|prescri|treat)\b", re.I
    ),
    "diagnosis": re.compile(
        r"\b(?:diagnosis|diagnos|criteria|workup|investigate|assess)\b", re.I
    ),
    "prognosis": re.compile(
        r"\b(?:prognosis|outcome|survival|mortality|life expectancy)\b", re.I
    ),
    "pathophysiology": re.compile(
        r"\b(?:pathophysiology|mechanism|etiology|cause|pathogenesis)\b", re.I
    ),
}


def _detect_focus_instruction(query: str) -> str:
    """Detect query intent and return a focus instruction for the LLM.

    Uses both the legacy intent patterns and the new keyword-based focus detection,
    preferring the keyword-based result when a clear focus is found.
    """
    focus = detect_query_focus(query)
    if focus != "overview":
        return _FOCUS_INSTRUCTIONS.get(focus, "")
    # Fallback: legacy pattern-based detection for prognosis / pathophysiology
    for intent, pattern in _INTENT_PATTERNS.items():
        if pattern.search(query):
            return (
                f"The user is specifically asking about **{intent}**. "
                f"Lead with detailed {intent} content. Include 1-2 sentence "
                f"summaries of related clinical areas for context, but do NOT "
                f"elaborate on sections the user didn't ask about."
            )
    return ""


def _build_format_prompt(
    query: str,
    query_type: str,
    fetched_data: "FetchedData",
    vector_results: "list[SearchResult] | None" = None,
    condition_context: "str | None" = None,
) -> str | None:
    """Build a format-mode prompt. Returns None if the data is insufficient.

    Vector context is appended to format prompts when available.
    """
    if (
        query_type == "drug"
        and fetched_data.drug_data
        and fetched_data.drug_data.fetch_success
    ):
        d = fetched_data.drug_data
        prompt = DRUG_FORMAT_PROMPT.format(
            query=query,
            evidence_rules=EVIDENCE_RULES,
            json_contract_rules=JSON_CONTRACT_RULES,
            condition_context_block=_build_condition_data_block(
                condition_context, fetched_data.condition_data
            ),
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
            systematic_review_abstracts_formatted=_format_abstracts(
                d.systematic_review_abstracts
            ),
        )
        focus = _drug_focus_hint(query)
        if focus:
            prompt = focus + "\n\n" + prompt
        if vector_results:
            prompt += "\n\n" + _format_vector_context(vector_results)
        return prompt

    if (
        query_type == "disease"
        and fetched_data.disease_data
        and fetched_data.disease_data.fetch_success
    ):
        d = fetched_data.disease_data
        prompt = DISEASE_FORMAT_PROMPT.format(
            query=query,
            evidence_rules=EVIDENCE_RULES,
            json_contract_rules=JSON_CONTRACT_RULES,
            guideline_abstracts_formatted=_format_abstracts(d.guideline_abstracts),
            systematic_review_abstracts_formatted=_format_abstracts(
                d.systematic_review_abstracts
            ),
            nice_recommendations_formatted=_format_nice_recs(d.nice_recommendations),
            medlineplus_summary=d.medlineplus_summary or "Not available",
        )
        focus = _disease_focus_hint(query)
        if focus:
            prompt = focus + "\n\n" + prompt
        if vector_results:
            prompt += "\n\n" + _format_vector_context(vector_results)
        return prompt

    if query_type == "comparative" and fetched_data.comparative_drug_data:
        drugs = fetched_data.comparative_drug_data
        d1 = drugs[0] if len(drugs) > 0 else None
        d2 = drugs[1] if len(drugs) > 1 else None
        entity1 = (d1.generic_name or "Drug 1") if d1 else "Drug 1"
        entity2 = (d2.generic_name or "Drug 2") if d2 else "Drug 2"
        prompt = COMPARATIVE_FORMAT_PROMPT.format(
            query=query,
            evidence_rules=EVIDENCE_RULES,
            json_contract_rules=JSON_CONTRACT_RULES,
            entity1=entity1,
            entity2=entity2,
            drug1_data_block=_format_drug_block(d1),
            drug2_data_block=_format_drug_block(d2),
        )
        if vector_results:
            prompt += "\n\n" + _format_vector_context(vector_results)
        return prompt

    if (
        query_type == "procedure"
        and fetched_data.procedure_data
        and fetched_data.procedure_data.fetch_success
    ):
        d = fetched_data.procedure_data
        prompt = PROCEDURE_FORMAT_PROMPT.format(
            query=query,
            evidence_rules=EVIDENCE_RULES,
            json_contract_rules=JSON_CONTRACT_RULES,
            focus_instruction=_detect_focus_instruction(query),
            guideline_abstracts_formatted=_format_abstracts(d.guideline_abstracts),
            practice_guideline_abstracts_formatted=_format_abstracts(
                d.practice_guideline_abstracts
            ),
        )
        if vector_results:
            prompt += "\n\n" + _format_vector_context(vector_results)
        return prompt

    if (
        query_type == "evidence"
        and fetched_data.evidence_data
        and fetched_data.evidence_data.fetch_success
    ):
        d = fetched_data.evidence_data
        prompt = EVIDENCE_FORMAT_PROMPT.format(
            query=query,
            evidence_rules=EVIDENCE_RULES,
            json_contract_rules=JSON_CONTRACT_RULES,
            focus_instruction=_detect_focus_instruction(query),
            clinical_trial_abstracts_formatted=_format_abstracts(
                d.clinical_trial_abstracts
            ),
            systematic_review_abstracts_formatted=_format_abstracts(
                d.systematic_review_abstracts
            ),
            guideline_abstracts_formatted=_format_abstracts(d.guideline_abstracts),
        )
        if vector_results:
            prompt += "\n\n" + _format_vector_context(vector_results)
        return prompt

    return None


def get_prompt_version() -> int:
    return settings.prompt_version


# ──────────────────────────────────────────────
# Unified adaptive prompt (all query types → AdaptiveResponse)
# ──────────────────────────────────────────────

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
}

_ADAPTIVE_SYSTEM_TEMPLATE = """\
You are a clinical reference assistant for medical professionals.
{approved_sources}
{evidence_rules}
{json_contract_rules}

QUERY TYPE: {query_type}
REQUIRED SECTIONS (prioritise these): {required_sections}
DEPTH: comprehensive — populate every relevant section fully; sparse responses are rejected.

SECTION GUIDANCE FOR {query_type_upper}:
{section_guidance}

{condition_context_block}{focus_instruction}"""

_ADAPTIVE_RESPONSE_SCHEMA = """\

RESPOND WITH A SINGLE JSON OBJECT — no markdown fences, no prose outside the JSON:
{
  "bluf": {
    "headline": "One sentence directly answering the query",
    "body": "2-4 sentence elaboration with the key clinical bottom line",
    "key_points": ["Actionable bullet 1", "Actionable bullet 2", ...],
    "caveats": ["Safety or evidence caveat 1", ...]
  },
  "sections": [
    {
      "title": "Section heading",
      "content_items": [
        {
          "text": "Evidence-based claim in GFM markdown. Examples: **metformin 500mg BD** for bold key terms, | Dose | Notes | format for tables, - bullet sub-lists for multi-part claims, plain prose for simple facts.",
          "loe": "I | II | III | null",
          "cor": "I | IIa | IIb | III-no-benefit | III-harm | null",
          "source": "Source label e.g. 'AHA/ACC 2022', 'FDA label', 'PubMed PMID:38293847'"
        }
      ],
      "loe": null,
      "cor": null
    }
  ],
  "references": [
    {
      "title": "Article or guideline title",
      "source": "FDA | PubMed | NICE | AHA | WHO | etc.",
      "pmid": "numeric string or null",
      "year": "4-digit year string or null",
      "url": null
    }
  ],
  "tables": [
    {
      "title": "Table title",
      "headers": ["Column 1", "Column 2"],
      "rows": [["Row 1 Cell 1", "Row 1 Cell 2"]]
    }
  ],
  "flowcharts": [
    {
      "title": "Flowchart title",
      "steps": ["Step 1: clinical action or decision", "Step 2: next action"]
    }
  ]
}

TABLES: Include ONLY when comparing entities, showing dosing schedules, staging criteria, diagnostic criteria, or other structured data where a table genuinely aids comprehension over prose. Use [] if not applicable.
FLOWCHARTS: Include ONLY when a clinical decision pathway or algorithm clearly exists (e.g. PE diagnosis/treatment algorithm, sepsis bundle, ACLS, anaphylaxis management). Do NOT include for purely descriptive or epidemiological topics. Each step must be one concise clinical action or decision point. Use [] if not applicable.
QUALITY: Tables and flowcharts are supplemental — sections must remain fully comprehensive regardless."""


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
    """Return (static_system, data_block, user_text) for the adaptive LLM call.

    static_system contains all stable instructions and is suitable for Anthropic
    cache_control (ephemeral). data_block contains per-query fetched data and must
    NOT be cached. user_text is just the query.
    """
    focus_instruction = _detect_focus_instruction(query)
    if query_type == "drug":
        drug_focus = _drug_focus_hint(query)
        if drug_focus:
            focus_instruction = drug_focus
    elif query_type == "disease":
        disease_focus = _disease_focus_hint(query)
        if disease_focus:
            focus_instruction = disease_focus

    condition_block = ""
    if condition_context:
        condition_block = (
            f"CONDITION CONTEXT: This is a drug-in-disease query for "
            f'"{condition_context}". Prioritise dosing, contraindications, '
            f"monitoring, and guideline positioning for this condition.\n\n"
        )

    guidance_key = "comparative_drug" if (query_type == "comparative" and comparative_is_drug) else query_type
    base_guidance = _SECTION_GUIDANCE.get(guidance_key, _SECTION_GUIDANCE.get(query_type, ""))
    sections_str = ", ".join(required_sections) if required_sections else base_guidance
    data_block = _build_adaptive_data_block(query_type, fetched_data, vector_results)

    static_system = (
        _ADAPTIVE_SYSTEM_TEMPLATE.format(
            approved_sources=APPROVED_SOURCES,
            evidence_rules=EVIDENCE_RULES,
            json_contract_rules=JSON_CONTRACT_RULES,
            query_type=query_type,
            query_type_upper=query_type.upper(),
            required_sections=sections_str,
            section_guidance=base_guidance,
            condition_context_block=condition_block,
            focus_instruction=(focus_instruction + "\n\n") if focus_instruction else "",
        )
        + _ADAPTIVE_RESPONSE_SCHEMA
    )

    user_text = f"Query: {query}"
    return static_system, data_block, user_text


# ──────────────────────────────────────────────
# Parallel section agent prompts
# ──────────────────────────────────────────────

_BLUF_ONLY_SCHEMA = """\

RESPOND WITH A SINGLE JSON OBJECT — no markdown fences, no prose outside the JSON:
{
  "bluf": {
    "headline": "One sentence directly answering the query",
    "body": "2-4 sentence elaboration with the key clinical bottom line",
    "key_points": ["Actionable bullet 1", "Actionable bullet 2", "Actionable bullet 3"],
    "caveats": ["Safety or evidence caveat 1"]
  },
  "section_titles": [
    "Section heading 1",
    "Section heading 2"
  ],
  "response_focus": "Brief description of what this response focuses on",
  "related_topics": ["Related query 1", "Related query 2"]
}

Generate 5-10 section_titles that cover the REQUIRED SECTIONS for this query type.
Each title must be a short, clear heading (3-6 words).
Do NOT generate section content — section_titles are plain strings only."""


def build_bluf_only_messages(
    query: str,
    query_type: str,
    fetched_data: "FetchedData | None" = None,
    vector_results: "list[SearchResult] | None" = None,
    condition_context: "str | None" = None,
    comparative_is_drug: bool = False,
) -> tuple[str, str, str]:
    """Return (system, data_block, user_text) for the Phase-1 BLUF+titles call."""
    guidance_key = "comparative_drug" if (query_type == "comparative" and comparative_is_drug) else query_type
    section_guidance = _SECTION_GUIDANCE.get(guidance_key, _SECTION_GUIDANCE.get(query_type, ""))

    condition_block = ""
    if condition_context:
        condition_block = (
            f"CONDITION CONTEXT: This is a drug-in-disease query for "
            f'"{condition_context}".\n\n'
        )

    system = (
        f"You are a clinical reference assistant.\n"
        f"{APPROVED_SOURCES}\n"
        f"{EVIDENCE_RULES}\n\n"
        f"QUERY TYPE: {query_type}\n"
        f"REQUIRED SECTION AREAS: {section_guidance}\n"
        f"{condition_block}"
        f"Generate a concise BLUF (bottom-line up front) and a list of section titles "
        f"that a comprehensive answer to this query should contain."
        + _BLUF_ONLY_SCHEMA
    )
    data_block = _build_adaptive_data_block(query_type, fetched_data, vector_results)
    user_text = f"Query: {query}"
    return system, data_block, user_text


_SECTION_AGENT_SCHEMA = """\

RESPOND WITH A SINGLE JSON OBJECT — no markdown fences, no prose outside the JSON:
{{
  "title": "{section_title}",
  "content_items": [
    {{
      "text": "Evidence-based claim in GFM markdown. Use **bold** for key terms, tables for structured data, bullets for multi-part claims.",
      "loe": "I | II | III | null",
      "cor": "I | IIa | IIb | III-no-benefit | III-harm | null",
      "source": "Source label e.g. 'AHA/ACC 2022', 'FDA label', 'PubMed PMID:38293847'"
    }}
  ],
  "references": [
    {{
      "title": "Article or guideline title",
      "source": "FDA | PubMed | NICE | AHA | WHO | etc.",
      "pmid": "numeric string or null",
      "year": "4-digit year string or null",
      "url": null
    }}
  ]
}}

QUALITY: Populate content_items with 3-8 comprehensive, evidence-backed claims.
Sparse content_items (fewer than 2 items) are rejected — generate substantive content."""


def build_section_messages(
    section_title: str,
    all_section_titles: "list[str]",
    bluf_text: str,
    query: str,
    query_type: str,
    fetched_data: "FetchedData | None" = None,
    vector_results: "list[SearchResult] | None" = None,
) -> tuple[str, str, str]:
    """Return (system, data_block, user_text) for one Phase-2 section agent call."""
    other_titles = [t for t in all_section_titles if t != section_title]
    other_str = ", ".join(f'"{t}"' for t in other_titles) if other_titles else "none"

    system = (
        f"You are a clinical reference assistant generating one section of a structured medical response.\n"
        f"{APPROVED_SOURCES}\n"
        f"{EVIDENCE_RULES}\n\n"
        f"QUERY TYPE: {query_type}\n"
        f"SECTION TO GENERATE: \"{section_title}\"\n"
        f"OTHER SECTIONS IN THIS RESPONSE (do NOT duplicate their content): {other_str}\n"
        f"ALIGNMENT — keep content consistent with this clinical summary: {bluf_text}\n\n"
        f"Generate ONLY the content for the section \"{section_title}\"."
        + _SECTION_AGENT_SCHEMA.format(section_title=section_title)
    )
    data_block = _build_adaptive_data_block(query_type, fetched_data, vector_results)
    user_text = f"Query: {query}\nSection to generate: {section_title}"
    return system, data_block, user_text
