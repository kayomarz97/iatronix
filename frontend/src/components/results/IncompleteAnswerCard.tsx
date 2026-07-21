"use client";

import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { KeyRound } from "lucide-react";

/**
 * Shown when a query returns without a complete answer — most commonly because
 * the user has no valid LLM API key (the app is BYOK), but also for a transient
 * incomplete generation. Replaces what used to be a hard white-screen crash when
 * the adaptive response lacked a `bluf`.
 */
export function IncompleteAnswerCard({ onRetry }: { onRetry?: () => void }) {
  return (
    <Card variant="degraded">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 text-accent" aria-hidden>
          <KeyRound size={22} />
        </span>
        <div className="space-y-2">
          <p className="font-semibold text-text-primary">We couldn&apos;t complete this answer</p>
          <p className="text-sm text-text-secondary">
            Iatronix runs on <strong>your own LLM API key</strong>. If you haven&apos;t added one
            yet — or it&apos;s expired or out of credit — the model can&apos;t generate a full
            response. Add or update your key in Settings, then try again.
          </p>
          <p className="text-sm text-text-secondary">
            If your key is already set, the model likely returned an incomplete response this time —
            please retry.
          </p>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Link
              href="/settings"
              className="inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-1.5 text-sm font-semibold text-white no-underline"
            >
              <KeyRound size={15} /> Open Settings
            </Link>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center rounded-full border border-border px-4 py-1.5 text-sm font-medium text-text-secondary"
              >
                Try again
              </button>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
