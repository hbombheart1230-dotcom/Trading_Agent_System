from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from libs.performance.strategy_memory import load_strategy_memory_hint
from libs.runtime.operator_summary_memory import load_operator_daily_summary, resolve_operator_summary_day
from libs.runtime.strategy_memory_support_artifacts import (
    resolve_monitor_status,
    resolve_report_focus_targets,
    resolve_route_context,
    resolve_scanner_status,
)
from libs.runtime.strategy_memory_window_sections import (
    build_execution_risk,
    build_failure_patterns,
    build_recommended_bias_inputs,
    build_regime_stats,
    build_sample_quality,
    build_source_performance,
    build_window_summary,
)


def _resolve_state_day(state: Dict[str, Any]) -> str:
    for key in ("day", "trade_day"):
        text = str(state.get(key) or "").strip()
        if text:
            return text
    ts = str(state.get("ts") or "").strip()
    if len(ts) >= 10:
        return ts[:10]
    return ""


def _read_json_dict(path: Path) -> Dict[str, Any]:
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_daily_strategy_memory_packet(*, state: Dict[str, Any]) -> Dict[str, Any]:
    reports_root = Path(str(state.get("reports_root") or os.getenv("REPORTS_ROOT", "reports")).strip() or "reports")
    operator_day = resolve_operator_summary_day(state) or _resolve_state_day(state)
    operator_summary = load_operator_daily_summary(reports_root=reports_root, day=operator_day)
    src = state.get("strategy_memory") if isinstance(state.get("strategy_memory"), dict) else {}
    source = "state.strategy_memory"
    if not src:
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
                "operator_summary": operator_summary,
                "advisory_only": True,
            }
    row = dict(src or {})
    if row:
        resolved_day = str(row.get("resolved_day") or row.get("day") or _resolve_state_day(state)).strip()
        row["support_metrics"] = _read_json_dict(reports_root / "metrics" / f"metrics_{resolved_day}.json")
        row["support_reporter_analysis"] = _read_json_dict(
            reports_root / "dev" / "analysis" / "reporter_analysis" / f"reporter_analysis_{resolved_day}.json"
        )
    status = str(row.get("status") or "empty").strip() or "empty"
    requested_day = str(row.get("requested_day") or row.get("day") or "").strip()
    resolved_day = str(row.get("resolved_day") or row.get("day") or "").strip()
    rows = [row] if row else []
    sample_quality = build_sample_quality(
        rows=rows,
        requested_day=requested_day,
        resolved_day=resolved_day,
        max_days=1,
        min_required_days=1,
    ) if row else {
        "trade_count": 0,
        "filled_trade_count": 0,
        "usable": status == "ok",
        "confidence": 0.0,
        "max_age_days": 0,
        "sample_day_ratio": 0.0,
        "trade_density": 0.0,
        "min_required_days": 1,
    }
    source_performance = build_source_performance(rows)
    failure_patterns = build_failure_patterns(rows)
    execution_risk = build_execution_risk(rows)
    route_context = resolve_route_context(row) if row else {}
    source_context = {
        "route_source": str(route_context.get("route_source") or ""),
        "route_selected_total": dict(route_context.get("route_selected_total") or {}),
        "strategist_mode_total": dict(route_context.get("strategist_mode_total") or {}),
        "alignment_totals": dict(route_context.get("alignment_totals") or {}),
        "report_focus_targets": resolve_report_focus_targets(row) if row else [],
        "scanner_status": resolve_scanner_status(row) if row else "",
        "monitor_status": resolve_monitor_status(row) if row else "",
    }
    regime_stats = build_regime_stats(rows)
    best_playbooks = [str(x or "") for x in list(row.get("best_playbooks") or [])[:3] if str(x or "").strip()]
    worst_playbooks = [str(x or "") for x in list(row.get("worst_playbooks") or [])[:3] if str(x or "").strip()]
    recent_failures = [str(x or "") for x in list(row.get("recent_failures") or [])[:4] if str(x or "").strip()]
    recent_success_patterns = [str(x or "") for x in list(row.get("recent_success_patterns") or [])[:4] if str(x or "").strip()]
    recommended_bias_inputs = build_recommended_bias_inputs(
        layer="daily",
        best_playbooks=best_playbooks,
        worst_playbooks=worst_playbooks,
        source_performance=source_performance,
        failure_patterns=failure_patterns,
        execution_risk=execution_risk,
    )
    summary_detail = build_window_summary(
        layer="daily",
        contributing_days=[resolved_day] if resolved_day else [],
        best_playbooks=best_playbooks,
        worst_playbooks=worst_playbooks,
        failure_patterns=failure_patterns,
        source_performance=source_performance,
        execution_risk=execution_risk,
    )
    is_same_day = bool(requested_day and resolved_day and requested_day == resolved_day)
    active = (
        status == "ok"
        and is_same_day
        and bool(sample_quality.get("usable"))
    )
    return {
        "schema_version": "commander.memory_packet.v1",
        "memory_type": "daily",
        "layer": "daily",
        "status": status,
        "source": source,
        "active": active,
        "requested_day": requested_day,
        "resolved_day": resolved_day,
        "window_days": 1,
        "window_label": "same_day",
        "window": {
            "label": "same_day",
            "start": resolved_day,
            "end": resolved_day,
            "contributing_days": [resolved_day] if resolved_day else [],
        },
        "sample_day_count": 1 if resolved_day else 0,
        "sample_quality": sample_quality,
        "best_playbooks": best_playbooks,
        "worst_playbooks": worst_playbooks,
        "recent_failures": recent_failures,
        "recent_success_patterns": recent_success_patterns,
        "playbook_performance_snapshot": dict(row.get("playbook_performance_snapshot") or {}),
        "pattern_performance_snapshot": dict(row.get("pattern_performance_snapshot") or {}),
        "playbook_stats": dict(row.get("playbook_performance_snapshot") or {}),
        "source_performance": source_performance,
        "failure_patterns": failure_patterns,
        "execution_risk": execution_risk,
        "source_context": source_context,
        "regime_stats": regime_stats,
        "session_regime_observation": {
            "preferred_regimes": list((row.get("market_condition_bias") or {}).get("preferred_regimes") or [])[:2],
            "avoid_regimes": list((row.get("market_condition_bias") or {}).get("avoid_regimes") or [])[:2],
            "regime_stats": regime_stats,
        },
        "recommended_bias_inputs": recommended_bias_inputs,
        "operator_summary": operator_summary,
        "summary": summary_detail["headline"],
        "summary_detail": summary_detail,
        "advisory_only": bool(row.get("advisory_only", True)),
    }
