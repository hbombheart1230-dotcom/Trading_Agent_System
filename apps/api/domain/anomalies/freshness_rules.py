from __future__ import annotations

from datetime import datetime

from ...adapters.source_freshness import FreshnessObservation
from ...models.anomalies import (
    AnomalyCategory,
    AnomalyEvidence,
    AnomalySeverity,
    OperationalAnomaly,
)
from .factory import anomaly_item
from .policy import AnomalyPolicy, KST


def evaluate_freshness(
    observation: FreshnessObservation,
    *,
    now: datetime,
    policy: AnomalyPolicy,
) -> list[OperationalAnomaly]:
    local = now.astimezone(KST)
    in_session = local.weekday() < 5 and (8, 50) <= (local.hour, local.minute) <= (16, 10)
    if not in_session:
        return []
    if not observation.available:
        return [
            _freshness_item(
                severity=AnomalySeverity.CRITICAL,
                observed=None,
                threshold=policy.runtime_stale_critical_seconds,
                summary="장중 runtime event source를 찾을 수 없습니다.",
                observed_at=None,
            )
        ]
    age = observation.age_seconds
    if age is None or age <= policy.runtime_stale_warning_seconds:
        return []
    severity = (
        AnomalySeverity.CRITICAL
        if age > policy.runtime_stale_critical_seconds
        else AnomalySeverity.WARNING
    )
    return [
        _freshness_item(
            severity=severity,
            observed=age,
            threshold=(
                policy.runtime_stale_critical_seconds
                if severity == AnomalySeverity.CRITICAL
                else policy.runtime_stale_warning_seconds
            ),
            summary=f"장중 runtime event 갱신이 {int(age)}초 지연됐습니다.",
            observed_at=observation.modified_at,
        )
    ]


def _freshness_item(*, severity, observed, threshold, summary, observed_at):
    return anomaly_item(
        category=AnomalyCategory.DATA_FRESHNESS,
        severity=severity,
        identity=f"runtime:{observed}",
        title="장중 runtime 데이터 갱신 지연",
        summary=summary,
        symbols=[],
        evidence=AnomalyEvidence(
            metric="runtime_event_age",
            observed_value=observed,
            threshold_value=threshold,
            comparator=">",
            unit="seconds",
            sample_count=1 if observed is not None else 0,
        ),
        source="runtime_events",
        observed_at=observed_at,
    )
