"use client";

import type { DiseaseResponse } from "@/lib/types";
import { Accordion } from "@/components/ui/Accordion";
import { ClaimItem } from "./ClaimItem";
import { EvidencedText } from "./EvidenceBadge";
import { TruncatedList } from "./TruncatedList";

interface DiseaseInfoResultProps {
  data: DiseaseResponse;
}

export function DiseaseInfoResult({ data }: DiseaseInfoResultProps) {
  return (
    <div className="space-y-5">
      <div className="border-b border-border pb-4">
        <h2 className="text-2xl font-bold">{data.disease_name}</h2>
        {data.icd_10 && (
          <p className="text-text-muted text-sm mt-1">ICD-10: {data.icd_10}</p>
        )}
      </div>

      {data.etiology && data.etiology.length > 0 && (
        <Section title="Etiology">
          <ul className="list-disc list-inside space-y-1">
            <TruncatedList
              items={data.etiology}
              renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
            />
          </ul>
        </Section>
      )}

      {data.clinical_features.length > 0 && (
        <Section title="Signs &amp; Symptoms">
          <ul className="list-disc list-inside space-y-1">
            <TruncatedList
              items={data.clinical_features}
              renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
            />
          </ul>
        </Section>
      )}

      {data.pathophysiology && (
        <Section title="Pathophysiology">
          <p className="text-sm leading-relaxed">
            <EvidencedText claim={data.pathophysiology} />
          </p>
        </Section>
      )}

      {data.epidemiology && (
        <Section title="Epidemiology">
          <p className="text-sm leading-relaxed">
            <EvidencedText claim={data.epidemiology} />
          </p>
        </Section>
      )}

      {data.diagnostic_criteria.length > 0 && (
        <Section title="Diagnosis">
          <ul className="list-disc list-inside space-y-1">
            <TruncatedList
              items={data.diagnostic_criteria}
              renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
            />
          </ul>
        </Section>
      )}

      <Section title="Management">
        <div className="space-y-4">
          {data.treatment.first_line.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-primary mb-2">First Line</h4>
              <TruncatedList
                items={data.treatment.first_line}
                renderItem={(entry, i) => (
                  <div key={i} className="py-2 border-b border-border/50 last:border-0">
                    <p className="text-sm leading-relaxed">
                      <EvidencedText claim={entry} />
                    </p>
                    {entry.drug_names.length > 0 && (
                      <p className="text-xs text-primary-light mt-1">
                        {entry.drug_names.join(", ")}
                      </p>
                    )}
                  </div>
                )}
              />
            </div>
          )}

          {data.treatment.second_line.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-text-secondary mb-2">Second Line</h4>
              <TruncatedList
                items={data.treatment.second_line}
                renderItem={(entry, i) => (
                  <div key={i} className="py-2 border-b border-border/50 last:border-0">
                    <p className="text-sm leading-relaxed">
                      <EvidencedText claim={entry} />
                    </p>
                    {entry.drug_names.length > 0 && (
                      <p className="text-xs text-primary-light mt-1">
                        {entry.drug_names.join(", ")}
                      </p>
                    )}
                  </div>
                )}
              />
            </div>
          )}

          {data.treatment.adjunctive.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-text-secondary mb-2">Adjunctive Therapy</h4>
              <TruncatedList
                items={data.treatment.adjunctive}
                renderItem={(entry, i) => (
                  <div key={i} className="py-2 border-b border-border/50 last:border-0">
                    <p className="text-sm leading-relaxed">
                      <EvidencedText claim={entry} />
                    </p>
                  </div>
                )}
              />
            </div>
          )}

          {data.treatment.non_pharmacological.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-text-secondary mb-2">Non-Pharmacological</h4>
              <ul className="list-disc list-inside space-y-1">
                <TruncatedList
                  items={data.treatment.non_pharmacological}
                  renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
                />
              </ul>
            </div>
          )}
        </div>
      </Section>

      {data.complications.length > 0 && (
        <Section title="Complications">
          <ul className="list-disc list-inside space-y-1">
            <TruncatedList
              items={data.complications}
              renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
            />
          </ul>
        </Section>
      )}

      {data.prognosis && (
        <Section title="Prognosis">
          <p className="text-sm leading-relaxed">
            <EvidencedText claim={data.prognosis} />
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
