from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..adapters.runtime_status_artifacts import RuntimeStatusArtifacts
from ..models.common import AvailabilityStatus
from ..models.runtime_status import (
    RuntimeLockStatus,
    RuntimeMarketStatus,
    RuntimeProcessLink,
    RuntimeProcessStatus,
    RuntimeState,
    RuntimeStatusResponse,
    RuntimeSupervisorStatus,
    RuntimeWatchdogStatus,
)

KST = ZoneInfo("Asia/Seoul")
FRESH_HEARTBEAT_SECONDS = 180
DELAYED_HEARTBEAT_SECONDS = 600
FRESH_WATCHDOG_SECONDS = 7 * 60
MARKET_OPEN_LABELS = {"regular_session_open", "closeout_notice"}
MARKET_CLOSED_LABELS = {
    "regular_session_close",
    "regular_session_close_confirmed",
    "all_markets_closed",
    "after_hours_close_price_open",
    "after_hours_close_price_closed",
    "after_hours_single_price_open",
    "after_hours_single_price_closed",
}


def build_runtime_status_projection(
    artifacts: RuntimeStatusArtifacts,
    *,
    now: datetime | None = None,
    public_mode: bool = False,
) -> RuntimeStatusResponse:
    checked_at = _as_aware(now) or datetime.now(UTC)
    now_kst = checked_at.astimezone(KST)
    issues = list(artifacts.issues)

    market = _market_status(artifacts.market, now_kst)
    watchdog = _watchdog_status(artifacts.watchdog, checked_at)
    supervisor = _supervisor_status(artifacts.watchdog)
    lock = _lock_status(artifacts.lock, checked_at)
    process = _process_status(artifacts.watchdog, watchdog)
    runtime_state = _runtime_state(lock, process, watchdog, market, issues)
    availability = _availability(runtime_state, watchdog, issues)

    if public_mode:
        lock = lock.model_copy(update={"owner_pid": None})
        process = process.model_copy(update={"processes": []})

    return RuntimeStatusResponse(
        status=availability,
        runtime_state=runtime_state,
        checked_at=checked_at,
        lock=lock,
        process=process,
        watchdog=watchdog,
        supervisor=supervisor,
        market=market,
        issues=sorted(set(issues)),
    )


def _runtime_state(
    lock: RuntimeLockStatus,
    process: RuntimeProcessStatus,
    watchdog: RuntimeWatchdogStatus,
    market: RuntimeMarketStatus,
    issues: list[str],
) -> RuntimeState:
    if not lock.exists:
        return (
            RuntimeState.STOPPED_UNEXPECTED
            if market.expected_running
            else RuntimeState.STOPPED_EXPECTED
        )

    if watchdog.fresh and process.logical_session_count is not None:
        if process.logical_session_count > 1 or process.tree_state == "DUPLICATE_SESSION":
            issues.append("DUPLICATE_RUNTIME_SESSION")
            return RuntimeState.DUPLICATE
        if process.tree_state == "OWNER_MISSING":
            issues.append("RUNTIME_LOCK_OWNER_NOT_IN_PROCESS_TREE")
            return RuntimeState.INCONSISTENT

    age = lock.heartbeat_age_seconds
    if age is None:
        issues.append("RUNTIME_HEARTBEAT_MISSING")
        return RuntimeState.INCONSISTENT
    if age <= FRESH_HEARTBEAT_SECONDS:
        return RuntimeState.RUNNING
    if age <= DELAYED_HEARTBEAT_SECONDS:
        issues.append("RUNTIME_HEARTBEAT_DELAYED")
        return RuntimeState.DELAYED
    issues.append("RUNTIME_HEARTBEAT_STALE")
    return RuntimeState.STALE


def _availability(
    state: RuntimeState,
    watchdog: RuntimeWatchdogStatus,
    issues: list[str],
) -> AvailabilityStatus:
    if state in {RuntimeState.RUNNING, RuntimeState.STOPPED_EXPECTED}:
        if watchdog.fresh and watchdog.ok is False:
            issues.append("RUNTIME_WATCHDOG_REPORTED_BLOCKERS")
            return AvailabilityStatus.PARTIAL
        return AvailabilityStatus.AVAILABLE
    if state == RuntimeState.UNKNOWN:
        return AvailabilityStatus.NO_DATA
    if state == RuntimeState.DELAYED:
        return AvailabilityStatus.PARTIAL
    return AvailabilityStatus.ERROR


def _lock_status(payload: dict[str, Any], now: datetime) -> RuntimeLockStatus:
    started = _parse_datetime(payload.get("started_ts"))
    heartbeat = _parse_datetime(payload.get("heartbeat_ts")) or started
    return RuntimeLockStatus(
        exists=bool(payload),
        owner_pid=_positive_int(payload.get("pid")),
        started_at=started,
        heartbeat_at=heartbeat,
        heartbeat_age_seconds=_age_seconds(heartbeat, now),
    )


def _watchdog_status(payload: dict[str, Any], now: datetime) -> RuntimeWatchdogStatus:
    observed = _parse_datetime(payload.get("generated_at"))
    age = _age_seconds(observed, now)
    blockers = []
    for row in payload.get("blockers") if isinstance(payload.get("blockers"), list) else []:
        code = str(_mapping(row).get("code") or row or "").strip()
        if code:
            blockers.append(code)
    return RuntimeWatchdogStatus(
        observed_at=observed,
        observation_age_seconds=age,
        fresh=age is not None and age <= FRESH_WATCHDOG_SECONDS,
        ok=payload.get("ok") if isinstance(payload.get("ok"), bool) else None,
        blockers=blockers,
    )


def _supervisor_status(payload: dict[str, Any]) -> RuntimeSupervisorStatus:
    supervisor = _mapping(payload.get("supervisor"))
    available = bool(supervisor)
    return RuntimeSupervisorStatus(
        available=available,
        policy_version=str(supervisor.get("policy_version") or "LEGACY_UNKNOWN"),
        decision=str(supervisor.get("decision") or "UNKNOWN"),
        decision_reason=str(supervisor.get("decision_reason") or "").strip() or None,
        heartbeat_stale_seconds=_non_negative_int(supervisor.get("heartbeat_stale_seconds")),
        restart_cooldown_seconds=_non_negative_int(supervisor.get("restart_cooldown_seconds")),
        restart_count=_non_negative_int(supervisor.get("restart_count")) or 0,
        max_daily_restarts=_non_negative_int(supervisor.get("max_daily_restarts")),
        last_action=str(supervisor.get("last_action") or "UNKNOWN"),
        last_reason=str(supervisor.get("last_reason") or "").strip() or None,
        last_restart_at=_parse_datetime(supervisor.get("last_restart_at")),
        last_restart_reason=str(supervisor.get("last_restart_reason") or "").strip() or None,
        last_restart_success=(
            supervisor.get("last_restart_success")
            if isinstance(supervisor.get("last_restart_success"), bool)
            else None
        ),
        cooldown_until=_parse_datetime(supervisor.get("cooldown_until")),
        runtime_issue_after=str(supervisor.get("runtime_issue_after") or "").strip() or None,
    )


def _process_status(
    payload: dict[str, Any],
    watchdog: RuntimeWatchdogStatus,
) -> RuntimeProcessStatus:
    live = _mapping(payload.get("live_after")) or _mapping(payload.get("live_before"))
    tree = _mapping(live.get("process_tree"))
    rows = tree.get("processes") if isinstance(tree.get("processes"), list) else []
    processes = [
        RuntimeProcessLink(
            pid=_positive_int(_mapping(row).get("pid")) or 0,
            parent_pid=_positive_int(_mapping(row).get("parent_pid")) or 0,
            is_owner=bool(_mapping(row).get("is_owner")),
        )
        for row in rows
        if _positive_int(_mapping(row).get("pid"))
    ]
    raw_count = _non_negative_int(tree.get("raw_process_count"))
    logical_count = _non_negative_int(tree.get("logical_session_count"))
    if raw_count is None:
        raw_count = _non_negative_int(live.get("process_count"))
    return RuntimeProcessStatus(
        observed_at=watchdog.observed_at,
        observation_age_seconds=watchdog.observation_age_seconds,
        raw_process_count=raw_count,
        logical_session_count=logical_count,
        tree_state=str(tree.get("tree_state") or "LEGACY_UNKNOWN"),
        processes=processes,
    )


def _market_status(payload: dict[str, Any], now_kst: datetime) -> RuntimeMarketStatus:
    current = _mapping(payload.get("current"))
    observed = _parse_datetime(current.get("received_at") or payload.get("updated_at"))
    code = str(current.get("code") or "").strip() or None
    label = str(current.get("label") or "").strip() or None
    observed_today = observed is not None and observed.astimezone(KST).date() == now_kst.date()
    if observed_today and label in MARKET_OPEN_LABELS:
        expected = True
        source = "KIWOOM_MARKET_STATUS"
    elif observed_today and (label in MARKET_CLOSED_LABELS or str(label or "").startswith("after_hours_")):
        expected = False
        source = "KIWOOM_MARKET_STATUS"
    else:
        minute = now_kst.hour * 60 + now_kst.minute
        expected = now_kst.weekday() < 5 and 9 * 60 <= minute < 15 * 60 + 31
        source = "WEEKDAY_SESSION_FALLBACK" if expected else "OFF_HOURS_CLOCK"
    return RuntimeMarketStatus(
        observed_at=observed,
        code=code,
        label=label,
        expected_running=expected,
        expectation_source=source,
    )


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return _as_aware(datetime.fromisoformat(text))
    except ValueError:
        return None


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value
    return datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        value.second,
        value.microsecond,
        tzinfo=UTC,
        fold=value.fold,
    )


def _age_seconds(value: datetime | None, now: datetime) -> int | None:
    if value is None:
        return None
    return max(0, int((now.astimezone(UTC) - value.astimezone(UTC)).total_seconds()))


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _non_negative_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
