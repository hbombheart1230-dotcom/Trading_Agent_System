import { formatDateTime } from "../../shared/formatters/dates";
import { SortableHeaderRow, type SortableColumn } from "../../shared/tables/SortableHeaderRow";
import { timestamp, type SortValue } from "../../shared/tables/sorting";
import { useSortableRows } from "../../shared/tables/useSortableRows";
import { CATEGORY_LABELS, formatEvidence } from "./labels";
import { SeverityBadge } from "./SeverityBadge";
import type { OperationalAnomaly } from "./types";

type AnomalySortKey = "severity" | "category" | "title" | "observed" | "symbols" | "time";

const COLUMNS: Array<SortableColumn<AnomalySortKey>> = [
  { key: "severity", label: "등급" },
  { key: "category", label: "분류" },
  { key: "title", label: "운영 신호" },
  { key: "observed", label: "관측값" },
  { key: "symbols", label: "대상" },
  { key: "time", label: "시각" },
];
const SEVERITY_ORDER = { WATCH: 1, WARNING: 2, CRITICAL: 3 };

function sortValue(item: OperationalAnomaly, key: AnomalySortKey): SortValue {
  if (key === "severity") return SEVERITY_ORDER[item.severity];
  if (key === "category") return CATEGORY_LABELS[item.category] ?? item.category;
  if (key === "title") return item.title;
  if (key === "observed") return item.evidence.observed_value;
  if (key === "symbols") return item.affected_symbols.join(",") || "전체";
  return timestamp(item.observed_at);
}

export function AnomalyTable({ items }: { items: OperationalAnomaly[] }) {
  const sorted = useSortableRows(items, sortValue);
  return (
    <div className="data-table-wrap">
      <table className="data-table anomaly-table sortable-table">
        <thead><SortableHeaderRow columns={COLUMNS} sort={sorted.sort} onSort={sorted.toggleSort} /></thead>
        <tbody>{sorted.rows.map((item) => (
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
