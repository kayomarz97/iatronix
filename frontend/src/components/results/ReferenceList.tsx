"use client";

import type { Reference } from "@/lib/types";
import { ExternalLink } from "lucide-react";
import { ResultSection } from "./ResultChrome";

interface ReferenceListProps {
  references: Reference[];
}

function buildFallbackUrl(ref: Reference): string {
  // Build a PubMed search URL from source + title
  const terms = [ref.source, ref.title, ref.year?.toString()]
    .filter(Boolean)
    .join(" ")
    .trim();
  return `https://pubmed.ncbi.nlm.nih.gov/?term=${encodeURIComponent(terms)}`;
}

export function ReferenceList({ references }: ReferenceListProps) {
  if (references.length === 0) return null;

  return (
    <ResultSection title="References" eyebrow="Source trail">
      <ul className="space-y-3">
        {references.map((ref, i) => {
          const safeUrl =
            ref.url &&
            (ref.url.startsWith("https://") || ref.url.startsWith("http://"))
              ? ref.url
              : null;
          const url = safeUrl || buildFallbackUrl(ref);
          return (
            <li
              key={i}
              className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3 text-sm"
            >
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
              >
                {ref.source}
                <ExternalLink size={12} className="flex-shrink-0" />
              </a>
              {ref.title && (
                <span className="text-text-secondary"> — {ref.title}</span>
              )}
              {ref.year && (
                <span className="text-text-muted"> ({ref.year})</span>
              )}
            </li>
          );
        })}
      </ul>
    </ResultSection>
  );
}
