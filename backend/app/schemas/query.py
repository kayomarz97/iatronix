from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

from app.config import settings


# --- Evidence ---


class EvidencedClaim(BaseModel):
    value: str
    loe: Optional[str] = None
    cor: Optional[str] = None
    source: str
    source_year: Optional[int] = None
    confidence: Literal["high", "moderate", "low"]


class Reference(BaseModel):
    source: str
    title: Optional[str] = None
    year: Optional[int] = None
    url: Optional[str] = None


# --- Drug Response ---


class DrugDosing(EvidencedClaim):
    route: Optional[str] = None
    frequency: Optional[str] = None


class DrugInteraction(BaseModel):
    drug: str
    severity: Literal["major", "moderate", "minor"]
    description: str
    evidence: Optional[EvidencedClaim] = None


class DrugResponse(BaseModel):
    drug_name: str
    bluf: Optional[str] = Field(default=None, max_length=1000)
    additional_clinical_context: Optional[str] = Field(default=None, max_length=2000)
    drug_class: Optional[str] = None
    mechanism_of_action: Optional[EvidencedClaim] = None
    indications: list[EvidencedClaim] = []
    dosing: list[DrugDosing] = []
    contraindications: list[EvidencedClaim] = []
    side_effects: list[EvidencedClaim] = []
    interactions: list[DrugInteraction] = []
    pharmacokinetics: Optional[EvidencedClaim] = None
    special_populations: list[EvidencedClaim] = []
    monitoring: list[EvidencedClaim] = []
    references: list[Reference] = []
    tables: list[dict] = []
    flowcharts: list[dict] = []
    extended_data: Optional[dict] = None


# --- Disease Response ---


class TreatmentEntry(EvidencedClaim):
    drug_names: list[str] = []


class DiseaseResponse(BaseModel):
    disease_name: str
    bluf: Optional[str] = Field(default=None, max_length=1000)
    additional_clinical_context: Optional[str] = Field(default=None, max_length=2000)
    icd_10: Optional[str] = None
    etiology: list[EvidencedClaim] = []
    pathophysiology: Optional[EvidencedClaim] = None
    epidemiology: Optional[EvidencedClaim] = None
    clinical_features: list[EvidencedClaim] = []
    diagnostic_criteria: list[EvidencedClaim] = []
    treatment: "TreatmentSection" = Field(default_factory=lambda: TreatmentSection())
    complications: list[EvidencedClaim] = []
    prognosis: Optional[EvidencedClaim] = None
    references: list[Reference] = []
    tables: list[dict] = []
    flowcharts: list[dict] = []
    extended_data: Optional[dict] = None


class TreatmentSection(BaseModel):
    first_line: list[TreatmentEntry] = []
    second_line: list[TreatmentEntry] = []
    adjunctive: list[TreatmentEntry] = []
    non_pharmacological: list[EvidencedClaim] = []


DiseaseResponse.model_rebuild()


# --- Comparative Response ---


class ComparisonDimension(BaseModel):
    dimension: str
    values: dict[str, EvidencedClaim]


class ComparativeResponse(BaseModel):
    entities_compared: list[str]
    comparison_type: Optional[str] = None
    summary: Optional[EvidencedClaim] = None
    detailed_comparison: list[ComparisonDimension] = []
    clinical_preference: Optional[EvidencedClaim] = None
    references: list[Reference] = []
    extended_data: Optional[dict] = None


# --- Procedure Response ---


class ProcedureStep(BaseModel):
    step_number: int
    description: str
    notes: Optional[str] = None


class ProcedureGuideline(EvidencedClaim):
    society: Optional[str] = None


class ProcedureResponse(BaseModel):
    procedure_name: str
    indications: list[EvidencedClaim] = []
    contraindications: list[EvidencedClaim] = []
    technique_steps: list[ProcedureStep] = []
    complications: list[EvidencedClaim] = []
    guidelines: list[ProcedureGuideline] = []
    references: list[Reference] = []
    extended_data: Optional[dict] = None


# --- Evidence Response ---


class StudyEvidence(BaseModel):
    title: str
    pmid: Optional[str] = None
    year: Optional[int] = None
    finding: str
    sample_size: Optional[str] = None
    loe: Literal["I", "II-1", "II-2", "II-3", "III"]


class EvidenceResponse(BaseModel):
    query_topic: str
    summary: str
    supporting_studies: list[StudyEvidence] = []
    opposing_studies: list[StudyEvidence] = []
    clinical_recommendation: Optional[EvidencedClaim] = None
    guideline_status: str = "No formal guideline exists"
    references: list[Reference] = []
    extended_data: Optional[dict] = None


# --- General Response ---


class GeneralResponse(BaseModel):
    summary: str
    key_points: list[str] = []
    related_drugs: list[str] = []
    related_conditions: list[str] = []
    confidence: Literal["high", "moderate", "low"]
    references: list[Reference] = []
    extended_data: Optional[dict] = None


# --- Degraded Response ---


class DegradedResponse(BaseModel):
    message: str = "AI service temporarily unavailable"
    suggestion: str = "Try again in 30 seconds or switch model"
    cached_similar: Optional["QueryResponse"] = None


# --- Adaptive (DSPy) ---


class AdaptiveBLUF(BaseModel):
    headline: str
    body: Optional[str] = None
    key_points: list[str] = []
    caveats: list[str] = []


class AdaptiveContentItem(BaseModel):
    text: str
    loe: Optional[str] = None
    cor: Optional[str] = None
    source: Optional[str] = None
    pmid: Optional[str] = None
    url: Optional[str] = None


class AdaptiveReference(BaseModel):
    title: str
    source: Optional[str] = None
    pmid: Optional[Union[str, int]] = None
    url: Optional[str] = None
    year: Optional[Union[str, int]] = None


class AdaptiveSection(BaseModel):
    title: str
    content: Any = None
    content_items: list[AdaptiveContentItem] = []
    loe: Optional[str] = None
    cor: Optional[str] = None


class AdaptiveResponse(BaseModel):
    query_type: str
    bluf: AdaptiveBLUF
    sections: list[AdaptiveSection]
    references: list[AdaptiveReference] = []
    response_focus: str
    depth: str
    related_topics: list[str] = []
    tables: list[dict] = []
    flowcharts: list[dict] = []
    images: list[dict] = []
    extended_data: Optional[dict] = None


# --- Text Nodes ---


class TextNode(BaseModel):
    type: Literal["text", "drug_link"]
    content: str
    drug_query: Optional[str] = None
    match_score: Optional[float] = None


# --- Request / Response ---


class QueryRequest(BaseModel):
    query: str = Field(max_length=settings.max_query_length)
    query_type: Optional[
        Literal["drug", "disease", "comparative", "procedure", "evidence", "complex"]
    ] = None
    model_id: str = "claude-haiku-4-5-20251001"
    model_explicit: bool = (
        False  # True when user explicitly chose a model (not just default)
    )
    source_mode: Literal["ai", "scraping", "pdfs"] = "ai"


class ModelCost(BaseModel):
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    subtotal_usd: float = 0.0


class TokenUsage(BaseModel):
    models: list[ModelCost] = []
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    note: str = ""


class QueryResponse(BaseModel):
    query_type: Literal[
        "drug", "disease", "comparative", "general", "procedure", "evidence", "adaptive", "complex"
    ]
    model_used: str
    response: Union[AdaptiveResponse, DegradedResponse]
    text_nodes: list[TextNode] = []
    safety_warnings: list[str] = []
    validation_warnings: list[str] = []
    disclaimer: str = ""
    cached: bool = False
    truncated: bool = False
    latency_ms: int = 0
    recommendation_level: Optional[str] = None
    audit_id: Optional[int] = None
    version: str = "2.1"
    needs_review: bool = False
    rewritten_query: Optional[str] = None
    fetch_sources: list[str] = []
    token_usage: Optional[TokenUsage] = None


DegradedResponse.model_rebuild()
