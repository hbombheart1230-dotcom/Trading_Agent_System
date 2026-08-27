import { formatNumber, formatPct, toneFor } from "../../shared/formatters/numbers";
import { SortableHeaderRow, type SortableColumn } from "../../shared/tables/SortableHeaderRow";
import type { SortValue } from "../../shared/tables/sorting";
import { useSortableRows } from "../../shared/tables/useSortableRows";
import type { StrategyPerformanceItem } from "./types";

type StrategySortKey = "group" | "sample" | "coverage" | "win_rate" | "average" | "pf" | "mdd";
const COLUMNS: Array<SortableColumn<StrategySortKey>> = [
  { key: "group", label: "그룹" }, { key: "sample", label: "표본" }, { key: "coverage", label: "Coverage" },
  { key: "win_rate", label: "승률" }, { key: "average", label: "평균" },
  { key: "pf", label: "PF" }, { key: "mdd", label: "MDD" },
];

function sortValue(item: StrategyPerformanceItem, key: StrategySortKey): SortValue {
  if (key === "group") return item.label;
  if (key === "sample") return item.trade_count;
  if (key === "coverage") return item.coverage;
  if (key === "win_rate") return item.win_rate;
  if (key === "average") return item.average_return_pct;
  if (key === "pf") return item.profit_factor;
  return item.max_drawdown_pct;
}

export function StrategyPerformanceTable({ items }: { items: StrategyPerformanceItem[] }) {
  const sorted = useSortableRows(items, sortValue);
  return <div className="data-table-wrap"><table className="data-table sortable-table">
    <thead><SortableHeaderRow columns={COLUMNS} sort={sorted.sort} onSort={sorted.toggleSort} /></thead>
    <tbody>{sorted.rows.map((item) => <tr key={item.key}><td><strong>{item.label}</strong></td><td>{item.resolved_count}/{item.trade_count}</td><td>{formatPct((item.coverage ?? 0) * 100)}</td><td>{formatPct(item.win_rate != null ? item.win_rate * 100 : null)}</td><td className={toneFor(item.average_return_pct)}>{formatPct(item.average_return_pct, true)}</td><td>{formatNumber(item.profit_factor)}</td><td className="negative">{formatPct(item.max_drawdown_pct)}</td></tr>)}</tbody>
  </table></div>;
}
