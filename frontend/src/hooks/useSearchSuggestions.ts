"use client";

import { useState, useEffect, useRef } from "react";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";

export function useSearchSuggestions(query: string) {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (query.trim().length < 2) {
      setSuggestions([]);
      return;
    }

    // Debounce 200ms
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      // Abort previous request
      if (abortRef.current) abortRef.current.abort();
      abortRef.current = new AbortController();

      setLoading(true);
      try {
        const authToken = localStorage.getItem(API_KEY_STORAGE_KEY) ?? "";
        const headers: HeadersInit = authToken ? { Authorization: `Bearer ${authToken}` } : {};
        const res = await fetch(`/api/suggestions?q=${encodeURIComponent(query.trim())}`, {
          headers,
          signal: abortRef.current.signal,
        });
        if (res.ok) {
          const data = await res.json();
          setSuggestions(data.suggestions ?? []);
        }
      } catch (e) {
        if (e instanceof Error && e.name !== "AbortError") {
          setSuggestions([]);
        }
      } finally {
        setLoading(false);
      }
    }, 200);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [query]);

  const clear = () => setSuggestions([]);

  return { suggestions, loading, clear };
}
