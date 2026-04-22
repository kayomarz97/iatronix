"use client";

import { useState } from "react";
import { Wind, Activity } from "lucide-react";
import { SpirometryUploader } from "@/components/waves/SpirometryUploader";
import { EcgComingSoon } from "@/components/waves/EcgComingSoon";

type Tab = "spirometry" | "ecg";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "spirometry", label: "Spirometry", icon: <Wind size={16} /> },
  { id: "ecg", label: "ECG", icon: <Activity size={16} /> },
];

export default function WavesPage() {
  const [activeTab, setActiveTab] = useState<Tab>("spirometry");

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "2rem 1.25rem 4rem" }}>
      {/* Header */}
      <div style={{ marginBottom: "1.75rem" }}>
        <h1 style={{ margin: "0 0 0.4rem", fontSize: "1.75rem", fontWeight: 800, color: "var(--text-primary)" }}>
          Waves
        </h1>
        <p style={{ margin: 0, fontSize: "0.9rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
          Medical diagnostic tools powered by AI. Upload reports for structured clinical interpretation.
        </p>
      </div>

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          gap: "0.25rem",
          marginBottom: "1.5rem",
          background: "var(--bg-elevated)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)",
          padding: "4px",
          width: "fit-content",
        }}
      >
        {TABS.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
                padding: "7px 16px",
                background: active ? "var(--accent)" : "transparent",
                color: active ? "#fff" : "var(--text-secondary)",
                border: "none",
                borderRadius: "var(--radius-md)",
                cursor: "pointer",
                fontSize: "0.875rem",
                fontWeight: active ? 600 : 500,
                transition: "all var(--transition)",
              }}
            >
              {tab.icon}
              {tab.label}
              {tab.id === "ecg" && (
                <span style={{ fontSize: "0.65rem", fontWeight: 600, padding: "1px 5px", background: "rgba(255,255,255,0.15)", borderRadius: 999, letterSpacing: "0.04em" }}>
                  SOON
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Content */}
      {activeTab === "spirometry" ? (
        <section>
          <div style={{ marginBottom: "1rem" }}>
            <h2 style={{ margin: "0 0 0.25rem", fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>
              Spirometry Interpretation
            </h2>
            <p style={{ margin: 0, fontSize: "0.825rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
              Upload a spirometry report image or PDF. Claude extracts FVC, FEV1, and ratio values, then applies ATS/ERS guidelines to produce a structured interpretation with severity grading and reversibility assessment.
            </p>
          </div>
          <SpirometryUploader />
        </section>
      ) : (
        <EcgComingSoon />
      )}
    </div>
  );
}
