from __future__ import annotations

from datetime import datetime, timedelta

from libs.runtime.host_supervisor import (
    MAX_DAILY_RESTARTS,
    evaluate_supervisor,
    initial_supervisor_state,
    record_watchdog_result,
)


NOW = datetime.fromisoformat("2026-08-27T10:00:00+09:00")


def live(*, running: bool = True, heartbeat_age: int | None = 30, sessions: int = 1, tree_state: str = "NORMAL_PROCESS_TREE"):
    return {
        "running": running,
        "heartbeat_age_seconds": heartbeat_age,
        "process_tree": {"logical_session_count": sessions, "tree_state": tree_state},
    }


def test_healthy_runtime_is_not_restarted() -> None:
    decision = evaluate_supervisor(live(), initial_supervisor_state("2026-08-27"), now=NOW)
    assert decision.action == "NOOP"
    assert decision.reason == "runtime_healthy"


def test_stale_heartbeat_and_duplicate_session_are_recoverable() -> None:
    state = initial_supervisor_state("2026-08-27")
    assert evaluate_supervisor(live(heartbeat_age=301), state, now=NOW).reason == "heartbeat_stale"
    assert evaluate_supervisor(live(sessions=2), state, now=NOW).reason == "duplicate_runtime_session"


def test_cooldown_blocks_restart() -> None:
    state = initial_supervisor_state("2026-08-27")
    state["cooldown_until"] = (NOW + timedelta(minutes=5)).isoformat()
    decision = evaluate_supervisor(live(running=False), state, now=NOW)
    assert decision.action == "BLOCKED"
    assert decision.reason == "restart_cooldown_active"


def test_daily_limit_blocks_restart() -> None:
    state = initial_supervisor_state("2026-08-27")
    state["restart_count"] = MAX_DAILY_RESTARTS
    decision = evaluate_supervisor(live(running=False), state, now=NOW)
    assert decision.action == "BLOCKED"
    assert decision.reason == "daily_restart_limit_reached"


def test_recovery_result_updates_count_and_cooldown() -> None:
    state = record_watchdog_result(
        initial_supervisor_state("2026-08-27"),
        evaluate_supervisor(live(running=False), initial_supervisor_state("2026-08-27"), now=NOW),
        now=NOW,
        recovery_attempted=True,
        recovery_success=True,
    )
    assert state["restart_count"] == 1
    assert state["last_action"] == "RECOVERED"
    assert state["last_restart_reason"] == "live_session_not_running"
