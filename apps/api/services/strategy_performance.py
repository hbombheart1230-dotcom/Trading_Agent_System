from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime

from ..config import ApiSettings
from ..models.common import AvailabilityStatus, CostBasis, Provenance
from ..models.strategies import (
    StrategyDimension,
    StrategyPerformanceItem,
    StrategyPerformanceResponse,
)
from .trades import build_trade_list

SOURCE = "trade_read_model.strategy_breakdown"


def build_strategy_performance(
    settings: ApiSettings,
    start: date,
    end: date,
    dimension: StrategyDimension,
) -> StrategyPerformanceResponse:
    trade_list = build_trade_list(
        settings,
        start,
        end,
        symbol=None,
        result=None,
        offset=0,
        limit=settings.max_trade_bundles,
    )
    groups: dict[str, list] = defaultdict(list)
    missing = 0
    for trade in trade_list.items:
        labels = _labels(trade, dimension)
        if not labels:
            labels = ["UNSPECIFIED"]
            missing += 1
        for label in labels:
            groups[label].append(trade)
    items = [_item(label, rows) for label, rows in groups.items()]
    items.sort(key=lambda item: (-item.trade_count, item.label))
    resolved = sum(trade.realized_return_pct is not None for trade in trade_list.items)
    issues = list(trade_list.issues)
    if missing:
        issues.append(f"MISSING_DIMENSION:{dimension.value}:{missing}")
    if not trade_list.items:
        status = AvailabilityStatus.NO_DATA
    elif issues or missing or resolved < len(trade_list.items):
        status = AvailabilityStatus.PARTIAL
    else:
        status = AvailabilityStatus.AVAILABLE
    return StrategyPerformanceResponse(
        status=status,
        start_date=start,
        end_date=end,
        generated_at=datetime.now(UTC),
        dimension=dimension,
        cost_basis=CostBasis.MOCK_BROKER_NET,
        trade_count=len(trade_list.items),
        resolved_count=resolved,
        items=items,
        issues=sorted(set(issues))[: settings.max_event_rows],
        provenance=Provenance(
            source=SOURCE,
            sample_count=resolved,
            coverage=resolved / len(trade_list.items) if trade_list.items else None,
        ),
    )


def _labels(trade, dimension: StrategyDimension) -> list[str]:
    if dimension == StrategyDimension.PLAYBOOK:
        value = trade.playbook
    elif dimension in (StrategyDimension.TACTIC, StrategyDimension.SETUP):
        value = trade.tactic_id
    elif dimension == StrategyDimension.HORIZON:
        value = trade.strategy_horizon
    else:
        return sorted(set(trade.themes))
    return [value] if value else []


def _item(label: str, trades: list) -> StrategyPerformanceItem:
    chronological = sorted(trades, key=lambda trade: (trade.day, trade.trade_id))
    values = [
        trade.realized_return_pct
        for trade in chronological
        if trade.realized_return_pct is not None
    ]
    gains = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    flats = len(values) - len(gains) - len(losses)
    directional = len(gains) + len(losses)
    return StrategyPerformanceItem(
        key=label,
        label=label,
        trade_count=len(trades),
        resolved_count=len(values),
        win_count=len(gains),
        loss_count=len(losses),
        flat_count=flats,
        coverage=len(values) / len(trades) if trades else None,
        win_rate=len(gains) / directional if directional else None,
        average_return_pct=sum(values) / len(values) if values else None,
        profit_factor=(sum(gains) / abs(sum(losses)) if gains and losses else None),
        max_drawdown_pct=_max_drawdown(values),
    )


def _max_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown
