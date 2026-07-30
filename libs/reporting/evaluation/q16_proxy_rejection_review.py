from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.evaluation.cost_basis_comparison import build_evaluation_cost_bases
from libs.reporting.evaluation.metrics import performance_metrics
from libs.reporting.quant_shadow_forward_outcomes import (
    attach_forward_outcomes,
    load_minute_rows_from_state,
)
from libs.runtime.broker_cost_profile import load_broker_cost_profile


Q16_START_DAY = "2026-07-22"
Q17_START_DAY = "2026-07-27"
Q16_HORIZONS = ("+15m", "+30m")
Q16_MIN_EXACT_SAMPLES = 20
Q16_MIN_DAYS = 2


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _candidate_class(row: Mapping[str, Any]) -> str:
    if not bool(row.get("triggered")):
        return ""
    cost_filter = row.get("entry_cost_filter")
    cost_filter = cost_filter if isinstance(cost_filter, Mapping) else {}
    if cost_filter:
        directional_admitted = bool(cost_filter.get("directional_edge_available")) and bool(
            cost_filter.get("passed")
        ) and not bool(row.get("guard_blocked"))
        if directional_admitted:
            return "DIRECTIONAL_ADMITTED"
        proxy_only = bool(cost_filter.get("proxy_edge_available")) and not bool(
            cost_filter.get("directional_edge_available")
        )
        proxy_disallowed = not bool(
            cost_filter.get("allow_triggered_signal_proxy_edge")
            or cost_filter.get("triggered_signal_proxy_edge_allowed")
        )
        rejected = not bool(cost_filter.get("passed"))
        return (
            "EXACT_PROXY_ONLY_REJECTION"
            if proxy_only and proxy_disallowed and rejected and bool(row.get("guard_blocked"))
            else ""
        )
    reason = str(row.get("reason") or "")
    cost_state = str(row.get("entry_quant_cost_floor_state") or "")
    if bool(row.get("guard_blocked")) and "cost_edge_fail" in reason and cost_state == "not_met":
        return "LEGACY_COST_REJECTION_UNATTRIBUTED"
    return ""


def _q17_candidate_class(row: Mapping[str, Any]) -> str:
    if not bool(row.get("triggered")):
        return ""
    estimate = row.get("directional_edge_estimate")
    if not isinstance(estimate, Mapping) or not estimate:
        return "DIRECTIONAL_ESTIMATE_ARTIFACT_MISSING"
    if not bool(estimate.get("available")):
        return "DIRECTIONAL_EVIDENCE_UNAVAILABLE"
    cost_filter = row.get("entry_cost_filter")
    cost_filter = cost_filter if isinstance(cost_filter, Mapping) else {}
    if bool(cost_filter.get("passed")) and not bool(row.get("guard_blocked")):
        return "DIRECTIONAL_ADMITTED"
    fail_reasons = {
        str(value) for value in cost_filter.get("fail_reasons") or []
    }
    if fail_reasons & {
        "estimated_gross_edge_below_cost_floor",
        "cost_adjusted_edge_below_min",
    }:
        return "DIRECTIONAL_BELOW_COST_REJECTION"
    return "DIRECTIONAL_AVAILABLE_OTHER_BLOCK"


def _load_day_rows(reports_root: Path, day: str) -> list[dict[str, Any]]:
    root = reports_root.parent / "data" / "logs" / "quant_shadow_candidates" / day
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for path in sorted(root.glob("*.json")) if root.exists() else []:
        if path.name == "latest.json":
            continue
        payload = _read(path)
        generated_at = str(payload.get("generated_at") or "")
        for raw in payload.get("candidates") or []:
            if not isinstance(raw, Mapping) or str(raw.get("shadow_role") or "") != "top_pick":
                continue
            row = dict(raw)
            candidate_class = _candidate_class(row)
            q17_candidate_class = _q17_candidate_class(row)
            if not candidate_class and not q17_candidate_class:
                continue
            key = (str(row.get("q9_decision_id") or generated_at), str(row.get("symbol") or ""))
            if key in seen:
                continue
            seen.add(key)
            row["q16_candidate_class"] = candidate_class
            row["q17_candidate_class"] = q17_candidate_class
            row["q16_day"] = day
            row.setdefault("_payload_generated_at", generated_at)
            rows.append(row)
    return attach_forward_outcomes(
        rows,
        minute_rows_by_symbol=load_minute_rows_from_state(
            reports_root.parent / "data" / "state.json"
        ),
    )


def _metric_bundle(rows: list[dict[str, Any]], drag_pct: float, horizon: str) -> dict[str, Any]:
    gross: list[float] = []
    for row in rows:
        outcome = row.get("shadow_forward_outcome")
        outcome = outcome if isinstance(outcome, Mapping) else {}
        checkpoint = (outcome.get("checkpoints") or {}).get(horizon)
        checkpoint = checkpoint if isinstance(checkpoint, Mapping) else {}
        if checkpoint.get("status") != "observed":
            continue
        try:
            gross.append(float(checkpoint.get("return_pct")))
        except (TypeError, ValueError):
            continue
    return {
        "gross": performance_metrics(gross),
        "net": performance_metrics(value - drag_pct for value in gross),
    }


def _observed_rows(rows: list[dict[str, Any]], horizon: str) -> list[dict[str, Any]]:
    observed: list[dict[str, Any]] = []
    for row in rows:
        outcome = row.get("shadow_forward_outcome")
        outcome = outcome if isinstance(outcome, Mapping) else {}
        checkpoint = (outcome.get("checkpoints") or {}).get(horizon)
        if isinstance(checkpoint, Mapping) and checkpoint.get("status") == "observed":
            observed.append(row)
    return observed


def _daily_exact_metrics(rows: list[dict[str, Any]], live_drag: float) -> list[dict[str, Any]]:
    days = sorted({str(row.get("q16_day") or "") for row in rows if row.get("q16_day")})
    daily: list[dict[str, Any]] = []
    for source_day in days:
        day_rows = [row for row in rows if str(row.get("q16_day") or "") == source_day]
        metric = _metric_bundle(day_rows, live_drag, "+30m")["net"]
        count = int(metric.get("count") or 0)
        positive_day = bool(
            count > 0
            and float(metric.get("expectancy_pct") or 0.0) > 0.0
            and float(metric.get("profit_factor") or 0.0) > 1.0
        )
        daily.append(
            {
                "day": source_day,
                "exact_rejection_count": len(day_rows),
                "observed_30m_count": count,
                "live_net_30m": metric,
                "positive_30m_day": positive_day,
            }
        )
    return daily


def _q16_decision(observed_30m: int, daily_exact: list[dict[str, Any]]) -> tuple[bool, str, int, int]:
    observed_day_count = sum(int(row.get("observed_30m_count") or 0) > 0 for row in daily_exact)
    positive_day_count = sum(bool(row.get("positive_30m_day")) for row in daily_exact)
    ready = observed_30m >= Q16_MIN_EXACT_SAMPLES and observed_day_count >= Q16_MIN_DAYS
    if not ready:
        return False, "INSUFFICIENT_EVIDENCE", observed_day_count, positive_day_count
    decision = "ROLL_BACK" if positive_day_count >= Q16_MIN_DAYS else "RETAIN"
    return True, decision, observed_day_count, positive_day_count


def build_q16_proxy_rejection_review(
    *,
    reports_root: Path,
    day: str,
    start_day: str = Q16_START_DAY,
) -> dict[str, Any]:
    reports_root = Path(reports_root)
    rows: list[dict[str, Any]] = []
    day_root = reports_root / "evaluation" / "daily"
    for path in sorted(day_root.glob("*/q16_proxy_rejection_review.json")) if day_root.exists() else []:
        source_day = path.parent.name
        if start_day <= source_day < day:
            prior = _read(path)
            rows.extend(row for row in prior.get("samples") or [] if isinstance(row, dict))
    rows.extend(_load_day_rows(reports_root, day))
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("q16_day") or ""),
            str(row.get("q9_decision_id") or row.get("_payload_generated_at") or ""),
            str(row.get("symbol") or ""),
        )
        deduped[key] = row
    rows = list(deduped.values())
    for row in rows:
        row.setdefault("q17_candidate_class", _q17_candidate_class(row))
    exact = [row for row in rows if row.get("q16_candidate_class") == "EXACT_PROXY_ONLY_REJECTION"]
    directional_admitted = [row for row in rows if row.get("q16_candidate_class") == "DIRECTIONAL_ADMITTED"]
    legacy = [row for row in rows if row.get("q16_candidate_class") == "LEGACY_COST_REJECTION_UNATTRIBUTED"]
    q17_rows = [
        row
        for row in rows
        if str(row.get("q16_day") or "") >= Q17_START_DAY
        and str(row.get("q17_candidate_class") or "")
    ]
    q17_class_counts = Counter(
        str(row.get("q17_candidate_class") or "") for row in q17_rows
    )
    q17_unavailable_reasons = Counter(
        str(
            (
                row.get("directional_edge_estimate")
                if isinstance(row.get("directional_edge_estimate"), Mapping)
                else {}
            ).get("reason")
            or "artifact_missing"
        )
        for row in q17_rows
        if str(row.get("q17_candidate_class") or "")
        in {
            "DIRECTIONAL_EVIDENCE_UNAVAILABLE",
            "DIRECTIONAL_ESTIMATE_ARTIFACT_MISSING",
        }
    )
    q17_below_cost = [
        row
        for row in q17_rows
        if row.get("q17_candidate_class") == "DIRECTIONAL_BELOW_COST_REJECTION"
    ]
    q17_admitted = [
        row
        for row in q17_rows
        if row.get("q17_candidate_class") == "DIRECTIONAL_ADMITTED"
    ]
    bases = build_evaluation_cost_bases(load_broker_cost_profile(None))
    live_drag = float(bases["live_deployment_equity"]["total_drag_with_slippage_pct"])
    mock_drag = float(bases["mock_observed"]["total_drag_with_slippage_pct"])
    horizons = []
    for horizon in Q16_HORIZONS:
        horizons.append(
            {
                "horizon": horizon,
                "exact_proxy_only": {
                    "live": _metric_bundle(exact, live_drag, horizon),
                    "mock": _metric_bundle(exact, mock_drag, horizon),
                },
                "legacy_unattributed_cost_rejection": {
                    "live": _metric_bundle(legacy, live_drag, horizon),
                    "mock": _metric_bundle(legacy, mock_drag, horizon),
                },
                "directional_admitted": {
                    "live": _metric_bundle(directional_admitted, live_drag, horizon),
                    "mock": _metric_bundle(directional_admitted, mock_drag, horizon),
                },
            }
        )
    observed_30m = int(
        next(row for row in horizons if row["horizon"] == "+30m")["exact_proxy_only"]["live"]["gross"]["count"]
    )
    daily_exact = _daily_exact_metrics(exact, live_drag)
    decision_ready, decision, observed_day_count, positive_30m_day_count = _q16_decision(
        observed_30m,
        daily_exact,
    )
    return {
        "schema_version": "q16_proxy_rejection_review.v1",
        "behavior_effect": "evaluation_only",
        "start_day": start_day,
        "end_day": day,
        "evidence_status": "DECISION_READY" if decision_ready else "INSUFFICIENT_EVIDENCE",
        "decision": decision,
        "decision_rule": {
            "minimum_exact_proxy_only_samples": Q16_MIN_EXACT_SAMPLES,
            "minimum_days": Q16_MIN_DAYS,
            "rollback_requires_positive_30m_expectancy_and_pf_above_one_on_each_minimum_day": True,
            "legacy_unattributed_rows_are_decision_ineligible": True,
        },
        "counts": {
            "exact_proxy_only_rejection_count": len(exact),
            "exact_observed_30m_count": observed_30m,
            "exact_observed_day_count": observed_day_count,
            "positive_30m_day_count": positive_30m_day_count,
            "directional_admitted_count": len(directional_admitted),
            "legacy_cost_rejection_unattributed_count": len(legacy),
        },
        "cost_bases": bases,
        "horizons": horizons,
        "daily_exact_proxy_only": daily_exact,
        "q17_directional_edge_validation": {
            "schema_version": "q17_directional_edge_validation.v1",
            "behavior_effect": "evaluation_only",
            "start_day": Q17_START_DAY,
            "class_counts": dict(q17_class_counts),
            "unavailable_reasons": dict(q17_unavailable_reasons),
            "below_cost_horizons": [
                {
                    "horizon": horizon,
                    "live": _metric_bundle(q17_below_cost, live_drag, horizon),
                    "mock": _metric_bundle(q17_below_cost, mock_drag, horizon),
                }
                for horizon in Q16_HORIZONS
            ],
            "admitted_horizons": [
                {
                    "horizon": horizon,
                    "live": _metric_bundle(q17_admitted, live_drag, horizon),
                    "mock": _metric_bundle(q17_admitted, mock_drag, horizon),
                }
                for horizon in Q16_HORIZONS
            ],
        },
        "samples": rows,
    }


def render_q16_proxy_rejection_review(payload: Mapping[str, Any]) -> str:
    counts = payload.get("counts") or {}
    lines = [
        "# Q16 Proxy-Only Rejection Review",
        "",
        f"- Window: `{payload.get('start_day')}` to `{payload.get('end_day')}`",
        f"- Evidence: **{payload.get('evidence_status')}**",
        f"- Decision: **{payload.get('decision')}**",
        f"- Exact proxy-only rejections: {counts.get('exact_proxy_only_rejection_count', 0)}",
        f"- Exact +30m observations: {counts.get('exact_observed_30m_count', 0)}",
        f"- Exact observed days: {counts.get('exact_observed_day_count', 0)}",
        f"- Positive +30m days: {counts.get('positive_30m_day_count', 0)}",
        f"- Directional admitted candidates: {counts.get('directional_admitted_count', 0)}",
        f"- Legacy cost rejections without proxy attribution: {counts.get('legacy_cost_rejection_unattributed_count', 0)}",
        "",
        "| Horizon | Cohort | Basis | Count | Win Rate | Avg Return | Profit Factor | MDD |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for horizon in payload.get("horizons") or []:
        for cohort in ("exact_proxy_only", "directional_admitted", "legacy_unattributed_cost_rejection"):
            for basis in ("live", "mock"):
                metric = ((horizon.get(cohort) or {}).get(basis) or {}).get("net") or {}
                lines.append(
                    f"| {horizon.get('horizon')} | {cohort} | {basis} | {metric.get('count', 0)} | "
                    f"{float(metric.get('win_rate') or 0):.2%} | {float(metric.get('average_return_pct') or 0):.4f}% | "
                    f"{float(metric.get('profit_factor') or 0):.4f} | {float(metric.get('maximum_drawdown_pct') or 0):.4f}% |"
                )
    lines += [
        "",
        "## Daily Exact Proxy-Only Decision Evidence",
        "",
        "| Day | Rejections | +30m Observed | Live Win Rate | Live Avg Return | Profit Factor | Positive Day |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in payload.get("daily_exact_proxy_only") or []:
        metric = row.get("live_net_30m") or {}
        lines.append(
            f"| {row.get('day')} | {row.get('exact_rejection_count', 0)} | "
            f"{row.get('observed_30m_count', 0)} | {float(metric.get('win_rate') or 0):.2%} | "
            f"{float(metric.get('average_return_pct') or 0):.4f}% | "
            f"{float(metric.get('profit_factor') or 0):.4f} | "
            f"{'yes' if row.get('positive_30m_day') else 'no'} |"
        )
    lines += [
        "",
        "Legacy rows are shown for context only. They cannot prove that the rejected edge was proxy-only.",
    ]
    if payload.get("evidence_status") == "DECISION_READY":
        lines.append(f"Q16 decision is final under the fixed sample contract: **{payload.get('decision')}**.")
    else:
        lines.append("Q16 RETAIN/ROLL_BACK is unavailable until exact post-patch fields meet the sample contract.")
    q17 = payload.get("q17_directional_edge_validation") or {}
    lines += [
        "",
        "## Q17 Directional Edge Validation",
        "",
        f"- Start day: `{q17.get('start_day', Q17_START_DAY)}`",
    ]
    class_counts = q17.get("class_counts") or {}
    if class_counts:
        for name, count in sorted(class_counts.items()):
            lines.append(f"- `{name}`: {count}")
    else:
        lines.append("- No classified Q17 candidates.")
    unavailable_reasons = q17.get("unavailable_reasons") or {}
    if unavailable_reasons:
        lines.append("- Unavailable reasons:")
        for name, count in sorted(unavailable_reasons.items()):
            lines.append(f"  - `{name}`: {count}")
    lines += [
        "",
        "Q17 fields are additive and do not change the final Q16 RETAIN/ROLL_BACK decision.",
    ]
    return "\n".join(lines) + "\n"


__all__ = ["build_q16_proxy_rejection_review", "render_q16_proxy_rejection_review"]
