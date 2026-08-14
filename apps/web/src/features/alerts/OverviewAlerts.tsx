import { BellRing } from "lucide-react";

import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { SeverityBadge } from "./SeverityBadge";
import type { AnomalyResponse } from "./types";

export function OverviewAlerts() {
  const response = useApi<AnomalyResponse>("/api/v1/anomalies");
  const items = response.data?.items.slice(0, 4) ?? [];
  return (
    <DataState loading={response.loading} error={response.error} empty={!items.length} emptyText="현재 탐지된 긴급·주의·관찰 신호가 없습니다." onRetry={response.refresh}>
      <div className="overview-alert-list">{items.map((item) => (
        <div className="overview-alert" key={item.anomaly_id}>
          <BellRing size={15} />
          <div><strong>{item.title}</strong><span>{item.summary}</span></div>
          <SeverityBadge severity={item.severity} />
        </div>
      ))}</div>
    </DataState>
  );
}
