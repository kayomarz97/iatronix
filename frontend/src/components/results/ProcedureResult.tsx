"use client";

import type { ProcedureResponse } from "@/lib/types";
import { ClaimItem } from "@/components/results/ClaimItem";
import { Accordion } from "@/components/ui/Accordion";
import { ReferenceList } from "@/components/results/ReferenceList";

interface ProcedureResultProps {
  data: ProcedureResponse;
}

export function ProcedureResult({ data }: ProcedureResultProps) {
  return (
    <div className="space-y-5">
      <div className="border-b border-border pb-4">
        <h2 className="text-2xl font-bold">{data.procedure_name}</h2>
      </div>

      {data.indications.length > 0 && (
        <Accordion title="Indications" count={data.indications.length} defaultOpen>
          <ul className="space-y-2">
            {data.indications.map((item, i) => (
              <li key={i}>
                <ClaimItem claim={item} />
              </li>
            ))}
          </ul>
        </Accordion>
      )}

      {data.contraindications.length > 0 && (
        <Accordion title="Contraindications" count={data.contraindications.length}>
          <ul className="space-y-2">
            {data.contraindications.map((item, i) => (
              <li key={i}>
                <ClaimItem claim={item} />
              </li>
            ))}
          </ul>
        </Accordion>
      )}

      {data.technique_steps.length > 0 && (
        <Accordion title="Technique / Steps" count={data.technique_steps.length} defaultOpen>
          <ol className="space-y-3">
            {data.technique_steps.map((step) => (
              <li key={step.step_number} className="flex gap-3">
                <span className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/10 text-primary text-sm font-bold flex items-center justify-center">
                  {step.step_number}
                </span>
                <div>
                  <p className="text-sm">{step.description}</p>
                  {step.notes && (
                    <p className="text-xs text-text-muted mt-1">{step.notes}</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </Accordion>
      )}

      {data.complications.length > 0 && (
        <Accordion title="Complications" count={data.complications.length}>
          <ul className="space-y-2">
            {data.complications.map((item, i) => (
              <li key={i}>
                <ClaimItem claim={item} />
              </li>
            ))}
          </ul>
        </Accordion>
      )}

      {data.guidelines.length > 0 && (
        <Accordion title="Guidelines & Recommendations" count={data.guidelines.length}>
          <ul className="space-y-2">
            {data.guidelines.map((g, i) => (
              <li key={i}>
                <ClaimItem claim={g} />
                {g.society && (
                  <span className="text-xs text-text-muted ml-2">
                    — {g.society}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Accordion>
      )}

      {data.references.length > 0 && (
        <ReferenceList references={data.references} />
      )}
    </div>
  );
}
