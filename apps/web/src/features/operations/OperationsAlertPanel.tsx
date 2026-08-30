import { AlertCircle, AlertTriangle, Eye } from "lucide-react";

import { formatDateTime } from "../../shared/formatters/dates";
import type { OperationsAlert } from "./types";

const ICONS = { CRITICAL: AlertCircle, WARNING: AlertTriangle, WATCH: Eye } as const;

export function OperationsAlertPanel({ alerts }: { alerts: OperationsAlert[] }) {
  if (!alerts.length) return <div className="operations-clear-state">현재 운영일에서 확인할 이상 징후가 없습니다.</div>;
  return <div className="operations-alert-list">
    {alerts.map((alert) => {
      const Icon = ICONS[alert.severity] ?? Eye;
      return <article className={`operations-alert severity-${alert.severity.toLowerCase()}`} key={alert.alert_id}>
        <Icon size={16} />
        <div><strong>{alert.title}</strong><p>{alert.detail}</p><small>{alert.source} · {formatDateTime(alert.observed_at)}</small></div>
      </article>;
    })}
  </div>;
}
