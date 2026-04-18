export interface EvidencedClaim {
  value: string;
  loe: string;
  cor?: string | null;
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
  bluf?: string | null;
  additional_clinical_context?: string | null;
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
  tables?: { title: string; headers: string[]; rows: string[][] }[];
  flowcharts?: { title: string; steps: string[] }[];
  extended_data?: Record<string, unknown> | null;
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
  bluf?: string | null;
  additional_clinical_context?: string | null;
  icd_10?: string | null;
  etiology: EvidencedClaim[];
  pathophysiology?: EvidencedClaim | null;
  epidemiology?: EvidencedClaim | null;
  clinical_features: EvidencedClaim[];
  diagnostic_criteria: EvidencedClaim[];
  treatment: TreatmentSection;
  complications: EvidencedClaim[];
  prognosis?: EvidencedClaim | null;
  tables?: { title: string; headers: string[]; rows: string[][] }[];
  flowcharts?: { title: string; steps: string[] }[];
  extended_data?: Record<string, unknown> | null;
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
  extended_data?: Record<string, unknown> | null;
  references: Reference[];
}

export interface GeneralResponse {
  summary: string;
  key_points: string[];
  related_drugs: string[];
  related_conditions: string[];
  confidence: "high" | "moderate" | "low";
  extended_data?: Record<string, unknown> | null;
  references: Reference[];
}

export interface DegradedResponse {
  message: string;
  suggestion: string;
  cached_similar?: QueryResponse | null;
}

// --- Procedure Response ---

export interface ProcedureStep {
  step_number: number;
  description: string;
  notes?: string | null;
}

export interface ProcedureGuideline extends EvidencedClaim {
  society?: string | null;
}

export interface ProcedureResponse {
  procedure_name: string;
  indications: EvidencedClaim[];
  contraindications: EvidencedClaim[];
  technique_steps: ProcedureStep[];
  complications: EvidencedClaim[];
  guidelines: ProcedureGuideline[];
  extended_data?: Record<string, unknown> | null;
  references: Reference[];
}

// --- Evidence Response ---

export interface StudyEvidence {
  title: string;
  pmid?: string | null;
  year?: number | null;
  finding: string;
  sample_size?: string | null;
  loe: string;
}

export interface EvidenceResponse {
  query_topic: string;
  summary: string;
  supporting_studies: StudyEvidence[];
  opposing_studies: StudyEvidence[];
  clinical_recommendation?: EvidencedClaim | null;
  guideline_status: string;
  extended_data?: Record<string, unknown> | null;
  references: Reference[];
}

// --- Adaptive (DSPy) ---

export interface AdaptiveContentItem {
  text: string;
  loe?: string;
  cor?: string;
  source?: string;
}

export interface AdaptiveReference {
  title: string;
  source?: string;
  pmid?: string;
  url?: string;
  year?: string;
}

export interface AdaptiveSection {
  title: string;
  content?: unknown;
  content_items: AdaptiveContentItem[];
  loe?: string;
  cor?: string;
}

export interface AdaptiveBLUF {
  headline: string;
  body?: string | null;
  key_points: string[];
  caveats: string[];
}

export interface AdaptiveResponse {
  query_type: string;
  bluf: AdaptiveBLUF;
  sections: AdaptiveSection[];
  references: AdaptiveReference[];
  response_focus: string;
  depth: string;
  related_topics: string[];
}

// --- Text Nodes ---

export interface TextNode {
  type: "text" | "drug_link";
  content: string;
  drug_query?: string | null;
  match_score?: number | null;
}

// --- Token Usage ---

export interface ModelCost {
  model_id: string;
  input_tokens: number;
  output_tokens: number;
  input_cost_usd: number;
  output_cost_usd: number;
  subtotal_usd: number;
}

export interface TokenUsage {
  models: ModelCost[];
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
}

// --- Request / Response ---

export interface QueryResponse {
  query_type:
    | "drug"
    | "disease"
    | "comparative"
    | "general"
    | "procedure"
    | "evidence"
    | "adaptive";
  model_used: string;
  response: AdaptiveResponse | DegradedResponse;
  text_nodes: TextNode[];
  safety_warnings: string[];
  validation_warnings: string[];
  disclaimer: string;
  cached: boolean;
  truncated: boolean;
  latency_ms: number;
  recommendation_level?: string | null;
  audit_id?: number | null;
  version?: string;
  needs_review?: boolean;
  rewritten_query?: string | null;
  fetch_sources?: string[];
  token_usage?: TokenUsage | null;
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  description: string;
}

// --- Document Types ---

export interface DocumentInfo {
  id: number;
  title: string;
  source_type: string;
  file_name?: string | null;
  page_count?: number | null;
  verified: boolean;
  publisher?: string | null;
  chunk_count: number;
  created_at: string;
}

export interface DocumentListResponse {
  documents: DocumentInfo[];
  total: number;
  verified_count: number;
}

// --- Auth Types ---

export interface AuthResponse {
  api_key: string;
  email: string;
  message: string;
}

export interface LLMKeyStatus {
  provider: string;
  is_set: boolean;
  message: string;
}
