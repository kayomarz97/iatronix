"use client";

import { useState, useEffect } from "react";
import { DEFAULT_MODEL, MODEL_STORAGE_KEY } from "@/lib/constants";
import type { ModelInfo } from "@/lib/types";

const MODELS: ModelInfo[] = [
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
  {
    id: "anthropic/claude-sonnet-4-20250514",
    name: "Claude Sonnet 4 (OpenRouter)",
    provider: "openrouter",
    description: "Claude Sonnet 4 via OpenRouter",
  },
  {
    id: "google/gemini-2.5-pro-preview",
    name: "Gemini 2.5 Pro (OpenRouter)",
    provider: "openrouter",
    description: "Google Gemini 2.5 Pro via OpenRouter",
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
