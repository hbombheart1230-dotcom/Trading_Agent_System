from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from ...models.anomalies import AnomalyCategory, AnomalyEvidence, AnomalySeverity
from ...models.common import CostBasis
from ...models.trades import TradeSummary
from .factory import anomaly_item
from .policy import AnomalyPolicy, KST


def evaluate_repeated_losses(trades: list[TradeSummary], policy: AnomalyPolicy):
    by_symbol: dict[str, list[TradeSummary]] = defaultdict(list)
    for trade in trades:
        by_symbol[trade.symbol].append(trade)
    items = []
    for symbol, rows in by_symbol.items():
        rows.sort(key=lambda row: row.entry_time or datetime(1, 1, 1, tzinfo=KST))
        longest = current = 0
        for row in rows:
            if row.realized_return_pct is not None and row.realized_return_pct < 0:
                current += 1
                longest = max(longest, current)
            else:
                current = 0
        if longest < policy.repeated_loss_count:
            continue
        items.append(
            anomaly_item(
                category=AnomalyCategory.REPEATED_LOSS,
                severity=AnomalySeverity.WARNING,
                identity=f"{symbol}:{longest}",
                title="동일 종목 연속 손실",
                summary=f"{symbol}에서 당일 최대 {longest}회 연속 손실이 확인됐습니다.",
                symbols=[symbol],
                evidence=AnomalyEvidence(
                    metric="same_symbol_consecutive_losses",
                    observed_value=longest,
                    threshold_value=policy.repeated_loss_count,
                    comparator=">=",
                    unit="count",
                    sample_count=len(rows),
                    cost_basis=CostBasis.MOCK_BROKER_NET,
                ),
                source="trade_bundle.normalized_read_model",
            )
        )
    return items
