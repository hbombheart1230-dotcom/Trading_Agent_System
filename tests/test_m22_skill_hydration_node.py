from __future__ import annotations

import json
from typing import Any, Dict

from graphs.nodes.hydrate_skill_results_node import hydrate_skill_results_node
from graphs.nodes.monitor_node import monitor_node
from graphs.nodes.scanner_node import scanner_node
from scripts.demo_m22_skill_hydration import main as hydration_demo_main


class _FakeSkillRunnerOk:
    def run(self, *, run_id: str, skill: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if skill == "market.quote":
            sym = str(args.get("symbol") or "")
            return {"result": {"action": "ready", "data": {"symbol": sym, "cur": 1000}}}
        if skill == "account.orders":
            return {"result": {"action": "ready", "data": {"rows": [{"symbol": "AAA", "order_id": "ord-1"}]}}}
        if skill == "order.status":
            return {
                "result": {
                    "action": "ready",
                    "data": {
                        "ord_no": str(args.get("ord_no") or ""),
                        "symbol": str(args.get("symbol") or ""),
                        "status": "PARTIAL",
                        "filled_qty": 1,
                        "order_qty": 2,
                    },
                }
            }
        return {"result": {"action": "error", "meta": {"error_type": "unknown_skill"}}}


class _FakeSkillRunnerFail:
    def run(self, *, run_id: str, skill: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if skill == "market.quote":
            return {"result": {"action": "error", "meta": {"error_type": "TimeoutError"}}}
        if skill == "account.orders":
            return {"result": {"action": "ask", "question": "account required"}}
        if skill == "order.status":
            return {"result": {"action": "error", "meta": {"error_type": "TimeoutError"}}}
        return {"result": {"action": "error", "meta": {"error_type": "unknown_skill"}}}


class _CaptureLogger:
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
        row = {
            "run_id": run_id,
            "stage": stage,
            "event": event,
            "payload": payload,
            "ts": ts,
        }
        self.rows.append(row)
        return row


def test_m22_hydration_node_populates_skill_results_for_scanner_monitor():
    state = {
        "run_id": "r-m22-5-ok",
        "skill_runner": _FakeSkillRunnerOk(),
        "candidates": [{"symbol": "AAA"}, {"symbol": "BBB"}],
        "mock_scan_results": {
            "AAA": {"score": 0.4, "risk_score": 0.2, "confidence": 0.8},
            "BBB": {"score": 0.6, "risk_score": 0.2, "confidence": 0.8},
        },
        "plan": {"thesis": "demo"},
        "order_ref": {"ord_no": "ord-1", "symbol": "AAA", "ord_dt": "20260216", "qry_tp": "3"},
    }

    out = hydrate_skill_results_node(state)
    assert out["skill_fetch"]["used_runner"] is True
    assert out["skill_fetch"]["runner_source"] == "state.skill_runner"
    assert out["skill_fetch"]["attempted"]["market.quote"] == 2
    assert out["skill_fetch"]["errors_total"] == 0
    assert isinstance(out.get("skill_results"), dict)
    assert "market.quote" in out["skill_results"]
    assert "account.orders" in out["skill_results"]
    assert "order.status" in out["skill_results"]

    out = scanner_node(out)
    out = monitor_node(out)
    assert out["scanner_skill"]["used"] is True
    assert out["monitor"]["order_status_loaded"] is True
    assert out["monitor"]["order_lifecycle_loaded"] is True
    assert out["monitor"]["order_lifecycle"]["stage"] == "partial_fill"


def test_m22_hydration_logs_skill_hydration_summary_event():
    logger = _CaptureLogger()
    state = {
        "run_id": "r-m22-9-log",
        "event_logger": logger,
        "skill_runner": _FakeSkillRunnerOk(),
        "candidates": [{"symbol": "AAA"}],
        "order_ref": {"ord_no": "ord-1", "symbol": "AAA", "ord_dt": "20260216", "qry_tp": "3"},
    }
    out = hydrate_skill_results_node(state)
    rows = [r for r in logger.rows if r.get("stage") == "skill_hydration" and r.get("event") == "summary"]
    assert len(rows) == 1
    assert rows[0]["payload"]["used_runner"] is True
    assert rows[0]["payload"]["runner_source"] == "state.skill_runner"
    assert rows[0]["payload"]["errors_total"] == 0
    assert out["skill_fetch"]["used_runner"] is True


def test_m22_hydration_node_failure_keeps_pipeline_safe():
    state = {
        "run_id": "r-m22-5-fail",
        "skill_runner": _FakeSkillRunnerFail(),
        "candidates": [{"symbol": "AAA"}, {"symbol": "BBB"}],
        "mock_scan_results": {
            "AAA": {"score": 0.3, "risk_score": 0.2, "confidence": 0.8},
            "BBB": {"score": 0.7, "risk_score": 0.2, "confidence": 0.8},
        },
        "selected": {"symbol": "BBB", "score": 0.7, "risk_score": 0.2, "confidence": 0.8},
        "order_ref": {"ord_no": "ord-2", "symbol": "BBB", "ord_dt": "20260216", "qry_tp": "3"},
    }

    out = hydrate_skill_results_node(state)
    assert out["skill_fetch"]["used_runner"] is True
    assert out["skill_fetch"]["runner_source"] == "state.skill_runner"
    assert out["skill_fetch"]["errors_total"] >= 2

    out = scanner_node(out)
    assert out["selected"]["symbol"] == "BBB"
    assert out["scanner_skill"]["fallback"] is True

    out = monitor_node(out)
    assert out["monitor"]["order_status_loaded"] is False
    assert out["monitor"]["order_status_fallback"] is True


def test_m22_hydration_demo_script_outputs_fetch_summary(capsys):
    rc = hydration_demo_main(["--json"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    obj = json.loads(out)
    assert obj["skill_fetch"]["used_runner"] is True
    assert obj["skill_fetch"]["runner_source"] == "state.skill_runner"
    assert "attempted" in obj["skill_fetch"]
    assert "monitor" in obj
    assert "scanner_skill" in obj


def test_m22_hydration_demo_script_timeout_mode(capsys):
    rc = hydration_demo_main(["--simulate-timeout", "--json"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    obj = json.loads(out)
    assert obj["skill_fetch"]["errors_total"] >= 1
    assert obj["scanner_skill"]["fallback"] is True
    assert obj["monitor"]["order_status_fallback"] is True


def test_m22_hydration_uses_state_runner_factory_when_runner_missing():
    state = {
        "run_id": "r-m22-8-factory",
        "skill_runner_factory": lambda: _FakeSkillRunnerOk(),
        "candidates": [{"symbol": "AAA"}],
        "plan": {"thesis": "demo"},
    }

    out = hydrate_skill_results_node(state)
    assert out["skill_fetch"]["used_runner"] is True
    assert out["skill_fetch"]["runner_source"] == "state.skill_runner_factory"
    assert out["skill_fetch"]["attempted"]["market.quote"] == 1


def test_m22_hydration_can_auto_build_composite_runner(monkeypatch):
    class _AutoRunner(_FakeSkillRunnerOk):
        pass

    monkeypatch.setattr(
        "graphs.nodes.hydrate_skill_results_node._build_composite_skill_runner",
        lambda state: _AutoRunner(),
    )

    state = {
        "run_id": "r-m22-8-auto",
        "auto_skill_runner": True,
        "candidates": [{"symbol": "AAA"}],
    }
    out = hydrate_skill_results_node(state)
    assert out["skill_fetch"]["used_runner"] is True
    assert out["skill_fetch"]["runner_source"] == "auto.composite_skill_runner"
    assert out["skill_fetch"]["attempted"]["market.quote"] == 1


def test_m22_hydration_auto_runner_failure_is_safe(monkeypatch):
    def _raise(state):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "graphs.nodes.hydrate_skill_results_node._build_composite_skill_runner",
        _raise,
    )

    state = {
        "run_id": "r-m22-8-auto-fail",
        "auto_skill_runner": True,
        "candidates": [{"symbol": "AAA"}],
    }
    out = hydrate_skill_results_node(state)
    assert out["skill_fetch"]["used_runner"] is False
    assert out["skill_fetch"]["runner_source"] == "none"
    assert out["skill_fetch"]["errors_total"] >= 1
    assert any("auto_runner:exception:RuntimeError" in x for x in out["skill_fetch"]["errors"])
