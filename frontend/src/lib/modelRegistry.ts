export type LLMProvider = "cerebras" | "anthropic" | "openrouter";

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

let _cache: LLMConfig | null = null;

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
      anthropic: { model_id: "claude-haiku-4-5-20251001", display: "Claude Haiku 4.5", provider: "anthropic", input: 0.80, output: 4.00 },
    },
  };
}

export function clearLLMConfigCache() {
  _cache = null;
}

export function displayFor(modelId: string, cfg: LLMConfig): string {
  for (const info of Object.values(cfg.providers)) {
    if (info.model_id === modelId) return info.display;
  }
  return modelId;
}
