import { formatNumber, formatPct, toneFor } from "../../shared/formatters/numbers";
import { SortableHeaderRow, type SortableColumn } from "../../shared/tables/SortableHeaderRow";
import type { SortValue } from "../../shared/tables/sorting";
import { useSortableRows } from "../../shared/tables/useSortableRows";
import type { MarketMetric } from "./types";

type MetricSortKey = "metric" | "category" | "value" | "change" | "role" | "source";
const COLUMNS: Array<SortableColumn<MetricSortKey>> = [
  { key: "metric", label: "지표" }, { key: "category", label: "구분" }, { key: "value", label: "현재값" },
  { key: "change", label: "변동" }, { key: "role", label: "역할" }, { key: "source", label: "Source" },
];

function sortValue(item: MarketMetric, key: MetricSortKey): SortValue {
  if (key === "metric") return item.label;
  if (key === "category") return item.category;
  if (key === "value") return item.value;
  if (key === "change") return item.change_pct ?? item.change;
  if (key === "role") return item.role;
  return item.source;
}

export function MarketMetricTable({ metrics }: { metrics: MarketMetric[] }) {
  const sorted = useSortableRows(metrics, sortValue);
  return <div className="data-table-wrap"><table className="data-table sortable-table">
    <thead><SortableHeaderRow columns={COLUMNS} sort={sorted.sort} onSort={sorted.toggleSort} /></thead>
    <tbody>{sorted.rows.map((item) => <tr key={item.key}><td><strong>{item.label}</strong><div className="muted mono">{item.key}</div></td><td>{item.category}</td><td>{formatNumber(item.value, 4)} <span className="muted">{item.unit}</span></td><td className={toneFor(item.change_pct)}>{item.change_pct != null ? formatPct(item.change_pct, true) : formatNumber(item.change, 4)}</td><td>{item.role?.replaceAll("_", " ") ?? "-"}</td><td>{item.source ?? "-"}</td></tr>)}</tbody>
  </table></div>;
}
