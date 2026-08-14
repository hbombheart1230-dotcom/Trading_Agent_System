import { formatDateTime } from "../../shared/formatters/dates";
import { roleStateLabel } from "./labels";
import type { LlmRoleUsage } from "./types";

export function ModelRouteTable({ roles }: { roles: LlmRoleUsage[] }) {
  return <div className="data-table-wrap"><table className="data-table"><thead><tr><th>역할</th><th>현재 설정 모델</th><th>당일 실사용 모델</th><th>Fallback</th><th>호출</th><th>상태</th><th>최근 호출</th></tr></thead><tbody>{roles.map((role) => <tr key={role.role}><td><strong>{role.label}</strong><div className="table-subline">{role.configuration_source}</div></td><td className="mono model-name">{role.configured_model}</td><td className="mono model-name">{role.observed_model ?? "-"}</td><td className="mono model-name muted">{role.fallback_model ?? "-"}</td><td>{role.success_count}/{role.call_count}</td><td><span className={`llm-role-state state-${role.state.toLowerCase()}`}>{roleStateLabel(role.state)}</span></td><td>{formatDateTime(role.latest_call_at)}</td></tr>)}</tbody></table></div>;
}
