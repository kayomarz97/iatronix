import json
import logging
import types

import dspy

from app.services.dspy_signatures import MedicalQueryAnalysis, MedicalResponseGeneration

logger = logging.getLogger(__name__)

_REQUIRED_SECTIONS = {
    "disease": ["etiology", "clinical_features", "diagnostic_criteria", "treatment", "prognosis"],
    "drug": ["indications", "dosing", "contraindications", "side_effects"],
    "procedure": ["indications", "technique_steps", "complications"],
    "evidence": ["supporting_studies", "summary"],
}


class AdaptiveMedicalPipeline(dspy.Module):
    def __init__(self) -> None:
        self.analyzer = dspy.ChainOfThought(MedicalQueryAnalysis)
        self.generator = dspy.ChainOfThought(MedicalResponseGeneration)

    def _is_critically_sparse(self, response_json: str, query_type: str) -> bool:
        """Return True if the response is missing more than one required section."""
        try:
            data = json.loads(response_json)
        except Exception:
            return True
        required = _REQUIRED_SECTIONS.get(query_type, [])
        missing = [s for s in required if not data.get(s)]
        return len(missing) > 1

    def forward(
        self,
        query: str,
        fetched_data: str,
        vector_results: str,
        available_data_types: str,
        query_type_hint: str | None = None,
        condition_context_hint: str | None = None,
        pre_analysis: dict | None = None,
    ):
        if pre_analysis is not None:
            # Re-use Step 1 analysis result — skip the redundant LLM call
            _qt = query_type_hint or pre_analysis.get("query_type", "general") or "general"
            analysis = types.SimpleNamespace(
                query_type=_qt,
                condition_context=pre_analysis.get("condition_context") or "",
                response_focus=pre_analysis.get("response_focus") or "",
                depth=pre_analysis.get("depth") or "standard",
                required_sections=_REQUIRED_SECTIONS.get(_qt, []),
                related_topics=pre_analysis.get("related_topics") or [],
            )
        else:
            analysis = self.analyzer(
                query=query,
                available_data_types=available_data_types,
            )

        resolved_query_type = str(
            query_type_hint or getattr(analysis, "query_type", "general") or "general"
        )
        resolved_condition_context = str(
            (
                condition_context_hint
                if condition_context_hint is not None
                else getattr(analysis, "condition_context", "")
            )
            or ""
        )
        response = self.generator(
            query=query,
            query_type=resolved_query_type,
            condition_context=resolved_condition_context,
            response_focus=analysis.response_focus,
            fetched_data=fetched_data,
            vector_context=vector_results,
            required_sections=", ".join(analysis.required_sections),
            depth=analysis.depth,
        )

        # Sparse-response retry (item 5): one retry with expansion instruction
        resp_json = getattr(response, "response_json", "") or ""
        if self._is_critically_sparse(resp_json, resolved_query_type):
            logger.info(
                "DSPy response critically sparse for %s — retrying with expansion",
                resolved_query_type,
            )
            response = self.generator(
                query=query,
                query_type=resolved_query_type,
                condition_context=resolved_condition_context,
                response_focus=analysis.response_focus + (
                    "\n\nIMPORTANT: Previous response was critically sparse. "
                    "Expand ALL required sections. Use full token budget. Do NOT truncate."
                ),
                fetched_data=fetched_data,
                vector_context=vector_results,
                required_sections=", ".join(analysis.required_sections),
                depth=analysis.depth,
            )

        analysis.query_type = resolved_query_type
        analysis.condition_context = resolved_condition_context
        return analysis, response
