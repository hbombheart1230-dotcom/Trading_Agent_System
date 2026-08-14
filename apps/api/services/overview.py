from __future__ import annotations

from datetime import UTC, date, datetime

from ..config import ApiSettings
from ..models.common import AvailabilityStatus, CostBasis
from ..models.overview import OverviewResponse
from .performance import build_performance_summary
from .portfolio import build_portfolio


def build_overview(settings: ApiSettings, day: date) -> OverviewResponse:
    performance = build_performance_summary(
        settings,
        day,
        day,
        CostBasis.MOCK_BROKER_NET,
    )
    portfolio = build_portfolio(settings, day)
    issues = list(portfolio.issues)
    if performance.invalid_source_day_count:
        issues.append("PERFORMANCE_SOURCE_INVALID")
    status = _combined_status(performance.status, portfolio.status)
    return OverviewResponse(
        status=status,
        day=day,
        generated_at=datetime.now(UTC),
        mode="SIMULATION_MOCK_BROKER",
        performance=performance,
        portfolio=portfolio,
        issues=issues,
    )


def _combined_status(*statuses: AvailabilityStatus) -> AvailabilityStatus:
    if AvailabilityStatus.ERROR in statuses:
        return AvailabilityStatus.ERROR
    if all(status == AvailabilityStatus.UNAVAILABLE for status in statuses):
        return AvailabilityStatus.UNAVAILABLE
    if any(
        status in {AvailabilityStatus.PARTIAL, AvailabilityStatus.UNAVAILABLE}
        for status in statuses
    ):
        return AvailabilityStatus.PARTIAL
    if all(status == AvailabilityStatus.NO_DATA for status in statuses):
        return AvailabilityStatus.NO_DATA
    return AvailabilityStatus.AVAILABLE
