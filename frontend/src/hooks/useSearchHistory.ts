"use client";

import { useState, useCallback } from "react";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";

export interface HistoryItem {
  id: number;
  query_text: string;
  query_type: string | null;
  response_summary: string | null;
  created_at: string;
}

export function useSearchHistory() {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);

  const getApiKey = () =>
    typeof window !== "undefined"
      ? (localStorage.getItem(API_KEY_STORAGE_KEY) ?? "")
      : "";

  const fetchHistory = useCallback(async () => {
    const apiKey = getApiKey();
    if (!apiKey) return;
    setLoading(true);
    try {
      const res = await fetch("/api/history", {
        headers: { Authorization: `Bearer ${apiKey}` },
      });
      if (res.ok) setHistory(await res.json());
    } catch {
      /* silently fail */
    } finally {
      setLoading(false);
    }
  }, []);

  const clearHistory = useCallback(async () => {
    const apiKey = getApiKey();
    await fetch("/api/history", {
      method: "DELETE",
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    setHistory([]);
  }, []);

  const deleteItem = useCallback(async (id: number) => {
    const apiKey = getApiKey();
    await fetch(`/api/history/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    setHistory((prev) => prev.filter((h) => h.id !== id));
  }, []);

  return { history, loading, fetchHistory, clearHistory, deleteItem };
}
