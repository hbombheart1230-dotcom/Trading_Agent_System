from __future__ import annotations

import json
import time
from datetime import date, datetime, time as clock_time, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from libs.market.preopen_macro_snapshot import capture_preopen_macro_snapshot


KST = ZoneInfo("Asia/Seoul")
SCHEMA_VERSION = "opening_macro_snapshot_manifest.v1"
SLOT_MINUTES = (8 * 60 + 50, 8 * 60 + 55, 8 * 60 + 58, 8 * 60 + 59, *range(9 * 60, 9 * 60 + 21))


def scheduled_slots(day: str) -> list[datetime]:
    parsed = date.fromisoformat(str(day)[:10])
    return [
        datetime.combine(parsed, clock_time(minute // 60, minute % 60), tzinfo=KST)
        for minute in SLOT_MINUTES
    ]


def _read_manifest(path: Path, day: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        value = {}
    if not isinstance(value, Mapping) or value.get("day") != day:
        value = {}
    return {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": "observation_only",
        "scope": "opening_lead_market_08_50_to_09_20",
        "day": day,
        "slots": list(value.get("slots") or []),
    }


def _write_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _snapshot_files(root: Path, day: str) -> dict[Path, int]:
    day_root = root / day
    return {
        path: path.stat().st_mtime_ns
        for path in day_root.glob("*_macro_indicators.json")
        if path.is_file()
    }


def _new_snapshot_path(before: Mapping[Path, int], after: Mapping[Path, int]) -> str:
    changed = [path for path, stamp in after.items() if before.get(path) != stamp]
    if not changed:
        return ""
    return str(max(changed, key=lambda path: after[path]))


def capture_slot(
    *,
    day: str,
    scheduled_at: datetime,
    manifest_path: Path,
    macro_root: Path = Path("data/logs/macro_indicators"),
    env_path: Path = Path(".env"),
    state_path: Path = Path("data/state.json"),
    now_fn: Callable[[], datetime] = lambda: datetime.now(KST),
    capture: Callable[..., Mapping[str, Any]] = capture_preopen_macro_snapshot,
) -> dict[str, Any]:
    manifest = _read_manifest(manifest_path, day)
    slot_id = scheduled_at.strftime("%H:%M")
    existing = next((row for row in manifest["slots"] if row.get("slot") == slot_id), None)
    if existing is not None:
        return dict(existing)

    started = now_fn().astimezone(KST)
    delay_sec = max(0, int((started - scheduled_at).total_seconds()))
    before = _snapshot_files(macro_root, day)
    try:
        result = dict(capture(env_path=env_path, state_path=state_path))
        error = ""
    except Exception as exc:
        result = {}
        error = f"{type(exc).__name__}: {exc}"
    finished = now_fn().astimezone(KST)
    after = _snapshot_files(macro_root, day)
    source_path = _new_snapshot_path(before, after)
    status = "CAPTURED" if source_path else "CAPTURE_FAILED"
    row = {
        "slot": slot_id,
        "scheduled_at_kst": scheduled_at.isoformat(timespec="seconds"),
        "started_at_kst": started.isoformat(timespec="seconds"),
        "finished_at_kst": finished.isoformat(timespec="seconds"),
        "start_delay_sec": delay_sec,
        "duration_sec": max(0, int((finished - started).total_seconds())),
        "freshness_sla_sec": 60,
        "within_sla": delay_sec <= 60,
        "status": status,
        "signal_status": result.get("status") or "unavailable",
        "signal_source": result.get("source") or "",
        "source_path": source_path,
        "error": error or ("macro_snapshot_artifact_not_created" if not source_path else ""),
    }
    manifest["slots"].append(row)
    manifest["slots"].sort(key=lambda item: str(item.get("slot") or ""))
    manifest["updated_at_kst"] = finished.isoformat(timespec="seconds")
    _write_manifest(manifest_path, manifest)
    return row


def mark_missed_slots(
    *, day: str, now: datetime, manifest_path: Path, grace_sec: int = 60
) -> list[dict[str, Any]]:
    manifest = _read_manifest(manifest_path, day)
    known = {str(row.get("slot") or "") for row in manifest["slots"]}
    added = []
    for scheduled_at in scheduled_slots(day):
        if scheduled_at.strftime("%H:%M") in known:
            continue
        delay = int((now - scheduled_at).total_seconds())
        if delay <= grace_sec:
            continue
        row = {
            "slot": scheduled_at.strftime("%H:%M"),
            "scheduled_at_kst": scheduled_at.isoformat(timespec="seconds"),
            "status": "MISSED",
            "start_delay_sec": delay,
            "within_sla": False,
            "reason": "collector_not_running_or_capture_overrun",
        }
        manifest["slots"].append(row)
        added.append(row)
    if added:
        manifest["slots"].sort(key=lambda item: str(item.get("slot") or ""))
        manifest["updated_at_kst"] = now.isoformat(timespec="seconds")
        _write_manifest(manifest_path, manifest)
    return added


def run_collector(
    *,
    day: str,
    manifest_path: Path,
    macro_root: Path = Path("data/logs/macro_indicators"),
    env_path: Path = Path(".env"),
    state_path: Path = Path("data/state.json"),
    poll_sec: float = 1.0,
    keepalive_until: clock_time = clock_time(15, 30),
) -> dict[str, Any]:
    slots = scheduled_slots(day)
    session_end = datetime.combine(date.fromisoformat(day), keepalive_until, tzinfo=KST)
    while datetime.now(KST) <= session_end:
        now = datetime.now(KST)
        mark_missed_slots(day=day, now=now, manifest_path=manifest_path)
        manifest = _read_manifest(manifest_path, day)
        known = {str(row.get("slot") or "") for row in manifest["slots"]}
        due = [
            slot for slot in slots
            if slot.strftime("%H:%M") not in known and slot <= now <= slot + timedelta(seconds=60)
        ]
        if due:
            capture_slot(
                day=day,
                scheduled_at=due[0],
                manifest_path=manifest_path,
                macro_root=macro_root,
                env_path=env_path,
                state_path=state_path,
            )
        else:
            time.sleep(max(0.1, poll_sec))
    manifest = _read_manifest(manifest_path, day)
    captured = sum(1 for row in manifest["slots"] if row.get("status") == "CAPTURED")
    return {"day": day, "captured": captured, "slot_count": len(slots), "manifest_path": str(manifest_path)}
