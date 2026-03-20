export function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function confidenceColor(
  confidence: "high" | "moderate" | "low"
): string {
  switch (confidence) {
    case "high":
      return "text-evidence-high";
    case "moderate":
      return "text-evidence-moderate";
    case "low":
      return "text-evidence-low";
  }
}

export function severityColor(
  severity: "major" | "moderate" | "minor"
): string {
  switch (severity) {
    case "major":
      return "text-danger";
    case "moderate":
      return "text-warning";
    case "minor":
      return "text-text-muted";
  }
}
