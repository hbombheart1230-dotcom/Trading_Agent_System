from __future__ import annotations

from ...models.anomalies import OperationalAnomaly
from ...models.trades import TradeSummary
from .factory import sort_anomalies
from .policy import AnomalyPolicy
from .trade_cost_rule import evaluate_cost_spikes
from .trade_exit_rule import evaluate_early_loss_exits
from .trade_sequence_rule import evaluate_repeated_losses


def evaluate_trade_anomalies(
    trades: list[TradeSummary],
    policy: AnomalyPolicy,
) -> list[OperationalAnomaly]:
    return sort_anomalies(
        [
            *evaluate_repeated_losses(trades, policy),
            *evaluate_early_loss_exits(trades, policy),
            *evaluate_cost_spikes(trades, policy),
        ]
    )
