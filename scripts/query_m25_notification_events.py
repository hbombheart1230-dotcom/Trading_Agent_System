from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file


def _env_str(name: str, default: str) -> str:
    raw = str(os.getenv(name, "") or "").strip()
    return raw if raw else str(default)


def _to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)
    s = str(ts).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        pass
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _utc_day(ts: Any) -> str:
    epoch = _to_epoch(ts)
    if epoch is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def _iter_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
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


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Query M25 notification event log summary.")
    p.add_argument(
        "--event-log-path",
        default=_env_str("M25_NOTIFY_EVENT_LOG_PATH", "data/logs/m25_notify_events.jsonl"),
    )
    p.add_argument("--day", default=None)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    load_env_file(".env")
    args = _build_parser().parse_args(argv)

    event_log_path = Path(str(args.event_log_path))
    day_filter = str(args.day or "").strip()

    rows = _iter_rows(event_log_path)
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        if str(row.get("stage") or "") != "ops_batch_notify":
            continue
        if str(row.get("event") or "") != "result":
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        day = str(payload.get("day") or _utc_day(row.get("ts")))
        if day_filter and day != day_filter:
            continue
        filtered.append(row)

    provider_total: Counter[str] = Counter()
    reason_total: Counter[str] = Counter()
    status_code_total: Counter[str] = Counter()
    ok_total = 0
    fail_total = 0
    sent_total = 0
    skipped_total = 0
    for row in filtered:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        provider_total[str(payload.get("provider") or "unknown")] += 1
        reason_total[str(payload.get("reason") or "unknown")] += 1
        status_code_total[str(int(payload.get("status_code") or 0))] += 1
        if bool(payload.get("ok")):
            ok_total += 1
        else:
            fail_total += 1
        if bool(payload.get("sent")):
            sent_total += 1
        if bool(payload.get("skipped")):
            skipped_total += 1

    out = {
        "event_log_path": str(event_log_path),
        "day": day_filter or "",
        "total": int(len(filtered)),
        "ok_total": int(ok_total),
        "fail_total": int(fail_total),
        "sent_total": int(sent_total),
        "skipped_total": int(skipped_total),
        "provider_total": dict(provider_total),
        "reason_total": dict(reason_total),
        "status_code_total": dict(status_code_total),
    }
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"total={out['total']} ok_total={out['ok_total']} fail_total={out['fail_total']} "
            f"sent_total={out['sent_total']} skipped_total={out['skipped_total']}"
        )
        print(f"provider_total={out['provider_total']}")
        print(f"reason_total={out['reason_total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
