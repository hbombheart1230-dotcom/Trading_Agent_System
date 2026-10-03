import type { TradeDetail } from "../trades/types";
import { formatPct, toneFor } from "../../shared/formatters/numbers";
import type { OperationsDashboard } from "./types";

export function OperationsComparisonPanel({ dashboard, detail }: { dashboard: OperationsDashboard; detail: TradeDetail | null }) {
  const observed = detail?.post_exit.filter((row) => row.return_pct !== null) ?? [];
  const best = observed.reduce<(typeof observed)[number] | null>((current, row) => !current || (row.return_pct ?? -Infinity) > (current.return_pct ?? -Infinity) ? row : current, null);
  const actual = detail?.trade.realized_return_pct ?? null;
  const opportunityDelta = best?.return_pct !== null && best?.return_pct !== undefined && actual !== null ? best.return_pct - actual : null;
  return <div className="operations-comparison-stack">
    <div className="data-table-wrap"><table className="data-table operations-comparison-table"><thead><tr><th>운영 기준</th><th>{dashboard.day}</th><th>{dashboard.previous_day ?? "이전 없음"}</th><th>변화</th></tr></thead><tbody>
      {dashboard.comparison.map((row) => <tr key={row.metric}><td><strong>{row.metric}</strong></td><td>{row.current_value ?? "-"}</td><td>{row.previous_value ?? "-"}</td><td><span className={`comparison-change change-${row.change}`}>{row.change}</span></td></tr>)}
    </tbody></table></div>
    <div className="trade-outcome-comparison">
      <div><span>실제 청산</span><strong className={toneFor(actual)}>{formatPct(actual, true)}</strong><small>{detail?.trade.trade_id ?? "거래 선택 필요"}</small></div>
      <div><span>매도 후 최선 checkpoint</span><strong className={toneFor(best?.return_pct)}>{formatPct(best?.return_pct, true)}</strong><small>{best?.horizon ?? "관측 없음"}</small></div>
      <div><span>청산 기회 차이</span><strong className={toneFor(opportunityDelta)}>{formatPct(opportunityDelta, true)}</strong><small>사후 관측 · 행동 근거 아님</small></div>
    </div>
  </div>;
}
