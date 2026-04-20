"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  type ReactNode,
} from "react";
import { submitQuery as apiSubmitQuery } from "@/lib/api";
import { useAuth } from "@/components/providers/AuthProvider";
import { API_KEY_STORAGE_KEY, DEFAULT_MODEL, LLM_PROVIDER_STORAGE_KEY } from "@/lib/constants";
import type { QueryResponse } from "@/lib/types";
import { usePostHog } from "posthog-js/react";

type LLMProvider = "anthropic" | "openai" | "openrouter";

const PROVIDER_DEFAULT_MODELS: Record<LLMProvider, string> = {
  anthropic: "claude-haiku-4-5-20251001",
  openai: "gpt-4o-mini",
  openrouter: "meta-llama/llama-3.3-70b-instruct:free",
};

const PROVIDER_DEFAULT_MODEL_NAMES: Record<LLMProvider, string> = {
  anthropic: "Claude Haiku 4.5",
  openai: "GPT-4o Mini",
  openrouter: "Llama 3.3 70B",
};

export const SOURCE_MODE_KEY = "iatronix_source_mode";

function getProviderModel(provider: string): { id: string; name: string } {
  const p = (provider as LLMProvider) in PROVIDER_DEFAULT_MODELS
    ? (provider as LLMProvider)
    : "anthropic";
  return { id: PROVIDER_DEFAULT_MODELS[p], name: PROVIDER_DEFAULT_MODEL_NAMES[p] };
}

interface QueryContextType {
  result: QueryResponse | null;
  isLoading: boolean;
  loadingStage: string;
  error: string | null;
  activeModelName: string;
  submitQuery: (query: string) => Promise<void>;
  clearResult: () => void;
}

const QueryContext = createContext<QueryContextType | null>(null);

export function QueryProvider({ children }: { children: ReactNode }) {
  const { getIdToken } = useAuth();
  const posthog = usePostHog();
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [activeModelName, setActiveModelName] = useState(PROVIDER_DEFAULT_MODEL_NAMES.anthropic);

  useEffect(() => {
    const provider = localStorage.getItem(LLM_PROVIDER_STORAGE_KEY) || "anthropic";
    setActiveModelName(getProviderModel(provider).name);
  }, []);

  const submitQuery = useCallback(async (query: string) => {
    let apiKey = await getIdToken();
    if (!apiKey) apiKey = localStorage.getItem(API_KEY_STORAGE_KEY);
    if (!apiKey) {
      setError("Please sign in to submit queries");
      return;
    }

    const sourceMode = localStorage.getItem(SOURCE_MODE_KEY) || "ai";
    const provider = localStorage.getItem(LLM_PROVIDER_STORAGE_KEY) || "anthropic";
    const { id: modelId, name: modelName } = getProviderModel(provider);
    setActiveModelName(modelName);

    setIsLoading(true);
    setLoadingStage("classifying");
    setError(null);

    const t1 = setTimeout(() => setLoadingStage("fetching"), 1000);
    const t2 = setTimeout(() => setLoadingStage("generating"), 5000);
    const queryStart = Date.now();

    try {
      const response = await apiSubmitQuery(query, modelId, apiKey, undefined, sourceMode, false);
      setLoadingStage("verifying");
      await new Promise((r) => setTimeout(r, 400));
      setResult(response);
      posthog?.capture("query_submitted", {
        query_type: response.query_type,
        cached: response.cached,
        model_id: modelId,
        response_time_ms: Date.now() - queryStart,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "An error occurred";
      if (msg.includes("401")) {
        let retryApiKey = await getIdToken();
        if (!retryApiKey) retryApiKey = localStorage.getItem(API_KEY_STORAGE_KEY);
        if (retryApiKey && retryApiKey !== apiKey) {
          try {
            const response = await apiSubmitQuery(query, modelId, retryApiKey, undefined, sourceMode, false);
            setLoadingStage("verifying");
            await new Promise((r) => setTimeout(r, 400));
            setResult(response);
            posthog?.capture("query_submitted", {
              query_type: response.query_type,
              cached: response.cached,
              model_id: modelId,
              response_time_ms: Date.now() - queryStart,
            });
            return;
          } catch {
            posthog?.capture("query_error", { error_type: "auth", model_id: modelId });
            setError("Session expired. Please sign in again.");
            return;
          }
        }
        posthog?.capture("query_error", { error_type: "auth", model_id: modelId });
        setError("Session expired. Please sign in again.");
      } else if (msg.includes("429") || msg.toLowerCase().includes("rate limit")) {
        posthog?.capture("query_error", { error_type: "rate_limit", model_id: modelId });
        setError("Rate limit exceeded. Please wait a minute before trying again.");
      } else {
        posthog?.capture("query_error", { error_type: "other", model_id: modelId });
        setError(msg);
      }
    } finally {
      clearTimeout(t1);
      clearTimeout(t2);
      setIsLoading(false);
      setLoadingStage("");
    }
  }, []);

  const clearResult = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  const value = useMemo(
    () => ({ result, isLoading, loadingStage, error, activeModelName, submitQuery, clearResult }),
    [result, isLoading, loadingStage, error, activeModelName, submitQuery, clearResult]
  );

  return <QueryContext.Provider value={value}>{children}</QueryContext.Provider>;
}

export function useQueryContext() {
  const ctx = useContext(QueryContext);
  if (!ctx) throw new Error("useQueryContext must be inside QueryProvider");
  return ctx;
}
