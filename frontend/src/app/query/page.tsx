"use client";

import { Suspense } from "react";
import { SearchBar } from "@/components/ui/SearchBar";
import { LoadingScreen } from "@/components/LoadingScreen";
import { DisclaimerBanner } from "@/components/results/DisclaimerBanner";
import { AdaptiveResultRenderer } from "@/components/results/AdaptiveResultRenderer";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useQueryContext } from "@/components/providers/QueryProvider";
import { formatLatency } from "@/lib/formatters";
import type { DegradedResponse, AdaptiveResponse, TokenUsage } from "@/lib/types";

function QueryContent() {
  const { result, isLoading, loadingStage, error, activeModelName, submitQuery } = useQueryContext();

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <SearchBar onSubmit={submitQuery} isLoading={isLoading} />
      </div>

      {error && (
        <Card>
          <p className="text-danger text-sm">{error}</p>
        </Card>
      )}

      {isLoading && (
        <LoadingScreen
          currentStep={
            (loadingStage as "classifying" | "fetching" | "generating" | "verifying") ||
            "classifying"
          }
        />
      )}

      {result && !isLoading && (
        <div className="space-y-6">
          <div className="rounded-[24px] border border-border/70 bg-background/70 px-4 py-3 shadow-[0_12px_30px_rgba(2,8,23,0.08)]">
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
          </div>

          {/* Degraded response */}
          {"message" in result.response && "suggestion" in result.response && (
            <Card variant="degraded">
              <p className="font-medium">
                {(result.response as DegradedResponse).message}
              </p>
              <p className="text-sm text-text-secondary mt-1">
                {(result.response as DegradedResponse).suggestion}
              </p>
            </Card>
          )}

          {/* Adaptive result — always rendered for non-degraded responses */}
          {"sections" in result.response && (
            <AdaptiveResultRenderer data={result.response as AdaptiveResponse} fetchSources={result.fetch_sources} />
          )}

          {/* Token usage breakdown */}
          {result.token_usage && (
            <div className="mt-3 rounded-lg border bg-surface-alt p-3 text-xs space-y-1">
              {result.token_usage.models.map((m) => (
                <div key={m.model_id} className="flex justify-between gap-4">
                  <span className="font-mono text-text-muted">{m.model_id}</span>
                  <span>{m.input_tokens.toLocaleString()} in · ${m.input_cost_usd.toFixed(5)}</span>
                  <span>{m.output_tokens.toLocaleString()} out · ${m.output_cost_usd.toFixed(5)}</span>
                  <span className="font-semibold">${m.subtotal_usd.toFixed(5)}</span>
                </div>
              ))}
              <div className="flex justify-between border-t pt-1 font-bold">
                <span>
                  Total — {result.token_usage.total_input_tokens.toLocaleString()} in /{" "}
                  {result.token_usage.total_output_tokens.toLocaleString()} out
                </span>
                <span>${result.token_usage.total_cost_usd.toFixed(5)}</span>
              </div>
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
