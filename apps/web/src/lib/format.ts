/** The one duration format: "850ms", "39.4s", "41m 57s", "1h 12m", "3d 4h". */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const s = Math.floor(ms / 1000);
  const [d, h, m] = [Math.floor(s / 86_400), Math.floor(s / 3600) % 24, Math.floor(s / 60) % 60];
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m ${s % 60}s`;
}

const COMPACT = new Intl.NumberFormat("en", { notation: "compact", maximumSignificantDigits: 3 });

/** Large counts in compact notation ("1.04B"); pair with the exact value
 *  (`toLocaleString()`) on hover. */
export function formatCompact(n: number): string {
  return COMPACT.format(n);
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
