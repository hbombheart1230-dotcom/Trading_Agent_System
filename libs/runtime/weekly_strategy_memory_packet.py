from __future__ import annotations

from typing import Any, Dict

from libs.runtime.strategy_memory_window_common import (
    build_window_strategy_memory_packet,
    normalize_window_strategy_memory_packet,
)

def build_weekly_strategy_memory_packet(*, state: Dict[str, Any]) -> Dict[str, Any]:
    row = state.get("weekly_strategy_memory") if isinstance(state.get("weekly_strategy_memory"), dict) else {}
    if row:
        return normalize_window_strategy_memory_packet(
            row={
                **dict(row),
                "source": "state.weekly_strategy_memory",
                "active": bool(row.get("active", str(row.get("status") or "ok").strip() == "ok")),
            },
            layer="weekly",
            max_days=5,
            min_required_days=2,
        )
    return build_window_strategy_memory_packet(state=state, layer="weekly", max_days=5, min_required_days=2)
