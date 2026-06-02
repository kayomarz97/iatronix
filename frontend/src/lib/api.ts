import type { QueryResponse, ModelInfo, AdaptiveBLUF, AdaptiveSection, AdaptiveFlowchart, AdaptiveTable } from "./types";

export interface FetchedArticle {
  title: string;
  journal?: string;
  year?: number | null;
  pmid?: string;
}

export type StreamEvent =
  | { type: "stage"; payload: { stage: string } }
  | { type: "token"; payload: { text: string } }
  | { type: "bluf"; payload: AdaptiveBLUF & { section_titles?: string[]; flowcharts?: AdaptiveFlowchart[]; tables?: AdaptiveTable[] } }
  | { type: "section_complete"; payload: AdaptiveSection & { index: number } }
  | { type: "fetch_articles"; payload: { titles: FetchedArticle[] } }
  | { type: "model_info"; payload: { is_fallback: boolean; model: string } }
  | { type: "reconnecting"; payload: { attempt: number } }
  | { type: "done"; payload: { result: QueryResponse } }
  | { type: "error"; payload: { detail: string; error_type?: string } };

const RESUME_MAX_ATTEMPTS = 15;

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// Resolve once the tab is foreground again. Mobile browsers freeze background tabs
// and tear down sockets, so there is no point retrying while hidden.
function waitUntilVisible(): Promise<void> {
  if (typeof document === "undefined" || document.visibilityState === "visible") {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const handler = () => {
      if (document.visibilityState === "visible") {
        document.removeEventListener("visibilitychange", handler);
        resolve();
      }
    };
    document.addEventListener("visibilitychange", handler);
  });
}

/**
 * Self-healing SSE stream. The backend (RESUMABLE_STREAM_ENABLED) runs the query as a
 * detached job and persists every event to a Redis stream, handing us a `job_id` up
 * front. If the connection drops — the classic "I switched tabs / my screen turned off
 * on mobile and the search failed" case — we transparently reconnect using the job_id
 * and the last event id we saw, replaying only what we missed, until a terminal event.
 *
 * When the backend flag is off, no `job_id` is sent: behaviour degrades gracefully to a
 * single non-resumable pass (identical to the legacy client).
 */
export async function* submitQueryStream(
  query: string,
  modelId: string,
  apiKey: string,
): AsyncGenerator<StreamEvent> {
  let jobId: string | null = null;
  let lastEventId = "";
  let attempt = 0;
  const baseBody = { query, model_id: modelId, model_explicit: false };

  // When the tab returns to the foreground after being hidden, abort the (likely dead)
  // in-flight read so we reconnect immediately instead of blocking on a stale socket.
  let abort = new AbortController();
  let wasHidden = false;
  const onVisibility = () => {
    if (typeof document === "undefined") return;
    if (document.visibilityState === "hidden") {
      wasHidden = true;
    } else if (document.visibilityState === "visible" && wasHidden) {
      wasHidden = false;
      try { abort.abort(); } catch { /* no-op */ }
    }
  };
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", onVisibility);
  }

  try {
    while (true) {
      const resuming = jobId !== null;
      const body = resuming
        ? { ...baseBody, job_id: jobId, last_event_id: lastEventId }
        : baseBody;
      abort = new AbortController();

      try {
        const res = await fetch("/api/query/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
          body: JSON.stringify(body),
          signal: abort.signal,
        });

        if (!res.ok || !res.body) {
          if (!resuming) {
            const err = await res.json().catch(() => ({ detail: "Request failed" }));
            throw new Error(err.detail || `HTTP ${res.status}`);
          }
          throw new Error(`__resume_retry__ HTTP ${res.status}`); // transient during resume
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break; // stream ended without terminal → fall through to reconnect
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";
          for (const part of parts) {
            const idMatch = part.match(/^id: (.+)/m);
            const eventMatch = part.match(/^event: (.+)/m);
            const dataMatch = part.match(/^data: (.+)/m);
            if (idMatch) lastEventId = idMatch[1].trim();
            if (!eventMatch || !dataMatch) continue;
            const type = eventMatch[1].trim();
            const payload = JSON.parse(dataMatch[1].trim());
            if (type === "job") {
              jobId = payload.job_id; // internal handshake — not surfaced to the UI
              attempt = 0;
              continue;
            }
            yield { type, payload } as StreamEvent;
            if (type === "done" || type === "error") return; // terminal — never auto-reconnect
          }
        }
      } catch (e) {
        const name = (e as { name?: string })?.name;
        const msg = (e as Error)?.message ?? "";
        const isAbort = name === "AbortError";
        const isResumeRetry = msg.startsWith("__resume_retry__");
        // A hard failure on the very first connect is surfaced (legacy behaviour). Aborts
        // (visibility kick) and transient resume failures fall through to reconnect.
        if (!resuming && !isAbort && !isResumeRetry) throw e;
      }

      // Reached only when the stream dropped before a terminal event.
      if (!jobId) return; // resumable disabled / no job handed out → cannot resume
      attempt += 1;
      if (attempt > RESUME_MAX_ATTEMPTS) {
        throw new Error("Lost connection to the answer. Please search again.");
      }
      yield { type: "reconnecting", payload: { attempt } };
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        await waitUntilVisible(); // don't burn attempts in the background
      } else {
        await sleep(Math.min(3000, 250 * 2 ** (attempt - 1)));
      }
    }
  } finally {
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", onVisibility);
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
  const res = await fetch("/api/v1/models", {
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return Array.isArray(data?.models) ? data.models : [];
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
    body: JSON.stringify({ service: serviceName, api_key: serviceKey }),
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
