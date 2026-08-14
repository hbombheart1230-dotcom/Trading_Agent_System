import type { Availability, PerformanceSummary, Provenance } from "../../shared/api/types";

export interface PerformancePoint {
  day: string;
  status: Availability;
  trade_count: number;
  sample_count: number;
  average_trade_return_pct: number | null;
  realized_pnl_krw: number | null;
  cumulative_realized_pnl_krw: number | null;
}

export interface PerformanceSeries {
  status: Availability;
  start_date: string;
  end_date: string;
  generated_at: string;
  cost_basis: string;
  series_kind: string;
  points: PerformancePoint[];
  provenance: Provenance;
}

export type { PerformanceSummary };
