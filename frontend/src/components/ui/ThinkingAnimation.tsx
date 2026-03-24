"use client";

import { useState, useEffect } from "react";

const MEDICAL_PHRASES = [
  "Analyzing pharmacokinetics...",
  "Checking dosing guidelines...",
  "Reviewing clinical trials...",
  "Consulting treatment protocols...",
  "Cross-referencing evidence...",
  "Evaluating safety profiles...",
  "Verifying drug interactions...",
  "Reviewing guideline recommendations...",
  "Analyzing mechanism of action...",
  "Checking contraindications...",
  "Consulting WHO classifications...",
  "Reviewing level of evidence...",
];

export function ThinkingAnimation() {
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setIndex((i) => (i + 1) % MEDICAL_PHRASES.length);
        setVisible(true);
      }, 300);
    }, 1800);
    return () => clearInterval(interval);
  }, []);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "1.25rem",
        padding: "3rem 1rem",
      }}
    >
      {/* Pulsing ring */}
      <div style={{ position: "relative", width: 56, height: 56 }}>
        <div
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: "50%",
            border: "2px solid var(--accent)",
            opacity: 0.3,
            animation: "ping 1.5s cubic-bezier(0,0,0.2,1) infinite",
          }}
        />
        <div
          style={{
            position: "absolute",
            inset: "6px",
            borderRadius: "50%",
            background: "var(--accent-glow)",
            border: "2px solid var(--accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg>
        </div>
      </div>

      {/* Rotating phrase */}
      <p
        style={{
          fontSize: "0.95rem",
          color: "var(--text-secondary)",
          fontWeight: 500,
          opacity: visible ? 1 : 0,
          transform: visible ? "translateY(0)" : "translateY(4px)",
          transition: "opacity 300ms ease, transform 300ms ease",
          minHeight: "1.5em",
          textAlign: "center",
        }}
      >
        {MEDICAL_PHRASES[index]}
      </p>

      {/* Three pulsing dots */}
      <div style={{ display: "flex", gap: "0.4rem" }}>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: "var(--accent)",
              display: "inline-block",
              animation: `pulse-dot 1.2s ease-in-out ${i * 0.2}s infinite`,
            }}
          />
        ))}
      </div>

      <style>{`
        @keyframes ping {
          75%, 100% { transform: scale(1.8); opacity: 0; }
        }
      `}</style>
    </div>
  );
}
