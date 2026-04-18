"use client";
import React from "react";

const STEPS = [
  { key: "classifying", label: "Classifying query" },
  { key: "fetching", label: "Fetching medical data" },
  { key: "generating", label: "Generating answer" },
  { key: "verifying", label: "Verifying citations" },
] as const;

type Step = (typeof STEPS)[number]["key"];

interface LoadingScreenProps {
  currentStep: Step;
}

export const LoadingScreen: React.FC<LoadingScreenProps> = ({ currentStep }) => {
  const currentIndex = STEPS.findIndex((s) => s.key === currentStep);

  return (
    <div style={{ padding: "2rem", maxWidth: 400, margin: "0 auto" }}>
      <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {STEPS.map((step, i) => {
          const done = i < currentIndex;
          const active = i === currentIndex;
          return (
            <li
              key={step.key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
                padding: "0.5rem 0",
                opacity: done || active ? 1 : 0.35,
              }}
            >
              <span
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: "50%",
                  border: `2px solid ${done ? "#22c55e" : active ? "#3b82f6" : "#6b7280"}`,
                  background: done ? "#22c55e" : "transparent",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                  fontSize: "0.75rem",
                  color: done ? "#fff" : active ? "#3b82f6" : "#6b7280",
                  fontWeight: "bold",
                }}
              >
                {done ? "✓" : i + 1}
              </span>
              <span
                style={{
                  fontSize: "0.95rem",
                  color: active ? "#3b82f6" : done ? "#22c55e" : "#6b7280",
                  fontWeight: active ? 600 : 400,
                }}
              >
                {step.label}
                {active && (
                  <span
                    style={{
                      display: "inline-block",
                      marginLeft: "0.25rem",
                      animation: "pulse 1.4s ease-in-out infinite",
                    }}
                  >
                    …
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
};
