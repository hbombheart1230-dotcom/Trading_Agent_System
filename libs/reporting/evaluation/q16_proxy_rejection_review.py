from __future__ import annotations

import json
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
    if not bool(row.get("triggered")) or not bool(row.get("guard_blocked")):
        return ""
    cost_filter = row.get("entry_cost_filter")
    cost_filter = cost_filter if isinstance(cost_filter, Mapping) else {}
    if cost_filter:
        proxy_only = bool(cost_filter.get("proxy_edge_available")) and not bool(
            cost_filter.get("directional_edge_available")
        )
        proxy_disallowed = not bool(
            cost_filter.get("allow_triggered_signal_proxy_edge")
            or cost_filter.get("triggered_signal_proxy_edge_allowed")
        )
        rejected = not bool(cost_filter.get("passed"))
        return "EXACT_PROXY_ONLY_REJECTION" if proxy_only and proxy_disallowed and rejected else ""
    reason = str(row.get("reason") or "")
    cost_state = str(row.get("entry_quant_cost_floor_state") or "")
    if "cost_edge_fail" in reason and cost_state == "not_met":
        return "LEGACY_COST_REJECTION_UNATTRIBUTED"
    return ""


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
            if not candidate_class:
                continue
            key = (str(row.get("q9_decision_id") or generated_at), str(row.get("symbol") or ""))
            if key in seen:
                continue
            seen.add(key)
            row["q16_candidate_class"] = candidate_class
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
    exact = [row for row in rows if row.get("q16_candidate_class") == "EXACT_PROXY_ONLY_REJECTION"]
    legacy = [row for row in rows if row.get("q16_candidate_class") == "LEGACY_COST_REJECTION_UNATTRIBUTED"]
    bases = build_evaluation_cost_bases(load_broker_cost_profile(None))
    live_drag = float(bases["live_deployment_equity"]["total_drag_with_slippage_pct"])
    mock_drag = float(bases["mock_observed"]["total_drag_with_slippage_pct"])
    exact_days = sorted({str(row.get("q16_day") or "") for row in exact})
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
            }
        )
    observed_30m = int(
        next(row for row in horizons if row["horizon"] == "+30m")["exact_proxy_only"]["live"]["gross"]["count"]
    )
    decision_ready = observed_30m >= Q16_MIN_EXACT_SAMPLES and len(exact_days) >= Q16_MIN_DAYS
    decision = "INSUFFICIENT_EVIDENCE"
    if decision_ready:
        thirty = next(row for row in horizons if row["horizon"] == "+30m")["exact_proxy_only"]["live"]["net"]
        decision = (
            "ROLL_BACK"
            if float(thirty.get("expectancy_pct") or 0.0) > 0
            and float(thirty.get("profit_factor") or 0.0) > 1.0
            else "RETAIN"
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
            "legacy_unattributed_rows_are_decision_ineligible": True,
        },
        "counts": {
            "exact_proxy_only_rejection_count": len(exact),
            "exact_observed_30m_count": observed_30m,
            "exact_observed_day_count": len(exact_days),
            "legacy_cost_rejection_unattributed_count": len(legacy),
        },
        "cost_bases": bases,
        "horizons": horizons,
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
        f"- Legacy cost rejections without proxy attribution: {counts.get('legacy_cost_rejection_unattributed_count', 0)}",
        "",
        "| Horizon | Cohort | Basis | Count | Win Rate | Avg Return | Profit Factor | MDD |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for horizon in payload.get("horizons") or []:
        for cohort in ("exact_proxy_only", "legacy_unattributed_cost_rejection"):
            for basis in ("live", "mock"):
                metric = ((horizon.get(cohort) or {}).get(basis) or {}).get("net") or {}
                lines.append(
                    f"| {horizon.get('horizon')} | {cohort} | {basis} | {metric.get('count', 0)} | "
                    f"{float(metric.get('win_rate') or 0):.2%} | {float(metric.get('average_return_pct') or 0):.4f}% | "
                    f"{float(metric.get('profit_factor') or 0):.4f} | {float(metric.get('maximum_drawdown_pct') or 0):.4f}% |"
                )
    lines += [
        "",
        "Legacy rows are shown for context only. They cannot prove that the rejected edge was proxy-only.",
        "Q16 RETAIN/ROLL_BACK is unavailable until exact post-patch fields meet the sample contract.",
    ]
    return "\n".join(lines) + "\n"


__all__ = ["build_q16_proxy_rejection_review", "render_q16_proxy_rejection_review"]
