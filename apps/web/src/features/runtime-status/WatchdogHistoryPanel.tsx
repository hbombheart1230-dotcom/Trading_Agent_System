import { useCallback, useEffect } from "react";
import { CheckCircle2, History, RotateCcw, ShieldAlert } from "lucide-react";

import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { Panel } from "../../shared/components/Panel";
import { formatDateTime } from "../../shared/formatters/dates";
import { SortableHeaderRow, type SortableColumn } from "../../shared/tables/SortableHeaderRow";
import { timestamp } from "../../shared/tables/sorting";
import { useSortableRows } from "../../shared/tables/useSortableRows";
import {
  runtimeHistoryLabel,
  supervisorActionLabel,
  supervisorReasonLabel,
} from "./presentation";
import type { WatchdogHistory, WatchdogHistoryItem } from "./types";
import { useRuntimeStatus } from "./RuntimeStatusContext";

type Column = "time" | "result" | "action" | "transition";
const COLUMNS: Array<SortableColumn<Column>> = [
  { key: "time", label: "점검 시각" },
  { key: "result", label: "결과" },
  { key: "action", label: "자동 조치" },
  { key: "transition", label: "MAIN 전후 상태" },
];

export function WatchdogHistoryPanel() {
  const history = useApi<WatchdogHistory>("/api/v1/runtime/watchdog-history?limit=10");
  const runtime = useRuntimeStatus();
  const valueFor = useCallback((row: WatchdogHistoryItem, key: Column) => {
    if (key === "time") return timestamp(row.observed_at);
    if (key === "result") return row.ok;
    if (key === "action") return row.action;
    return `${row.runtime_before}-${row.runtime_after}`;
  }, []);
  const sorted = useSortableRows(history.data?.items ?? [], valueFor);

  useEffect(() => {
    const timer = window.setInterval(history.refresh, 60_000);
    return () => window.clearInterval(timer);
  }, [history.refresh]);

  const supervisor = runtime.data?.supervisor;
  const restartLimit = supervisor?.max_daily_restarts;
  const last = history.data?.items[0];

  return (
    <Panel title="Watchdog / 자동 복구" meta="5분 점검 · 관측 및 제한적 자동 복구" className="span-12 panel-flush watchdog-panel">
      <DataState loading={history.loading} error={history.error} empty={!history.data} onRetry={history.refresh}>
        {history.data && <>
          <div className="watchdog-summary-strip">
            <div><CheckCircle2 size={15} /><span>최근 점검</span><strong>{last?.ok ? "정상" : last ? "확인 필요" : "이력 대기"}</strong><small>{formatDateTime(last?.observed_at)}</small></div>
            <div><RotateCcw size={15} /><span>오늘 자동 복구</span><strong>{supervisor?.restart_count ?? 0} / {restartLimit ?? "-"}</strong><small>10분 쿨다운 · 최대 3회</small></div>
            <div><History size={15} /><span>최근 조치</span><strong>{supervisorActionLabel(supervisor?.last_action ?? last?.action ?? "UNKNOWN")}</strong><small>{supervisorReasonLabel(supervisor?.last_reason ?? last?.reason ?? null)}</small></div>
            <div><ShieldAlert size={15} /><span>현재 제한/잔존 문제</span><strong>{supervisor?.runtime_issue_after ? "점검 필요" : "없음"}</strong><small>{supervisor?.runtime_issue_after ?? (runtime.data?.watchdog.blockers.join(", ") || "자동복구 정책 정상")}</small></div>
          </div>
          <div className="data-table-wrap">
            <table className="data-table sortable-table watchdog-history-table">
              <thead><SortableHeaderRow columns={COLUMNS} sort={sorted.sort} onSort={sorted.toggleSort} /></thead>
              <tbody>{sorted.rows.map((item, index) => <tr key={`${item.observed_at}-${index}`}>
                <td><strong>{formatDateTime(item.observed_at)}</strong><div className="table-subline">{item.day}</div></td>
                <td><span className={`runtime-state-pill ${item.ok ? "runtime-running" : "runtime-error"}`}>{item.ok ? "정상" : "점검 필요"}</span>{item.blockers.length > 0 && <div className="table-subline">{item.blockers.join(", ")}</div>}</td>
                <td><strong>{supervisorActionLabel(item.action)}</strong><div className="table-subline">{supervisorReasonLabel(item.reason)}</div></td>
                <td><span className="mono">{runtimeHistoryLabel(item.runtime_before)} → {runtimeHistoryLabel(item.runtime_after)}</span><div className="table-subline">Heartbeat {item.heartbeat_age_after_seconds == null ? "-" : `${item.heartbeat_age_after_seconds}초`}</div></td>
              </tr>)}</tbody>
            </table>
          </div>
        </>}
      </DataState>
    </Panel>
  );
}
