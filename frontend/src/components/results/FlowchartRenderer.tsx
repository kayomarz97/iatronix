"use client";

import React from "react";
import { ResultSection } from "./ResultChrome";
import { ArrowDown } from "lucide-react";

interface FlowchartRendererProps {
  flowcharts?: { title: string; steps: string[] }[];
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
            <div className="flex flex-col items-center">
              {flowchart.steps.map((step, sIdx) => (
                <React.Fragment key={sIdx}>
                  <div className="max-w-md rounded-xl border border-secondary bg-background/50 px-5 py-3 text-center text-sm shadow-sm backdrop-blur-sm transition-all hover:border-primary/50">
                    {step}
                  </div>
                  {sIdx < flowchart.steps.length - 1 && (
                    <div className="flex h-6 flex-col items-center justify-center my-1 text-muted-foreground">
                      <div className="h-full w-px bg-border"></div>
                      <ArrowDown size={14} className="text-border -mt-1" />
                    </div>
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>
        ))}
      </div>
    </ResultSection>
  );
}
