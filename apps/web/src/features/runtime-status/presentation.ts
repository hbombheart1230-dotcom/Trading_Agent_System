import type { RuntimeState, RuntimeStatus } from "./types";

const STATE_LABELS: Record<RuntimeState, string> = {
  RUNNING: "MAIN \uc815\uc0c1",
  DELAYED: "MAIN \uc9c0\uc5f0",
  STALE: "MAIN \uc751\ub2f5 \uc5c6\uc74c",
  DUPLICATE: "MAIN \uc911\ubcf5",
  INCONSISTENT: "MAIN \ubd88\uc77c\uce58",
  STOPPED_EXPECTED: "MAIN \uc815\uc0c1 \uc885\ub8cc",
  STOPPED_UNEXPECTED: "MAIN \uc911\uc9c0",
  UNKNOWN: "MAIN \ud655\uc778 \ubd88\uac00",
};

const MARKET_LABELS: Record<string, string> = {
  regular_session_open: "\uc815\uaddc\uc7a5 \uc9c4\ud589",
  closeout_notice: "\ub9c8\uac10 \uc900\ube44",
  regular_session_close: "\uc815\uaddc\uc7a5 \ub9c8\uac10",
  regular_session_close_confirmed: "\uc815\uaddc\uc7a5 \ub9c8\uac10 \ud655\uc778",
  all_markets_closed: "\uc804\uccb4 \uc2dc\uc7a5 \ub9c8\uac10",
  after_hours_close_price_open: "\uc2dc\uac04\uc678 \uc885\uac00 \uc9c4\ud589",
  after_hours_close_price_closed: "\uc2dc\uac04\uc678 \uc885\uac00 \ub9c8\uac10",
  after_hours_single_price_open: "\uc2dc\uac04\uc678 \ub2e8\uc77c\uac00 \uc9c4\ud589",
  after_hours_single_price_closed: "\uc2dc\uac04\uc678 \ub2e8\uc77c\uac00 \ub9c8\uac10",
};

export function runtimeStateLabel(state: RuntimeState): string {
  return STATE_LABELS[state];
}

export function runtimeStateTone(state: RuntimeState): string {
  if (state === "RUNNING") return "runtime-running";
  if (state === "STOPPED_EXPECTED") return "runtime-stopped-expected";
  if (state === "DELAYED" || state === "UNKNOWN") return "runtime-warning";
  return "runtime-error";
}

export function ageLabel(seconds: number | null): string {
  if (seconds == null) return "\ud655\uc778 \ubd88\uac00";
  if (seconds < 60) return `${seconds}\ucd08 \uc804`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}\ubd84 \uc804`;
  return `${Math.floor(seconds / 3600)}\uc2dc\uac04 \uc804`;
}

export function logicalSessionLabel(runtime: RuntimeStatus): string {
  if (!runtime.lock.exists) return "0\uac1c";
  const count = runtime.process.logical_session_count;
  if (count == null) return "\ub2e4\uc74c Watchdog\uc5d0\uc11c \ud655\uc778";
  return `${count}\uac1c`;
}

export function processTreeLabel(runtime: RuntimeStatus): string {
  if (!runtime.lock.exists) return "\ud504\ub85c\uc138\uc2a4 \uc5c6\uc74c";
  if (runtime.process.tree_state === "NORMAL_PROCESS_TREE") {
    return `\ubd80\ubaa8/\uc790\uc2dd ${runtime.process.raw_process_count ?? 0}\uac1c = 1\uc138\uc158`;
  }
  if (runtime.process.tree_state === "DUPLICATE_SESSION") return "\ub3c5\ub9bd \uc2e4\ud589 \ud2b8\ub9ac 2\uac1c \uc774\uc0c1";
  if (runtime.process.tree_state === "OWNER_MISSING") return "Lock \uc18c\uc720\uc790\uc640 \ud504\ub85c\uc138\uc2a4 \ubd88\uc77c\uce58";
  return "\ub2e4\uc74c Watchdog\uc5d0\uc11c \uad6c\uc870 \ud655\uc778";
}

export function marketStateLabel(runtime: RuntimeStatus): string {
  if (runtime.market.expectation_source !== "KIWOOM_MARKET_STATUS") {
    return runtime.market.expected_running ? "\uc7a5\uc911 \uc2e4\ud589 \uc608\uc0c1" : "\uc7a5\uc678 / \uc2e4\ud589 \ube44\ub300\uc0c1";
  }
  const label = runtime.market.label;
  return (label && MARKET_LABELS[label]) || (runtime.market.expected_running ? "\uc7a5\uc911 \uc2e4\ud589 \uc608\uc0c1" : "\uc7a5\uc678 / \uc2e4\ud589 \ube44\ub300\uc0c1");
}

const SUPERVISOR_ACTION_LABELS: Record<string, string> = {
  HEALTHY: "정상 유지",
  OBSERVE: "상태 확인",
  RECOVER: "복구 실행",
  RECOVERED: "복구 완료",
  RECOVERY_FAILED: "복구 실패",
  RECOVERY_BLOCKED: "복구 제한",
  STARTED: "예약 시작",
  OFFHOURS_NOOP: "장외 대기",
  NOT_RUN: "아직 실행 전",
  NOOP: "정상 유지",
  BLOCKED: "복구 제한",
  UNKNOWN: "이력 없음",
};

const SUPERVISOR_REASON_LABELS: Record<string, string> = {
  runtime_healthy: "런타임 정상",
  live_session_not_running: "MAIN 프로세스 중지",
  duplicate_runtime_session: "MAIN 중복 실행",
  lock_owner_missing: "Lock 소유자 불일치",
  heartbeat_missing: "Heartbeat 누락",
  heartbeat_stale: "Heartbeat 응답 지연",
  restart_cooldown_active: "복구 후 대기 시간",
  daily_restart_limit_reached: "일일 자동복구 한도 도달",
};

export function supervisorActionLabel(value: string): string {
  return SUPERVISOR_ACTION_LABELS[value] ?? value;
}

export function supervisorReasonLabel(value: string | null): string {
  if (!value) return "사유 없음";
  return SUPERVISOR_REASON_LABELS[value] ?? value;
}

export function runtimeHistoryLabel(value: string): string {
  const labels: Record<string, string> = {
    RUNNING: "정상",
    STOPPED: "중지",
    STALE: "응답 없음",
    DUPLICATE: "중복",
    INCONSISTENT: "불일치",
    UNKNOWN: "확인 불가",
  };
  return labels[value] ?? value;
}
