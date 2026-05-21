from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return dict(payload or {}) if isinstance(payload, dict) else {}
    except Exception:
        return {}
    return {}


def _period_summary_path(*, reports_root: Path, period_type: str, period_key: str) -> Path:
    kind = str(period_type or "").strip().lower()
    key = str(period_key or "").strip()
    if kind == "daily":
        return reports_root / "operator_summary" / "daily" / key / "daily_summary.json"
    if kind == "monthly":
        return reports_root / "operator_summary" / "monthly" / key / "monthly_summary.json"
    return reports_root / "operator_summary" / "weekly" / key / "weekly_summary.json"


def load_operator_period_summary(
    *,
    reports_root: str | Path,
    period_type: str = "weekly",
    period_key: str,
) -> Dict[str, Any]:
    root = Path(reports_root)
    path = _period_summary_path(reports_root=root, period_type=period_type, period_key=period_key)
    payload = _read_json(path)
    return {
        "available": bool(payload),
        "artifact_path": str(path),
        "period_type": str(period_type or "weekly"),
        "period_key": str(period_key or ""),
        "summary": payload,
    }


def _rows(root: Dict[str, Any], *path: str) -> List[Dict[str, Any]]:
    cur: Any = root
    for key in path:
        if not isinstance(cur, dict):
            return []
        cur = cur.get(key)
    if not isinstance(cur, list):
        return []
    return [dict(row) for row in cur if isinstance(row, dict)]


def build_quant_memory_packet_from_operator_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(summary or {})
    perf = dict(payload.get("pattern_performance") or {})
    metrics = dict(payload.get("metrics") or {})
    return {
        "schema_version": "quant_memory_packet.v1",
        "source": "operator_period_summary",
        "available": bool(payload),
        "period_type": str(payload.get("period_type") or ""),
        "period_key": str(payload.get("period_key") or ""),
        "date_range": dict(payload.get("date_range") or {}),
        "metrics": {
            "trade_count": int(metrics.get("trade_count") or 0),
            "closed_trade_count": int(metrics.get("closed_trade_count") or metrics.get("closed_or_realized_exit_count") or 0),
            "win_rate": metrics.get("win_rate"),
            "avg_return_pct": metrics.get("avg_return_pct"),
            "avg_hold_seconds": metrics.get("avg_hold_seconds"),
            "return_basis": str(metrics.get("return_basis") or ""),
        },
        "tactic_rows": _rows(perf, "strategist", "by_tactical_strategy"),
        "playbook_rows": _rows(perf, "strategist", "by_final_playbook"),
        "horizon_rows": _rows(perf, "strategist", "by_strategy_horizon"),
        "scanner_rank_rows": _rows(perf, "scanner", "by_scanner_rank_bucket"),
        "entry_pattern_rows": _rows(perf, "monitor_entry", "by_entry_pattern_type"),
        "exit_reason_rows": _rows(perf, "monitor_exit", "by_exit_reason"),
        "cost_floor_rows": _rows(perf, "monitor_exit", "by_cost_floor_state"),
        "quant_tactic_rows": _rows(perf, "quant", "by_tactic_id"),
        "quant_tactic_suitability_rows": _rows(perf, "quant", "by_tactic_suitability_tier"),
        "quant_entry_decision_rows": _rows(perf, "quant", "by_entry_decision"),
        "quant_entry_blocker_rows": _rows(perf, "quant", "by_entry_primary_blocker"),
        "quant_entry_cost_floor_rows": _rows(perf, "quant", "by_entry_cost_floor_state"),
        "quant_exit_decision_rows": _rows(perf, "quant", "by_exit_decision"),
        "quant_exit_blocker_rows": _rows(perf, "quant", "by_exit_primary_blocker"),
        "quant_exit_confirmation_rows": _rows(perf, "quant", "by_exit_confirmation_state"),
        "quant_exit_hold_window_rows": _rows(perf, "quant", "by_exit_hold_window_state"),
        "combined_rows": _rows(perf, "combined", "by_strategy_scanner_entry_exit"),
    }


def load_quant_memory_packet(
    *,
    reports_root: str | Path,
    period_type: str = "weekly",
    period_key: str,
) -> Dict[str, Any]:
    loaded = load_operator_period_summary(
        reports_root=reports_root,
        period_type=period_type,
        period_key=period_key,
    )
    packet = build_quant_memory_packet_from_operator_summary(dict(loaded.get("summary") or {}))
    packet["artifact_path"] = str(loaded.get("artifact_path") or "")
    return packet
