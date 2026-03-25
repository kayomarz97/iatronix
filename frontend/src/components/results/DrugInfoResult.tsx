"use client";

import type { DrugResponse } from "@/lib/types";
import { Accordion } from "@/components/ui/Accordion";
import { Badge } from "@/components/ui/Badge";
import { ClaimItem } from "./ClaimItem";
import { EvidencedText } from "./EvidenceBadge";
import { TruncatedList } from "./TruncatedList";

interface DrugInfoResultProps {
  data: DrugResponse;
}

export function DrugInfoResult({ data }: DrugInfoResultProps) {
  return (
    <div className="space-y-5">
      <div className="border-b border-border pb-4">
        <h2 className="text-2xl font-bold">{data.drug_name}</h2>
        {data.drug_class && (
          <p className="text-text-secondary mt-1">{data.drug_class}</p>
        )}
      </div>

      {data.bluf && (
        <div style={{ background: "var(--surface-2)", borderLeft: "3px solid var(--accent)", padding: "0.75rem 1rem", borderRadius: "0 4px 4px 0" }}>
          <p className="text-sm font-medium leading-relaxed">{data.bluf}</p>
        </div>
      )}

      {data.additional_clinical_context && (
        <div style={{ background: "var(--surface-2)", padding: "0.75rem 1rem", borderRadius: "4px" }}>
          <p className="text-xs text-text-secondary leading-relaxed">{data.additional_clinical_context}</p>
        </div>
      )}

      {data.mechanism_of_action && (
        <Section title="Mechanism of Action">
          <p className="text-sm leading-relaxed">
            <EvidencedText claim={data.mechanism_of_action} />
          </p>
        </Section>
      )}

      {data.indications.length > 0 && (
        <Section title="Indications">
          <ul className="list-disc list-inside space-y-1">
            <TruncatedList
              items={data.indications}
              renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
            />
          </ul>
        </Section>
      )}

      {data.dosing.length > 0 && (
        <Section title="Dosing">
          <TruncatedList
            items={data.dosing}
            renderItem={(dose, i) => (
              <div key={i} className="py-2 border-b border-border/50 last:border-0">
                <p className="text-sm leading-relaxed">
                  <EvidencedText claim={dose} />
                </p>
                {(dose.route || dose.frequency) && (
                  <div className="flex gap-3 mt-1">
                    {dose.route && (
                      <span className="text-xs text-text-muted">
                        Route: <span className="text-text-secondary">{dose.route}</span>
                      </span>
                    )}
                    {dose.frequency && (
                      <span className="text-xs text-text-muted">
                        Frequency: <span className="text-text-secondary">{dose.frequency}</span>
                      </span>
                    )}
                  </div>
                )}
              </div>
            )}
          />
        </Section>
      )}

      {data.contraindications.length > 0 && (
        <Section title="Contraindications">
          <ul className="list-disc list-inside space-y-1">
            <TruncatedList
              items={data.contraindications}
              renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
            />
          </ul>
        </Section>
      )}

      {data.side_effects.length > 0 && (
        <Section title="Adverse Effects">
          <ul className="list-disc list-inside space-y-1">
            <TruncatedList
              items={data.side_effects}
              renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
            />
          </ul>
        </Section>
      )}

      {data.interactions.length > 0 && (
        <Section title="Drug Interactions">
          <TruncatedList
            items={data.interactions}
            renderItem={(ix, i) => (
              <div key={i} className="py-2 border-b border-border/50 last:border-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-sm">{ix.drug}</span>
                  <Badge
                    variant={
                      ix.severity === "major"
                        ? "danger"
                        : ix.severity === "moderate"
                          ? "warning"
                          : "default"
                    }
                  >
                    {ix.severity}
                  </Badge>
                </div>
                <p className="text-sm text-text-secondary">{ix.description}</p>
              </div>
            )}
          />
        </Section>
      )}

      {data.pharmacokinetics && (
        <Section title="Pharmacokinetics">
          <p className="text-sm leading-relaxed">
            <EvidencedText claim={data.pharmacokinetics} />
          </p>
        </Section>
      )}

      {data.special_populations.length > 0 && (
        <Section title="Special Populations">
          <ul className="list-disc list-inside space-y-1">
            <TruncatedList
              items={data.special_populations}
              renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
            />
          </ul>
        </Section>
      )}

      {data.monitoring.length > 0 && (
        <Section title="Monitoring Parameters">
          <ul className="list-disc list-inside space-y-1">
            <TruncatedList
              items={data.monitoring}
              renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
            />
          </ul>
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
