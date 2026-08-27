from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..adapters.runtime_status_artifacts import ScheduledIntelligenceArtifacts
from ..models.common import AvailabilityStatus
from ..models.runtime_status import ScheduledIntelligenceResponse, ScheduledJobStatus


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
    if job == "preopen":
        delivery = briefing.get("memory_delivery") if isinstance(briefing.get("memory_delivery"), dict) else {}
        frame = briefing.get("market_frame") if isinstance(briefing.get("market_frame"), dict) else {}
        memory_status = str(delivery.get("status") or "") or None
        source_day = str(delivery.get("source_day") or "") or None
        summary = str(frame.get("one_line") or "") or None
    else:
        memory_status = str(memory.get("status") or "") or None
        source_day = str(payload.get("day") or "") or None
        summary = "Broker Truth, report, evaluation and memory closeout"
    return ScheduledJobStatus(
        job=job,
        expected_time_kst=expected,
        day=str(payload.get("day") or "") or None,
        generated_at=_parse_datetime(payload.get("generated_at")),
        status=str(payload.get("status") or "NOT_RUN"),
        memory_status=memory_status,
        memory_source_day=source_day,
        summary=summary,
        issues=[str(row) for row in payload.get("issues", []) if str(row).strip()],
    )


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text: return None
    if text.endswith("Z"): text = f"{text[:-1]}+00:00"
    try: return datetime.fromisoformat(text)
    except ValueError: return None
