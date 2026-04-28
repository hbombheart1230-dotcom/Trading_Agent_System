from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict

from libs.reporting.llm_artifacts import (
    daily_artifact_paths,
    monthly_artifact_paths,
    symbol_artifact_paths,
    weekly_artifact_paths,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_json_dict(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_day(value: Any) -> date | None:
    text = _text(value)
    if len(text) >= 10:
        text = text[:10]
    if len(text) != 10:
        return None
    try:
        return date.fromisoformat(text)
    except Exception:
        return None


def _day_from_epoch(value: Any) -> str:
    try:
        epoch = int(float(value))
    except Exception:
        return ""
    if epoch <= 0:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).date().isoformat()


def resolve_operator_summary_day(state: Dict[str, Any]) -> str:
    for key in ("runtime_day", "session_day", "trade_day", "day"):
        parsed = _parse_day(state.get(key))
        if parsed:
            return parsed.isoformat()
    for key in ("started_at", "now_iso", "tick_ts", "ts"):
        raw = state.get(key)
        parsed = _parse_day(raw)
        if parsed:
            return parsed.isoformat()
        from_epoch = _day_from_epoch(raw)
        if from_epoch:
            return from_epoch
    return ""


def week_key_from_day(day_value: Any) -> str:
    parsed = _parse_day(day_value)
    if parsed is None:
        return ""
    iso = parsed.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def month_key_from_day(day_value: Any) -> str:
    parsed = _parse_day(day_value)
    if parsed is None:
        return ""
    return f"{parsed.year:04d}-{parsed.month:02d}"


def _with_status(payload: Dict[str, Any], *, path: Path, layer: str, key: str) -> Dict[str, Any]:
    if not payload:
        return {
            "available": False,
            "status": "missing",
            "layer": layer,
            "key": key,
            "artifact_path": str(path),
        }
    out = dict(payload)
    out["available"] = True
    out["status"] = "ok"
    out["layer"] = layer
    out["key"] = key
    out["artifact_path"] = str(path)
    return out


def load_operator_daily_summary(*, reports_root: Path, day: str) -> Dict[str, Any]:
    normalized_day = _text(day)
    path = daily_artifact_paths(Path(reports_root), normalized_day)["daily_summary_json"]
    return _with_status(_read_json_dict(path), path=path, layer="daily", key=normalized_day)


def load_operator_weekly_summary(*, reports_root: Path, week: str) -> Dict[str, Any]:
    normalized_week = _text(week)
    path = weekly_artifact_paths(Path(reports_root), normalized_week)["weekly_summary_json"]
    return _with_status(_read_json_dict(path), path=path, layer="weekly", key=normalized_week)


def load_operator_monthly_summary(*, reports_root: Path, month: str) -> Dict[str, Any]:
    normalized_month = _text(month)
    path = monthly_artifact_paths(Path(reports_root), normalized_month)["monthly_summary_json"]
    return _with_status(_read_json_dict(path), path=path, layer="monthly", key=normalized_month)


def load_operator_symbol_summary(*, reports_root: Path, symbol: str) -> Dict[str, Any]:
    normalized_symbol = _text(symbol).upper()
    path = symbol_artifact_paths(Path(reports_root), normalized_symbol)["symbol_summary_json"]
    return _with_status(_read_json_dict(path), path=path, layer="symbol", key=normalized_symbol)


def load_operator_period_summary_for_state(
    *,
    reports_root: Path,
    state: Dict[str, Any],
    layer: str,
) -> Dict[str, Any]:
    day = resolve_operator_summary_day(state)
    if layer == "daily":
        return load_operator_daily_summary(reports_root=reports_root, day=day)
    if layer == "weekly":
        return load_operator_weekly_summary(reports_root=reports_root, week=week_key_from_day(day))
    if layer == "monthly":
        return load_operator_monthly_summary(reports_root=reports_root, month=month_key_from_day(day))
    return {
        "available": False,
        "status": "unsupported_layer",
        "layer": layer,
        "key": "",
        "artifact_path": "",
    }


__all__ = [
    "load_operator_daily_summary",
    "load_operator_monthly_summary",
    "load_operator_period_summary_for_state",
    "load_operator_symbol_summary",
    "load_operator_weekly_summary",
    "month_key_from_day",
    "resolve_operator_summary_day",
    "week_key_from_day",
]
