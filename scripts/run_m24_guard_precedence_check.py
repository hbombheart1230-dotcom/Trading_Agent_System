from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from libs.approval.service import ApprovalService
from libs.catalog.api_request_builder import PreparedRequest
from libs.core.settings import Settings
from libs.execution.executors.real_executor import RealExecutor
from libs.supervisor.intent_state_store import INTENT_STATE_APPROVED, INTENT_STATE_EXECUTING, SQLiteIntentStateStore
from libs.supervisor.intent_store import IntentStore


def _seed_intent(store: IntentStore, *, intent_id: str, symbol: str = "005930") -> None:
    store.save(
        {
            "intent_id": intent_id,
            "action": "BUY",
            "symbol": symbol,
            "qty": 1,
            "order_type": "market",
            "price": None,
            "rationale": "m24_6_guard_precedence",
        }
    )


def _mk_req(symbol: str) -> PreparedRequest:
    return PreparedRequest(
        api_id="ORDER_SUBMIT",
        method="POST",
        path="/api/dostk/ordr",
        headers={},
        query={},
        body={"stk_cd": symbol, "ord_qty": "1"},
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M24 guard precedence check (approval state + duplicate claim + preflight code)")
    p.add_argument("--intent-log-path", default="data/logs/m24_guard_precedence_intents.jsonl")
    p.add_argument("--state-db-path", default="data/state/m24_guard_precedence.db")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--skip-duplicate-case", action="store_true")
    return p


def _run_preflight_case() -> Dict[str, Any]:
    # isolate env mutation
    old = {
        "KIWOOM_MODE": os.getenv("KIWOOM_MODE"),
        "EXECUTION_ENABLED": os.getenv("EXECUTION_ENABLED"),
        "ALLOW_REAL_EXECUTION": os.getenv("ALLOW_REAL_EXECUTION"),
        "KIWOOM_APP_KEY": os.getenv("KIWOOM_APP_KEY"),
        "KIWOOM_APP_SECRET": os.getenv("KIWOOM_APP_SECRET"),
        "KIWOOM_ACCOUNT_NO": os.getenv("KIWOOM_ACCOUNT_NO"),
    }
    try:
        os.environ["KIWOOM_MODE"] = "real"
        os.environ["EXECUTION_ENABLED"] = "false"
        os.environ["ALLOW_REAL_EXECUTION"] = "false"
        os.environ.pop("KIWOOM_APP_KEY", None)
        os.environ.pop("KIWOOM_APP_SECRET", None)
        os.environ.pop("KIWOOM_ACCOUNT_NO", None)

        ex = RealExecutor(settings=Settings.from_env(env_path="__missing__.env"))
        pf = ex.preflight_check(_mk_req("005930"))
        return {"ok": bool(not pf.get("ok")), "code": str(pf.get("code") or "")}
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    intent_log_path = Path(args.intent_log_path)
    state_db_path = Path(args.state_db_path)
    intent_log_path.parent.mkdir(parents=True, exist_ok=True)
    state_db_path.parent.mkdir(parents=True, exist_ok=True)

    if (not args.no_clear) and intent_log_path.exists():
        intent_log_path.unlink()
    if (not args.no_clear) and state_db_path.exists():
        state_db_path.unlink()

    store = IntentStore(str(intent_log_path))
    state = SQLiteIntentStateStore(str(state_db_path))
    svc1 = ApprovalService(store, state_store=state)
    svc2 = ApprovalService(store, state_store=state)

    failures: List[str] = []

    # Case 1: reject blocked after approved.
    _seed_intent(store, intent_id="i-m24-6-rj")
    a1 = svc1.approve(intent_id="i-m24-6-rj", execution_enabled=False, execute_fn=lambda it: {"ok": True})
    rj = svc1.reject(intent_id="i-m24-6-rj", reason="late reject")
    reject_blocked = bool(a1.get("ok")) and bool(rj.get("ok") is False)
    if not reject_blocked:
        failures.append("reject_after_approved_not_blocked")

    # Case 2: executing state blocks additional approve execute.
    _seed_intent(store, intent_id="i-m24-6-exec")
    svc1.approve(intent_id="i-m24-6-exec", execution_enabled=False, execute_fn=lambda it: {"ok": True})
    state.transition(
        intent_id="i-m24-6-exec",
        to_state=INTENT_STATE_EXECUTING,
        expected_from_state=INTENT_STATE_APPROVED,
        reason="external executing claim",
    )
    blocked = svc1.approve(intent_id="i-m24-6-exec", execution_enabled=True, execute_fn=lambda it: {"ok": True})
    executing_blocked = bool(blocked.get("ok") is False) and ("executing" in str(blocked.get("message") or "").lower())
    if not executing_blocked:
        failures.append("executing_state_not_blocked")

    duplicate_blocked = False
    if not bool(args.skip_duplicate_case):
        # Case 3: duplicate claim across two services.
        _seed_intent(store, intent_id="i-m24-6-dup")
        svc1.approve(intent_id="i-m24-6-dup", execution_enabled=False, execute_fn=lambda it: {"ok": True})

        dup_box: Dict[str, Any] = {}

        def _exec_main(intent):  # type: ignore[no-untyped-def]
            dup = svc2.approve(intent_id="i-m24-6-dup", execution_enabled=True, execute_fn=lambda it: {"ok": True, "id": "dup"})
            dup_box["dup"] = dup
            return {"ok": True, "id": "main"}

        out = svc1.approve(intent_id="i-m24-6-dup", execution_enabled=True, execute_fn=_exec_main)
        dup = dup_box.get("dup") if isinstance(dup_box.get("dup"), dict) else {}
        duplicate_blocked = bool(out.get("ok")) and bool(dup.get("ok") is False)
    if not duplicate_blocked:
        failures.append("duplicate_claim_not_blocked")

    # Case 4: real preflight explicit denial code.
    pf = _run_preflight_case()
    preflight_ok = bool(pf.get("ok")) and str(pf.get("code") or "") == "EXECUTION_DISABLED"
    if not preflight_ok:
        failures.append("preflight_explicit_denial_code_missing")

    summary = {
        "ok": len(failures) == 0,
        "intent_log_path": str(intent_log_path),
        "state_db_path": str(state_db_path),
        "checks": {
            "reject_after_approved_blocked": bool(reject_blocked),
            "executing_state_blocked": bool(executing_blocked),
            "duplicate_claim_blocked": bool(duplicate_blocked),
            "preflight_denial_code_ok": bool(preflight_ok),
        },
        "failures": failures,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(
            f"ok={summary['ok']} reject_blocked={summary['checks']['reject_after_approved_blocked']} "
            f"executing_blocked={summary['checks']['executing_state_blocked']} "
            f"duplicate_blocked={summary['checks']['duplicate_claim_blocked']} "
            f"preflight_code_ok={summary['checks']['preflight_denial_code_ok']}"
        )
        if failures:
            for m in failures:
                print(m)

    return 0 if summary["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
