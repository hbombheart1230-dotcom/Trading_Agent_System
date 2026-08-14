from __future__ import annotations

from datetime import UTC, date, datetime

from ..adapters.performance_summary import PerformanceDaySource, load_performance_day
from ..config import ApiSettings
from ..domain.performance_math import (
    calculate_return_statistics,
    trusted_net_pnl,
)
from ..infrastructure.dates import inclusive_days
from ..models.common import AvailabilityStatus, CostBasis, Provenance
from ..models.performance import (
    PerformanceCounts,
    PerformancePoint,
    PerformanceSeriesResponse,
    PerformanceSummaryResponse,
)
from .metric_factory import metric

SOURCE = "performance_summary.v1.truth_surface_net"


def build_performance_summary(
    settings: ApiSettings,
    start: date,
    end: date,
    cost_basis: CostBasis,
) -> PerformanceSummaryResponse:
    sources = _load_sources(settings, start, end)
    rows = _deduplicated_rows(sources)
    stats = calculate_return_statistics(rows)
    generated_at = datetime.now(UTC)
    source_generated_at = _latest_generated_at(sources)
    valid_count = sum(source.source_status == "VALID" for source in sources)
    invalid_count = sum(source.source_status == "INVALID" for source in sources)
    coverage = stats.resolved_count / stats.trade_count if stats.trade_count else None
    status = _summary_status(
        cost_basis,
        valid_count,
        invalid_count,
        stats.trade_count,
        stats.unresolved_count,
    )
    metric_status = _metric_status(cost_basis, stats.resolved_count)
    unsupported = None if cost_basis == CostBasis.MOCK_BROKER_NET else "cost basis is not available from this source"
    provenance = Provenance(
        source=SOURCE,
        generated_at=source_generated_at,
        sample_count=stats.resolved_count,
        coverage=coverage,
    )
    pnl_values = [value for row in rows if (value := trusted_net_pnl(row)) is not None]
    pnl_status = AvailabilityStatus.AVAILABLE if pnl_values else AvailabilityStatus.NO_DATA
    unavailable_cost = "gross and explicit cost components are absent from performance_summary.v1"
    return PerformanceSummaryResponse(
        status=status,
        start_date=start,
        end_date=end,
        generated_at=generated_at,
        cost_basis=cost_basis,
        counts=PerformanceCounts(
            trade_count=stats.trade_count,
            resolved_count=stats.resolved_count,
            unresolved_count=stats.unresolved_count,
            win_count=stats.win_count,
            loss_count=stats.loss_count,
            flat_count=stats.flat_count,
        ),
        win_rate=metric(
            stats.win_count / (stats.win_count + stats.loss_count)
            if stats.win_count + stats.loss_count
            else None,
            unit="ratio",
            status=metric_status if stats.win_count + stats.loss_count else AvailabilityStatus.NO_DATA,
            source=SOURCE,
            generated_at=source_generated_at,
            sample_count=stats.win_count + stats.loss_count,
            coverage=coverage,
            cost_basis=cost_basis,
            reason=unsupported or ("no directional resolved trades" if not stats.win_count + stats.loss_count else None),
        ),
        average_trade_return=_return_metric(stats.average_return, "average", metric_status, source_generated_at, stats.resolved_count, coverage, cost_basis, unsupported),
        average_gain=_return_metric(stats.average_gain, "gain", metric_status, source_generated_at, stats.win_count, coverage, cost_basis, unsupported),
        average_loss=_return_metric(stats.average_loss, "loss", metric_status, source_generated_at, stats.loss_count, coverage, cost_basis, unsupported),
        realized_pnl=metric(
            sum(pnl_values) if pnl_values else None,
            unit="KRW",
            status=pnl_status if not unsupported else AvailabilityStatus.UNAVAILABLE,
            source=SOURCE,
            generated_at=source_generated_at,
            sample_count=len(pnl_values),
            coverage=len(pnl_values) / stats.trade_count if stats.trade_count else None,
            cost_basis=cost_basis,
            reason=unsupported or ("no trusted PnL samples" if not pnl_values else None),
        ),
        gross_pnl=_unavailable_cost_metric("gross PnL", source_generated_at, unavailable_cost),
        total_cost=_unavailable_cost_metric("total cost", source_generated_at, unavailable_cost),
        cost_drag=_unavailable_cost_metric("cost drag", source_generated_at, unavailable_cost),
        profit_factor=metric(
            stats.profit_factor if not unsupported else None,
            unit="ratio",
            status=metric_status if stats.profit_factor is not None else AvailabilityStatus.NO_DATA,
            source=SOURCE,
            generated_at=source_generated_at,
            sample_count=stats.resolved_count,
            coverage=coverage,
            cost_basis=cost_basis,
            reason=unsupported or ("profit factor requires both gains and losses" if stats.profit_factor is None else None),
        ),
        max_drawdown=_return_metric(stats.max_drawdown, "drawdown", metric_status, source_generated_at, stats.resolved_count, coverage, cost_basis, unsupported),
        source_day_count=valid_count,
        invalid_source_day_count=invalid_count,
        provenance=provenance,
    )


def build_performance_series(
    settings: ApiSettings,
    start: date,
    end: date,
    cost_basis: CostBasis,
) -> PerformanceSeriesResponse:
    sources = _load_sources(settings, start, end)
    points = _points(sources, cost_basis)
    valid_count = sum(source.source_status == "VALID" for source in sources)
    invalid_count = sum(source.source_status == "INVALID" for source in sources)
    if cost_basis != CostBasis.MOCK_BROKER_NET:
        status = AvailabilityStatus.UNAVAILABLE
    elif invalid_count and valid_count:
        status = AvailabilityStatus.PARTIAL
    elif invalid_count:
        status = AvailabilityStatus.ERROR
    elif not points:
        status = AvailabilityStatus.UNAVAILABLE
    elif not any(point.sample_count for point in points):
        status = AvailabilityStatus.NO_DATA
    else:
        status = AvailabilityStatus.AVAILABLE
    return PerformanceSeriesResponse(
        status=status,
        start_date=start,
        end_date=end,
        generated_at=datetime.now(UTC),
        cost_basis=cost_basis,
        series_kind="DAILY_AVERAGE_TRUSTED_TRADE_RETURN",
        points=points,
        provenance=Provenance(
            source=SOURCE,
            generated_at=_latest_generated_at(sources),
            sample_count=sum(point.sample_count for point in points),
        ),
    )


def _load_sources(settings: ApiSettings, start: date, end: date) -> list[PerformanceDaySource]:
    return [
        load_performance_day(settings.reports_root, day, max_bytes=settings.max_report_bytes)
        for day in inclusive_days(start, end, max_days=settings.max_period_days)
    ]


def _deduplicated_rows(sources: list[PerformanceDaySource]) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for source in sources:
        for index, row in enumerate(source.rows):
            identity = str(row.get("trade_id") or f"{source.day.isoformat()}:{index}")
            if identity in seen:
                continue
            seen.add(identity)
            rows.append(row)
    return rows


def _point(source: PerformanceDaySource, cost_basis: CostBasis) -> PerformancePoint:
    if source.source_status == "INVALID":
        return PerformancePoint(day=source.day, status=AvailabilityStatus.ERROR, trade_count=0, sample_count=0, average_trade_return_pct=None, realized_pnl_krw=None, cumulative_realized_pnl_krw=None)
    stats = calculate_return_statistics(source.rows)
    pnl_values = [value for row in source.rows if (value := trusted_net_pnl(row)) is not None]
    if cost_basis != CostBasis.MOCK_BROKER_NET:
        status = AvailabilityStatus.UNAVAILABLE
        value = None
    elif not stats.resolved_count:
        status = AvailabilityStatus.NO_DATA
        value = None
    else:
        status = AvailabilityStatus.PARTIAL if stats.unresolved_count else AvailabilityStatus.AVAILABLE
        value = stats.average_return * 100.0 if stats.average_return is not None else None
    return PerformancePoint(day=source.day, status=status, trade_count=stats.trade_count, sample_count=stats.resolved_count, average_trade_return_pct=value, realized_pnl_krw=sum(pnl_values) if pnl_values else None, cumulative_realized_pnl_krw=None)


def _points(sources: list[PerformanceDaySource], cost_basis: CostBasis) -> list[PerformancePoint]:
    points: list[PerformancePoint] = []
    cumulative = 0.0
    observed_pnl = False
    for source in sources:
        if source.source_status == "MISSING":
            continue
        point = _point(source, cost_basis)
        if point.realized_pnl_krw is not None:
            cumulative += point.realized_pnl_krw
            observed_pnl = True
        points.append(
            point.model_copy(
                update={
                    "cumulative_realized_pnl_krw": cumulative if observed_pnl else None
                }
            )
        )
    return points


def _summary_status(cost_basis: CostBasis, valid: int, invalid: int, trades: int, unresolved: int) -> AvailabilityStatus:
    if cost_basis != CostBasis.MOCK_BROKER_NET:
        return AvailabilityStatus.UNAVAILABLE
    if invalid and valid:
        return AvailabilityStatus.PARTIAL
    if invalid:
        return AvailabilityStatus.ERROR
    if not valid:
        return AvailabilityStatus.UNAVAILABLE
    if not trades:
        return AvailabilityStatus.NO_DATA
    return AvailabilityStatus.PARTIAL if unresolved else AvailabilityStatus.AVAILABLE


def _metric_status(cost_basis: CostBasis, samples: int) -> AvailabilityStatus:
    if cost_basis != CostBasis.MOCK_BROKER_NET:
        return AvailabilityStatus.UNAVAILABLE
    return AvailabilityStatus.AVAILABLE if samples else AvailabilityStatus.NO_DATA


def _return_metric(value, label, status, generated_at, sample_count, coverage, cost_basis, unsupported):
    reason = unsupported or (f"no qualifying {label} samples" if value is None else None)
    resolved_status = status if value is not None and not unsupported else (AvailabilityStatus.UNAVAILABLE if unsupported else AvailabilityStatus.NO_DATA)
    return metric(value * 100.0 if value is not None and not unsupported else None, unit="pct", status=resolved_status, source=SOURCE, generated_at=generated_at, sample_count=sample_count, coverage=coverage, cost_basis=cost_basis, reason=reason)


def _latest_generated_at(sources: list[PerformanceDaySource]) -> datetime | None:
    values = [source.generated_at for source in sources if source.generated_at is not None]
    return max(values) if values else None


def _unavailable_cost_metric(label: str, generated_at, reason: str):
    return metric(
        None,
        unit="KRW",
        status=AvailabilityStatus.UNAVAILABLE,
        source=SOURCE,
        generated_at=generated_at,
        cost_basis=CostBasis.GROSS if label == "gross PnL" else CostBasis.NOT_APPLICABLE,
        reason=reason,
    )
