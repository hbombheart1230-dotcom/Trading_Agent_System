from __future__ import annotations

from datetime import UTC, date, datetime

from ..adapters.performance_summary import load_performance_day
from ..config import ApiSettings
from ..infrastructure.dates import inclusive_days
from ..infrastructure.trade_index import trade_day_from_id
from ..models.common import AvailabilityStatus, Provenance
from ..models.trades import (
    ArtifactIntegrity,
    DecisionLineage,
    TradeDetailResponse,
    TradeSummary,
)
from .trade_fallback_projection import project_performance_fallback


def append_performance_fallbacks(
    settings: ApiSettings,
    start: date,
    end: date,
    items: list[TradeSummary],
    seen: set[str],
    issues: list[str],
) -> None:
    for day in inclusive_days(start, end, max_days=settings.max_period_days):
        source = load_performance_day(
            settings.reports_root,
            day,
            max_bytes=settings.max_report_bytes,
        )
        if source.source_status != "VALID":
            continue
        for row in source.rows:
            trade_id = str(row.get("trade_id") or "")
            if not trade_id or trade_id in seen:
                continue
            item = project_performance_fallback(day, row)
            if item is None:
                continue
            items.append(item)
            seen.add(trade_id)
            issues.append(f"TRADE_BUNDLE_MISSING:{trade_id}")


def build_fallback_detail(
    settings: ApiSettings,
    trade_id: str,
) -> TradeDetailResponse | None:
    day = trade_day_from_id(trade_id)
    if day is None:
        return None
    source = load_performance_day(
        settings.reports_root,
        day,
        max_bytes=settings.max_report_bytes,
    )
    row = next(
        (item for item in source.rows if item.get("trade_id") == trade_id),
        None,
    )
    trade = project_performance_fallback(day, row) if row else None
    if trade is None:
        return None
    return TradeDetailResponse(
        status=AvailabilityStatus.PARTIAL,
        generated_at=datetime.now(UTC),
        trade=trade,
        decisions=_empty_decisions(trade.playbook),
        timeline=[],
        post_exit=[],
        integrity=ArtifactIntegrity(
            status=AvailabilityStatus.PARTIAL,
            lifecycle_status=trade.status,
            lifecycle_completeness="performance_fallback_only",
            completeness_score=None,
            broker_reconciliation_status=(
                "truth_surface_net"
                if trade.realized_return_pct is not None
                else None
            ),
            agent_sources={},
            evaluation_eligible=False,
            exclusion_reason="TRADE_BUNDLE_MISSING",
            issues=["TRADE_BUNDLE_MISSING"],
        ),
        provenance=Provenance(
            source="performance_summary.v1.fallback",
            sample_count=1,
        ),
    )


def _empty_decisions(playbook: str | None) -> DecisionLineage:
    return DecisionLineage(
        playbook=playbook,
        tactic_id=None,
        strategist_horizon=None,
        commander_horizon=None,
        scanner_rank=None,
        scanner_score=None,
        scanner_chart_fit_score=None,
        selection_basis=None,
        monitor_entry_reason=None,
        monitor_exit_trigger=None,
        tactic_suitability_score=None,
    )
