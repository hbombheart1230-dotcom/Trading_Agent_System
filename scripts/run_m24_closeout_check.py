from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.query_intent_state_store import main as query_state_main
from scripts.run_m24_guard_precedence_check import main as guard_main


def _run_guard_json(
    *,
    intent_log_path: Path,
    state_db_path: Path,
    no_clear: bool,
    skip_duplicate_case: bool,
) -> Tuple[int, Dict[str, Any]]:
    argv = [
        "--intent-log-path",
        str(intent_log_path),
        "--state-db-path",
        str(state_db_path),
        "--json",
    ]
    if no_clear:
        argv.append("--no-clear")
    if skip_duplicate_case:
        argv.append("--skip-duplicate-case")

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = guard_main(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _run_state_query_json(
    *,
    intent_log_path: Path,
    state_db_path: Path,
    stuck_executing_sec: int,
) -> Tuple[int, Dict[str, Any]]:
    argv = [
        "--intent-log-path",
        str(intent_log_path),
        "--state-db-path",
        str(state_db_path),
        "--stuck-executing-sec",
        str(max(0, int(stuck_executing_sec))),
        "--require-no-stuck",
        "--json",
        "--limit",
        "50",
    ]

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = query_state_main(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _inject_stuck_executing(db_path: Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("UPDATE intent_state SET updated_ts = ? WHERE state = ?", (1, "executing"))
        conn.commit()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="M24 closeout check (guard precedence + intent-state ops visibility)."
    )
    p.add_argument("--intent-log-path", default="data/logs/m24_closeout_intents.jsonl")
    p.add_argument("--state-db-path", default="data/state/m24_closeout_state.db")
    p.add_argument("--stuck-executing-sec", type=int, default=300)
    p.add_argument("--inject-stuck-case", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--skip-duplicate-case", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    intent_log_path = Path(args.intent_log_path)
    state_db_path = Path(args.state_db_path)
    intent_log_path.parent.mkdir(parents=True, exist_ok=True)
    state_db_path.parent.mkdir(parents=True, exist_ok=True)

    guard_rc, guard_obj = _run_guard_json(
        intent_log_path=intent_log_path,
        state_db_path=state_db_path,
        no_clear=bool(args.no_clear),
        skip_duplicate_case=bool(args.skip_duplicate_case),
    )

    if bool(args.inject_stuck_case):
        _inject_stuck_executing(state_db_path)

    query_rc, query_obj = _run_state_query_json(
        intent_log_path=intent_log_path,
        state_db_path=state_db_path,
        stuck_executing_sec=max(0, int(args.stuck_executing_sec)),
    )

    summary = query_obj.get("summary") if isinstance(query_obj.get("summary"), dict) else {}
    transition_total = (
        summary.get("journal_transition_total")
        if isinstance(summary.get("journal_transition_total"), dict)
        else {}
    )

    total = int(summary.get("total") or 0)
    stuck_total = int(summary.get("stuck_executing_total") or 0)
    approved_to_executing = int(transition_total.get("approved->executing") or 0)
    executing_to_executed = int(transition_total.get("executing->executed") or 0)

    ok = True
    failures: List[str] = []
    if guard_rc != 0:
        ok = False
        failures.append("guard_precedence rc != 0")
    if guard_obj and not bool(guard_obj.get("ok")):
        ok = False
        failures.append("guard_precedence ok != true")
    if query_rc != 0:
        ok = False
        failures.append("state_query rc != 0")
    if total < 3:
        ok = False
        failures.append("state_summary.total < 3")
    if approved_to_executing < 1:
        ok = False
        failures.append("state_summary.journal_transition_total[approved->executing] < 1")
    if executing_to_executed < 1:
        ok = False
        failures.append("state_summary.journal_transition_total[executing->executed] < 1")
    if stuck_total > 0:
        ok = False
        failures.append("state_summary.stuck_executing_total > 0")

    out = {
        "ok": bool(ok),
        "intent_log_path": str(intent_log_path),
        "state_db_path": str(state_db_path),
        "guard": {
            "rc": int(guard_rc),
            "ok": bool(guard_obj.get("ok")) if isinstance(guard_obj, dict) else False,
            "checks": guard_obj.get("checks") if isinstance(guard_obj, dict) else {},
        },
        "query": {
            "rc": int(query_rc),
            "ok": bool(query_obj.get("ok")) if isinstance(query_obj, dict) else False,
        },
        "state_summary": {
            "total": int(total),
            "stuck_executing_total": int(stuck_total),
            "journal_transition_total": transition_total,
        },
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} guard_rc={guard_rc} query_rc={query_rc} "
            f"total={total} stuck_executing_total={stuck_total} "
            f"approved_to_executing={approved_to_executing} executing_to_executed={executing_to_executed}"
        )
        if failures:
            for msg in failures:
                print(msg)

    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
