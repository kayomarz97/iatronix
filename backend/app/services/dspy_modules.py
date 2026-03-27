import dspy

from app.services.dspy_signatures import MedicalQueryAnalysis, MedicalResponseGeneration


class AdaptiveMedicalPipeline(dspy.Module):
    def __init__(self) -> None:
        self.analyzer = dspy.ChainOfThought(MedicalQueryAnalysis)
        self.generator = dspy.ChainOfThought(MedicalResponseGeneration)

    def forward(
        self,
        query: str,
        fetched_data: str,
        vector_results: str,
        available_data_types: str,
    ):
        analysis = self.analyzer(
            query=query,
            available_data_types=available_data_types,
        )
        response = self.generator(
            query=query,
            response_focus=analysis.response_focus,
            fetched_data=fetched_data,
            vector_context=vector_results,
            required_sections=", ".join(analysis.required_sections),
            depth=analysis.depth,
        )
        return analysis, response
