from __future__ import annotations

from ...models.anomalies import (
    AnomalyCategory,
    AnomalyEvidence,
    AnomalySeverity,
    OperationalAnomaly,
)
from ...models.common import CostBasis
from ...models.opportunities import OpportunityOutcome
from .factory import anomaly_item, sort_anomalies
from .policy import AnomalyPolicy


def evaluate_missed_opportunities(
    outcomes: list[OpportunityOutcome],
    traded_symbols: set[str],
    policy: AnomalyPolicy,
) -> list[OperationalAnomaly]:
    items: list[OperationalAnomaly] = []
    for outcome in outcomes:
        checkpoint = next(
            (row for row in outcome.checkpoints if row.horizon.lower() == "+30m"),
            None,
        )
        value = checkpoint.mock_broker_net_return_pct if checkpoint else None
        if (
            not outcome.prospective_eligible
            or outcome.symbol in traded_symbols
            or checkpoint is None
            or checkpoint.status.lower() != "observed"
            or value is None
            or value <= policy.missed_opportunity_net_return_pct
        ):
            continue
        items.append(
            anomaly_item(
                category=AnomalyCategory.MISSED_OPPORTUNITY,
                severity=AnomalySeverity.WATCH,
                identity=outcome.opportunity_id,
                title="관측 후보의 후행 수익 기회 누락",
                summary=(
                    f"{outcome.symbol} shadow 후보가 체결되지 않았고 +30분 mock 순수익률이 "
                    f"{value:.2f}%였습니다. 행동 변경이 아닌 검토 신호입니다."
                ),
                symbols=[outcome.symbol],
                evidence=AnomalyEvidence(
                    metric="forward_30m_mock_net_return",
                    observed_value=value,
                    threshold_value=policy.missed_opportunity_net_return_pct,
                    comparator=">",
                    unit="pct",
                    sample_count=1,
                    cost_basis=CostBasis.MOCK_BROKER_NET,
                ),
                source="opening_rank1_shadow",
                observed_at=outcome.observed_at,
            )
        )
    return sort_anomalies(items)
