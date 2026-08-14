import { useState } from "react";

import { query } from "../../shared/api/client";
import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { DateRange } from "../../shared/components/DateRange";
import { MetricStrip } from "../../shared/components/MetricStrip";
import { PageHeader } from "../../shared/components/PageHeader";
import { Panel } from "../../shared/components/Panel";
import { StatusPill } from "../../shared/components/StatusPill";
import { isoDayOffset } from "../../shared/formatters/dates";
import { formatKrw, formatNumber, formatPct, formatRatioPct, toneFor } from "../../shared/formatters/numbers";
import { PerformanceChart } from "./PerformanceChart";
import type { PerformanceSeries, PerformanceSummary } from "./types";

export function PerformancePage() {
  const [start, setStart] = useState(isoDayOffset(-74));
  const [end, setEnd] = useState(isoDayOffset(0));
  const params = { start, end };
  const summary = useApi<PerformanceSummary>(query("/api/v1/performance/summary", params));
  const series = useApi<PerformanceSeries>(query("/api/v1/performance/series", params));
  const data = summary.data;

  return (
    <>
      <PageHeader title="성과" description="실현 거래의 mock broker net 기준 성과와 데이터 coverage를 기간별로 비교합니다." actions={<DateRange start={start} end={end} onChange={(nextStart, nextEnd) => { setStart(nextStart); setEnd(nextEnd); }} />} />
      <DataState loading={summary.loading} error={summary.error} onRetry={summary.refresh}>
        <MetricStrip items={[
          { label: "실현손익", value: formatKrw(data?.realized_pnl.value), tone: toneFor(data?.realized_pnl.value), note: data?.cost_basis },
          { label: "승률", value: formatRatioPct(data?.win_rate.value), note: `${data?.counts.win_count ?? 0}승 ${data?.counts.loss_count ?? 0}패 ${data?.counts.flat_count ?? 0}보합` },
          { label: "평균 수익률", value: formatPct(data?.average_trade_return.value, true), tone: toneFor(data?.average_trade_return.value), note: `표본 ${data?.counts.resolved_count ?? 0}건` },
          { label: "Profit Factor", value: formatNumber(data?.profit_factor.value), note: "이익합 / 손실합" },
          { label: "최대 낙폭", value: formatPct(data?.max_drawdown.value), tone: "negative", note: "누적 거래수익 기준" },
        ]} />
      </DataState>
      <div className="page-grid" style={{ marginTop: 14 }}>
        <Panel title="성과 추이" meta={data && <StatusPill status={data.status} />} className="span-8">
          <DataState loading={series.loading} error={series.error} empty={!series.data?.points.length} onRetry={series.refresh}><PerformanceChart points={series.data?.points ?? []} /></DataState>
        </Panel>
        <Panel title="표본과 비용 가용성" className="span-4">
          <div className="detail-stack">
            <div className="detail-row"><span>전체 거래</span><strong>{data?.counts.trade_count ?? 0}건</strong></div>
            <div className="detail-row"><span>수익률 확인</span><strong>{data?.counts.resolved_count ?? 0}건</strong></div>
            <div className="detail-row"><span>미확정</span><strong>{data?.counts.unresolved_count ?? 0}건</strong></div>
            <div className="detail-row"><span>소스 일수</span><strong>{data?.source_day_count ?? 0}일</strong></div>
            <div className="detail-row"><span>Gross PnL</span><strong><StatusPill status={data?.gross_pnl.status ?? "UNAVAILABLE"} /></strong></div>
            <div className="detail-row"><span>명시 비용</span><strong><StatusPill status={data?.total_cost.status ?? "UNAVAILABLE"} /></strong></div>
          </div>
        </Panel>
        <Panel title="이익·손실 분포" className="span-12">
          <div className="kpi-pair">
            <div className="compact-kpi"><span>평균 이익</span><strong className="positive">{formatPct(data?.average_gain.value, true)}</strong></div>
            <div className="compact-kpi" style={{ borderLeftColor: "var(--red)" }}><span>평균 손실</span><strong className="negative">{formatPct(data?.average_loss.value)}</strong></div>
          </div>
        </Panel>
      </div>
    </>
  );
}
