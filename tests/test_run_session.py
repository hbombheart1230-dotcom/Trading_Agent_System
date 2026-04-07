from __future__ import annotations

import json

import scripts.run_session as mod


def test_build_execution_plan_live_intraday_uses_loop_backend() -> None:
    parser = mod._build_parser(mod.ROOT / ".env")
    args = parser.parse_args(["--mode", "live", "--phase", "intraday"])
    plan = mod.build_execution_plan(args)
    assert plan["official_entrypoint"] == "scripts/run_session.py"
    assert plan["route_selected"] == "commander_live_intraday_loop"
    assert plan["implementation"] == "scripts.run_m13_live_loop.main"
    assert plan["commander_phase"] == "session"


def test_build_execution_plan_mock_intraday_probe_routes_to_probe() -> None:
    parser = mod._build_parser(mod.ROOT / ".env")
    args = parser.parse_args(
        [
            "--mode",
            "mock",
            "--phase",
            "intraday",
            "--probe",
            "--probe-symbol",
            "000660",
        ]
    )
    plan = mod.build_execution_plan(args)
    assert plan["route_selected"] == "commander_mock_intraday_probe"
    assert plan["implementation"] == "scripts.run_m31_agent_chain_probe.main"
    assert "--symbol" in plan["argv"]
    assert "000660" in plan["argv"]


def test_main_dry_run_emits_json_plan(capsys) -> None:
    rc = mod.main(["--mode", "mock", "--phase", "watch", "--dry-run", "--json"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["official_entrypoint"] == "scripts/run_session.py"
    assert out["route_selected"] == "commander_mock_watch"
    assert out["implementation"] == "scripts.run_live_session_watch.main"
