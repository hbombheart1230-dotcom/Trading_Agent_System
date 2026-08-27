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
import { formatPct, toneFor } from "../../shared/formatters/numbers";
import { StrategyChart } from "./StrategyChart";
import { StrategyPerformanceTable } from "./StrategyPerformanceTable";
import type { StrategyDimension, StrategyPerformance } from "./types";

const DIMENSIONS: Array<{ key: StrategyDimension; label: string }> = [{ key: "playbook", label: "Playbook" }, { key: "tactic", label: "Tactic" }, { key: "horizon", label: "Horizon" }, { key: "theme", label: "Theme" }];

export function StrategiesPage() {
  const [start, setStart] = useState(isoDayOffset(-45));
  const [end, setEnd] = useState(isoDayOffset(0));
  const [dimension, setDimension] = useState<StrategyDimension>("playbook");
  const data = useApi<StrategyPerformance>(query("/api/v1/strategies/performance", { start, end, dimension }));
  const top = data.data?.items.find((item) => item.resolved_count > 0);
  return <>
    <PageHeader title="전략" description="실현 거래를 playbook, tactic, horizon, theme별로 나누어 성과와 표본 신뢰도를 비교합니다." actions={<DateRange start={start} end={end} onChange={(a, b) => { setStart(a); setEnd(b); }} />} />
    <div className="toolbar" style={{ marginBottom: 13 }}><div className="segmented">{DIMENSIONS.map((item) => <button className={dimension === item.key ? "active" : ""} key={item.key} onClick={() => setDimension(item.key)}>{item.label}</button>)}</div>{data.data && <StatusPill status={data.data.status} />}</div>
    <DataState loading={data.loading} error={data.error} onRetry={data.refresh}>
      <MetricStrip items={[
        { label: "전체 거래", value: `${data.data?.trade_count ?? 0}건`, note: `${start} ~ ${end}` },
        { label: "수익률 확인", value: `${data.data?.resolved_count ?? 0}건`, note: `coverage ${formatPct((data.data?.provenance.coverage ?? 0) * 100)}` },
        { label: "최다 그룹", value: top?.label ?? "-", note: top ? `${top.trade_count}건` : "표본 없음" },
        { label: "최다 그룹 평균", value: formatPct(top?.average_return_pct, true), tone: toneFor(top?.average_return_pct), note: data.data?.cost_basis },
        { label: "Artifact 이슈", value: `${data.data?.issues.length ?? 0}건`, note: "누락 포함" },
      ]} />
    </DataState>
    <div className="page-grid" style={{ marginTop: 14 }}>
      <Panel title={`${DIMENSIONS.find((item) => item.key === dimension)?.label} 평균 수익률`} meta="표본 보유 그룹 상위 12개" className="span-6"><DataState loading={data.loading} error={data.error} empty={!data.data?.items.length}><StrategyChart items={data.data?.items ?? []} /></DataState></Panel>
      <Panel title="그룹별 상세" meta="mock broker net" className="span-6"><DataState loading={data.loading} error={data.error} empty={!data.data?.items.length}><StrategyPerformanceTable items={data.data?.items ?? []} /></DataState></Panel>
    </div>
  </>;
}
