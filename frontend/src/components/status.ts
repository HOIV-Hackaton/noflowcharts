export function getStatusBadgeClass(label: string) {
  const normalized = label.toLowerCase();

  if (
    normalized.includes("critical") ||
    normalized.includes("failed") ||
    normalized.includes("rejected") ||
    normalized.includes("error") ||
    normalized.includes("abort")
  ) {
    return "bg-accent-error-soft text-accent-error";
  }

  if (normalized.includes("high")) {
    return "bg-accent-error-soft text-accent-error";
  }

  if (normalized.includes("medium") || normalized.includes("pending") || normalized.includes("awaiting")) {
    return "bg-accent-pending-soft text-accent-pending-deep";
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
    return "bg-accent-success-soft text-accent-success-deep";
  }

  if (normalized.includes("open") || normalized.includes("approval") || normalized.includes("analysis")) {
    return "bg-accent-link-soft text-accent-link-deep";
  }

  if (
    normalized.includes("idle") ||
    normalized.includes("draft") ||
    normalized.includes("not_run") ||
    normalized.includes("not requested") ||
    normalized.includes("incomplete") ||
    normalized.includes("disconnected")
  ) {
    return "bg-muted text-muted-foreground";
  }

  return "bg-muted text-muted-foreground";
}
