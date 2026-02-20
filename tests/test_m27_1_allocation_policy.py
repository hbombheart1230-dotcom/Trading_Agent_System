from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from libs.runtime.portfolio_allocation import allocate_portfolio_budget
from scripts.run_m27_allocation_policy_check import main as allocation_check_main


def test_m27_1_allocate_portfolio_budget_proportional():
    out = allocate_portfolio_budget(
        [
            {"strategy_id": "s1", "enabled": True, "weight": 1},
            {"strategy_id": "s2", "enabled": True, "weight": 1},
        ],
        total_notional=100.0,
        reserve_ratio=0.0,
    )
    assert out["ok"] is True
    rows = {x["strategy_id"]: x for x in out["allocations"]}
    assert rows["s1"]["allocated_notional"] == 50.0
    assert rows["s2"]["allocated_notional"] == 50.0
    assert out["unallocated_notional"] == 0.0


def test_m27_1_allocate_portfolio_budget_cap_and_redistribution():
    out = allocate_portfolio_budget(
        [
            {"strategy_id": "s1", "enabled": True, "weight": 0.8, "max_notional_ratio": 0.3},
            {"strategy_id": "s2", "enabled": True, "weight": 0.2},
        ],
        total_notional=100.0,
        reserve_ratio=0.0,
    )
    assert out["ok"] is True
    rows = {x["strategy_id"]: x for x in out["allocations"]}
    assert rows["s1"]["allocated_notional"] == 30.0
    assert rows["s2"]["allocated_notional"] == 70.0
    assert out["allocation_total"] == 100.0


def test_m27_1_allocation_policy_check_script_passes(capsys):
    rc = allocation_check_main(["--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 0
    assert obj["ok"] is True
    assert obj["active_strategy_total"] >= 1
    assert obj["allocation_total"] <= obj["allocatable_notional"] + 1e-8


def test_m27_1_script_file_entrypoint_resolves_repo_imports():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m27_allocation_policy_check.py"
    cp = subprocess.run(
        [sys.executable, str(script), "--json"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
