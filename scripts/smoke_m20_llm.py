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

from libs.core.settings import load_env_file
from graphs.nodes.decide_trade import decide_trade


def _build_state(symbol: str, price: int, cash: int, open_positions: int) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "market_snapshot": {"symbol": symbol, "price": price},
        "portfolio_snapshot": {"cash": cash, "open_positions": open_positions},
        # Smoke only: no execution path in this script.
        "exec_context": {"mode": "mock", "smoke": "m20_llm"},
    }


def _load_jsonl(path: Path) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except Exception:
        return []
    return rows


def _latest_llm_event_for_run(path: Path, run_id: str) -> Optional[Dict[str, Any]]:
    if not run_id:
        return None
    latest: Optional[Dict[str, Any]] = None
    for rec in _load_jsonl(path):
        if str(rec.get("run_id") or "") != run_id:
            continue
        if rec.get("stage") != "strategist_llm" or rec.get("event") != "result":
            continue
        latest = rec
    return latest


def main(argv: Optional[list[str]] = None) -> int:
    # Load .env before parser defaults are resolved.
    load_env_file(".env")

    p = argparse.ArgumentParser(description="M20 LLM smoke: strategist->decide_trade only (no execution).")
    p.add_argument("--symbol", default=os.getenv("SMOKE_SYMBOL", "005930"))
    p.add_argument("--price", type=int, default=int(os.getenv("SMOKE_PRICE", "70000")))
    p.add_argument("--cash", type=int, default=int(os.getenv("SMOKE_CASH", "2000000")))
    p.add_argument("--open-positions", type=int, default=int(os.getenv("SMOKE_OPEN_POSITIONS", "0")))
    p.add_argument("--provider", default="", help="Override AI_STRATEGIST_PROVIDER (e.g. openai|rule)")
    p.add_argument("--require-openai", action="store_true", help="Fail if strategist is not OpenAIStrategist.")
    p.add_argument("--event-log-path", default="", help="Override EVENT_LOG_PATH for this run.")
    p.add_argument(
        "--show-llm-event",
        action="store_true",
        help="Print latest strategist_llm event summary (ok/latency/attempts/error).",
    )
    p.add_argument(
        "--require-llm-event",
        action="store_true",
        help="Fail if strategist_llm result event is missing for this run (exit code 3).",
    )
    args = p.parse_args(argv)

    if args.provider:
        os.environ["AI_STRATEGIST_PROVIDER"] = str(args.provider).strip()
    if args.event_log_path:
        os.environ["EVENT_LOG_PATH"] = str(args.event_log_path).strip()

    state = _build_state(
        symbol=str(args.symbol).strip(),
        price=int(args.price),
        cash=int(args.cash),
        open_positions=int(args.open_positions),
    )
    out = decide_trade(state)

    strategy = str((out.get("decision_trace") or {}).get("strategy") or "")
    intent = ((out.get("decision_packet") or {}).get("intent") or {})
    run_id = str(out.get("run_id") or "")
    event_log_path = Path(os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl"))

    print("=== M20 LLM Smoke ===")
    print(f"provider={os.getenv('AI_STRATEGIST_PROVIDER', 'rule')}")
    print(f"strategy={strategy}")
    print("intent=", json.dumps(intent, ensure_ascii=False))
    print("trace_rationale=", str(((out.get("decision_trace") or {}).get("rationale") or "")))
    print(f"run_id={run_id}")
    print(f"event_log_path={event_log_path}")

    if args.show_llm_event or args.require_llm_event:
        ev = _latest_llm_event_for_run(event_log_path, run_id)
        if ev is None:
            print("llm_event=not_found")
            if args.require_llm_event:
                print("ERROR: strategist_llm result event not found for this run.", file=sys.stderr)
                return 3
        else:
            pld = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
            llm_summary = {
                "ok": pld.get("ok"),
                "provider": pld.get("provider"),
                "model": pld.get("model"),
                "latency_ms": pld.get("latency_ms"),
                "attempts": pld.get("attempts"),
                "intent_action": pld.get("intent_action"),
                "intent_reason": pld.get("intent_reason"),
                "prompt_version": pld.get("prompt_version"),
                "schema_version": pld.get("schema_version"),
                "prompt_tokens": pld.get("prompt_tokens"),
                "completion_tokens": pld.get("completion_tokens"),
                "total_tokens": pld.get("total_tokens"),
                "estimated_cost_usd": pld.get("estimated_cost_usd"),
                "error_type": pld.get("error_type"),
            }
            print("llm_event=", json.dumps(llm_summary, ensure_ascii=False))

    if args.require_openai and strategy != "OpenAIStrategist":
        print("ERROR: OpenAIStrategist was not selected. Check AI_STRATEGIST_* env.", file=sys.stderr)
        return 2

    # Safety guarantee: this script never executes orders.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
