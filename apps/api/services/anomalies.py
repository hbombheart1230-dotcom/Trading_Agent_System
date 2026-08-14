from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from ..adapters.source_freshness import inspect_runtime_event_freshness
from ..config import ApiSettings
from ..domain.anomaly_rules import (
    POLICY_VERSION,
    AnomalyPolicy,
    artifact_integrity_anomaly,
    evaluate_freshness,
    evaluate_missed_opportunities,
    evaluate_trade_anomalies,
    sort_anomalies,
)
from ..models.anomalies import AnomalyResponse, AnomalySeverity
from ..models.common import AvailabilityStatus, Provenance
from .opportunities import build_opportunity_outcomes
from .trades import build_trade_list

KST = ZoneInfo("Asia/Seoul")


def resolve_anomaly_day(day: date | None) -> date:
    return day or datetime.now(KST).date()


def build_anomalies(
    settings: ApiSettings,
    day: date,
    *,
    now: datetime | None = None,
    policy: AnomalyPolicy | None = None,
) -> AnomalyResponse:
    instant = now or datetime.now(UTC)
    rules = policy or AnomalyPolicy()
    trades = build_trade_list(
        settings,
        day,
        day,
        symbol=None,
        result=None,
        offset=0,
        limit=settings.max_trade_bundles,
    )
    opportunities = build_opportunity_outcomes(settings, day)
    items = [
        *evaluate_trade_anomalies(trades.items, rules),
        *artifact_integrity_anomaly(trades.issue_count),
        *evaluate_missed_opportunities(
            opportunities.outcomes,
            {trade.symbol for trade in trades.items},
            rules,
        ),
    ]
    if day == instant.astimezone(KST).date():
        items.extend(
            evaluate_freshness(
                inspect_runtime_event_freshness(settings.logs_root, now=instant),
                now=instant,
                policy=rules,
            )
        )
    items = sort_anomalies(items)
    issues = sorted(set([*trades.issues, *opportunities.issues]))
    has_evidence = bool(trades.items or opportunities.outcomes)
    if not has_evidence:
        status = AvailabilityStatus.NO_DATA if not issues else AvailabilityStatus.PARTIAL
    elif issues:
        status = AvailabilityStatus.PARTIAL
    else:
        status = AvailabilityStatus.AVAILABLE
    return AnomalyResponse(
        status=status,
        day=day,
        generated_at=instant,
        policy_version=POLICY_VERSION,
        critical_count=sum(row.severity == AnomalySeverity.CRITICAL for row in items),
        warning_count=sum(row.severity == AnomalySeverity.WARNING for row in items),
        watch_count=sum(row.severity == AnomalySeverity.WATCH for row in items),
        evaluated_trade_count=len(trades.items),
        evaluated_opportunity_count=len(opportunities.outcomes),
        evaluated_rule_count=6,
        items=items,
        issues=issues,
        provenance=Provenance(
            source="operational_anomaly.read_model",
            as_of=instant,
            sample_count=len(trades.items) + len(opportunities.outcomes),
            coverage=opportunities.coverage,
        ),
    )
