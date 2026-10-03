import { formatDateTime } from "../../shared/formatters/dates";
import { formatNumber, formatPct, toneFor } from "../../shared/formatters/numbers";
import { SortableHeaderRow, type SortableColumn } from "../../shared/tables/SortableHeaderRow";
import { timestamp, type SortValue } from "../../shared/tables/sorting";
import { useSortableRows } from "../../shared/tables/useSortableRows";
import type { OpportunitySignal } from "./types";

type SignalSortKey = "symbol" | "state" | "score" | "vwap" | "volume" | "relative" | "decision";
const COLUMNS: Array<SortableColumn<SignalSortKey>> = [
  { key: "symbol", label: "종목" }, { key: "state", label: "상태" }, { key: "score", label: "점수" },
  { key: "vwap", label: "VWAP 거리" }, { key: "volume", label: "거래량" },
  { key: "relative", label: "시장 대비" }, { key: "decision", label: "판정" },
];

function sortValue(signal: OpportunitySignal, key: SignalSortKey): SortValue {
  if (key === "symbol") return `${signal.symbol}|${timestamp(signal.observed_at) ?? ""}`;
  if (key === "state") return signal.state;
  if (key === "score") return signal.score;
  if (key === "vwap") return signal.vwap_distance_pct;
  if (key === "volume") return signal.volume_ratio;
  if (key === "relative") return signal.market_relative_strength;
  return signal.probe_candidate ? 2 : signal.probe_near_miss ? 1 : 0;
}

export function OpportunitySignalTable({ signals }: { signals: OpportunitySignal[] }) {
  const sorted = useSortableRows(signals, sortValue);
  return <div className="data-table-wrap"><table className="data-table sortable-table">
    <thead><SortableHeaderRow columns={COLUMNS} sort={sorted.sort} onSort={sorted.toggleSort} /></thead>
    <tbody>{sorted.rows.map((signal) => <tr key={signal.symbol}><td className="symbol-cell"><strong>{signal.symbol}</strong><span>{formatDateTime(signal.observed_at)}</span></td><td>{signal.state ?? "-"}</td><td>{formatNumber(signal.score, 3)}</td><td className={toneFor(signal.vwap_distance_pct)}>{formatPct(signal.vwap_distance_pct, true)}</td><td>{formatNumber(signal.volume_ratio, 2)}x</td><td className={toneFor(signal.market_relative_strength)}>{formatNumber(signal.market_relative_strength, 3)}</td><td>{signal.probe_candidate ? <span className="status-pill status-available">PROBE</span> : signal.probe_near_miss ? <span className="status-pill status-partial">NEAR MISS</span> : <span className="muted">관찰</span>}</td></tr>)}</tbody>
  </table></div>;
}
