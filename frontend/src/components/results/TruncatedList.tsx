"use client";

import { useState, type ReactNode } from "react";
import { TRUNCATION_LIMIT } from "@/lib/constants";

interface TruncatedListProps<T> {
  items: T[];
  renderItem: (item: T, index: number) => ReactNode;
  limit?: number;
}

export function TruncatedList<T>({
  items,
  renderItem,
  limit = TRUNCATION_LIMIT,
}: TruncatedListProps<T>) {
  const [showAll, setShowAll] = useState(false);
  const displayed = showAll ? items : items.slice(0, limit);
  const hasMore = items.length > limit;

  return (
    <div className="space-y-2">
      {displayed.map((item, i) => renderItem(item, i))}
      {hasMore && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="text-sm text-primary-light hover:text-primary min-h-[44px]"
        >
          [Showing {limit} of {items.length}] Show all
        </button>
      )}
    </div>
  );
}
