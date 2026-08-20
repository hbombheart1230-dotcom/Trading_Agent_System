from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


KST = timezone(timedelta(hours=9))
SELECTION_POLICY = "LATEST_AT_OR_BEFORE_DECISION"


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _snapshot_epoch(path: Path, payload: Mapping[str, Any], *, day: str) -> int:
    generated_at = str(payload.get("generated_at") or "").strip()
    if generated_at:
        try:
            return int(datetime.fromisoformat(generated_at.replace("Z", "+00:00")).timestamp())
        except ValueError:
            pass
    clock = path.name[:6]
    if len(clock) == 6 and clock.isdigit():
        try:
            return int(
                datetime.fromisoformat(
                    f"{day}T{clock[:2]}:{clock[2:4]}:{clock[4:]}+09:00"
                ).timestamp()
            )
        except ValueError:
            pass
    return 0


def load_market_snapshot_timeline(
    *,
    day: str,
    macro_root: Path = Path("data/logs/macro_indicators"),
) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    day_root = macro_root / day
    for path in sorted(day_root.glob("*_macro_indicators.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, Mapping):
            continue
        epoch = _snapshot_epoch(path, payload, day=day)
        if epoch <= 0:
            continue
        timeline.append(
            {
                "snapshot_epoch": epoch,
                "source_path": str(path),
                "payload": dict(payload),
            }
        )
    return sorted(timeline, key=lambda row: int(row["snapshot_epoch"]))


def select_market_snapshot(
    timeline: Sequence[Mapping[str, Any]],
    *,
    decision_epoch: int,
) -> dict[str, Any]:
    eligible = [
        row
        for row in timeline
        if 0 < int(row.get("snapshot_epoch") or 0) <= int(decision_epoch or 0)
    ]
    if not eligible:
        return {
            "schema_version": "opening_rank1_market_snapshot.v1",
            "evidence_status": "MISSING_NO_SNAPSHOT_AT_OR_BEFORE_DECISION",
            "selection_policy": SELECTION_POLICY,
            "decision_epoch": int(decision_epoch or 0),
            "snapshot_epoch": None,
            "snapshot_time_kst": "",
            "snapshot_age_sec": None,
            "source_path": "",
            "kospi_pct": None,
            "kosdaq_pct": None,
            "kospi200_pct": None,
            "krx_night_futures_pct": None,
        }
    selected = max(eligible, key=lambda row: int(row.get("snapshot_epoch") or 0))
    snapshot_epoch = int(selected.get("snapshot_epoch") or 0)
    payload = selected.get("payload") if isinstance(selected.get("payload"), Mapping) else {}
    moves = payload.get("index_moves") if isinstance(payload.get("index_moves"), Mapping) else {}
    return {
        "schema_version": "opening_rank1_market_snapshot.v1",
        "evidence_status": "OBSERVED_POINT_IN_TIME",
        "selection_policy": SELECTION_POLICY,
        "decision_epoch": int(decision_epoch or 0),
        "snapshot_epoch": snapshot_epoch,
        "snapshot_time_kst": datetime.fromtimestamp(snapshot_epoch, tz=KST).isoformat(timespec="seconds"),
        "snapshot_age_sec": max(0, int(decision_epoch or 0) - snapshot_epoch),
        "source_path": str(selected.get("source_path") or ""),
        "kospi_pct": _number(moves.get("kospi_pct")),
        "kosdaq_pct": _number(moves.get("kosdaq_pct")),
        "kospi200_pct": _number(moves.get("kospi200_pct")),
        "krx_night_futures_pct": _number(moves.get("krx_night_futures_pct")),
    }


__all__ = ["load_market_snapshot_timeline", "select_market_snapshot"]
