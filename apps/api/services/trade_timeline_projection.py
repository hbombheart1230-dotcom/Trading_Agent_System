from __future__ import annotations

from ..adapters.trade_bundle import TradeBundleSource
from ..models.trades import PostExitCheckpoint, TimelineEvent
from .trade_values import (
    first_text,
    list_value,
    mapping,
    number,
    ratio_to_pct,
    text_value,
    timestamp,
)


def project_timeline(
    source: TradeBundleSource,
) -> tuple[list[TimelineEvent], list[str]]:
    events: list[TimelineEvent] = []
    issues: list[str] = []
    entry_time = timestamp((source.entry or {}).get("ts"))
    exit_time = timestamp((source.exit or {}).get("ts"))
    if entry_time is not None:
        events.append(_execution_event(source.entry or {}, entry_time, "ENTRY"))
    for row in list_value(mapping(source.hold).get("holding_events")):
        if not isinstance(row, dict):
            continue
        event_time = timestamp(row.get("ts"))
        if event_time is None:
            issues.append("HOLD_EVENT_WITHOUT_TIMESTAMP")
            continue
        outside_start = entry_time is not None and event_time < entry_time
        outside_end = exit_time is not None and event_time > exit_time
        if outside_start or outside_end:
            issues.append("HOLD_EVENT_OUTSIDE_LIFECYCLE")
            continue
        monitor = mapping(row.get("monitor_context"))
        events.append(
            TimelineEvent(
                timestamp=event_time,
                stage="HOLD",
                action="OBSERVE",
                reason=first_text(
                    monitor.get("reason_human"),
                    monitor.get("monitor_reason"),
                    monitor.get("reason"),
                ),
                price=number(monitor.get("current_price")),
                quantity=None,
                source="hold.json",
            )
        )
    if exit_time is not None:
        events.append(_execution_event(source.exit or {}, exit_time, "EXIT"))
    events.sort(key=lambda event: event.timestamp)
    return events, sorted(set(issues))


def project_post_exit(source: TradeBundleSource) -> list[PostExitCheckpoint]:
    root = source.summary_input or {}
    checkpoints = mapping(mapping(root.get("post_exit_shadow")).get("checkpoints"))
    rows = [
        _checkpoint(str(horizon), mapping(value))
        for horizon, value in checkpoints.items()
    ]
    order = {
        "+5m": 1,
        "+15m": 2,
        "+30m": 3,
        "+60m": 4,
        "EOD": 5,
        "T+1": 6,
        "T+2": 7,
    }
    return sorted(rows, key=lambda row: order.get(row.horizon, 99))


def _checkpoint(horizon, item):
    return PostExitCheckpoint(
        horizon=horizon,
        status=text_value(item.get("status")) or "unknown",
        observed_at=timestamp(item.get("observed_ts")),
        price=number(item.get("price")),
        return_pct=ratio_to_pct(item.get("return_pct")),
    )


def _execution_event(row, event_time, stage):
    return TimelineEvent(
        timestamp=event_time,
        stage=stage,
        action=text_value(row.get("action")) or stage,
        reason=text_value(row.get("reason_human")),
        price=number(row.get("filled_price")) or number(row.get("price")),
        quantity=number(row.get("filled_qty")) or number(row.get("qty")),
        source="entry.json" if stage == "ENTRY" else "exit.json",
    )
