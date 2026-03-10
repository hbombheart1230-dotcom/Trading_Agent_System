from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


KST = timezone.utc
try:
    from zoneinfo import ZoneInfo

    KST = ZoneInfo("Asia/Seoul")
except Exception:
    KST = timezone.utc


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


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


def _tail(s: str, max_chars: int = 2000) -> str:
    txt = str(s or "")
    if len(txt) <= max_chars:
        return txt
    return txt[-max_chars:]


def _latest_event_epoch(event_log_path: Path, *, max_tail_lines: int = 2000) -> Optional[int]:
    if not event_log_path.exists():
        return None
    tail: deque[str] = deque(maxlen=max(100, int(max_tail_lines)))
    with event_log_path.open("r", encoding="utf-8") as f:
        for line in f:
            tail.append(line)
    for raw in reversed(tail):
        line = str(raw or "").strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        e = _to_epoch(obj.get("ts"))
        if e is not None:
            return int(e)
    return None


def _pid_exists(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
                PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                int(pid),
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
    except Exception:
        return False
    return True


def _read_loop_pid(lock_path: Path) -> int:
    if not lock_path.exists():
        return 0
    try:
        obj = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(obj, dict):
        return 0
    return _to_int(obj.get("pid"), 0)


def _parse_stdout_json(stdout_text: str) -> Dict[str, Any]:
    body = str(stdout_text or "").strip()
    if not body:
        return {}
    try:
        obj = json.loads(body)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    for line in reversed(lines):
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {}


def _severity_rank(level: str) -> int:
    raw = str(level or "").upper()
    if raw == "RED":
        return 3
    if raw == "YELLOW":
        return 2
    return 1


def _merge_severity(cur: str, nxt: str) -> str:
    return nxt if _severity_rank(nxt) > _severity_rank(cur) else cur


def evaluate_watch_health(
    summary: Dict[str, Any],
    *,
    loop_alive: bool,
    event_lag_sec: Optional[int],
    max_event_lag_sec: int,
) -> Dict[str, Any]:
    level = "GREEN"
    reasons: List[str] = []
    actions: List[str] = []

    events = summary.get("events") if isinstance(summary.get("events"), dict) else {}
    llm = summary.get("strategist_llm") if isinstance(summary.get("strategist_llm"), dict) else {}
    execution = summary.get("execution") if isinstance(summary.get("execution"), dict) else {}

    window_total = _to_int(events.get("window_total"), 0)
    llm_total = _to_int(llm.get("total"), 0)
    llm_error_rate = _to_float(llm.get("error_rate"), 0.0)

    verdict_total = _to_int(execution.get("verdict_total"), 0)
    blocked_total = _to_int(execution.get("blocked_total"), 0)
    blocked_rate = (float(blocked_total) / float(verdict_total)) if verdict_total > 0 else 0.0
    exec_fail_total = _to_int(execution.get("executed_broker_fail_total"), 0)

    if not loop_alive:
        level = _merge_severity(level, "RED")
        reasons.append("loop_not_alive")
        actions.append("run session wrapper to restart live loop")

    if event_lag_sec is None:
        level = _merge_severity(level, "RED")
        reasons.append("event_ts_missing")
        actions.append("check event logger output path and runtime process")
    elif int(event_lag_sec) > int(max_event_lag_sec):
        level = _merge_severity(level, "RED")
        reasons.append(f"event_lag_exceeded:{int(event_lag_sec)}s>{int(max_event_lag_sec)}s")
        actions.append("inspect loop lock/process and event write permissions")

    if window_total == 0:
        level = _merge_severity(level, "YELLOW")
        reasons.append("window_empty")
        actions.append("verify market session and event stream source")

    if llm_total >= 3 and llm_error_rate >= 0.30:
        level = _merge_severity(level, "YELLOW")
        reasons.append(f"llm_error_rate_high:{llm_error_rate:.2%}")
        actions.append("check provider/model health and fallback policy")

    if verdict_total >= 5 and blocked_rate >= 0.90:
        level = _merge_severity(level, "YELLOW")
        reasons.append(f"blocked_rate_high:{blocked_rate:.2%}")
        actions.append("inspect guard block reasons and policy thresholds")

    if exec_fail_total > 0:
        level = _merge_severity(level, "RED")
        reasons.append(f"broker_execution_fail:{exec_fail_total}")
        actions.append("inspect broker response payload and halt auto session if repeated")

    return {
        "status": level,
        "reasons": reasons,
        "recommended_actions": actions,
        "metrics": {
            "window_total": int(window_total),
            "llm_total": int(llm_total),
            "llm_error_rate": float(llm_error_rate),
            "verdict_total": int(verdict_total),
            "blocked_total": int(blocked_total),
            "blocked_rate": float(blocked_rate),
            "executed_broker_fail_total": int(exec_fail_total),
        },
    }


def _build_markdown(snapshot: Dict[str, Any]) -> str:
    health = snapshot.get("health") if isinstance(snapshot.get("health"), dict) else {}
    metrics = health.get("metrics") if isinstance(health.get("metrics"), dict) else {}
    reasons = health.get("reasons") if isinstance(health.get("reasons"), list) else []
    actions = health.get("recommended_actions") if isinstance(health.get("recommended_actions"), list) else []
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    decision = summary.get("decision") if isinstance(summary.get("decision"), dict) else {}
    action_counts = decision.get("action_counts") if isinstance(decision.get("action_counts"), dict) else {}

    lines = [
        f"# Live Session Watch ({snapshot.get('ts_kst')})",
        "",
        f"- status: **{health.get('status', 'UNKNOWN')}**",
        f"- loop_alive: **{bool(snapshot.get('loop_alive'))}** (pid={int(snapshot.get('loop_pid') or 0)})",
        f"- event_lag_sec: **{snapshot.get('event_lag_sec')}**",
        f"- summary_rc: **{int(snapshot.get('summary_rc') or 0)}**",
        "",
        "## Metrics",
        "",
        f"- window_total: **{int(metrics.get('window_total') or 0)}**",
        f"- decision action_counts: `{json.dumps(action_counts, ensure_ascii=False)}`",
        f"- llm_error_rate: **{float(metrics.get('llm_error_rate') or 0.0):.2%}**",
        f"- blocked_rate: **{float(metrics.get('blocked_rate') or 0.0):.2%}**",
        f"- executed_broker_fail_total: **{int(metrics.get('executed_broker_fail_total') or 0)}**",
        "",
        "## Reasons",
        "",
    ]
    if reasons:
        for r in reasons:
            lines.append(f"- {str(r)}")
    else:
        lines.append("- none")
    lines.extend(["", "## Recommended Actions", ""])
    if actions:
        for a in actions:
            lines.append(f"- {str(a)}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- summary_report_json_path: `{snapshot.get('summary_report_json_path')}`",
            f"- summary_report_md_path: `{snapshot.get('summary_report_md_path')}`",
            f"- watch_jsonl_path: `{snapshot.get('watch_jsonl_path')}`",
        ]
    )
    return "\n".join(lines)


def _run_live_summary(
    *,
    event_log_path: Path,
    summary_report_dir: Path,
    lookback_min: int,
) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_live_session_summary.py"),
        "--event-log-path",
        str(event_log_path),
        "--report-dir",
        str(summary_report_dir),
        "--lookback-min",
        str(max(1, int(lookback_min))),
        "--json",
    ]
    out: Dict[str, Any] = {"rc": 1, "ok": False, "stdout_tail": "", "stderr_tail": "", "summary": {}}
    try:
        cp = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        out["rc"] = int(cp.returncode)
        out["ok"] = int(cp.returncode) == 0
        out["stdout_tail"] = _tail(cp.stdout or "")
        out["stderr_tail"] = _tail(cp.stderr or "")
        out["summary"] = _parse_stdout_json(cp.stdout or "")
    except Exception as ex:
        out["rc"] = 1
        out["ok"] = False
        out["stderr_tail"] = f"{type(ex).__name__}: {ex}"
    return out


def _parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="5-minute live-session watch summary for operators.")
    p.add_argument(
        "--event-log-path",
        default=os.getenv("EVENT_LOG_PATH", "data/logs/events.jsonl"),
        help="Event log path used by runtime loop.",
    )
    p.add_argument("--summary-report-dir", default="reports/live_summary")
    p.add_argument("--watch-report-dir", default="reports/live_watch")
    p.add_argument("--lock-path", default=os.getenv("M13_LIVE_LOCK_PATH", "data/state/m13_live_loop.lock"))
    p.add_argument("--lookback-min", type=int, default=_to_int(os.getenv("LIVE_SUMMARY_LOOKBACK_MIN"), 30))
    p.add_argument("--sleep-sec", type=int, default=_to_int(os.getenv("LIVE_WATCH_SLEEP_SEC"), 300))
    p.add_argument("--max-event-lag-sec", type=int, default=_to_int(os.getenv("LIVE_WATCH_MAX_EVENT_LAG_SEC"), 420))
    p.add_argument("--once", action="store_true", help="Run one check and exit.")
    p.add_argument("--max-iterations", type=int, default=0, help="0 means infinite loop.")
    p.add_argument("--json", action="store_true", help="Print full snapshot JSON per iteration.")
    p.add_argument("--fail-on-red", action="store_true", help="Return non-zero when health status is RED.")
    return p.parse_args(argv)


def _run_once(args: argparse.Namespace) -> Dict[str, Any]:
    now_epoch = int(time.time())
    ts_utc = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat()
    ts_kst = datetime.fromtimestamp(now_epoch, tz=KST).isoformat()

    event_log_path = Path(str(args.event_log_path).strip())
    summary_report_dir = Path(str(args.summary_report_dir).strip())
    watch_report_dir = Path(str(args.watch_report_dir).strip())
    lock_path = Path(str(args.lock_path).strip())
    if not event_log_path.is_absolute():
        event_log_path = ROOT / event_log_path
    if not summary_report_dir.is_absolute():
        summary_report_dir = ROOT / summary_report_dir
    if not watch_report_dir.is_absolute():
        watch_report_dir = ROOT / watch_report_dir
    if not lock_path.is_absolute():
        lock_path = ROOT / lock_path

    summary_report_dir.mkdir(parents=True, exist_ok=True)
    watch_report_dir.mkdir(parents=True, exist_ok=True)

    summary_run = _run_live_summary(
        event_log_path=event_log_path,
        summary_report_dir=summary_report_dir,
        lookback_min=max(1, int(args.lookback_min)),
    )
    summary = summary_run.get("summary") if isinstance(summary_run.get("summary"), dict) else {}

    loop_pid = _read_loop_pid(lock_path)
    loop_alive = _pid_exists(loop_pid)

    latest_event_epoch = _latest_event_epoch(event_log_path)
    event_lag_sec: Optional[int] = None
    if latest_event_epoch is not None:
        event_lag_sec = max(0, int(now_epoch - int(latest_event_epoch)))

    health = evaluate_watch_health(
        summary,
        loop_alive=bool(loop_alive),
        event_lag_sec=event_lag_sec,
        max_event_lag_sec=max(30, int(args.max_event_lag_sec)),
    )

    watch_day = datetime.fromtimestamp(now_epoch, tz=KST).strftime("%Y-%m-%d")
    watch_jsonl_path = watch_report_dir / f"live_watch_{watch_day}.jsonl"
    latest_md_path = watch_report_dir / "live_watch_latest.md"
    snapshot_json_path = watch_report_dir / f"live_watch_snapshot_{watch_day}.json"

    snapshot: Dict[str, Any] = {
        "schema_version": "live_watch.v1",
        "ts_utc": ts_utc,
        "ts_kst": ts_kst,
        "event_log_path": str(event_log_path),
        "summary_rc": int(summary_run.get("rc") or 1),
        "summary_ok": bool(summary_run.get("ok")),
        "summary_stderr_tail": str(summary_run.get("stderr_tail") or ""),
        "summary_stdout_tail": str(summary_run.get("stdout_tail") or ""),
        "summary": summary,
        "loop_pid": int(loop_pid),
        "loop_alive": bool(loop_alive),
        "event_lag_sec": event_lag_sec,
        "health": health,
        "summary_report_json_path": str(summary.get("report_json_path") or ""),
        "summary_report_md_path": str(summary.get("report_md_path") or ""),
        "watch_jsonl_path": str(watch_jsonl_path),
        "watch_latest_md_path": str(latest_md_path),
    }

    with watch_jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    snapshot_json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_md_path.write_text(_build_markdown(snapshot), encoding="utf-8")
    return snapshot


def _build_console_line(snapshot: Dict[str, Any]) -> str:
    health = snapshot.get("health") if isinstance(snapshot.get("health"), dict) else {}
    metrics = health.get("metrics") if isinstance(health.get("metrics"), dict) else {}
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    decision = summary.get("decision") if isinstance(summary.get("decision"), dict) else {}
    actions = decision.get("action_counts") if isinstance(decision.get("action_counts"), dict) else {}
    return (
        f"[{snapshot.get('ts_kst')}] status={health.get('status')} "
        f"loop_alive={bool(snapshot.get('loop_alive'))} "
        f"lag_sec={snapshot.get('event_lag_sec')} "
        f"window={int(metrics.get('window_total') or 0)} "
        f"buy={int(actions.get('BUY') or 0)} "
        f"sell={int(actions.get('SELL') or 0)} "
        f"noop={int(actions.get('NOOP') or 0)} "
        f"llm_error_rate={float(metrics.get('llm_error_rate') or 0.0):.2%} "
        f"blocked_rate={float(metrics.get('blocked_rate') or 0.0):.2%}"
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    sleep_sec = max(10, int(args.sleep_sec))
    max_iterations = max(0, int(args.max_iterations))
    run_once = bool(args.once)
    fail_on_red = bool(args.fail_on_red)

    iteration = 0
    last_status = "GREEN"
    while True:
        iteration += 1
        snapshot = _run_once(args)
        health = snapshot.get("health") if isinstance(snapshot.get("health"), dict) else {}
        last_status = str(health.get("status") or "GREEN").upper()

        if bool(args.json):
            print(json.dumps(snapshot, ensure_ascii=False))
        else:
            print(_build_console_line(snapshot))

        if run_once:
            break
        if max_iterations > 0 and iteration >= max_iterations:
            break
        time.sleep(sleep_sec)

    if fail_on_red and last_status == "RED":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
