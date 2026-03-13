from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from .strategy_memory_store import load_recent_strategy_feedback


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _append_unique(out: List[str], value: Any, *, limit: int = 8) -> None:
    text = str(value or "").strip()
    if not text or text in out:
        return
    if len(out) >= int(limit):
        return
    out.append(text)


def aggregate_theme_performance(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for record in records:
        strategist_eval = record.get("strategist_evaluation") if isinstance(record.get("strategist_evaluation"), dict) else {}
        themes = strategist_eval.get("themes_proposed") if isinstance(strategist_eval.get("themes_proposed"), list) else []
        alignment = str(strategist_eval.get("theme_alignment_status") or "").strip().lower()
        performance = record.get("performance_summary") if isinstance(record.get("performance_summary"), dict) else {}
        pnl = _safe_float(performance.get("estimated_realized_pnl_total"), 0.0)
        for theme in themes:
            name = str(theme or "").strip().lower()
            if not name:
                continue
            bucket = buckets.setdefault(
                name,
                {
                    "appearance_count": 0,
                    "win_count": 0,
                    "alignment_count": 0,
                    "pnl_total": 0.0,
                    "trade_count_total": 0,
                },
            )
            bucket["appearance_count"] += 1
            bucket["trade_count_total"] += _safe_int((record.get("trade_summary") or {}).get("trade_count"), 0)
            bucket["pnl_total"] += pnl
            if pnl > 0:
                bucket["win_count"] += 1
            if alignment == "aligned":
                bucket["alignment_count"] += 1

    out: Dict[str, Dict[str, Any]] = {}
    for theme, bucket in buckets.items():
        appearances = max(1, _safe_int(bucket.get("appearance_count"), 1))
        out[theme] = {
            "appearance_count": int(appearances),
            "win_rate": round(_safe_int(bucket.get("win_count"), 0) / appearances, 4),
            "avg_return": round(_safe_float(bucket.get("pnl_total"), 0.0) / appearances, 6),
            "alignment_rate": round(_safe_int(bucket.get("alignment_count"), 0) / appearances, 4),
            "trade_count_total": int(_safe_int(bucket.get("trade_count_total"), 0)),
        }
    return dict(sorted(out.items(), key=lambda kv: (-_safe_int(kv[1].get("appearance_count"), 0), kv[0]))[:8])


def aggregate_playbook_performance(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for record in records:
        frame = record.get("strategy_frame_summary") if isinstance(record.get("strategy_frame_summary"), dict) else {}
        playbook_counts = frame.get("playbook_top") if isinstance(frame.get("playbook_top"), dict) else {}
        performance = record.get("performance_summary") if isinstance(record.get("performance_summary"), dict) else {}
        pnl = _safe_float(performance.get("estimated_realized_pnl_total"), 0.0)
        for playbook, count in playbook_counts.items():
            name = str(playbook or "").strip().lower()
            if not name:
                continue
            bucket = buckets.setdefault(name, {"appearance_count": 0, "win_count": 0, "pnl_total": 0.0})
            bucket["appearance_count"] += _safe_int(count, 0)
            bucket["pnl_total"] += pnl
            if pnl > 0:
                bucket["win_count"] += 1
    out: Dict[str, Dict[str, Any]] = {}
    for playbook, bucket in buckets.items():
        appearances = max(1, _safe_int(bucket.get("appearance_count"), 1))
        out[playbook] = {
            "appearance_count": int(appearances),
            "win_rate": round(_safe_int(bucket.get("win_count"), 0) / appearances, 4),
            "avg_return": round(_safe_float(bucket.get("pnl_total"), 0.0) / appearances, 6),
        }
    return dict(sorted(out.items(), key=lambda kv: (-_safe_int(kv[1].get("appearance_count"), 0), kv[0]))[:8])


def aggregate_monitor_issues(records: List[Dict[str, Any]]) -> List[str]:
    issues: List[str] = []
    for record in records:
        monitor = record.get("monitor_evaluation") if isinstance(record.get("monitor_evaluation"), dict) else {}
        if str(monitor.get("monitor_status") or "") == "overtrading_risk":
            _append_unique(issues, "overtrading risk persisted in recent monitor runs")
        if _safe_int(monitor.get("rapid_buy_sell_cycles"), 0) > 0:
            _append_unique(issues, "rapid buy/sell cycles were observed in recent runs")
        if _safe_int(monitor.get("min_hold_blocked_total"), 0) > 0:
            _append_unique(issues, "min-hold protection blocked exits in recent runs")
        if _safe_int(monitor.get("sell_cooldown_blocked_total"), 0) > 0:
            _append_unique(issues, "sell cooldown blocked repeat exits in recent runs")
        _append_unique(issues, monitor.get("assessment"))
    return issues[:8]


def aggregate_scanner_issues(records: List[Dict[str, Any]]) -> List[str]:
    issues: List[str] = []
    for record in records:
        scanner = record.get("scanner_evaluation") if isinstance(record.get("scanner_evaluation"), dict) else {}
        if str(scanner.get("selection_status") or "") == "needs_review":
            _append_unique(issues, "scanner selection quality needs review in recent runs")
        if _safe_int(scanner.get("no_candidate_total"), 0) > 0:
            _append_unique(issues, "scanner produced no-candidate outcomes in recent runs")
        source_top = scanner.get("candidate_source_top") if isinstance(scanner.get("candidate_source_top"), dict) else {}
        if len(source_top) == 1 and "kiwoom_market_data" in source_top:
            _append_unique(issues, "scanner candidate sourcing remained concentrated in a single Kiwoom source family")
        _append_unique(issues, scanner.get("assessment"))
    return issues[:8]


def aggregate_overtrading_patterns(records: List[Dict[str, Any]]) -> List[str]:
    patterns: List[str] = []
    for record in records:
        incidents = record.get("incidents") if isinstance(record.get("incidents"), list) else []
        for incident in incidents:
            if not isinstance(incident, dict):
                continue
            text = str(incident.get("type") or "").strip()
            if text:
                _append_unique(patterns, text)
        ai_causes = record.get("ai_root_causes") if isinstance(record.get("ai_root_causes"), list) else []
        for cause in ai_causes:
            cause_text = str(cause or "").strip()
            if "overtrad" in cause_text.lower() or "rapid" in cause_text.lower():
                _append_unique(patterns, cause_text)
    return patterns[:8]


def _aggregate_guard_patterns(records: List[Dict[str, Any]]) -> List[str]:
    counts: Counter[str] = Counter()
    for record in records:
        supervisor = record.get("supervisor_activity") if isinstance(record.get("supervisor_activity"), dict) else {}
        blocked_top = supervisor.get("blocked_reason_top") if isinstance(supervisor.get("blocked_reason_top"), dict) else {}
        for reason, count in blocked_top.items():
            text = str(reason or "").strip()
            if text:
                counts[text] += _safe_int(count, 0)
    return [reason for reason, _ in counts.most_common(8)]


def _recent_reporter_summary(records: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for record in records:
        summary = record.get("operator_facing_summary") if isinstance(record.get("operator_facing_summary"), dict) else {}
        for row in list(summary.get("summary_lines") or []):
            _append_unique(lines, row, limit=8)
    return lines[:8]


def _top_strengths(records: List[Dict[str, Any]]) -> List[str]:
    strengths: List[str] = []
    for record in records:
        strategist = record.get("strategist_evaluation") if isinstance(record.get("strategist_evaluation"), dict) else {}
        supervisor = record.get("supervisor_activity") if isinstance(record.get("supervisor_activity"), dict) else {}
        monitor = record.get("monitor_evaluation") if isinstance(record.get("monitor_evaluation"), dict) else {}
        if str(strategist.get("theme_alignment_status") or "") == "aligned":
            _append_unique(strengths, "strategist theme alignment was recently validated")
        if _safe_float(supervisor.get("blocked_rate"), 1.0) < 0.2:
            _append_unique(strengths, "supervisor block rate stayed low in recent runs")
        if str(monitor.get("monitor_status") or "") == "stable":
            _append_unique(strengths, "monitor flow remained stable under recent guard settings")
    return strengths[:6]


def _top_weaknesses(
    monitor_issues: List[str],
    scanner_issues: List[str],
    guard_patterns: List[str],
    overtrading_patterns: List[str],
) -> List[str]:
    out: List[str] = []
    for item in monitor_issues[:3] + scanner_issues[:3] + guard_patterns[:2] + overtrading_patterns[:2]:
        _append_unique(out, item, limit=8)
    return out[:8]


def _suggested_report_focus(
    monitor_issues: List[str],
    scanner_issues: List[str],
    guard_patterns: List[str],
    overtrading_patterns: List[str],
) -> List[str]:
    focus: List[str] = []
    if monitor_issues:
        _append_unique(focus, "exit_quality", limit=6)
    if scanner_issues:
        _append_unique(focus, "scanner_fit", limit=6)
    if guard_patterns:
        _append_unique(focus, "guard_blocks", limit=6)
    if overtrading_patterns:
        _append_unique(focus, "overtrading", limit=6)
    if not focus:
        _append_unique(focus, "theme_accuracy", limit=6)
    return focus[:6]


def build_recent_strategy_feedback(
    last_n_runs: int,
    *,
    path: Optional[str] = None,
    records: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    rows = list(records) if isinstance(records, list) else load_recent_strategy_feedback(last_n_runs, path=path)
    theme_perf = aggregate_theme_performance(rows)
    playbook_perf = aggregate_playbook_performance(rows)
    monitor_issues = aggregate_monitor_issues(rows)
    scanner_issues = aggregate_scanner_issues(rows)
    overtrading_patterns = aggregate_overtrading_patterns(rows)
    guard_patterns = _aggregate_guard_patterns(rows)
    reporter_summary = _recent_reporter_summary(rows)
    strengths = _top_strengths(rows)
    weaknesses = _top_weaknesses(monitor_issues, scanner_issues, guard_patterns, overtrading_patterns)
    report_focus = _suggested_report_focus(monitor_issues, scanner_issues, guard_patterns, overtrading_patterns)

    return {
        "feedback_window_size": int(len(rows)),
        "recent_theme_performance": theme_perf,
        "recent_playbook_performance": playbook_perf,
        "recent_monitor_issues": monitor_issues,
        "recent_scanner_issues": scanner_issues,
        "recent_guard_patterns": guard_patterns,
        "recent_overtrading_patterns": overtrading_patterns,
        "recent_reporter_summary": reporter_summary,
        "top_recent_strengths": strengths,
        "top_recent_weaknesses": weaknesses,
        "suggested_report_focus": report_focus,
        "advisory_only": True,
    }
