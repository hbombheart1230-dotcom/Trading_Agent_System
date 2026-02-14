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
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                rec = json.loads(s)
            except Exception:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


def _filtered_events(
    rows: List[Dict[str, Any]],
    *,
    run_id: str = "",
    only_failures: bool = False,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rec in rows:
        if rec.get("stage") != "strategist_llm" or rec.get("event") != "result":
            continue
        if run_id and str(rec.get("run_id") or "") != run_id:
            continue
        p = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        if only_failures and bool(p.get("ok")):
            continue
        out.append(rec)
    return out


def _print_human(path: Path, rows: List[Dict[str, Any]]) -> None:
    print("=== Strategist LLM Events ===")
    print(f"path={path}")
    print(f"shown={len(rows)}")
    for rec in rows:
        p = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        ts = str(rec.get("ts") or "")
        run_id = str(rec.get("run_id") or "")
        ok = p.get("ok")
        action = str(p.get("intent_action") or "")
        reason = str(p.get("intent_reason") or "")
        latency = p.get("latency_ms")
        attempts = p.get("attempts")
        err = str(p.get("error_type") or "")
        print(
            f"{ts} run_id={run_id} ok={ok} action={action} reason={reason} "
            f"latency_ms={latency} attempts={attempts} error_type={err}"
        )


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Query strategist_llm result events from EVENT_LOG_PATH JSONL.")
    p.add_argument("--path", default=os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl"))
    p.add_argument("--run-id", default="", help="Filter by exact run_id.")
    p.add_argument("--limit", type=int, default=20, help="Show last N matched rows.")
    p.add_argument("--only-failures", action="store_true", help="Only include rows where payload.ok is false.")
    p.add_argument("--json", action="store_true", help="Print JSON array instead of human-readable lines.")
    args = p.parse_args(argv)

    path = Path(str(args.path).strip())
    if not path.exists():
        print(f"ERROR: event log path does not exist: {path}", file=sys.stderr)
        return 2

    rows = _load_jsonl(path)
    matched = _filtered_events(
        rows,
        run_id=str(args.run_id or "").strip(),
        only_failures=bool(args.only_failures),
    )
    limit = max(1, int(args.limit))
    shown = matched[-limit:]

    if args.json:
        print(json.dumps(shown, ensure_ascii=False))
    else:
        _print_human(path, shown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
