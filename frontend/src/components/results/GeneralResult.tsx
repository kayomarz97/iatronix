"use client";

import ReactMarkdown from "react-markdown";
import type { GeneralResponse } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";
import { ReferenceList } from "@/components/results/ReferenceList";

interface GeneralResultProps {
  data: GeneralResponse;
}

export function GeneralResult({ data }: GeneralResultProps) {
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

      {data.key_points?.length > 0 && (
        <div
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-md)",
            padding: "1rem 1.25rem",
          }}
        >
          <h3
            style={{
              fontSize: "0.875rem",
              fontWeight: 600,
              marginBottom: "0.75rem",
              color: "var(--text-primary)",
            }}
          >
            Key Points
          </h3>
          <ul style={{ margin: 0, paddingLeft: "1.25rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {data.key_points.map((point, i) => (
              <li key={i} style={{ fontSize: "0.85rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
                {point}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.related_drugs?.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", alignItems: "center" }}>
          <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", marginRight: "0.25rem" }}>
            Related drugs:
          </span>
          {data.related_drugs.map((drug, i) => (
            <span
              key={i}
              style={{
                fontSize: "0.7rem",
                padding: "2px 8px",
                borderRadius: "9999px",
                background: "var(--accent-bg, rgba(59,130,246,0.12))",
                color: "var(--accent)",
                fontWeight: 500,
              }}
            >
              {drug}
            </span>
          ))}
        </div>
      )}

      {data.related_conditions?.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", alignItems: "center" }}>
          <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", marginRight: "0.25rem" }}>
            Related conditions:
          </span>
          {data.related_conditions.map((cond, i) => (
            <span
              key={i}
              style={{
                fontSize: "0.7rem",
                padding: "2px 8px",
                borderRadius: "9999px",
                background: "rgba(139,92,246,0.12)",
                color: "#a78bfa",
                fontWeight: 500,
              }}
            >
              {cond}
            </span>
          ))}
        </div>
      )}

      {data.references?.length > 0 && (
        <ReferenceList references={data.references} />
      )}
    </div>
  );
}
