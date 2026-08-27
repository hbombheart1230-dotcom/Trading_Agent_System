from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..adapters.runtime_status_artifacts import WatchdogHistoryArtifacts
from ..models.common import AvailabilityStatus
from ..models.runtime_status import WatchdogHistoryItem, WatchdogHistoryResponse


def build_watchdog_history_projection(
    artifacts: WatchdogHistoryArtifacts,
    *,
    now: datetime | None = None,
) -> WatchdogHistoryResponse:
    items = [_history_item(payload) for payload in artifacts.payloads]
    status = AvailabilityStatus.AVAILABLE if items else AvailabilityStatus.NO_DATA
    if artifacts.issues:
        status = AvailabilityStatus.PARTIAL if items else AvailabilityStatus.ERROR
    return WatchdogHistoryResponse(
        status=status,
        generated_at=_aware(now) or datetime.now(UTC),
        items=items,
        issues=sorted(set(artifacts.issues)),
    )


def _history_item(payload: dict[str, Any]) -> WatchdogHistoryItem:
    supervisor = _mapping(payload.get("supervisor"))
    before = _mapping(payload.get("live_before"))
    after = _mapping(payload.get("live_after"))
    blockers = [
        str(_mapping(row).get("code") or row).strip()
        for row in payload.get("blockers", [])
        if str(_mapping(row).get("code") or row).strip()
    ]
    return WatchdogHistoryItem(
        day=str(payload.get("day") or "UNKNOWN"),
        observed_at=_parse_datetime(payload.get("generated_at")),
        ok=bool(payload.get("ok")),
        offhours_noop=bool(payload.get("offhours_noop")),
        action=str(supervisor.get("last_action") or supervisor.get("decision") or "OBSERVE"),
        reason=_optional_text(supervisor.get("last_reason") or supervisor.get("decision_reason")),
        restart_count=_non_negative_int(supervisor.get("restart_count")) or 0,
        max_daily_restarts=_non_negative_int(supervisor.get("max_daily_restarts")),
        runtime_before=_runtime_summary(before),
        runtime_after=_runtime_summary(after),
        heartbeat_age_before_seconds=_non_negative_int(before.get("heartbeat_age_seconds")),
        heartbeat_age_after_seconds=_non_negative_int(after.get("heartbeat_age_seconds")),
        blockers=blockers,
    )


def _runtime_summary(live: dict[str, Any]) -> str:
    if not live:
        return "UNKNOWN"
    tree = _mapping(live.get("process_tree"))
    logical_count = _non_negative_int(tree.get("logical_session_count"))
    tree_state = str(tree.get("tree_state") or "")
    heartbeat_age = _non_negative_int(live.get("heartbeat_age_seconds"))
    if not bool(live.get("running")):
        return "STOPPED"
    if logical_count is not None and logical_count > 1 or tree_state == "DUPLICATE_SESSION":
        return "DUPLICATE"
    if tree_state == "OWNER_MISSING":
        return "INCONSISTENT"
    if heartbeat_age is not None and heartbeat_age > 300:
        return "STALE"
    return "RUNNING"


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return _aware(datetime.fromisoformat(text))
    except ValueError:
        return None


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return datetime(
        value.year, value.month, value.day, value.hour, value.minute,
        value.second, value.microsecond, tzinfo=UTC, fold=value.fold,
    )


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _non_negative_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
