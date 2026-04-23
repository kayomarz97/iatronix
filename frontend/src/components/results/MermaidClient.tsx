"use client";

import { useEffect, useRef } from "react";
import mermaid from "mermaid";

let initialized = false;

function ensureMermaidInit() {
  if (initialized) return;
  initialized = true;
  mermaid.initialize({
    startOnLoad: false,
    theme: "base",
    themeVariables: {
      lineColor: "#94a3b8",
      primaryColor: "#1e293b",
      primaryTextColor: "#f1f5f9",
      primaryBorderColor: "#3b82f6",
      secondaryColor: "#0f172a",
      tertiaryColor: "#1e293b",
      edgeLabelBackground: "transparent",
      clusterBkg: "#0f172a",
    },
    flowchart: { curve: "basis", htmlLabels: true },
  });
}

export function MermaidClient({ chart }: { chart: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !chart) return;
    ensureMermaidInit();

    const id = `mermaid-${Math.random().toString(36).slice(2)}`;
    (async () => {
      try {
        const { svg } = await mermaid.render(id, chart);
        if (containerRef.current) {
          containerRef.current.innerHTML = svg;
          const svgEl = containerRef.current.querySelector("svg");
          if (svgEl) {
            svgEl.style.width = "100%";
            svgEl.style.height = "auto";
          }
        }
      } catch {
        if (containerRef.current) {
          containerRef.current.innerHTML = `<div style="color:var(--danger);font-size:0.8rem;padding:0.5rem;">Chart render failed</div>`;
        }
      }
    })();
  }, [chart]);

  return (
    <div
      style={{ overflowX: "auto", maxWidth: "100%", WebkitOverflowScrolling: "touch" as never }}
    >
      <div ref={containerRef} className="mermaid" style={{ minWidth: "min-content" }} />
    </div>
  );
}
