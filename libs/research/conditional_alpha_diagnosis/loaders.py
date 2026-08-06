from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .metrics import number


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def load_existing_research(
    *, deep_dive_path: Path, longitudinal_path: Path, horizon_path: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    deep = read_json(deep_dive_path)
    longitudinal = read_json(longitudinal_path)
    horizon = read_json(horizon_path)
    return (
        [dict(row) for row in deep.get("cases", []) if isinstance(row, Mapping)],
        [dict(row) for row in longitudinal.get("events", []) if isinstance(row, Mapping)],
        [dict(row) for row in horizon.get("trade_rows", []) if isinstance(row, Mapping)],
    )


def _candidate(selection: Mapping[str, Any], symbol: str) -> dict[str, Any]:
    for key in ("selected_candidate", "scanner_selected", "scanner_top1"):
        value = selection.get(key)
        if isinstance(value, Mapping) and str(value.get("symbol") or "") == symbol:
            return dict(value)
    for key in ("post_strategist_top10", "scanner_top10", "raw_scanner_top10"):
        values = selection.get(key)
        if isinstance(values, list):
            for value in values:
                if isinstance(value, Mapping) and str(value.get("symbol") or "") == symbol:
                    return dict(value)
    return {}


def load_actual_trade_context(reports_root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted((reports_root / "evaluation" / "trades").glob("**/trade_read_model.json")):
        model = read_json(path)
        trade_id = str(model.get("trade_id") or path.parent.name)
        symbol = str(model.get("symbol") or "")
        selection = model.get("selection")
        selection = selection if isinstance(selection, Mapping) else {}
        candidate = _candidate(selection, symbol)
        monitor = model.get("monitor")
        monitor = monitor if isinstance(monitor, Mapping) else {}
        entry = model.get("entry")
        entry = entry if isinstance(entry, Mapping) else {}
        exit_data = model.get("exit")
        exit_data = exit_data if isinstance(exit_data, Mapping) else {}
        outcome = model.get("outcome")
        outcome = outcome if isinstance(outcome, Mapping) else {}
        evaluation = read_json(path.with_name("trade_evaluation.json"))
        tactic = evaluation.get("tactic_alignment")
        tactic = tactic if isinstance(tactic, Mapping) else {}
        horizon = evaluation.get("horizon_alignment")
        horizon = horizon if isinstance(horizon, Mapping) else {}
        result[trade_id] = {
            "trade_id": trade_id,
            "day": str(model.get("day") or "")[:10],
            "symbol": symbol,
            "entry_timestamp": entry.get("timestamp"),
            "entry_price": number(entry.get("price")),
            "entry_reason": entry.get("reason"),
            "exit_timestamp": exit_data.get("timestamp"),
            "exit_price": number(exit_data.get("price")),
            "exit_reason": exit_data.get("reason"),
            "realized_return_pct": number(outcome.get("net_return_pct")),
            "holding_seconds": number(outcome.get("holding_seconds")),
            "strategy_horizon": horizon.get("strategy_horizon"),
            "horizon_bucket": horizon.get("bucket"),
            "horizon_violation_candidate": horizon.get("horizon_violation_candidate"),
            "playbook": tactic.get("playbook"),
            "selected_rank": tactic.get("selected_rank"),
            "scanner_score": number(candidate.get("score_total")),
            "risk_score": number(candidate.get("risk_score")),
            "confidence": number(candidate.get("confidence")),
            "chart_fit_score": number(candidate.get("scanner_chart_fit_score")),
            "macro_chart_fit_score": number(candidate.get("scanner_macro_chart_fit_score")),
            "score_breakdown": candidate.get("score_breakdown") or {},
            "monitor_primary_blocker": monitor.get("primary_blocker"),
            "source_path": str(path),
        }
    return result
