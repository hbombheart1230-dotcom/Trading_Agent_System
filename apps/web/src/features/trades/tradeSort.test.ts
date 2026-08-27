import { describe, expect, it } from "vitest";

import { sortTrades } from "./tradeSort";
import type { TradeSummary } from "./types";

function trade(overrides: Partial<TradeSummary>): TradeSummary {
  return {
    trade_id: "trade",
    day: "2026-08-27",
    symbol: "005930",
    symbol_name: "삼성전자",
    themes: [],
    status: "closed",
    entry_time: "2026-08-27T00:10:00Z",
    exit_time: null,
    entry_price: 100,
    exit_price: 101,
    quantity: 1,
    hold_seconds: 60,
    realized_pnl_krw: 100,
    realized_return_pct: 1,
    result: "win",
    playbook: "pullback",
    tactic_id: null,
    strategy_horizon: "intraday",
    scanner_rank: 1,
    cost_basis: "MOCK_BROKER_NET",
    artifact_status: "AVAILABLE",
    artifact_scope: "full",
    ...overrides,
  };
}

describe("sortTrades", () => {
  it("sorts numeric values in both directions without mutating input", () => {
    const items = [
      trade({ trade_id: "middle", realized_return_pct: 0.2 }),
      trade({ trade_id: "high", realized_return_pct: 1.5 }),
      trade({ trade_id: "low", realized_return_pct: -0.7 }),
    ];

    expect(sortTrades(items, "realized_return_pct", "asc").map((item) => item.trade_id)).toEqual(["low", "middle", "high"]);
    expect(sortTrades(items, "realized_return_pct", "desc").map((item) => item.trade_id)).toEqual(["high", "middle", "low"]);
    expect(items.map((item) => item.trade_id)).toEqual(["middle", "high", "low"]);
  });

  it("keeps missing values last for either direction", () => {
    const items = [
      trade({ trade_id: "missing", scanner_rank: null }),
      trade({ trade_id: "rank2", scanner_rank: 2 }),
      trade({ trade_id: "rank1", scanner_rank: 1 }),
    ];

    expect(sortTrades(items, "scanner_rank", "asc").map((item) => item.trade_id)).toEqual(["rank1", "rank2", "missing"]);
    expect(sortTrades(items, "scanner_rank", "desc").map((item) => item.trade_id)).toEqual(["rank2", "rank1", "missing"]);
  });

  it("uses the original order as a deterministic tie breaker", () => {
    const items = [trade({ trade_id: "first" }), trade({ trade_id: "second" })];
    expect(sortTrades(items, "hold_seconds", "asc").map((item) => item.trade_id)).toEqual(["first", "second"]);
  });
});
