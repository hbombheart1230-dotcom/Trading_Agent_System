import type { AnomalySeverity } from "./types";

export const SEVERITY_LABELS: Record<AnomalySeverity, string> = {
  CRITICAL: "긴급",
  WARNING: "주의",
  WATCH: "관찰",
};

export const CATEGORY_LABELS: Record<string, string> = {
  DATA_FRESHNESS: "데이터 갱신",
  ARTIFACT_INTEGRITY: "데이터 정합성",
  COST_SPIKE: "비용 급증",
  REPEATED_LOSS: "반복 손실",
  EARLY_LOSS_EXIT: "단기 손실 청산",
  MISSED_OPPORTUNITY: "기회 누락",
};

export function formatEvidence(value: number | null, unit: string): string {
  if (value == null) return "미확인";
  if (unit === "seconds") return `${Math.round(value)}초`;
  if (unit === "count") return `${Math.round(value)}건`;
  if (unit === "pct") return `${value.toFixed(2)}%`;
  if (unit === "pct_point") return `${value.toFixed(2)}%p`;
  return String(value);
}

export function formatIssue(issue: string): string {
  const labels: Record<string, string> = {
    "MISSING_SOURCE:opening_outcomes": "장초반 후보의 forward 결과가 아직 생성되지 않았습니다.",
    "MISSING_SOURCE:signals": "당일 기회 신호 artifact가 없습니다.",
    "MISSING_SOURCE:blockers": "당일 차단 사유 artifact가 없습니다.",
    "INVALID_SOURCE:opening_outcomes": "장초반 후보 결과 artifact를 읽을 수 없습니다.",
  };
  return labels[issue] ?? issue;
}
