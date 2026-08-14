import type { Availability, Provenance } from "../../shared/api/types";

export interface LlmRoleUsage {
  role: string;
  label: string;
  configured_model: string;
  fallback_model: string | null;
  configuration_source: string;
  observed_model: string | null;
  call_count: number;
  success_count: number;
  failure_count: number;
  latest_call_at: string | null;
  state: "ACTIVE" | "DEGRADED" | "CONFIGURED" | "ROUTING_WARNING";
}

export interface LlmStageUsage {
  stage_key: string;
  stage_label: string;
  stage_index: number | null;
  call_count: number;
  success_count: number;
  failure_count: number;
  model: string | null;
  latest_call_at: string | null;
}

export interface LlmRecentCall {
  occurred_at: string;
  role: string;
  stage: string;
  model: string;
  status: string;
  latency_ms: number | null;
  attempts: number | null;
  error_type: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  estimated_cost_usd: number | null;
}

export interface LlmOperations {
  status: Availability;
  day: string;
  generated_at: string;
  provider: string;
  total_calls: number;
  success_count: number;
  failure_count: number;
  success_rate: number | null;
  latency: {
    status: Availability;
    observed_count: number;
    average_ms: number | null;
    p95_ms: number | null;
    maximum_ms: number | null;
    coverage: number | null;
    recent_window_only: boolean;
  };
  token_usage: {
    status: Availability;
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
    estimated_cost_usd: number | null;
    reason: string | null;
  };
  roles: LlmRoleUsage[];
  stages: LlmStageUsage[];
  recent_calls: LlmRecentCall[];
  issues: string[];
  provenance: Provenance;
}
