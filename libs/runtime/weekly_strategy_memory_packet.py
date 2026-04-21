from __future__ import annotations

from typing import Any, Dict


def build_weekly_strategy_memory_packet(*, state: Dict[str, Any]) -> Dict[str, Any]:
    row = state.get("weekly_strategy_memory") if isinstance(state.get("weekly_strategy_memory"), dict) else {}
    status = str(row.get("status") or ("ok" if row else "unavailable")).strip() or "unavailable"
    return {
        "schema_version": "commander.memory_packet.v1",
        "layer": "weekly",
        "status": status,
        "source": "state.weekly_strategy_memory" if row else "not_built_yet",
        "active": bool(row) and status == "ok",
        "summary": str(row.get("summary") or "").strip(),
        "best_playbooks": [str(x or "") for x in list(row.get("best_playbooks") or [])[:3] if str(x or "").strip()],
        "worst_playbooks": [str(x or "") for x in list(row.get("worst_playbooks") or [])[:3] if str(x or "").strip()],
        "advisory_only": True,
    }
