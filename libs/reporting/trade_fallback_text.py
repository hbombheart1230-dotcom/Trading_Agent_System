from __future__ import annotations

from typing import Any


ENTRY_REASON_NOT_CAPTURED = "진입 이유는 기록되지 않았습니다."
EXIT_REASON_NOT_CAPTURED = "청산 이유는 기록되지 않았습니다."
EXECUTION_OUTCOME_NOT_CAPTURED = "거래 생애주기 실행 요약은 기록되지 않았습니다."
REPORTER_LINKAGE_NOT_CAPTURED = "리포터 연계 정보는 기록되지 않았습니다."
LIFECYCLE_CONCLUSION_NOT_CAPTURED = "최종 생애주기 결론은 기록되지 않았습니다."
OPEN_POSITION_WATCHING = "포지션은 아직 열려 있으며 청산 신호를 계속 감시 중입니다."
PARTIAL_EXIT_EVIDENCE_MISSING = "생애주기 기록이 partial 상태이며 청산 근거가 누락됐습니다."
HOLDING_DURATION_UNAVAILABLE = "진입 시각 근거가 부족해 보유 시간을 확정하지 못했습니다."


def entry_reason_missing_in_summary(text: Any) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return False
    return "Entry reason was not captured" in cleaned or ENTRY_REASON_NOT_CAPTURED in cleaned


def lifecycle_conclusion_summary_is_placeholder(text: Any) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return True
    lowered = cleaned.lower()
    return (
        cleaned == LIFECYCLE_CONCLUSION_NOT_CAPTURED
        or "Lifecycle conclusion was not captured" in cleaned
        or lowered in {"not captured", "not_captured"}
    )
