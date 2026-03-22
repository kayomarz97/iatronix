import type { EvidencedClaim } from "@/lib/types";
import { EvidencedText } from "./EvidenceBadge";

interface ClaimItemProps {
  claim: EvidencedClaim;
}

export function ClaimItem({ claim }: ClaimItemProps) {
  return (
    <li className="py-1.5 text-sm leading-relaxed">
      <EvidencedText claim={claim} />
    </li>
  );
}
