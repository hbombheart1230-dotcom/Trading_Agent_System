from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graphs.nodes.monitor_node import monitor_node
from graphs.nodes.scanner_node import scanner_node


def _build_demo_state(*, simulate_timeout: bool = False) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "plan": {"thesis": "m22_skill_native_demo"},
        "candidates": [
            {"symbol": "005930", "why": "demo"},
            {"symbol": "000660", "why": "demo"},
            {"symbol": "035420", "why": "demo"},
        ],
        # Keep baseline similar to make skill effects visible.
        "mock_scan_results": {
            "005930": {"score": 0.60, "risk_score": 0.20, "confidence": 0.82},
            "000660": {"score": 0.60, "risk_score": 0.20, "confidence": 0.82},
            "035420": {"score": 0.55, "risk_score": 0.25, "confidence": 0.78},
        },
        "skill_results": {
            "market.quote": {
                "005930": {"symbol": "005930", "cur": 70500},
                "000660": {"symbol": "000660", "cur": 129000},
                "035420": {"symbol": "035420", "cur": 198000},
            },
            "account.orders": {
                "rows": [
                    {"symbol": "005930", "order_id": "ord-1"},
                    {"symbol": "005930", "order_id": "ord-2"},
                ]
            },
            "order.status": {
                "ord_no": "ord-2",
                "symbol": "005930",
                "status": "PARTIAL",
                "filled_qty": 1,
                "order_qty": 2,
                "filled_price": 70400,
                "order_price": 70500,
            },
        },
    }
    if simulate_timeout:
        state["skill_results"]["market.quote"] = {"action": "error", "meta": {"error_type": "TimeoutError"}}
        state["skill_results"]["account.orders"] = {"result": {"action": "ask", "question": "account missing"}}
        state["skill_results"]["order.status"] = {"result": {"action": "error", "meta": {"error_type": "TimeoutError"}}}
    return state


def _to_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    selected = state.get("selected") if isinstance(state.get("selected"), dict) else {}
    scan_results = state.get("scan_results") if isinstance(state.get("scan_results"), list) else []
    top: List[Dict[str, Any]] = []
    for row in scan_results[:3]:
        if not isinstance(row, dict):
            continue
        feats = row.get("features") if isinstance(row.get("features"), dict) else {}
        top.append(
            {
                "symbol": row.get("symbol"),
                "score": row.get("score"),
                "risk_score": row.get("risk_score"),
                "confidence": row.get("confidence"),
                "skill_quote_price": feats.get("skill_quote_price"),
                "skill_open_orders": feats.get("skill_open_orders"),
            }
        )
    return {
        "selected": {
            "symbol": selected.get("symbol"),
            "score": selected.get("score"),
            "risk_score": selected.get("risk_score"),
            "confidence": selected.get("confidence"),
        },
        "scanner_skill": state.get("scanner_skill"),
        "monitor": state.get("monitor"),
        "order_lifecycle": (state.get("monitor") or {}).get("order_lifecycle"),
        "top": top,
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M22 skill-native scanner/monitor demo")
    p.add_argument("--json", action="store_true", help="Emit JSON output")
    p.add_argument("--simulate-timeout", action="store_true", help="Show fallback behavior on skill timeout/error")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    state = _build_demo_state(simulate_timeout=bool(args.simulate_timeout))
    state = scanner_node(state)
    state = monitor_node(state)
    summary = _to_summary(state)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        sel = summary.get("selected") or {}
        print(f"selected={sel.get('symbol')} score={sel.get('score')} risk={sel.get('risk_score')}")
        print(f"scanner_skill={json.dumps(summary.get('scanner_skill'), ensure_ascii=False)}")
        print(f"monitor={json.dumps(summary.get('monitor'), ensure_ascii=False)}")
        print("top_candidates=")
        for row in summary.get("top") or []:
            print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
