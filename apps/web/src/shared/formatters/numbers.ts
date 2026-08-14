export function formatKrw(value: number | null | undefined): string {
  if (value == null) return "-";
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value)}원`;
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: digits }).format(value);
}

export function formatPct(value: number | null | undefined, signed = false): string {
  if (value == null || !Number.isFinite(value)) return "-";
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${formatNumber(value, 2)}%`;
}

export function formatRatioPct(value: number | null | undefined): string {
  return value == null ? "-" : formatPct(value * 100);
}

export function toneFor(value: number | null | undefined): "positive" | "negative" | "neutral" {
  if (value == null || value === 0) return "neutral";
  return value > 0 ? "positive" : "negative";
}
