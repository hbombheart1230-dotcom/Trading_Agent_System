from __future__ import annotations

import json
from pathlib import Path

from graphs.commander_runtime import run_commander_runtime
from graphs.nodes.execute_from_packet import execute_from_packet
from graphs.nodes.monitor_node import monitor_node
from graphs.nodes.scanner_node import scanner_node
from graphs.nodes.strategist_node import strategist_node
from libs.runtime.canonical_artifacts import canonical_run_artifact_paths


def test_strategist_node_emits_canonical_writer(monkeypatch) -> None:
    calls: list[str] = []

    def fake_write(state):  # type: ignore[no-untyped-def]
        calls.append(str(state.get("run_id") or ""))
        return "ok"

    monkeypatch.setattr("graphs.nodes.strategist_node.write_strategist_artifact", fake_write)
    strategist_node({"run_id": "run-1"})
    assert calls == ["run-1"]


def test_scanner_node_emits_canonical_writer(monkeypatch) -> None:
    calls: list[str] = []

    def fake_write(state):  # type: ignore[no-untyped-def]
        calls.append(str(state.get("run_id") or ""))
        return "ok"

    monkeypatch.setattr("graphs.nodes.scanner_node.write_scanner_artifact", fake_write)
    scanner_node(
        {
            "run_id": "run-2",
            "mock_top_value_symbols": ["AAA", "BBB"],
            "mock_top_volume_symbols": ["AAA", "BBB"],
            "mock_top_change_symbols": ["AAA", "BBB"],
            "mock_condition_symbols": ["AAA", "BBB"],
            "skill_data": {
                "market.quote": {
                    "data": [
                        {"symbol": "AAA", "price": 100, "change_pct": 2.1, "volume": 900_000, "value": 4_000_000_000},
                        {"symbol": "BBB", "price": 100, "change_pct": -0.4, "volume": 350_000, "value": 1_000_000_000},
                    ]
                }
            },
        }
    )
    assert calls == ["run-2"]


def test_monitor_node_emits_canonical_writer(monkeypatch) -> None:
    calls: list[str] = []

    def fake_write(state):  # type: ignore[no-untyped-def]
        calls.append(str(state.get("run_id") or ""))
        return "ok"

    monkeypatch.setattr("graphs.nodes.monitor_node.write_monitor_artifact", fake_write)
    monitor_node(
        {
            "run_id": "run-3",
            "plan": {"thesis": "test"},
            "selected": {
                "symbol": "005930",
                "price": 71000.0,
                "features": {"engine_volatility20": 0.02},
            },
            "portfolio_snapshot": {
                "cash": 2_000_000.0,
                "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 120}],
            },
            "policy": {
                "use_exit_policy": True,
                "exit_policy": {"take_profit_pct": 0.01},
            },
        }
    )
    assert calls == ["run-3"]


def test_execute_from_packet_writes_supervisor_and_executor_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path / "reports"))
    catalog = tmp_path / "api_catalog.jsonl"
    catalog.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )
    state = {
        "run_id": "run-4",
        "started_at": "2026-03-18T00:00:00+00:00",
        "catalog_path": str(catalog),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT", "order_type": "market"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    execute_from_packet(state)

    paths = canonical_run_artifact_paths("run-4", day="2026-03-18", reports_root=tmp_path / "reports")
    supervisor = json.loads(paths["supervisor"].read_text(encoding="utf-8"))
    executor = json.loads(paths["executor"].read_text(encoding="utf-8"))
    assert supervisor["agent"] == "supervisor"
    assert executor["agent"] == "executor"
    assert supervisor["run_id"] == "run-4"
    assert executor["run_id"] == "run-4"


def test_commander_runtime_writes_commander_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path / "reports"))

    def fake_graph_runner(state):  # type: ignore[no-untyped-def]
        state["runtime_status"] = "ok"
        state["path"] = "graph_spine"
        return state

    state = {
        "run_id": "run-5",
        "started_at": "2026-03-18T00:00:00+00:00",
        "runtime_plan": {"agents": ["strategist", "scanner", "monitor"]},
    }

    out = run_commander_runtime(state, mode="graph_spine", graph_runner=fake_graph_runner)

    paths = canonical_run_artifact_paths("run-5", day="2026-03-18", reports_root=tmp_path / "reports")
    commander = json.loads(paths["commander"].read_text(encoding="utf-8"))
    commander_shadow = json.loads(paths["commander_shadow"].read_text(encoding="utf-8"))
    assert commander["agent"] == "commander"
    assert commander["run_id"] == "run-5"
    assert commander["decision"] == "graph_spine"
    assert commander["selected_route"] == "full_cycle"
    assert commander["runtime_mode"] == "graph_spine"
    assert commander["runtime_phase"] == "session"
    assert isinstance(commander.get("route_reason_codes"), list)
    assert isinstance(commander.get("open_position_symbols"), list)
    assert isinstance(commander.get("incident_state"), dict)
    assert isinstance(commander.get("portfolio_preflight_result"), dict)
    assert isinstance(commander.get("commander_decision"), dict)
    assert commander.get("shadow_used") in {True, False}
    assert isinstance(commander.get("source_priority"), list)
    assert "session_type" in commander
    assert "agent_invocation_plan" in commander
    assert "final_runtime_path" in commander
    assert "handoff_instruction" in commander
    assert out["path"] == "graph_spine"
    assert commander_shadow["agent"] == "commander"
    assert commander_shadow["mode"] == "shadow"
    assert commander_shadow["shadow_only"] is True
    assert commander_shadow["decision"] == "OBSERVE_ONLY"
    assert commander_shadow["actual_runtime"]["runtime_path"] == "graph_spine"
    assert isinstance(commander_shadow.get("monitor_gate_details"), dict)
    assert isinstance(commander_shadow.get("context_delta_summary"), dict)
    assert isinstance(commander_shadow.get("pre_strategist_shadow_snapshot"), dict)
    assert isinstance(commander_shadow.get("post_strategist_assessment"), dict)
    assert isinstance(commander_shadow.get("post_monitor_assessment"), dict)
    assert isinstance(commander_shadow.get("end_of_cycle_summary"), dict)
    assert commander_shadow.get("shadow_only") is True
    assert commander_shadow.get("integrated_into_commander_decision") is True
    assert commander_shadow.get("integration_version") == "phase1_2"
    assert commander_shadow.get("integration_role") == "upstream_assessment"


def test_commander_runtime_writes_artifact_when_cooldown_blocks_execution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path / "reports"))
    monkeypatch.setenv("COMMANDER_INCIDENT_THRESHOLD", "1")
    monkeypatch.setenv("COMMANDER_COOLDOWN_SEC", "120")

    state = {
        "run_id": "run-6",
        "started_at": "2026-03-18T00:00:00+00:00",
        "resilience": {"incident_count": 1, "cooldown_until_epoch": 0},
    }

    out = run_commander_runtime(state)
    assert str(out.get("runtime_status") or "") == "cooldown_wait"

    paths = canonical_run_artifact_paths("run-6", day="2026-03-18", reports_root=tmp_path / "reports")
    commander = json.loads(paths["commander"].read_text(encoding="utf-8"))
    assert commander.get("selected_route") in {"blocked", "degraded"}
    assert commander.get("cooldown_applied") is True
    assert commander.get("runtime_phase") == "session"


def test_commander_shadow_write_failure_does_not_break_runtime(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path / "reports"))

    def fake_graph_runner(state):  # type: ignore[no-untyped-def]
        state["runtime_status"] = "ok"
        state["path"] = "graph_spine"
        return state

    def fail_shadow(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("shadow write failed")

    monkeypatch.setattr("graphs.commander_runtime.write_commander_shadow_artifact", fail_shadow)

    state = {
        "run_id": "run-7",
        "started_at": "2026-03-18T00:00:00+00:00",
        "runtime_plan": {"agents": ["strategist", "scanner", "monitor"]},
    }

    out = run_commander_runtime(state, mode="graph_spine", graph_runner=fake_graph_runner)

    paths = canonical_run_artifact_paths("run-7", day="2026-03-18", reports_root=tmp_path / "reports")
    assert out["path"] == "graph_spine"
    assert paths["commander"].exists()
    assert not paths["commander_shadow"].exists()
