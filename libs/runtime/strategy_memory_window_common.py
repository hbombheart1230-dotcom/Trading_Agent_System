from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

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


def resolve_state_day(state: Dict[str, Any]) -> str:
    for key in ("day", "trade_day"):
        text = str(state.get(key) or "").strip()
        if text:
            return text
    ts = str(state.get("ts") or "").strip()
    if len(ts) >= 10:
        return ts[:10]
    return ""


def resolve_reports_root(state: Dict[str, Any]) -> Path:
    return Path(str(state.get("reports_root") or os.getenv("REPORTS_ROOT", "reports")).strip() or "reports")


def _valid_day_name(text: str) -> bool:
    return len(text) == 10 and text[4:5] == "-" and text[7:8] == "-"


def _read_json_dict(path: Path) -> Dict[str, Any]:
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def list_available_performance_days(*, reports_root: Path, end_day: str) -> List[str]:
    performance_root = Path(reports_root) / "performance"
    if not performance_root.exists():
        return []
    days = [
        path.name
        for path in performance_root.iterdir()
        if path.is_dir() and _valid_day_name(path.name) and (not end_day or path.name <= end_day)
    ]
    return sorted(days)


def load_strategy_memory_window_rows(
    *,
    reports_root: Path,
    end_day: str,
    max_days: int,
) -> List[Dict[str, Any]]:
    days = list_available_performance_days(reports_root=reports_root, end_day=end_day)
    selected_days = days[-max_days:] if max_days > 0 else days
    out: List[Dict[str, Any]] = []
    for day in selected_days:
        memory_path = Path(reports_root) / "performance" / day / "strategy_memory.json"
        row = _read_json_dict(memory_path)
        if not row:
            continue
        normalized = dict(row)
        normalized.setdefault("day", day)
        normalized["artifact_path"] = str(memory_path)
        normalized["support_metrics"] = _read_json_dict(Path(reports_root) / "metrics" / f"metrics_{day}.json")
        normalized["support_reporter_analysis"] = _read_json_dict(
            Path(reports_root) / "dev" / "analysis" / "reporter_analysis" / f"reporter_analysis_{day}.json"
        )
        out.append(normalized)
    return out


def _tally_items(rows: Iterable[Mapping[str, Any]], key: str, *, limit: int) -> List[str]:
    counts: Dict[str, int] = {}
    for row in rows:
        for item in list((row or {}).get(key) or []):
            text = str(item or "").strip()
            if not text:
                continue
            counts[text] = counts.get(text, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [name for name, _count in ordered[:limit]]


def _collect_playbook_snapshot(rows: Iterable[Mapping[str, Any]], *, limit: int) -> Dict[str, Any]:
    aggregate: Dict[str, Dict[str, float]] = {}
    for row in rows:
        snapshot = row.get("playbook_performance_snapshot") if isinstance(row.get("playbook_performance_snapshot"), dict) else {}
        for name, payload in snapshot.items():
            item = payload if isinstance(payload, dict) else {}
            text = str(name or "").strip()
            if not text:
                continue
            target = aggregate.setdefault(
                text,
                {
                    "sample_days": 0.0,
                    "usage_count": 0.0,
                    "win_rate_sum": 0.0,
                    "avg_return_sum": 0.0,
                    "stability_sum": 0.0,
                },
            )
            target["sample_days"] += 1.0
            target["usage_count"] += float(item.get("usage_count") or 0.0)
            target["win_rate_sum"] += float(item.get("win_rate") or 0.0)
            target["avg_return_sum"] += float(item.get("avg_return") or 0.0)
            target["stability_sum"] += float(item.get("stability_score") or 0.0)
    ranked = sorted(
        aggregate.items(),
        key=lambda item: (
            -(item[1]["stability_sum"] / max(item[1]["sample_days"], 1.0)),
            -(item[1]["avg_return_sum"] / max(item[1]["sample_days"], 1.0)),
            item[0],
        ),
    )
    out: Dict[str, Any] = {}
    for name, stats in ranked[:limit]:
        sample_days = max(int(stats["sample_days"]), 1)
        out[name] = {
            "sample_days": sample_days,
            "usage_count": int(stats["usage_count"]),
            "win_rate": stats["win_rate_sum"] / sample_days,
            "avg_return": stats["avg_return_sum"] / sample_days,
            "stability_score": stats["stability_sum"] / sample_days,
        }
    return out


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _normalize_summary_detail(summary: Any) -> Dict[str, Any]:
    if isinstance(summary, dict):
        headline = str(summary.get("headline") or "").strip()
        bullets = [str(x or "").strip() for x in list(summary.get("bullets") or []) if str(x or "").strip()]
        return {"headline": headline, "bullets": bullets[:5]}
    headline = str(summary or "").strip()
    return {"headline": headline, "bullets": [headline] if headline else []}


def _base_unavailable_packet(
    *,
    layer: str,
    requested_day: str,
    max_days: int,
    min_required_days: int,
) -> Dict[str, Any]:
    summary_detail = {
        "headline": f"{layer} memory is unavailable.",
        "bullets": ["no performance-window artifacts were found"],
    }
    return {
        "schema_version": "commander.memory_packet.v1",
        "memory_type": layer,
        "layer": layer,
        "status": "unavailable",
        "source": "reports.performance.strategy_memory_window",
        "active": False,
        "requested_day": requested_day,
        "resolved_day": "",
        "window_days": max_days,
        "window_label": f"last_{max_days}_trading_days",
        "window": {
            "label": f"last_{max_days}_trading_days",
            "start": "",
            "end": "",
            "contributing_days": [],
        },
        "sample_day_count": 0,
        "sample_quality": {
            "trade_count": 0,
            "filled_trade_count": 0,
            "usable": False,
            "confidence": 0.0,
            "max_age_days": 0,
            "sample_day_ratio": 0.0,
            "trade_density": 0.0,
            "min_required_days": min_required_days,
        },
        "contributing_days": [],
        "best_playbooks": [],
        "worst_playbooks": [],
        "recent_failures": [],
        "recent_success_patterns": [],
        "playbook_performance_snapshot": {},
        "playbook_stats": {},
        "source_performance": {},
        "failure_patterns": {
            "dominant_failures": [],
            "dominant_monitor_reasons": [],
            "dominant_supervisor_blockers": [],
            "repeat_failure_count": 0,
        },
        "execution_risk": {
            "system_health": "",
            "scanner_status": "",
            "monitor_status": "",
            "dominant_risks": [],
            "incident_total": 0,
            "avg_monitor_only_ratio": 0.0,
            "avg_cached_strategist_ratio": 0.0,
            "avg_full_cycle_ratio": 0.0,
            "route_source": "",
            "report_focus_targets": [],
            "alignment_totals": {},
            "preferred_risk_posture": "balanced",
        },
        "source_context": {
            "route_source": "",
            "route_selected_total": {},
            "strategist_mode_total": {},
            "alignment_totals": {},
            "report_focus_targets": [],
            "scanner_status": "",
            "monitor_status": "",
        },
        "regime_stats": {},
        "regime_fit": {
            "preferred_regimes": [],
            "avoid_regimes": [],
            "regime_stats": {},
        },
        "baseline_playbook_preference": {"prefer": [], "avoid": []},
        "risk_posture_baseline": {"preferred_risk_posture": "balanced"},
        "recommended_bias_inputs": {
            "scanner": {"source_weight_delta": {}, "prefer_playbooks": [], "avoid_playbooks": []},
            "monitor": {"dominant_blockers": []},
            "commander": {"preferred_risk_posture": "balanced", "bias_confidence_hint": "normal"},
        },
        "summary": summary_detail["headline"],
        "summary_detail": summary_detail,
        "advisory_only": True,
    }


def normalize_window_strategy_memory_packet(
    *,
    row: Dict[str, Any],
    layer: str,
    max_days: int,
    min_required_days: int,
) -> Dict[str, Any]:
    packet = dict(row or {})
    requested_day = str(packet.get("requested_day") or packet.get("day") or "").strip()
    resolved_day = str(packet.get("resolved_day") or packet.get("day") or "").strip()
    contributing_days = [str(x or "").strip() for x in list(packet.get("contributing_days") or []) if str(x or "").strip()]
    if not contributing_days and resolved_day:
        contributing_days = [resolved_day]
    window_label = str(packet.get("window_label") or f"last_{max_days}_trading_days").strip()
    sample_day_count = _safe_int(packet.get("sample_day_count") or len(contributing_days))
    active = bool(packet.get("active"))
    status = str(packet.get("status") or ("ok" if active else "unavailable")).strip() or "unavailable"
    sample_quality = dict(packet.get("sample_quality") or {})
    sample_quality.setdefault("trade_count", _safe_int(packet.get("trade_count")))
    sample_quality.setdefault("filled_trade_count", _safe_int(packet.get("filled_trade_count") or sample_quality.get("trade_count")))
    sample_quality.setdefault("usable", active)
    sample_quality.setdefault("confidence", 1.0 if active else 0.0)
    sample_quality.setdefault("max_age_days", 0)
    sample_quality.setdefault("sample_day_ratio", 0.0)
    sample_quality.setdefault("trade_density", 0.0)
    sample_quality.setdefault("min_required_days", min_required_days)
    summary_detail = _normalize_summary_detail(packet.get("summary_detail") or packet.get("summary"))
    return {
        **_base_unavailable_packet(
            layer=layer,
            requested_day=requested_day,
            max_days=max_days,
            min_required_days=min_required_days,
        ),
        **packet,
        "memory_type": layer,
        "layer": layer,
        "status": status,
        "active": active,
        "requested_day": requested_day,
        "resolved_day": resolved_day,
        "window_days": _safe_int(packet.get("window_days") or max_days),
        "window_label": window_label,
        "window": {
            "label": window_label,
            "start": contributing_days[0] if contributing_days else "",
            "end": resolved_day,
            "contributing_days": contributing_days,
        },
        "sample_day_count": sample_day_count,
        "sample_quality": sample_quality,
        "contributing_days": contributing_days,
        "playbook_stats": dict(packet.get("playbook_stats") or packet.get("playbook_performance_snapshot") or {}),
        "source_performance": dict(packet.get("source_performance") or {}),
        "failure_patterns": dict(packet.get("failure_patterns") or {}),
        "execution_risk": dict(packet.get("execution_risk") or {}),
        "source_context": dict(packet.get("source_context") or {}),
        "regime_stats": dict(packet.get("regime_stats") or {}),
        "regime_fit": dict(packet.get("regime_fit") or {}),
        "baseline_playbook_preference": dict(packet.get("baseline_playbook_preference") or {}),
        "risk_posture_baseline": dict(packet.get("risk_posture_baseline") or {}),
        "recommended_bias_inputs": dict(packet.get("recommended_bias_inputs") or {}),
        "summary": summary_detail["headline"],
        "summary_detail": summary_detail,
    }


def build_window_strategy_memory_packet(
    *,
    state: Dict[str, Any],
    layer: str,
    max_days: int,
    min_required_days: int,
) -> Dict[str, Any]:
    reports_root = resolve_reports_root(state)
    requested_day = resolve_state_day(state)
    rows = load_strategy_memory_window_rows(
        reports_root=reports_root,
        end_day=requested_day,
        max_days=max_days,
    )
    if not rows:
        return _base_unavailable_packet(
            layer=layer,
            requested_day=requested_day,
            max_days=max_days,
            min_required_days=min_required_days,
        )
    contributing_days = [str(row.get("day") or "").strip() for row in rows if str(row.get("day") or "").strip()]
    best_playbooks = _tally_items(rows, "best_playbooks", limit=3)
    worst_playbooks = _tally_items(rows, "worst_playbooks", limit=3)
    recent_failures = _tally_items(rows, "recent_failures", limit=4)
    recent_success_patterns = _tally_items(rows, "recent_success_patterns", limit=4)
    playbook_snapshot = _collect_playbook_snapshot(rows, limit=4)
    sample_quality = build_sample_quality(
        rows=rows,
        requested_day=requested_day,
        resolved_day=contributing_days[-1],
        max_days=max_days,
        min_required_days=min_required_days,
    )
    source_performance = build_source_performance(rows)
    failure_patterns = build_failure_patterns(rows)
    execution_risk = build_execution_risk(rows)
    latest_route_context = resolve_route_context(rows[-1]) if rows else {}
    source_context = {
        "route_source": str(latest_route_context.get("route_source") or ""),
        "route_selected_total": dict(latest_route_context.get("route_selected_total") or {}),
        "strategist_mode_total": dict(latest_route_context.get("strategist_mode_total") or {}),
        "alignment_totals": dict(latest_route_context.get("alignment_totals") or {}),
        "report_focus_targets": resolve_report_focus_targets(rows[-1]) if rows else [],
        "scanner_status": resolve_scanner_status(rows[-1]) if rows else "",
        "monitor_status": resolve_monitor_status(rows[-1]) if rows else "",
    }
    regime_stats = build_regime_stats(rows)
    recommended_bias_inputs = build_recommended_bias_inputs(
        layer=layer,
        best_playbooks=best_playbooks,
        worst_playbooks=worst_playbooks,
        source_performance=source_performance,
        failure_patterns=failure_patterns,
        execution_risk=execution_risk,
    )
    window_label = f"last_{max_days}_trading_days"
    sample_day_count = len(contributing_days)
    confidence_floor = 0.5 if layer == "weekly" else 0.45
    usable = bool(sample_quality.get("usable"))
    active = usable and float(sample_quality.get("confidence") or 0.0) >= confidence_floor
    summary_detail = build_window_summary(
        layer=layer,
        contributing_days=contributing_days,
        best_playbooks=best_playbooks,
        worst_playbooks=worst_playbooks,
        failure_patterns=failure_patterns,
        source_performance=source_performance,
        execution_risk=execution_risk,
    )
    return {
        "schema_version": "commander.memory_packet.v1",
        "memory_type": layer,
        "layer": layer,
        "status": "ok",
        "source": "reports.performance.strategy_memory_window",
        "active": active,
        "requested_day": requested_day,
        "resolved_day": contributing_days[-1],
        "window_days": max_days,
        "window_label": window_label,
        "window": {
            "label": window_label,
            "start": contributing_days[0],
            "end": contributing_days[-1],
            "contributing_days": contributing_days,
        },
        "sample_day_count": sample_day_count,
        "sample_quality": sample_quality,
        "contributing_days": contributing_days,
        "best_playbooks": best_playbooks,
        "worst_playbooks": worst_playbooks,
        "recent_failures": recent_failures,
        "recent_success_patterns": recent_success_patterns,
        "playbook_performance_snapshot": playbook_snapshot,
        "playbook_stats": playbook_snapshot,
        "source_performance": source_performance,
        "failure_patterns": failure_patterns,
        "execution_risk": execution_risk,
        "source_context": source_context,
        "regime_stats": regime_stats,
        "regime_fit": {
            "preferred_regimes": [
                name for name, payload in list(regime_stats.items())[:2] if float((payload or {}).get("avg_return_pct") or 0.0) >= 0.0
            ][:2],
            "avoid_regimes": [
                name for name, payload in sorted(
                    regime_stats.items(),
                    key=lambda item: float((item[1] or {}).get("avg_return_pct") or 0.0),
                )
                if float((payload or {}).get("avg_return_pct") or 0.0) < 0.0
            ][:2],
            "regime_stats": regime_stats,
        },
        "baseline_playbook_preference": {
            "prefer": best_playbooks[:2],
            "avoid": worst_playbooks[:2],
        },
        "risk_posture_baseline": {
            "preferred_risk_posture": str(execution_risk.get("preferred_risk_posture") or "balanced"),
            "system_health": str(execution_risk.get("system_health") or ""),
        },
        "recommended_bias_inputs": recommended_bias_inputs,
        "summary": summary_detail["headline"],
        "summary_detail": summary_detail,
        "advisory_only": True,
    }


__all__ = [
    "build_window_strategy_memory_packet",
    "list_available_performance_days",
    "load_strategy_memory_window_rows",
    "normalize_window_strategy_memory_packet",
    "resolve_reports_root",
    "resolve_state_day",
]
