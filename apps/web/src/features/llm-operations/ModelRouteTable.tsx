import { formatDateTime } from "../../shared/formatters/dates";
import { SortableHeaderRow, type SortableColumn } from "../../shared/tables/SortableHeaderRow";
import { timestamp, type SortValue } from "../../shared/tables/sorting";
import { useSortableRows } from "../../shared/tables/useSortableRows";
import { roleStateLabel } from "./labels";
import type { LlmRoleUsage } from "./types";

type RoleSortKey = "role" | "configured" | "observed" | "fallback" | "calls" | "state" | "latest";
const COLUMNS: Array<SortableColumn<RoleSortKey>> = [
  { key: "role", label: "역할" }, { key: "configured", label: "현재 설정 모델" },
  { key: "observed", label: "당일 실사용 모델" }, { key: "fallback", label: "Fallback" },
  { key: "calls", label: "호출" }, { key: "state", label: "상태" }, { key: "latest", label: "최근 호출" },
];

function sortValue(role: LlmRoleUsage, key: RoleSortKey): SortValue {
  if (key === "role") return role.label;
  if (key === "configured") return role.configured_model;
  if (key === "observed") return role.observed_model;
  if (key === "fallback") return role.fallback_model;
  if (key === "calls") return role.call_count;
  if (key === "state") return role.state;
  return timestamp(role.latest_call_at);
}

export function ModelRouteTable({ roles }: { roles: LlmRoleUsage[] }) {
  const sorted = useSortableRows(roles, sortValue);
  return <div className="data-table-wrap"><table className="data-table sortable-table">
    <thead><SortableHeaderRow columns={COLUMNS} sort={sorted.sort} onSort={sorted.toggleSort} /></thead>
    <tbody>{sorted.rows.map((role) => <tr key={role.role}><td><strong>{role.label}</strong><div className="table-subline">{role.configuration_source}</div></td><td className="mono model-name">{role.configured_model}</td><td className="mono model-name">{role.observed_model ?? "-"}</td><td className="mono model-name muted">{role.fallback_model ?? "-"}</td><td>{role.success_count}/{role.call_count}</td><td><span className={`llm-role-state state-${role.state.toLowerCase()}`}>{roleStateLabel(role.state)}</span></td><td>{formatDateTime(role.latest_call_at)}</td></tr>)}</tbody>
  </table></div>;
}
