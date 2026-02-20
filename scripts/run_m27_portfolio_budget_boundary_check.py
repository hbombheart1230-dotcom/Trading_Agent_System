from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.runtime.portfolio_allocation import allocate_portfolio_budget
from libs.runtime.portfolio_budget_guard import apply_portfolio_budget_guard


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M27-3 portfolio budget boundary check.")
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


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    inject_fail = bool(args.inject_fail)

    allocation = allocate_portfolio_budget(
        _profiles(),
        total_notional=2000.0,
        reserve_ratio=0.0,
    )

    out_guard = apply_portfolio_budget_guard(
        _intents(inject_fail=inject_fail),
        allocation_result=allocation,
        symbol_max_notional_map=_symbol_caps(inject_fail=inject_fail),
    )

    failures: List[str] = list(out_guard.get("failures") or [])
    reason_counts = (
        out_guard.get("blocked_reason_counts") if isinstance(out_guard.get("blocked_reason_counts"), dict) else {}
    )

    if not bool(allocation.get("ok")):
        failures.append("allocation ok != true")
    if int(out_guard.get("approved_total") or 0) < 1:
        failures.append("approved_total < 1")
    if int(reason_counts.get("strategy_budget_exceeded") or 0) < 1:
        failures.append("strategy_budget_exceeded not observed")
    if int(reason_counts.get("opposite_side_conflict") or 0) < 1:
        failures.append("opposite_side_conflict not observed")
    if int(reason_counts.get("symbol_notional_cap_exceeded") or 0) < 1:
        failures.append("symbol_notional_cap_exceeded not observed")

    out = {
        "ok": len(failures) == 0,
        "inject_fail": inject_fail,
        "allocation": {
            "ok": bool(allocation.get("ok")),
            "active_strategy_total": int(allocation.get("active_strategy_total") or 0),
            "allocation_total": float(allocation.get("allocation_total") or 0.0),
            "allocations": allocation.get("allocations") or [],
        },
        "guard": {
            "ok": bool(out_guard.get("ok")),
            "intent_total": int(out_guard.get("intent_total") or 0),
            "budget_screened_total": int(out_guard.get("budget_screened_total") or 0),
            "approved_total": int(out_guard.get("approved_total") or 0),
            "blocked_total": int(out_guard.get("blocked_total") or 0),
            "blocked_reason_counts": reason_counts,
            "strategy_budget": out_guard.get("strategy_budget") or {},
        },
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} intent_total={out['guard']['intent_total']} "
            f"approved_total={out['guard']['approved_total']} blocked_total={out['guard']['blocked_total']} "
            f"failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
