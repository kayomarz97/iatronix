"use client";

import type { DrugResponse } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";
import { ClaimItem } from "./ClaimItem";
import { EvidencedText } from "./EvidenceBadge";
import { ReferenceList } from "./ReferenceList";
import { ResultHero, ResultMetaCard, ResultSection } from "./ResultChrome";
import { TruncatedList } from "./TruncatedList";

interface DrugInfoResultProps {
  data: DrugResponse;
}

export function DrugInfoResult({ data }: DrugInfoResultProps) {
  return (
    <div className="space-y-6">
      <ResultHero
        eyebrow="Drug Reference"
        title={data.drug_name}
        subtitle={data.drug_class}
        stats={[
          ...(data.indications?.length
            ? [{ label: "indications", value: data.indications.length }]
            : []),
          ...(data.dosing?.length
            ? [{ label: "regimens", value: data.dosing.length }]
            : []),
          ...(data.monitoring?.length
            ? [{ label: "monitoring items", value: data.monitoring.length }]
            : []),
        ]}
        directAnswer={data.bluf ?? undefined}
        context={data.additional_clinical_context ?? undefined}
      />

      {(data.mechanism_of_action || data.pharmacokinetics) && (
        <div className="grid gap-4 lg:grid-cols-2">
          {data.mechanism_of_action && (
            <ResultSection title="Mechanism of Action" eyebrow="How it works">
              <p className="text-sm leading-7">
                <EvidencedText claim={data.mechanism_of_action} />
              </p>
            </ResultSection>
          )}
          {data.pharmacokinetics && (
            <ResultSection title="Pharmacokinetics" eyebrow="Disposition">
              <p className="text-sm leading-7">
                <EvidencedText claim={data.pharmacokinetics} />
              </p>
            </ResultSection>
          )}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[1.3fr_0.9fr]">
        <div className="space-y-4">
          {data.indications?.length > 0 && (
            <ResultSection title="Indications" eyebrow="Clinical use">
              <ul className="space-y-1">
                <TruncatedList
                  items={data.indications}
                  renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
                />
              </ul>
            </ResultSection>
          )}

          {data.dosing?.length > 0 && (
            <ResultSection title="Dosing and Practical Use" eyebrow="Regimens">
              <TruncatedList
                items={data.dosing}
                renderItem={(dose, i) => (
                  <ResultMetaCard key={i}>
                    <p className="text-sm leading-7">
                      <EvidencedText claim={dose} />
                    </p>
                    {(dose.route || dose.frequency) && (
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-text-muted">
                        {dose.route && (
                          <MetaChip label="Route" value={dose.route} />
                        )}
                        {dose.frequency && (
                          <MetaChip label="Frequency" value={dose.frequency} />
                        )}
                      </div>
                    )}
                  </ResultMetaCard>
                )}
              />
            </ResultSection>
          )}

          {data.monitoring?.length > 0 && (
            <ResultSection title="Monitoring" eyebrow="Follow-up">
              <ul className="space-y-1">
                <TruncatedList
                  items={data.monitoring}
                  renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
                />
              </ul>
            </ResultSection>
          )}
        </div>

        <div className="space-y-4">
          {data.contraindications?.length > 0 && (
            <ResultSection title="Contraindications" eyebrow="Avoid use">
              <ul className="space-y-1">
                <TruncatedList
                  items={data.contraindications}
                  renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
                />
              </ul>
            </ResultSection>
          )}

          {data.side_effects?.length > 0 && (
            <ResultSection title="Adverse Effects" eyebrow="Safety">
              <ul className="space-y-1">
                <TruncatedList
                  items={data.side_effects}
                  renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
                />
              </ul>
            </ResultSection>
          )}

          {data.interactions?.length > 0 && (
            <ResultSection title="Drug Interactions" eyebrow="Watch for">
              <TruncatedList
                items={data.interactions}
                renderItem={(ix, i) => (
                  <ResultMetaCard key={i}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-sm text-text">
                        {ix.drug}
                      </span>
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
                    <p className="mt-2 text-sm leading-7 text-text-secondary">
                      {ix.description}
                    </p>
                  </ResultMetaCard>
                )}
              />
            </ResultSection>
          )}

          {data.special_populations?.length > 0 && (
            <ResultSection title="Special Populations" eyebrow="Adjustments">
              <ul className="space-y-1">
                <TruncatedList
                  items={data.special_populations}
                  renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
                />
              </ul>
            </ResultSection>
          )}
        </div>
      </div>

      {data.references?.length > 0 && (
        <ReferenceList references={data.references} />
      )}
    </div>
  );
}

function MetaChip({ label, value }: { label: string; value: string }) {
  return (
    <span className="rounded-full bg-surface px-2.5 py-1">
      {label}: <span className="text-text-secondary">{value}</span>
    </span>
  );
}
