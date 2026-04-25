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

export interface DegradedResponse {
  message: string;
  suggestion: string;
  cached_similar?: QueryResponse | null;
}

// --- Adaptive (DSPy) ---

export interface AdaptiveContentItem {
  text: string;
  loe?: string;
  cor?: string;
  source?: string;
  pmid?: string;
  url?: string;
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
  section_titles?: string[];
  flowcharts?: AdaptiveFlowchart[];
  tables?: AdaptiveTable[];
}

export interface AdaptiveTable {
  title: string;
  headers: string[];
  rows: string[][];
}

export interface FlowchartBranch {
  condition: string;
  outcome: string;
}

export interface FlowchartStep {
  text: string;
  label?: string;
  is_decision?: boolean;
  branches?: FlowchartBranch[];
}

export interface AdaptiveFlowchart {
  title: string;
  steps: FlowchartStep[];
}

export interface AdaptiveImage {
  url: string;
  caption?: string;
  license?: string;
  source?: string;
}

export interface AdaptiveResponse {
  query_type: string;
  bluf: AdaptiveBLUF;
  sections: AdaptiveSection[];
  references: AdaptiveReference[];
  response_focus: string;
  depth: string;
  related_topics: string[];
  tables?: AdaptiveTable[];
  flowcharts?: AdaptiveFlowchart[];
  images?: AdaptiveImage[];
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
  note?: string;
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
