"use client";

import type { DrugResponse } from "@/lib/types";
import { Accordion } from "@/components/ui/Accordion";
import { Badge } from "@/components/ui/Badge";
import { ClaimItem } from "./ClaimItem";
import { EvidenceBadge } from "./EvidenceBadge";
import { TruncatedList } from "./TruncatedList";
import { severityColor } from "@/lib/formatters";

interface DrugInfoResultProps {
  data: DrugResponse;
}

export function DrugInfoResult({ data }: DrugInfoResultProps) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold">{data.drug_name}</h2>
        {data.drug_class && (
          <p className="text-text-secondary text-sm mt-1">{data.drug_class}</p>
        )}
      </div>

      {data.mechanism_of_action && (
        <Accordion title="Mechanism of Action" defaultOpen>
          <p className="text-sm">{data.mechanism_of_action.value}</p>
          <EvidenceBadge claim={data.mechanism_of_action} />
        </Accordion>
      )}

      {data.indications.length > 0 && (
        <Accordion title="Indications" count={data.indications.length} defaultOpen>
          <TruncatedList
            items={data.indications}
            renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
          />
        </Accordion>
      )}

      {data.dosing.length > 0 && (
        <Accordion title="Dosing" count={data.dosing.length} defaultOpen>
          <TruncatedList
            items={data.dosing}
            renderItem={(dose, i) => (
              <div key={i} className="py-2 border-b border-border last:border-0">
                <p className="text-sm">{dose.value}</p>
                {dose.route && (
                  <span className="text-xs text-text-muted mr-2">
                    Route: {dose.route}
                  </span>
                )}
                {dose.frequency && (
                  <span className="text-xs text-text-muted">
                    Freq: {dose.frequency}
                  </span>
                )}
                <EvidenceBadge claim={dose} />
              </div>
            )}
          />
        </Accordion>
      )}

      {data.contraindications.length > 0 && (
        <Accordion title="Contraindications" count={data.contraindications.length}>
          <TruncatedList
            items={data.contraindications}
            renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
          />
        </Accordion>
      )}

      {data.side_effects.length > 0 && (
        <Accordion title="Side Effects" count={data.side_effects.length}>
          <TruncatedList
            items={data.side_effects}
            renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
          />
        </Accordion>
      )}

      {data.interactions.length > 0 && (
        <Accordion title="Interactions" count={data.interactions.length}>
          <TruncatedList
            items={data.interactions}
            renderItem={(ix, i) => (
              <div key={i} className="py-2 border-b border-border last:border-0">
                <div className="flex items-center gap-2">
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
                <p className="text-sm text-text-secondary mt-1">
                  {ix.description}
                </p>
                {ix.evidence && <EvidenceBadge claim={ix.evidence} />}
              </div>
            )}
          />
        </Accordion>
      )}

      {data.pharmacokinetics && (
        <Accordion title="Pharmacokinetics">
          <p className="text-sm">{data.pharmacokinetics.value}</p>
          <EvidenceBadge claim={data.pharmacokinetics} />
        </Accordion>
      )}

      {data.special_populations.length > 0 && (
        <Accordion title="Special Populations" count={data.special_populations.length}>
          <TruncatedList
            items={data.special_populations}
            renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
          />
        </Accordion>
      )}

      {data.monitoring.length > 0 && (
        <Accordion title="Monitoring" count={data.monitoring.length}>
          <TruncatedList
            items={data.monitoring}
            renderItem={(claim, i) => <ClaimItem key={i} claim={claim} />}
          />
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
