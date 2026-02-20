from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from libs.runtime.portfolio_allocation import allocate_portfolio_budget
from libs.runtime.portfolio_budget_guard import apply_portfolio_budget_guard
from scripts.run_m27_portfolio_budget_boundary_check import main as boundary_check_main


def test_m27_3_budget_guard_blocks_strategy_budget_overflow():
    allocation = allocate_portfolio_budget(
        [{"strategy_id": "trend", "enabled": True, "weight": 1.0}],
        total_notional=100.0,
        reserve_ratio=0.0,
    )
    out = apply_portfolio_budget_guard(
        [
            {"intent_id": "i1", "strategy_id": "trend", "symbol": "005930", "side": "BUY", "requested_notional": 70},
            {"intent_id": "i2", "strategy_id": "trend", "symbol": "005930", "side": "BUY", "requested_notional": 40},
        ],
        allocation_result=allocation,
        symbol_max_notional_map={"005930": 1_000.0},
    )
    assert out["ok"] is True
    assert out["approved_total"] == 1
    assert out["blocked_reason_counts"]["strategy_budget_exceeded"] == 1


def test_m27_3_budget_guard_integration_applies_conflict_and_symbol_cap():
    allocation = allocate_portfolio_budget(
        [
            {"strategy_id": "trend", "enabled": True, "weight": 0.5},
            {"strategy_id": "mean_reversion", "enabled": True, "weight": 0.5},
        ],
        total_notional=2000.0,
        reserve_ratio=0.0,
    )
    out = apply_portfolio_budget_guard(
        [
            {
                "intent_id": "i1",
                "strategy_id": "trend",
                "symbol": "005930",
                "side": "BUY",
                "requested_notional": 450,
                "priority": 9,
                "confidence": 0.9,
            },
            {
                "intent_id": "i2",
                "strategy_id": "mean_reversion",
                "symbol": "005930",
                "side": "SELL",
                "requested_notional": 300,
                "priority": 8,
                "confidence": 0.8,
            },
            {
                "intent_id": "i3",
                "strategy_id": "mean_reversion",
                "symbol": "000660",
                "side": "BUY",
                "requested_notional": 350,
                "priority": 7,
                "confidence": 0.7,
            },
            {
                "intent_id": "i4",
                "strategy_id": "mean_reversion",
                "symbol": "000660",
                "side": "BUY",
                "requested_notional": 250,
                "priority": 2,
                "confidence": 0.2,
            },
        ],
        allocation_result=allocation,
        symbol_max_notional_map={"000660": 500.0, "005930": 10_000.0},
    )
    assert out["ok"] is True
    assert out["blocked_reason_counts"]["opposite_side_conflict"] >= 1
    assert out["blocked_reason_counts"]["symbol_notional_cap_exceeded"] >= 1


def test_m27_3_boundary_check_script_passes_default(capsys):
    rc = boundary_check_main(["--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 0
    assert obj["ok"] is True
    assert obj["failure_total"] == 0


def test_m27_3_boundary_check_script_fails_when_injected(capsys):
    rc = boundary_check_main(["--inject-fail", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 3
    assert obj["ok"] is False
    assert obj["failure_total"] >= 1


def test_m27_3_script_file_entrypoint_resolves_repo_imports():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m27_portfolio_budget_boundary_check.py"
    cp = subprocess.run(
        [sys.executable, str(script), "--json"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
