import { AlertTriangle, Clock3, Database, WalletCards } from "lucide-react";

import type { Overview } from "../../shared/api/types";
import { query } from "../../shared/api/client";
import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { MetricStrip } from "../../shared/components/MetricStrip";
import { PageHeader } from "../../shared/components/PageHeader";
import { Panel } from "../../shared/components/Panel";
import { StatusPill } from "../../shared/components/StatusPill";
import { formatDateTime, isoDayOffset } from "../../shared/formatters/dates";
import { formatKrw, formatNumber, formatPct, formatRatioPct, toneFor } from "../../shared/formatters/numbers";
import { PerformanceChart } from "../performance/PerformanceChart";
import type { PerformanceSeries } from "../performance/types";

export function OverviewPage() {
  const overview = useApi<Overview>("/api/v1/overview");
  const series = useApi<PerformanceSeries>(query("/api/v1/performance/series", {
    start: isoDayOffset(-74),
    end: isoDayOffset(0),
  }));
  const performance = overview.data?.performance;
  const portfolio = overview.data?.portfolio;

  return (
    <>
      <PageHeader title="운영 요약" description="오늘의 거래 상태, 실현 성과, 보유 위험과 데이터 신뢰도를 한 화면에서 확인합니다." actions={overview.data && <><StatusPill status={overview.data.status} /><span className="muted">기준 {overview.data.day}</span></>} />
      <DataState loading={overview.loading} error={overview.error} onRetry={overview.refresh}>
        <MetricStrip items={[
          { label: "당일 실현손익", value: formatKrw(performance?.realized_pnl.value), tone: toneFor(performance?.realized_pnl.value), note: performance?.cost_basis ?? "MOCK_BROKER_NET" },
          { label: "승률", value: formatRatioPct(performance?.win_rate.value), note: `${performance?.counts.win_count ?? 0}승 / ${performance?.counts.loss_count ?? 0}패` },
          { label: "평균 거래수익률", value: formatPct(performance?.average_trade_return.value, true), tone: toneFor(performance?.average_trade_return.value), note: `확인 ${performance?.counts.resolved_count ?? 0} / 전체 ${performance?.counts.trade_count ?? 0}` },
          { label: "Profit Factor", value: formatNumber(performance?.profit_factor.value), note: "mock broker net" },
          { label: "현재 보유", value: `${portfolio?.position_count ?? 0}종목`, note: `평가 ${formatKrw(portfolio?.total_market_value.value)}` },
        ]} />
      </DataState>

      <div className="page-grid" style={{ marginTop: 14 }}>
        <Panel title="누적 실현손익과 일별 평균 수익률" meta="최근 75일 · mock broker net" className="span-8">
          <DataState loading={series.loading} error={series.error} empty={!series.data?.points.length} onRetry={series.refresh}>
            <PerformanceChart points={series.data?.points ?? []} />
          </DataState>
        </Panel>
        <Panel title="운영 상태" meta={overview.data ? formatDateTime(overview.data.generated_at) : undefined} className="span-4">
          <div className="detail-stack">
            <div className="detail-row"><span><Database size={14} /> 데이터 상태</span><strong>{overview.data ? <StatusPill status={overview.data.status} /> : "-"}</strong></div>
            <div className="detail-row"><span><WalletCards size={14} /> 포트폴리오 권위</span><strong>{portfolio?.authority ?? "-"}</strong></div>
            <div className="detail-row"><span><Clock3 size={14} /> 최종 갱신</span><strong>{formatDateTime(overview.data?.generated_at)}</strong></div>
            <div className="detail-row"><span>실행 모드</span><strong>{overview.data?.mode ?? "-"}</strong></div>
            <div className="detail-row"><span>Broker reconciliation</span><strong>{portfolio?.reconciliation_available ? "확인" : "미확인"}</strong></div>
          </div>
        </Panel>

        <Panel title="보유 포지션" meta={`${portfolio?.position_count ?? 0}종목`} className="span-7">
          {!portfolio?.positions.length ? <div className="empty-line">현재 표시할 잔존 포지션이 없습니다.</div> : (
            <div className="data-table-wrap"><table className="data-table"><thead><tr><th>종목</th><th>수량</th><th>평균가</th><th>현재가</th><th>평가손익</th><th>상태</th></tr></thead><tbody>{portfolio.positions.map((position) => <tr key={position.symbol}><td className="symbol-cell"><strong>{position.symbol_name ?? position.symbol}</strong><span>{position.symbol}</span></td><td>{formatNumber(position.quantity, 0)}</td><td>{formatNumber(position.average_price, 0)}</td><td>{formatNumber(position.current_price, 0)}</td><td className={toneFor(position.unrealized_pnl)}>{formatKrw(position.unrealized_pnl)}</td><td>{position.lifecycle_status ?? "-"}</td></tr>)}</tbody></table></div>
          )}
        </Panel>
        <Panel title="데이터 주의사항" meta={`${overview.data?.issues.length ?? 0}건`} className="span-5">
          {overview.data?.issues.length ? <ul className="issue-list">{overview.data.issues.map((issue) => <li key={issue}><AlertTriangle size={13} /> {issue}</li>)}</ul> : <div className="callout">현재 운영 요약에서 보고된 데이터 이상은 없습니다.</div>}
        </Panel>
      </div>
    </>
  );
}
