from __future__ import annotations

from ..adapters.runtime_status_artifacts import (
    load_runtime_status_artifacts,
    load_watchdog_history_artifacts,
    load_scheduled_intelligence_artifacts,
)
from ..config import ApiSettings
from ..domain.runtime_status_projection import build_runtime_status_projection
from ..domain.watchdog_history_projection import build_watchdog_history_projection
from ..domain.scheduled_intelligence_projection import build_scheduled_intelligence_projection
from ..models.runtime_status import RuntimeStatusResponse, ScheduledIntelligenceResponse, WatchdogHistoryResponse


def build_runtime_status(settings: ApiSettings) -> RuntimeStatusResponse:
    artifacts = load_runtime_status_artifacts(
        settings.state_root,
        settings.reports_root,
        max_bytes=settings.max_report_bytes,
    )
    return build_runtime_status_projection(
        artifacts,
        public_mode=settings.public_mode,
    )


def build_watchdog_history(settings: ApiSettings, *, limit: int) -> WatchdogHistoryResponse:
    artifacts = load_watchdog_history_artifacts(
        settings.reports_root,
        max_bytes=settings.max_report_bytes,
        limit=limit,
    )
    return build_watchdog_history_projection(artifacts)


def build_scheduled_intelligence(settings: ApiSettings) -> ScheduledIntelligenceResponse:
    artifacts = load_scheduled_intelligence_artifacts(settings.reports_root, max_bytes=settings.max_report_bytes)
    return build_scheduled_intelligence_projection(artifacts)
