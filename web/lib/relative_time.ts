// I-f14-003 — relative-time formatter for cross-session surfacing.

export function formatRelative(
  iso: string,
  nowMs: number = Date.now(),
): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "unknown";
  const ms = Math.max(0, nowMs - then);
  const day = 24 * 60 * 60 * 1000;
  const days = Math.floor(ms / day);
  if (days < 1) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  if (days === 7) return "last week";
  if (days < 14) return `${days} days ago`;
  if (days < 30) return `${Math.floor(days / 7)} weeks ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1 month ago" : `${months} months ago`;
}
