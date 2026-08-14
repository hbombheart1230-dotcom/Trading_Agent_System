import { useState } from "react";

import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { MetricStrip } from "../../shared/components/MetricStrip";
import { PageHeader } from "../../shared/components/PageHeader";
import { Panel } from "../../shared/components/Panel";
import { StatusPill } from "../../shared/components/StatusPill";
import { formatDateTime } from "../../shared/formatters/dates";
import { formatNumber, formatPct, toneFor } from "../../shared/formatters/numbers";
import { BlockerChart } from "./BlockerChart";
import type { OpportunityFunnel, OpportunityOutcomes } from "./types";

const HORIZONS = ["+5m", "+15m", "+30m", "+60m", "EOD"];

export function OpportunitiesPage() {
  const [horizon, setHorizon] = useState("+30m");
  const funnel = useApi<OpportunityFunnel>("/api/v1/opportunities/funnel");
  const outcomes = useApi<OpportunityOutcomes>("/api/v1/opportunities/outcomes");
  return (
    <>
      <PageHeader title="기회" description="실제 주문과 분리된 후보 신호, 차단 사유와 forward 가격 경로를 관측합니다." actions={<><span className="readonly-flag">SHADOW / OBSERVATION</span>{funnel.data && <StatusPill status={funnel.data.status} />}</>} />
      <DataState loading={funnel.loading} error={funnel.error} onRetry={funnel.refresh}>
        <MetricStrip items={[
          { label: "원본 후보", value: `${funnel.data?.raw_candidate_count ?? 0}건`, note: `중복 ${funnel.data?.duplicate_count ?? 0}건` },
          { label: "독립 후보", value: `${funnel.data?.deduplicated_candidate_count ?? 0}건`, note: "deduplicated" },
          { label: "당일 신호", value: `${funnel.data?.signal_count ?? 0}건`, note: `현재 종목 ${funnel.data?.current_signal_count ?? 0}` },
          { label: "Probe 가능", value: `${funnel.data?.probe_candidate_count ?? 0}종목`, tone: "positive", note: "주문 실행 없음" },
          { label: "Forward coverage", value: formatPct((outcomes.data?.coverage ?? 0) * 100), note: `${outcomes.data?.observed_checkpoint_count ?? 0} / ${outcomes.data?.expected_checkpoint_count ?? 0}` },
        ]} />
      </DataState>
      <div className="page-grid" style={{ marginTop: 14 }}>
        <Panel title="현재 후보 신호" meta={funnel.data?.day} className="span-7">
          <DataState loading={funnel.loading} error={funnel.error} empty={!funnel.data?.current_signals.length} onRetry={funnel.refresh}>
            <div className="data-table-wrap"><table className="data-table"><thead><tr><th>종목</th><th>상태</th><th>점수</th><th>VWAP 거리</th><th>거래량</th><th>시장 대비</th><th>판정</th></tr></thead><tbody>{funnel.data?.current_signals.map((signal) => <tr key={signal.symbol}><td className="symbol-cell"><strong>{signal.symbol}</strong><span>{formatDateTime(signal.observed_at)}</span></td><td>{signal.state ?? "-"}</td><td>{formatNumber(signal.score, 3)}</td><td className={toneFor(signal.vwap_distance_pct)}>{formatPct(signal.vwap_distance_pct, true)}</td><td>{formatNumber(signal.volume_ratio, 2)}x</td><td className={toneFor(signal.market_relative_strength)}>{formatNumber(signal.market_relative_strength, 3)}</td><td>{signal.probe_candidate ? <span className="status-pill status-available">PROBE</span> : signal.probe_near_miss ? <span className="status-pill status-partial">NEAR MISS</span> : <span className="muted">관찰</span>}</td></tr>)}</tbody></table></div>
          </DataState>
        </Panel>
        <Panel title="차단 사유 분포" meta="forward 관측 포함" className="span-5">
          <DataState loading={funnel.loading} error={funnel.error} empty={!funnel.data?.blockers.length}><BlockerChart blockers={funnel.data?.blockers ?? []} /></DataState>
        </Panel>
        <Panel title="장초반 후보 Forward 결과" meta="비용 기준 분리 · 실현 거래 아님" className="span-12">
          <div className="segmented" style={{ marginBottom: 12 }}>{HORIZONS.map((item) => <button className={horizon === item ? "active" : ""} key={item} onClick={() => setHorizon(item)}>{item}</button>)}</div>
          <DataState loading={outcomes.loading} error={outcomes.error} empty={!outcomes.data?.outcomes.length} onRetry={outcomes.refresh}>
            <div className="data-table-wrap"><table className="data-table"><thead><tr><th>종목</th><th>관측 시각</th><th>Score</th><th>Gross</th><th>Live-equivalent</th><th>Mock net</th><th>MFE</th><th>MAE</th></tr></thead><tbody>{outcomes.data?.outcomes.map((outcome) => { const point = outcome.checkpoints.find((item) => item.horizon === horizon); return <tr key={outcome.opportunity_id}><td className="symbol-cell"><strong>{outcome.symbol_name ?? outcome.symbol}</strong><span>{outcome.symbol} · Rank {outcome.rank ?? "-"}</span></td><td>{formatDateTime(outcome.observed_at)}</td><td>{formatNumber(outcome.score, 3)}</td><td className={toneFor(point?.gross_return_pct)}>{formatPct(point?.gross_return_pct, true)}</td><td className={toneFor(point?.live_equivalent_net_return_pct)}>{formatPct(point?.live_equivalent_net_return_pct, true)}</td><td className={toneFor(point?.mock_broker_net_return_pct)}>{formatPct(point?.mock_broker_net_return_pct, true)}</td><td className="positive">{formatPct(point?.maximum_favorable_excursion_pct, true)}</td><td className="negative">{formatPct(point?.maximum_adverse_excursion_pct)}</td></tr>; })}</tbody></table></div>
          </DataState>
        </Panel>
      </div>
    </>
  );
}
