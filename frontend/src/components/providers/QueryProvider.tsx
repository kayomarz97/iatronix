"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { submitQuery as apiSubmitQuery } from "@/lib/api";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";
import { useModelSelection } from "@/hooks/useModelSelection";
import type { QueryResponse } from "@/lib/types";

interface QueryContextType {
  result: QueryResponse | null;
  isLoading: boolean;
  error: string | null;
  submitQuery: (query: string) => Promise<void>;
  clearResult: () => void;
}

const QueryContext = createContext<QueryContextType | null>(null);

export function QueryProvider({ children }: { children: ReactNode }) {
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { selectedModel } = useModelSelection();

  const submitQuery = useCallback(
    async (query: string) => {
      const apiKey = localStorage.getItem(API_KEY_STORAGE_KEY);
      if (!apiKey) {
        setError("Please set your API key in the header");
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        const response = await apiSubmitQuery(query, selectedModel, apiKey);
        setResult(response);
      } catch (err) {
        setError(err instanceof Error ? err.message : "An error occurred");
      } finally {
        setIsLoading(false);
      }
    },
    [selectedModel]
  );

  const clearResult = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  return (
    <QueryContext.Provider
      value={{ result, isLoading, error, submitQuery, clearResult }}
    >
      {children}
    </QueryContext.Provider>
  );
}

export function useQueryContext() {
  const ctx = useContext(QueryContext);
  if (!ctx) throw new Error("useQueryContext must be inside QueryProvider");
  return ctx;
}
