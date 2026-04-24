"use client";

import React from "react";
import { ResultSection } from "./ResultChrome";
import type { AdaptiveFlowchart, FlowchartStep } from "@/lib/types";

interface FlowchartRendererProps {
  flowcharts?: AdaptiveFlowchart[];
}

// ── Colors ───────────────────────────────────────────────────────────────────
const COLORS = {
  first:    "#818CF8",
  last:     "#22D3EE",
  decision: "#f59e0b",
  normal:   "#3b82f6",
  branch:   ["#10b981", "#f59e0b", "#ef4444", "#a78bfa"],
};

// ── Step number circle ────────────────────────────────────────────────────────
function StepCircle({ index, color }: { index: number; color: string }) {
  return (
    <div
      className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white z-10"
      style={{ background: color, boxShadow: `0 0 0 3px ${color}33` }}
    >
      {index + 1}
    </div>
  );
}

// ── Diamond decision node ─────────────────────────────────────────────────────
function DecisionNode({
  step,
  index,
  isLast,
}: {
  step: FlowchartStep;
  index: number;
  isLast: boolean;
}) {
  const branches = step.branches ?? [];

  return (
    <div className="relative flex gap-3 items-start">
      {!isLast && (
        <div
          className="absolute left-3.5 top-7 bottom-0 w-[1.5px]"
          style={{ background: "linear-gradient(to bottom, #f59e0b80, transparent)", transform: "translateX(-50%)" }}
        />
      )}
      <StepCircle index={index} color={COLORS.decision} />
      <div className="flex-1 mb-3">
        {/* Diamond node */}
        <div
          className="rounded-xl px-3.5 py-2.5 text-sm border mb-3"
          style={{ background: "var(--bg-elevated)", borderColor: "#f59e0b60" }}
        >
          {step.label && (
            <div className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: "#f59e0b" }}>
              {step.label}
            </div>
          )}
          {/* Diamond icon */}
          <div className="flex items-center gap-2">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="flex-shrink-0">
              <polygon points="7,1 13,7 7,13 1,7" fill="#f59e0b" opacity="0.9" />
            </svg>
            <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{step.text}</span>
          </div>
        </div>

        {/* Branches */}
        {branches.length > 0 && (
          <div className="flex flex-col gap-2 pl-3 border-l-2" style={{ borderColor: "#f59e0b40" }}>
            {branches.map((branch, bIdx) => {
              const color = COLORS.branch[bIdx % COLORS.branch.length];
              return (
                <div key={bIdx} className="flex items-start gap-2">
                  {/* Branch arrow label */}
                  <div
                    className="flex-shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap"
                    style={{ background: `${color}20`, color, border: `1px solid ${color}40` }}
                  >
                    {branch.condition}
                  </div>
                  {/* Arrow */}
                  <span className="flex-shrink-0 text-[var(--text-muted)] mt-0.5">→</span>
                  {/* Outcome pill */}
                  <div
                    className="rounded-lg px-2.5 py-1 text-xs"
                    style={{ background: "var(--bg-elevated)", border: `1px solid ${color}30`, color: "var(--text-primary)" }}
                  >
                    {branch.outcome}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Linear action step ────────────────────────────────────────────────────────
function ActionStep({
  step,
  index,
  isFirst,
  isLast,
}: {
  step: FlowchartStep;
  index: number;
  isFirst: boolean;
  isLast: boolean;
}) {
  const color = isFirst ? COLORS.first : isLast ? COLORS.last : COLORS.normal;

  return (
    <div className="relative flex gap-3 items-start">
      {!isLast && (
        <div
          className="absolute left-3.5 top-7 bottom-0 w-[1.5px]"
          style={{ background: `linear-gradient(to bottom, ${color}80, transparent)`, transform: "translateX(-50%)" }}
        />
      )}
      <StepCircle index={index} color={color} />
      <div
        className="flex-1 mb-3 rounded-xl px-3.5 py-2.5 text-sm border"
        style={{ background: "var(--bg-elevated)", borderColor: "var(--border)" }}
      >
        {step.label && (
          <div className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color }}>
            {step.label}
          </div>
        )}
        <span style={{ color: "var(--text-primary)" }}>{step.text}</span>
      </div>
    </div>
  );
}

// ── Single flowchart step dispatcher ─────────────────────────────────────────
function FlowStep({ step, index, total }: { step: FlowchartStep; index: number; total: number }) {
  const isFirst = index === 0;
  const isLast = index === total - 1;

  if (step.is_decision) {
    return <DecisionNode step={step} index={index} isLast={isLast} />;
  }
  return <ActionStep step={step} index={index} isFirst={isFirst} isLast={isLast} />;
}

// ── Public component ──────────────────────────────────────────────────────────
export function FlowchartRenderer({ flowcharts }: FlowchartRendererProps) {
  if (!flowcharts || flowcharts.length === 0) return null;

  // Filter out flowcharts with empty steps
  const valid = flowcharts.filter(fc => fc.steps && fc.steps.length > 0);
  if (valid.length === 0) return null;

  return (
    <ResultSection title="Clinical Pathways" eyebrow="Flowchart">
      <div className="flex flex-col gap-8">
        {valid.map((flowchart, fIdx) => (
          <div key={fIdx} id={`fc-${fIdx}`}>
            {flowchart.title && (
              <div className="flex items-center gap-2 mb-4">
                <div className="w-2 h-2 rounded-sm flex-shrink-0" style={{ background: "#818CF8" }} />
                <h4 className="font-semibold" style={{ color: "var(--text-primary)" }}>{flowchart.title}</h4>
              </div>
            )}
            <div className="pl-1">
              {flowchart.steps.map((step, sIdx) => (
                <FlowStep key={sIdx} step={step} index={sIdx} total={flowchart.steps.length} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </ResultSection>
  );
}
