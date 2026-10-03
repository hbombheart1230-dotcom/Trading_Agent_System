import { formatDateTime } from "../../shared/formatters/dates";
import { SortableHeaderRow, type SortableColumn } from "../../shared/tables/SortableHeaderRow";
import { timestamp, type SortValue } from "../../shared/tables/sorting";
import { useSortableRows } from "../../shared/tables/useSortableRows";
import { stageLabel } from "./labels";
import type { LlmStageUsage } from "./types";

type StageSortKey = "stage" | "calls" | "success" | "failure" | "latest";
const COLUMNS: Array<SortableColumn<StageSortKey>> = [
  { key: "stage", label: "단계" }, { key: "calls", label: "호출" },
  { key: "success", label: "성공" }, { key: "failure", label: "실패" },
  { key: "latest", label: "최근" },
];

function sortValue(stage: LlmStageUsage, key: StageSortKey): SortValue {
  if (key === "stage") return stage.stage_index ?? stage.stage_label;
  if (key === "calls") return stage.call_count;
  if (key === "success") return stage.success_count;
  if (key === "failure") return stage.failure_count;
  return timestamp(stage.latest_call_at);
}

export function StageUsageTable({ stages }: { stages: LlmStageUsage[] }) {
  const sorted = useSortableRows(stages, sortValue);
  return <div className="data-table-wrap"><table className="data-table sortable-table">
    <thead><SortableHeaderRow columns={COLUMNS} sort={sorted.sort} onSort={sorted.toggleSort} /></thead>
    <tbody>{sorted.rows.map((stage) => <tr key={stage.stage_key}><td><strong>{stageLabel(stage.stage_label)}</strong><div className="table-subline mono">{stage.model ?? "-"}</div></td><td>{stage.call_count}</td><td className="positive">{stage.success_count}</td><td className={stage.failure_count ? "negative" : "muted"}>{stage.failure_count}</td><td>{formatDateTime(stage.latest_call_at)}</td></tr>)}</tbody>
  </table></div>;
}
