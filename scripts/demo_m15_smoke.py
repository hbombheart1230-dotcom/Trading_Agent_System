# scripts/demo_m15_smoke.py
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

from libs.core.settings import Settings
from libs.skills.runner import CompositeSkillRunner
from libs.supervisor.two_phase import TwoPhaseSupervisor
from libs.supervisor.intent_store import IntentStore
from libs.agent.executor.executor_agent import ExecutorAgent


def _ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def _write_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    _ensure_parent(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _clear_file(p: Path) -> None:
    if p.exists():
        p.unlink(missing_ok=True)


def _env_bool(name: str, default: str = "false") -> bool:
    return (os.getenv(name, default) or default).strip().lower() == "true"


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _resolve_approval_mode() -> str:
    """
    Priority:
      1) APPROVAL_MODE if set and non-empty
      2) AUTO_APPROVE legacy fallback if APPROVAL_MODE missing/empty
      3) default manual
    """
    raw_approval = os.getenv("APPROVAL_MODE")
    approval_mode: Optional[str] = None

    if raw_approval is not None:
        raw_approval = raw_approval.strip()
        if raw_approval:
            approval_mode = raw_approval.lower()

    if not approval_mode:
        raw_legacy = os.getenv("AUTO_APPROVE")
        if raw_legacy is not None:
            raw_legacy = raw_legacy.strip().lower()
            if raw_legacy == "true":
                approval_mode = "auto"
            elif raw_legacy == "false":
                approval_mode = "manual"

    if not approval_mode:
        approval_mode = "manual"

    return approval_mode


def _try_agent_approve(agent: ExecutorAgent, intent_id: str) -> Dict[str, Any]:
    """
    Best-effort approval call. Different repos may expose different method names.
    We try a few common ones; if none exist, return a "skipped" payload.
    """
    # Candidate method names (keyword-only signatures are common in this repo)
    candidates = [
        "approve",
        "approve_intent",
        "accept",
        "accept_intent",
        "confirm",
        "confirm_intent",
    ]

    for name in candidates:
        fn = getattr(agent, name, None)
        if callable(fn):
            try:
                # try keyword style first
                return {"ok": True, "method": name, "result": fn(intent_id=intent_id)}
            except TypeError:
                # fallback positional if needed
                return {"ok": True, "method": name, "result": fn(intent_id)}
            except Exception as e:
                return {"ok": False, "method": name, "error": repr(e)}

    return {
        "ok": False,
        "skipped": True,
        "reason": "No approve/accept method found on ExecutorAgent",
        "intent_id": intent_id,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clear", action="store_true", help="Clear demo jsonl logs before running")
    args = ap.parse_args()

    # Lock approval mode BEFORE loading .env (prevents .env from overriding legacy test scenarios)
    approval_mode = _resolve_approval_mode()
    os.environ["APPROVAL_MODE"] = approval_mode

    cfg = Settings.from_env()

    kiwoom_mode = (os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower()
    execution_enabled = _env_bool("EXECUTION_ENABLED", "false")

    demo_symbol = (os.getenv("DEMO_SYMBOL", "005930") or "005930").strip()
    demo_qty = _env_int("DEMO_QTY", 1)

    demo_price = _env_int("DEMO_PRICE", 0)
    if demo_price > 0:
        order_type = "limit"
        price = demo_price
    else:
        order_type = "market"
        price = None

    demo_do_approve = _env_bool("DEMO_DO_APPROVE", "false")

    data_dir = ROOT / "data"
    intents_path = data_dir / "m15_demo_intents.jsonl"
    events_path = data_dir / "m15_demo_events.jsonl"

    if args.clear:
        _clear_file(intents_path)
        _clear_file(events_path)

    print("=== M15 Smoke Demo ===")
    print(f"KIWOOM_MODE={kiwoom_mode} EXECUTION_ENABLED={execution_enabled} APPROVAL_MODE={approval_mode}")
    print(f"AUTO_APPROVE={os.getenv('AUTO_APPROVE')}")
    print(f"DEMO_SYMBOL={demo_symbol} DEMO_QTY={demo_qty} DEMO_PRICE={demo_price}")
    print(f"DEMO_DO_APPROVE={demo_do_approve}")  # <-- S11 expectation hook
    print(f"intents: {intents_path}")
    print(f"events : {events_path}")

    runner = CompositeSkillRunner(settings=cfg, event_log_path=str(events_path))
    supervisor = TwoPhaseSupervisor(cfg)
    store = IntentStore(str(intents_path))

    agent = ExecutorAgent(
        runner=runner,
        supervisor=supervisor,
        intent_store=store,
        intent_store_path=str(intents_path),
    )

    # ---- intent1 (buy) ----
    res1 = agent.submit_order_intent(
        side="buy",
        symbol=demo_symbol,
        qty=demo_qty,
        order_type=order_type,
        price=price,
        rationale="m15 smoke demo/intent1",
        approval_mode=approval_mode,
        execution_enabled=execution_enabled,
    )
    print("\n[intent1/submit]", res1)
    _write_jsonl(events_path, {"tag": "intent1_submit", "result": res1})

    # repo API: all keyword-only
    print("\n[preview]", agent.preview())
    print("\n[last_intent]", agent.last_intent())
    print("\n[list_intents]", agent.list_intents(limit=50))
    print("\n[reject]", agent.reject(reason="demo reject"))

    # Optional manual approve path for matrix S11/S12
    try:
        intent_id_1 = res1["decision"]["intent"]["intent_id"]
    except Exception:
        intent_id_1 = None

    if demo_do_approve and approval_mode == "manual" and intent_id_1:
        print("\n[approve] attempting manual approval for intent1:", intent_id_1)
        appr = _try_agent_approve(agent, intent_id_1)
        print("[approve]", appr)
        _write_jsonl(events_path, {"tag": "approve", "result": appr})

    # ---- intent2 (sell) ----
    res2 = agent.submit_order_intent(
        side="sell",
        symbol=demo_symbol,
        qty=demo_qty,
        order_type=order_type,
        price=price,
        rationale="m15 smoke demo/intent2",
        approval_mode=approval_mode,
        execution_enabled=execution_enabled,
    )
    print("\n[intent2/submit]", res2)
    _write_jsonl(events_path, {"tag": "intent2_submit", "result": res2})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
