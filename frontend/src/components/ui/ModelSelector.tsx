"use client";

import { useModelSelection } from "@/hooks/useModelSelection";

export function ModelSelector() {
  const { models, selectedModel, selectModel, mounted } = useModelSelection();

  if (!mounted) return null;

  return (
    <select
      value={selectedModel}
      onChange={(e) => selectModel(e.target.value)}
      className="px-3 py-2 rounded-md border border-border bg-surface text-text text-sm min-h-[44px]"
    >
      {models.map((m) => (
        <option key={m.id} value={m.id}>
          {m.name}
        </option>
      ))}
    </select>
  );
}
