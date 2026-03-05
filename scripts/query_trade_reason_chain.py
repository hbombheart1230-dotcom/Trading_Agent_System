from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _broker_code_success(value: Any) -> Optional[bool]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(float(s)) == 0
    except Exception:
        pass
    t = s.lower()
    if t in ("ok", "success", "accepted"):
        return True
    if t in ("error", "failed", "rejected"):
        return False
    return False


def _build_rows(
    events: List[Dict[str, Any]],
    *,
    run_id_filter: str = "",
    action_filter: str = "",
    only_broker_success: bool = False,
) -> List[Dict[str, Any]]:
    by_run: Dict[str, Dict[str, Any]] = {}
    out: List[Dict[str, Any]] = []

    for rec in events:
        run_id = str(rec.get("run_id") or "").strip()
        if not run_id:
            continue
        if run_id not in by_run:
            by_run[run_id] = {}
        ctx = by_run[run_id]

        stage = str(rec.get("stage") or "").strip()
        event = str(rec.get("event") or "").strip()
        payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}

        if stage == "strategist_llm" and event == "result":
            ctx["llm"] = payload
            continue

        if stage == "decision" and event == "trace":
            ctx["decision"] = payload
            continue

        if stage == "execute_from_packet" and event == "verdict":
            ctx["verdict"] = payload
            continue

        if stage == "execute_from_packet" and event == "execution":
            order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
            ex_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
            action = str(order.get("action") or "").strip().upper()
            if action not in ("BUY", "SELL"):
                continue

            if run_id_filter and run_id != run_id_filter:
                continue
            if action_filter and action != action_filter:
                continue

            broker_ok = _broker_code_success(ex_payload.get("broker_code"))
            if only_broker_success and broker_ok is not True:
                continue

            llm = ctx.get("llm") if isinstance(ctx.get("llm"), dict) else {}
            decision = ctx.get("decision") if isinstance(ctx.get("decision"), dict) else {}
            decision_trace = decision.get("trace") if isinstance(decision.get("trace"), dict) else {}
            decision_packet = decision.get("decision_packet") if isinstance(decision.get("decision_packet"), dict) else {}
            decision_intent = decision_packet.get("intent") if isinstance(decision_packet.get("intent"), dict) else {}
            verdict = ctx.get("verdict") if isinstance(ctx.get("verdict"), dict) else {}

            row = {
                "ts": str(rec.get("ts") or ""),
                "run_id": run_id,
                "action": action,
                "symbol": str(order.get("symbol") or ""),
                "qty": order.get("qty"),
                "price": order.get("price"),
                "order_type": order.get("order_type"),
                "execution_reason": str(payload.get("reason") or ""),
                "allowed": verdict.get("allowed"),
                "verdict_reason": str(verdict.get("reason") or ""),
                "broker_code": str(ex_payload.get("broker_code") or ""),
                "broker_ok": broker_ok,
                "broker_message": str(ex_payload.get("broker_message") or ""),
                "order_id": str(ex_payload.get("order_id") or ""),
                "decision_strategy": str(decision_trace.get("strategy") or ""),
                "decision_rationale": str(decision_trace.get("rationale") or ""),
                "decision_reason": str(decision_intent.get("reason") or ""),
                "llm_provider": str(llm.get("provider") or ""),
                "llm_model": str(llm.get("model") or ""),
                "llm_ok": llm.get("ok"),
                "llm_intent_action": str(llm.get("intent_action") or ""),
                "llm_intent_reason": str(llm.get("intent_reason") or ""),
                "llm_latency_ms": llm.get("latency_ms"),
            }
            out.append(row)

    return out


def _print_human(path: Path, rows: List[Dict[str, Any]]) -> None:
    print("=== Trade Reason Chain ===")
    print(f"path={path}")
    print(f"shown={len(rows)}")
    for r in rows:
        print(
            f"{r.get('ts')} run_id={r.get('run_id')} "
            f"action={r.get('action')} symbol={r.get('symbol')} qty={r.get('qty')} "
            f"order_type={r.get('order_type')} broker_code={r.get('broker_code')} "
            f"order_id={r.get('order_id')} strategy={r.get('decision_strategy')} "
            f"decision_rationale={r.get('decision_rationale')} "
            f"decision_reason={r.get('decision_reason')} "
            f"llm_model={r.get('llm_model')} llm_reason={r.get('llm_intent_reason')}"
        )


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Show run_id-level trade reasons (LLM -> decision -> execution) from EVENT_LOG_PATH JSONL."
    )
    p.add_argument("--path", default=os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl"))
    p.add_argument("--run-id", default="", help="Filter by exact run_id.")
    p.add_argument("--action", default="", help="Filter by action BUY|SELL.")
    p.add_argument("--only-broker-success", action="store_true", help="Only include rows with broker_code==0.")
    p.add_argument("--limit", type=int, default=20, help="Show last N rows.")
    p.add_argument("--json", action="store_true", help="Print JSON array.")
    args = p.parse_args(argv)

    path = Path(str(args.path).strip())
    if not path.exists():
        print(f"ERROR: event log path does not exist: {path}", file=sys.stderr)
        return 2

    action_filter = str(args.action or "").strip().upper()
    if action_filter and action_filter not in ("BUY", "SELL"):
        print("ERROR: --action must be BUY or SELL", file=sys.stderr)
        return 3

    rows = _build_rows(
        _load_jsonl(path),
        run_id_filter=str(args.run_id or "").strip(),
        action_filter=action_filter,
        only_broker_success=bool(args.only_broker_success),
    )
    limit = max(1, int(args.limit))
    shown = rows[-limit:]

    if args.json:
        print(json.dumps(shown, ensure_ascii=False))
    else:
        _print_human(path, shown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

