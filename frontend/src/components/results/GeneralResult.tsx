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
    <div className="space-y-5">
      <div className="border-b border-border pb-4 flex items-center gap-2">
        <h2 className="text-2xl font-bold">Result</h2>
        {data.confidence === "low" && (
          <Badge variant="danger">Low confidence</Badge>
        )}
      </div>

      <div className="prose prose-sm max-w-none dark:prose-invert">
        <ReactMarkdown>{data.summary}</ReactMarkdown>
      </div>

      {data.key_points.length > 0 && (
        <div>
          <h3 className="text-base font-semibold mb-2">Key Points</h3>
          <ul className="list-disc list-inside space-y-1 text-sm">
            {data.key_points.map((point, i) => (
              <li key={i}>{point}</li>
            ))}
          </ul>
        </div>
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
