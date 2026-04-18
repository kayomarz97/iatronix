"use client";

import React from "react";
import { ResultSection } from "./ResultChrome";

interface TableRendererProps {
  tables?: { title: string; headers: string[]; rows: string[][] }[];
}

export function TableRenderer({ tables }: TableRendererProps) {
  if (!tables || tables.length === 0) return null;

  return (
    <ResultSection title="Data Tables" eyebrow="Structured Summary">
      <div className="flex flex-col gap-6">
        {tables.map((table, tIdx) => (
          <div key={tIdx} className="overflow-hidden rounded-xl border border-border">
            {table.title && (
              <div className="bg-secondary/50 px-4 py-2 text-sm font-semibold border-b border-border">
                {table.title}
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                {table.headers && table.headers.length > 0 && (
                  <thead className="bg-muted/50 text-text-secondary">
                    <tr>
                      {table.headers.map((h, i) => (
                        <th key={i} className="px-4 py-3 font-medium">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                )}
                <tbody className="divide-y divide-border">
                  {table.rows.map((row, rIdx) => (
                    <tr key={rIdx} className="hover:bg-muted/30 transition-colors">
                      {row.map((cell, cIdx) => (
                        <td key={cIdx} className="px-4 py-3 align-top text-text">
                          {cell}
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
