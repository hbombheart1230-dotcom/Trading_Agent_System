from __future__ import annotations

from typing import Any, Dict, List


_REPORTER_TEXT_REPLACEMENTS = (
    ("Same-day reporter analysis was not generated yet.", "당일 리포터 분석은 아직 생성되지 않았습니다."),
    (
        "A same-day reporter file exists, but this run was not linked to a run-specific evaluation yet.",
        "당일 리포터 파일은 있지만 이 run에 대한 개별 평가는 아직 연결되지 않았습니다.",
    ),
    ("A same-day reporter analysis was linked to this run.", "당일 리포터 분석이 이 run에 연결됐습니다."),
    ("Interim summary:", "중간 요약:"),
    ("Reporter status:", "리포터 상태는"),
    ("Reporter reason:", "리포터 판단 사유는"),
    ("Reporter grade:", "리포터 등급은"),
    ("Reporter summary:", "리포터 요약은"),
    ("reporter linkage was not available yet.", "리포터 연계 결과는 아직 연결되지 않았습니다."),
    ("reporter linkage status was recorded separately.", "리포터 연계 상태는 별도로 기록되어 있습니다."),
    (
        "Link same-day reporter analysis to this lifecycle for a complete quality review.",
        "동일 일자 리포터 분석이 아직 이 거래 생애주기에 연결되지 않았습니다.",
    ),
    (
        "Holding-phase evidence is thin; preserve more monitor context between entry and exit.",
        "보유 구간 근거는 제한적이며 진입과 청산 사이 모니터 문맥이 충분하지 않습니다.",
    ),
    (
        "완전한 품질 검토를 위해 동일 일자 리포터 분석을 이 거래 생애주기에 연결해야 합니다.",
        "동일 일자 리포터 분석이 아직 이 거래 생애주기에 연결되지 않았습니다.",
    ),
    (
        "보유 구간 근거가 얇습니다. 진입과 청산 사이 모니터 문맥을 더 보존해야 합니다.",
        "보유 구간 근거는 제한적이며 진입과 청산 사이 모니터 문맥이 충분하지 않습니다.",
    ),
    (
        "같은 날 생성된 reporter 분석을 이 lifecycle에 연결해 전체 품질 평가를 완성해 주세요.",
        "동일 일자 리포터 분석이 아직 이 거래 생애주기에 연결되지 않았습니다.",
    ),
    (
        "보유 단계 근거가 얇아 진입과 청산 사이의 모니터 맥락을 더 보존해야 합니다.",
        "보유 구간 근거는 제한적이며 진입과 청산 사이 모니터 맥락이 충분하지 않습니다.",
    ),
)


def normalize_reporter_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = text
    for before, after in _REPORTER_TEXT_REPLACEMENTS:
        normalized = normalized.replace(before, after)
    return normalized.strip()


def normalize_reporter_status_human(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    data = dict(payload or {})
    if not data:
        return {}
    normalized: Dict[str, Any] = dict(data)
    for key in ("summary", "reason", "status_human"):
        if key in normalized:
            normalized[key] = normalize_reporter_text(normalized.get(key))
    if isinstance(normalized.get("bullets"), list):
        normalized["bullets"] = [
            normalize_reporter_text(item)
            for item in normalized.get("bullets") or []
            if str(item or "").strip()
        ]
    if isinstance(normalized.get("improvement_points"), list):
        normalized["improvement_points"] = [
            normalize_reporter_text(item)
            for item in normalized.get("improvement_points") or []
            if str(item or "").strip()
        ]
    return normalized
