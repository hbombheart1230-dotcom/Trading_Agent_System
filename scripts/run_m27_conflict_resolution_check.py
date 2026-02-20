from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.runtime.intent_conflict_resolver import resolve_intent_conflicts


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M27-2 intent conflict resolution policy check.")
    p.add_argument("--json", action="store_true")
    p.add_argument("--inject-fail", action="store_true")
    return p


def _default_intents(*, inject_fail: bool) -> List[Dict[str, Any]]:
    if inject_fail:
        # no opposite-side conflict and no cap overflow on purpose.
        return [
            {
                "intent_id": "i1",
                "strategy_id": "trend",
                "symbol": "005930",
                "side": "BUY",
                "qty": 1,
                "price": 100,
                "priority": 9,
                "confidence": 0.9,
            },
            {
                "intent_id": "i2",
                "strategy_id": "mean_reversion",
                "symbol": "000660",
                "side": "BUY",
                "qty": 1,
                "price": 100,
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
            "qty": 1,
            "price": 100,
            "priority": 9,
            "confidence": 0.9,
        },
        {
            "intent_id": "i2",
            "strategy_id": "mean_reversion",
            "symbol": "005930",
            "side": "SELL",
            "qty": 1,
            "price": 100,
            "priority": 3,
            "confidence": 0.4,
        },
        {
            "intent_id": "i3",
            "strategy_id": "event_driven",
            "symbol": "000660",
            "side": "BUY",
            "qty": 4,
            "price": 40,
            "priority": 8,
            "confidence": 0.8,
        },
        {
            "intent_id": "i4",
            "strategy_id": "trend",
            "symbol": "000660",
            "side": "BUY",
            "qty": 3,
            "price": 40,
            "priority": 2,
            "confidence": 0.4,
        },
    ]


def _default_caps(*, inject_fail: bool) -> Dict[str, float]:
    if inject_fail:
        return {"005930": 1_000_000.0, "000660": 1_000_000.0}
    return {"005930": 1_000_000.0, "000660": 200.0}


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    inject_fail = bool(args.inject_fail)

    intents = _default_intents(inject_fail=inject_fail)
    caps = _default_caps(inject_fail=inject_fail)
    result = resolve_intent_conflicts(
        intents,
        default_symbol_max_notional=0.0,
        symbol_max_notional_map=caps,
    )

    reason_counts = result.get("blocked_reason_counts") if isinstance(result.get("blocked_reason_counts"), dict) else {}
    failures: List[str] = list(result.get("failures") or [])

    if int(result.get("approved_total") or 0) < 1:
        failures.append("approved_total < 1")
    if int(reason_counts.get("opposite_side_conflict") or 0) < 1:
        failures.append("opposite_side_conflict not observed")
    if int(reason_counts.get("symbol_notional_cap_exceeded") or 0) < 1:
        failures.append("symbol_notional_cap_exceeded not observed")

    out = {
        "ok": len(failures) == 0,
        "inject_fail": inject_fail,
        "intent_total": int(result.get("intent_total") or 0),
        "approved_total": int(result.get("approved_total") or 0),
        "blocked_total": int(result.get("blocked_total") or 0),
        "invalid_total": int(result.get("invalid_total") or 0),
        "blocked_reason_counts": reason_counts,
        "failure_total": len(failures),
        "failures": failures,
    }
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} intent_total={out['intent_total']} approved_total={out['approved_total']} "
            f"blocked_total={out['blocked_total']} invalid_total={out['invalid_total']} failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)
    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
