"use client";

import type { Reference } from "@/lib/types";
import { Accordion } from "@/components/ui/Accordion";
import { ExternalLink } from "lucide-react";

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
    <Accordion title="References" count={references.length}>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {references.map((ref, i) => {
          const safeUrl = ref.url && ref.url.startsWith("https://") ? ref.url : null;
          const url = safeUrl || buildFallbackUrl(ref);
          return (
            <li key={i} style={{ fontSize: "0.8rem", lineHeight: 1.5 }}>
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  color: "var(--accent)",
                  textDecoration: "none",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.3rem",
                  fontWeight: 500,
                }}
                onMouseOver={(e) => (e.currentTarget.style.textDecoration = "underline")}
                onMouseOut={(e) => (e.currentTarget.style.textDecoration = "none")}
              >
                {ref.source}
                <ExternalLink size={11} style={{ flexShrink: 0 }} />
              </a>
              {ref.title && (
                <span style={{ color: "var(--text-secondary)" }}> — {ref.title}</span>
              )}
              {ref.year && (
                <span style={{ color: "var(--text-muted)" }}> ({ref.year})</span>
              )}
            </li>
          );
        })}
      </ul>
    </Accordion>
  );
}
