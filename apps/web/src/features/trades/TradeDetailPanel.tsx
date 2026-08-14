import { DataState } from "../../shared/components/DataState";
import { Panel } from "../../shared/components/Panel";
import { StatusPill } from "../../shared/components/StatusPill";
import { formatDateTime } from "../../shared/formatters/dates";
import { formatNumber, formatPct, toneFor } from "../../shared/formatters/numbers";
import type { ApiState } from "../../shared/api/useApi";
import type { TradeDetail } from "./types";

export function TradeDetailPanel({ state }: { state: ApiState<TradeDetail> }) {
  const detail = state.data;
  return (
    <Panel title="거래 의사결정 계보" meta={detail && <StatusPill status={detail.integrity.status} />} className="span-12">
      <DataState loading={state.loading} error={state.error} onRetry={state.refresh} empty={!detail}>
        {detail && <div className="split-view">
          <div className="detail-stack">
            <div className="detail-row"><span>Playbook</span><strong>{detail.decisions.playbook ?? "-"}</strong></div>
            <div className="detail-row"><span>Tactic</span><strong>{detail.decisions.tactic_id ?? "-"}</strong></div>
            <div className="detail-row"><span>Strategist horizon</span><strong>{detail.decisions.strategist_horizon ?? "-"}</strong></div>
            <div className="detail-row"><span>Commander horizon</span><strong>{detail.decisions.commander_horizon ?? "-"}</strong></div>
            <div className="detail-row"><span>Scanner score</span><strong>{formatNumber(detail.decisions.scanner_score, 3)}</strong></div>
            <div className="detail-row"><span>Chart fit</span><strong>{formatNumber(detail.decisions.scanner_chart_fit_score, 3)}</strong></div>
            <div className="detail-row"><span>진입 근거</span><strong>{detail.decisions.monitor_entry_reason ?? "-"}</strong></div>
            <div className="detail-row"><span>청산 근거</span><strong>{detail.decisions.monitor_exit_trigger ?? "-"}</strong></div>
            <div className="detail-row"><span>Broker truth</span><strong>{detail.integrity.broker_reconciliation_status ?? "-"}</strong></div>
          </div>
          <div>
            <h3 style={{ fontSize: 12 }}>타임라인</h3>
            <div className="data-table-wrap"><table className="data-table"><thead><tr><th>시각</th><th>단계</th><th>행동</th><th>가격</th><th>근거</th></tr></thead><tbody>{detail.timeline.map((event, index) => <tr key={`${event.timestamp}-${index}`}><td>{formatDateTime(event.timestamp)}</td><td>{event.stage}</td><td><strong>{event.action}</strong></td><td>{formatNumber(event.price, 0)}</td><td>{event.reason ?? "-"}</td></tr>)}</tbody></table></div>
            <h3 style={{ marginTop: 18, fontSize: 12 }}>매도 후 가격 경로</h3>
            {!detail.post_exit.length ? <div className="empty-line">관측된 checkpoint가 없습니다.</div> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>구간</th><th>상태</th><th>관측가</th><th>매도 대비</th></tr></thead><tbody>{detail.post_exit.map((point) => <tr key={point.horizon}><td><strong>{point.horizon}</strong></td><td>{point.status}</td><td>{formatNumber(point.price, 0)}</td><td className={toneFor(point.return_pct)}>{formatPct(point.return_pct, true)}</td></tr>)}</tbody></table></div>}
          </div>
        </div>}
      </DataState>
    </Panel>
  );
}
