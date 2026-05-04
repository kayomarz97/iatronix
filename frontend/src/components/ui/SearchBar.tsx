"use client";

import { useState, type FormEvent } from "react";
import { Search } from "lucide-react";

interface SearchBarProps {
  onSubmit: (query: string) => void;
  isLoading?: boolean;
  initialValue?: string;
}

export function SearchBar({
  onSubmit,
  isLoading = false,
  initialValue = "",
}: SearchBarProps) {
  const [query, setQuery] = useState(initialValue);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (query.trim() && !isLoading) {
      onSubmit(query.trim());
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Ask about drugs, diseases, or compare treatments..."
        className="flex-1 px-4 py-3 rounded-lg border border-border bg-surface text-text placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary-light min-h-[44px]"
        disabled={isLoading}
      />
      <button
        type="submit"
        disabled={isLoading || !query.trim()}
        className="px-6 py-3 bg-primary text-white rounded-lg font-medium hover:bg-primary-dark disabled:opacity-50 transition-colors min-h-[44px] flex items-center justify-center whitespace-nowrap"
      >
        <span className="hidden sm:inline">{isLoading ? "..." : "Search"}</span>
        <Search size={18} className="sm:hidden" />
      </button>
    </form>
  );
}
