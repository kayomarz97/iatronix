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
    depth: Literal["quick", "standard", "comprehensive"] = dspy.OutputField()
    entities: list[str] = dspy.OutputField()
    response_focus: str = dspy.OutputField(
        desc="What the user actually wants to know in 1 sentence"
    )


class MedicalResponseGeneration(dspy.Signature):
    """Generate an evidence-based medical response using fetched data. Include only the requested sections."""

    query: str = dspy.InputField()
    response_focus: str = dspy.InputField()
    fetched_data: str = dspy.InputField(desc="Raw data from FDA, PubMed, NICE APIs")
    vector_context: str = dspy.InputField(
        desc="Relevant excerpts from indexed documents"
    )
    required_sections: str = dspy.InputField(
        desc="Comma-separated list of sections to include"
    )
    depth: str = dspy.InputField()

    response_json: str = dspy.OutputField(
        desc=(
            'JSON object with exactly this structure: '
            '{"sections": [{"title": "<section name>", "content": "<evidence-based text>", '
            '"loe": "<I|II|III|null>", "cor": "<I|IIa|IIb|III|null>"}], "references": ["<source>"]}. '
            "Include only the required_sections. "
            "Do NOT nest further — content is a plain string. "
            "Output ONLY valid JSON starting with { and ending with }."
        )
    )
    bluf: str = dspy.OutputField(desc="Bottom line up front — 2 sentences max")
