"use client";

import { useEffect, useRef } from "react";
import mermaid from "mermaid";

export function MermaidClient({ chart }: { chart: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current && chart) {
      mermaid.contentLoaded();
      (async () => {
        try {
          const { svg } = await mermaid.render("mermaid-diagram", chart);
          if (containerRef.current) {
            containerRef.current.innerHTML = svg;
          }
        } catch (e) {
          if (containerRef.current) {
            containerRef.current.innerHTML = `<div class="text-red-500 text-sm">Chart render failed</div>`;
          }
        }
      })();
    }
  }, [chart]);

  return <div ref={containerRef} className="mermaid overflow-auto" />;
}
