from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .contracts import LEDGER_SCHEMA_VERSION


DEFAULT_ROOT = Path("data/logs/controlled_mock_lanes")


def _text(value: Any) -> str:
    return str(value or "").strip()


def ledger_path(day: str, *, root: Path | str | None = None) -> Path:
    base = Path(root or os.getenv("CONTROLLED_MOCK_LANE_LOG_ROOT") or DEFAULT_ROOT)
    return base / _text(day) / "lane_submissions.json"


def load_submissions(day: str, *, root: Path | str | None = None) -> list[dict[str, Any]]:
    path = ledger_path(day, root=root)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    rows = payload.get("submissions") if isinstance(payload, Mapping) else []
    return [dict(row) for row in list(rows or []) if isinstance(row, Mapping)]


def lane_already_submitted(
    day: str, lane_id: str, *, root: Path | str | None = None
) -> bool:
    return any(
        _text(row.get("lane_id")) == _text(lane_id)
        for row in load_submissions(day, root=root)
    )


def reserve_submission(
    *,
    day: str,
    candidate: Mapping[str, Any],
    run_id: str,
    recorded_at: str,
    root: Path | str | None = None,
) -> dict[str, Any]:
    path = ledger_path(day, root=root)
    rows = load_submissions(day, root=root)
    lane_id = _text(candidate.get("lane_id"))
    if any(_text(row.get("lane_id")) == lane_id for row in rows):
        return {
            "recorded": False,
            "reason": "daily_lane_limit_reached",
            "path": str(path),
            "lane_id": lane_id,
        }
    row = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "lane_id": lane_id,
        "run_id": _text(run_id),
        "recorded_at": _text(recorded_at),
        "symbol": _text(candidate.get("symbol")),
        "name": _text(candidate.get("name")),
        "score": candidate.get("score"),
        "signal_epoch": candidate.get("signal_epoch"),
        "signal_id": _text(candidate.get("signal_id")),
        "evidence": dict(candidate.get("evidence") or {}),
        "status": "INTENT_RESERVED",
    }
    rows.append(row)
    payload = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "day": _text(day),
        "submissions": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return {
        "recorded": True,
        "reason": "reserved",
        "path": str(path),
        "lane_id": lane_id,
        "row": row,
    }


__all__ = [
    "lane_already_submitted",
    "ledger_path",
    "load_submissions",
    "reserve_submission",
]
