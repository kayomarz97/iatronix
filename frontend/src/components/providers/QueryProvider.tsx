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
import { submitQueryStream } from "@/lib/api";
import type { FetchedArticle } from "@/lib/api";
import { useAuth } from "@/components/providers/AuthProvider";
import { API_KEY_STORAGE_KEY, LLM_PROVIDER_STORAGE_KEY } from "@/lib/constants";
import type { QueryResponse, AdaptiveBLUF, AdaptiveSection, AdaptiveFlowchart, AdaptiveTable } from "@/lib/types";
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

function getProviderModel(provider: string): { id: string; name: string } {
  const p = (provider as LLMProvider) in PROVIDER_DEFAULT_MODELS
    ? (provider as LLMProvider)
    : "anthropic";
  return { id: PROVIDER_DEFAULT_MODELS[p], name: PROVIDER_DEFAULT_MODEL_NAMES[p] };
}

interface QueryContextType {
  result: QueryResponse | null;
  streamingText: string;
  streamingBluf: AdaptiveBLUF | null;
  streamingSections: AdaptiveSection[];
  streamingSectionTitles: string[];
  streamingFlowcharts: AdaptiveFlowchart[];
  streamingTables: AdaptiveTable[];
  fetchedArticles: FetchedArticle[];
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
  const [streamingText, setStreamingText] = useState<string>("");
  const [streamingBluf, setStreamingBluf] = useState<AdaptiveBLUF | null>(null);
  const [streamingSections, setStreamingSections] = useState<AdaptiveSection[]>([]);
  const [streamingSectionTitles, setStreamingSectionTitles] = useState<string[]>([]);
  const [streamingFlowcharts, setStreamingFlowcharts] = useState<AdaptiveFlowchart[]>([]);
  const [streamingTables, setStreamingTables] = useState<AdaptiveTable[]>([]);
  const [fetchedArticles, setFetchedArticles] = useState<FetchedArticle[]>([]);
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

    const provider = localStorage.getItem(LLM_PROVIDER_STORAGE_KEY) || "anthropic";
    const { id: modelId, name: modelName } = getProviderModel(provider);
    setActiveModelName(modelName);

    setIsLoading(true);
    setLoadingStage("classifying");
    setStreamingText("");
    setStreamingBluf(null);
    setStreamingSections([]);
    setStreamingSectionTitles([]);
    setStreamingFlowcharts([]);
    setStreamingTables([]);
    setFetchedArticles([]);
    setError(null);
    setResult(null);

    const queryStart = Date.now();

    const runStream = async (key: string) => {
      for await (const event of submitQueryStream(query, modelId, key)) {
        if (event.type === "stage") {
          setLoadingStage(event.payload.stage);
        } else if (event.type === "token") {
          setStreamingText((prev) => prev + event.payload.text);
          setLoadingStage("generating");
        } else if (event.type === "bluf") {
          const { section_titles, flowcharts, tables, ...blufData } = event.payload;
          setStreamingBluf(blufData);
          if (section_titles) setStreamingSectionTitles(section_titles);
          if (flowcharts) setStreamingFlowcharts(flowcharts);
          if (tables) setStreamingTables(tables);
          setLoadingStage("generating");
        } else if (event.type === "fetch_articles") {
          setFetchedArticles(event.payload.titles);
        } else if (event.type === "section_complete") {
          setStreamingSections((prev) => [...prev, event.payload]);
        } else if (event.type === "done") {
          const response = event.payload.result;
          setStreamingText("");
          setStreamingBluf(null);
          setStreamingSections([]);
          setStreamingSectionTitles([]);
          setStreamingFlowcharts([]);
          setStreamingTables([]);
          setResult(response);
          posthog?.capture("query_submitted", {
            query_type: response.query_type,
            cached: response.cached,
            model_id: modelId,
            response_time_ms: Date.now() - queryStart,
          });
        } else if (event.type === "error") {
          const detail = event.payload.detail ?? "An error occurred";
          const err = new Error(detail);
          (err as Error & { errorType?: string }).errorType = event.payload.error_type;
          throw err;
        }
      }
    };

    try {
      await runStream(apiKey);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "An error occurred";
      const errType = (err as Error & { errorType?: string }).errorType;
      if (msg.includes("401")) {
        // Retry once with a fresh token
        let retryApiKey = await getIdToken();
        if (!retryApiKey) retryApiKey = localStorage.getItem(API_KEY_STORAGE_KEY);
        if (retryApiKey && retryApiKey !== apiKey) {
          try {
            setStreamingText("");
            await runStream(retryApiKey);
            return;
          } catch {
            posthog?.capture("query_error", { error_type: "auth", model_id: modelId });
            setError("Session expired. Please sign in again.");
            return;
          }
        }
        posthog?.capture("query_error", { error_type: "auth", model_id: modelId });
        setError("Session expired. Please sign in again.");
      } else if (errType === "rate_limit" || msg.includes("429") || msg.toLowerCase().includes("rate limit")) {
        posthog?.capture("query_error", { error_type: "rate_limit", model_id: modelId });
        setError("Service temporarily busy. Please try again.");
      } else {
        posthog?.capture("query_error", { error_type: errType ?? "other", model_id: modelId });
        setError(msg);
      }
    } finally {
      setIsLoading(false);
      setLoadingStage("");
    }
  }, []);

  const clearResult = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  const value = useMemo(
    () => ({ result, streamingText, streamingBluf, streamingSections, streamingSectionTitles, streamingFlowcharts, streamingTables, fetchedArticles, isLoading, loadingStage, error, activeModelName, submitQuery, clearResult }),
    [result, streamingText, streamingBluf, streamingSections, streamingSectionTitles, streamingFlowcharts, streamingTables, fetchedArticles, isLoading, loadingStage, error, activeModelName, submitQuery, clearResult]
  );

  return <QueryContext.Provider value={value}>{children}</QueryContext.Provider>;
}

export function useQueryContext() {
  const ctx = useContext(QueryContext);
  if (!ctx) throw new Error("useQueryContext must be inside QueryProvider");
  return ctx;
}
