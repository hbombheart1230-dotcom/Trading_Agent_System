import { formatDateTime, formatDuration } from "../../shared/formatters/dates";
import { formatKrw, formatPct, toneFor } from "../../shared/formatters/numbers";
import { StatusPill } from "../../shared/components/StatusPill";
import type { TradeSummary } from "./types";

interface Props {
  items: TradeSummary[];
  selectedId: string | null;
  onSelect: (tradeId: string) => void;
}

export function TradeTable({ items, selectedId, onSelect }: Props) {
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead><tr><th>거래일 / 종목</th><th>진입</th><th>보유</th><th>전략</th><th>순위</th><th>실현손익</th><th>수익률</th><th>Artifact</th></tr></thead>
        <tbody>
          {items.map((trade) => (
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
