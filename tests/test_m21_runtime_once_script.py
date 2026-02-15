from __future__ import annotations

import json

from scripts.run_commander_runtime_once import main


def test_m21_runtime_once_script_default_smoke_json(capsys):
    rc = main(["--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["live"] is False
    assert obj["runtime_mode"] == "graph_spine"
    assert obj["path"] == "graph_spine"
    assert obj["runtime_status"] == "running"
    assert obj["runtime_agents"] == [
        "commander_router",
        "strategist",
        "scanner",
        "monitor",
        "supervisor",
        "executor",
        "reporter",
    ]


def test_m21_runtime_once_script_decision_packet_smoke_json(capsys):
    rc = main(["--mode", "decision_packet", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["runtime_mode"] == "decision_packet"
    assert obj["path"] == "decision_packet"
    assert obj["execution_allowed"] is True
    assert obj["runtime_agents"] == [
        "commander_router",
        "strategist",
        "supervisor",
        "executor",
        "reporter",
    ]


def test_m21_runtime_once_script_pause_control(capsys):
    rc = main(["--runtime-control", "pause", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["runtime_status"] == "paused"
    assert obj["runtime_transition"] == "pause"
    assert obj["path"] is None
