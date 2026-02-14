from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graphs.nodes.decide_trade import decide_trade


def _build_state(symbol: str, price: int, cash: int, open_positions: int) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "market_snapshot": {"symbol": symbol, "price": price},
        "portfolio_snapshot": {"cash": cash, "open_positions": open_positions},
        # Smoke only: no execution path in this script.
        "exec_context": {"mode": "mock", "smoke": "m20_llm"},
    }


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="M20 LLM smoke: strategist->decide_trade only (no execution).")
    p.add_argument("--symbol", default=os.getenv("SMOKE_SYMBOL", "005930"))
    p.add_argument("--price", type=int, default=int(os.getenv("SMOKE_PRICE", "70000")))
    p.add_argument("--cash", type=int, default=int(os.getenv("SMOKE_CASH", "2000000")))
    p.add_argument("--open-positions", type=int, default=int(os.getenv("SMOKE_OPEN_POSITIONS", "0")))
    p.add_argument("--provider", default="", help="Override AI_STRATEGIST_PROVIDER (e.g. openai|rule)")
    p.add_argument("--require-openai", action="store_true", help="Fail if strategist is not OpenAIStrategist.")
    args = p.parse_args(argv)

    if args.provider:
        os.environ["AI_STRATEGIST_PROVIDER"] = str(args.provider).strip()

    state = _build_state(
        symbol=str(args.symbol).strip(),
        price=int(args.price),
        cash=int(args.cash),
        open_positions=int(args.open_positions),
    )
    out = decide_trade(state)

    strategy = str((out.get("decision_trace") or {}).get("strategy") or "")
    intent = ((out.get("decision_packet") or {}).get("intent") or {})

    print("=== M20 LLM Smoke ===")
    print(f"provider={os.getenv('AI_STRATEGIST_PROVIDER', 'rule')}")
    print(f"strategy={strategy}")
    print("intent=", json.dumps(intent, ensure_ascii=False))
    print("trace_rationale=", str(((out.get("decision_trace") or {}).get("rationale") or "")))

    if args.require_openai and strategy != "OpenAIStrategist":
        print("ERROR: OpenAIStrategist was not selected. Check AI_STRATEGIST_* env.", file=sys.stderr)
        return 2

    # Safety guarantee: this script never executes orders.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
