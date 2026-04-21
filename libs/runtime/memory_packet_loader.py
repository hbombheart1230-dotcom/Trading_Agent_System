from __future__ import annotations

from typing import Any, Dict

from libs.runtime.daily_strategy_memory_packet import build_daily_strategy_memory_packet
from libs.runtime.monthly_strategy_memory_packet import build_monthly_strategy_memory_packet
from libs.runtime.symbol_memory_packet import build_symbol_memory_packet
from libs.runtime.weekly_strategy_memory_packet import build_weekly_strategy_memory_packet


def load_commander_memory_packets(*, state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        "daily_strategy_memory": build_daily_strategy_memory_packet(state=state),
        "weekly_strategy_memory": build_weekly_strategy_memory_packet(state=state),
        "monthly_strategy_memory": build_monthly_strategy_memory_packet(state=state),
        "symbol_memory_packet": build_symbol_memory_packet(state=state),
    }
