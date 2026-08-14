import type { Availability, Provenance } from "../../shared/api/types";

export interface TradeSummary {
  trade_id: string;
  day: string;
  symbol: string;
  symbol_name: string | null;
  themes: string[];
  status: string;
  entry_time: string | null;
  exit_time: string | null;
  entry_price: number | null;
  exit_price: number | null;
  quantity: number | null;
  hold_seconds: number | null;
  realized_pnl_krw: number | null;
  realized_return_pct: number | null;
  result: string | null;
  playbook: string | null;
  tactic_id: string | null;
  strategy_horizon: string | null;
  scanner_rank: number | null;
  cost_basis: string;
  artifact_status: Availability;
  artifact_scope: string;
}

export interface TradeList {
  status: Availability;
  start_date: string;
  end_date: string;
  generated_at: string;
  total_count: number;
  offset: number;
  limit: number;
  items: TradeSummary[];
  issue_count: number;
  issues_truncated: boolean;
  issues: string[];
  provenance: Provenance;
}

export interface TradeDetail {
  status: Availability;
  generated_at: string;
  trade: TradeSummary;
  decisions: {
    playbook: string | null;
    tactic_id: string | null;
    strategist_horizon: string | null;
    commander_horizon: string | null;
    scanner_rank: number | null;
    scanner_score: number | null;
    scanner_chart_fit_score: number | null;
    selection_basis: string | null;
    monitor_entry_reason: string | null;
    monitor_exit_trigger: string | null;
    tactic_suitability_score: number | null;
  };
  timeline: Array<{
    timestamp: string;
    stage: string;
    action: string;
    reason: string | null;
    price: number | null;
    quantity: number | null;
    source: string;
  }>;
  post_exit: Array<{
    horizon: string;
    status: string;
    observed_at: string | null;
    price: number | null;
    return_pct: number | null;
  }>;
  integrity: {
    status: Availability;
    lifecycle_status: string | null;
    lifecycle_completeness: string | null;
    completeness_score: number | null;
    broker_reconciliation_status: string | null;
    agent_sources: Record<string, string>;
    evaluation_eligible: boolean;
    exclusion_reason: string | null;
    issues: string[];
  };
  provenance: Provenance;
}

export interface ReportCatalog {
  status: Availability;
  trade_id: string;
  generated_at: string;
  reports: Array<{ report_id: string; title: string; format: string; available: boolean; size_bytes: number | null }>;
  provenance: Provenance;
}

export interface ReportContent {
  status: Availability;
  trade_id: string;
  report_id: string;
  title: string;
  format: string;
  generated_at: string;
  markdown: string | null;
  json_content: Record<string, unknown> | unknown[] | null;
  provenance: Provenance;
}
