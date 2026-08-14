export type Availability =
  | "AVAILABLE"
  | "PARTIAL"
  | "UNAVAILABLE"
  | "STALE"
  | "NO_DATA"
  | "ERROR";

export interface Provenance {
  source: string;
  generated_at?: string | null;
  as_of?: string | null;
  sample_count?: number | null;
  coverage?: number | null;
}

export interface MetricValue {
  value: number | null;
  unit: string;
  status: Availability;
  cost_basis: string;
  provenance: Provenance;
  reason?: string | null;
}

export interface PerformanceCounts {
  trade_count: number;
  resolved_count: number;
  unresolved_count: number;
  win_count: number;
  loss_count: number;
  flat_count: number;
}

export interface PerformanceSummary {
  status: Availability;
  start_date: string;
  end_date: string;
  generated_at: string;
  cost_basis: string;
  counts: PerformanceCounts;
  win_rate: MetricValue;
  average_trade_return: MetricValue;
  average_gain: MetricValue;
  average_loss: MetricValue;
  realized_pnl: MetricValue;
  gross_pnl: MetricValue;
  total_cost: MetricValue;
  cost_drag: MetricValue;
  profit_factor: MetricValue;
  max_drawdown: MetricValue;
  source_day_count: number;
  invalid_source_day_count: number;
  provenance: Provenance;
}

export interface Portfolio {
  status: Availability;
  day: string;
  generated_at: string;
  authority: string;
  position_count: number;
  positions: Array<{
    symbol: string;
    symbol_name: string | null;
    quantity: number;
    average_price: number | null;
    current_price: number | null;
    market_value: number | null;
    unrealized_pnl: number | null;
    unrealized_return_ratio: number | null;
    lifecycle_status: string | null;
    overnight_action: string | null;
  }>;
  total_market_value: MetricValue;
  total_unrealized_pnl: MetricValue;
  open_order_count: MetricValue;
  reconciliation_available: boolean;
  provenance: Provenance;
  issues: string[];
}

export interface Overview {
  status: Availability;
  day: string;
  generated_at: string;
  mode: string;
  read_only: boolean;
  performance: PerformanceSummary;
  portfolio: Portfolio;
  issues: string[];
}
