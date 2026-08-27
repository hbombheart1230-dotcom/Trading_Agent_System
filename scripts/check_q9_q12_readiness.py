from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.runtime.entrypoint_common import to_int
from libs.runtime.live_loop_lock import pid_exists
from libs.runtime.live_loop_process_query import query_live_loop_processes, read_lock_owner_pid


KST = ZoneInfo("Asia/Seoul")
LOOP_PATTERNS = {
    "q10_samsung_hynix": "run_baseline_samsung_hynix.py",
    "q11_opening_opportunity": "run_opportunity_engine_shadow.py",
    "q12_btc_woori": "run_baseline_btc_woori_tech.py",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(KST)


def _powershell_processes() -> list[dict[str, Any]]:
    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -match 'run_baseline_samsung_hynix|run_opportunity_engine_shadow|run_baseline_btc_woori_tech' } | "
        "Select-Object Name,ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Depth 4"
    )
    try:
        cp = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []
    if cp.returncode != 0 or not (cp.stdout or "").strip():
        return []
    try:
        payload = json.loads(cp.stdout)
    except Exception:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    return [row for row in payload if isinstance(row, dict)]


def _process_status() -> dict[str, Any]:
    rows = _powershell_processes()
    out: dict[str, Any] = {}
    for name, pattern in LOOP_PATTERNS.items():
        matches = [
            row
            for row in rows
            if pattern in str(row.get("CommandLine") or "")
            and "powershell" not in str(row.get("Name") or "").lower()
        ]
        out[name] = {
            "running": bool(matches),
            "process_count": len(matches),
            "pids": [to_int(row.get("ProcessId"), 0) for row in matches],
        }
    return out


def _live_status(lock_path: Path) -> dict[str, Any]:
    payload = _read_json(lock_path)
    lock_pid = read_lock_owner_pid(lock_path)
    processes = query_live_loop_processes(ROOT, lock_path)
    heartbeat = _parse_dt(payload.get("heartbeat_ts"))
    now = datetime.now(KST)
    age_sec = int((now - heartbeat).total_seconds()) if heartbeat else None
    return {
        "lock_path": str(lock_path),
        "lock_exists": lock_path.exists(),
        "lock_pid": lock_pid,
        "lock_pid_alive": bool(lock_pid and pid_exists(lock_pid)),
        "process_count": len(processes),
        "pids": [to_int(row.get("pid"), 0) for row in processes],
        "heartbeat_ts": payload.get("heartbeat_ts") or "",
        "heartbeat_age_sec": age_sec,
        "running": bool(lock_pid and pid_exists(lock_pid) and processes),
    }


def _artifact(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "schema_version": payload.get("schema_version") or "",
    }


def _q9_checks(reports_root: Path, day: str) -> dict[str, Any]:
    q9_path = reports_root / "operator_summary" / "daily" / day / "q9_decision_windows.json"
    validity_path = reports_root / "evaluation" / "daily" / day / "q9_day_validity.json"
    q9 = _read_json(q9_path)
    validity = _read_json(validity_path)
    windows = [row for row in q9.get("windows") or [] if isinstance(row, dict)]
    times = [parsed for parsed in (_parse_dt(row.get("generated_at")) for row in windows) if parsed is not None]
    first = min(times) if times else None
    last = max(times) if times else None
    return {
        "artifact": _artifact(q9_path),
        "validity_artifact": _artifact(validity_path),
        "window_count": len(windows),
        "first_window_kst": first.isoformat() if first else "",
        "last_window_kst": last.isoformat() if last else "",
        "day_validity_status": validity.get("status") or "",
        "counts_as_formal_day": bool(validity.get("counts_as_formal_day")),
        "validity_blockers": validity.get("blockers") or [],
        "validity_warnings": validity.get("warnings") or [],
    }


def _baseline_artifacts(reports_root: Path, day: str) -> dict[str, Any]:
    return {
        "q10": {
            "decisions": _artifact(reports_root / "evaluation" / "baseline_samsung_hynix" / day / "baseline_samsung_hynix_decisions.json"),
            "forward": _artifact(reports_root / "evaluation" / "baseline_samsung_hynix" / day / "baseline_samsung_hynix_forward_returns.json"),
            "comparison": _artifact(reports_root / "evaluation" / "baseline_samsung_hynix" / day / "q9_vs_samsung_hynix_daily_comparison.json"),
        },
        "q11": {
            "signals": _artifact(reports_root / "evaluation" / "opportunity_engine_shadow" / day / "opportunity_engine_signals.json"),
            "virtual_trades": _artifact(reports_root / "evaluation" / "opportunity_engine_shadow" / day / "opportunity_engine_virtual_trades.json"),
            "report": _artifact(reports_root / "evaluation" / "opportunity_engine_shadow" / day / "opportunity_engine_daily_report.json"),
        },
        "q12": {
            "decisions": _artifact(reports_root / "evaluation" / "baseline_btc_woori_tech" / day / "baseline_btc_woori_decisions.json"),
            "forward": _artifact(reports_root / "evaluation" / "baseline_btc_woori_tech" / day / "baseline_btc_woori_forward_returns.json"),
            "comparison": _artifact(reports_root / "evaluation" / "baseline_btc_woori_tech" / day / "baseline_btc_woori_comparison.json"),
            "hypothesis_validation": _artifact(reports_root / "evaluation" / "baseline_btc_woori_tech" / day / "q12_btc_woori_hypothesis_validation.json"),
            "hypothesis_cumulative": _artifact(reports_root / "evaluation" / "baseline_btc_woori_tech" / "hypothesis_validation" / "q12_btc_woori_hypothesis_cumulative.json"),
        },
    }


def _evaluate(
    *,
    phase: str,
    day: str,
    live: dict[str, Any],
    processes: dict[str, Any],
    q9: dict[str, Any],
    artifacts: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if phase in {"preopen", "intraday"}:
        if not live.get("running"):
            blockers.append({"code": "live_session_not_running"})
        elif to_int(live.get("heartbeat_age_sec"), 999999) > 180:
            blockers.append({"code": "live_heartbeat_stale", "age_sec": live.get("heartbeat_age_sec")})
        for name, row in processes.items():
            if not row.get("running"):
                blockers.append({"code": f"{name}_loop_not_running"})
            if to_int(row.get("process_count"), 0) > 2:
                warnings.append({"code": f"{name}_duplicate_processes", "pids": row.get("pids")})
    if phase == "intraday":
        now = datetime.now(KST)
        if (now.hour, now.minute) >= (9, 10):
            first = _parse_dt(q9.get("first_window_kst"))
            if not first:
                blockers.append({"code": "q9_first_window_missing_after_0910"})
            elif (first.hour, first.minute) > (9, 5):
                blockers.append({"code": "q9_first_window_late", "first_window_kst": first.isoformat()})
    if phase == "closeout":
        for group, rows in artifacts.items():
            for key, record in rows.items():
                if not record.get("exists"):
                    blockers.append({"code": f"{group}_{key}_missing", "path": record.get("path")})
        if q9.get("day_validity_status") == "INVALID":
            blockers.append({"code": "q9_day_invalid", "blockers": q9.get("validity_blockers")})
        elif q9.get("day_validity_status") not in {"VALID", ""}:
            warnings.append({"code": "q9_day_not_final_valid", "status": q9.get("day_validity_status")})
    return blockers, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Q9/Q10/Q11/Q12 operational readiness without changing behavior.")
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--phase", choices=["preopen", "intraday", "closeout"], default="preopen")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--lock-path", default="data/state/m13_live_loop.lock")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    reports_root = Path(args.reports_root)
    if not reports_root.is_absolute():
        reports_root = ROOT / reports_root
    lock_path = Path(args.lock_path)
    if not lock_path.is_absolute():
        lock_path = ROOT / lock_path

    live = _live_status(lock_path)
    processes = _process_status()
    q9 = _q9_checks(reports_root, args.day)
    artifacts = _baseline_artifacts(reports_root, args.day)
    blockers, warnings = _evaluate(
        phase=args.phase,
        day=args.day,
        live=live,
        processes=processes,
        q9=q9,
        artifacts=artifacts,
    )
    payload = {
        "schema_version": "q9_q12_readiness_check.v1",
        "behavior_effect": "observability_only",
        "day": args.day,
        "phase": args.phase,
        "status": "BLOCKED" if blockers else "PASS_WITH_WARNINGS" if warnings else "PASS",
        "blockers": blockers,
        "warnings": warnings,
        "live": live,
        "processes": processes,
        "q9": q9,
        "artifacts": artifacts,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"status={payload['status']}")
        for row in blockers:
            print(f"BLOCKER {row}")
        for row in warnings:
            print(f"WARNING {row}")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
