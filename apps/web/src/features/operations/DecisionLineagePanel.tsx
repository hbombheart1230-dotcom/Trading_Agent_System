import { Bot, ChartNoAxesCombined, CheckCheck, Crosshair, ScanSearch } from "lucide-react";

import type { TradeDetail, TradeSummary } from "../trades/types";
import { formatNumber, formatPct, toneFor } from "../../shared/formatters/numbers";

interface Props {
  trades: TradeSummary[];
  selectedTradeId: string | null;
  onSelect: (tradeId: string) => void;
  detail: TradeDetail | null;
}

export function DecisionLineagePanel({ trades, selectedTradeId, onSelect, detail }: Props) {
  if (!trades.length) return <div className="empty-line">계보를 표시할 거래가 없습니다.</div>;
  const horizonChanged = Boolean(detail?.decisions.strategist_horizon && detail.decisions.commander_horizon && detail.decisions.strategist_horizon !== detail.decisions.commander_horizon);
  const stages = detail ? [
    { id: "strategist", label: "Strategist", icon: Bot, value: detail.decisions.playbook ?? detail.decisions.tactic_id ?? "근거 미확인", sub: `${detail.decisions.tactic_id ?? "tactic -"} · ${detail.decisions.strategist_horizon ?? "horizon -"}` },
    { id: "scanner", label: "Scanner", icon: ScanSearch, value: `Rank ${detail.decisions.scanner_rank ?? "-"} · ${formatNumber(detail.decisions.scanner_score, 3)}`, sub: detail.decisions.selection_basis ?? `chart fit ${formatNumber(detail.decisions.scanner_chart_fit_score, 3)}` },
    { id: "monitor", label: "Monitor", icon: Crosshair, value: detail.decisions.monitor_entry_reason ?? "진입 근거 미확인", sub: detail.decisions.monitor_exit_trigger ? `exit: ${detail.decisions.monitor_exit_trigger}` : "청산 trigger 미확인" },
    { id: "commander", label: "Commander", icon: CheckCheck, value: detail.decisions.commander_horizon ?? "horizon 미확인", sub: horizonChanged ? "Strategist horizon 조정" : "Strategist horizon 유지 또는 증거 부족" },
    { id: "execution", label: "Execution", icon: ChartNoAxesCombined, value: `${detail.trade.result ?? detail.trade.status} · ${formatPct(detail.trade.realized_return_pct, true)}`, sub: `보유 ${Math.round(detail.trade.hold_seconds ?? 0)}초 · broker ${detail.integrity.broker_reconciliation_status ?? "미확인"}` },
  ] : [];
  return <div className="decision-lineage-wrap">
    <div className="operations-select-row">
      <label>거래 선택<select value={selectedTradeId ?? ""} onChange={(event) => onSelect(event.target.value)}>{trades.map((trade) => <option value={trade.trade_id} key={trade.trade_id}>{trade.day} · {trade.symbol} {trade.symbol_name ?? ""}</option>)}</select></label>
      {detail && <span className={toneFor(detail.trade.realized_return_pct)}>{formatPct(detail.trade.realized_return_pct, true)}</span>}
    </div>
    <div className="decision-lineage">
      {stages.map((stage) => <article key={stage.id}>
        <span className="lineage-icon"><stage.icon size={16} /></span>
        <small>{stage.label}</small>
        <strong>{stage.value}</strong>
        <p>{stage.sub}</p>
      </article>)}
    </div>
    {detail && <div className="lineage-source-strip">
      <span>Artifact {detail.integrity.status}</span>
      <span>Completeness {formatNumber(detail.integrity.completeness_score, 2)}</span>
      <span>Evaluation {detail.integrity.evaluation_eligible ? "eligible" : detail.integrity.exclusion_reason ?? "excluded"}</span>
    </div>}
  </div>;
}
