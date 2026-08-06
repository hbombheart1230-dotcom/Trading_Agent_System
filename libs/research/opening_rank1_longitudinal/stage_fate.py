from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .delayed_outcomes import forward_30m_net


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in value or []
        if isinstance(row, Mapping)
    ]


def _rank(rows: list[dict[str, Any]], symbol: str) -> int | None:
    for index, row in enumerate(rows, start=1):
        if str(row.get("symbol") or "") == symbol:
            try:
                return int(row.get("rank") or index)
            except (TypeError, ValueError):
                return index
    return None


def load_executions_by_q9(
    reports_root: Path,
    days: set[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for day in sorted(days):
        root = reports_root / "evaluation" / "trades" / day
        for path in root.glob("*/trade_read_model.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            selection = _dict(payload.get("selection"))
            decision_id = str(selection.get("q9_decision_id") or "")
            if not decision_id:
                continue
            outcome = _dict(payload.get("outcome"))
            result[decision_id] = {
                "trade_id": payload.get("trade_id"),
                "symbol": payload.get("symbol"),
                "realized_return_pct": outcome.get("net_return_pct"),
                "holding_seconds": outcome.get("holding_seconds"),
            }
    return result


def stage_fate(
    case: Mapping[str, Any],
    *,
    window: Mapping[str, Any],
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
    execution: Mapping[str, Any] | None,
) -> dict[str, Any]:
    symbol = str(case.get("symbol") or "")
    strategist = _dict(window.get("strategist_selection"))
    post_rows = _rows(strategist.get("post_strategist_top10"))
    strategist_symbol = str(strategist.get("selected_symbol") or "")
    strategist_rank = _rank(post_rows, symbol)
    commander = _dict(window.get("commander_final"))
    monitor_symbol = str(
        commander.get("candidate_symbol")
        or commander.get("selected_symbol")
        or ""
    )
    decision_epoch = int(window.get("decision_epoch") or 0)
    day = str(case.get("day") or "")

    def shadow(symbol_value: str) -> float | None:
        if not symbol_value:
            return None
        return forward_30m_net(
            rows=minute_rows_by_symbol.get(symbol_value) or [],
            day=day,
            decision_epoch=decision_epoch,
        )

    if strategist_rank == 1:
        strategist_relation = "KEPT_TOP1"
    elif strategist_rank is not None:
        strategist_relation = "DEMOTED"
    else:
        strategist_relation = "OMITTED"
    if monitor_symbol == symbol:
        monitor_relation = "PRESERVED_INTRINSIC"
    elif monitor_symbol:
        monitor_relation = "SWITCHED_SYMBOL"
    else:
        monitor_relation = "NO_CANDIDATE"
    execution_row = dict(execution or {})
    executed_symbol = str(execution_row.get("symbol") or "")
    return {
        "intrinsic_symbol": symbol,
        "intrinsic_30m_net_pct": case.get("net_return_30m_pct"),
        "strategist_selected_symbol": strategist_symbol,
        "intrinsic_post_strategist_rank": strategist_rank,
        "strategist_relation": strategist_relation,
        "strategist_selected_30m_net_pct": shadow(strategist_symbol),
        "monitor_candidate_symbol": monitor_symbol,
        "monitor_intent": commander.get("monitor_intent"),
        "monitor_relation": monitor_relation,
        "monitor_candidate_30m_net_pct": shadow(monitor_symbol),
        "commander_decision": commander.get("decision"),
        "commander_reason": commander.get("reason"),
        "executed_trade_id": execution_row.get("trade_id"),
        "executed_symbol": executed_symbol,
        "executed_30m_net_pct": shadow(executed_symbol),
        "executed_realized_return_pct": execution_row.get(
            "realized_return_pct"
        ),
        "executed_holding_seconds": execution_row.get("holding_seconds"),
        "intrinsic_preserved_to_execution": executed_symbol == symbol
        if executed_symbol
        else False,
    }
