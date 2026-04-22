"use client";

import { Activity } from "lucide-react";

export function EcgComingSoon() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "1rem",
        padding: "3rem 1.5rem",
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-lg)",
        textAlign: "center",
      }}
    >
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: "50%",
          background: "var(--accent-glow)",
          border: "1px solid rgba(59,130,246,0.3)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Activity size={24} color="var(--accent)" />
      </div>
      <div>
        <h3 style={{ margin: "0 0 0.4rem", fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>
          ECG Analysis
        </h3>
        <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.6, maxWidth: 380 }}>
          12-lead ECG interpretation with AI-assisted lead identification and deterministic diagnostic rules is coming soon.
          Upload a 12-lead ECG image and get structured findings with clinical significance ratings.
        </p>
      </div>
      <span
        style={{
          display: "inline-block",
          padding: "4px 12px",
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          borderRadius: 999,
          fontSize: "0.75rem",
          fontWeight: 600,
          color: "var(--text-muted)",
          letterSpacing: "0.04em",
        }}
      >
        COMING SOON
      </span>
    </div>
  );
}
