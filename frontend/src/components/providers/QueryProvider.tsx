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
import { API_KEY_STORAGE_KEY, DEFAULT_MODEL, LLM_PROVIDER_STORAGE_KEY } from "@/lib/constants";
import type { QueryResponse } from "@/lib/types";

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
    const apiKey = localStorage.getItem(API_KEY_STORAGE_KEY);
    if (!apiKey) {
      setError("Please sign in to submit queries");
      return;
    }

    const sourceMode = localStorage.getItem(SOURCE_MODE_KEY) || "ai";
    const provider = localStorage.getItem(LLM_PROVIDER_STORAGE_KEY) || "anthropic";
    const { id: modelId, name: modelName } = getProviderModel(provider);
    setActiveModelName(modelName);

    setIsLoading(true);
    setLoadingStage("fetching");
    setError(null);

    const stageTimer = setTimeout(() => setLoadingStage("generating"), 4000);

    try {
      const response = await apiSubmitQuery(query, modelId, apiKey, undefined, sourceMode, false);
      setLoadingStage("validating");
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      clearTimeout(stageTimer);
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
