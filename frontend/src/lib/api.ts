import type { QueryResponse, ModelInfo } from "./types";

export async function submitQuery(
  query: string,
  modelId: string,
  apiKey: string,
  queryType?: string
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
      query_type: queryType || null,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export async function fetchModels(apiKey: string): Promise<ModelInfo[]> {
  const res = await fetch("/api/query", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: JSON.stringify({ _models: true }),
  });

  // Models are fetched from a hardcoded list on the frontend for now
  return [];
}
