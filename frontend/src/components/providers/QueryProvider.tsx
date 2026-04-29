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
import type { QueryResponse, AdaptiveBLUF, AdaptiveSection, AdaptiveFlowchart, AdaptiveTable, AdaptiveResponse } from "@/lib/types";
import { usePostHog } from "posthog-js/react";
import { getLLMConfig, displayFor, type LLMConfig } from "@/lib/modelRegistry";

type LLMProvider = "cerebras" | "anthropic" | "openai" | "openrouter";

const PROVIDER_DEFAULT_MODELS: Record<string, string> = {
  openai: "gpt-4o-mini",
  openrouter: "google/gemma-4-31b-it",
};

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
  isFallback: boolean;
  fallbackModel: string | null;
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
  const [activeModelName, setActiveModelName] = useState("GPT-OSS 120B (Cerebras)");
  const [isFallback, setIsFallback] = useState(false);
  const [fallbackModel, setFallbackModel] = useState<string | null>(null);
  const [llmConfig, setLlmConfig] = useState<LLMConfig | null>(null);

  useEffect(() => {
    getLLMConfig().then((cfg) => {
      setLlmConfig(cfg);
      const provider = localStorage.getItem(LLM_PROVIDER_STORAGE_KEY) || cfg.default_provider;
      const info = cfg.providers[provider];
      if (info) setActiveModelName(info.display);
    });
  }, []);

  const submitQuery = useCallback(async (query: string) => {
    let apiKey = await getIdToken();
    if (!apiKey) apiKey = localStorage.getItem(API_KEY_STORAGE_KEY);
    if (!apiKey) {
      setError("Please sign in to submit queries");
      return;
    }

    const provider = localStorage.getItem(LLM_PROVIDER_STORAGE_KEY) || llmConfig?.default_provider || "cerebras";
    const cfg = llmConfig || await getLLMConfig();
    const providerInfo = cfg.providers[provider];
    const modelId = providerInfo?.model_id ?? PROVIDER_DEFAULT_MODELS[provider] ?? "gpt-oss-120b";
    const modelName = providerInfo?.display ?? modelId;
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
    setIsFallback(false);
    setFallbackModel(null);

    const queryStart = Date.now();

    posthog?.capture("query_started", {
      query_text: query,
      model_id: modelId,
      provider,
    });

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
        } else if (event.type === "model_info") {
          if (event.payload.is_fallback) {
            setIsFallback(true);
            setFallbackModel(event.payload.model);
          }
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
          const adaptiveResp = response.response as AdaptiveResponse;
          posthog?.capture("query_submitted", {
            // Query identity
            query_text: query,
            query_type: response.query_type,
            rewritten_query: response.rewritten_query ?? null,
            audit_id: response.audit_id ?? null,

            // Model info
            model_id: modelId,
            model_used: response.model_used,
            provider,
            cached: response.cached,

            // Performance
            response_time_ms: Date.now() - queryStart,
            latency_ms: response.latency_ms,

            // Data sources (which APIs were searched)
            fetch_sources: response.fetch_sources ?? [],
            fetch_sources_count: (response.fetch_sources ?? []).length,

            // Answer summary
            bluf_headline: adaptiveResp?.bluf?.headline ?? null,
            sections_count: adaptiveResp?.sections?.length ?? 0,
            references_count: adaptiveResp?.references?.length ?? 0,
          });

          // Separate full-answer event — for browsing exactly what users received
          posthog?.capture("answer_viewed", {
            query_text: query,
            query_type: response.query_type,
            model_used: response.model_used,
            fetch_sources: response.fetch_sources ?? [],
            bluf_headline: adaptiveResp?.bluf?.headline ?? null,
            bluf_body: adaptiveResp?.bluf?.body ?? null,
            bluf_key_points: adaptiveResp?.bluf?.key_points ?? [],
            bluf_caveats: adaptiveResp?.bluf?.caveats ?? [],
            section_titles: adaptiveResp?.sections?.map((s) => s.title) ?? [],
            references_count: adaptiveResp?.references?.length ?? 0,
            cached: response.cached,
            audit_id: response.audit_id ?? null,
          });

          // PostHog native LLM analytics — only emit when LLM was actually called
          if (!response.cached) {
            const providerDisplay: Record<string, string> = {
              cerebras: "Cerebras",
              anthropic: "Anthropic",
              openai: "OpenAI",
              openrouter: "OpenRouter",
            };

            posthog?.capture("$ai_generation", {
              // Required PostHog LLM properties
              $ai_model: response.model_used,
              $ai_provider: providerDisplay[provider] ?? provider,
              $ai_input_tokens: response.token_usage?.total_input_tokens ?? 0,
              $ai_output_tokens: response.token_usage?.total_output_tokens ?? 0,
              $ai_total_cost_usd: response.token_usage?.total_cost_usd ?? undefined,

              // Trace grouping — links LLM call to the query in PostHog
              $ai_trace_id: response.audit_id?.toString() ?? undefined,
              $ai_span_name: `medical_query_${response.query_type}`,

              // Input/output content (for PostHog Generations viewer)
              $ai_input: [{ role: "user", content: query }],
              $ai_output_choices: [{
                role: "assistant",
                content: (response.response as AdaptiveResponse)?.bluf?.headline ?? "",
              }],

              // Custom context properties (filterable in PostHog dashboard)
              query_type: response.query_type,
              fetch_sources: response.fetch_sources ?? [],
              sections_count: adaptiveResp?.sections?.length ?? 0,
              latency_ms: response.latency_ms,
            });
          }
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
            posthog?.capture("query_error", { error_type: "auth", model_id: modelId, query_text: query });
            setError("Session expired. Please sign in again.");
            return;
          }
        }
        posthog?.capture("query_error", { error_type: "auth", model_id: modelId, query_text: query });
        setError("Session expired. Please sign in again.");
      } else if (errType === "rate_limit" || msg.includes("429") || msg.toLowerCase().includes("rate limit")) {
        posthog?.capture("query_error", { error_type: "rate_limit", model_id: modelId, query_text: query });
        setError("Service temporarily busy. Please try again.");
      } else {
        posthog?.capture("query_error", { error_type: errType ?? "other", model_id: modelId, query_text: query });
        setError(msg);
      }
    } finally {
      setIsLoading(false);
      setLoadingStage("");
    }
  }, [llmConfig]);

  const clearResult = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  const value = useMemo(
    () => ({ result, streamingText, streamingBluf, streamingSections, streamingSectionTitles, streamingFlowcharts, streamingTables, fetchedArticles, isLoading, loadingStage, error, activeModelName, isFallback, fallbackModel, submitQuery, clearResult }),
    [result, streamingText, streamingBluf, streamingSections, streamingSectionTitles, streamingFlowcharts, streamingTables, fetchedArticles, isLoading, loadingStage, error, activeModelName, isFallback, fallbackModel, submitQuery, clearResult]
  );

  return <QueryContext.Provider value={value}>{children}</QueryContext.Provider>;
}

export function useQueryContext() {
  const ctx = useContext(QueryContext);
  if (!ctx) throw new Error("useQueryContext must be inside QueryProvider");
  return ctx;
}
