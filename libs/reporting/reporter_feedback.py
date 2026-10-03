from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from libs.core.evidence_identity import stable_evidence_id
from libs.reporting.llm_artifacts import iter_trade_dirs, resolve_trade_day_root


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
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


def _reporter_analysis_report_path(reports_root: Path, day: str) -> Path:
    return reports_root / "dev" / "analysis" / "reporter_analysis" / f"reporter_analysis_{day}.json"


def _events_log_candidates(reports_root: Path) -> list[Path]:
    root = Path(reports_root)
    return [
        root.parent / "data" / "logs" / "events.jsonl",
        root / "data" / "logs" / "events.jsonl",
    ]


def _load_or_generate_metrics_payload(reports_root: Path, day: str) -> Dict[str, Any]:
    existing = _read_json(_metrics_report_path(reports_root, day))
    if existing:
        return existing
    for events_path in _events_log_candidates(reports_root):
        if not events_path.exists():
            continue
        try:
            from libs.reporting.metrics_report_generator import generate_metrics_report

            _, js_path = generate_metrics_report(events_path, reports_root / "metrics", day=day)
        except Exception:
            continue
        generated = _read_json(js_path)
        if generated:
            return generated
    return {}


def _trade_report_paths(reports_root: Path, day: str) -> list[Path]:
    trade_root = resolve_trade_day_root(reports_root, day)
    if not trade_root.exists():
        return []
    return sorted(
        path
        for trade_dir in iter_trade_dirs(trade_root)
        for path in [trade_dir / "reports" / "ai_trade_report.json"]
        if path.is_file()
    )


def _build_trade_report_feedback_summary(reports_root: Path, day: str) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "trade_count": 0,
        "closed_trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "flat_count": 0,
        "unknown_pnl_count": 0,
        "avg_pnl_pct": 0.0,
        "pnl_pct_sample_count": 0,
        "same_price_cost_loss_count": 0,
        "broker_truth_count": 0,
        "exit_reason_counts": {},
        "symbols": [],
    }
    symbol_counts: Dict[str, int] = {}
    exit_reason_counts: Dict[str, int] = {}
    pnl_pct_values: list[float] = []

    for path in _trade_report_paths(reports_root, day):
        payload = _read_json(path)
        if not payload:
            continue
        summary["trade_count"] += 1
        truth_surface = dict(payload.get("truth_surface") or {})
        status = dict(truth_surface.get("status") or {})
        price = dict(truth_surface.get("price") or {})
        pnl = dict(truth_surface.get("pnl") or {})
        availability = dict(truth_surface.get("availability") or {})
        if str(status.get("status") or "").strip().lower() != "closed":
            continue

        summary["closed_trade_count"] += 1
        symbol = str(payload.get("symbol") or status.get("symbol") or "").strip()
        if symbol:
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1

        exit_reason = str(status.get("exit_reason") or "").strip()
        if exit_reason:
            exit_reason_counts[exit_reason] = exit_reason_counts.get(exit_reason, 0) + 1

        pnl_value = pnl.get("value")
        pnl_pct = pnl.get("pct")
        pnl_value_known = pnl_value not in (None, "")
        pnl_pct_known = pnl_pct not in (None, "")
        pnl_value_num = _safe_float(pnl_value, 0.0) if pnl_value_known else 0.0
        classification_value = pnl_value_num if pnl_value_known else (_safe_float(pnl_pct, 0.0) if pnl_pct_known else None)
        if classification_value is None:
            summary["unknown_pnl_count"] += 1
        else:
            if classification_value > 0.0:
                summary["win_count"] += 1
            elif classification_value < 0.0:
                summary["loss_count"] += 1
            else:
                summary["flat_count"] += 1
        if pnl_pct_known:
            pnl_pct_values.append(_safe_float(pnl_pct, 0.0))

        if bool(availability.get("broker_fill_present")) and bool(availability.get("broker_pnl_present")):
            summary["broker_truth_count"] += 1

        buy_price = price.get("broker_buy_price")
        sell_price = price.get("broker_fill_price")
        fee = _safe_float(pnl.get("broker_fee"), 0.0)
        tax = _safe_float(pnl.get("broker_tax"), 0.0)
        if (
            buy_price not in (None, "")
            and sell_price not in (None, "")
            and _safe_float(buy_price, 0.0) == _safe_float(sell_price, 0.0)
            and pnl_value_num < 0.0
            and (fee > 0.0 or tax > 0.0)
        ):
            summary["same_price_cost_loss_count"] += 1

    if pnl_pct_values:
        summary["avg_pnl_pct"] = round(sum(pnl_pct_values) / len(pnl_pct_values), 4)
        summary["pnl_pct_sample_count"] = len(pnl_pct_values)
    summary["exit_reason_counts"] = exit_reason_counts
    summary["symbols"] = [name for name, _count in sorted(symbol_counts.items(), key=lambda item: (-item[1], item[0]))[:5]]
    return summary


def _extract_reporter_analysis_blocker_totals(payload: Mapping[str, Any] | None) -> Dict[str, int]:
    row = dict(payload or {})
    monitor_eval = row.get("monitor_evaluation") if isinstance(row.get("monitor_evaluation"), dict) else {}
    supervisor = row.get("supervisor_activity") if isinstance(row.get("supervisor_activity"), dict) else {}
    intent_flow = row.get("intent_flow_analysis") if isinstance(row.get("intent_flow_analysis"), dict) else {}
    totals: Dict[str, int] = {}
    for key, value in dict(monitor_eval.get("monitor_reason_top") or {}).items():
        name = str(key or "").strip()
        if not name:
            continue
        totals[name] = totals.get(name, 0) + _safe_int(value, 0)
    for key, value in dict(supervisor.get("blocked_reason_top") or {}).items():
        name = str(key or "").strip()
        if not name:
            continue
        totals[name] = totals.get(name, 0) + _safe_int(value, 0)
    for key, value in dict(intent_flow.get("reason_top") or {}).items():
        name = str(key or "").strip()
        if not name or name.startswith("monitor:"):
            continue
        totals[name] = totals.get(name, 0) + _safe_int(value, 0)
    return totals


def _extract_reporter_analysis_recommendations(payload: Mapping[str, Any] | None) -> list[str]:
    row = dict(payload or {})
    operator = row.get("operator_facing_summary") if isinstance(row.get("operator_facing_summary"), dict) else {}
    direct = [str(x or "").strip() for x in list(row.get("improvement_suggestions") or []) if str(x or "").strip()]
    if direct:
        return direct[:4]
    recommended = [str(x or "").strip() for x in list(operator.get("recommended_actions") or []) if str(x or "").strip()]
    return recommended[:4]


def _build_dominant_patterns(
    *,
    route_summary: Mapping[str, Any],
    blocker_totals: Mapping[str, int],
    freshness: Mapping[str, Any],
    trade_report_summary: Mapping[str, Any] | None = None,
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
    trade_summary = dict(trade_report_summary or {})
    closed_trade_count = _safe_int(trade_summary.get("closed_trade_count"), 0)
    if closed_trade_count > 0:
        patterns.append(
            {
                "name": "same_day_closed_trade_count",
                "value": closed_trade_count,
                "detail": f"closed trade reports {closed_trade_count}",
            }
        )
        patterns.append(
            {
                "name": "same_day_avg_pnl_pct",
                "value": trade_summary.get("avg_pnl_pct"),
                "detail": f"average same-day pnl pct {trade_summary.get('avg_pnl_pct')}",
            }
        )
        cost_loss_count = _safe_int(trade_summary.get("same_price_cost_loss_count"), 0)
        if cost_loss_count > 0:
            patterns.append(
                {
                    "name": "same_price_cost_loss_ratio",
                    "value": _ratio(cost_loss_count, closed_trade_count),
                    "detail": f"same-price cost-loss trades {cost_loss_count}/{closed_trade_count}",
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
    trade_report_summary: Mapping[str, Any] | None = None,
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
    trade_summary = dict(trade_report_summary or {})
    closed_trade_count = _safe_int(trade_summary.get("closed_trade_count"), 0)
    if closed_trade_count > 0:
        same_price_cost_loss_count = _safe_int(trade_summary.get("same_price_cost_loss_count"), 0)
        win_count = _safe_int(trade_summary.get("win_count"), 0)
        loss_count = _safe_int(trade_summary.get("loss_count"), 0)
        if same_price_cost_loss_count > 0:
            recommendations.append("Same-price round trips produced fee/tax drag; tighten follow-through evidence before repeating quick reversals.")
        if loss_count > win_count:
            recommendations.append("Same-day closed trades are loss-heavy; keep defensive entry posture until follow-through quality improves.")
    if not recommendations:
        recommendations.append("Route and blocker mix look balanced; continue observing for stable multi-session patterns before changing strategy.")
    return recommendations[:4]


def _build_insight_summary(
    *,
    route_analysis: Mapping[str, Any],
    blocker_analysis: list[dict[str, Any]],
    trade_report_summary: Mapping[str, Any] | None = None,
) -> str:
    parts: list[str] = []
    route_total = _safe_total(route_analysis.get("route_selected_total") if isinstance(route_analysis.get("route_selected_total"), dict) else {})
    if route_total > 0:
        route_counts = route_analysis.get("route_selected_total") if isinstance(route_analysis.get("route_selected_total"), dict) else {}
        monitor_only = _safe_int((route_counts or {}).get("monitor_only"), 0)
        cached = _safe_int((route_counts or {}).get("cached_strategist"), 0)
        leader = ""
        leader_count = 0
        if isinstance(route_counts, dict):
            leader, leader_count = max(
                ((str(name), _safe_int(count, 0)) for name, count in route_counts.items()),
                key=lambda item: item[1],
                default=("", 0),
            )
        if leader and leader_count > 0:
            parts.append(
                f"Route mix is led by {leader} {leader_count}/{route_total}; "
                f"monitor_only {monitor_only}/{route_total}, cached_strategist {cached}/{route_total}."
            )
        else:
            parts.append(
                f"Route mix recorded {route_total} routed decisions; "
                f"monitor_only {monitor_only}/{route_total}, cached_strategist {cached}/{route_total}."
            )
    if blocker_analysis:
        top = blocker_analysis[0]
        parts.append(f"Top blocker is {top.get('blocker')} ({top.get('count')}).")
    trade_summary = dict(trade_report_summary or {})
    closed_trade_count = _safe_int(trade_summary.get("closed_trade_count"), 0)
    if closed_trade_count > 0:
        win_count = _safe_int(trade_summary.get("win_count"), 0)
        loss_count = _safe_int(trade_summary.get("loss_count"), 0)
        flat_count = _safe_int(trade_summary.get("flat_count"), 0)
        unknown_pnl_count = _safe_int(trade_summary.get("unknown_pnl_count"), 0)
        avg_pnl_pct = trade_summary.get("avg_pnl_pct")
        pnl_pct_sample_count = _safe_int(trade_summary.get("pnl_pct_sample_count"), 0)
        result_bits = [f"{win_count} wins", f"{loss_count} losses"]
        if flat_count > 0:
            result_bits.append(f"{flat_count} flat")
        if unknown_pnl_count > 0:
            result_bits.append(f"{unknown_pnl_count} unknown pnl")
        avg_text = f", avg pnl pct {avg_pnl_pct}" if pnl_pct_sample_count > 0 else ""
        parts.append(
            f"Same-day closed trade reports show {closed_trade_count} trades with {', '.join(result_bits)}{avg_text}."
        )
    if not parts:
        parts.append("Feedback packet is available but source evidence is limited.")
    return " ".join(parts)


def _build_confidence(
    *,
    route_analysis: Mapping[str, Any],
    blocker_analysis: list[dict[str, Any]],
    trade_report_summary: Mapping[str, Any] | None = None,
) -> str:
    route_total = _safe_total(route_analysis.get("route_selected_total") if isinstance(route_analysis.get("route_selected_total"), dict) else {})
    blocker_total = sum(_safe_int(item.get("count"), 0) for item in list(blocker_analysis or []))
    trade_summary = dict(trade_report_summary or {})
    closed_trade_count = _safe_int(trade_summary.get("closed_trade_count"), 0)
    broker_truth_count = _safe_int(trade_summary.get("broker_truth_count"), 0)
    if route_total >= 50 and len(blocker_analysis) >= 3:
        return "high"
    if route_total >= 10:
        return "medium"
    if closed_trade_count >= 3 and broker_truth_count >= 2:
        return "high"
    if closed_trade_count >= 1 and broker_truth_count >= 1:
        return "medium"
    if blocker_total >= 20 and len(blocker_analysis) >= 2:
        return "high"
    if blocker_total >= 5 and len(blocker_analysis) >= 1:
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
    reporter_analysis_payload = row if str(mode or "") == "reporter_analysis" else {}
    if normalized_day:
        if not metrics_payload:
            metrics_payload = _load_or_generate_metrics_payload(root, normalized_day)
        if not reporter_analysis_payload:
            reporter_analysis_payload = _read_json(_reporter_analysis_report_path(root, normalized_day))
    trade_report_summary = _build_trade_report_feedback_summary(root, normalized_day) if normalized_day else {}

    route_summary = _extract_route_summary(row)
    metrics_route_summary = _extract_route_summary(metrics_payload)
    trade_route_summary = _extract_route_summary(trade_explain_payload)
    reporter_route_summary = _extract_route_summary(reporter_analysis_payload)
    if not route_summary.get("route_selected_total"):
        if metrics_route_summary.get("route_selected_total"):
            route_summary = metrics_route_summary
        elif trade_route_summary.get("route_selected_total"):
            route_summary = trade_route_summary
        else:
            route_summary = reporter_route_summary

    blocker_totals = _extract_blocker_totals(metrics_payload)
    if not blocker_totals:
        blocker_totals = _extract_blocker_totals(trade_explain_payload)
    if not blocker_totals:
        blocker_totals = _extract_reporter_analysis_blocker_totals(reporter_analysis_payload)
    if not blocker_totals:
        blocker_totals = _extract_blocker_totals(row)

    freshness = _extract_freshness(row)
    if not freshness.get("latest_run_id"):
        freshness = _extract_freshness(metrics_payload) if metrics_payload else freshness
    if not freshness.get("latest_run_id"):
        freshness = _extract_freshness(trade_explain_payload) if trade_explain_payload else freshness
    if not freshness.get("latest_run_id"):
        freshness = _extract_freshness(reporter_analysis_payload) if reporter_analysis_payload else freshness

    route_analysis = _build_route_analysis(route_summary)
    blocker_analysis = _build_blocker_analysis(blocker_totals)
    dominant_patterns = _build_dominant_patterns(
        route_summary=route_summary,
        blocker_totals=blocker_totals,
        freshness=freshness,
        trade_report_summary=trade_report_summary,
    )
    recommendations = _build_recommendations(
        route_analysis=route_analysis,
        blocker_analysis=blocker_analysis,
        trade_report_summary=trade_report_summary,
    )
    reporter_analysis_recommendations = _extract_reporter_analysis_recommendations(reporter_analysis_payload)
    if reporter_analysis_recommendations and not metrics_payload:
        recommendations = reporter_analysis_recommendations[:4]
    elif not recommendations or recommendations == ["Route and blocker mix look balanced; continue observing for stable multi-session patterns before changing strategy."]:
        if reporter_analysis_recommendations:
            recommendations = reporter_analysis_recommendations[:4]
    confidence = _build_confidence(
        route_analysis=route_analysis,
        blocker_analysis=blocker_analysis,
        trade_report_summary=trade_report_summary,
    )

    packet = {
        "available": bool(route_analysis.get("route_selected_total")) or bool(blocker_analysis) or _safe_int(trade_report_summary.get("closed_trade_count"), 0) > 0,
        "packet_version": "strategist_feedback.v1",
        "source_day": normalized_day,
        "feedback_mode": "deterministic",
        "source_mode": str(mode or ""),
        "source_reports": {
            "metrics": bool(metrics_payload),
            "trade_explain": bool(trade_explain_payload),
            "reporter_analysis": bool(reporter_analysis_payload),
            "trade_reports": _safe_int(trade_report_summary.get("closed_trade_count"), 0) > 0,
            "current_payload": bool(row),
        },
        "insight_summary": _build_insight_summary(
            route_analysis=route_analysis,
            blocker_analysis=blocker_analysis,
            trade_report_summary=trade_report_summary,
        ),
        "dominant_patterns": dominant_patterns,
        "blocker_analysis": blocker_analysis,
        "route_analysis": route_analysis,
        "recommendation": recommendations,
        "confidence": confidence,
        "data_freshness": freshness,
        "trade_report_analysis": trade_report_summary,
        "runtime_semantics_unchanged": True,
    }
    packet["feedback_id"] = stable_evidence_id(
        "feedback",
        {
            "source_day": normalized_day,
            "source_mode": packet.get("source_mode"),
            "dominant_patterns": packet.get("dominant_patterns"),
            "blocker_analysis": packet.get("blocker_analysis"),
            "route_analysis": packet.get("route_analysis"),
            "recommendation": packet.get("recommendation"),
            "confidence": packet.get("confidence"),
        },
    )
    return packet
