import { CheckCircle2, CircleAlert, ShieldCheck } from "lucide-react";

import type { Availability, Overview } from "../../shared/api/types";
import { query } from "../../shared/api/client";
import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { PageHeader } from "../../shared/components/PageHeader";
import { Panel } from "../../shared/components/Panel";
import { StatusPill } from "../../shared/components/StatusPill";
import { formatDateTime, isoDayOffset } from "../../shared/formatters/dates";
import { formatPct } from "../../shared/formatters/numbers";
import type { OpportunityFunnel, OpportunityOutcomes } from "../opportunities/types";
import type { TradeList } from "../trades/types";

interface Ready {
  status: Availability;
  checked_at: string;
  read_only: boolean;
  execution_callable: boolean;
  sources: Array<{ source: string; status: Availability; readable: boolean }>;
}

export function DataQualityPage() {
  const ready = useApi<Ready>("/health/ready");
  const overview = useApi<Overview>("/api/v1/overview");
  const trades = useApi<TradeList>(query("/api/v1/trades", { start: isoDayOffset(-90), end: isoDayOffset(0), limit: 100 }));
  const funnel = useApi<OpportunityFunnel>("/api/v1/opportunities/funnel");
  const outcomes = useApi<OpportunityOutcomes>("/api/v1/opportunities/outcomes");
  const allIssues = [...(overview.data?.issues ?? []), ...(trades.data?.issues ?? []), ...(funnel.data?.issues ?? []), ...(outcomes.data?.issues ?? [])];
  const loading = ready.loading || overview.loading || trades.loading || funnel.loading || outcomes.loading;
  const error = ready.error || overview.error || trades.error || funnel.error || outcomes.error;
  return <>
    <PageHeader title="데이터 품질" description="Broker·report·evaluation·market 읽기면의 누락, 부분 상태와 coverage를 운영 관점에서 점검합니다." actions={ready.data && <StatusPill status={ready.data.status} />} />
    <DataState loading={loading} error={error} onRetry={() => { ready.refresh(); overview.refresh(); trades.refresh(); funnel.refresh(); outcomes.refresh(); }}>
      <div className="page-grid">
        <Panel title="Read-only 안전 경계" meta={formatDateTime(ready.data?.checked_at)} className="span-4">
          <div className="detail-stack"><div className="detail-row"><span>API read only</span><strong className="positive">{ready.data?.read_only ? "YES" : "NO"}</strong></div><div className="detail-row"><span>Execution callable</span><strong className={ready.data?.execution_callable ? "negative" : "positive"}>{ready.data?.execution_callable ? "YES" : "NO"}</strong></div><div className="detail-row"><span>Trading Core import</span><strong className="positive">NONE</strong></div></div>
        </Panel>
        <Panel title="Source root 상태" className="span-4">
          <div className="detail-stack">{ready.data?.sources.map((source) => <div className="detail-row" key={source.source}><span>{source.source}</span><strong><StatusPill status={source.status} /></strong></div>)}</div>
        </Panel>
        <Panel title="Coverage" className="span-4">
          <div className="detail-stack"><div className="detail-row"><span>거래 표본</span><strong>{trades.data?.provenance.sample_count ?? 0}건</strong></div><div className="detail-row"><span>기회 forward</span><strong>{formatPct((outcomes.data?.coverage ?? 0) * 100)}</strong></div><div className="detail-row"><span>Blocker forward</span><strong>{formatPct((funnel.data?.provenance.coverage ?? 0) * 100)}</strong></div><div className="detail-row"><span>거래 artifact 이슈</span><strong>{trades.data?.issue_count ?? 0}건</strong></div></div>
        </Panel>
        <Panel title="운영 점검 결과" meta={`${allIssues.length}건`} className="span-12">
          {allIssues.length ? <ul className="issue-list">{Array.from(new Set(allIssues)).slice(0, 100).map((issue) => <li key={issue}><CircleAlert size={13} /> {issue}</li>)}</ul> : <div className="callout"><CheckCircle2 size={15} /> 현재 API 읽기면에서 보고된 데이터 이상이 없습니다.</div>}
        </Panel>
        <Panel title="운영 원칙" className="span-12"><div className="callout"><ShieldCheck size={15} /> 이 화면은 기존 artifact를 읽기만 합니다. 오류 수정, 평가 재실행, 주문 또는 설정 변경 기능은 제공하지 않습니다.</div></Panel>
      </div>
    </DataState>
  </>;
}
