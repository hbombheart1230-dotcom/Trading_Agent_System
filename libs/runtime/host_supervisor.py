from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


POLICY_VERSION = "host_supervisor.v1"
HEARTBEAT_STALE_SECONDS = 300
RESTART_COOLDOWN_SECONDS = 600
MAX_DAILY_RESTARTS = 3


@dataclass(frozen=True, slots=True)
class SupervisorDecision:
    action: str
    reason: str
    restart_allowed: bool


def evaluate_supervisor(
    live: dict[str, Any],
    state: dict[str, Any],
    *,
    now: datetime,
) -> SupervisorDecision:
    reason = recovery_reason(live)
    if not reason:
        return SupervisorDecision("NOOP", "runtime_healthy", False)

    restart_count = _non_negative_int(state.get("restart_count"))
    if restart_count >= MAX_DAILY_RESTARTS:
        return SupervisorDecision("BLOCKED", "daily_restart_limit_reached", False)

    cooldown_until = _parse_datetime(state.get("cooldown_until"), now)
    if cooldown_until is not None and now < cooldown_until:
        return SupervisorDecision("BLOCKED", "restart_cooldown_active", False)
    return SupervisorDecision("RECOVER", reason, True)


def recovery_reason(live: dict[str, Any]) -> str:
    if not bool(live.get("running")):
        return "live_session_not_running"
    tree = live.get("process_tree") if isinstance(live.get("process_tree"), dict) else {}
    if _non_negative_int(tree.get("logical_session_count")) > 1:
        return "duplicate_runtime_session"
    if str(tree.get("tree_state") or "") == "OWNER_MISSING":
        return "lock_owner_missing"
    heartbeat_age = _optional_non_negative_int(live.get("heartbeat_age_seconds"))
    if heartbeat_age is None:
        return "heartbeat_missing"
    if heartbeat_age > HEARTBEAT_STALE_SECONDS:
        return "heartbeat_stale"
    return ""


def initial_supervisor_state(day: str) -> dict[str, Any]:
    return {
        "schema_version": POLICY_VERSION,
        "day": day,
        "restart_count": 0,
        "last_restart_at": None,
        "last_restart_reason": None,
        "last_restart_success": None,
        "cooldown_until": None,
        "last_watchdog_at": None,
        "last_action": "NOT_RUN",
        "last_reason": None,
    }


def load_supervisor_state(path: Path, day: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return initial_supervisor_state(day)
    if not isinstance(payload, dict) or str(payload.get("day") or "") != day:
        return initial_supervisor_state(day)
    state = initial_supervisor_state(day)
    state.update(payload)
    state["restart_count"] = _non_negative_int(state.get("restart_count"))
    return state


def record_watchdog_result(
    state: dict[str, Any],
    decision: SupervisorDecision,
    *,
    now: datetime,
    recovery_attempted: bool,
    recovery_success: bool | None,
) -> dict[str, Any]:
    updated = dict(state)
    updated["schema_version"] = POLICY_VERSION
    updated["last_watchdog_at"] = now.isoformat(timespec="seconds")
    updated["last_reason"] = decision.reason
    if recovery_attempted:
        updated["restart_count"] = _non_negative_int(updated.get("restart_count")) + 1
        updated["last_restart_at"] = now.isoformat(timespec="seconds")
        updated["last_restart_reason"] = decision.reason
        updated["last_restart_success"] = bool(recovery_success)
        updated["cooldown_until"] = (now + timedelta(seconds=RESTART_COOLDOWN_SECONDS)).isoformat(timespec="seconds")
        updated["last_action"] = "RECOVERED" if recovery_success else "RECOVERY_FAILED"
    elif decision.action == "BLOCKED":
        updated["last_action"] = "RECOVERY_BLOCKED"
    else:
        updated["last_action"] = "HEALTHY"
    return updated


def write_supervisor_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def public_supervisor_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "heartbeat_stale_seconds": HEARTBEAT_STALE_SECONDS,
        "restart_cooldown_seconds": RESTART_COOLDOWN_SECONDS,
        "max_daily_restarts": MAX_DAILY_RESTARTS,
        "restart_count": _non_negative_int(state.get("restart_count")),
        "last_restart_at": state.get("last_restart_at"),
        "last_restart_reason": state.get("last_restart_reason"),
        "last_restart_success": state.get("last_restart_success"),
        "cooldown_until": state.get("cooldown_until"),
        "last_watchdog_at": state.get("last_watchdog_at"),
        "last_action": str(state.get("last_action") or "UNKNOWN"),
        "last_reason": state.get("last_reason"),
    }


def _parse_datetime(value: Any, reference: datetime) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=reference.tzinfo)
    return parsed.astimezone(reference.tzinfo) if reference.tzinfo else parsed


def _non_negative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, parsed)
