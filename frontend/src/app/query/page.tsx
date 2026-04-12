"use client";

import { Suspense } from "react";
import { SearchBar } from "@/components/ui/SearchBar";
import { ThinkingAnimation } from "@/components/ui/ThinkingAnimation";
import { DisclaimerBanner } from "@/components/results/DisclaimerBanner";
import { TextNodeRenderer } from "@/components/results/TextNodeRenderer";
import { DrugInfoResult } from "@/components/results/DrugInfoResult";
import { DiseaseInfoResult } from "@/components/results/DiseaseInfoResult";
import { ComparativeResult } from "@/components/results/ComparativeResult";
import { GeneralResult } from "@/components/results/GeneralResult";
import { ProcedureResult } from "@/components/results/ProcedureResult";
import { EvidenceResult } from "@/components/results/EvidenceResult";
import { AdaptiveResultRenderer } from "@/components/results/AdaptiveResultRenderer";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useQueryContext } from "@/components/providers/QueryProvider";
import { formatLatency } from "@/lib/formatters";
import type {
  DrugResponse,
  DiseaseResponse,
  ComparativeResponse,
  GeneralResponse,
  ProcedureResponse,
  EvidenceResponse,
  DegradedResponse,
  AdaptiveResponse,
} from "@/lib/types";

function QueryContent() {
  const { result, isLoading, loadingStage, error, activeModelName, submitQuery } = useQueryContext();

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <SearchBar onSubmit={submitQuery} isLoading={isLoading} />
        <div className="flex justify-end">
          <span className="rounded-full bg-surface-alt px-2.5 py-1 text-xs text-text-muted">
            {activeModelName}
          </span>
        </div>
      </div>

      {error && (
        <Card>
          <p className="text-danger text-sm">{error}</p>
        </Card>
      )}

      {isLoading && <ThinkingAnimation stage={loadingStage} />}

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

          {/* Typed results */}
          {result.query_type === "drug" &&
            "drug_name" in result.response && (
              <DrugInfoResult data={result.response as DrugResponse} />
            )}

          {result.query_type === "disease" &&
            "disease_name" in result.response && (
              <DiseaseInfoResult data={result.response as DiseaseResponse} />
            )}

          {result.query_type === "comparative" &&
            "entities_compared" in result.response && (
              <ComparativeResult
                data={result.response as ComparativeResponse}
              />
            )}

          {result.query_type === "general" &&
            "summary" in result.response &&
            "key_points" in result.response && (
              <GeneralResult data={result.response as GeneralResponse} />
            )}

          {result.query_type === "procedure" &&
            "procedure_name" in result.response && (
              <ProcedureResult data={result.response as ProcedureResponse} />
            )}

          {result.query_type === "evidence" &&
            "query_topic" in result.response && (
              <EvidenceResult data={result.response as EvidenceResponse} />
            )}

          {result.query_type === "adaptive" &&
            "sections" in result.response && (
              <AdaptiveResultRenderer data={result.response as AdaptiveResponse} />
            )}

          {/* Text nodes — only show when no typed result rendered (fallback) */}
          {result.text_nodes.length > 0 &&
            !("drug_name" in result.response) &&
            !("disease_name" in result.response) &&
            !("entities_compared" in result.response) &&
            !("procedure_name" in result.response) &&
            !("query_topic" in result.response) &&
            !("key_points" in result.response) && (
              <Card>
                <TextNodeRenderer nodes={result.text_nodes} />
              </Card>
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
    <Suspense fallback={<ThinkingAnimation />}>
      <QueryContent />
    </Suspense>
  );
}
