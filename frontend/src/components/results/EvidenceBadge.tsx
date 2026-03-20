import { Badge } from "@/components/ui/Badge";
import type { EvidencedClaim } from "@/lib/types";

interface EvidenceBadgeProps {
  claim: EvidencedClaim;
  compact?: boolean;
}

export function EvidenceBadge({ claim, compact = false }: EvidenceBadgeProps) {
  const variant =
    claim.confidence === "high"
      ? "success"
      : claim.confidence === "moderate"
        ? "warning"
        : "danger";

  if (compact) {
    return (
      <Badge variant={variant}>
        LOE {claim.loe} / COR {claim.cor}
      </Badge>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 mt-1">
      <Badge variant={variant}>LOE {claim.loe}</Badge>
      <Badge variant={variant}>COR {claim.cor}</Badge>
      <span className="text-xs text-text-muted">
        {claim.source}
        {claim.source_year ? ` (${claim.source_year})` : ""}
      </span>
    </div>
  );
}
