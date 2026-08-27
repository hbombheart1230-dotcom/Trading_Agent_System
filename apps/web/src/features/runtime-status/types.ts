import type { Availability } from "../../shared/api/types";

export type RuntimeState =
  | "RUNNING"
  | "DELAYED"
  | "STALE"
  | "DUPLICATE"
  | "INCONSISTENT"
  | "STOPPED_EXPECTED"
  | "STOPPED_UNEXPECTED"
  | "UNKNOWN";

export interface RuntimeStatus {
  status: Availability;
  runtime_state: RuntimeState;
  checked_at: string;
  read_only: boolean;
  execution_callable: boolean;
  lock: {
    exists: boolean;
    owner_pid: number | null;
    started_at: string | null;
    heartbeat_at: string | null;
    heartbeat_age_seconds: number | null;
  };
  process: {
    observed_at: string | null;
    observation_age_seconds: number | null;
    raw_process_count: number | null;
    logical_session_count: number | null;
    tree_state: string;
    processes: Array<{ pid: number; parent_pid: number; is_owner: boolean }>;
  };
  watchdog: {
    observed_at: string | null;
    observation_age_seconds: number | null;
    fresh: boolean;
    ok: boolean | null;
    blockers: string[];
  };
  supervisor: {
    available: boolean;
    policy_version: string;
    decision: string;
    decision_reason: string | null;
    heartbeat_stale_seconds: number | null;
    restart_cooldown_seconds: number | null;
    restart_count: number;
    max_daily_restarts: number | null;
    last_action: string;
    last_reason: string | null;
    last_restart_at: string | null;
    last_restart_reason: string | null;
    last_restart_success: boolean | null;
    cooldown_until: string | null;
    runtime_issue_after: string | null;
  };
  market: {
    observed_at: string | null;
    code: string | null;
    label: string | null;
    expected_running: boolean;
    expectation_source: string;
  };
  issues: string[];
}

export interface WatchdogHistoryItem {
  day: string;
  observed_at: string | null;
  ok: boolean;
  offhours_noop: boolean;
  action: string;
  reason: string | null;
  restart_count: number;
  max_daily_restarts: number | null;
  runtime_before: string;
  runtime_after: string;
  heartbeat_age_before_seconds: number | null;
  heartbeat_age_after_seconds: number | null;
  blockers: string[];
}

export interface WatchdogHistory {
  status: Availability;
  generated_at: string;
  read_only: boolean;
  execution_callable: boolean;
  items: WatchdogHistoryItem[];
  issues: string[];
}

export interface ScheduledIntelligence {
  status: Availability;
  generated_at: string;
  read_only: boolean;
  execution_callable: boolean;
  jobs: Array<{
    job: string;
    expected_time_kst: string;
    day: string | null;
    generated_at: string | null;
    status: string;
    memory_status: string | null;
    memory_source_day: string | null;
    summary: string | null;
    issues: string[];
  }>;
  issues: string[];
}
