import type { Availability, Provenance } from "../../shared/api/types";

export type StrategyDimension = "playbook" | "tactic" | "setup" | "horizon" | "theme";

export interface StrategyPerformance {
  status: Availability;
  start_date: string;
  end_date: string;
  generated_at: string;
  dimension: StrategyDimension;
  cost_basis: string;
  trade_count: number;
  resolved_count: number;
  items: Array<{
    key: string;
    label: string;
    trade_count: number;
    resolved_count: number;
    win_count: number;
    loss_count: number;
    flat_count: number;
    coverage: number | null;
    win_rate: number | null;
    average_return_pct: number | null;
    profit_factor: number | null;
    max_drawdown_pct: number | null;
  }>;
  issues: string[];
  provenance: Provenance;
}
