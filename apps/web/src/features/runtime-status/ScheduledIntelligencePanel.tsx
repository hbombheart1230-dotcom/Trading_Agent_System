import { BrainCircuit, CalendarClock, FileCheck2 } from "lucide-react";

import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { Panel } from "../../shared/components/Panel";
import { formatDateTime } from "../../shared/formatters/dates";
import type { ScheduledIntelligence } from "./types";

const JOB_LABELS: Record<string, string> = { preopen: "장전 브리핑", closeout: "장후 통합 정리" };
const STATUS_LABELS: Record<string, string> = {
  SUCCESS: "정상 완료", PARTIAL: "일부 점검", FAILED: "실패", NOT_RUN: "실행 전",
};

export function ScheduledIntelligencePanel() {
  const state = useApi<ScheduledIntelligence>("/api/v1/runtime/scheduled-intelligence");
  return (
    <Panel title="예약 브리핑 및 메모리" meta="기존 Preopen / Closeout 결과 재사용" className="span-12 scheduled-intelligence-panel">
      <DataState loading={state.loading} error={state.error} empty={!state.data} onRetry={state.refresh}>
        {state.data && <div className="scheduled-job-grid">
          {state.data.jobs.map((job) => <div className="scheduled-job" key={job.job}>
            <div className="scheduled-job-title"><CalendarClock size={16} /><div><span>{JOB_LABELS[job.job] ?? job.job}</span><strong>{job.expected_time_kst} KST</strong></div><span className={`runtime-state-pill ${job.status === "SUCCESS" ? "runtime-running" : job.status === "NOT_RUN" ? "runtime-stopped-expected" : "runtime-warning"}`}>{STATUS_LABELS[job.status] ?? job.status}</span></div>
            <div className="scheduled-job-detail"><FileCheck2 size={14} /><span>실제 완료</span><strong>{formatDateTime(job.generated_at)}</strong></div>
            <div className="scheduled-job-detail"><BrainCircuit size={14} /><span>메모리</span><strong>{job.memory_status ?? "확인 대기"}</strong><small>{job.memory_source_day ? `원본 ${job.memory_source_day}` : "전달 영수증 대기"}</small></div>
            <p>{job.summary ?? "예약 실행 후 요약이 표시됩니다."}</p>
            {job.issues.length > 0 && <div className="scheduled-job-issues">{job.issues.join(", ")}</div>}
          </div>)}
        </div>}
      </DataState>
    </Panel>
  );
}
