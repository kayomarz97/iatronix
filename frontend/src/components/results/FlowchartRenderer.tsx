"use client";

import React from "react";
import { ResultSection } from "./ResultChrome";
import { MermaidRenderer } from "./MermaidRenderer";

interface FlowchartRendererProps {
  flowcharts?: { title: string; steps: string[] }[];
}

const DECISION_RE = /\?$|^(?:if|is|are|does|do|can|should|has|have|check|assess|consider)\b/i;

function stepsToMermaid(steps: string[]): string {
  if (steps.length === 0) return "flowchart TD\n  A[No steps]";

  const lines: string[] = [];
  const sanitize = (s: string) => s.replace(/"/g, "'").replace(/[[\]{}]/g, "");

  let i = 0;
  while (i < steps.length) {
    const step = sanitize(steps[i]);
    const isDecision = DECISION_RE.test(step);
    const nodeId = `S${i}`;

    if (isDecision) {
      lines.push(`  ${nodeId}{{"${step}"}}`);
      // Next two steps become yes/no branches if they exist
      const yesStep = steps[i + 1] ? sanitize(steps[i + 1]) : null;
      const noStep = steps[i + 2] ? sanitize(steps[i + 2]) : null;
      if (yesStep) {
        lines.push(`  ${nodeId} -- Yes --> S${i + 1}["${yesStep}"]`);
      }
      if (noStep) {
        lines.push(`  ${nodeId} -- No --> S${i + 2}["${noStep}"]`);
      }
      // Skip the two branch steps since we've already added them inline
      if (yesStep && noStep) {
        i += 3;
        // Connect both branches to the next step if it exists
        if (steps[i]) {
          const nextId = `S${i}`;
          lines.push(`  S${i - 2} --> ${nextId}`);
          lines.push(`  S${i - 1} --> ${nextId}`);
        }
        continue;
      }
      i++;
      continue;
    }

    lines.push(`  ${nodeId}["${step}"]`);
    if (i > 0) {
      // Find the previous node that isn't already a branch target
      const prevIdx = i - 1;
      // Only add edge if previous step wasn't already connected via decision branch
      const prevWasDecision = DECISION_RE.test(sanitize(steps[prevIdx] ?? ""));
      if (!prevWasDecision) {
        lines.push(`  S${prevIdx} --> ${nodeId}`);
      }
    }
    i++;
  }

  return `flowchart TD\n${lines.join("\n")}`;
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
