import type { Availability, Provenance } from "../../shared/api/types";

export interface MarketMetric {
  key: string;
  label: string;
  category: string;
  value: number | null;
  change: number | null;
  change_pct: number | null;
  unit: string;
  status: string;
  source: string | null;
  role: string | null;
}

export interface MarketSnapshot {
  status: Availability;
  day: string;
  generated_at: string;
  source_generated_at: string | null;
  sentiment_score: number | null;
  sentiment_reason: string | null;
  breadth: { rising: number; falling: number; unchanged: number; breadth_ratio: number | null } | null;
  metrics: MarketMetric[];
  warning_count: number;
  warnings: string[];
  provenance: Provenance;
}

export interface MarketSeries {
  status: Availability;
  start_date: string;
  end_date: string;
  generated_at: string;
  metric_key: string;
  label: string | null;
  unit: string | null;
  points: Array<{ day: string; source_generated_at: string | null; value: number | null; change: number | null; change_pct: number | null; status: string }>;
  missing_day_count: number;
  provenance: Provenance;
}
