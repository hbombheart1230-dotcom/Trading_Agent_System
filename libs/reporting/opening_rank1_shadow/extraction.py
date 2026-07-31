from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .contracts import OPEN_END_MINUTE, OPEN_START_MINUTE


KST = timezone(timedelta(hours=9))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _valid_opening_epoch(epoch: int, day: str) -> bool:
    if epoch <= 0:
        return False
    try:
        value = datetime.fromtimestamp(epoch, tz=KST)
    except Exception:
        return False
    minute = value.hour * 60 + value.minute
    return (
        value.date().isoformat() == day
        and OPEN_START_MINUTE <= minute < OPEN_END_MINUTE
    )


def extract_opening_rank1_windows(
    *,
    reports_root: Path,
    day: str,
) -> dict[str, Any]:
    path = (
        Path(reports_root)
        / "operator_summary"
        / "daily"
        / day
        / "q9_decision_windows.json"
    )
    payload = _read_json(path)
    raw_scanner_windows = 0
    invalid_epoch_count = 0
    missing_universe_count = 0
    missing_rank1_count = 0
    canonical: dict[int, dict[str, Any]] = {}
    for raw in payload.get("windows") or []:
        if not isinstance(raw, Mapping) or raw.get("window_type") != "scanner_selection":
            continue
        raw_scanner_windows += 1
        epoch = int(raw.get("decision_epoch") or 0)
        if not _valid_opening_epoch(epoch, day):
            if epoch <= 0:
                invalid_epoch_count += 1
            continue
        universe = raw.get("scanner_pre_strategist_universe")
        universe = universe if isinstance(universe, Mapping) else {}
        candidates = [
            dict(row)
            for row in universe.get("intrinsic_ranked_top20") or []
            if isinstance(row, Mapping) and str(row.get("symbol") or "").strip()
        ]
        if not candidates:
            missing_universe_count += 1
            continue
        candidates.sort(
            key=lambda row: (
                int(row.get("rank") or 999),
                str(row.get("symbol") or ""),
            )
        )
        rank1 = next(
            (row for row in candidates if int(row.get("rank") or 999) == 1),
            None,
        )
        if rank1 is None:
            missing_rank1_count += 1
            continue
        canonical[epoch] = {
            "decision_id": str(raw.get("decision_id") or ""),
            "day": day,
            "decision_epoch": epoch,
            "candidates": [rank1],
            "source_path": str(path),
        }
    windows = [canonical[key] for key in sorted(canonical)]
    return {
        "source_path": str(path),
        "source_exists": path.exists(),
        "raw_scanner_window_count": raw_scanner_windows,
        "opening_window_count": len(windows),
        "invalid_epoch_count": invalid_epoch_count,
        "missing_universe_count": missing_universe_count,
        "missing_rank1_count": missing_rank1_count,
        "symbols": sorted(
            {
                str(candidate.get("symbol") or "")
                for window in windows
                for candidate in window["candidates"]
            }
        ),
        "windows": windows,
    }
