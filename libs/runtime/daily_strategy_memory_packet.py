from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from libs.performance.strategy_memory import load_strategy_memory_hint


def _resolve_state_day(state: Dict[str, Any]) -> str:
    for key in ("day", "trade_day"):
        text = str(state.get(key) or "").strip()
        if text:
            return text
    ts = str(state.get("ts") or "").strip()
    if len(ts) >= 10:
        return ts[:10]
    return ""


def build_daily_strategy_memory_packet(*, state: Dict[str, Any]) -> Dict[str, Any]:
    src = state.get("strategy_memory") if isinstance(state.get("strategy_memory"), dict) else {}
    source = "state.strategy_memory"
    if not src:
        reports_root = Path(str(state.get("reports_root") or os.getenv("REPORTS_ROOT", "reports")).strip() or "reports")
        try:
            src = load_strategy_memory_hint(
                reports_root=reports_root,
                day=_resolve_state_day(state),
                auto_build=False,
            )
            source = "reports.performance.strategy_memory"
        except Exception as exc:
            return {
                "schema_version": "commander.memory_packet.v1",
                "layer": "daily",
                "status": "error",
                "source": "reports.performance.strategy_memory",
                "active": False,
                "error": str(exc),
                "advisory_only": True,
            }
    row = dict(src or {})
    status = str(row.get("status") or "empty").strip() or "empty"
    return {
        "schema_version": "commander.memory_packet.v1",
        "layer": "daily",
        "status": status,
        "source": source,
        "active": status in {"ok", "empty"},
        "requested_day": str(row.get("requested_day") or row.get("day") or "").strip(),
        "resolved_day": str(row.get("resolved_day") or row.get("day") or "").strip(),
        "best_playbooks": [str(x or "") for x in list(row.get("best_playbooks") or [])[:3] if str(x or "").strip()],
        "worst_playbooks": [str(x or "") for x in list(row.get("worst_playbooks") or [])[:3] if str(x or "").strip()],
        "recent_failures": [str(x or "") for x in list(row.get("recent_failures") or [])[:4] if str(x or "").strip()],
        "recent_success_patterns": [str(x or "") for x in list(row.get("recent_success_patterns") or [])[:4] if str(x or "").strip()],
        "playbook_performance_snapshot": dict(row.get("playbook_performance_snapshot") or {}),
        "advisory_only": bool(row.get("advisory_only", True)),
    }
