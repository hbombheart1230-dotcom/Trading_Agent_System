from __future__ import annotations

from typing import Any, Dict

from libs.runtime.strategy_memory_window_common import (
    build_window_strategy_memory_packet,
    normalize_window_strategy_memory_packet,
    resolve_reports_root,
)
from libs.runtime.operator_summary_memory import load_operator_period_summary_for_state


def build_weekly_strategy_memory_packet(*, state: Dict[str, Any]) -> Dict[str, Any]:
    row = state.get("weekly_strategy_memory") if isinstance(state.get("weekly_strategy_memory"), dict) else {}
    if row:
        packet = normalize_window_strategy_memory_packet(
            row={
                **dict(row),
                "source": "state.weekly_strategy_memory",
                "active": bool(row.get("active", str(row.get("status") or "ok").strip() == "ok")),
            },
            layer="weekly",
            max_days=5,
            min_required_days=2,
        )
        if "operator_summary" not in packet:
            packet["operator_summary"] = load_operator_period_summary_for_state(
                reports_root=resolve_reports_root(state),
                state=state,
                layer="weekly",
            )
        return packet
    return build_window_strategy_memory_packet(state=state, layer="weekly", max_days=5, min_required_days=2)
