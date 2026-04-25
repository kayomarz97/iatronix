"use client";

import React from "react";
import { ResultSection } from "./ResultChrome";
import type { AdaptiveFlowchart, FlowchartStep } from "@/lib/types";

interface FlowchartRendererProps {
  flowcharts?: AdaptiveFlowchart[];
}

// ── Palette ───────────────────────────────────────────────────────────────────
const C = {
  start:    { bg: "#1e3a5f", border: "#3b82f6", text: "#93c5fd", label: "#60a5fa" },
  end:      { bg: "#0f2d2d", border: "#22d3ee", text: "#67e8f9", label: "#22d3ee" },
  action:   { bg: "#1a2035", border: "#4f6aff40", text: "#e2e8f0", label: "#818cf8" },
  decision: { bg: "#2d1f00", border: "#f59e0b60", text: "#fcd34d", label: "#f59e0b" },
  branch:   ["#10b981", "#f59e0b", "#ef4444", "#a78bfa", "#06b6d4"],
};

// ── Connector arrow ───────────────────────────────────────────────────────────
function Arrow({ color = "#4b5563" }: { color?: string }) {
  return (
    <div className="flex flex-col items-center my-0" aria-hidden>
      <div className="w-[2px] h-5" style={{ background: color }} />
      <svg width="12" height="8" viewBox="0 0 12 8" fill="none">
        <path d="M6 8L0 0h12L6 8z" fill={color} />
      </svg>
    </div>
  );
}

// ── START / END terminal ──────────────────────────────────────────────────────
function TerminalNode({ step, variant }: { step: FlowchartStep; variant: "start" | "end" }) {
  const colors = variant === "start" ? C.start : C.end;
  return (
    <div
      className="w-full rounded-full px-6 py-2.5 text-center text-sm font-bold tracking-wide border"
      style={{
        background: colors.bg,
        borderColor: colors.border,
        color: colors.text,
        boxShadow: `0 0 12px ${colors.border}40`,
      }}
    >
      {step.label && (
        <span className="mr-2 text-[10px] uppercase tracking-widest opacity-70">{step.label}</span>
      )}
      {step.text}
    </div>
  );
}

// ── Decision diamond ──────────────────────────────────────────────────────────
function DecisionNode({ step }: { step: FlowchartStep }) {
  const branches = step.branches ?? [];
  return (
    <div className="w-full flex flex-col items-center gap-0">
      {/* Diamond shape via CSS clip */}
      <div
        className="w-full max-w-[480px] px-8 py-4 text-sm font-semibold text-center border-2 rounded-lg relative"
        style={{
          background: C.decision.bg,
          borderColor: C.decision.border,
          color: C.decision.text,
        }}
      >
        {/* Diamond icon left */}
        <span className="absolute left-3 top-1/2 -translate-y-1/2 opacity-70">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <polygon points="8,1 15,8 8,15 1,8" fill={C.decision.label} />
          </svg>
        </span>
        {step.label && (
          <div className="text-[10px] font-bold uppercase tracking-widest mb-1 opacity-60" style={{ color: C.decision.label }}>
            {step.label}
          </div>
        )}
        {step.text}
      </div>

      {/* Branch outcomes */}
      {branches.length > 0 && (
        <div className="w-full mt-3">
          {/* Horizontal T-bar connector */}
          <div className="flex justify-center mb-0">
            <div className="w-[2px] h-3" style={{ background: C.decision.border }} />
          </div>
          <div
            className="grid gap-3 w-full"
            style={{ gridTemplateColumns: `repeat(${Math.min(branches.length, 3)}, 1fr)` }}
          >
            {branches.map((branch, bIdx) => {
              const color = C.branch[bIdx % C.branch.length];
              return (
                <div key={bIdx} className="flex flex-col items-center gap-1">
                  {/* Condition label pill */}
                  <div
                    className="rounded-full px-3 py-1 text-[11px] font-bold tracking-wide border text-center w-full"
                    style={{ background: `${color}18`, borderColor: `${color}50`, color }}
                  >
                    {branch.condition}
                  </div>
                  {/* Down arrow */}
                  <div className="flex flex-col items-center">
                    <div className="w-[2px] h-3" style={{ background: color }} />
                    <svg width="10" height="7" viewBox="0 0 10 7" fill="none">
                      <path d="M5 7L0 0h10L5 7z" fill={color} />
                    </svg>
                  </div>
                  {/* Outcome box */}
                  <div
                    className="w-full rounded-lg px-3 py-2.5 text-xs text-center border leading-snug"
                    style={{
                      background: `${color}12`,
                      borderColor: `${color}35`,
                      color: "var(--text-primary)",
                    }}
                  >
                    {branch.outcome}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Action box ────────────────────────────────────────────────────────────────
function ActionNode({ step }: { step: FlowchartStep }) {
  return (
    <div
      className="w-full rounded-xl px-5 py-3.5 text-sm border leading-snug"
      style={{
        background: C.action.bg,
        borderColor: C.action.border,
        color: C.action.text,
      }}
    >
      {step.label && (
        <div
          className="text-[10px] font-bold uppercase tracking-widest mb-1.5"
          style={{ color: C.action.label }}
        >
          {step.label}
        </div>
      )}
      <span>{step.text}</span>
    </div>
  );
}

// ── Single step dispatcher ────────────────────────────────────────────────────
function FlowStep({
  step,
  index,
  total,
  showArrowAfter,
}: {
  step: FlowchartStep;
  index: number;
  total: number;
  showArrowAfter: boolean;
}) {
  const isFirst = index === 0;
  const isLast = index === total - 1;

  const arrowColor = step.is_decision
    ? C.decision.border
    : isFirst
    ? C.start.border
    : isLast
    ? C.end.border
    : "#4b5563";

  return (
    <>
      {isFirst ? (
        <TerminalNode step={step} variant="start" />
      ) : isLast ? (
        <TerminalNode step={step} variant="end" />
      ) : step.is_decision ? (
        <DecisionNode step={step} />
      ) : (
        <ActionNode step={step} />
      )}
      {showArrowAfter && <Arrow color={arrowColor} />}
    </>
  );
}

// ── Public component ──────────────────────────────────────────────────────────
export function FlowchartRenderer({ flowcharts }: FlowchartRendererProps) {
  if (!flowcharts || flowcharts.length === 0) return null;

  const valid = flowcharts.filter(fc => fc.steps && fc.steps.length > 0);
  if (valid.length === 0) return null;

  return (
    <ResultSection title="Clinical Pathways" eyebrow="Flowchart">
      <div className="flex flex-col gap-10">
        {valid.map((flowchart, fIdx) => (
          <div key={fIdx} id={`fc-${fIdx}`}>
            {flowchart.title && (
              <div className="flex items-center gap-2 mb-5">
                <div
                  className="h-5 w-1 rounded-full shrink-0"
                  style={{ background: "linear-gradient(to bottom, #818CF8, #22D3EE)" }}
                />
                <h4 className="font-semibold text-base" style={{ color: "var(--text-primary)" }}>
                  {flowchart.title}
                </h4>
              </div>
            )}

            {/* Flow column — centered, full available width */}
            <div className="flex flex-col items-stretch w-full">
              {flowchart.steps.map((step, sIdx) => (
                <FlowStep
                  key={sIdx}
                  step={step}
                  index={sIdx}
                  total={flowchart.steps.length}
                  showArrowAfter={sIdx < flowchart.steps.length - 1}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </ResultSection>
  );
}
