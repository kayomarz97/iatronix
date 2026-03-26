"use client";

import { useState } from "react";
import type { EvidencedClaim } from "@/lib/types";

interface EvidenceBadgeProps {
  claim: EvidencedClaim;
}

export function EvidenceBadge({ claim }: EvidenceBadgeProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  const isLow = claim.confidence === "low";
  const dotColor =
    claim.confidence === "high"
      ? "bg-green-500"
      : claim.confidence === "moderate"
        ? "bg-amber-500"
        : "bg-red-500";

  return (
    <span
      className="relative inline-flex items-center ml-1 cursor-help"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      onTouchStart={() => setShowTooltip((v) => !v)}
    >
      <span className={`inline-block w-2 h-2 rounded-full ${dotColor}`} />

      {showTooltip && (
        <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 px-3 py-2 rounded-lg bg-gray-900 text-white text-xs whitespace-nowrap shadow-lg">
          <span className="block font-medium mb-0.5">
            LOE {claim.loe} &middot; COR {claim.cor} &middot;{" "}
            {claim.confidence}
          </span>
          <span className="block text-gray-300">
            {claim.source || "Unknown source"}
            {claim.source_year ? ` (${claim.source_year})` : ""}
          </span>
          <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
        </span>
      )}
    </span>
  );
}

export function EvidencedText({ claim }: { claim: EvidencedClaim }) {
  const isLow = claim.confidence === "low";
  return (
    <span className={isLow ? "bg-amber-50 dark:bg-amber-950/30 px-0.5 rounded" : ""}>
      {claim.value}
      <EvidenceBadge claim={claim} />
    </span>
  );
}
