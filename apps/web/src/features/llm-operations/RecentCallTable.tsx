import { formatDateTime } from "../../shared/formatters/dates";
import { formatNumber } from "../../shared/formatters/numbers";
import { SortableHeaderRow, type SortableColumn } from "../../shared/tables/SortableHeaderRow";
import { timestamp, type SortValue } from "../../shared/tables/sorting";
import { useSortableRows } from "../../shared/tables/useSortableRows";
import { stageLabel } from "./labels";
import type { LlmRecentCall } from "./types";

type CallSortKey = "time" | "stage" | "model" | "status" | "latency" | "attempts";
const COLUMNS: Array<SortableColumn<CallSortKey>> = [
  { key: "time", label: "시각" }, { key: "stage", label: "단계" }, { key: "model", label: "모델" },
  { key: "status", label: "상태" }, { key: "latency", label: "지연" }, { key: "attempts", label: "시도" },
];

function sortValue(call: LlmRecentCall, key: CallSortKey): SortValue {
  if (key === "time") return timestamp(call.occurred_at);
  if (key === "stage") return stageLabel(call.stage);
  if (key === "model") return call.model;
  if (key === "status") return call.status;
  if (key === "latency") return call.latency_ms;
  return call.attempts;
}

export function RecentCallTable({ calls }: { calls: LlmRecentCall[] }) {
  const sorted = useSortableRows(calls, sortValue);
  return <div className="data-table-wrap"><table className="data-table sortable-table">
    <thead><SortableHeaderRow columns={COLUMNS} sort={sorted.sort} onSort={sorted.toggleSort} /></thead>
    <tbody>{sorted.rows.map((call, index) => <tr key={`${call.occurred_at}-${index}`}><td>{formatDateTime(call.occurred_at)}</td><td>{stageLabel(call.stage)}</td><td className="mono model-name">{call.model}</td><td className={call.status === "ok" ? "positive" : "negative"}><strong>{call.status === "ok" ? "성공" : "실패"}</strong>{call.error_type && <div className="table-subline">{call.error_type}</div>}</td><td>{call.latency_ms == null ? "-" : `${formatNumber(call.latency_ms / 1000, 1)}초`}</td><td>{call.attempts ?? "-"}</td></tr>)}</tbody>
  </table></div>;
}
