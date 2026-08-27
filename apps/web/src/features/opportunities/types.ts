import type { Availability, Provenance } from "../../shared/api/types";

export interface OpportunityFunnel {
  status: Availability;
  day: string;
  generated_at: string;
  behavior_effect: string;
  raw_candidate_count: number;
  deduplicated_candidate_count: number;
  duplicate_count: number;
  signal_count: number;
  current_signal_count: number;
  probe_candidate_count: number;
  probe_near_miss_count: number;
  blockers: Array<{
    reason: string;
    candidate_count: number;
    observed_count: number;
    coverage: number | null;
    positive_rate: number | null;
    missed_opportunity_rate: number | null;
    adverse_rate: number | null;
    average_latest_return_pct: number | null;
    decision: string | null;
  }>;
  current_signals: Array<{
    symbol: string;
    observed_at: string | null;
    price: number | null;
    score: number | null;
    state: string | null;
    probe_candidate: boolean;
    probe_near_miss: boolean;
    blocker_reasons: string[];
    market_state: string | null;
    market_relative_strength: number | null;
    vwap_distance_pct: number | null;
    volume_ratio: number | null;
    breakout_5m: boolean | null;
  }>;
  issues: string[];
  provenance: Provenance;
}

export interface OpportunityOutcomes {
  status: Availability;
  day: string;
  generated_at: string;
  behavior_effect: string;
  cost_basis: string;
  opportunity_count: number;
  observed_checkpoint_count: number;
  expected_checkpoint_count: number;
  coverage: number | null;
  outcomes: Array<{
    opportunity_id: string;
    symbol: string;
    symbol_name: string | null;
    observed_at: string | null;
    reference_entry_at: string | null;
    rank: number | null;
    score: number | null;
    source_labels: string[];
    prospective_eligible: boolean;
    checkpoints: Array<{
      horizon: string;
      status: string;
      gross_return_pct: number | null;
      live_equivalent_net_return_pct: number | null;
      mock_broker_net_return_pct: number | null;
      maximum_favorable_excursion_pct: number | null;
      maximum_adverse_excursion_pct: number | null;
    }>;
  }>;
  issues: string[];
  provenance: Provenance;
}

export type OpportunitySignal = OpportunityFunnel["current_signals"][number];
export type OpportunityOutcome = OpportunityOutcomes["outcomes"][number];
