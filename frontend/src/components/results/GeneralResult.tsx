"use client";

import ReactMarkdown from "react-markdown";
import type { GeneralResponse } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";
import { ReferenceList } from "@/components/results/ReferenceList";
import { ResultChipRow, ResultHero, ResultSection } from "@/components/results/ResultChrome";

interface GeneralResultProps {
  data: GeneralResponse;
}

export function GeneralResult({ data }: GeneralResultProps) {
  return (
    <div className="space-y-6">
      <ResultHero
        eyebrow="Clinical Summary"
        title="Result"
        stats={[
          { label: "key points", value: data.key_points?.length ?? 0 },
          { label: "references", value: data.references?.length ?? 0 },
          { label: "confidence", value: data.confidence },
        ]}
        directAnswer={firstSentence(data.summary) ?? data.summary}
        context={
          data.confidence === "low" ? (
            <Badge variant="danger">Low confidence: verify with primary sources.</Badge>
          ) : undefined
        }
      />

      {data.key_points?.length > 0 && (
        <ResultSection title="Key Points" eyebrow="More detail">
          <ul className="list-disc space-y-2 pl-5">
            {data.key_points.map((point, i) => (
              <li key={i} className="text-sm leading-7 text-text-secondary">
                {point}
              </li>
            ))}
          </ul>
        </ResultSection>
      )}

      <ResultSection title="Supporting Summary" eyebrow="Expanded view">
        <div className="prose prose-sm max-w-none dark:prose-invert">
          <ReactMarkdown>{data.summary}</ReactMarkdown>
        </div>
      </ResultSection>

      <div className="grid gap-4 lg:grid-cols-2">
        <ResultSection title="Related Drugs" eyebrow="Explore next">
          <ResultChipRow label="Drugs" items={data.related_drugs ?? []} tone="accent" />
        </ResultSection>

        <ResultSection title="Related Conditions" eyebrow="Explore next">
          <ResultChipRow label="Conditions" items={data.related_conditions ?? []} />
        </ResultSection>
      </div>

      {data.references?.length > 0 && <ReferenceList references={data.references} />}
    </div>
  );
}

function firstSentence(text: string): string | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  const match = trimmed.match(/.+?[.!?](\s|$)/);
  return (match?.[0] ?? trimmed).trim();
}
