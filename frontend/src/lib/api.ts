import type { QueryResponse, ModelInfo, AdaptiveBLUF, AdaptiveSection, AdaptiveFlowchart, AdaptiveTable } from "./types";

export type StreamEvent =
  | { type: "stage"; payload: { stage: string } }
  | { type: "token"; payload: { text: string } }
  | { type: "bluf"; payload: AdaptiveBLUF & { section_titles?: string[]; flowcharts?: AdaptiveFlowchart[]; tables?: AdaptiveTable[] } }
  | { type: "section_complete"; payload: AdaptiveSection & { index: number } }
  | { type: "done"; payload: { result: QueryResponse } }
  | { type: "error"; payload: { detail: string } };

export async function* submitQueryStream(
  query: string,
  modelId: string,
  apiKey: string,
): AsyncGenerator<StreamEvent> {
  const res = await fetch("/api/query/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ query, model_id: modelId, model_explicit: false }),
  });

  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const eventMatch = part.match(/^event: (.+)/m);
      const dataMatch = part.match(/^data: (.+)/m);
      if (eventMatch && dataMatch) {
        const type = eventMatch[1].trim() as StreamEvent["type"];
        const payload = JSON.parse(dataMatch[1].trim());
        yield { type, payload } as StreamEvent;
      }
    }
  }
}

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
