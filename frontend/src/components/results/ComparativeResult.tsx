"use client";

import type { ComparativeResponse } from "@/lib/types";
import { Accordion } from "@/components/ui/Accordion";
import { EvidencedText, EvidenceBadge } from "./EvidenceBadge";
import { TruncatedList } from "./TruncatedList";

interface ComparativeResultProps {
  data: ComparativeResponse;
}

export function ComparativeResult({ data }: ComparativeResultProps) {
  return (
    <div className="space-y-5">
      <div className="border-b border-border pb-4">
        <h2 className="text-2xl font-bold">
          {data.entities_compared.join(" vs ")}
        </h2>
        {data.comparison_type && (
          <p className="text-text-secondary mt-1">{data.comparison_type}</p>
        )}
      </div>

      {data.summary && (
        <Section title="Summary">
          <p className="text-sm leading-relaxed">
            <EvidencedText claim={data.summary} />
          </p>
        </Section>
      )}

      {data.detailed_comparison.length > 0 && (
        <Section title="Detailed Comparison">
          <TruncatedList
            items={data.detailed_comparison}
            renderItem={(dim, i) => (
              <div key={i} className="py-3 border-b border-border/50 last:border-0">
                <h4 className="font-semibold text-sm mb-2">{dim.dimension}</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Object.entries(dim.values).map(([entity, claim]) => (
                    <div
                      key={entity}
                      className="p-3 rounded-lg bg-surface-alt border border-border"
                    >
                      <p className="font-medium text-xs text-primary mb-1">
                        {entity}
                      </p>
                      <p className="text-sm leading-relaxed">
                        <EvidencedText claim={claim} />
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          />
        </Section>
      )}

      {data.clinical_preference && (
        <Section title="Clinical Preference">
          <p className="text-sm leading-relaxed">
            <EvidencedText claim={data.clinical_preference} />
          </p>
        </Section>
      )}

      {data.references.length > 0 && (
        <Accordion title="References" count={data.references.length}>
          <ul className="text-xs text-text-muted space-y-1">
            {data.references.map((ref, i) => (
              <li key={i}>
                {ref.source}
                {ref.title ? ` — ${ref.title}` : ""}
                {ref.year ? ` (${ref.year})` : ""}
              </li>
            ))}
          </ul>
        </Accordion>
      )}
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-base font-semibold mb-2 text-text">{title}</h3>
      {children}
    </div>
  );
}
