"use client";

import { useState, useEffect } from "react";
import { DEFAULT_MODEL, MODEL_STORAGE_KEY } from "@/lib/constants";
import type { ModelInfo } from "@/lib/types";

const MODELS: ModelInfo[] = [
  {
    id: "claude-haiku-4-5-20251001",
    name: "Claude Haiku 4.5",
    provider: "anthropic",
    description: "Fast and efficient for drug lookups",
  },
  {
    id: "claude-sonnet-4-20250514",
    name: "Claude Sonnet 4",
    provider: "anthropic",
    description: "Balanced performance and speed",
  },
  {
    id: "claude-opus-4-20250514",
    name: "Claude Opus 4",
    provider: "anthropic",
    description: "Most capable, slower responses",
  },
];

export function useModelSelection() {
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const stored = localStorage.getItem(MODEL_STORAGE_KEY);
    if (stored) setSelectedModel(stored);
  }, []);

  const selectModel = (modelId: string) => {
    setSelectedModel(modelId);
    localStorage.setItem(MODEL_STORAGE_KEY, modelId);
  };

  return { models: MODELS, selectedModel, selectModel, mounted };
}
