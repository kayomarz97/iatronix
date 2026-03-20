"use client";

import type { ComparativeResponse } from "@/lib/types";
import { Accordion } from "@/components/ui/Accordion";
import { EvidenceBadge } from "./EvidenceBadge";
import { TruncatedList } from "./TruncatedList";

interface ComparativeResultProps {
  data: ComparativeResponse;
}

export function ComparativeResult({ data }: ComparativeResultProps) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold">
          {data.entities_compared.join(" vs ")}
        </h2>
        {data.comparison_type && (
          <p className="text-text-secondary text-sm mt-1">
            {data.comparison_type}
          </p>
        )}
      </div>

      {data.summary && (
        <Accordion title="Summary" defaultOpen>
          <p className="text-sm">{data.summary.value}</p>
          <EvidenceBadge claim={data.summary} />
        </Accordion>
      )}

      {data.detailed_comparison.length > 0 && (
        <Accordion
          title="Detailed Comparison"
          count={data.detailed_comparison.length}
          defaultOpen
        >
          <TruncatedList
            items={data.detailed_comparison}
            renderItem={(dim, i) => (
              <div
                key={i}
                className="py-3 border-b border-border last:border-0"
              >
                <h4 className="font-medium text-sm mb-2">{dim.dimension}</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Object.entries(dim.values).map(([entity, claim]) => (
                    <div
                      key={entity}
                      className="p-3 rounded bg-surface-alt border border-border"
                    >
                      <p className="font-medium text-xs text-text-secondary mb-1">
                        {entity}
                      </p>
                      <p className="text-sm">{claim.value}</p>
                      <EvidenceBadge claim={claim} compact />
                    </div>
                  ))}
                </div>
              </div>
            )}
          />
        </Accordion>
      )}

      {data.clinical_preference && (
        <Accordion title="Clinical Preference">
          <p className="text-sm">{data.clinical_preference.value}</p>
          <EvidenceBadge claim={data.clinical_preference} />
        </Accordion>
      )}

      {data.references.length > 0 && (
        <Accordion title="References" count={data.references.length}>
          <ul className="text-xs text-text-muted space-y-1">
            {data.references.map((ref, i) => (
              <li key={i}>
                {ref.source}
                {ref.title ? `: ${ref.title}` : ""}
                {ref.year ? ` (${ref.year})` : ""}
              </li>
            ))}
          </ul>
        </Accordion>
      )}
    </div>
  );
}
