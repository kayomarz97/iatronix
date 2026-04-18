import type { QueryResponse, ModelInfo } from "./types";

export interface ServiceKeyInfo {
  id: number;
  service_name: string;
  created_at: string;
  updated_at: string;
}

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
      "Authorization": `Bearer ${apiKey}`,
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

export async function listServiceKeys(apiKey: string): Promise<ServiceKeyInfo[]> {
  const res = await fetch("/api/service-keys", {
    headers: { "Authorization": `Bearer ${apiKey}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function saveServiceKey(
  apiKey: string,
  serviceName: string,
  serviceKey: string
): Promise<ServiceKeyInfo> {
  const res = await fetch("/api/service-keys", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ service_name: serviceName, key_value: serviceKey }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function deleteServiceKey(
  apiKey: string,
  serviceName: string
): Promise<void> {
  const res = await fetch(`/api/service-keys/${serviceName}`, {
    method: "DELETE",
    headers: { "Authorization": `Bearer ${apiKey}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}
