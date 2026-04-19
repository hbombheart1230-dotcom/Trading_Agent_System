from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


def _normalize_day(day: Optional[str]) -> str:
    return str(day or "").strip()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_total(counter_like: Mapping[str, Any] | None) -> int:
    total = 0
    if not isinstance(counter_like, Mapping):
        return 0
    for value in counter_like.values():
        total += _safe_int(value, 0)
    return total


def _ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(float(count) / float(total), 4)


def _extract_route_summary(payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    row = dict(payload or {})
    nested = row.get("route_summary") if isinstance(row.get("route_summary"), dict) else {}
    route_selected_total = nested.get("route_selected_total")
    strategy_generation_mode_total = nested.get("strategy_generation_mode_total")
    strategist_fallback_total = nested.get("strategist_fallback_total")
    if not isinstance(route_selected_total, dict):
        route_selected_total = row.get("route_selected_total") if isinstance(row.get("route_selected_total"), dict) else {}
    if not isinstance(strategy_generation_mode_total, dict):
        strategy_generation_mode_total = row.get("strategist_mode_total") if isinstance(row.get("strategist_mode_total"), dict) else {}
    if strategist_fallback_total is None:
        strategist_fallback_total = row.get("strategist_fallback_total")
    return {
        "route_source": str(nested.get("route_source") or row.get("route_source") or "unavailable"),
        "route_source_run_count": _safe_int(nested.get("route_source_run_count") or row.get("route_source_run_count"), 0),
        "route_source_missing_count": _safe_int(nested.get("route_source_missing_count") or row.get("route_source_missing_count"), 0),
        "route_source_breakdown": dict(nested.get("route_source_breakdown") or row.get("route_source_breakdown") or {}),
        "route_selected_total": dict(route_selected_total or {}),
        "strategy_generation_mode_total": dict(strategy_generation_mode_total or {}),
        "strategist_fallback_total": _safe_int(strategist_fallback_total, 0),
    }


def _extract_blocker_totals(payload: Mapping[str, Any] | None) -> Dict[str, int]:
    row = dict(payload or {})
    direct = row.get("dominant_blocker_total") if isinstance(row.get("dominant_blocker_total"), dict) else {}
    if direct:
        return {str(k): _safe_int(v, 0) for k, v in direct.items()}
    no_trade = row.get("no_trade_summary") if isinstance(row.get("no_trade_summary"), dict) else {}
    topn = list(no_trade.get("dominant_blocker_topN") or [])
    totals: Dict[str, int] = {}
    for item in topn:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or "").strip()
        if not reason:
            continue
        totals[reason] = _safe_int(item.get("count"), 0)
    return totals


def _extract_freshness(payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    row = dict(payload or {})
    freshness = row.get("data_freshness") if isinstance(row.get("data_freshness"), dict) else {}
    if freshness:
        return dict(freshness)
    generated_at = str(row.get("generated_at") or "")
    return {
        "generated_at": generated_at,
        "source_run_count": _safe_int(row.get("source_run_count"), 0),
        "latest_run_id": str(row.get("latest_run_id") or ""),
        "latest_run_ts": str(row.get("latest_run_ts") or ""),
        "freshness_status": "unknown" if not generated_at else "fresh",
        "stale": False,
        "stale_reason": "source_not_declared" if not generated_at else "aligned_with_source_window",
        "source_window_summary": "",
    }


def _metrics_report_path(reports_root: Path, day: str) -> Path:
    return reports_root / "metrics" / f"metrics_{day}.json"


def _build_dominant_patterns(
    *,
    route_summary: Mapping[str, Any],
    blocker_totals: Mapping[str, int],
    freshness: Mapping[str, Any],
) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    route_total = _safe_total(route_summary.get("route_selected_total") if isinstance(route_summary.get("route_selected_total"), dict) else {})
    route_selected_total = route_summary.get("route_selected_total") if isinstance(route_summary.get("route_selected_total"), dict) else {}
    if route_total > 0:
        for name in ("monitor_only", "cached_strategist", "full_cycle"):
            count = _safe_int(route_selected_total.get(name), 0)
            if count <= 0:
                continue
            patterns.append(
                {
                    "name": f"{name}_ratio",
                    "value": _ratio(count, route_total),
                    "detail": f"{name} {count}/{route_total} runs",
                }
            )

    blocker_total = _safe_total(blocker_totals)
    reclaim_total = sum(count for name, count in blocker_totals.items() if "reclaim" in str(name))
    if reclaim_total > 0 and blocker_total > 0:
        patterns.append(
            {
                "name": "reclaim_blocked_ratio",
                "value": _ratio(reclaim_total, blocker_total),
                "detail": f"reclaim-related blockers {reclaim_total}/{blocker_total}",
            }
        )

    fallback_total = _safe_int(route_summary.get("strategist_fallback_total"), 0)
    if fallback_total > 0 and route_total > 0:
        patterns.append(
            {
                "name": "strategist_fallback_ratio",
                "value": _ratio(fallback_total, route_total),
                "detail": f"fallback observed in {fallback_total}/{route_total} route-tagged runs",
            }
        )

    if freshness:
        patterns.append(
            {
                "name": "freshness_status",
                "value": str(freshness.get("freshness_status") or "unknown"),
                "detail": str(freshness.get("source_window_summary") or ""),
            }
        )
    return patterns[:6]


def _build_blocker_analysis(blocker_totals: Mapping[str, int]) -> list[dict[str, Any]]:
    total = _safe_total(blocker_totals)
    ranked = sorted(((str(name), _safe_int(count, 0)) for name, count in blocker_totals.items()), key=lambda item: (-item[1], item[0]))
    out: list[dict[str, Any]] = []
    for name, count in ranked[:5]:
        out.append(
            {
                "blocker": name,
                "count": count,
                "ratio": _ratio(count, total),
            }
        )
    return out


def _build_route_analysis(route_summary: Mapping[str, Any]) -> Dict[str, Any]:
    route_selected_total = dict(route_summary.get("route_selected_total") or {})
    route_total = _safe_total(route_selected_total)
    return {
        "route_source": str(route_summary.get("route_source") or "unavailable"),
        "route_selected_total": route_selected_total,
        "strategy_generation_mode_total": dict(route_summary.get("strategy_generation_mode_total") or {}),
        "strategist_fallback_total": _safe_int(route_summary.get("strategist_fallback_total"), 0),
        "route_source_run_count": _safe_int(route_summary.get("route_source_run_count"), 0),
        "route_source_missing_count": _safe_int(route_summary.get("route_source_missing_count"), 0),
        "route_source_breakdown": dict(route_summary.get("route_source_breakdown") or {}),
        "monitor_only_ratio": _ratio(_safe_int(route_selected_total.get("monitor_only"), 0), route_total),
        "cached_strategist_ratio": _ratio(_safe_int(route_selected_total.get("cached_strategist"), 0), route_total),
        "full_cycle_ratio": _ratio(_safe_int(route_selected_total.get("full_cycle"), 0), route_total),
    }


def _build_recommendations(
    *,
    route_analysis: Mapping[str, Any],
    blocker_analysis: list[dict[str, Any]],
) -> list[str]:
    recommendations: list[str] = []
    if float(route_analysis.get("monitor_only_ratio") or 0.0) >= 0.5:
        recommendations.append("Monitor-only share is high; review hold-management concentration before widening entry tuning.")
    if float(route_analysis.get("cached_strategist_ratio") or 0.0) >= 0.25:
        recommendations.append("Cached strategist reuse is elevated; compare refresh cadence against fresh full-cycle opportunities.")
    if blocker_analysis:
        top_blocker = blocker_analysis[0]
        blocker_name = str(top_blocker.get("blocker") or "")
        if blocker_name:
            recommendations.append(f"Top blocker is {blocker_name}; inspect whether this gate is dominating no-trade outcomes.")
        if "reclaim" in blocker_name:
            recommendations.append("VWAP reclaim-related failures are prominent; review reclaim readiness evidence before loosening thresholds.")
    if not recommendations:
        recommendations.append("Route and blocker mix look balanced; continue observing for stable multi-session patterns before changing strategy.")
    return recommendations[:4]


def _build_insight_summary(
    *,
    route_analysis: Mapping[str, Any],
    blocker_analysis: list[dict[str, Any]],
) -> str:
    parts: list[str] = []
    route_total = _safe_total(route_analysis.get("route_selected_total") if isinstance(route_analysis.get("route_selected_total"), dict) else {})
    if route_total > 0:
        monitor_only = _safe_int((route_analysis.get("route_selected_total") or {}).get("monitor_only"), 0) if isinstance(route_analysis.get("route_selected_total"), dict) else 0
        cached = _safe_int((route_analysis.get("route_selected_total") or {}).get("cached_strategist"), 0) if isinstance(route_analysis.get("route_selected_total"), dict) else 0
        parts.append(f"Route mix is led by monitor_only {monitor_only}/{route_total} and cached_strategist {cached}/{route_total}.")
    if blocker_analysis:
        top = blocker_analysis[0]
        parts.append(f"Top blocker is {top.get('blocker')} ({top.get('count')}).")
    if not parts:
        parts.append("Feedback packet is available but source evidence is limited.")
    return " ".join(parts)


def _build_confidence(
    *,
    route_analysis: Mapping[str, Any],
    blocker_analysis: list[dict[str, Any]],
) -> str:
    route_total = _safe_total(route_analysis.get("route_selected_total") if isinstance(route_analysis.get("route_selected_total"), dict) else {})
    if route_total >= 50 and len(blocker_analysis) >= 3:
        return "high"
    if route_total >= 10:
        return "medium"
    return "low"


def build_strategist_feedback_packet(
    *,
    mode: str,
    payload: Mapping[str, Any] | None,
    reports_root: str | Path,
    day: Optional[str] = None,
) -> Dict[str, Any]:
    row = dict(payload or {})
    root = Path(str(reports_root))
    normalized_day = _normalize_day(day or row.get("day"))

    metrics_payload = row if str(mode or "") == "metrics_report" else {}
    trade_explain_payload = row if str(mode or "") == "trade_explain" else {}
    if normalized_day:
        if not metrics_payload:
            metrics_payload = _read_json(_metrics_report_path(root, normalized_day))

    route_summary = _extract_route_summary(row)
    metrics_route_summary = _extract_route_summary(metrics_payload)
    trade_route_summary = _extract_route_summary(trade_explain_payload)
    if not route_summary.get("route_selected_total"):
        route_summary = metrics_route_summary if metrics_route_summary.get("route_selected_total") else trade_route_summary

    blocker_totals = _extract_blocker_totals(metrics_payload)
    if not blocker_totals:
        blocker_totals = _extract_blocker_totals(trade_explain_payload)
    if not blocker_totals:
        blocker_totals = _extract_blocker_totals(row)

    freshness = _extract_freshness(row)
    if not freshness.get("latest_run_id"):
        freshness = _extract_freshness(metrics_payload) if metrics_payload else freshness
    if not freshness.get("latest_run_id"):
        freshness = _extract_freshness(trade_explain_payload) if trade_explain_payload else freshness

    route_analysis = _build_route_analysis(route_summary)
    blocker_analysis = _build_blocker_analysis(blocker_totals)
    dominant_patterns = _build_dominant_patterns(
        route_summary=route_summary,
        blocker_totals=blocker_totals,
        freshness=freshness,
    )
    recommendations = _build_recommendations(route_analysis=route_analysis, blocker_analysis=blocker_analysis)
    confidence = _build_confidence(route_analysis=route_analysis, blocker_analysis=blocker_analysis)

    return {
        "available": bool(route_analysis.get("route_selected_total")) or bool(blocker_analysis),
        "packet_version": "strategist_feedback.v1",
        "feedback_mode": "deterministic",
        "source_mode": str(mode or ""),
        "source_reports": {
            "metrics": bool(metrics_payload),
            "trade_explain": bool(trade_explain_payload),
            "current_payload": bool(row),
        },
        "insight_summary": _build_insight_summary(route_analysis=route_analysis, blocker_analysis=blocker_analysis),
        "dominant_patterns": dominant_patterns,
        "blocker_analysis": blocker_analysis,
        "route_analysis": route_analysis,
        "recommendation": recommendations,
        "confidence": confidence,
        "data_freshness": freshness,
        "runtime_semantics_unchanged": True,
    }
