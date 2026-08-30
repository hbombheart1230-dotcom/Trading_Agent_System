from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..adapters.runtime_status_artifacts import ScheduledIntelligenceArtifacts
from ..models.common import AvailabilityStatus
from ..models.runtime_status import (
    ScheduledArtifactRef,
    ScheduledIntelligenceResponse,
    ScheduledJobDetail,
    ScheduledJobStatus,
    ScheduledStepStatus,
)


def build_scheduled_intelligence_projection(
    artifacts: ScheduledIntelligenceArtifacts,
    *,
    now: datetime | None = None,
) -> ScheduledIntelligenceResponse:
    jobs = [
        _job(artifacts.preopen, "preopen", "08:50", artifacts.briefing),
        _job(artifacts.closeout, "closeout", "16:00", {}),
    ]
    available = any(job.day for job in jobs)
    status = AvailabilityStatus.AVAILABLE if available else AvailabilityStatus.NO_DATA
    if artifacts.issues:
        status = AvailabilityStatus.PARTIAL if available else AvailabilityStatus.ERROR
    return ScheduledIntelligenceResponse(
        status=status,
        generated_at=now or datetime.now(UTC),
        jobs=jobs,
        issues=sorted(set(artifacts.issues)),
    )


def _job(payload: dict[str, Any], job: str, expected: str, briefing: dict[str, Any]) -> ScheduledJobStatus:
    memory = payload.get("memory") if isinstance(payload.get("memory"), dict) else {}
    day = str(payload.get("day") or "") or None
    raw_steps = payload.get("steps") if isinstance(payload.get("steps"), dict) else {}
    steps = [
        ScheduledStepStatus(
            name=str(name),
            status=str(row.get("status") or "UNKNOWN") if isinstance(row, dict) else "UNKNOWN",
        )
        for name, row in raw_steps.items()
    ]
    details: list[ScheduledJobDetail] = []
    artifacts: list[ScheduledArtifactRef] = []
    issues = [str(row) for row in payload.get("issues", []) if str(row).strip()]
    if job == "preopen":
        delivery = briefing.get("memory_delivery") if isinstance(briefing.get("memory_delivery"), dict) else {}
        frame = briefing.get("market_frame") if isinstance(briefing.get("market_frame"), dict) else {}
        strategist = briefing.get("strategist") if isinstance(briefing.get("strategist"), dict) else {}
        entry = briefing.get("entry_frame") if isinstance(briefing.get("entry_frame"), dict) else {}
        memory_status = str(delivery.get("status") or "") or None
        source_day = str(delivery.get("source_day") or "") or None
        summary = str(frame.get("one_line") or "") or None
        details = _details(
            (
                ("시장 국면", frame.get("regime")),
                ("플레이북", frame.get("playbook")),
                ("전술", frame.get("tactical_strategy")),
                ("전술 유형", frame.get("tactical_subtype")),
                ("리스크", frame.get("risk_tone")),
                ("진입 권한", entry.get("permission_level")),
                ("Strategist 모델", strategist.get("model")),
                ("메모리 적용", delivery.get("application_mode")),
            )
        )
        artifacts = _artifacts(
            (
                ("장전 브리핑", f"reports/briefings/{day}/preopen_briefing.json" if day else ""),
                ("메모리 전달 영수증", f"reports/briefings/{day}/memory_delivery_receipt.json" if day else ""),
                ("메모리 원본", delivery.get("source_artifact")),
                ("Strategist 원본", strategist.get("artifact")),
            )
        )
        issues.extend(str(row) for row in briefing.get("data_quality_warnings", []) if str(row).strip())
        issues.extend(str(row) for row in briefing.get("issues", []) if str(row).strip())
    else:
        memory_status = str(memory.get("status") or "") or None
        source_day = day
        success_count = sum(step.status == "SUCCESS" for step in steps)
        summary = f"Broker Truth, report, evaluation and memory closeout; {success_count}/{len(steps)} steps successful."
        sync = memory.get("sync") if isinstance(memory.get("sync"), dict) else {}
        daily_index = payload.get("daily_index") if isinstance(payload.get("daily_index"), dict) else {}
        details = _details(
            (
                ("단계 완료", f"{success_count}/{len(steps)}" if steps else None),
                ("거래 수", sync.get("total_trades")),
                ("플레이북 수", sync.get("playbook_count")),
                ("메모리 동기화", sync.get("status")),
                ("다음 장전 전달", memory.get("next_session_delivery")),
            )
        )
        artifacts = _artifacts(
            (
                ("장후 실행 원본", f"reports/runtime/scheduled_jobs/{day}/closeout.json" if day else ""),
                ("전략 메모리", memory.get("artifact")),
                ("통합 인덱스 JSON", daily_index.get("json")),
                ("통합 인덱스 Markdown", daily_index.get("markdown")),
            )
        )
    return ScheduledJobStatus(
        job=job,
        expected_time_kst=expected,
        day=day,
        generated_at=_parse_datetime(payload.get("generated_at")),
        status=str(payload.get("status") or "NOT_RUN"),
        memory_status=memory_status,
        memory_source_day=source_day,
        summary=summary,
        details=details,
        artifacts=artifacts,
        steps=steps,
        issues=sorted(set(issues)),
    )


def _details(rows: tuple[tuple[str, Any], ...]) -> list[ScheduledJobDetail]:
    return [ScheduledJobDetail(label=label, value=str(value)) for label, value in rows if value not in (None, "")]


def _artifacts(rows: tuple[tuple[str, Any], ...]) -> list[ScheduledArtifactRef]:
    return [ScheduledArtifactRef(label=label, path=str(path)) for label, path in rows if path]


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text: return None
    if text.endswith("Z"): text = f"{text[:-1]}+00:00"
    try: return datetime.fromisoformat(text)
    except ValueError: return None
