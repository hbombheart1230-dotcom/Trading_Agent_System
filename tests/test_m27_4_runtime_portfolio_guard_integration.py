from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from graphs.commander_runtime import run_commander_runtime
from graphs.trading_graph import run_trading_graph
from libs.runtime.portfolio_allocation import allocate_portfolio_budget
from scripts.run_m27_runtime_portfolio_guard_check import main as check_main


def _strategist(state: Dict[str, Any]) -> Dict[str, Any]:
    return state


def _scanner(state: Dict[str, Any]) -> Dict[str, Any]:
    state["selected"] = {"symbol": "005930", "risk_score": 0.1, "confidence": 0.9}
    return state


def _monitor(state: Dict[str, Any]) -> Dict[str, Any]:
    state["intents"] = [
        {
            "intent_id": "i1",
            "strategy_id": "trend",
            "symbol": "005930",
            "side": "BUY",
            "requested_notional": 700,
            "priority": 9,
            "confidence": 0.9,
        },
        {
            "intent_id": "i2",
            "strategy_id": "trend",
            "symbol": "005930",
            "side": "BUY",
            "requested_notional": 400,
            "priority": 2,
            "confidence": 0.2,
        },
        {
            "intent_id": "i3",
            "strategy_id": "mean_reversion",
            "symbol": "005930",
            "side": "SELL",
            "requested_notional": 300,
            "priority": 8,
            "confidence": 0.8,
        },
    ]
    return state


def _decide_approve(state: Dict[str, Any]) -> Dict[str, Any]:
    state["decision"] = "approve"
    return state


def test_m27_4_trading_graph_wires_portfolio_guard_node():
    allocation = allocate_portfolio_budget(
        [
            {"strategy_id": "trend", "enabled": True, "weight": 0.5},
            {"strategy_id": "mean_reversion", "enabled": True, "weight": 0.5},
        ],
        total_notional=2000.0,
        reserve_ratio=0.0,
    )

    out = run_trading_graph(
        {
            "use_portfolio_budget_guard": True,
            "portfolio_allocation_result": allocation,
            "symbol_max_notional_map": {"005930": 10_000.0},
        },
        strategist=_strategist,
        scanner=_scanner,
        monitor=_monitor,
        decide=_decide_approve,
    )

    pg = out["portfolio_guard"]
    assert pg["applied"] is True
    assert pg["blocked_reason_counts"]["strategy_budget_exceeded"] >= 1
    assert pg["blocked_reason_counts"]["opposite_side_conflict"] >= 1
    assert len(out["intents"]) == 1


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


def test_m27_4_commander_end_event_includes_portfolio_guard_summary():
    logger = _FakeEventLogger()

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["portfolio_guard"] = {
            "applied": True,
            "approved_total": 1,
            "blocked_total": 2,
            "blocked_reason_counts": {"strategy_budget_exceeded": 1, "opposite_side_conflict": 1},
        }
        return state

    out = run_commander_runtime({"event_logger": logger}, graph_runner=graph_runner)
    assert out["portfolio_guard"]["applied"] is True

    end_rows = [r for r in logger.rows if r.get("stage") == "commander_router" and r.get("event") == "end"]
    assert len(end_rows) == 1
    payload = end_rows[0]["payload"]
    assert payload["path"] == "graph_spine"
    assert payload["portfolio_guard"]["applied"] is True
    assert payload["portfolio_guard"]["blocked_total"] == 2


def test_m27_4_runtime_portfolio_guard_check_passes_default(capsys):
    rc = check_main(["--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 0
    assert obj["ok"] is True
    assert obj["failure_total"] == 0
    assert obj["portfolio_guard"]["blocked_reason_counts"]["strategy_budget_exceeded"] >= 1


def test_m27_4_runtime_portfolio_guard_check_fails_when_injected(capsys):
    rc = check_main(["--inject-fail", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 3
    assert obj["ok"] is False
    assert obj["failure_total"] >= 1


def test_m27_4_script_file_entrypoint_resolves_repo_imports():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m27_runtime_portfolio_guard_check.py"
    cp = subprocess.run(
        [sys.executable, str(script), "--json"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
