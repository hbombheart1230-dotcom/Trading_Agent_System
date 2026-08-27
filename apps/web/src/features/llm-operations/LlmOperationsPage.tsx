import { CircleAlert, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { query } from "../../shared/api/client";
import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { MetricStrip } from "../../shared/components/MetricStrip";
import { PageHeader } from "../../shared/components/PageHeader";
import { Panel } from "../../shared/components/Panel";
import { StatusPill } from "../../shared/components/StatusPill";
import { formatDateTime, isoDayOffset } from "../../shared/formatters/dates";
import { formatNumber, formatPct } from "../../shared/formatters/numbers";
import { issueLabel } from "./labels";
import { LlmStageChart } from "./LlmStageChart";
import { ModelRouteTable } from "./ModelRouteTable";
import { RecentCallTable } from "./RecentCallTable";
import { StageUsageTable } from "./StageUsageTable";
import type { LlmOperations } from "./types";

function seconds(value: number | null) {
  return value == null ? "-" : `${formatNumber(value / 1000, 1)}초`;
}

export function LlmOperationsPage() {
  const [day, setDay] = useState(isoDayOffset(0));
  const data = useApi<LlmOperations>(query("/api/v1/llm/operations", { day }));
  const actions = <div className="toolbar"><label className="single-date"><span>조회일</span><input type="date" value={day} onChange={(event) => setDay(event.target.value)} /></label><button className="icon-button" onClick={data.refresh} title="LLM 운영 데이터 갱신"><RefreshCw size={17} /></button>{data.data && <StatusPill status={data.data.status} />}</div>;
  return <>
    <PageHeader title="LLM 운영" description="OpenRouter 역할별 모델, 전략가 단계 호출, 성공 상태와 최근 응답 지연을 한 화면에서 확인합니다." actions={actions} />
    <DataState loading={data.loading} error={data.error} onRetry={data.refresh}>
      <MetricStrip items={[
        { label: "당일 LLM 호출", value: `${data.data?.total_calls ?? 0}회`, note: `${data.data?.provider ?? "OpenRouter"} · ${day}` },
        { label: "호출 성공률", value: formatPct(data.data?.success_rate != null ? data.data.success_rate * 100 : null), tone: (data.data?.failure_count ?? 0) > 0 ? "negative" : "positive", note: `실패 ${data.data?.failure_count ?? 0}회` },
        { label: "최근 평균 지연", value: seconds(data.data?.latency.average_ms ?? null), note: `${data.data?.latency.observed_count ?? 0}건 bounded 관측` },
        { label: "최근 P95 지연", value: seconds(data.data?.latency.p95_ms ?? null), note: `최대 ${seconds(data.data?.latency.maximum_ms ?? null)}` },
        { label: "토큰·비용", value: data.data?.token_usage.status === "AVAILABLE" ? formatNumber(data.data.token_usage.total_tokens) : "집계 불가", note: "미기록 값을 0으로 표시하지 않음" },
      ]} />
      <div className="page-grid" style={{ marginTop: 14 }}>
        <Panel title="역할별 모델 라우팅" meta="설정과 당일 실사용 분리" className="span-12 panel-flush"><ModelRouteTable roles={data.data?.roles ?? []} /></Panel>
        <Panel title="전략가 단계별 호출" meta={`${data.data?.stages.length ?? 0}개 단계`} className="span-6"><LlmStageChart stages={data.data?.stages ?? []} /></Panel>
        <Panel title="단계별 상세" meta="artifact 기준" className="span-6 panel-flush"><StageUsageTable stages={data.data?.stages ?? []} /></Panel>
        <Panel title="최근 OpenRouter 호출" meta={data.data?.latency.recent_window_only ? "최근 bounded event window" : "전체 관측"} className="span-8 panel-flush"><DataState loading={false} error={null} empty={!data.data?.recent_calls.length}><RecentCallTable calls={data.data?.recent_calls ?? []} /></DataState></Panel>
        <Panel title="계측 상태" meta={formatDateTime(data.data?.generated_at)} className="span-4"><div className="detail-stack"><div className="detail-row"><span>호출 artifact</span><strong>{data.data?.total_calls ?? 0}건</strong></div><div className="detail-row"><span>지연 coverage</span><strong>{formatPct((data.data?.latency.coverage ?? 0) * 100)}</strong></div><div className="detail-row"><span>토큰 상태</span><strong>{data.data?.token_usage.status ?? "-"}</strong></div><div className="detail-row"><span>원본 노출</span><strong className="positive">차단</strong></div></div></Panel>
        {!!data.data?.issues.length && <Panel title="확인 필요" meta={`${data.data.issues.length}건`} className="span-12"><ul className="issue-list">{data.data.issues.map((issue) => <li key={issue}><CircleAlert size={13} /> {issueLabel(issue)}</li>)}</ul></Panel>}
        <Panel title="보안 경계" className="span-12"><div className="callout"><ShieldCheck size={15} /> API 키, 프롬프트, 응답 원문과 내부 artifact 경로는 이 화면과 API 응답에서 제외됩니다.</div></Panel>
      </div>
    </DataState>
  </>;
}
