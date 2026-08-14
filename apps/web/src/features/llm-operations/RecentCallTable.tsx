import { formatDateTime } from "../../shared/formatters/dates";
import { formatNumber } from "../../shared/formatters/numbers";
import { stageLabel } from "./labels";
import type { LlmRecentCall } from "./types";

export function RecentCallTable({ calls }: { calls: LlmRecentCall[] }) {
  return <div className="data-table-wrap"><table className="data-table"><thead><tr><th>시각</th><th>단계</th><th>모델</th><th>상태</th><th>지연</th><th>시도</th></tr></thead><tbody>{calls.map((call, index) => <tr key={`${call.occurred_at}-${index}`}><td>{formatDateTime(call.occurred_at)}</td><td>{stageLabel(call.stage)}</td><td className="mono model-name">{call.model}</td><td className={call.status === "ok" ? "positive" : "negative"}><strong>{call.status === "ok" ? "성공" : "실패"}</strong>{call.error_type && <div className="table-subline">{call.error_type}</div>}</td><td>{call.latency_ms == null ? "-" : `${formatNumber(call.latency_ms / 1000, 1)}초`}</td><td>{call.attempts ?? "-"}</td></tr>)}</tbody></table></div>;
}
