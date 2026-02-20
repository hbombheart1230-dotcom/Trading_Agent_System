from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graphs.trading_graph import run_trading_graph
from libs.runtime.portfolio_allocation import allocate_portfolio_budget


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M27-4 runtime portfolio guard integration check.")
    p.add_argument("--json", action="store_true")
    p.add_argument("--inject-fail", action="store_true")
    return p


def _profiles() -> List[Dict[str, Any]]:
    return [
        {"strategy_id": "trend", "enabled": True, "weight": 0.5},
        {"strategy_id": "mean_reversion", "enabled": True, "weight": 0.3},
        {"strategy_id": "event_driven", "enabled": True, "weight": 0.2},
    ]


def _intents(*, inject_fail: bool) -> List[Dict[str, Any]]:
    if inject_fail:
        return [
            {
                "intent_id": "i1",
                "strategy_id": "trend",
                "symbol": "005930",
                "side": "BUY",
                "requested_notional": 300,
                "priority": 9,
                "confidence": 0.9,
            },
            {
                "intent_id": "i2",
                "strategy_id": "mean_reversion",
                "symbol": "000660",
                "side": "BUY",
                "requested_notional": 200,
                "priority": 8,
                "confidence": 0.8,
            },
        ]

    return [
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
            "priority": 3,
            "confidence": 0.3,
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
        {
            "intent_id": "i4",
            "strategy_id": "event_driven",
            "symbol": "000660",
            "side": "BUY",
            "requested_notional": 350,
            "priority": 9,
            "confidence": 0.9,
        },
        {
            "intent_id": "i5",
            "strategy_id": "mean_reversion",
            "symbol": "000660",
            "side": "BUY",
            "requested_notional": 300,
            "priority": 4,
            "confidence": 0.4,
        },
    ]


def _symbol_caps(*, inject_fail: bool) -> Dict[str, float]:
    if inject_fail:
        return {"005930": 10_000.0, "000660": 10_000.0}
    return {"005930": 10_000.0, "000660": 500.0}


def _strategist(state: Dict[str, Any]) -> Dict[str, Any]:
    return state


def _scanner(state: Dict[str, Any]) -> Dict[str, Any]:
    state["selected"] = {
        "symbol": "005930",
        "risk_score": 0.1,
        "confidence": 0.95,
    }
    return state


def _monitor_factory(intents: List[Dict[str, Any]]):
    def _monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        state["intents"] = list(intents)
        return state

    return _monitor


def _decide_approve(state: Dict[str, Any]) -> Dict[str, Any]:
    state["decision"] = "approve"
    state["decision_reason"] = "integration_check"
    return state


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    inject_fail = bool(args.inject_fail)

    allocation = allocate_portfolio_budget(
        _profiles(),
        total_notional=2000.0,
        reserve_ratio=0.0,
    )

    state: Dict[str, Any] = {
        "use_portfolio_budget_guard": True,
        "portfolio_allocation_result": allocation,
        "symbol_max_notional_map": _symbol_caps(inject_fail=inject_fail),
        "policy": {"min_confidence": 0.0, "max_risk": 1.0, "max_scan_retries": 0},
    }

    out = run_trading_graph(
        state,
        strategist=_strategist,
        scanner=_scanner,
        monitor=_monitor_factory(_intents(inject_fail=inject_fail)),
        decide=_decide_approve,
    )

    pg = out.get("portfolio_guard") if isinstance(out.get("portfolio_guard"), dict) else {}
    reason_counts = pg.get("blocked_reason_counts") if isinstance(pg.get("blocked_reason_counts"), dict) else {}
    failures: List[str] = []

    if not bool(allocation.get("ok")):
        failures.append("allocation ok != true")
    if not bool(pg.get("applied")):
        failures.append("portfolio_guard not applied")
    if int(pg.get("approved_total") or 0) < 1:
        failures.append("approved_total < 1")
    if int(reason_counts.get("strategy_budget_exceeded") or 0) < 1:
        failures.append("strategy_budget_exceeded not observed")
    if int(reason_counts.get("opposite_side_conflict") or 0) < 1:
        failures.append("opposite_side_conflict not observed")
    if int(reason_counts.get("symbol_notional_cap_exceeded") or 0) < 1:
        failures.append("symbol_notional_cap_exceeded not observed")

    result = {
        "ok": len(failures) == 0,
        "inject_fail": inject_fail,
        "decision": str(out.get("decision") or ""),
        "execution_pending": bool(out.get("execution_pending")),
        "portfolio_guard": {
            "applied": bool(pg.get("applied")),
            "intent_total": int(pg.get("intent_total") or 0),
            "approved_total": int(pg.get("approved_total") or 0),
            "blocked_total": int(pg.get("blocked_total") or 0),
            "blocked_reason_counts": reason_counts,
        },
        "approved_intent_total": len(out.get("intents") or []) if isinstance(out.get("intents"), list) else 0,
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(
            f"ok={result['ok']} approved_intent_total={result['approved_intent_total']} "
            f"decision={result['decision'] or 'n/a'} execution_pending={result['execution_pending']} "
            f"failure_total={result['failure_total']}"
        )
        for msg in failures:
            print(msg)
    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
