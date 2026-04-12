from __future__ import annotations

from typing import Literal

import dspy


class MedicalQueryAnalysis(dspy.Signature):
    """Analyze a medical query to determine what information the user actually needs."""

    query: str = dspy.InputField()
    available_data_types: str = dspy.InputField(
        desc="What API data was fetched (e.g. 'FDA label, PubMed guidelines')"
    )

    query_type: Literal[
        "drug", "disease", "comparative", "procedure", "evidence", "general"
    ] = dspy.OutputField()
    required_sections: list[str] = dspy.OutputField(
        desc="Only the sections relevant to this query"
    )
    depth: Literal["quick", "standard", "comprehensive"] = dspy.OutputField(
        desc="quick=simple factual lookup; standard=typical clinical query; comprehensive=complex multi-faceted question requiring full detail"
    )
    entities: list[str] = dspy.OutputField()
    condition_context: str = dspy.OutputField(
        desc="If the query is about a drug or intervention in a specific disease/condition, return that condition; otherwise return an empty string."
    )
    response_focus: str = dspy.OutputField(
        desc="What the user actually wants to know in 1 sentence"
    )
    related_topics: list[str] = dspy.OutputField(
        desc="5-8 related clinical topics the user might want to explore next. Examples: related drugs, differential diagnoses, management guidelines, complications, monitoring parameters."
    )


class MedicalResponseGeneration(dspy.Signature):
    """Generate an evidence-based medical response using fetched data ONLY.

    CRITICAL ANTI-HALLUCINATION RULES:
    - Generate content EXCLUSIVELY from the provided fetched_data. Do NOT use training knowledge.
    - Every claim must trace to a specific data source label in fetched_data (e.g. [SOURCE: FDA label], [SOURCE: PubMed PMID 12345678]).
    - If a required section has no supporting data in fetched_data, write content_items with a single item: {"text": "Insufficient data from available sources for this section.", "loe": null, "cor": null, "source": null}
    - NEVER invent drug doses, contraindications, adverse effects, or clinical outcomes not present in fetched_data.
    - Include only the required_sections listed — do not add extra sections.
    - The first section must directly answer the user's question before broader background sections.
    - If query_type=drug and condition_context is non-empty, prioritize condition-management guidelines and the drug's role in that condition before generic FDA-label facts.
    - If query_type=disease, answer the user's management/diagnosis/prognosis question first, then expand into disease detail.
    """

    query: str = dspy.InputField()
    query_type: str = dspy.InputField(
        desc="One of drug, disease, comparative, procedure, evidence, general"
    )
    condition_context: str = dspy.InputField(
        desc="Condition context for drug/comparative queries when present, otherwise empty string"
    )
    response_focus: str = dspy.InputField()
    fetched_data: str = dspy.InputField(
        desc="Raw data from FDA, PubMed, NICE APIs — each block prefixed with [SOURCE: ...]. Use ONLY this data."
    )
    vector_context: str = dspy.InputField(
        desc="Relevant excerpts from indexed documents"
    )
    required_sections: str = dspy.InputField(
        desc="Comma-separated list of sections to include"
    )
    depth: str = dspy.InputField(
        desc="quick=50-100 words/section; standard=100-200 words/section; comprehensive=200-400 words/section with full clinical detail"
    )

    response_json: str = dspy.OutputField(
        desc=(
            "JSON object with exactly this structure: "
            '{"sections": ['
            '{"title": "<section name>", '
            '"content_items": ['
            '{"text": "<evidence-based text — write in GitHub-flavored markdown: use **bold** for key terms, '
            '- bullets for lists, | col | tables for comparisons, blank lines between paragraphs>", '
            '"loe": "<I|II|III|null — I=RCT/meta-analysis, II=observational, III=expert opinion>", '
            '"cor": "<I|IIa|IIb|III-no-benefit|III-harm|null>", '
            '"source": "<cite the exact [SOURCE: ...] label from fetched_data>"}], '
            '"loe": "<overall section LOE: I|II|III|null>", '
            '"cor": "<overall section COR: I|IIa|IIb|III-no-benefit|III-harm|null>"}], '
            '"references": ['
            '{"title": "<article or guideline title>", '
            '"source": "<FDA|PubMed|NICE|DailyMed|RxNorm|etc>", '
            '"pmid": "<numeric PMID if from PubMed, else null>", '
            '"year": "<4-digit year or null>"}]}. '
            "Section ordering rule: section 1 must directly answer the user's clinical question. "
            "If query_type=drug and condition_context is non-empty, early sections must prioritize guideline positioning, role in the condition, practical use, monitoring, and safety in that condition before generic label background. "
            "If query_type=disease, early sections must prioritize the user's actual question such as management, diagnosis, workup, or prognosis before broader background sections. "
            "If query_type=comparative or query_type=evidence, early sections must state the clinical bottom line before supporting details. "
            "Each section must have at least 2 content_items (unless no data available — then use the insufficient-data placeholder). "
            "Content depth: comprehensive=200-400 words/section; standard=100-200 words; quick=50-100 words. "
            "Output ONLY valid JSON starting with { and ending with }. No markdown fences around the JSON."
        )
    )
    bluf_json: str = dspy.OutputField(
        desc=(
            "Bottom Line Up Front as a JSON object. "
            "Scale content to the richness of fetched_data: "
            "(1) fetched_data > 8000 chars → include all four fields: headline + body (4-6 sentence elaboration) + key_points (4-6 action bullets) + caveats if any safety warnings; "
            "(2) fetched_data 2000–8000 chars → headline + body (2-3 sentences) + key_points (2-3 bullets) + caveats if any; "
            "(3) fetched_data < 2000 chars → headline only, omit body/key_points/caveats. "
            "Fields: headline (string, always present — single most important clinical sentence), "
            "body (string or null — elaboration sentences, omit if sparse data), "
            "key_points (array of strings — action bullets with specific numbers/doses/thresholds, omit if sparse data), "
            "caveats (array of strings — safety warnings only, omit if none). "
            "Output ONLY valid JSON starting with { and ending with }. No markdown fences. "
            'Example for rich data: {"headline": "Metformin is first-line for T2DM with strong cardiovascular benefit.", '
            '"body": "Initiating at 500 mg twice daily minimises GI side effects. Titrate to 2000 mg/day over 4 weeks.", '
            '"key_points": ["Dose: 500 mg twice daily, titrate to 2000 mg/day", "Contraindicated: eGFR < 30 mL/min/1.73m²", "Monitor: renal function annually"], '
            '"caveats": ["Hold 48 h before contrast procedures"]}. '
            'Example for sparse data: {"headline": "Metformin is the preferred first-line agent for type 2 diabetes."}'
        )
    )
