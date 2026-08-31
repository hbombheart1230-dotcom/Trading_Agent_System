from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


KST = timezone(timedelta(hours=9))
DEFAULT_ROOT = Path("data/logs/q12_btc_0855")
MAX_SOURCE_AGE_SEC = 15 * 60


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return dict(value) if isinstance(value, Mapping) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def capture_paths(day: str, *, root: Path | str = DEFAULT_ROOT) -> dict[str, Path]:
    base = Path(root) / str(day)[:10]
    return {
        "snapshot": base / "btc_0855_snapshot.json",
        "ledger": base / "capture_ledger.json",
    }


def load_capture_snapshot(
    day: str, *, root: Path | str = DEFAULT_ROOT
) -> dict[str, Any]:
    return _read(capture_paths(day, root=root)["snapshot"])


def load_captured_sources(
    day: str, *, root: Path | str = DEFAULT_ROOT
) -> dict[str, list[dict[str, Any]]]:
    payload = load_capture_snapshot(day, root=root)
    if payload.get("capture_status") != "CAPTURED":
        return {}
    sources = payload.get("sources")
    sources = sources if isinstance(sources, Mapping) else {}
    return {
        str(name): [dict(row) for row in list(rows or []) if isinstance(row, Mapping)]
        for name, rows in sources.items()
    }


def _target(day: str) -> datetime:
    return datetime.combine(date.fromisoformat(str(day)[:10]), time(8, 55), tzinfo=KST)


def _record_attempt(path: Path, result: Mapping[str, Any], *, snapshot_path: Path) -> None:
    existing = _read(path)
    attempts = [
        dict(row)
        for row in list(existing.get("attempts") or [])
        if isinstance(row, Mapping)
    ]
    attempt = {
        "attempted_at_kst": result.get("attempted_at_kst"),
        "capture_status": result.get("capture_status"),
        "reason": result.get("reason"),
        "source_count": result.get("source_count"),
        "snapshot_submitted": result.get("snapshot_submitted"),
    }
    if attempt not in attempts:
        attempts.append(attempt)
    _write(
        path,
        {
            "schema_version": "q12_btc_0855_capture_ledger.v1",
            "day": result.get("day"),
            "scheduled_target_kst": result.get("scheduled_target_kst"),
            "latest_status": result.get("capture_status"),
            "snapshot_submitted": result.get("snapshot_submitted"),
            "snapshot_path": str(snapshot_path),
            "attempt_count": len(attempts),
            "attempts": attempts,
        },
    )


def _source_points(payload: Mapping[str, Any], *, target_epoch: int) -> dict[str, list[dict[str, Any]]]:
    sources = payload.get("sources")
    sources = sources if isinstance(sources, Mapping) else {}
    output: dict[str, list[dict[str, Any]]] = {}
    for name in ("btc_krw", "btc_usd"):
        rows = [dict(row) for row in list(sources.get(name) or []) if isinstance(row, Mapping)]
        eligible = [row for row in rows if 0 < int(row.get("ts") or 0) <= target_epoch]
        if not eligible:
            continue
        latest = max(eligible, key=lambda row: int(row.get("ts") or 0))
        age_sec = target_epoch - int(latest.get("ts") or 0)
        if age_sec > MAX_SOURCE_AGE_SEC:
            continue
        latest["capture_age_sec"] = age_sec
        output[name] = [latest]
    return output


def capture_q12_btc_0855_snapshot(
    *,
    day: str,
    root: Path | str = DEFAULT_ROOT,
    now: datetime | None = None,
    signal_loader: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_day = str(day)[:10]
    paths = capture_paths(normalized_day, root=root)
    existing = _read(paths["snapshot"])
    if existing.get("capture_status") in {"CAPTURED", "MISSED"}:
        return existing

    current = (now or datetime.now(KST)).astimezone(KST)
    target = _target(normalized_day)
    deadline = target.replace(hour=8, minute=59, second=59)
    base = {
        "schema_version": "q12_btc_0855_snapshot.v1",
        "day": normalized_day,
        "scheduled_target_kst": target.isoformat(),
        "attempted_at_kst": current.isoformat(),
        "behavior_effect": "controlled_mock_lane_input",
    }
    if current < target:
        result = {
            **base,
            "capture_status": "WAITING",
            "reason": "08:55_capture_window_not_open",
            "snapshot_submitted": False,
            "sources": {},
            "source_count": 0,
        }
        _record_attempt(paths["ledger"], result, snapshot_path=paths["snapshot"])
        return result
    if current > deadline:
        result = {
            **base,
            "capture_status": "MISSED",
            "reason": "08:55_capture_window_missed_no_backfill",
            "snapshot_submitted": False,
            "sources": {},
            "source_count": 0,
        }
        _write(paths["snapshot"], result)
        _record_attempt(paths["ledger"], result, snapshot_path=paths["snapshot"])
        return result

    if signal_loader is None:
        from .data_provider import load_btc_signal_rows

        payload = dict(
            load_btc_signal_rows(
                day=normalized_day,
                include_research_context=False,
            )
        )
    else:
        payload = dict(signal_loader(day=normalized_day))
    sources = _source_points(payload, target_epoch=int(target.timestamp()))
    has_btc_usd = bool(sources.get("btc_usd"))
    status = "CAPTURED" if has_btc_usd else "MISSING"
    result = {
        **base,
        "capture_status": status,
        "reason": "" if status == "CAPTURED" else "btc_usd_point_in_time_source_missing",
        "snapshot_submitted": status == "CAPTURED",
        "target_epoch": int(target.timestamp()),
        "sources": sources,
        "source_count": len(sources),
        "available_sources": sorted(sources),
    }
    _write(paths["snapshot"], result)
    _record_attempt(paths["ledger"], result, snapshot_path=paths["snapshot"])
    return result


__all__ = [
    "DEFAULT_ROOT",
    "capture_paths",
    "capture_q12_btc_0855_snapshot",
    "load_capture_snapshot",
    "load_captured_sources",
]
