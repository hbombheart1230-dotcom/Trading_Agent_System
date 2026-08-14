from __future__ import annotations

from ...models.anomalies import AnomalyCategory, AnomalyEvidence, AnomalySeverity
from ...models.common import CostBasis
from ...models.trades import TradeSummary
from .factory import anomaly_item
from .policy import AnomalyPolicy


def evaluate_cost_spikes(trades: list[TradeSummary], policy: AnomalyPolicy):
    items = []
    for trade in trades:
        if not trade.entry_price or trade.exit_price is None or trade.realized_return_pct is None:
            continue
        gross = ((trade.exit_price - trade.entry_price) / trade.entry_price) * 100.0
        drag = gross - trade.realized_return_pct
        if drag <= policy.cost_drag_warning_pct:
            continue
        items.append(
            anomaly_item(
                category=AnomalyCategory.COST_SPIKE,
                severity=AnomalySeverity.WARNING,
                identity=trade.trade_id,
                title="거래 비용 차감폭 급증",
                summary=f"{trade.symbol}의 가격 수익률과 broker 순수익률 차이가 {drag:.2f}%p입니다.",
                symbols=[trade.symbol],
                evidence=AnomalyEvidence(
                    metric="price_to_mock_net_cost_drag",
                    observed_value=round(drag, 8),
                    threshold_value=policy.cost_drag_warning_pct,
                    comparator=">",
                    unit="pct_point",
                    sample_count=1,
                    cost_basis=CostBasis.MOCK_BROKER_NET,
                ),
                source="trade_bundle.normalized_read_model",
                observed_at=trade.exit_time,
            )
        )
    return items
