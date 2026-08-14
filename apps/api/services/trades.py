from __future__ import annotations

from datetime import UTC, date, datetime

from ..adapters.trade_bundle import load_trade_bundle
from ..config import ApiSettings
from ..infrastructure.trade_index import (
    discover_trade_bundles,
    latest_trade_day,
    locate_trade_bundle,
)
from ..models.common import AvailabilityStatus, Provenance
from ..models.trades import TradeDetailResponse, TradeListResponse
from .trade_fallbacks import append_performance_fallbacks, build_fallback_detail
from .trade_integrity_projection import project_integrity
from .trade_summary_projection import project_decisions, project_trade_summary
from .trade_timeline_projection import project_post_exit, project_timeline

SOURCE = "trade_bundle.normalized_read_model"


def resolve_trade_range(
    settings: ApiSettings,
    start: date | None,
    end: date | None,
) -> tuple[date, date] | None:
    if start is None and end is None:
        latest = latest_trade_day(settings.reports_root)
        return (latest, latest) if latest else None
    resolved_start = start or end
    resolved_end = end or start
    return (resolved_start, resolved_end) if resolved_start and resolved_end else None


def build_trade_list(
    settings: ApiSettings,
    start: date,
    end: date,
    *,
    symbol: str | None,
    result: str | None,
    offset: int,
    limit: int,
) -> TradeListResponse:
    refs, issues = discover_trade_bundles(
        settings.reports_root,
        start,
        end,
        max_days=settings.max_period_days,
        max_bundles=settings.max_trade_bundles,
    )
    items = []
    seen: set[str] = set()
    for ref in refs:
        source = load_trade_bundle(ref, max_bytes=settings.max_report_bytes, detail=False)
        item = project_trade_summary(source)
        if item is None:
            issues.append(f"UNREADABLE_TRADE:{ref.trade_id}")
            continue
        if item.artifact_status == AvailabilityStatus.PARTIAL:
            issues.append(f"PARTIAL_TRADE_ARTIFACT:{ref.trade_id}")
        items.append(item)
        seen.add(item.trade_id)
    append_performance_fallbacks(settings, start, end, items, seen, issues)
    items = [
        item
        for item in items
        if (not symbol or item.symbol == symbol)
        and (not result or (item.result or "").lower() == result.lower())
    ]
    items.sort(key=lambda item: (item.day, item.trade_id), reverse=True)
    status = _list_status(refs, items, issues)
    unique_issues = sorted(set(issues))
    visible_issues = unique_issues[: settings.max_event_rows]
    return TradeListResponse(
        status=status,
        start_date=start,
        end_date=end,
        generated_at=datetime.now(UTC),
        total_count=len(items),
        offset=offset,
        limit=limit,
        items=items[offset : offset + limit],
        issue_count=len(unique_issues),
        issues_truncated=len(visible_issues) < len(unique_issues),
        issues=visible_issues,
        provenance=Provenance(source=SOURCE, sample_count=len(items)),
    )


def build_trade_detail(
    settings: ApiSettings,
    trade_id: str,
) -> TradeDetailResponse | None:
    ref = locate_trade_bundle(settings.reports_root, trade_id)
    if ref is None:
        return build_fallback_detail(settings, trade_id)
    source = load_trade_bundle(ref, max_bytes=settings.max_report_bytes, detail=True)
    trade = project_trade_summary(source)
    if trade is None:
        return None
    timeline, timeline_issues = project_timeline(source)
    integrity = project_integrity(source, timeline_issues)
    status = integrity.status
    return TradeDetailResponse(
        status=status,
        generated_at=datetime.now(UTC),
        trade=trade,
        decisions=project_decisions(source),
        timeline=timeline,
        post_exit=project_post_exit(source),
        integrity=integrity,
        provenance=Provenance(source=SOURCE, sample_count=1),
    )


def _list_status(refs, items, issues):
    if not refs and not items:
        return AvailabilityStatus.NO_DATA
    if not items:
        return AvailabilityStatus.ERROR
    return AvailabilityStatus.PARTIAL if issues else AvailabilityStatus.AVAILABLE
