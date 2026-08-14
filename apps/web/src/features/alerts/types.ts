import type { Availability, Provenance } from "../../shared/api/types";

export type AnomalySeverity = "CRITICAL" | "WARNING" | "WATCH";

export interface AnomalyEvidence {
  metric: string;
  observed_value: number | null;
  threshold_value: number | null;
  comparator: string;
  unit: string;
  sample_count: number;
  cost_basis: string;
}

export interface OperationalAnomaly {
  anomaly_id: string;
  category: string;
  severity: AnomalySeverity;
  title: string;
  summary: string;
  affected_symbols: string[];
  evidence: AnomalyEvidence;
  source: string;
  observed_at: string | null;
}

export interface AnomalyResponse {
  status: Availability;
  day: string;
  generated_at: string;
  policy_version: string;
  behavior_effect: "OBSERVATION_ONLY";
  critical_count: number;
  warning_count: number;
  watch_count: number;
  evaluated_trade_count: number;
  evaluated_opportunity_count: number;
  evaluated_rule_count: number;
  items: OperationalAnomaly[];
  issues: string[];
  provenance: Provenance;
}
