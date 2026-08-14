from __future__ import annotations

from datetime import UTC, date, datetime

from ..adapters.llm_artifacts import load_strategist_calls, load_trade_report_calls
from ..adapters.llm_event_tail import load_recent_transport_calls
from ..config import ApiSettings
from ..domain.llm_operations_projection import (
    build_latency_summary,
    build_roles,
    build_stages,
    build_token_summary,
    latest_call_at,
    success_count,
)
from ..domain.llm_role_catalog import ROUTING_ISSUES
from ..infrastructure.dates import latest_iso_day
from ..models.common import AvailabilityStatus, Provenance
from ..models.llm_operations import LlmOperationsResponse

SOURCE = "llm_artifacts_and_bounded_event_tail"


def resolve_llm_day(settings: ApiSettings, requested: date | None) -> date:
    if requested is not None:
        return requested
    latest = latest_iso_day(settings.reports_root / "llm")
    return latest or datetime.now().astimezone().date()


def build_llm_operations(settings: ApiSettings, day: date) -> LlmOperationsResponse:
    strategist = load_strategist_calls(
        settings.reports_root,
        day,
        max_bytes=settings.max_report_bytes,
        max_rows=settings.max_event_rows,
    )
    trade = load_trade_report_calls(
        settings.reports_root,
        day,
        max_bytes=settings.max_report_bytes,
        max_rows=settings.max_event_rows,
        max_bundles=settings.max_trade_bundles,
    )
    event_tail = load_recent_transport_calls(
        settings.logs_root,
        day,
        max_bytes=settings.max_tail_scan_bytes,
        max_rows=settings.max_event_rows,
    )
    calls = strategist.rows + trade.rows
    issues = list(ROUTING_ISSUES) + strategist.issues + trade.issues + event_tail.issues
    latency = build_latency_summary(event_tail.calls, len(calls), event_tail.truncated)
    token_usage = build_token_summary(event_tail.calls, len(calls))
    if token_usage.status != AvailabilityStatus.AVAILABLE:
        issues.append("TOKEN_USAGE_NOT_RECORDED")
    successes = success_count(calls)
    if not calls:
        status = AvailabilityStatus.NO_DATA
    elif issues or strategist.truncated or trade.truncated:
        status = AvailabilityStatus.PARTIAL
    else:
        status = AvailabilityStatus.AVAILABLE
    unique_issues = sorted(set(issues))[: settings.max_event_rows]
    return LlmOperationsResponse(
        status=status,
        day=day,
        generated_at=datetime.now(UTC),
        provider="OpenRouter",
        total_calls=len(calls),
        success_count=successes,
        failure_count=len(calls) - successes,
        success_rate=successes / len(calls) if calls else None,
        latency=latency,
        token_usage=token_usage,
        roles=build_roles(calls),
        stages=build_stages(calls),
        recent_calls=event_tail.calls[-50:][::-1],
        issues=unique_issues,
        provenance=Provenance(
            source=SOURCE,
            as_of=latest_call_at(calls),
            sample_count=len(calls),
            coverage=latency.coverage,
        ),
    )
