from __future__ import annotations

from datetime import datetime

from ..models.common import (
    AvailabilityStatus,
    CostBasis,
    MetricValue,
    Provenance,
)


def metric(
    value: float | int | None,
    *,
    unit: str,
    status: AvailabilityStatus,
    source: str,
    generated_at: datetime | None,
    sample_count: int | None = None,
    coverage: float | None = None,
    cost_basis: CostBasis = CostBasis.NOT_APPLICABLE,
    reason: str | None = None,
) -> MetricValue:
    return MetricValue(
        value=value,
        unit=unit,
        status=status,
        cost_basis=cost_basis,
        provenance=Provenance(
            source=source,
            generated_at=generated_at,
            sample_count=sample_count,
            coverage=coverage,
        ),
        reason=reason,
    )
