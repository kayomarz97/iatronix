export interface EvidencedClaim {
  value: string;
  loe: string;
  cor: string;
  source: string;
  source_year?: number | null;
  confidence: "high" | "moderate" | "low";
}

export interface Reference {
  source: string;
  title?: string | null;
  year?: number | null;
  url?: string | null;
}

export interface DrugDosing extends EvidencedClaim {
  route?: string | null;
  frequency?: string | null;
}

export interface DrugInteraction {
  drug: string;
  severity: "major" | "moderate" | "minor";
  description: string;
  evidence?: EvidencedClaim | null;
}

export interface DrugResponse {
  drug_name: string;
  drug_class?: string | null;
  mechanism_of_action?: EvidencedClaim | null;
  indications: EvidencedClaim[];
  dosing: DrugDosing[];
  contraindications: EvidencedClaim[];
  side_effects: EvidencedClaim[];
  interactions: DrugInteraction[];
  pharmacokinetics?: EvidencedClaim | null;
  special_populations: EvidencedClaim[];
  monitoring: EvidencedClaim[];
  references: Reference[];
}

export interface TreatmentEntry extends EvidencedClaim {
  drug_names: string[];
}

export interface TreatmentSection {
  first_line: TreatmentEntry[];
  second_line: TreatmentEntry[];
  adjunctive: TreatmentEntry[];
  non_pharmacological: EvidencedClaim[];
}

export interface DiseaseResponse {
  disease_name: string;
  icd_10?: string | null;
  pathophysiology?: EvidencedClaim | null;
  epidemiology?: EvidencedClaim | null;
  clinical_features: EvidencedClaim[];
  diagnostic_criteria: EvidencedClaim[];
  treatment: TreatmentSection;
  complications: EvidencedClaim[];
  prognosis?: EvidencedClaim | null;
  references: Reference[];
}

export interface ComparisonDimension {
  dimension: string;
  values: Record<string, EvidencedClaim>;
}

export interface ComparativeResponse {
  entities_compared: string[];
  comparison_type?: string | null;
  summary?: EvidencedClaim | null;
  detailed_comparison: ComparisonDimension[];
  clinical_preference?: EvidencedClaim | null;
  references: Reference[];
}

export interface GeneralResponse {
  summary: string;
  key_points: string[];
  related_drugs: string[];
  related_conditions: string[];
  confidence: "high" | "moderate" | "low";
  references: Reference[];
}

export interface DegradedResponse {
  message: string;
  suggestion: string;
  cached_similar?: QueryResponse | null;
}

export interface TextNode {
  type: "text" | "drug_link";
  content: string;
  drug_query?: string | null;
  match_score?: number | null;
}

export interface QueryResponse {
  query_type: "drug" | "disease" | "comparative" | "general";
  model_used: string;
  response:
    | DrugResponse
    | DiseaseResponse
    | ComparativeResponse
    | GeneralResponse
    | DegradedResponse;
  text_nodes: TextNode[];
  safety_warnings: string[];
  validation_warnings: string[];
  disclaimer: string;
  cached: boolean;
  truncated: boolean;
  latency_ms: number;
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  description: string;
}
