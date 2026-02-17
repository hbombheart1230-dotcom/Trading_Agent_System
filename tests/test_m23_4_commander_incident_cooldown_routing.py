from __future__ import annotations

from typing import Any, Dict

import pytest

from graphs.commander_runtime import run_commander_runtime


class _FakeEventLogger:
    def __init__(self) -> None:
        self.rows: list[Dict[str, Any]] = []

    def log(
        self,
        *,
        run_id: str,
        stage: str,
        event: str,
        payload: Dict[str, Any],
        ts: str | None = None,
    ) -> Dict[str, Any]:
        row = {"run_id": run_id, "stage": stage, "event": event, "payload": payload, "ts": ts}
        self.rows.append(row)
        return row


def test_m23_4_commander_blocks_when_cooldown_active():
    called = {"graph": 0}
    logger = _FakeEventLogger()

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        return state

    out = run_commander_runtime(
        {
            "now_epoch": 100,
            "event_logger": logger,
            "resilience": {"incident_count": 5, "cooldown_until_epoch": 200},
            "resilience_policy": {"incident_threshold": 3, "cooldown_sec": 60},
        },
        graph_runner=graph_runner,
    )

    assert out["runtime_status"] == "cooldown_wait"
    assert out["runtime_transition"] == "cooldown"
    assert out["resilience"]["degrade_mode"] is True
    assert called["graph"] == 0

    rows = [r for r in logger.rows if r.get("stage") == "commander_router"]
    assert [r.get("event") for r in rows] == ["route", "transition", "resilience", "end"]
    assert rows[1]["payload"]["reason"] == "cooldown_active"


def test_m23_4_commander_opens_cooldown_when_incident_threshold_reached():
    called = {"graph": 0}

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        return state

    out = run_commander_runtime(
        {
            "now_epoch": 100,
            "resilience": {"incident_count": 3, "cooldown_until_epoch": 0},
            "resilience_policy": {"incident_threshold": 3, "cooldown_sec": 60},
        },
        graph_runner=graph_runner,
    )

    assert out["runtime_status"] == "cooldown_wait"
    assert out["runtime_transition"] == "cooldown"
    assert int(out["resilience"]["cooldown_until_epoch"]) == 160
    assert out["resilience"]["degrade_mode"] is True
    assert called["graph"] == 0


def test_m23_4_commander_registers_incident_on_runtime_exception():
    logger = _FakeEventLogger()

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        raise RuntimeError("boom")

    state: Dict[str, Any] = {
        "now_epoch": 100,
        "event_logger": logger,
        "resilience": {"incident_count": 1, "cooldown_until_epoch": 0},
        "resilience_policy": {"incident_threshold": 2, "cooldown_sec": 30},
    }

    with pytest.raises(RuntimeError):
        run_commander_runtime(state, graph_runner=graph_runner)

    assert state["runtime_status"] == "error"
    assert int(state["resilience"]["incident_count"]) == 2
    assert state["resilience"]["last_error_type"] == "RuntimeError"
    assert int(state["resilience"]["cooldown_until_epoch"]) == 130
    assert state["resilience"]["degrade_mode"] is True

    rows = [r for r in logger.rows if r.get("stage") == "commander_router"]
    assert [r.get("event") for r in rows] == ["route", "error"]
    assert rows[-1]["payload"]["error_type"] == "RuntimeError"

