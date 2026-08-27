import { useMemo, useState } from "react";

import { StatusPill } from "../../shared/components/StatusPill";
import { formatDateTime, formatDuration } from "../../shared/formatters/dates";
import { formatKrw, formatPct, toneFor } from "../../shared/formatters/numbers";
import { SortableHeaderRow, type SortableColumn } from "../../shared/tables/SortableHeaderRow";
import type { SortState } from "../../shared/tables/sorting";
import { sortTrades, type TradeSortKey } from "./tradeSort";
import type { TradeSummary } from "./types";

interface Props {
  items: TradeSummary[];
  selectedId: string | null;
  onSelect: (tradeId: string) => void;
}

const HEADERS: Array<SortableColumn<TradeSortKey>> = [
  { key: "identity", label: "거래일 / 종목" },
  { key: "entry_time", label: "진입" },
  { key: "hold_seconds", label: "보유" },
  { key: "strategy", label: "전략" },
  { key: "scanner_rank", label: "순위" },
  { key: "realized_pnl_krw", label: "실현손익" },
  { key: "realized_return_pct", label: "수익률" },
  { key: "artifact_status", label: "Artifact" },
];

export function TradeTable({ items, selectedId, onSelect }: Props) {
  const [sort, setSort] = useState<SortState<TradeSortKey> | null>(null);
  const visibleItems = useMemo(
    () => sort ? sortTrades(items, sort.key, sort.direction) : items,
    [items, sort],
  );

  const toggleSort = (key: TradeSortKey) => {
    setSort((current) => ({
      key,
      direction: current?.key === key && current.direction === "asc" ? "desc" : "asc",
    }));
  };

  return (
    <div className="data-table-wrap">
      <table className="data-table sortable-table">
        <thead><SortableHeaderRow columns={HEADERS} sort={sort} onSort={toggleSort} /></thead>
        <tbody>
          {visibleItems.map((trade) => (
            <tr className="clickable" key={trade.trade_id} onClick={() => onSelect(trade.trade_id)} style={selectedId === trade.trade_id ? { background: "#edf8f5" } : undefined}>
              <td className="symbol-cell"><strong>{trade.symbol_name ?? trade.symbol}</strong><span>{trade.day} · {trade.symbol}</span></td>
              <td>{formatDateTime(trade.entry_time)}</td>
              <td>{formatDuration(trade.hold_seconds)}</td>
              <td><strong>{trade.playbook ?? "-"}</strong><div className="muted">{trade.strategy_horizon ?? "horizon 미확인"}</div></td>
              <td>{trade.scanner_rank != null ? `#${trade.scanner_rank}` : "-"}</td>
              <td className={toneFor(trade.realized_pnl_krw)}>{formatKrw(trade.realized_pnl_krw)}</td>
              <td className={toneFor(trade.realized_return_pct)}>{formatPct(trade.realized_return_pct, true)}</td>
              <td><StatusPill status={trade.artifact_status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
