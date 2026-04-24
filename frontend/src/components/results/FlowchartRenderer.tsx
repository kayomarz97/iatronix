"use client";

import React from "react";
import { ResultSection } from "./ResultChrome";

interface FlowchartRendererProps {
  flowcharts?: { title: string; steps: string[] }[];
}

function isBranchStep(step: string): boolean {
  return step.includes("→");
}

function StepCircle({ index, type }: { index: number; type: "first" | "last" | "branch" | "normal" }) {
  const colors = {
    first: "#818CF8",
    last: "#22D3EE",
    branch: "#f59e0b",
    normal: "#3b82f6",
  };
  const color = colors[type];
  return (
    <div
      className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white z-10"
      style={{ background: color, boxShadow: `0 0 0 3px ${color}33` }}
    >
      {index + 1}
    </div>
  );
}

function FlowStep({ step, index, total }: { step: string; index: number; total: number }) {
  const isFirst = index === 0;
  const isLast = index === total - 1;
  const isBranch = isBranchStep(step);
  const type = isFirst ? "first" : isLast ? "last" : isBranch ? "branch" : "normal";

  const parts = isBranch ? step.split("→").map(p => p.trim()) : null;

  return (
    <div className="relative flex gap-3 items-start">
      {/* Connector line */}
      {!isLast && (
        <div
          className="absolute left-3.5 top-7 bottom-0 w-[1.5px]"
          style={{
            background: "linear-gradient(to bottom, #3b82f680, transparent)",
            transform: "translateX(-50%)",
          }}
        />
      )}
      <StepCircle index={index} type={type} />
      <div
        className="flex-1 mb-3 rounded-xl px-3.5 py-2.5 text-sm border"
        style={{
          background: "var(--bg-elevated)",
          borderColor: type === "branch" ? "#f59e0b40" : "var(--border)",
        }}
      >
        {isBranch && parts ? (
          <div>
            <span className="font-medium" style={{ color: "#f59e0b" }}>{parts[0]}</span>
            <div className="mt-1 flex items-center gap-1.5 text-[var(--text-secondary)]">
              <span className="text-xs font-mono" style={{ color: "#f59e0b" }}>→</span>
              <span>{parts[1]}</span>
            </div>
          </div>
        ) : (
          <span className="text-[var(--text-primary)]">{step}</span>
        )}
      </div>
    </div>
  );
}

export function FlowchartRenderer({ flowcharts }: FlowchartRendererProps) {
  if (!flowcharts || flowcharts.length === 0) return null;

  return (
    <ResultSection title="Clinical Pathways" eyebrow="Flowchart">
      <div className="flex flex-col gap-8">
        {flowcharts.map((flowchart, fIdx) => (
          <div key={fIdx} id={`fc-${fIdx}`}>
            {flowchart.title && (
              <div className="flex items-center gap-2 mb-4">
                <div className="w-2 h-2 rounded-sm flex-shrink-0" style={{ background: "#818CF8" }} />
                <h4 className="font-semibold text-[var(--text-primary)]">{flowchart.title}</h4>
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
