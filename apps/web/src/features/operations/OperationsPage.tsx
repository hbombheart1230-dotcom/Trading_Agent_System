import { useEffect, useMemo, useState } from "react";

import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { MetricStrip } from "../../shared/components/MetricStrip";
import { PageHeader } from "../../shared/components/PageHeader";
import { Panel } from "../../shared/components/Panel";
import { StatusPill } from "../../shared/components/StatusPill";
import type { TradeDetail, TradeList } from "../trades/types";
import { DecisionLineagePanel } from "./DecisionLineagePanel";
import { OperationsAlertPanel } from "./OperationsAlertPanel";
import { OperationsComparisonPanel } from "./OperationsComparisonPanel";
import { OperationsTimeline } from "./OperationsTimeline";
import type { OperationsDashboard } from "./types";

export function OperationsPage() {
  const dashboard = useApi<OperationsDashboard>("/api/v1/operations");
  const trades = useApi<TradeList>("/api/v1/trades?limit=20");
  const [selectedTradeId, setSelectedTradeId] = useState<string | null>(null);
  useEffect(() => {
    if (!selectedTradeId && trades.data?.items.length) setSelectedTradeId(trades.data.items[0].trade_id);
  }, [selectedTradeId, trades.data]);
  const detail = useApi<TradeDetail>(selectedTradeId ? `/api/v1/trades/${encodeURIComponent(selectedTradeId)}` : null);
  const changeCount = useMemo(() => dashboard.data?.comparison.filter((row) => row.change === "변경").length ?? 0, [dashboard.data]);

  return <>
    <PageHeader title="운영 관제" description="운영 흐름, 이상 징후, 거래 의사결정 계보와 전후 차이를 읽기 전용으로 확인합니다." actions={dashboard.data && <><StatusPill status={dashboard.data.status} /><span className="muted">기준 {dashboard.data.day}</span></>} />
    <DataState loading={dashboard.loading} error={dashboard.error} empty={!dashboard.data} onRetry={dashboard.refresh}>
      {dashboard.data && <MetricStrip items={[
        { label: "운영 이벤트", value: `${dashboard.data.timeline.length}건`, note: "장전·거래·장후" },
        { label: "확인 알림", value: `${dashboard.data.alerts.length}건`, note: "observation only" },
        { label: "당일 거래", value: `${dashboard.data.trade_count}건`, note: dashboard.data.day },
        { label: "전일 대비 변경", value: `${changeCount}항목`, note: dashboard.data.previous_day ?? "비교일 없음" },
        { label: "제어 권한", value: "없음", note: "read-only" },
      ]} />}
    </DataState>
    {dashboard.data && <div className="page-grid operations-page-grid" style={{ marginTop: 14 }}>
      <Panel title="운영 타임라인" meta="예정 → 실제 → 근거" className="span-7"><OperationsTimeline items={dashboard.data.timeline} onSelectTrade={setSelectedTradeId} /></Panel>
      <Panel title="이상 징후" meta={`${dashboard.data.alerts.length}건`} className="span-5"><OperationsAlertPanel alerts={dashboard.data.alerts} /></Panel>
      <Panel title="거래 의사결정 계보" meta="Strategist → Scanner → Monitor → Commander → Execution" className="span-12">
        <DataState loading={trades.loading || detail.loading} error={trades.error || detail.error} onRetry={() => { trades.refresh(); detail.refresh(); }}>
          <DecisionLineagePanel trades={trades.data?.items ?? []} selectedTradeId={selectedTradeId} onSelect={setSelectedTradeId} detail={detail.data} />
        </DataState>
      </Panel>
      <Panel title="운영 및 결과 비교" meta="전일 차이 · 청산 후 관측" className="span-12"><OperationsComparisonPanel dashboard={dashboard.data} detail={detail.data} /></Panel>
      {dashboard.data.issues.length > 0 && <Panel title="데이터 주의사항" meta={`${dashboard.data.issues.length}건`} className="span-12"><ul className="issue-list">{dashboard.data.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul></Panel>}
    </div>}
  </>;
}
