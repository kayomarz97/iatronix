export const TRUNCATION_LIMIT = 20;

export const DEFAULT_PROVIDER: "cerebras" | "anthropic" = "cerebras";
export const DEFAULT_MODEL = process.env.NEXT_PUBLIC_CEREBRAS_MODEL ?? "llama3.1-8b";

export const API_KEY_STORAGE_KEY = "iatronix_api_key";
export const LLM_PROVIDER_STORAGE_KEY = "iatronix_llm_provider";
