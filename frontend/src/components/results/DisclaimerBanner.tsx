interface DisclaimerBannerProps {
  disclaimer: string;
  safetyWarnings: string[];
  validationWarnings: string[];
}

export function DisclaimerBanner({
  disclaimer,
  safetyWarnings,
  validationWarnings,
}: DisclaimerBannerProps) {
  if (
    safetyWarnings.length === 0 &&
    validationWarnings.length === 0 &&
    !disclaimer
  ) {
    return null;
  }

  return (
    <div className="space-y-3 rounded-[24px] border border-border/80 bg-surface/90 p-4 shadow-[0_16px_36px_rgba(2,8,23,0.12)]">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
          Evidence and Safety Notes
        </p>
        <p className="mt-1 text-sm text-text-secondary">
          Review these caveats after the main answer, especially before acting on dose, indication, or risk information.
        </p>
      </div>

      {safetyWarnings.length > 0 && (
        <div className="rounded-2xl border border-danger/20 bg-danger-bg/40 p-4 text-sm">
          <p className="mb-2 font-medium text-danger">Safety Warnings</p>
          <ul className="list-disc space-y-1 pl-5 text-danger">
            {safetyWarnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {validationWarnings.length > 0 && (
        <div className="rounded-2xl border border-warning/20 bg-warning-bg/40 p-4 text-sm">
          <p className="mb-2 font-medium text-warning">Evidence Warnings</p>
          <ul className="list-disc space-y-1 pl-5 text-warning">
            {validationWarnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {disclaimer && (
        <div className="rounded-2xl border border-border bg-background/70 p-4 text-xs leading-6 text-text-muted">
          {disclaimer}
        </div>
      )}
    </div>
  );
}
