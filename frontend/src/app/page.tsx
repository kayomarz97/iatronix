"use client";

import { SearchBar } from "@/components/ui/SearchBar";
import { ModelSelector } from "@/components/ui/ModelSelector";
import { useQueryContext } from "@/components/providers/QueryProvider";
import { DisclaimerBanner } from "@/components/results/DisclaimerBanner";
import { TextNodeRenderer } from "@/components/results/TextNodeRenderer";
import { DrugInfoResult } from "@/components/results/DrugInfoResult";
import { DiseaseInfoResult } from "@/components/results/DiseaseInfoResult";
import { ComparativeResult } from "@/components/results/ComparativeResult";
import { GeneralResult } from "@/components/results/GeneralResult";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { QuerySkeleton } from "@/components/ui/Skeleton";
import { formatLatency } from "@/lib/formatters";
import type {
  DrugResponse,
  DiseaseResponse,
  ComparativeResponse,
  GeneralResponse,
  DegradedResponse,
} from "@/lib/types";

export default function HomePage() {
  const { submitQuery, isLoading, error, result, clearResult } =
    useQueryContext();

  return (
    <div className="space-y-8">
      {/* Hero - only show when no result */}
      {!result && !isLoading && (
        <div className="text-center space-y-3 pt-12">
          <h1 className="text-4xl font-bold text-primary">Iatronix</h1>
          <p className="text-text-secondary text-lg max-w-xl mx-auto">
            AI-powered medical reference with evidence grading. Query drugs,
            diseases, or compare treatments.
          </p>
        </div>
      )}

      {/* Search */}
      <div className="max-w-2xl mx-auto space-y-3">
        <SearchBar onSubmit={submitQuery} isLoading={isLoading} />
        <div className="flex justify-center">
          <ModelSelector />
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="max-w-2xl mx-auto p-3 rounded-lg bg-danger-bg border border-danger/30 text-sm text-danger">
          {error}
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="max-w-3xl mx-auto">
          <QuerySkeleton />
        </div>
      )}

      {/* Results */}
      {result && !isLoading && (
        <div className="max-w-3xl mx-auto space-y-6">
          {/* Meta */}
          <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
            <Badge>{result.query_type}</Badge>
            <span>{result.model_used}</span>
            <span>{formatLatency(result.latency_ms)}</span>
            {result.cached && <Badge variant="success">cached</Badge>}
            {result.truncated && <Badge variant="warning">truncated</Badge>}
            <button
              onClick={clearResult}
              className="ml-auto text-primary-light hover:text-primary text-xs"
            >
              Clear
            </button>
          </div>

          {/* Warnings - only if present */}
          {(result.safety_warnings.length > 0 ||
            result.validation_warnings.length > 0) && (
            <DisclaimerBanner
              disclaimer=""
              safetyWarnings={result.safety_warnings}
              validationWarnings={result.validation_warnings}
            />
          )}

          {/* Degraded */}
          {"message" in result.response && "suggestion" in result.response && !("drug_name" in result.response) && !("disease_name" in result.response) && !("entities_compared" in result.response) && !("key_points" in result.response) && (
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
          {result.query_type === "drug" && "drug_name" in result.response && (
            <DrugInfoResult data={result.response as DrugResponse} />
          )}
          {result.query_type === "disease" &&
            "disease_name" in result.response && (
              <DiseaseInfoResult
                data={result.response as DiseaseResponse}
              />
            )}
          {result.query_type === "comparative" &&
            "entities_compared" in result.response && (
              <ComparativeResult
                data={result.response as ComparativeResponse}
              />
            )}
          {result.query_type === "general" &&
            "key_points" in result.response && (
              <GeneralResult data={result.response as GeneralResponse} />
            )}

          {/* Disclaimer at bottom */}
          <div className="p-3 rounded-lg bg-surface-alt border border-border text-xs text-text-muted">
            {result.disclaimer}
          </div>
        </div>
      )}

      {/* Example cards - only when no result */}
      {!result && !isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl mx-auto text-sm">
          <ExampleCard
            title="Drug Query"
            example="metformin dosing and interactions"
            onClick={() => submitQuery("metformin dosing and interactions")}
          />
          <ExampleCard
            title="Disease Query"
            example="heart failure management guidelines"
            onClick={() =>
              submitQuery("heart failure management guidelines")
            }
          />
          <ExampleCard
            title="Comparison"
            example="lisinopril vs losartan for hypertension"
            onClick={() =>
              submitQuery("lisinopril vs losartan for hypertension")
            }
          />
        </div>
      )}
    </div>
  );
}

function ExampleCard({
  title,
  example,
  onClick,
}: {
  title: string;
  example: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="p-4 rounded-lg border border-border bg-surface-alt hover:bg-surface-hover transition-colors text-left cursor-pointer"
    >
      <div className="font-medium text-text mb-1">{title}</div>
      <div className="text-text-muted text-xs">{example}</div>
    </button>
  );
}
