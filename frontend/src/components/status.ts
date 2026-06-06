export function getStatusBadgeClass(label: string) {
  const normalized = label.toLowerCase();

  if (
    normalized.includes("critical") ||
    normalized.includes("failed") ||
    normalized.includes("rejected") ||
    normalized.includes("error") ||
    normalized.includes("abort")
  ) {
    return "border-severity-critical/45 bg-severity-critical/10 text-severity-critical";
  }

  if (normalized.includes("high")) {
    return "border-severity-high/45 bg-severity-high/10 text-severity-high";
  }

  if (normalized.includes("medium") || normalized.includes("pending") || normalized.includes("awaiting")) {
    return "border-severity-medium/45 bg-severity-medium/10 text-severity-medium";
  }

  if (
    normalized.includes("low") ||
    normalized.includes("passed") ||
    normalized.includes("connected") ||
    normalized.includes("complete") ||
    normalized.includes("submitted") ||
    normalized.includes("executed") ||
    normalized.includes("done")
  ) {
    return "border-severity-low/45 bg-severity-low/10 text-severity-low";
  }

  if (normalized.includes("open") || normalized.includes("approval") || normalized.includes("analysis")) {
    return "border-state-open/45 bg-state-open/10 text-state-open";
  }

  if (
    normalized.includes("idle") ||
    normalized.includes("draft") ||
    normalized.includes("not_run") ||
    normalized.includes("not requested") ||
    normalized.includes("incomplete") ||
    normalized.includes("disconnected")
  ) {
    return "border-state-neutral/45 bg-state-neutral/10 text-state-neutral";
  }

  return "border-border bg-background text-muted-foreground";
}
