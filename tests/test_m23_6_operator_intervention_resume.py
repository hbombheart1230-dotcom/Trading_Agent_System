from __future__ import annotations

import json
from typing import Any, Dict

from graphs.commander_runtime import run_commander_runtime
from scripts.run_commander_runtime_once import main as runtime_once_main


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


def test_m23_6_operator_resume_clears_cooldown_and_continues_runtime():
    called = {"graph": 0}
    logger = _FakeEventLogger()

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        state["path"] = "graph_spine"
        return state

    out = run_commander_runtime(
        {
            "runtime_control": "resume",
            "now_epoch": 100,
            "event_logger": logger,
            "resilience": {
                "degrade_mode": True,
                "degrade_reason": "incident_threshold_cooldown",
                "incident_count": 5,
                "cooldown_until_epoch": 200,
                "last_error_type": "TimeoutError",
            },
            "resilience_policy": {"incident_threshold": 3, "cooldown_sec": 60},
        },
        graph_runner=graph_runner,
    )

    assert called["graph"] == 1
    assert out["path"] == "graph_spine"
    assert out["runtime_transition"] == "resume"
    assert out["runtime_status"] == "resuming"

    resilience = out["resilience"]
    assert resilience["degrade_mode"] is False
    assert resilience["degrade_reason"] == ""
    assert int(resilience["incident_count"]) == 0
    assert int(resilience["cooldown_until_epoch"]) == 0
    assert resilience["last_error_type"] == ""

    rows = [r for r in logger.rows if r.get("stage") == "commander_router"]
    assert [r.get("event") for r in rows] == ["route", "transition", "intervention", "end"]
    assert rows[2]["payload"]["type"] == "operator_resume"


def test_m23_6_runtime_once_cli_accepts_resume_control(capsys):
    rc = runtime_once_main(["--runtime-control", "resume", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["runtime_transition"] == "resume"
    assert obj["runtime_status"] == "resuming"
    assert obj["path"] == "graph_spine"
