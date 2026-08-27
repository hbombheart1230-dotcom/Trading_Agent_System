import { formatKrw, formatNumber, toneFor } from "../../shared/formatters/numbers";
import type { PortfolioPosition } from "../../shared/api/types";
import { SortableHeaderRow, type SortableColumn } from "../../shared/tables/SortableHeaderRow";
import type { SortValue } from "../../shared/tables/sorting";
import { useSortableRows } from "../../shared/tables/useSortableRows";

type PositionSortKey = "symbol" | "quantity" | "average" | "current" | "pnl" | "status";
const COLUMNS: Array<SortableColumn<PositionSortKey>> = [
  { key: "symbol", label: "종목" }, { key: "quantity", label: "수량" }, { key: "average", label: "평균가" },
  { key: "current", label: "현재가" }, { key: "pnl", label: "평가손익" }, { key: "status", label: "상태" },
];

function sortValue(position: PortfolioPosition, key: PositionSortKey): SortValue {
  if (key === "symbol") return position.symbol_name ?? position.symbol;
  if (key === "quantity") return position.quantity;
  if (key === "average") return position.average_price;
  if (key === "current") return position.current_price;
  if (key === "pnl") return position.unrealized_pnl;
  return position.lifecycle_status;
}

export function PositionTable({ positions }: { positions: PortfolioPosition[] }) {
  const sorted = useSortableRows(positions, sortValue);
  return <div className="data-table-wrap"><table className="data-table sortable-table">
    <thead><SortableHeaderRow columns={COLUMNS} sort={sorted.sort} onSort={sorted.toggleSort} /></thead>
    <tbody>{sorted.rows.map((position) => <tr key={position.symbol}><td className="symbol-cell"><strong>{position.symbol_name ?? position.symbol}</strong><span>{position.symbol}</span></td><td>{formatNumber(position.quantity, 0)}</td><td>{formatNumber(position.average_price, 0)}</td><td>{formatNumber(position.current_price, 0)}</td><td className={toneFor(position.unrealized_pnl)}>{formatKrw(position.unrealized_pnl)}</td><td>{position.lifecycle_status ?? "-"}</td></tr>)}</tbody>
  </table></div>;
}
