from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from libs.runtime.intent_conflict_resolver import resolve_intent_conflicts
from scripts.run_m27_conflict_resolution_check import main as check_main


def test_m27_2_resolver_blocks_opposite_side_for_same_symbol():
    out = resolve_intent_conflicts(
        [
            {
                "intent_id": "i1",
                "strategy_id": "s1",
                "symbol": "005930",
                "side": "BUY",
                "qty": 1,
                "price": 100,
                "priority": 10,
                "confidence": 0.9,
            },
            {
                "intent_id": "i2",
                "strategy_id": "s2",
                "symbol": "005930",
                "side": "SELL",
                "qty": 1,
                "price": 100,
                "priority": 1,
                "confidence": 0.1,
            },
        ],
        symbol_max_notional_map={"005930": 1_000_000.0},
    )
    assert out["ok"] is True
    assert out["approved_total"] == 1
    assert out["blocked_reason_counts"]["opposite_side_conflict"] == 1
    approved = out["approved"][0]
    assert approved["side"] == "BUY"


def test_m27_2_resolver_applies_symbol_notional_cap():
    out = resolve_intent_conflicts(
        [
            {
                "intent_id": "i1",
                "strategy_id": "s1",
                "symbol": "000660",
                "side": "BUY",
                "qty": 4,
                "price": 40,
                "priority": 10,
                "confidence": 0.9,
            },
            {
                "intent_id": "i2",
                "strategy_id": "s2",
                "symbol": "000660",
                "side": "BUY",
                "qty": 3,
                "price": 40,
                "priority": 1,
                "confidence": 0.1,
            },
        ],
        symbol_max_notional_map={"000660": 200.0},
    )
    assert out["ok"] is True
    assert out["approved_total"] == 1
    assert out["blocked_reason_counts"]["symbol_notional_cap_exceeded"] == 1
    assert out["approved"][0]["intent"]["intent_id"] == "i1"


def test_m27_2_conflict_resolution_check_passes_default(capsys):
    rc = check_main(["--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 0
    assert obj["ok"] is True
    assert obj["failure_total"] == 0
    assert obj["blocked_reason_counts"]["opposite_side_conflict"] >= 1
    assert obj["blocked_reason_counts"]["symbol_notional_cap_exceeded"] >= 1


def test_m27_2_conflict_resolution_check_fails_when_injected(capsys):
    rc = check_main(["--inject-fail", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 3
    assert obj["ok"] is False
    assert obj["failure_total"] >= 1


def test_m27_2_script_file_entrypoint_resolves_repo_imports():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m27_conflict_resolution_check.py"
    cp = subprocess.run(
        [sys.executable, str(script), "--json"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
