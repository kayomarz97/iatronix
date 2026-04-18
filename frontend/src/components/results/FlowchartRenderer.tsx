"use client";

import React from "react";
import { ResultSection } from "./ResultChrome";
import { MermaidRenderer } from "./MermaidRenderer";

interface FlowchartRendererProps {
  flowcharts?: { title: string; steps: string[] }[];
}

function stepsToMermaid(steps: string[]): string {
  const nodes = steps.map((s, i) => `  S${i}["${s.replace(/"/g, "'")}"]`).join("\n");
  const edges = steps.slice(1).map((_, i) => `  S${i} --> S${i + 1}`).join("\n");
  return `flowchart TD\n${nodes}\n${edges}`;
}

export function FlowchartRenderer({ flowcharts }: FlowchartRendererProps) {
  if (!flowcharts || flowcharts.length === 0) return null;

  return (
    <ResultSection title="Clinical Pathways" eyebrow="Flowchart">
      <div className="flex flex-col gap-8">
        {flowcharts.map((flowchart, fIdx) => (
          <div key={fIdx} className="flex flex-col items-center">
            {flowchart.title && (
              <h4 className="mb-4 text-center font-semibold text-text-secondary">
                {flowchart.title}
              </h4>
            )}
            <MermaidRenderer chart={stepsToMermaid(flowchart.steps)} />
          </div>
        ))}
      </div>
    </ResultSection>
  );
}
