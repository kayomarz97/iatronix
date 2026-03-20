"use client";

import type { DiseaseResponse } from "@/lib/types";
import { Accordion } from "@/components/ui/Accordion";
import { ClaimItem } from "./ClaimItem";
import { EvidenceBadge } from "./EvidenceBadge";
import { TruncatedList } from "./TruncatedList";

interface DiseaseInfoResultProps {
  data: DiseaseResponse;
}

export function DiseaseInfoResult({ data }: DiseaseInfoResultProps) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold">{data.disease_name}</h2>
        {data.icd_10 && (
          <p className="text-text-secondary text-sm mt-1">
            ICD-10: {data.icd_10}
          </p>
        )}
      </div>

      {data.pathophysiology && (
        <Accordion title="Pathophysiology" defaultOpen>
          <p className="text-sm">{data.pathophysiology.value}</p>
          <EvidenceBadge claim={data.pathophysiology} />
        </Accordion>
      )}

      {data.epidemiology && (
        <Accordion title="Epidemiology">
          <p className="text-sm">{data.epidemiology.value}</p>
          <EvidenceBadge claim={data.epidemiology} />
        </Accordion>
      )}

      {data.clinical_features.length > 0 && (
        <Accordion title="Clinical Features" count={data.clinical_features.length} defaultOpen>
          <TruncatedList
            items={data.clinical_features}
            renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
          />
        </Accordion>
      )}

      {data.diagnostic_criteria.length > 0 && (
        <Accordion title="Diagnostic Criteria" count={data.diagnostic_criteria.length}>
          <TruncatedList
            items={data.diagnostic_criteria}
            renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
          />
        </Accordion>
      )}

      <Accordion title="Treatment" defaultOpen>
        <div className="space-y-4">
          {data.treatment.first_line.length > 0 && (
            <div>
              <h4 className="font-medium text-sm mb-2">First Line</h4>
              <TruncatedList
                items={data.treatment.first_line}
                renderItem={(entry, i) => (
                  <div key={i} className="py-2 border-b border-border last:border-0">
                    <p className="text-sm">{entry.value}</p>
                    {entry.drug_names.length > 0 && (
                      <p className="text-xs text-primary-light mt-1">
                        Drugs: {entry.drug_names.join(", ")}
                      </p>
                    )}
                    <EvidenceBadge claim={entry} />
                  </div>
                )}
              />
            </div>
          )}

          {data.treatment.second_line.length > 0 && (
            <div>
              <h4 className="font-medium text-sm mb-2">Second Line</h4>
              <TruncatedList
                items={data.treatment.second_line}
                renderItem={(entry, i) => (
                  <div key={i} className="py-2 border-b border-border last:border-0">
                    <p className="text-sm">{entry.value}</p>
                    {entry.drug_names.length > 0 && (
                      <p className="text-xs text-primary-light mt-1">
                        Drugs: {entry.drug_names.join(", ")}
                      </p>
                    )}
                    <EvidenceBadge claim={entry} />
                  </div>
                )}
              />
            </div>
          )}

          {data.treatment.adjunctive.length > 0 && (
            <div>
              <h4 className="font-medium text-sm mb-2">Adjunctive</h4>
              <TruncatedList
                items={data.treatment.adjunctive}
                renderItem={(entry, i) => (
                  <div key={i} className="py-2 border-b border-border last:border-0">
                    <p className="text-sm">{entry.value}</p>
                    <EvidenceBadge claim={entry} />
                  </div>
                )}
              />
            </div>
          )}

          {data.treatment.non_pharmacological.length > 0 && (
            <div>
              <h4 className="font-medium text-sm mb-2">Non-Pharmacological</h4>
              <TruncatedList
                items={data.treatment.non_pharmacological}
                renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
              />
            </div>
          )}
        </div>
      </Accordion>

      {data.complications.length > 0 && (
        <Accordion title="Complications" count={data.complications.length}>
          <TruncatedList
            items={data.complications}
            renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
          />
        </Accordion>
      )}

      {data.prognosis && (
        <Accordion title="Prognosis">
          <p className="text-sm">{data.prognosis.value}</p>
          <EvidenceBadge claim={data.prognosis} />
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
