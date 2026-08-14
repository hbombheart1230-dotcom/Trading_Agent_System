import { formatDateTime } from "../../shared/formatters/dates";
import { CATEGORY_LABELS, formatEvidence } from "./labels";
import { SeverityBadge } from "./SeverityBadge";
import type { OperationalAnomaly } from "./types";

export function AnomalyTable({ items }: { items: OperationalAnomaly[] }) {
  return (
    <div className="data-table-wrap">
      <table className="data-table anomaly-table">
        <thead><tr><th>등급</th><th>분류</th><th>운영 신호</th><th>관측값</th><th>대상</th><th>시각</th></tr></thead>
        <tbody>{items.map((item) => (
          <tr key={item.anomaly_id}>
            <td><SeverityBadge severity={item.severity} /></td>
            <td><strong>{CATEGORY_LABELS[item.category] ?? item.category}</strong></td>
            <td className="anomaly-summary"><strong>{item.title}</strong><span>{item.summary}</span></td>
            <td className="mono">{formatEvidence(item.evidence.observed_value, item.evidence.unit)} <span className="table-subline">{item.evidence.comparator} {formatEvidence(item.evidence.threshold_value, item.evidence.unit)}</span></td>
            <td>{item.affected_symbols.length ? item.affected_symbols.join(", ") : "전체"}</td>
            <td>{formatDateTime(item.observed_at)}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
