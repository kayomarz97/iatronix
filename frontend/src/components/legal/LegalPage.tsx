// Shared shell for /privacy and /terms so the two stay visually identical and
// only their content differs. Token-based styling only — no hardcoded chrome colours.

import type { ReactNode } from "react";

export function LegalPage({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: ReactNode;
}) {
  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "3rem 1.25rem 4rem" }}>
      <h1 style={{ fontSize: "2rem", fontWeight: 700, margin: "0 0 0.5rem", color: "var(--text-primary)" }}>
        {title}
      </h1>
      <p style={{ margin: "0 0 2rem", fontSize: "0.85rem", color: "var(--text-muted)" }}>
        Last updated {updated}
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>{children}</div>
    </div>
  );
}

export function Section({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section>
      <h2
        style={{
          fontSize: "1.05rem",
          fontWeight: 600,
          margin: "0 0 0.6rem",
          color: "var(--text-primary)",
        }}
      >
        {heading}
      </h2>
      <div
        style={{
          fontSize: "0.9rem",
          lineHeight: 1.65,
          color: "var(--text-secondary)",
          display: "flex",
          flexDirection: "column",
          gap: "0.6rem",
        }}
      >
        {children}
      </div>
    </section>
  );
}

export function Callout({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        padding: "0.9rem 1.1rem",
        background: "var(--accent-glow)",
        border: "1px solid rgba(59,130,246,0.3)",
        borderRadius: "var(--radius-md)",
        fontSize: "0.875rem",
        lineHeight: 1.6,
        color: "var(--text-secondary)",
      }}
    >
      {children}
    </div>
  );
}

export function Bullets({ items }: { items: ReactNode[] }) {
  return (
    <ul style={{ margin: 0, paddingLeft: "1.15rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  );
}
