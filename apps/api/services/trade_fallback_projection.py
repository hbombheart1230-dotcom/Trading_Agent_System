from __future__ import annotations

from datetime import date
from typing import Any

from ..models.common import AvailabilityStatus, CostBasis
from ..models.trades import TradeSummary
from .trade_values import number, ratio_to_pct, text_value


def project_performance_fallback(
    day: date,
    row: dict[str, Any],
) -> TradeSummary | None:
    trade_id = text_value(row.get("trade_id"))
    symbol = text_value(row.get("symbol"))
    if trade_id is None or symbol is None:
        return None
    return_value = number(row.get("return"))
    trusted = row.get("return_basis") == "truth_surface_net"
    return TradeSummary(
        trade_id=trade_id,
        day=day,
        symbol=symbol,
        symbol_name=None,
        themes=[],
        status="closed" if trusted else "unresolved",
        entry_time=None,
        exit_time=None,
        entry_price=None,
        exit_price=None,
        quantity=None,
        hold_seconds=None,
        realized_pnl_krw=number(row.get("pnl")) if trusted else None,
        realized_return_pct=ratio_to_pct(return_value) if trusted else None,
        result=_result(return_value) if trusted else None,
        playbook=text_value(row.get("playbook")),
        tactic_id=None,
        strategy_horizon=None,
        scanner_rank=None,
        cost_basis=CostBasis.MOCK_BROKER_NET,
        artifact_status=AvailabilityStatus.PARTIAL,
        artifact_scope="PERFORMANCE_FALLBACK",
    )


def _result(value: float | None) -> str | None:
    if value is None:
        return None
    if value > 0:
        return "win"
    if value < 0:
        return "loss"
    return "flat"
