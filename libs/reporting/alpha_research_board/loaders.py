from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    source = {
        "path": str(path),
        "available": path.exists(),
        "error": None,
    }
    if not path.exists():
        source["error"] = "MISSING_ARTIFACT"
        return {}, source
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        source["error"] = f"INVALID_ARTIFACT:{type(exc).__name__}"
        return {}, source
    if not isinstance(payload, Mapping):
        source["error"] = "SCHEMA_MISMATCH:ROOT_NOT_OBJECT"
        return {}, source
    source["schema_version"] = payload.get("schema_version")
    source["through_day"] = payload.get("through_day") or payload.get("day")
    return dict(payload), source


def metric_snapshot(value: Any) -> dict[str, Any]:
    row = mapping(value)
    return {
        "sample_count": int(
            row.get("day_symbol_count")
            or row.get("observed_count")
            or row.get("trade_count")
            or row.get("count")
            or 0
        ),
        "window_count": int(
            row.get("observed_count")
            or row.get("episode_count")
            or row.get("trade_count")
            or row.get("count")
            or 0
        ),
        "win_rate": row.get("day_symbol_win_rate", row.get("win_rate")),
        "avg_net_return_pct": row.get(
            "day_symbol_avg_net_return_pct",
            row.get(
                "avg_net_return_pct",
                row.get("avg_return_pct", row.get("average_return_pct")),
            ),
        ),
        "profit_factor": row.get("profit_factor"),
        "max_drawdown_pct": row.get(
            "max_drawdown_pct", row.get("maximum_drawdown_pct")
        ),
        "coverage": row.get("target_coverage", row.get("coverage")),
        "avg_mfe_pct": row.get("avg_mfe_pct", row.get("average_mfe_pct")),
        "avg_mae_pct": row.get("avg_mae_pct", row.get("average_mae_pct")),
    }


def find_by_id(rows: Any, key: str, value: str) -> dict[str, Any]:
    for row in rows or []:
        item = mapping(row)
        nested = mapping(item.get("candidate"))
        if item.get(key) == value or nested.get(key) == value:
            return item
    return {}


def find_horizon(rows: Any, horizon: str) -> dict[str, Any]:
    for row in rows or []:
        item = mapping(row)
        if item.get("horizon") == horizon:
            return item
    return {}
