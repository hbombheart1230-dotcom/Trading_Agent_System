from __future__ import annotations

from datetime import UTC, datetime

from ..config import ApiSettings
from ..infrastructure.source_roots import inspect_source_roots
from ..models.common import AvailabilityStatus
from ..models.health import HealthResponse, ReadinessResponse

SERVICE_NAME = "trading-agent-read-only-api"


def build_liveness() -> HealthResponse:
    return HealthResponse(
        status=AvailabilityStatus.AVAILABLE,
        service=SERVICE_NAME,
        checked_at=datetime.now(UTC),
    )


def build_readiness(settings: ApiSettings) -> ReadinessResponse:
    sources = inspect_source_roots(settings.source_roots)
    available_count = sum(
        source.status == AvailabilityStatus.AVAILABLE for source in sources
    )
    if available_count == len(sources):
        status = AvailabilityStatus.AVAILABLE
    elif available_count:
        status = AvailabilityStatus.PARTIAL
    else:
        status = AvailabilityStatus.UNAVAILABLE

    return ReadinessResponse(
        status=status,
        service=SERVICE_NAME,
        checked_at=datetime.now(UTC),
        sources=sources,
    )
