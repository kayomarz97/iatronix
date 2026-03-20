from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

from app.config import settings


# --- Evidence ---

class EvidencedClaim(BaseModel):
    value: str
    loe: Literal["I", "II-1", "II-2", "II-3", "III"]
    cor: Literal["I", "IIa", "IIb", "III-no-benefit", "III-harm"]
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


# --- Disease Response ---

class TreatmentEntry(EvidencedClaim):
    drug_names: list[str] = []


class DiseaseResponse(BaseModel):
    disease_name: str
    icd_10: Optional[str] = None
    pathophysiology: Optional[EvidencedClaim] = None
    epidemiology: Optional[EvidencedClaim] = None
    clinical_features: list[EvidencedClaim] = []
    diagnostic_criteria: list[EvidencedClaim] = []
    treatment: "TreatmentSection"
    complications: list[EvidencedClaim] = []
    prognosis: Optional[EvidencedClaim] = None
    references: list[Reference] = []


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


# --- General Response ---

class GeneralResponse(BaseModel):
    summary: str
    key_points: list[str] = []
    related_drugs: list[str] = []
    related_conditions: list[str] = []
    confidence: Literal["high", "moderate", "low"]
    references: list[Reference] = []


# --- Degraded Response ---

class DegradedResponse(BaseModel):
    message: str = "AI service temporarily unavailable"
    suggestion: str = "Try again in 30 seconds or switch model"
    cached_similar: Optional["QueryResponse"] = None


# --- Text Nodes ---

class TextNode(BaseModel):
    type: Literal["text", "drug_link"]
    content: str
    drug_query: Optional[str] = None
    match_score: Optional[float] = None


# --- Request / Response ---

class QueryRequest(BaseModel):
    query: str = Field(max_length=settings.max_query_length)
    query_type: Optional[Literal["drug", "disease", "comparative"]] = None
    model_id: str = "claude-sonnet-4-20250514"


class QueryResponse(BaseModel):
    query_type: Literal["drug", "disease", "comparative", "general"]
    model_used: str
    response: Union[DrugResponse, DiseaseResponse, ComparativeResponse, GeneralResponse, DegradedResponse]
    text_nodes: list[TextNode] = []
    safety_warnings: list[str] = []
    validation_warnings: list[str] = []
    disclaimer: str = ""
    cached: bool = False
    truncated: bool = False
    latency_ms: int = 0


DegradedResponse.model_rebuild()
