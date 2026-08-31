from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .contracts import LEDGER_SCHEMA_VERSION


DEFAULT_ROOT = Path("data/logs/controlled_mock_lanes")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _base(day: str, root: Path | str | None) -> Path:
    return Path(root or os.getenv("CONTROLLED_MOCK_LANE_LOG_ROOT") or DEFAULT_ROOT) / _text(day)


def ledger_path(day: str, *, root: Path | str | None = None) -> Path:
    return _base(day, root) / "lane_submissions.json"


def attempts_path(day: str, *, root: Path | str | None = None) -> Path:
    return _base(day, root) / "lane_attempts.json"


def evaluations_path(day: str, *, root: Path | str | None = None) -> Path:
    return _base(day, root) / "lane_evaluations.json"


def _read_rows(path: Path, key: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    rows = payload.get(key) if isinstance(payload, Mapping) else []
    return [dict(row) for row in list(rows or []) if isinstance(row, Mapping)]


def _write_rows(path: Path, *, day: str, key: str, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "day": _text(day),
        key: [dict(row) for row in rows],
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_submissions(day: str, *, root: Path | str | None = None) -> list[dict[str, Any]]:
    return _read_rows(ledger_path(day, root=root), "submissions")


def load_attempts(day: str, *, root: Path | str | None = None) -> list[dict[str, Any]]:
    return _read_rows(attempts_path(day, root=root), "attempts")


def load_evaluations(day: str, *, root: Path | str | None = None) -> list[dict[str, Any]]:
    return _read_rows(evaluations_path(day, root=root), "evaluations")


def lane_already_submitted(
    day: str, lane_id: str, *, root: Path | str | None = None
) -> bool:
    return any(
        _text(row.get("lane_id")) == _text(lane_id)
        and _text(row.get("status")) in {"BROKER_ACCEPTED", "FILLED"}
        for row in load_submissions(day, root=root)
    )


def signal_already_attempted(
    day: str, signal_id: str, *, root: Path | str | None = None
) -> bool:
    normalized = _text(signal_id)
    return bool(normalized) and any(
        _text(row.get("signal_id")) == normalized
        for row in load_attempts(day, root=root)
    )


def record_evaluations(
    *, day: str, rows: list[Mapping[str, Any]], recorded_at: str,
    root: Path | str | None = None,
) -> dict[str, Any]:
    path = evaluations_path(day, root=root)
    by_key = {
        (_text(row.get("lane_id")), _text(row.get("status")), _text(row.get("reason")), _text(row.get("signal_id"))): dict(row)
        for row in load_evaluations(day, root=root)
    }
    for raw in rows:
        row = dict(raw)
        key = (_text(row.get("lane_id")), _text(row.get("status")), _text(row.get("reason")), _text(row.get("signal_id")))
        prior = by_key.get(key, {})
        by_key[key] = {
            **row,
            "first_recorded_at": prior.get("first_recorded_at") or recorded_at,
            "last_recorded_at": recorded_at,
            "observation_count": int(prior.get("observation_count") or 0) + 1,
        }
    output = sorted(by_key.values(), key=lambda row: (_text(row.get("lane_id")), _text(row.get("first_recorded_at"))))
    _write_rows(path, day=day, key="evaluations", rows=output)
    return {"recorded": True, "path": str(path), "count": len(output)}


def record_attempt(
    *, day: str, candidate: Mapping[str, Any], run_id: str, recorded_at: str,
    execution: Mapping[str, Any], status: str, root: Path | str | None = None,
) -> dict[str, Any]:
    path = attempts_path(day, root=root)
    rows = load_attempts(day, root=root)
    signal_id = _text(candidate.get("signal_id"))
    if signal_id and any(_text(row.get("signal_id")) == signal_id for row in rows):
        return {"recorded": False, "reason": "signal_already_attempted", "path": str(path)}
    row = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "lane_id": _text(candidate.get("lane_id")),
        "run_id": _text(run_id),
        "recorded_at": _text(recorded_at),
        "symbol": _text(candidate.get("symbol")),
        "name": _text(candidate.get("name")),
        "score": candidate.get("score"),
        "signal_epoch": candidate.get("signal_epoch"),
        "signal_id": signal_id,
        "evidence": dict(candidate.get("evidence") or {}),
        "status": _text(status),
        "execution": {
            "allowed": bool(execution.get("allowed")),
            "ok": bool(execution.get("ok") or execution.get("execution_ok")),
            "reason": _text(execution.get("reason")),
            "order_id": _text(execution.get("order_id") or execution.get("ord_no")),
            "broker_code": _text(execution.get("broker_code")),
            "broker_message": _text(execution.get("broker_message")),
            "filled_qty": execution.get("filled_qty"),
            "filled_price": execution.get("filled_price"),
        },
    }
    rows.append(row)
    _write_rows(path, day=day, key="attempts", rows=rows)
    return {"recorded": True, "reason": "attempt_recorded", "path": str(path), "row": row}


def record_accepted_submission(
    *, day: str, candidate: Mapping[str, Any], run_id: str, recorded_at: str,
    execution: Mapping[str, Any], root: Path | str | None = None,
) -> dict[str, Any]:
    path = ledger_path(day, root=root)
    rows = load_submissions(day, root=root)
    lane_id = _text(candidate.get("lane_id"))
    if lane_already_submitted(day, lane_id, root=root):
        return {"recorded": False, "reason": "daily_lane_limit_reached", "path": str(path)}
    try:
        filled_qty = int(float(execution.get("filled_qty") or 0))
    except (TypeError, ValueError):
        filled_qty = 0
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
        "status": "FILLED" if filled_qty > 0 else "BROKER_ACCEPTED",
        "order_id": _text(execution.get("order_id") or execution.get("ord_no")),
        "broker_code": _text(execution.get("broker_code")),
        "filled_qty": filled_qty,
        "filled_price": execution.get("filled_price"),
    }
    rows.append(row)
    _write_rows(path, day=day, key="submissions", rows=rows)
    return {"recorded": True, "reason": "accepted_submission_recorded", "path": str(path), "row": row}


__all__ = [
    "attempts_path", "evaluations_path", "lane_already_submitted", "ledger_path",
    "load_attempts", "load_evaluations", "load_submissions", "record_accepted_submission",
    "record_attempt", "record_evaluations", "signal_already_attempted",
]
