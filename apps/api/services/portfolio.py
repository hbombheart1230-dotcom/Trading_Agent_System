from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from ..adapters.operator_summary import load_portfolio_day
from ..config import ApiSettings
from ..infrastructure.dates import latest_iso_day
from ..models.common import AvailabilityStatus, Provenance
from ..models.portfolio import PortfolioResponse, Position
from .metric_factory import metric

SOURCE = "operator_daily_summary.residual_positions"


def resolve_portfolio_day(settings: ApiSettings, requested: date | None) -> date | None:
    if requested is not None:
        return requested
    root = settings.reports_root / "operator_summary" / "daily"
    return latest_iso_day(root)


def build_portfolio(settings: ApiSettings, day: date) -> PortfolioResponse:
    source = load_portfolio_day(
        settings.reports_root,
        day,
        max_bytes=settings.max_report_bytes,
    )
    now = datetime.now(UTC)
    if source.source_status != "VALID" or source.residual is None:
        status = (
            AvailabilityStatus.ERROR
            if source.source_status == "INVALID"
            else AvailabilityStatus.UNAVAILABLE
        )
        return _empty_portfolio(day, now, status, source.error)

    residual = source.residual
    raw_positions = residual.get("positions")
    rows = raw_positions if isinstance(raw_positions, list) else []
    positions, issues = _positions(rows)
    declared_count = _nonnegative_int(residual.get("position_count"), len(rows))
    if declared_count != len(positions):
        issues.append("POSITION_COUNT_MISMATCH")

    reconciliation = residual.get("account_snapshot_reconciliation")
    reconciliation_available = bool(
        isinstance(reconciliation, dict) and reconciliation.get("available")
    )
    if not reconciliation_available:
        issues.append("BROKER_RECONCILIATION_NOT_AVAILABLE")
    if residual.get("available") is not True:
        issues.append("RESIDUAL_POSITION_SOURCE_UNAVAILABLE")

    status = AvailabilityStatus.AVAILABLE if not issues else AvailabilityStatus.PARTIAL
    provenance = Provenance(
        source=SOURCE,
        generated_at=source.generated_at,
        sample_count=len(positions),
    )
    market_values = [position.market_value for position in positions]
    pnl_values = [position.unrealized_pnl for position in positions]
    return PortfolioResponse(
        status=status,
        day=day,
        generated_at=now,
        authority=(
            "RECONCILED_CLOSEOUT_READ_MODEL"
            if reconciliation_available
            else "STATE_SNAPSHOT_READ_MODEL"
        ),
        position_count=len(positions),
        positions=positions,
        total_market_value=_sum_metric(
            market_values,
            "KRW",
            source.generated_at,
            len(positions),
        ),
        total_unrealized_pnl=_sum_metric(
            pnl_values,
            "KRW",
            source.generated_at,
            len(positions),
        ),
        open_order_count=_unavailable_order_metric(source.generated_at),
        reconciliation_available=reconciliation_available,
        provenance=provenance,
        issues=issues,
    )


def _positions(rows: list[Any]) -> tuple[list[Position], list[str]]:
    positions: list[Position] = []
    issues: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("symbol") or "").strip():
            issues.append("INVALID_POSITION_ROW")
            continue
        quantity = _number(row.get("qty")) or 0.0
        average_price = _number(row.get("avg_price"))
        current_price = _number(row.get("current_price"))
        positions.append(
            Position(
                symbol=str(row["symbol"]).strip(),
                symbol_name=_text(row.get("symbol_name")),
                quantity=quantity,
                average_price=average_price,
                current_price=current_price,
                market_value=(
                    quantity * current_price if current_price is not None else None
                ),
                unrealized_pnl=_number(row.get("unrealized_pnl")),
                unrealized_return_ratio=_number(row.get("account_pnl_ratio")),
                lifecycle_status=_text(row.get("status")),
                overnight_action=_text(row.get("overnight_action")),
            )
        )
    return positions, issues


def _sum_metric(values, unit, generated_at, sample_count):
    complete = all(value is not None for value in values)
    status = AvailabilityStatus.AVAILABLE if complete else AvailabilityStatus.PARTIAL
    return metric(
        sum(value for value in values if value is not None) if complete else None,
        unit=unit,
        status=status,
        source=SOURCE,
        generated_at=generated_at,
        sample_count=sample_count,
        reason=None if complete else "one or more position values are unavailable",
    )


def _empty_portfolio(day, generated_at, status, error):
    unavailable = metric(
        None,
        unit="KRW",
        status=status,
        source=SOURCE,
        generated_at=None,
        reason=error or "daily operator summary is unavailable",
    )
    return PortfolioResponse(
        status=status,
        day=day,
        generated_at=generated_at,
        authority="UNAVAILABLE",
        position_count=0,
        positions=[],
        total_market_value=unavailable,
        total_unrealized_pnl=unavailable.model_copy(deep=True),
        open_order_count=_unavailable_order_metric(None),
        reconciliation_available=False,
        provenance=Provenance(source=SOURCE),
        issues=["PORTFOLIO_SOURCE_INVALID" if error else "PORTFOLIO_SOURCE_MISSING"],
    )


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _nonnegative_int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _unavailable_order_metric(generated_at):
    return metric(
        None,
        unit="count",
        status=AvailabilityStatus.UNAVAILABLE,
        source=SOURCE,
        generated_at=generated_at,
        reason="open orders are not present in the daily residual-position read model",
    )
