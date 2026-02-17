from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file
from libs.reporting.alert_notifier import notify_batch_result
from scripts.run_m25_closeout_check import main as m25_closeout_main


def _env_str(name: str, default: str) -> str:
    raw = str(os.getenv(name, "") or "").strip()
    return raw if raw else str(default)


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return int(default)
    try:
        return int(float(raw))
    except Exception:
        return int(default)


def _env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "y", "on")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M25 ops batch hook (closeout wrapper + lock + latest status).")
    p.add_argument(
        "--event-log-path",
        default=_env_str("M25_BATCH_EVENT_LOG_PATH", "data/logs/m25_ops_batch_events.jsonl"),
    )
    p.add_argument(
        "--report-dir",
        default=_env_str("M25_BATCH_REPORT_DIR", "reports/m25_ops_batch"),
    )
    p.add_argument("--day", default=None)
    p.add_argument(
        "--fail-on",
        choices=["none", "warning", "critical"],
        default=_env_str("ALERT_POLICY_FAIL_ON", "critical"),
    )
    p.add_argument(
        "--lock-path",
        default=_env_str("M25_BATCH_LOCK_PATH", "data/state/m25_ops_batch.lock"),
    )
    p.add_argument(
        "--lock-stale-sec",
        type=int,
        default=_env_int("M25_BATCH_LOCK_STALE_SEC", 1800),
    )
    p.add_argument(
        "--status-json-path",
        default=_env_str("M25_BATCH_STATUS_JSON_PATH", "reports/m25_ops_batch/status_latest.json"),
    )
    p.add_argument(
        "--notify-event-log-path",
        default=_env_str("M25_NOTIFY_EVENT_LOG_PATH", "data/logs/m25_notify_events.jsonl"),
    )
    p.add_argument(
        "--notify-provider",
        choices=["none", "webhook", "slack_webhook"],
        default=_env_str("M25_NOTIFY_PROVIDER", "none"),
    )
    p.add_argument(
        "--notify-on",
        choices=["always", "failure", "success"],
        default=_env_str("M25_NOTIFY_ON", "failure"),
    )
    p.add_argument(
        "--notify-webhook-url",
        default=_env_str("M25_NOTIFY_WEBHOOK_URL", ""),
    )
    p.add_argument(
        "--notify-timeout-sec",
        type=int,
        default=_env_int("M25_NOTIFY_TIMEOUT_SEC", 5),
    )
    p.add_argument(
        "--notify-state-path",
        default=_env_str("M25_NOTIFY_STATE_PATH", "data/state/m25_notify_state.json"),
    )
    p.add_argument(
        "--notify-dedup-window-sec",
        type=int,
        default=_env_int("M25_NOTIFY_DEDUP_WINDOW_SEC", 600),
    )
    p.add_argument(
        "--notify-rate-limit-window-sec",
        type=int,
        default=_env_int("M25_NOTIFY_RATE_LIMIT_WINDOW_SEC", 600),
    )
    p.add_argument(
        "--notify-max-per-window",
        type=int,
        default=_env_int("M25_NOTIFY_MAX_PER_WINDOW", 3),
    )
    p.add_argument(
        "--notify-retry-max",
        type=int,
        default=_env_int("M25_NOTIFY_RETRY_MAX", 1),
    )
    p.add_argument(
        "--notify-retry-backoff-sec",
        type=float,
        default=_env_float("M25_NOTIFY_RETRY_BACKOFF_SEC", 0.5),
    )
    p.add_argument(
        "--notify-dry-run",
        action="store_true",
        default=_env_bool("M25_NOTIFY_DRY_RUN", False),
    )
    p.add_argument(
        "--fail-on-notify-error",
        action="store_true",
        default=_env_bool("M25_NOTIFY_FAIL_ON_ERROR", False),
    )
    p.add_argument("--inject-critical-case", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_day_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _acquire_lock(lock_path: Path, *, lock_stale_sec: int) -> Tuple[bool, str]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    now = int(time.time())

    if lock_path.exists():
        try:
            obj = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            obj = {}
        started_epoch = 0
        try:
            started_epoch = int(obj.get("started_epoch") or 0)
        except Exception:
            started_epoch = 0
        age = max(0, now - started_epoch) if started_epoch > 0 else (lock_stale_sec + 1)
        if age <= max(1, int(lock_stale_sec)):
            return False, "lock_active"
        # stale lock: remove and continue
        try:
            lock_path.unlink()
        except Exception:
            return False, "lock_stale_unlink_failed"

    payload = {
        "pid": int(os.getpid()),
        "started_epoch": now,
        "started_ts": _utc_now_iso(),
    }
    try:
        with open(lock_path, "x", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False))
        return True, ""
    except FileExistsError:
        return False, "lock_active"
    except Exception:
        return False, "lock_create_failed"


def _release_lock(lock_path: Path) -> None:
    try:
        if lock_path.exists():
            lock_path.unlink()
    except Exception:
        pass


def _run_closeout_json(
    *,
    event_log_path: Path,
    report_dir: Path,
    day: str,
    fail_on: str,
    inject_critical_case: bool,
) -> Tuple[int, Dict[str, Any]]:
    argv: List[str] = [
        "--event-log-path",
        str(event_log_path),
        "--report-dir",
        str(report_dir),
        "--day",
        str(day),
        "--fail-on",
        str(fail_on),
        "--json",
    ]
    if inject_critical_case:
        argv.append("--inject-critical-case")

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = m25_closeout_main(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _write_status(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    load_env_file(".env")
    args = _build_parser().parse_args(argv)

    day = str(args.day or _utc_day_now())
    event_log_path = Path(str(args.event_log_path))
    report_dir = Path(str(args.report_dir))
    lock_path = Path(str(args.lock_path))
    status_path = Path(str(args.status_json_path))
    notify_event_log_path = Path(str(args.notify_event_log_path))

    acquired, lock_reason = _acquire_lock(lock_path, lock_stale_sec=max(1, int(args.lock_stale_sec)))
    if not acquired:
        out_busy = {
            "ok": False,
            "rc": 4,
            "reason": lock_reason,
            "day": day,
            "lock_path": str(lock_path),
            "status_json_path": str(status_path),
        }
        _write_status(status_path, out_busy)
        if bool(args.json):
            print(json.dumps(out_busy, ensure_ascii=False))
        else:
            print(f"ok={out_busy['ok']} rc=4 reason={lock_reason}")
        return 4

    started_ts = _utc_now_iso()
    started_epoch = int(time.time())
    try:
        rc, closeout = _run_closeout_json(
            event_log_path=event_log_path,
            report_dir=report_dir,
            day=day,
            fail_on=str(args.fail_on),
            inject_critical_case=bool(args.inject_critical_case),
        )
    finally:
        _release_lock(lock_path)

    finished_epoch = int(time.time())
    finished_ts = _utc_now_iso()
    duration_sec = max(0, finished_epoch - started_epoch)

    ok = int(rc) == 0
    out = {
        "ok": bool(ok),
        "rc": int(rc),
        "day": day,
        "started_ts": started_ts,
        "finished_ts": finished_ts,
        "duration_sec": int(duration_sec),
        "lock_path": str(lock_path),
        "status_json_path": str(status_path),
        "closeout": closeout,
        "notify_event_log_path": str(notify_event_log_path),
    }

    notify = notify_batch_result(
        batch_result=out,
        provider=str(args.notify_provider),
        webhook_url=str(args.notify_webhook_url),
        timeout_sec=max(1, int(args.notify_timeout_sec)),
        state_path=str(args.notify_state_path),
        dedup_window_sec=max(0, int(args.notify_dedup_window_sec)),
        rate_limit_window_sec=max(0, int(args.notify_rate_limit_window_sec)),
        max_per_window=max(0, int(args.notify_max_per_window)),
        retry_max=max(0, int(args.notify_retry_max)),
        retry_backoff_sec=max(0.0, float(args.notify_retry_backoff_sec)),
        dry_run=bool(args.notify_dry_run),
        notify_on=str(args.notify_on),
    )
    out["notify"] = notify

    final_rc = int(rc)
    if bool(args.fail_on_notify_error) and (not bool(notify.get("skipped"))) and (not bool(notify.get("ok"))):
        if final_rc == 0:
            final_rc = 5
            out["ok"] = False
    out["rc"] = int(final_rc)

    notify_event = {
        "ts": finished_ts,
        "run_id": f"m25-ops-batch-{day}-{started_epoch}",
        "stage": "ops_batch_notify",
        "event": "result",
        "payload": {
            "day": day,
            "batch_rc": int(final_rc),
            "closeout_rc": int(rc),
            "provider": str(args.notify_provider),
            "notify_on": str(args.notify_on),
            "ok": bool(notify.get("ok")),
            "sent": bool(notify.get("sent")),
            "skipped": bool(notify.get("skipped")),
            "reason": str(notify.get("reason") or ""),
            "status_code": int(notify.get("status_code") or 0),
            "error": str(notify.get("error") or ""),
        },
    }
    try:
        _append_jsonl(notify_event_log_path, notify_event)
        out["notify_event_logged"] = True
    except Exception as e:
        out["notify_event_logged"] = False
        out["notify_event_log_error"] = str(e)

    _write_status(status_path, out)

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} rc={out['rc']} day={day} duration_sec={duration_sec} "
            f"notify_provider={args.notify_provider} notify_ok={notify.get('ok')} "
            f"status_json_path={status_path}"
        )
    return int(final_rc)


if __name__ == "__main__":
    raise SystemExit(main())
