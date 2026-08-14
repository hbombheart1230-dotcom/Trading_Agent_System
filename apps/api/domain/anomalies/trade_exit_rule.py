from __future__ import annotations

from ...models.anomalies import AnomalyCategory, AnomalyEvidence, AnomalySeverity
from ...models.common import CostBasis
from ...models.trades import TradeSummary
from .factory import anomaly_item
from .policy import AnomalyPolicy


def evaluate_early_loss_exits(trades: list[TradeSummary], policy: AnomalyPolicy):
    items = []
    for trade in trades:
        if (
            trade.hold_seconds is None
            or trade.realized_return_pct is None
            or trade.hold_seconds >= policy.early_loss_exit_seconds
            or trade.realized_return_pct >= 0
        ):
            continue
        items.append(
            anomaly_item(
                category=AnomalyCategory.EARLY_LOSS_EXIT,
                severity=AnomalySeverity.WARNING,
                identity=trade.trade_id,
                title="과도한 단기 손실 청산 검토",
                summary=(
                    f"{trade.symbol}이 {trade.hold_seconds:.0f}초 보유 후 "
                    f"{trade.realized_return_pct:.2f}% 손실로 청산됐습니다."
                ),
                symbols=[trade.symbol],
                evidence=AnomalyEvidence(
                    metric="loss_exit_hold_seconds",
                    observed_value=trade.hold_seconds,
                    threshold_value=policy.early_loss_exit_seconds,
                    comparator="<",
                    unit="seconds",
                    sample_count=1,
                    cost_basis=CostBasis.MOCK_BROKER_NET,
                ),
                source="trade_bundle.normalized_read_model",
                observed_at=trade.exit_time,
            )
        )
    return items
