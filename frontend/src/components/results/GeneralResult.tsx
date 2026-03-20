"use client";

import ReactMarkdown from "react-markdown";
import type { GeneralResponse } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";
import { Accordion } from "@/components/ui/Accordion";

interface GeneralResultProps {
  data: GeneralResponse;
}

export function GeneralResult({ data }: GeneralResultProps) {
  const variant =
    data.confidence === "high"
      ? "success"
      : data.confidence === "moderate"
        ? "warning"
        : "danger";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="text-2xl font-bold">General Response</h2>
        <Badge variant={variant}>{data.confidence} confidence</Badge>
      </div>

      <div className="prose prose-sm max-w-none dark:prose-invert">
        <ReactMarkdown>{data.summary}</ReactMarkdown>
      </div>

      {data.key_points.length > 0 && (
        <Accordion title="Key Points" count={data.key_points.length} defaultOpen>
          <ul className="list-disc list-inside space-y-1 text-sm">
            {data.key_points.map((point, i) => (
              <li key={i}>{point}</li>
            ))}
          </ul>
        </Accordion>
      )}

      {data.related_drugs.length > 0 && (
        <Accordion title="Related Drugs" count={data.related_drugs.length}>
          <div className="flex flex-wrap gap-2">
            {data.related_drugs.map((drug, i) => (
              <Badge key={i}>{drug}</Badge>
            ))}
          </div>
        </Accordion>
      )}

      {data.related_conditions.length > 0 && (
        <Accordion title="Related Conditions" count={data.related_conditions.length}>
          <div className="flex flex-wrap gap-2">
            {data.related_conditions.map((cond, i) => (
              <Badge key={i}>{cond}</Badge>
            ))}
          </div>
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
