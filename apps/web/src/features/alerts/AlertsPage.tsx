import { useState } from "react";

import { query } from "../../shared/api/client";
import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { MetricStrip } from "../../shared/components/MetricStrip";
import { PageHeader } from "../../shared/components/PageHeader";
import { Panel } from "../../shared/components/Panel";
import { StatusPill } from "../../shared/components/StatusPill";
import { isoDayOffset } from "../../shared/formatters/dates";
import { AnomalyTable } from "./AnomalyTable";
import { formatIssue } from "./labels";
import type { AnomalyResponse } from "./types";

export function AlertsPage() {
  const [day, setDay] = useState(isoDayOffset(0));
  const response = useApi<AnomalyResponse>(query("/api/v1/anomalies", { day }));

  return (
    <>
      <PageHeader
        title="운영 알림"
        description="데이터 신뢰성, 반복 손실, 단기 손실 청산, 비용과 shadow 기회 누락을 행동 변경 없이 감시합니다."
        actions={<><label className="single-date">거래일<input type="date" value={day} onChange={(event) => setDay(event.target.value)} /></label>{response.data && <StatusPill status={response.data.status} />}</>}
      />
      <DataState loading={response.loading} error={response.error} onRetry={response.refresh}>
        <MetricStrip items={[
          { label: "긴급", value: `${response.data?.critical_count ?? 0}건`, tone: response.data?.critical_count ? "negative" : "positive", note: "즉시 상태 확인" },
          { label: "주의", value: `${response.data?.warning_count ?? 0}건`, tone: response.data?.warning_count ? "negative" : "neutral", note: "운영 검토 필요" },
          { label: "관찰", value: `${response.data?.watch_count ?? 0}건`, note: "shadow evidence" },
          { label: "평가 거래", value: `${response.data?.evaluated_trade_count ?? 0}건`, note: "broker truth read model" },
          { label: "평가 후보", value: `${response.data?.evaluated_opportunity_count ?? 0}건`, note: response.data?.behavior_effect ?? "OBSERVATION_ONLY" },
        ]} />
      </DataState>
      <div className="page-grid" style={{ marginTop: 14 }}>
        <Panel title="현재 운영 신호" meta={`${response.data?.items.length ?? 0}건 · ${response.data?.policy_version ?? "-"}`} className="span-12">
          <DataState loading={response.loading} error={response.error} empty={!response.data?.items.length} emptyText="현재 고정 정책에서 탐지된 운영 이상이 없습니다." onRetry={response.refresh}>
            <AnomalyTable items={response.data?.items ?? []} />
          </DataState>
        </Panel>
        {response.data?.issues.length ? <Panel title="계측 주의사항" meta={`${response.data.issues.length}건`} className="span-12"><ul className="issue-list">{response.data.issues.map((issue) => <li key={issue}>{formatIssue(issue)}</li>)}</ul></Panel> : null}
      </div>
    </>
  );
}
