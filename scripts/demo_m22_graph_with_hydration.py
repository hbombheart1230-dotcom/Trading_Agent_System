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


class _DemoRunner:
    def __init__(self, *, fail: bool = False):
        self.fail = bool(fail)

    def run(self, *, run_id: str, skill: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if self.fail:
            if skill == "market.quote":
                return {"result": {"action": "error", "meta": {"error_type": "TimeoutError"}}}
            if skill == "account.orders":
                return {"result": {"action": "ask", "question": "account required"}}
            if skill == "order.status":
                return {"result": {"action": "error", "meta": {"error_type": "TimeoutError"}}}
            return {"result": {"action": "error", "meta": {"error_type": "unknown_skill"}}}

        if skill == "market.quote":
            sym = str(args.get("symbol") or "")
            px = {"005930": 70500, "000660": 129000, "035420": 198000}.get(sym, 10000)
            return {"result": {"action": "ready", "data": {"symbol": sym, "cur": px}}}
        if skill == "account.orders":
            return {"result": {"action": "ready", "data": {"rows": [{"symbol": "005930", "order_id": "ord-1"}]}}}
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
                        "filled_price": 70400,
                        "order_price": 70500,
                    },
                }
            }
        return {"result": {"action": "error", "meta": {"error_type": "unknown_skill"}}}


def _build_state(*, fail: bool = False) -> Dict[str, Any]:
    return {
        "run_id": "m22-graph-hydration-demo",
        "skill_runner": _DemoRunner(fail=fail),
        "candidates": [{"symbol": "005930"}, {"symbol": "000660"}, {"symbol": "035420"}],
        "mock_scan_results": {
            "005930": {"score": 0.60, "risk_score": 0.20, "confidence": 0.82},
            "000660": {"score": 0.60, "risk_score": 0.20, "confidence": 0.82},
            "035420": {"score": 0.55, "risk_score": 0.25, "confidence": 0.78},
        },
        "plan": {"thesis": "m22_graph_hydration_demo"},
        "order_ref": {"ord_no": "ord-2", "symbol": "005930", "ord_dt": "20260216", "qry_tp": "3"},
    }


def _to_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    selected = state.get("selected") if isinstance(state.get("selected"), dict) else {}
    return {
        "decision": state.get("decision"),
        "execution_pending": bool(state.get("execution_pending")),
        "selected": {
            "symbol": selected.get("symbol"),
            "score": selected.get("score"),
            "risk_score": selected.get("risk_score"),
            "confidence": selected.get("confidence"),
        },
        "skill_fetch": state.get("skill_fetch"),
        "scanner_skill": state.get("scanner_skill"),
        "monitor": state.get("monitor"),
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M22 graph-spine hydration demo")
    p.add_argument("--json", action="store_true")
    p.add_argument("--simulate-timeout", action="store_true")
    return p


def _strategist_passthrough(state: Dict[str, Any]) -> Dict[str, Any]:
    return state


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    state = _build_state(fail=bool(args.simulate_timeout))
    out = run_trading_graph(state, strategist=_strategist_passthrough)
    summary = _to_summary(out)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
