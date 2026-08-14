import type { Availability } from "../api/types";

const LABELS: Record<Availability, string> = {
  AVAILABLE: "정상",
  PARTIAL: "일부",
  UNAVAILABLE: "미수집",
  STALE: "지연",
  NO_DATA: "데이터 없음",
  ERROR: "오류",
};

export function StatusPill({ status }: { status: Availability }) {
  return <span className={`status-pill status-${status.toLowerCase()}`}>{LABELS[status]}</span>;
}
