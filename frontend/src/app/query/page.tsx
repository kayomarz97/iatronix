"use client";

import React, { Suspense, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { SearchBar } from "@/components/ui/SearchBar";
import { LoadingScreen } from "@/components/LoadingScreen";
import { SearchHistorySidebar } from "@/components/ui/SearchHistorySidebar";
import { DisclaimerBanner } from "@/components/results/DisclaimerBanner";
import { AdaptiveResultRenderer } from "@/components/results/AdaptiveResultRenderer";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useQueryContext } from "@/components/providers/QueryProvider";
import { useAuth } from "@/components/providers/AuthProvider";
import { formatLatency } from "@/lib/formatters";
import type { DegradedResponse, AdaptiveResponse, AdaptiveBLUF, AdaptiveSection, TokenUsage } from "@/lib/types";
import { getLLMConfig, displayFor, type LLMConfig } from "@/lib/modelRegistry";

function StreamingProgress({ streamingText, loadingStage }: { streamingText: string; loadingStage: string }) {
  const sectionTitles = React.useMemo(() => {
    const matches = [...streamingText.matchAll(/"title"\s*:\s*"([^"]{3,60})"/g)];
    return [...new Set(matches.map(m => m[1]))].slice(0, 12);
  }, [streamingText]);

  return (
    <Card>
      <p className="text-xs text-text-muted mb-3 font-medium tracking-wide uppercase">
        {loadingStage === "generating" ? "Generating response…" : "Analysing query…"}
      </p>
      {sectionTitles.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {sectionTitles.map((title, i) => (
            <span key={i} className="rounded-full bg-surface-alt border border-border px-3 py-1 text-xs text-text-secondary animate-pulse">
              {title}
            </span>
          ))}
        </div>
      ) : (
        <div className="flex items-center gap-2 text-sm text-text-muted">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent animate-bounce" />
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent animate-bounce [animation-delay:0.15s]" />
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent animate-bounce [animation-delay:0.3s]" />
        </div>
      )}
    </Card>
  );
}

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function SidebarNav({ data }: { data: AdaptiveResponse }) {
  const sections = data.sections.filter(s => (s.content_items?.length ?? 0) > 0 || s.content);
  const flowcharts = data.flowcharts ?? [];
  const tables = data.tables ?? [];
  const refCount = data.references?.length ?? 0;

  return (
    <div className="hidden md:flex w-[210px] shrink-0 sticky top-[66px] flex-col gap-0.5 max-h-[calc(100vh-80px)] overflow-y-auto pr-1">
      <p className="text-[0.65rem] font-bold tracking-[0.12em] uppercase text-[var(--text-muted)] mb-1.5 pl-2">
        Sections
      </p>
      {sections.map((sec, i) => (
        <button key={i} onClick={() => scrollTo(`sec-${i}`)}
          className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-left hover:bg-[var(--bg-elevated)] transition-colors group">
          <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: "var(--accent)" }} />
          <span className="text-[0.78rem] text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] leading-snug line-clamp-2">
            {sec.title}
          </span>
        </button>
      ))}
      {flowcharts.map((fc, i) => (
        <button key={`fc-${i}`} onClick={() => scrollTo(`fc-${i}`)}
          className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-left hover:bg-[var(--bg-elevated)] transition-colors group">
          <span className="w-1.5 h-1.5 rounded-sm shrink-0" style={{ background: "#818CF8" }} />
          <span className="text-[0.78rem] text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] leading-snug line-clamp-2">
            {fc.title || "Pathway"}
          </span>
        </button>
      ))}
      {tables.map((tbl, i) => (
        <button key={`tbl-${i}`} onClick={() => scrollTo(`tbl-${i}`)}
          className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-left hover:bg-[var(--bg-elevated)] transition-colors group">
          <span className="w-1.5 h-1.5 rounded-sm shrink-0" style={{ background: "#22D3EE" }} />
          <span className="text-[0.78rem] text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] leading-snug line-clamp-2">
            {tbl.title || "Table"}
          </span>
        </button>
      ))}
      {refCount > 0 && (
        <button onClick={() => scrollTo("references")}
          className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-left hover:bg-[var(--bg-elevated)] transition-colors group mt-1">
          <span className="w-1.5 h-1.5 rounded-full shrink-0 bg-[var(--text-muted)]" />
          <span className="text-[0.78rem] text-[var(--text-muted)] group-hover:text-[var(--text-secondary)]">
            References ({refCount})
          </span>
        </button>
      )}
    </div>
  );
}

function ErrorBanner({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm">
      <svg className="mt-0.5 h-4 w-4 shrink-0 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
      </svg>
      <span className="flex-1 text-red-300">{message}</span>
      <button
        onClick={onDismiss}
        className="shrink-0 text-red-400 hover:text-red-200 transition-colors leading-none"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  );
}

function PartialResultsNotice({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm">
      <svg className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
      </svg>
      <span className="flex-1 text-amber-300">
        Response may be incomplete — connection ended early. The results shown are valid.
      </span>
      <button
        onClick={onDismiss}
        className="shrink-0 text-amber-400 hover:text-amber-200 transition-colors leading-none"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  );
}

function ReconnectingBanner() {
  return (
    <span className="reconnect-pill" role="status" aria-live="polite">
      <svg className="spin" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round">
        <path d="M21 12a9 9 0 1 1-6.219-8.56" />
      </svg>
      Connection dropped — resuming your answer…
    </span>
  );
}

// Build a clean, shareable plain-text version of an answer for the Copy button.
function buildAnswerText(query: string, data: AdaptiveResponse): string {
  const lines: string[] = [];
  if (query) lines.push(query, "");
  if (data.bluf?.headline) lines.push(data.bluf.headline);
  if (data.bluf?.body) lines.push(data.bluf.body);
  if (data.bluf?.key_points?.length) {
    lines.push("");
    data.bluf.key_points.forEach((k) => lines.push(`• ${k}`));
  }
  (data.sections || []).forEach((s) => {
    lines.push("", (s.title || "").toUpperCase());
    (s.content_items || []).forEach((it) => { if (it.text) lines.push(`• ${it.text}`); });
    if (typeof s.content === "string" && s.content) lines.push(s.content);
  });
  if (data.references?.length) {
    lines.push("", "REFERENCES");
    data.references.forEach((r, i) => {
      const ref = r as { title?: string; url?: string };
      lines.push(`${i + 1}. ${ref.title ?? ""}${ref.url ? " — " + ref.url : ""}`);
    });
  }
  lines.push("", "— Generated by Iatronix (educational use only; verify with primary sources).");
  return lines.join("\n");
}

function CopyShareBar({ text, shareUrl }: { text: string; shareUrl: string }) {
  const [done, setDone] = React.useState<null | "copy" | "share">(null);
  const flash = (which: "copy" | "share") => { setDone(which); setTimeout(() => setDone(null), 1600); };
  const doCopy = async () => { try { await navigator.clipboard.writeText(text); flash("copy"); } catch { /* clipboard blocked */ } };
  const doShare = async () => {
    try {
      if (typeof navigator !== "undefined" && navigator.share) { await navigator.share({ title: "Iatronix answer", url: shareUrl }); return; }
      await navigator.clipboard.writeText(shareUrl); flash("share");
    } catch { /* user cancelled / blocked */ }
  };
  const btn = "inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--border-focus)] transition-colors";
  return (
    <div className="flex items-center gap-2 shrink-0">
      <button onClick={doCopy} className={btn} aria-label="Copy answer">
        {done === "copy" ? "Copied ✓" : "Copy"}
      </button>
      <button onClick={doShare} className={btn} aria-label="Share answer">
        {done === "share" ? "Link copied ✓" : "Share"}
      </button>
    </div>
  );
}

function QueryContent() {
  const { result, streamingText, streamingBluf, streamingSections, streamingSectionTitles, streamingFlowcharts, streamingTables, fetchedArticles, isLoading, loadingStage, error, activeModelName, isFallback, fallbackModel, submitQuery, clearResult } = useQueryContext();
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const lastAutoSubmit = useRef<string | null>(null);
  const [dismissedError, setDismissedError] = React.useState<string | null>(null);
  const [llmConfig, setLlmConfig] = React.useState<LLMConfig | null>(null);

  useEffect(() => {
    getLLMConfig().then(setLlmConfig);
  }, []);

  const visibleError = error && error !== dismissedError ? error : null;

  const handleDismissError = useCallback(() => {
    setDismissedError(error);
  }, [error]);

  // Reset dismissed state when a new query starts
  useEffect(() => {
    if (isLoading) setDismissedError(null);
  }, [isLoading]);

  useEffect(() => {
    const q = searchParams.get("q");
    if (q && q !== lastAutoSubmit.current) {
      lastAutoSubmit.current = q;
      submitQuery(q);
    }
  }, [searchParams, submitQuery]);

  return (
    <div className="space-y-6 pl-6">
      <SearchHistorySidebar onRerun={submitQuery} isLoggedIn={!!user} />
      <div className="space-y-3">
        <SearchBar onSubmit={submitQuery} isLoading={isLoading} />
      </div>

      {/* Only show the full error banner when there's no partial BLUF to show */}
      {visibleError && !streamingBluf && (
        <ErrorBanner message={visibleError} onDismiss={handleDismissError} />
      )}

      {isLoading && !streamingText && !streamingBluf && (
        <div className="space-y-3">
          {loadingStage === "reconnecting" && <ReconnectingBanner />}
          <LoadingScreen
            currentStep={
              (["classifying", "fetching", "generating", "verifying"].includes(loadingStage)
                ? loadingStage
                : "fetching") as "classifying" | "fetching" | "generating" | "verifying"
            }
            fetchedArticles={fetchedArticles}
          />
        </div>
      )}

      {/* Single-call path: show cleaned-up progress instead of raw JSON */}
      {streamingText && isLoading && !streamingBluf && (
        <StreamingProgress streamingText={streamingText} loadingStage={loadingStage} />
      )}

      {/* Parallel path: progressively render BLUF + sections as they arrive (or preserved on error) */}
      {streamingBluf && (isLoading || error) && !result && (
        <div className="space-y-5">
          {isLoading && loadingStage === "reconnecting" && <ReconnectingBanner />}
          <AdaptiveResultRenderer
            hideEvidenceBar
            data={{
              query_type: "adaptive",
              bluf: streamingBluf,
              sections: streamingSections.filter(s => (s.content_items?.length ?? 0) > 0 || s.content),
              references: [],
              response_focus: "",
              depth: "comprehensive",
              related_topics: [],
              tables: streamingTables,
              flowcharts: streamingFlowcharts,
              images: [],
            }}
          />

          {/* Skeleton cards for sections not yet arrived */}
          {isLoading && streamingSectionTitles.length > 0 && (() => {
            const arrivedTitles = new Set(streamingSections.map(s => s.title));
            const pending = streamingSectionTitles.filter(t => !arrivedTitles.has(t));
            return pending.map((title, i) => (
              <div
                key={`pending-${i}`}
                className="rounded-2xl border border-border/40 bg-[var(--bg-surface)] px-5 py-4 space-y-3 animate-pulse"
              >
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent/50" />
                  <span className="text-sm font-semibold text-text-secondary">{title}</span>
                </div>
                <div className="space-y-2">
                  <div className="h-2.5 rounded-full bg-[var(--bg-elevated)] w-full" />
                  <div className="h-2.5 rounded-full bg-[var(--bg-elevated)] w-5/6" />
                  <div className="h-2.5 rounded-full bg-[var(--bg-elevated)] w-4/6" />
                </div>
              </div>
            ));
          })()}

          {isLoading && streamingSectionTitles.length > 0 && (
            <div className="flex items-center gap-2 px-1 text-xs text-text-muted">
              <span className="inline-flex gap-1">
                {[0, 150, 300].map(delay => (
                  <span key={delay}
                    className="w-1 h-1 rounded-full bg-accent animate-bounce"
                    style={{ animationDelay: `${delay}ms` }} />
                ))}
              </span>
              <span>
                {streamingSections.length} of {streamingSectionTitles.length} sections complete
              </span>
            </div>
          )}

          {isLoading && streamingSectionTitles.length === 0 && (
            <Card>
              <div className="flex items-center gap-3 text-sm text-text-muted">
                <span className="inline-flex gap-1">
                  {[0, 150, 300].map(delay => (
                    <span key={delay}
                      className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce"
                      style={{ animationDelay: `${delay}ms` }} />
                  ))}
                </span>
                <span>Generating detailed sections…</span>
              </div>
            </Card>
          )}

          {/* Error note shown beneath partial results — only when BLUF already rendered */}
          {visibleError && !isLoading && (
            streamingSections.length > 0
              ? <PartialResultsNotice onDismiss={handleDismissError} />
              : <ErrorBanner message={visibleError} onDismiss={handleDismissError} />
          )}
        </div>
      )}

      {result && !isLoading && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[24px] border border-border/70 bg-background/70 px-4 py-3 shadow-[0_12px_30px_rgba(2,8,23,0.08)]">
            <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
              <Badge>{result.query_type}</Badge>
              <span className="rounded-full bg-surface-alt px-2.5 py-1">
                {result.model_used}
              </span>
              <span className="rounded-full bg-surface-alt px-2.5 py-1">
                {formatLatency(result.latency_ms)}
              </span>
              {result.cached && <Badge variant="success">cached</Badge>}
              {result.truncated && <Badge variant="warning">truncated</Badge>}
              {result.rewritten_query && (
                <span className="rounded-full bg-surface-alt px-2.5 py-1 text-text-muted italic">
                  Searched as: {result.rewritten_query}
                </span>
              )}
            </div>
            {"sections" in result.response && (
              <CopyShareBar
                text={buildAnswerText(searchParams.get("q") || result.rewritten_query || "", result.response as AdaptiveResponse)}
                shareUrl={typeof window !== "undefined" ? window.location.href : ""}
              />
            )}
          </div>

          {/* No-evidence info card — neutral style, no "Expert opinion" rendered */}
          {"message" in result.response && "suggestion" in result.response &&
           (result.response as DegradedResponse).error_code === "no_evidence" && (
            <Card>
              <div className="flex items-start gap-3">
                <span className="text-2xl mt-0.5" aria-hidden>🔍</span>
                <div>
                  <p className="font-medium text-text-primary">
                    {(result.response as DegradedResponse).message}
                  </p>
                  <p className="text-sm text-text-secondary mt-1">
                    {(result.response as DegradedResponse).suggestion}
                  </p>
                </div>
              </div>
            </Card>
          )}

          {/* Degraded response (service errors, circuit-breaker, etc.) */}
          {"message" in result.response && "suggestion" in result.response &&
           (result.response as DegradedResponse).error_code !== "no_evidence" && (
            <Card variant="degraded">
              <p className="font-medium">
                {(result.response as DegradedResponse).message}
              </p>
              <p className="text-sm text-text-secondary mt-1">
                {(result.response as DegradedResponse).suggestion}
              </p>
            </Card>
          )}

          {/* Adaptive result — two-column layout with sticky sidebar on desktop */}
          {"sections" in result.response && (
            <div className="flex gap-5 items-start">
              <SidebarNav data={result.response as AdaptiveResponse} />
              <div className="flex-1 min-w-0">
                <AdaptiveResultRenderer data={result.response as AdaptiveResponse} fetchSources={result.fetch_sources} isFallback={isFallback} fallbackModel={fallbackModel} />
              </div>
            </div>
          )}

          {/* Token usage breakdown */}
          {result.token_usage && (
            <div className="mt-3 rounded-lg border bg-surface-alt p-3 text-xs space-y-1">
              <div className="flex items-center gap-2 font-medium text-text-secondary mb-1">
                <span>Token Usage — {result.model_used}</span>
                {result.token_usage.total_cost_usd === 0 && (
                  <span className="rounded-full bg-green-500/15 border border-green-500/30 px-2 py-0.5 text-green-400 text-[10px]">
                    Free tier
                  </span>
                )}
              </div>
              {result.token_usage.models.map((m) => {
                const info = llmConfig?.providers && Object.values(llmConfig.providers).find(p => p.model_id === m.model_id);
                const name = llmConfig ? displayFor(m.model_id, llmConfig) : m.model_id;
                const tooltip = info ? `$${info.input} in / $${info.output} out per 1M tokens` : undefined;
                return (
                  <div key={m.model_id} className="flex justify-between">
                    <span className="text-text-muted truncate max-w-[200px]" title={tooltip}>{name}</span>
                    <span className="font-mono">
                      {m.input_tokens.toLocaleString()}↑&nbsp;{m.output_tokens.toLocaleString()}↓
                      {m.subtotal_usd > 0 && <>&nbsp;·&nbsp;${m.subtotal_usd.toFixed(5)}</>}
                    </span>
                  </div>
                );
              })}
              <div className="border-t border-border/50 pt-1 flex justify-between font-medium">
                <span>Total</span>
                <span className="font-mono">
                  {result.token_usage.total_input_tokens.toLocaleString()}↑&nbsp;
                  {result.token_usage.total_output_tokens.toLocaleString()}↓
                  {result.token_usage.total_cost_usd > 0 && (
                    <>&nbsp;·&nbsp;${result.token_usage.total_cost_usd.toFixed(5)}</>
                  )}
                </span>
              </div>
              {result.token_usage.note && (
                <p className="text-text-muted italic mt-1">{result.token_usage.note}</p>
              )}
            </div>
          )}

          <DisclaimerBanner
            disclaimer={result.disclaimer}
            safetyWarnings={result.safety_warnings}
            validationWarnings={result.validation_warnings}
          />
        </div>
      )}
    </div>
  );
}

export default function QueryPage() {
  return (
    <Suspense fallback={<LoadingScreen currentStep="classifying" />}>
      <QueryContent />
    </Suspense>
  );
}
