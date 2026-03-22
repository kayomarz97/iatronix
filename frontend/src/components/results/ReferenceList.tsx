"use client";

import type { Reference } from "@/lib/types";
import { Accordion } from "@/components/ui/Accordion";

interface ReferenceListProps {
  references: Reference[];
}

export function ReferenceList({ references }: ReferenceListProps) {
  if (references.length === 0) return null;

  return (
    <Accordion title="References" count={references.length}>
      <ul className="text-xs text-text-muted space-y-1">
        {references.map((ref, i) => (
          <li key={i}>
            {ref.url ? (
              <a
                href={ref.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                {ref.source}
              </a>
            ) : (
              ref.source
            )}
            {ref.title ? ` — ${ref.title}` : ""}
            {ref.year ? ` (${ref.year})` : ""}
          </li>
        ))}
      </ul>
    </Accordion>
  );
}
