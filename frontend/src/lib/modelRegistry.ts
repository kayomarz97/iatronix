// Provider/model identity is served by the backend (config/providers.yaml).
// LLMProvider is a free string — the set of providers is data, not a frozen union.
export type LLMProvider = string;

export interface LLMInfo {
  model_id: string;
  display: string;
  provider: LLMProvider;
  input: number;   // $/1M
  output: number;
}

export interface LLMConfig {
  default_provider: LLMProvider;
  providers: Record<string, LLMInfo>;
}

// Richer shape from GET /api/v1/providers (enabled-only, no secrets).
export interface ProviderModel {
  id: string;
  display: string;
  input: number;
  output: number;
  context_window?: number | null;
  tier?: number | null;
}
export interface ProviderPublic {
  id: string;
  display: string;
  supports_vision: boolean;
  key_prefix: string;
  signup_url?: string | null;
  blurb?: string | null;
  default_model: string;
  models: ProviderModel[];
}
export interface ProvidersResponse {
  default_provider: string;
  providers: Record<string, ProviderPublic>;
}

let _cache: LLMConfig | null = null;
let _provCache: ProvidersResponse | null = null;

export async function getLLMConfig(): Promise<LLMConfig> {
  if (_cache) return _cache;
  try {
    const r = await fetch("/api/v1/config/llm");
    if (r.ok) {
      _cache = await r.json();
      return _cache!;
    }
  } catch {
    // fall through to default
  }
  // Fallback if endpoint unreachable (e.g. during SSR or before backend starts)
  return {
    default_provider: "cerebras",
    providers: {
      cerebras: { model_id: "gpt-oss-120b", display: "GPT-OSS 120B (Cerebras)", provider: "cerebras", input: 0.35, output: 0.75 },
      anthropic: { model_id: "claude-haiku-4-5-20251001", display: "Claude Haiku 4.5", provider: "anthropic", input: 1.00, output: 5.00 },
    },
  };
}

/** Enabled providers + models from the registry (drives the settings key-entry UI). */
export async function getProviders(): Promise<ProvidersResponse> {
  if (_provCache) return _provCache;
  try {
    const r = await fetch("/api/v1/providers");
    if (r.ok) {
      _provCache = await r.json();
      return _provCache!;
    }
  } catch {
    // fall through
  }
  // Fallback: synthesise from /config/llm (provider display falls back to model display).
  const cfg = await getLLMConfig();
  const providers: Record<string, ProviderPublic> = {};
  for (const [id, info] of Object.entries(cfg.providers)) {
    providers[id] = {
      id,
      display: info.display,
      supports_vision: false,
      key_prefix: id === "anthropic" ? "sk-ant-" : id === "cerebras" ? "csk-" : "",
      signup_url: null,
      blurb: null,
      default_model: info.model_id,
      models: [{ id: info.model_id, display: info.display, input: info.input, output: info.output }],
    };
  }
  return { default_provider: cfg.default_provider, providers };
}

export function clearLLMConfigCache() {
  _cache = null;
  _provCache = null;
}

export function displayFor(modelId: string, cfg: LLMConfig): string {
  for (const info of Object.values(cfg.providers)) {
    if (info.model_id === modelId) return info.display;
  }
  return modelId;
}
