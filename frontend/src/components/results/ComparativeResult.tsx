"use client";

import type { ComparativeResponse } from "@/lib/types";
import { EvidencedText } from "./EvidenceBadge";
import { ReferenceList } from "./ReferenceList";
import { ResultHero, ResultMetaCard, ResultSection } from "./ResultChrome";

interface ComparativeResultProps {
  data: ComparativeResponse;
}

export function ComparativeResult({ data }: ComparativeResultProps) {
  const directAnswer =
    data.clinical_preference?.value ?? data.summary?.value ?? undefined;
  const context =
    data.clinical_preference?.value && data.summary?.value
      ? data.summary.value
      : undefined;

  return (
    <div className="space-y-6">
      <ResultHero
        eyebrow="Comparative Review"
        title={data.entities_compared.join(" vs ")}
        subtitle={data.comparison_type ?? undefined}
        stats={[
          { label: "entities", value: data.entities_compared.length },
          { label: "comparison rows", value: data.detailed_comparison?.length ?? 0 },
          { label: "references", value: data.references?.length ?? 0 },
        ]}
        directAnswer={directAnswer}
        context={context}
      />

      {data.detailed_comparison?.length > 0 && (
        <ResultSection title="Detailed Comparison" eyebrow="Side-by-side view">
          <div className="overflow-x-auto">
            <table className="min-w-full border-separate border-spacing-y-2">
              <thead>
                <tr>
                  <th className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                    Dimension
                  </th>
                  {data.entities_compared.map((entity) => (
                    <th
                      key={entity}
                      className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted"
                    >
                      {entity}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.detailed_comparison.map((dimension, index) => (
                  <tr key={`${dimension.dimension}-${index}`}>
                    <td className="align-top">
                      <ResultMetaCard className="min-w-[180px]">
                        <p className="text-sm font-semibold text-text">
                          {dimension.dimension}
                        </p>
                      </ResultMetaCard>
                    </td>
                    {data.entities_compared.map((entity) => {
                      const claim = dimension.values[entity];
                      return (
                        <td key={`${dimension.dimension}-${entity}`} className="align-top">
                          <ResultMetaCard className="min-w-[260px] h-full">
                            {claim ? (
                              <p className="text-sm leading-7">
                                <EvidencedText claim={claim} />
                              </p>
                            ) : (
                              <p className="text-sm text-text-muted">
                                No direct evidence retrieved.
                              </p>
                            )}
                          </ResultMetaCard>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ResultSection>
      )}

      {data.summary && data.clinical_preference && (
        <ResultSection title="Clinical Framing" eyebrow="Interpretation">
          <p className="text-sm leading-7">
            <EvidencedText claim={data.summary} />
          </p>
        </ResultSection>
      )}

      {data.references?.length > 0 && <ReferenceList references={data.references} />}
    </div>
  );
}
