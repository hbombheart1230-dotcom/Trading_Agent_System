from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .performance_aggregator import (
    aggregate_performance_from_reports_root,
    performance_artifact_paths,
    write_performance_summary,
)
from .playbook_stats import calculate_playbook_stats, write_playbook_stats


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _read_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _top_counter_keys(mapping: Any, *, limit: int = 3) -> List[str]:
    if not isinstance(mapping, dict):
        return []
    rows: List[tuple[str, float]] = []
    for key, value in mapping.items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            score = float(value)
        except Exception:
            score = 0.0
        rows.append((name, score))
    rows.sort(key=lambda item: (-item[1], item[0]))
    return [name for name, _score in rows[: max(1, int(limit))]]


def _extract_route_mix_digest(report: Dict[str, Any], reports_root: Path) -> Dict[str, Any]:
    source_reports = report.get("source_reports") if isinstance(report.get("source_reports"), dict) else {}
    trade_explain_path_raw = str(source_reports.get("trade_explain_json") or "").strip()
    trade_explain_path = Path(trade_explain_path_raw) if trade_explain_path_raw else Path()
    if trade_explain_path and not trade_explain_path.is_absolute():
        trade_explain_path = Path(reports_root) / trade_explain_path
    trade_explain_obj = _read_json_dict(trade_explain_path) if str(trade_explain_path) else {}
    route_summary = trade_explain_obj.get("route_summary") if isinstance(trade_explain_obj.get("route_summary"), dict) else {}
    route_selected_total = route_summary.get("route_selected_total") if isinstance(route_summary.get("route_selected_total"), dict) else {}
    route_selected_total = {str(k): _safe_int(v, 0) for k, v in dict(route_selected_total or {}).items() if str(k or "").strip()}
    total = sum(int(v) for v in route_selected_total.values())

    def _ratio(name: str) -> float:
        if total <= 0:
            return 0.0
        return round(float(_safe_int(route_selected_total.get(name), 0)) / float(total), 4)

    return {
        "route_selected_total": route_selected_total,
        "monitor_only_ratio": _ratio("monitor_only"),
        "cached_strategist_ratio": _ratio("cached_strategist"),
        "full_cycle_ratio": _ratio("full_cycle"),
        "route_source": str(route_summary.get("route_source") or ""),
    }


def _load_reporter_analysis_digest(reports_root: Path, day: str) -> Dict[str, Any]:
    report_path = (
        Path(reports_root)
        / "dev"
        / "analysis"
        / "reporter_analysis"
        / f"reporter_analysis_{str(day or '').strip()}.json"
    )
    report = _read_json_dict(report_path)
    if not report:
        return {
            "available": False,
            "status": "missing",
            "ai_run_grade": "",
            "ai_summary": "",
            "top_improvement_suggestions": [],
            "recommended_actions": [],
            "dominant_risks": [],
            "system_health": "",
            "report_focus_targets": [],
            "scanner_selection_status": "",
            "monitor_status": "",
            "top_monitor_reasons": [],
            "top_scanner_sources": [],
            "top_supervisor_blockers": [],
            "incident_total": 0,
            "artifact_path": str(report_path),
        }

    operator_summary = report.get("operator_facing_summary") if isinstance(report.get("operator_facing_summary"), dict) else {}
    scanner_evaluation = report.get("scanner_evaluation") if isinstance(report.get("scanner_evaluation"), dict) else {}
    monitor_evaluation = report.get("monitor_evaluation") if isinstance(report.get("monitor_evaluation"), dict) else {}
    supervisor_activity = report.get("supervisor_activity") if isinstance(report.get("supervisor_activity"), dict) else {}
    incidents = report.get("incident_postmortem") if isinstance(report.get("incident_postmortem"), dict) else {}
    route_mix = _extract_route_mix_digest(report, reports_root)
    recommended_actions = [str(x or "") for x in list(operator_summary.get("recommended_actions") or []) if str(x or "").strip()][:3]
    dominant_risks = [str(x or "") for x in list((report.get("ai_root_causes") or report.get("improvement_suggestions") or [])) if str(x or "").strip()][:3]
    top_improvements = [str(x or "") for x in list((report.get("ai_improvement_suggestions") or report.get("improvement_suggestions") or [])) if str(x or "").strip()][:3]
    return {
        "available": True,
        "status": "ok",
        "ai_run_grade": str(report.get("ai_run_grade") or ""),
        "ai_summary": str(report.get("ai_summary") or "")[:280],
        "top_improvement_suggestions": top_improvements,
        "recommended_actions": recommended_actions,
        "dominant_risks": dominant_risks,
        "system_health": str(operator_summary.get("system_health") or "").strip(),
        "report_focus_targets": [
            str(x or "").strip()
            for x in list(report.get("report_focus_targets") or [])
            if str(x or "").strip()
        ][:4],
        "scanner_selection_status": str(scanner_evaluation.get("selection_status") or "").strip(),
        "monitor_status": str(monitor_evaluation.get("monitor_status") or "").strip(),
        "top_monitor_reasons": _top_counter_keys(monitor_evaluation.get("monitor_reason_top"), limit=4),
        "top_scanner_sources": _top_counter_keys(scanner_evaluation.get("candidate_source_top"), limit=3),
        "top_supervisor_blockers": _top_counter_keys(supervisor_activity.get("blocked_reason_top"), limit=3),
        "incident_total": int(float(incidents.get("incident_total") or 0)),
        "route_mix": route_mix,
        "artifact_path": str(report_path),
    }


def _list_unique(values: List[str], *, limit: int = 8) -> List[str]:
    out: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in out:
            continue
        out.append(text)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _recent_patterns_from_playbooks(playbooks: Dict[str, Any], *, success: bool) -> List[str]:
    rows: List[tuple[str, float, float, float]] = []
    for name, payload in dict(playbooks or {}).items():
        item = payload if isinstance(payload, dict) else {}
        win_rate = _safe_float(item.get("win_rate"), 0.0)
        avg_return = _safe_float(item.get("avg_return"), 0.0)
        stability = _safe_float(item.get("stability_score"), 0.0)
        rows.append((str(name), win_rate, avg_return, stability))
    if success:
        rows.sort(key=lambda row: (-row[3], -row[2], -row[1], row[0]))
        selected = [name for name, win_rate, avg_return, _ in rows if win_rate >= 0.5 and avg_return >= 0.0]
    else:
        rows.sort(key=lambda row: (row[2], row[1], row[3], row[0]))
        selected = [name for name, win_rate, avg_return, _ in rows if win_rate <= 0.4 or avg_return < 0.0]
    return _list_unique(selected, limit=4)


def build_strategy_memory(
    summary: Dict[str, Any],
    playbook_stats: Dict[str, Any],
    reporter_analysis_digest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    summary_obj = dict(summary or {})
    playbooks = (
        playbook_stats.get("playbooks")
        if isinstance(playbook_stats.get("playbooks"), dict)
        else {}
    )
    playbook_rows: List[tuple[str, float, float, float]] = []
    for name, payload in dict(playbooks).items():
        item = payload if isinstance(payload, dict) else {}
        playbook_rows.append(
            (
                str(name),
                _safe_float(item.get("stability_score"), 0.0),
                _safe_float(item.get("avg_return"), 0.0),
                _safe_float(item.get("win_rate"), 0.0),
            )
        )
    playbook_rows.sort(key=lambda row: (-row[1], -row[2], -row[3], row[0]))
    best_playbooks = [row[0] for row in playbook_rows[:3] if row[0] and row[0] != "unknown"]
    worst_playbooks = [row[0] for row in sorted(playbook_rows, key=lambda row: (row[2], row[3], row[1], row[0]))[:3] if row[0] and row[0] != "unknown"]
    playbook_performance_snapshot: Dict[str, Any] = {}
    for name, _stability, _avg_return, _win_rate in playbook_rows[:4]:
        src = playbooks.get(name) if isinstance(playbooks.get(name), dict) else {}
        playbook_performance_snapshot[str(name)] = {
            "usage_count": int(float(src.get("usage_count") or 0)),
            "win_rate": _safe_float(src.get("win_rate"), 0.0),
            "avg_return": _safe_float(src.get("avg_return"), 0.0),
            "stability_score": _safe_float(src.get("stability_score"), 0.0),
        }

    regime_stats = (
        summary_obj.get("per_market_regime_stats")
        if isinstance(summary_obj.get("per_market_regime_stats"), dict)
        else {}
    )
    regime_bias: Dict[str, Any] = {}
    for regime, payload in regime_stats.items():
        item = payload if isinstance(payload, dict) else {}
        regime_bias[str(regime)] = {
            "win_rate": _safe_float(item.get("win_rate"), 0.0),
            "avg_return": _safe_float(item.get("avg_return"), 0.0),
            "trade_count": int(float(item.get("trade_count") or 0)),
        }

    success_patterns = _recent_patterns_from_playbooks(playbooks, success=True)
    failure_patterns = _recent_patterns_from_playbooks(playbooks, success=False)
    market_condition_bias: Dict[str, Any] = {
        "regime_bias": regime_bias,
        "preferred_regimes": [
            name
            for name, payload in sorted(
                regime_bias.items(),
                key=lambda item: (-_safe_float((item[1] or {}).get("avg_return"), 0.0), item[0]),
            )[:2]
            if str(name).strip() and str(name).strip() != "unknown"
        ],
        "avoid_regimes": [
            name
            for name, payload in sorted(
                regime_bias.items(),
                key=lambda item: (_safe_float((item[1] or {}).get("avg_return"), 0.0), item[0]),
            )[:2]
            if str(name).strip() and str(name).strip() != "unknown"
        ],
    }

    return {
        "schema_version": "strategy_memory.v1",
        "generated_at": _utc_now_iso(),
        "best_playbooks": _list_unique(best_playbooks, limit=3),
        "worst_playbooks": _list_unique(worst_playbooks, limit=3),
        "market_condition_bias": market_condition_bias,
        "recent_failures": [f"playbook:{name}" for name in failure_patterns],
        "recent_success_patterns": [f"playbook:{name}" for name in success_patterns],
        "playbook_performance_snapshot": playbook_performance_snapshot,
        "reporter_analysis_digest": dict(reporter_analysis_digest or {}),
        "advisory_only": True,
    }


def write_strategy_memory(
    reports_root: Path,
    *,
    day: str,
    summary: Optional[Dict[str, Any]] = None,
    playbook_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    root = Path(reports_root)
    target_day = str(day or "").strip()
    summary_obj = dict(summary) if isinstance(summary, dict) else aggregate_performance_from_reports_root(root, day=target_day)
    playbook_obj = dict(playbook_stats) if isinstance(playbook_stats, dict) else calculate_playbook_stats(
        [],
        day=target_day,
    )
    reporter_digest = _load_reporter_analysis_digest(root, target_day)
    if not playbook_obj.get("playbooks"):
        playbook_obj = write_playbook_stats(root, day=target_day)
    memory = build_strategy_memory(summary_obj, playbook_obj, reporter_digest)
    memory["day"] = str(target_day or summary_obj.get("day") or playbook_obj.get("day") or "")
    paths = performance_artifact_paths(root, memory["day"])
    paths["root_dir"].mkdir(parents=True, exist_ok=True)
    paths["strategy_memory_json"].write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")
    memory["artifact_path"] = str(paths["strategy_memory_json"])
    return memory


def _resolve_latest_day(performance_root: Path) -> str:
    if not performance_root.exists():
        return ""
    days = [path.name for path in performance_root.iterdir() if path.is_dir()]
    days = [day for day in days if len(day) == 10 and day[4:5] == "-" and day[7:8] == "-"]
    if not days:
        return ""
    return sorted(days)[-1]


def load_strategy_memory_hint(
    *,
    reports_root: Path,
    day: str = "",
    auto_build: bool = False,
) -> Dict[str, Any]:
    root = Path(reports_root)
    performance_root = root / "performance"
    target_day = str(day or "").strip() or _resolve_latest_day(performance_root)
    if not target_day:
        return {
            "schema_version": "strategy_memory.v1",
            "day": "",
            "status": "empty",
            "best_playbooks": [],
            "worst_playbooks": [],
            "market_condition_bias": {},
            "recent_failures": [],
            "recent_success_patterns": [],
            "playbook_performance_snapshot": {},
            "advisory_only": True,
        }
    paths = performance_artifact_paths(root, target_day)
    summary = _read_json_dict(paths["summary_json"])
    playbook = _read_json_dict(paths["playbook_stats_json"])
    memory = _read_json_dict(paths["strategy_memory_json"])
    reporter_digest = _load_reporter_analysis_digest(root, target_day)
    if not summary and auto_build:
        summary = write_performance_summary(root, day=target_day)
    if not playbook and auto_build:
        playbook = write_playbook_stats(root, day=target_day)
    if not memory:
        if summary or playbook:
            memory = build_strategy_memory(summary, playbook, reporter_digest)
            memory["day"] = target_day
        else:
            memory = {
                "schema_version": "strategy_memory.v1",
                "day": target_day,
                "best_playbooks": [],
                "worst_playbooks": [],
                "market_condition_bias": {},
                "recent_failures": [],
                "recent_success_patterns": [],
                "playbook_performance_snapshot": {},
                "reporter_analysis_digest": dict(reporter_digest),
                "advisory_only": True,
            }
    if not isinstance(memory.get("reporter_analysis_digest"), dict) or not (memory.get("reporter_analysis_digest") or {}):
        memory["reporter_analysis_digest"] = dict(reporter_digest)
    memory["status"] = "ok" if (memory.get("best_playbooks") or memory.get("worst_playbooks")) else "empty"
    memory["day"] = target_day
    memory.setdefault("advisory_only", True)
    return memory
