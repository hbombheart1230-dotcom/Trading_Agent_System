import type { TradeSummary } from "./types";

export type TradeSortKey =
  | "identity"
  | "entry_time"
  | "hold_seconds"
  | "strategy"
  | "scanner_rank"
  | "realized_pnl_krw"
  | "realized_return_pct"
  | "artifact_status";

export type SortDirection = "asc" | "desc";

const collator = new Intl.Collator("ko-KR", { numeric: true, sensitivity: "base" });

export function sortTrades(
  items: TradeSummary[],
  key: TradeSortKey,
  direction: SortDirection,
): TradeSummary[] {
  return items
    .map((trade, index) => ({ trade, index }))
    .sort((left, right) => {
      const leftValue = sortValue(left.trade, key);
      const rightValue = sortValue(right.trade, key);
      const nullOrder = compareNulls(leftValue, rightValue);
      if (nullOrder !== 0) return nullOrder;
      if (leftValue == null || rightValue == null) return left.index - right.index;

      const comparison = typeof leftValue === "number" && typeof rightValue === "number"
        ? leftValue - rightValue
        : collator.compare(String(leftValue), String(rightValue));
      return comparison === 0
        ? left.index - right.index
        : comparison * (direction === "asc" ? 1 : -1);
    })
    .map(({ trade }) => trade);
}

function sortValue(trade: TradeSummary, key: TradeSortKey): number | string | null {
  switch (key) {
    case "identity":
      return `${trade.day}|${trade.symbol_name ?? trade.symbol}|${trade.symbol}`;
    case "entry_time":
      return timestamp(trade.entry_time);
    case "hold_seconds":
      return finiteNumber(trade.hold_seconds);
    case "strategy":
      return trade.playbook ? `${trade.playbook}|${trade.strategy_horizon ?? ""}` : null;
    case "scanner_rank":
      return finiteNumber(trade.scanner_rank);
    case "realized_pnl_krw":
      return finiteNumber(trade.realized_pnl_krw);
    case "realized_return_pct":
      return finiteNumber(trade.realized_return_pct);
    case "artifact_status":
      return trade.artifact_status || null;
  }
}

function finiteNumber(value: number | null): number | null {
  return value != null && Number.isFinite(value) ? value : null;
}

function timestamp(value: string | null): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function compareNulls(left: number | string | null, right: number | string | null): number {
  if (left == null && right == null) return 0;
  if (left == null) return 1;
  if (right == null) return -1;
  return 0;
}
