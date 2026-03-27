"use client";

import React from "react";
import type { AdaptiveResponse, AdaptiveSection } from "@/lib/types";

interface Props {
  data: AdaptiveResponse;
}

function SectionCard({ section }: { section: AdaptiveSection }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 mb-3">
      <div className="flex items-center gap-2 mb-2">
        <h3 className="font-semibold text-sm text-foreground">{section.title}</h3>
        {section.loe && (
          <span className="text-xs px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300">
            LoE {section.loe}
          </span>
        )}
        {section.cor && (
          <span className="text-xs px-1.5 py-0.5 rounded bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300">
            Class {section.cor}
          </span>
        )}
      </div>
      {Array.isArray(section.content) ? (
        <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground">
          {(section.content as string[]).map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">{String(section.content)}</p>
      )}
    </div>
  );
}

export function AdaptiveResultRenderer({ data }: Props) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950 p-4">
        <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
          {data.bluf}
        </p>
      </div>

      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="capitalize bg-muted px-2 py-0.5 rounded">{data.depth}</span>
        <span>{data.response_focus}</span>
      </div>

      {data.sections.map((section, i) => (
        <SectionCard key={i} section={section} />
      ))}

      {data.references.length > 0 && (
        <div className="text-xs text-muted-foreground border-t pt-3 mt-2">
          <p className="font-medium mb-1">References</p>
          <ul className="space-y-0.5">
            {data.references.map((ref, i) => (
              <li key={i}>{ref}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
