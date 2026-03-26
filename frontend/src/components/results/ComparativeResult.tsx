"use client";

import type { ComparativeResponse } from "@/lib/types";
import { EvidencedText } from "./EvidenceBadge";
import { TruncatedList } from "./TruncatedList";
import { ReferenceList } from "./ReferenceList";

interface ComparativeResultProps {
  data: ComparativeResponse;
}

const ENTITY_COLORS = [
  { bg: "rgba(59,130,246,0.08)", border: "rgba(59,130,246,0.25)", label: "#60a5fa" },
  { bg: "rgba(139,92,246,0.08)", border: "rgba(139,92,246,0.25)", label: "#a78bfa" },
  { bg: "rgba(16,185,129,0.08)", border: "rgba(16,185,129,0.25)", label: "#34d399" },
];

export function ComparativeResult({ data }: ComparativeResultProps) {
  // Build entity → color map from entities_compared order
  const entityColor: Record<string, (typeof ENTITY_COLORS)[0]> = {};
  data.entities_compared.forEach((e, i) => {
    entityColor[e] = ENTITY_COLORS[i % ENTITY_COLORS.length];
  });

  return (
    <div className="space-y-5">
      {/* Header with entity pills */}
      <div style={{ borderBottom: "1px solid var(--border)", paddingBottom: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
          {data.entities_compared.map((entity, i) => (
            <span key={entity}>
              {i > 0 && (
                <span style={{ color: "var(--text-muted)", fontWeight: 600, fontSize: "1.1rem", marginRight: "0.75rem" }}>
                  vs
                </span>
              )}
              <span
                style={{
                  fontSize: "1.25rem",
                  fontWeight: 700,
                  color: entityColor[entity]?.label ?? "var(--text-primary)",
                }}
              >
                {entity}
              </span>
            </span>
          ))}
        </div>
        {data.comparison_type && (
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.85rem" }}>
            {data.comparison_type}
          </p>
        )}
      </div>

      {/* Summary */}
      {data.summary && (
        <div
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-md)",
            padding: "1rem",
          }}
        >
          <p style={{ fontSize: "0.875rem", lineHeight: 1.7 }}>
            <EvidencedText claim={data.summary} />
          </p>
        </div>
      )}

      {/* Detailed Comparison */}
      {data.detailed_comparison?.length > 0 && (
        <div>
          <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem" }}>
            Detailed Comparison
          </h3>
          <TruncatedList
            items={data.detailed_comparison}
            renderItem={(dim, i) => (
              <div
                key={i}
                style={{
                  marginBottom: "0.75rem",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-md)",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    padding: "0.5rem 0.75rem",
                    background: "var(--bg-elevated)",
                    borderBottom: "1px solid var(--border)",
                    fontWeight: 600,
                    fontSize: "0.8rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.03em",
                    color: "var(--text-secondary)",
                  }}
                >
                  {dim.dimension}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(Object.keys(dim.values).length, 2)}, 1fr)` }}>
                  {Object.entries(dim.values).map(([entity, claim], j) => {
                    const color = entityColor[entity] ?? ENTITY_COLORS[0];
                    return (
                      <div
                        key={entity}
                        style={{
                          padding: "0.75rem",
                          borderRight: j === 0 && Object.keys(dim.values).length > 1 ? "1px solid var(--border)" : "none",
                          background: color.bg,
                        }}
                      >
                        <p style={{ fontWeight: 600, fontSize: "0.7rem", color: color.label, marginBottom: "0.35rem", textTransform: "uppercase" }}>
                          {entity}
                        </p>
                        <p style={{ fontSize: "0.825rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
                          <EvidencedText claim={claim} />
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          />
        </div>
      )}

      {/* Clinical Preference */}
      {data.clinical_preference && (
        <div
          style={{
            background: "rgba(16,185,129,0.06)",
            border: "1px solid rgba(16,185,129,0.2)",
            borderRadius: "var(--radius-md)",
            padding: "0.75rem 1rem",
          }}
        >
          <h3 style={{ fontSize: "0.8rem", fontWeight: 600, color: "#34d399", marginBottom: "0.35rem" }}>
            Clinical Preference
          </h3>
          <p style={{ fontSize: "0.85rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
            <EvidencedText claim={data.clinical_preference} />
          </p>
        </div>
      )}

      {data.references?.length > 0 && (
        <ReferenceList references={data.references} />
      )}
    </div>
  );
}
