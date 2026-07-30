from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import TOP_K


KST = timezone(timedelta(hours=9))


def _days(start: str, end: str) -> Iterable[str]:
    current = date.fromisoformat(start[:10])
    last = date.fromisoformat(end[:10])
    while current <= last:
        yield current.isoformat()
        current += timedelta(days=1)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _valid_epoch(epoch: int, day: str) -> bool:
    if epoch <= 0:
        return False
    try:
        dt = datetime.fromtimestamp(epoch, tz=KST)
    except Exception:
        return False
    minute = dt.hour * 60 + dt.minute
    return dt.date().isoformat() == day and 9 * 60 <= minute <= 15 * 60 + 20


def load_point_in_time_windows(
    *,
    reports_root: Path,
    start: str,
    end: str,
) -> dict[str, Any]:
    canonical: dict[tuple[str, int], dict[str, Any]] = {}
    raw_window_count = 0
    invalid_epoch_count = 0
    for day in _days(start, end):
        path = reports_root / "operator_summary" / "daily" / day / "q9_decision_windows.json"
        payload = _read_json(path)
        for raw in payload.get("windows") or []:
            if not isinstance(raw, Mapping) or raw.get("window_type") != "scanner_selection":
                continue
            raw_window_count += 1
            epoch = int(raw.get("decision_epoch") or 0)
            if not _valid_epoch(epoch, day):
                invalid_epoch_count += 1
                continue
            universe = raw.get("scanner_pre_strategist_universe")
            universe = universe if isinstance(universe, Mapping) else {}
            candidates = [
                dict(row)
                for row in universe.get("intrinsic_ranked_top20") or []
                if isinstance(row, Mapping) and str(row.get("symbol") or "").strip()
            ]
            candidates.sort(key=lambda row: int(row.get("rank") or 999))
            candidates = candidates[:TOP_K]
            if not candidates:
                continue
            row = {
                "decision_id": str(raw.get("decision_id") or ""),
                "day": day,
                "decision_epoch": epoch,
                "candidates": candidates,
                "source_path": str(path),
            }
            key = (day, epoch)
            prior = canonical.get(key)
            if prior is None or len(candidates) > len(prior["candidates"]):
                canonical[key] = row
    rows = [canonical[key] for key in sorted(canonical)]
    return {
        "raw_window_count": raw_window_count,
        "canonical_window_count": len(rows),
        "invalid_epoch_count": invalid_epoch_count,
        "day_count": len({row["day"] for row in rows}),
        "symbol_count": len(
            {
                str(candidate.get("symbol") or "")
                for row in rows
                for candidate in row["candidates"]
            }
        ),
        "windows": rows,
    }
