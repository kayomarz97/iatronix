"use client";

import React from "react";
import { ResultSection } from "./ResultChrome";

interface TableRendererProps {
  tables?: { title: string; headers: string[]; rows: string[][] }[];
}

const LOE_CLR: Record<string, string> = {
  I: "var(--success)",
  II: "var(--warning)",
  III: "var(--text-muted)",
};

const COR_CLR: Record<string, string> = {
  I: "var(--success)",
  IIa: "var(--accent)",
  IIb: "var(--warning)",
  III: "var(--danger)",
  "III-no-benefit": "var(--warning)",
  "III-harm": "var(--danger)",
};

function CellBadge({ value, color }: { value: string; color: string }) {
  return (
    <span
      className="font-mono text-[10px] px-[5px] py-[1px] rounded-[4px] whitespace-nowrap"
      style={{
        backgroundColor: `color-mix(in srgb, ${color} 18%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 36%, transparent)`,
        color,
      }}
    >
      {value}
    </span>
  );
}

function renderCell(value: string, headerLower: string, colIdx: number) {
  if (colIdx === 0) {
    return <span className="font-semibold text-[var(--text-primary)]">{value}</span>;
  }
  if (headerLower.includes("loe") && value) {
    const color = LOE_CLR[value] ?? "var(--text-muted)";
    return <CellBadge value={`LoE ${value}`} color={color} />;
  }
  if (headerLower.includes("cor") && value) {
    const color = COR_CLR[value] ?? "var(--text-muted)";
    return <CellBadge value={`Class ${value}`} color={color} />;
  }
  return <span className="text-[var(--text-primary)]">{value}</span>;
}

export function TableRenderer({ tables }: TableRendererProps) {
  if (!tables || tables.length === 0) return null;

  return (
    <ResultSection title="Data Tables" eyebrow="Structured Summary">
      <div className="flex flex-col gap-6">
        {tables.map((table, tIdx) => (
          <div key={tIdx} id={`tbl-${tIdx}`} className="overflow-hidden rounded-xl border border-[var(--border)]">
            {table.title && (
              <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--border)]"
                   style={{ background: "var(--bg-elevated)" }}>
                <div className="w-2 h-2 rounded-sm flex-shrink-0" style={{ background: "var(--accent)" }} />
                <span className="text-sm font-semibold text-[var(--text-primary)]">{table.title}</span>
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                {table.headers && table.headers.length > 0 && (
                  <thead style={{ background: "var(--bg-elevated)", borderBottom: "1px solid var(--border)" }}>
                    <tr>
                      {table.headers.map((h, i) => (
                        <th key={i} className="px-4 py-3 text-[0.75rem] uppercase tracking-wide font-semibold text-[var(--text-muted)]">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                )}
                <tbody>
                  {table.rows.map((row, rIdx) => (
                    <tr key={rIdx}
                        className="border-b border-[var(--border)] transition-colors"
                        style={{ cursor: "default" }}
                        onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-elevated)")}
                        onMouseLeave={e => (e.currentTarget.style.background = "")}>
                      {row.map((cell, cIdx) => (
                        <td key={cIdx} className="px-4 py-3 align-top text-sm">
                          {renderCell(cell, (table.headers[cIdx] ?? "").toLowerCase(), cIdx)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </ResultSection>
  );
}
