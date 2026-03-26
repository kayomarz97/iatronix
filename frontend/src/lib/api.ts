import type { QueryResponse, ModelInfo } from "./types";

export async function submitQuery(
  query: string,
  modelId: string,
  apiKey: string,
  queryType?: string,
  sourceMode?: string,
  modelExplicit?: boolean
): Promise<QueryResponse> {
  const res = await fetch("/api/query", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: JSON.stringify({
      query,
      model_id: modelId,
      model_explicit: modelExplicit ?? false,
      query_type: queryType || null,
      source_mode: sourceMode || "ai",
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export async function fetchModels(apiKey: string): Promise<ModelInfo[]> {
  return [];
}
