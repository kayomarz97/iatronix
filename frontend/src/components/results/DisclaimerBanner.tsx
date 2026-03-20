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
  return (
    <div className="space-y-2">
      {safetyWarnings.length > 0 && (
        <div className="p-3 rounded-lg bg-danger-bg border border-danger/30 text-sm">
          <p className="font-medium text-danger mb-1">Safety Warnings</p>
          <ul className="list-disc list-inside text-danger space-y-1">
            {safetyWarnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {validationWarnings.length > 0 && (
        <div className="p-3 rounded-lg bg-warning-bg border border-warning/30 text-sm">
          <p className="font-medium text-warning mb-1">Evidence Warnings</p>
          <ul className="list-disc list-inside text-warning space-y-1">
            {validationWarnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="p-3 rounded-lg bg-surface-alt border border-border text-xs text-text-muted">
        {disclaimer}
      </div>
    </div>
  );
}
