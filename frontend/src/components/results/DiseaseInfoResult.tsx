"use client";

import type { DiseaseResponse, TreatmentEntry } from "@/lib/types";
import { ClaimItem } from "./ClaimItem";
import { EvidencedText } from "./EvidenceBadge";
import { ReferenceList } from "./ReferenceList";
import { ResultHero, ResultMetaCard, ResultSection } from "./ResultChrome";
import { TruncatedList } from "./TruncatedList";

interface DiseaseInfoResultProps {
  data: DiseaseResponse;
}

export function DiseaseInfoResult({ data }: DiseaseInfoResultProps) {
  return (
    <div className="space-y-6">
      <ResultHero
        eyebrow="Disease Reference"
        title={data.disease_name}
        subtitle={data.icd_10 ? `ICD-10: ${data.icd_10}` : undefined}
        stats={[
          ...(data.clinical_features?.length
            ? [{ label: "features", value: data.clinical_features.length }]
            : []),
          ...(data.diagnostic_criteria?.length
            ? [{ label: "diagnostics", value: data.diagnostic_criteria.length }]
            : []),
          ...(data.treatment?.first_line?.length
            ? [{ label: "first-line items", value: data.treatment.first_line.length }]
            : []),
        ]}
        directAnswer={data.bluf ?? undefined}
        context={data.additional_clinical_context ?? undefined}
      />

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.95fr]">
        <div className="space-y-4">
          {data.diagnostic_criteria?.length > 0 && (
            <ResultSection title="Diagnosis and Workup" eyebrow="What confirms it">
              <ul className="space-y-1">
                <TruncatedList
                  items={data.diagnostic_criteria}
                  renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
                />
              </ul>
            </ResultSection>
          )}

          <ResultSection title="Management" eyebrow="What to do">
            <div className="space-y-4">
              {data.treatment?.first_line?.length > 0 && (
                <TreatmentBlock
                  title="First Line"
                  tone="primary"
                  entries={data.treatment.first_line}
                />
              )}

              {data.treatment?.second_line?.length > 0 && (
                <TreatmentBlock
                  title="Second Line"
                  tone="default"
                  entries={data.treatment.second_line}
                />
              )}

              {data.treatment?.adjunctive?.length > 0 && (
                <TreatmentBlock
                  title="Adjunctive Therapy"
                  tone="default"
                  entries={data.treatment.adjunctive}
                />
              )}

              {data.treatment?.non_pharmacological?.length > 0 && (
                  <ResultMetaCard>
                    <h4 className="text-sm font-semibold text-text">
                      Non-Pharmacological
                    </h4>
                  <ul className="mt-3 space-y-1">
                    <TruncatedList
                      items={data.treatment.non_pharmacological}
                      renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
                      />
                    </ul>
                  </ResultMetaCard>
              )}
            </div>
          </ResultSection>
        </div>

        <div className="space-y-4">
          {data.clinical_features?.length > 0 && (
            <ResultSection title="Clinical Features" eyebrow="Presentation">
              <ul className="space-y-1">
                <TruncatedList
                  items={data.clinical_features}
                  renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
                />
              </ul>
            </ResultSection>
          )}

          {data.complications?.length > 0 && (
            <ResultSection title="Complications" eyebrow="What can go wrong">
              <ul className="space-y-1">
                <TruncatedList
                  items={data.complications}
                  renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
                />
              </ul>
            </ResultSection>
          )}

          {data.prognosis && (
            <ResultSection title="Prognosis" eyebrow="Expected course">
              <p className="text-sm leading-7">
                <EvidencedText claim={data.prognosis} />
              </p>
            </ResultSection>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {data.etiology && data.etiology.length > 0 && (
          <ResultSection title="Etiology" eyebrow="Causes and risk factors">
            <ul className="space-y-1">
              <TruncatedList
                items={data.etiology}
                renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
              />
            </ul>
          </ResultSection>
        )}

        {(data.pathophysiology || data.epidemiology) && (
          <ResultSection title="Background" eyebrow="Mechanism and burden">
            <div className="space-y-4">
              {data.pathophysiology && (
                <div>
                  <h4 className="text-sm font-semibold text-text">
                    Pathophysiology
                  </h4>
                  <p className="mt-2 text-sm leading-7">
                    <EvidencedText claim={data.pathophysiology} />
                  </p>
                </div>
              )}
              {data.epidemiology && (
                <div>
                  <h4 className="text-sm font-semibold text-text">
                    Epidemiology
                  </h4>
                  <p className="mt-2 text-sm leading-7">
                    <EvidencedText claim={data.epidemiology} />
                  </p>
                </div>
              )}
            </div>
          </ResultSection>
        )}
      </div>

      {data.references?.length > 0 && (
        <ReferenceList references={data.references} />
      )}
    </div>
  );
}

function TreatmentBlock({
  title,
  tone,
  entries,
}: {
  title: string;
  tone: "primary" | "default";
  entries: TreatmentEntry[];
}) {
  const toneClass =
    tone === "primary"
      ? "border-sky-500/20 bg-sky-500/10"
      : "border-border/60 bg-background/60";

  return (
    <div className={`rounded-xl border p-4 ${toneClass}`}>
      <h4 className="text-sm font-semibold text-text">{title}</h4>
      <div className="mt-3 space-y-3">
        <TruncatedList
          items={entries}
          renderItem={(entry, i) => (
            <ResultMetaCard key={i}>
              <p className="text-sm leading-7">
                <EvidencedText claim={entry} />
              </p>
              {entry.drug_names?.length > 0 && (
                <p className="mt-2 text-xs text-text-secondary">
                  {entry.drug_names.join(", ")}
                </p>
              )}
            </ResultMetaCard>
          )}
        />
      </div>
    </div>
  );
}
