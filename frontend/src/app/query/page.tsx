"use client";

import { Suspense } from "react";
import { SearchBar } from "@/components/ui/SearchBar";
import { ModelSelector } from "@/components/ui/ModelSelector";
import { ThinkingAnimation } from "@/components/ui/ThinkingAnimation";
import { DisclaimerBanner } from "@/components/results/DisclaimerBanner";
import { TextNodeRenderer } from "@/components/results/TextNodeRenderer";
import { DrugInfoResult } from "@/components/results/DrugInfoResult";
import { DiseaseInfoResult } from "@/components/results/DiseaseInfoResult";
import { ComparativeResult } from "@/components/results/ComparativeResult";
import { GeneralResult } from "@/components/results/GeneralResult";
import { ProcedureResult } from "@/components/results/ProcedureResult";
import { EvidenceResult } from "@/components/results/EvidenceResult";
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
} from "@/lib/types";

function QueryContent() {
  const { result, isLoading, error, submitQuery } = useQueryContext();

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <SearchBar onSubmit={submitQuery} isLoading={isLoading} />
        <div className="flex justify-end">
          <ModelSelector />
        </div>
      </div>

      {error && (
        <Card>
          <p className="text-danger text-sm">{error}</p>
        </Card>
      )}

      {isLoading && <ThinkingAnimation />}

      {result && !isLoading && (
        <div className="space-y-6">
          {/* Meta info */}
          <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
            <Badge>{result.query_type}</Badge>
            <span>{result.model_used}</span>
            <span>{formatLatency(result.latency_ms)}</span>
            {result.cached && <Badge variant="success">cached</Badge>}
            {result.truncated && <Badge variant="warning">truncated</Badge>}
          </div>

          {/* Warnings */}
          <DisclaimerBanner
            disclaimer={result.disclaimer}
            safetyWarnings={result.safety_warnings}
            validationWarnings={result.validation_warnings}
          />

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

          {/* Text nodes */}
          {result.text_nodes.length > 0 && (
            <Card>
              <h3 className="font-medium text-sm mb-2">Linked Content</h3>
              <TextNodeRenderer nodes={result.text_nodes} />
            </Card>
          )}
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
