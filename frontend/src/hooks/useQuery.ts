"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { submitQuery as apiSubmitQuery } from "@/lib/api";
import { useModelSelection } from "./useModelSelection";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";
import type { QueryResponse } from "@/lib/types";

export function useQuery() {
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { selectedModel } = useModelSelection();
  const router = useRouter();

  const submitQuery = useCallback(
    async (query: string) => {
      const apiKey = localStorage.getItem(API_KEY_STORAGE_KEY);
      if (!apiKey) {
        setError("Please set your API key first");
        return;
      }

      setIsLoading(true);
      setError(null);
      setResult(null);

      try {
        const response = await apiSubmitQuery(query, selectedModel, apiKey);
        setResult(response);
        router.push(`/query?q=${encodeURIComponent(query)}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "An error occurred");
      } finally {
        setIsLoading(false);
      }
    },
    [selectedModel, router]
  );

  return { result, isLoading, error, submitQuery, setResult, setError };
}
