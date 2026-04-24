from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Dict, Iterable, List, Mapping

from libs.runtime.strategy_memory_support_artifacts import (
    average_route_ratio,
    resolve_candidate_source_totals,
    resolve_monitor_reason_totals,
    resolve_monitor_status,
    resolve_regime_observation_counts,
    resolve_report_focus_targets,
    resolve_route_context,
    resolve_scanner_status,
    resolve_scanner_evaluation_context,
    resolve_supervisor_blocker_totals,
    resolve_system_health,
    resolve_top_scanner_sources,
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _parse_day(value: str) -> date | None:
    text = _text(value)
    if len(text) != 10:
        return None
    try:
        return date.fromisoformat(text)
    except Exception:
        return None


def _row_playbook_snapshot(row: Mapping[str, Any]) -> Dict[str, Any]:
    return _mapping(row.get("playbook_performance_snapshot"))


def _row_reporter_digest(row: Mapping[str, Any]) -> Dict[str, Any]:
    return _mapping(row.get("reporter_analysis_digest"))


def _row_market_bias(row: Mapping[str, Any]) -> Dict[str, Any]:
    return _mapping(row.get("market_condition_bias"))


def estimate_row_trade_count(row: Mapping[str, Any]) -> int:
    total = 0
    for payload in _row_playbook_snapshot(row).values():
        item = _mapping(payload)
        total += max(0, _safe_int(item.get("usage_count")))
    return total


def estimate_row_return_pct(row: Mapping[str, Any]) -> float:
    weighted_sum = 0.0
    total_usage = 0
    fallback_returns: List[float] = []
    for payload in _row_playbook_snapshot(row).values():
        item = _mapping(payload)
        usage_count = max(0, _safe_int(item.get("usage_count")))
        avg_return = _safe_float(item.get("avg_return"))
        if usage_count > 0:
            weighted_sum += float(avg_return) * float(usage_count)
            total_usage += usage_count
        fallback_returns.append(float(avg_return))
    if total_usage > 0:
        return weighted_sum / float(total_usage)
    if fallback_returns:
        return sum(fallback_returns) / float(len(fallback_returns))
    return 0.0


def build_sample_quality(
    *,
    rows: Iterable[Mapping[str, Any]],
    requested_day: str,
    resolved_day: str,
    max_days: int,
    min_required_days: int,
) -> Dict[str, Any]:
    row_list = [dict(row) for row in rows]
    sample_day_count = len(row_list)
    trade_count = sum(estimate_row_trade_count(row) for row in row_list)
    filled_trade_count = trade_count
    requested = _parse_day(requested_day)
    resolved = _parse_day(resolved_day)
    max_age_days = max(0, (requested - resolved).days) if requested and resolved else 0
    day_score = min(1.0, float(sample_day_count) / float(max(max_days, 1)))
    trade_score = min(1.0, float(trade_count) / float(max(min_required_days * 3, 1)))
    recency_score = max(0.0, 1.0 - (float(max_age_days) / float(max(max_days, 1))))
    confidence = round((0.5 * day_score) + (0.35 * trade_score) + (0.15 * recency_score), 4)
    usable = sample_day_count >= max(min_required_days, 1) and trade_count >= max(min_required_days, 1)
    return {
        "trade_count": trade_count,
        "filled_trade_count": filled_trade_count,
        "usable": bool(usable),
        "confidence": confidence,
        "max_age_days": max_age_days,
        "sample_day_ratio": round(day_score, 4),
        "trade_density": round(trade_score, 4),
        "min_required_days": min_required_days,
    }


def build_source_performance(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    aggregate: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        day = _text(row.get("day"))
        day_return = estimate_row_return_pct(row)
        scanner_eval = resolve_scanner_evaluation_context(row)
        source_totals = resolve_candidate_source_totals(row)
        source_names = []
        seen_sources = set()
        for source in list(resolve_top_scanner_sources(row)) + list(source_totals.keys()):
            name = _text(source)
            if not name or name in seen_sources:
                continue
            seen_sources.add(name)
            source_names.append(name)
        for source in source_names:
            name = _text(source)
            if not name:
                continue
            source_count = max(1, _safe_int(source_totals.get(name), 1))
            target = aggregate.setdefault(
                name,
                {
                    "sample_days": 0,
                    "mention_count": 0,
                    "source_selection_total": 0,
                    "avg_day_return_pct_estimate_sum": 0.0,
                    "avg_top_score_sum": 0.0,
                    "avg_candidate_pool_sum": 0.0,
                    "selection_status_counts": {},
                    "supporting_days": [],
                },
            )
            target["sample_days"] += 1
            target["mention_count"] += 1
            target["source_selection_total"] += source_count
            target["avg_day_return_pct_estimate_sum"] += float(day_return)
            target["avg_top_score_sum"] += _safe_float(scanner_eval.get("avg_top_score"))
            target["avg_candidate_pool_sum"] += _safe_float(scanner_eval.get("avg_candidate_pool_after_filter"))
            selection_status = _text(scanner_eval.get("selection_status"))
            if selection_status:
                counts = target.setdefault("selection_status_counts", {})
                counts[selection_status] = _safe_int(counts.get(selection_status), 0) + 1
            if day and day not in target["supporting_days"]:
                target["supporting_days"].append(day)
    ranked = sorted(
        aggregate.items(),
        key=lambda item: (
            -_safe_int(item[1].get("source_selection_total")),
            -_safe_int(item[1].get("sample_days")),
            -_safe_int(item[1].get("mention_count")),
            -_safe_float(item[1].get("avg_day_return_pct_estimate_sum")),
            item[0],
        ),
    )
    out: Dict[str, Any] = {}
    for name, stats in ranked[:6]:
        sample_days = max(_safe_int(stats.get("sample_days")), 1)
        avg_estimate = float(stats.get("avg_day_return_pct_estimate_sum") or 0.0) / float(sample_days)
        avg_top_score = float(stats.get("avg_top_score_sum") or 0.0) / float(sample_days)
        avg_candidate_pool = float(stats.get("avg_candidate_pool_sum") or 0.0) / float(sample_days)
        selection_status_counts = _mapping(stats.get("selection_status_counts"))
        selection_status = ""
        if selection_status_counts:
            selection_status = sorted(
                selection_status_counts.items(),
                key=lambda item: (-_safe_int(item[1]), str(item[0])),
            )[0][0]
        signal = "mixed"
        if selection_status.lower() in {"weak", "misaligned", "overfit"}:
            signal = "negative"
        elif avg_estimate >= 0.003:
            signal = "positive"
        elif avg_estimate <= -0.003:
            signal = "negative"
        out[name] = {
            "sample_days": sample_days,
            "mention_count": _safe_int(stats.get("mention_count")),
            "source_selection_total": _safe_int(stats.get("source_selection_total")),
            "avg_day_return_pct_estimate": round(avg_estimate, 6),
            "avg_top_score": round(avg_top_score, 6),
            "avg_candidate_pool_after_filter": round(avg_candidate_pool, 4),
            "selection_status": selection_status,
            "selection_status_counts": selection_status_counts,
            "signal": signal,
            "supporting_days": list(stats.get("supporting_days") or [])[:6],
        }
    return out


def build_failure_patterns(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    failure_counter: Counter[str] = Counter()
    monitor_counter: Counter[str] = Counter()
    blocker_counter: Counter[str] = Counter()
    for row in rows:
        for failure in list(row.get("recent_failures") or []):
            name = _text(failure)
            if name:
                failure_counter[name] += 1
        for reason, count in resolve_monitor_reason_totals(row).items():
            name = _text(reason)
            if name:
                monitor_counter[name] += max(1, _safe_int(count, 1))
        for blocker, count in resolve_supervisor_blocker_totals(row).items():
            name = _text(blocker)
            if name:
                blocker_counter[name] += max(1, _safe_int(count, 1))
    dominant_failures = [name for name, _count in failure_counter.most_common(4)]
    return {
        "dominant_failures": dominant_failures,
        "dominant_monitor_reasons": [name for name, _count in monitor_counter.most_common(4)],
        "dominant_supervisor_blockers": [name for name, _count in blocker_counter.most_common(3)],
        "repeat_failure_count": sum(int(count) for _name, count in failure_counter.items()),
    }


def build_execution_risk(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    health_counter: Counter[str] = Counter()
    scanner_status_counter: Counter[str] = Counter()
    monitor_status_counter: Counter[str] = Counter()
    focus_counter: Counter[str] = Counter()
    route_source_counter: Counter[str] = Counter()
    dominant_risk_counter: Counter[str] = Counter()
    alignment_total: Dict[str, int] = {}
    incident_total = 0
    for row in rows:
        digest = _row_reporter_digest(row)
        health = resolve_system_health(row)
        if health:
            health_counter[health] += 1
        scanner_status = resolve_scanner_status(row)
        if scanner_status:
            scanner_status_counter[scanner_status] += 1
        monitor_status = resolve_monitor_status(row)
        if monitor_status:
            monitor_status_counter[monitor_status] += 1
        for focus in resolve_report_focus_targets(row):
            name = _text(focus)
            if name:
                focus_counter[name] += 1
        route_context = resolve_route_context(row)
        route_source = _text(route_context.get("route_source"))
        if route_source:
            route_source_counter[route_source] += 1
        for key, value in _mapping(route_context.get("alignment_totals")).items():
            name = _text(key)
            if name:
                alignment_total[name] = alignment_total.get(name, 0) + _safe_int(value, 0)
        for risk in list(digest.get("dominant_risks") or []):
            name = _text(risk)
            if name:
                dominant_risk_counter[name] += 1
        incident_total += max(0, _safe_int(digest.get("incident_total")))
    system_health = health_counter.most_common(1)[0][0] if health_counter else ""
    avg_monitor_only_ratio = average_route_ratio(rows, "monitor_only")
    avg_cached_ratio = average_route_ratio(rows, "cached_strategist")
    avg_full_cycle_ratio = average_route_ratio(rows, "full_cycle")
    preferred_posture = "balanced"
    if system_health.upper() == "RED" or avg_monitor_only_ratio >= 0.65:
        preferred_posture = "defensive"
    elif system_health.upper() == "GREEN" and avg_full_cycle_ratio >= 0.18:
        preferred_posture = "opportunistic"
    return {
        "system_health": system_health,
        "scanner_status": scanner_status_counter.most_common(1)[0][0] if scanner_status_counter else "",
        "monitor_status": monitor_status_counter.most_common(1)[0][0] if monitor_status_counter else "",
        "dominant_risks": [name for name, _count in dominant_risk_counter.most_common(4)],
        "incident_total": incident_total,
        "avg_monitor_only_ratio": round(avg_monitor_only_ratio, 4),
        "avg_cached_strategist_ratio": round(avg_cached_ratio, 4),
        "avg_full_cycle_ratio": round(avg_full_cycle_ratio, 4),
        "route_source": route_source_counter.most_common(1)[0][0] if route_source_counter else "",
        "report_focus_targets": [name for name, _count in focus_counter.most_common(5)],
        "alignment_totals": alignment_total,
        "preferred_risk_posture": preferred_posture,
    }


def build_regime_stats(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    aggregate: Dict[str, Dict[str, float]] = {}
    regime_observation_counts: Counter[str] = Counter()
    for row in rows:
        for regime, count in resolve_regime_observation_counts(row).items():
            name = _text(regime)
            if name:
                regime_observation_counts[name] += _safe_int(count, 0)
        regime_bias = _mapping(_row_market_bias(row).get("regime_bias"))
        for name, payload in regime_bias.items():
            regime = _text(name)
            if not regime:
                continue
            item = _mapping(payload)
            trade_count = max(0, _safe_int(item.get("trade_count")))
            weight = float(trade_count or 1)
            target = aggregate.setdefault(
                regime,
                {
                    "weighted_trade_count": 0.0,
                    "weighted_win_rate_sum": 0.0,
                    "weighted_avg_return_sum": 0.0,
                    "sample_days": 0.0,
                },
            )
            target["weighted_trade_count"] += weight
            target["weighted_win_rate_sum"] += _safe_float(item.get("win_rate")) * weight
            target["weighted_avg_return_sum"] += _safe_float(item.get("avg_return")) * weight
            target["sample_days"] += 1.0
    ranked = sorted(
        aggregate.items(),
        key=lambda item: (
            -(
                item[1]["weighted_avg_return_sum"]
                / max(item[1]["weighted_trade_count"], 1.0)
            ),
            item[0],
        ),
    )
    regime_stats: Dict[str, Any] = {}
    for regime, stats in ranked[:6]:
        weighted_trade_count = max(stats["weighted_trade_count"], 1.0)
        regime_stats[regime] = {
            "trade_count": int(round(stats["weighted_trade_count"])),
            "sample_days": int(round(stats["sample_days"])),
            "win_rate": round(stats["weighted_win_rate_sum"] / weighted_trade_count, 6),
            "avg_return_pct": round(stats["weighted_avg_return_sum"] / weighted_trade_count, 6),
            "observation_count": _safe_int(regime_observation_counts.get(regime), 0),
        }
    return regime_stats


def build_recommended_bias_inputs(
    *,
    layer: str,
    best_playbooks: List[str],
    worst_playbooks: List[str],
    source_performance: Mapping[str, Any],
    failure_patterns: Mapping[str, Any],
    execution_risk: Mapping[str, Any],
) -> Dict[str, Any]:
    if layer == "daily":
        min_source_days = 1
    elif layer == "weekly":
        min_source_days = 2
    else:
        min_source_days = 3
    source_weight_delta: Dict[str, float] = {}
    for source, payload in source_performance.items():
        item = _mapping(payload)
        sample_days = _safe_int(item.get("sample_days"))
        avg_return = _safe_float(item.get("avg_day_return_pct_estimate"))
        if sample_days < min_source_days:
            continue
        delta = 0.0
        if avg_return >= 0.005:
            delta = 0.1 if layer == "monthly" else 0.08
        elif avg_return >= 0.002:
            delta = 0.06 if layer == "monthly" else 0.05
        elif avg_return <= -0.005:
            delta = -0.14 if layer == "monthly" else -0.12
        elif avg_return <= -0.002:
            delta = -0.08 if layer == "monthly" else -0.06
        if abs(delta) > 1e-9:
            source_weight_delta[str(source)] = round(delta, 4)
    dominant_failures = [str(x or "").strip().lower() for x in list(failure_patterns.get("dominant_failures") or [])]
    dominant_monitor = [str(x or "").strip().lower() for x in list(failure_patterns.get("dominant_monitor_reasons") or [])]
    monitor_delta: Dict[str, float] = {}
    if any("too_extended_from_vwap" in item for item in dominant_failures):
        monitor_delta["max_extended_from_vwap_pct_delta"] = -0.01
    if any("volume" in item for item in dominant_failures + dominant_monitor):
        monitor_delta["volume_ratio_min_delta"] = 0.03
    if any("breakout" in item for item in dominant_failures + dominant_monitor):
        monitor_delta["breakout_buffer_pct_delta"] = 0.0005
    preferred_risk_posture = _text(execution_risk.get("preferred_risk_posture")) or "balanced"
    if _text(execution_risk.get("scanner_status")).lower() in {"weak", "overfit", "misaligned"}:
        source_weight_delta.setdefault("top_change_rate", -0.08)
    return {
        "scanner": {
            "source_weight_delta": source_weight_delta,
            "prefer_playbooks": best_playbooks[:2],
            "avoid_playbooks": worst_playbooks[:2],
        },
        "monitor": {
            "dominant_blockers": [item for item in list(failure_patterns.get("dominant_failures") or [])[:3] if _text(item)],
            **monitor_delta,
        },
        "commander": {
            "preferred_risk_posture": preferred_risk_posture,
            "bias_confidence_hint": "high" if preferred_risk_posture == "defensive" else "normal",
            "report_focus_targets": [str(x or "") for x in list(execution_risk.get("report_focus_targets") or [])[:4] if _text(x)],
        },
    }


def build_window_summary(
    *,
    layer: str,
    contributing_days: List[str],
    best_playbooks: List[str],
    worst_playbooks: List[str],
    failure_patterns: Mapping[str, Any],
    source_performance: Mapping[str, Any],
    execution_risk: Mapping[str, Any],
) -> Dict[str, Any]:
    resolved_day = contributing_days[-1] if contributing_days else ""
    headline = (
        f"{layer} memory aggregated from {len(contributing_days)} performance days"
        + (f" ending {resolved_day}." if resolved_day else ".")
    )
    top_source = next(iter(source_performance.keys()), "")
    top_failure = next(iter(list(failure_patterns.get("dominant_failures") or [])), "")
    system_health = _text(execution_risk.get("system_health"))
    route_source = _text(execution_risk.get("route_source"))
    report_focus_targets = [str(x or "") for x in list(execution_risk.get("report_focus_targets") or []) if _text(x)]
    bullets = [
        f"preferred playbooks: {', '.join(best_playbooks[:2]) or 'none'}",
        f"avoid playbooks: {', '.join(worst_playbooks[:2]) or 'none'}",
        f"dominant failure: {top_failure or 'none'}",
    ]
    if top_source:
        bullets.append(f"top scanner source signal: {top_source}")
    if system_health:
        bullets.append(f"reporter system health baseline: {system_health}")
    if route_source:
        bullets.append(f"route source baseline: {route_source}")
    if report_focus_targets:
        bullets.append(f"report focus carry-over: {', '.join(report_focus_targets[:3])}")
    return {
        "headline": headline,
        "bullets": bullets[:6],
    }


__all__ = [
    "build_execution_risk",
    "build_failure_patterns",
    "build_recommended_bias_inputs",
    "build_regime_stats",
    "build_sample_quality",
    "build_source_performance",
    "build_window_summary",
    "estimate_row_trade_count",
]
