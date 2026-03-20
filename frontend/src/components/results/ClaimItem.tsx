import type { EvidencedClaim } from "@/lib/types";
import { EvidenceBadge } from "./EvidenceBadge";

interface ClaimItemProps {
  claim: EvidencedClaim;
}

export function ClaimItem({ claim }: ClaimItemProps) {
  return (
    <div className="py-2 border-b border-border last:border-0">
      <p className="text-sm">{claim.value}</p>
      <EvidenceBadge claim={claim} />
    </div>
  );
}
