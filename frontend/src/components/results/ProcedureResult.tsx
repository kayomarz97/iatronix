"use client";

import type { ProcedureResponse } from "@/lib/types";
import { ClaimItem } from "@/components/results/ClaimItem";
import { ReferenceList } from "@/components/results/ReferenceList";
import { ResultHero, ResultMetaCard, ResultSection } from "@/components/results/ResultChrome";

interface ProcedureResultProps {
  data: ProcedureResponse;
}

export function ProcedureResult({ data }: ProcedureResultProps) {
  const directAnswer =
    data.guidelines?.[0]?.value ??
    data.indications?.[0]?.value ??
    (data.technique_steps?.length
      ? `${data.procedure_name} includes ${data.technique_steps.length} key procedural steps in this response.`
      : undefined);

  return (
    <div className="space-y-6">
      <ResultHero
        eyebrow="Procedure Reference"
        title={data.procedure_name}
        stats={[
          { label: "indications", value: data.indications?.length ?? 0 },
          { label: "steps", value: data.technique_steps?.length ?? 0 },
          { label: "guidelines", value: data.guidelines?.length ?? 0 },
        ]}
        directAnswer={directAnswer}
      />

      {data.indications?.length > 0 && (
        <ResultSection title="Indications" eyebrow="When to use it">
          <ul className="space-y-2">
            {data.indications.map((item, i) => (
              <li key={i}>
                <ClaimItem claim={item} />
              </li>
            ))}
          </ul>
        </ResultSection>
      )}

      {data.technique_steps?.length > 0 && (
        <ResultSection title="Technique and Sequence" eyebrow="Step-by-step">
          <ol className="space-y-3">
            {data.technique_steps.map((step) => (
              <li key={step.step_number} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full border border-sky-500/20 bg-sky-500/10 text-sm font-semibold text-sky-300">
                    {step.step_number}
                  </span>
                  <span className="mt-2 h-full w-px bg-border/70" />
                </div>
                <ResultMetaCard className="flex-1">
                  <p className="text-sm leading-7 text-text">{step.description}</p>
                  {step.notes && (
                    <p className="mt-2 text-xs leading-6 text-text-muted">{step.notes}</p>
                  )}
                </ResultMetaCard>
              </li>
            ))}
          </ol>
        </ResultSection>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {data.contraindications?.length > 0 && (
          <ResultSection title="Contraindications" eyebrow="Avoid or defer">
            <ul className="space-y-2">
              {data.contraindications.map((item, i) => (
                <li key={i}>
                  <ClaimItem claim={item} />
                </li>
              ))}
            </ul>
          </ResultSection>
        )}

        {data.complications?.length > 0 && (
          <ResultSection title="Complications" eyebrow="Risks">
            <ul className="space-y-2">
              {data.complications.map((item, i) => (
                <li key={i}>
                  <ClaimItem claim={item} />
                </li>
              ))}
            </ul>
          </ResultSection>
        )}
      </div>

      {data.guidelines?.length > 0 && (
        <ResultSection title="Guidelines and Recommendations" eyebrow="Practice points">
          <div className="space-y-3">
            {data.guidelines.map((g, i) => (
              <ResultMetaCard key={i}>
                <ClaimItem claim={g} />
                {g.society && (
                  <p className="mt-2 text-xs uppercase tracking-[0.18em] text-text-muted">
                    {g.society}
                  </p>
                )}
              </ResultMetaCard>
            ))}
          </div>
        </ResultSection>
      )}

      {data.references?.length > 0 && <ReferenceList references={data.references} />}
    </div>
  );
}
