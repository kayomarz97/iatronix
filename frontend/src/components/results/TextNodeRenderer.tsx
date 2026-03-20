"use client";

import type { TextNode } from "@/lib/types";
import { useQueryContext } from "@/components/providers/QueryProvider";

interface TextNodeRendererProps {
  nodes: TextNode[];
}

export function TextNodeRenderer({ nodes }: TextNodeRendererProps) {
  const { submitQuery } = useQueryContext();

  if (nodes.length === 0) return null;

  return (
    <div className="text-sm leading-relaxed">
      {nodes.map((node, i) => {
        if (node.type === "drug_link" && node.drug_query) {
          return (
            <button
              key={i}
              onClick={() => submitQuery(node.drug_query!)}
              className="text-primary-light underline underline-offset-2 hover:text-primary cursor-pointer"
              title={`Query: ${node.drug_query}${node.match_score ? ` (${Math.round(node.match_score * 100)}% match)` : ""}`}
            >
              {node.content}
            </button>
          );
        }
        return <span key={i}>{node.content}</span>;
      })}
    </div>
  );
}
