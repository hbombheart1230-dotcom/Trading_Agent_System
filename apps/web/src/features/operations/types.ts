import type { Availability, Provenance } from "../../shared/api/types";

export interface OperationsTimelineItem {
  event_id: string;
  phase: string;
  title: string;
  expected_time_kst: string | null;
  actual_time: string | null;
  status: string;
  detail: string | null;
  source: string;
  trade_id: string | null;
}

export interface OperationsAlert {
  alert_id: string;
  severity: "CRITICAL" | "WARNING" | "WATCH";
  title: string;
  detail: string;
  source: string;
  observed_at: string | null;
}

export interface OperationsDashboard {
  status: Availability;
  day: string;
  previous_day: string | null;
  generated_at: string;
  read_only: true;
  execution_callable: false;
  timeline: OperationsTimelineItem[];
  alerts: OperationsAlert[];
  comparison: Array<{
    metric: string;
    current_value: string | null;
    previous_value: string | null;
    change: "동일" | "변경" | "신규";
  }>;
  trade_count: number;
  issues: string[];
  provenance: Provenance;
}
