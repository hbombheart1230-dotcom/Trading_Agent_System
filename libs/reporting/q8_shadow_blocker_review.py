from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from libs.reporting.quant_shadow_candidate_evaluation import (
    load_quant_shadow_candidate_payloads,
)
from libs.reporting.quant_shadow_forward_outcomes import attach_forward_outcomes
from libs.reporting.market_regime_rail_review import classify_market_regime_rail, load_latest_macro_snapshot


DEFAULT_REVIEW_REASONS = (
    "breakout_not_ready",
    "pullback_not_mature",
    "human_chart_sanity_guard_blocked",
    "volume_confirmation_missing",
    "below_vwap_reclaim_not_ready",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _candidate_rows(payloads: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        for raw in list(payload.get("candidates") or []):
            if not isinstance(raw, Mapping):
                continue
            row = dict(raw)
            row.setdefault("_payload_generated_at", payload.get("generated_at"))
            rows.append(row)
    return rows


def _dedupe_key(row: Mapping[str, Any]) -> tuple[str, str, str, int, str]:
    base = row.get("shadow_forward_base") if isinstance(row.get("shadow_forward_base"), Mapping) else {}
    baseline_epoch = 0
    try:
        baseline_epoch = int(float(base.get("baseline_epoch") or 0))
    except Exception:
        baseline_epoch = 0
    return (
        _text(row.get("symbol")).upper(),
        _text(row.get("reason")),
        _text(row.get("shadow_role")),
        baseline_epoch,
        _text(row.get("quant_tactic_id")),
    )


def _dedupe_rows(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str, int, str]] = set()
    for row in rows:
        key = _dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(row))
    return out


def _checkpoint_values(outcome: Mapping[str, Any]) -> Dict[str, Any]:
    checkpoints = outcome.get("checkpoints") if isinstance(outcome.get("checkpoints"), Mapping) else {}
    observed: List[Mapping[str, Any]] = [
        checkpoint
        for checkpoint in checkpoints.values()
        if isinstance(checkpoint, Mapping) and str(checkpoint.get("status") or "") == "observed"
    ]
    if not observed:
        return {"available": False}
    returns = [_to_float(row.get("return_pct")) for row in observed]
    mfes = [_to_float(row.get("mfe_pct")) for row in observed]
    maes = [_to_float(row.get("mae_pct")) for row in observed]
    returns = [value for value in returns if value is not None]
    mfes = [value for value in mfes if value is not None]
    maes = [value for value in maes if value is not None]
    latest = returns[-1] if returns else None
    return {
        "available": True,
        "latest_return_pct": latest,
        "max_favorable_pct": max(mfes) if mfes else None,
        "max_adverse_pct": min(maes) if maes else None,
    }


def _avg(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _decision_for_row(row: Mapping[str, Any]) -> str:
    reason = _text(row.get("reason"))
    if reason == "volume_confirmation_missing":
        return "retain_under_observation"
    if reason in {"breakout_not_ready", "pullback_not_mature"}:
        return "adjust_and_retest"
    if reason == "human_chart_sanity_guard_blocked":
        return "promotion_review_target"
    return "retain_under_observation"


def _summarize_group(reason: str, rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    observed_rows: List[Dict[str, Any]] = []
    for row in rows:
        outcome = row.get("shadow_forward_outcome") if isinstance(row.get("shadow_forward_outcome"), Mapping) else {}
        values = _checkpoint_values(outcome)
        if values.get("available"):
            observed_rows.append({**dict(row), "_q8_forward": values})
    latest_returns = [
        float(row["_q8_forward"]["latest_return_pct"])
        for row in observed_rows
        if row["_q8_forward"].get("latest_return_pct") is not None
    ]
    mfes = [
        float(row["_q8_forward"]["max_favorable_pct"])
        for row in observed_rows
        if row["_q8_forward"].get("max_favorable_pct") is not None
    ]
    maes = [
        float(row["_q8_forward"]["max_adverse_pct"])
        for row in observed_rows
        if row["_q8_forward"].get("max_adverse_pct") is not None
    ]
    positive_count = sum(1 for value in latest_returns if value > 0)
    missed_opportunity_count = sum(1 for value in mfes if value >= 1.0)
    adverse_count = sum(1 for value in maes if value <= -0.5)
    examples = sorted(
        observed_rows,
        key=lambda row: float(row["_q8_forward"].get("max_favorable_pct") or 0.0),
        reverse=True,
    )[:5]
    return {
        "reason": reason,
        "candidate_count": len(rows),
        "observed_count": len(observed_rows),
        "coverage": round(float(len(observed_rows)) / float(len(rows)), 4) if rows else 0.0,
        "avg_latest_return_pct": _avg(latest_returns),
        "avg_max_favorable_pct": _avg(mfes),
        "avg_max_adverse_pct": _avg(maes),
        "positive_latest_count": positive_count,
        "positive_latest_rate": round(float(positive_count) / float(len(latest_returns)), 4) if latest_returns else 0.0,
        "missed_opportunity_count": missed_opportunity_count,
        "missed_opportunity_rate": round(float(missed_opportunity_count) / float(len(mfes)), 4) if mfes else 0.0,
        "adverse_count": adverse_count,
        "adverse_rate": round(float(adverse_count) / float(len(maes)), 4) if maes else 0.0,
        "decision": _decision_for_row(rows[0]) if rows else "retain_under_observation",
        "examples": [
            {
                "symbol": _text(row.get("symbol")),
                "role": _text(row.get("shadow_role")),
                "rank": row.get("rank"),
                "tactic_id": _text(row.get("quant_tactic_id")),
                "latest_return_pct": row["_q8_forward"].get("latest_return_pct"),
                "max_favorable_pct": row["_q8_forward"].get("max_favorable_pct"),
                "max_adverse_pct": row["_q8_forward"].get("max_adverse_pct"),
            }
            for row in examples
        ],
    }


def build_q8_shadow_blocker_review(
    payloads: Iterable[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]] | None = None,
    review_reasons: Sequence[str] = DEFAULT_REVIEW_REASONS,
    market_regime_rail: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    raw_rows = attach_forward_outcomes(_candidate_rows(payloads), minute_rows_by_symbol=minute_rows_by_symbol)
    rows = _dedupe_rows(raw_rows)
    review_reason_set = {str(reason) for reason in review_reasons}
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        reason = _text(row.get("reason"))
        if reason in review_reason_set:
            grouped[reason].append(row)
    groups = [_summarize_group(reason, grouped.get(reason, [])) for reason in review_reasons]
    observed_total = sum(int(group.get("observed_count") or 0) for group in groups)
    return {
        "schema_version": "q8_shadow_blocker_review.v1",
        "behavior_effect": "evaluation_only",
        "market_regime_rail": dict(market_regime_rail or {}),
        "raw_candidate_count": len(raw_rows),
        "deduped_candidate_count": len(rows),
        "duplicate_count": max(0, len(raw_rows) - len(rows)),
        "dedupe_key": ["symbol", "reason", "shadow_role", "baseline_epoch", "quant_tactic_id"],
        "candidate_count": len(rows),
        "review_reason_count": len(groups),
        "observed_review_candidate_count": observed_total,
        "groups": groups,
    }


def render_q8_shadow_blocker_review_markdown(review: Mapping[str, Any], *, day: str) -> str:
    lines = [
        f"# Q8 Shadow Blocker Review ({day})",
        "",
        "This report is read-only evaluation output. It does not change trading behavior.",
        "",
        "## Summary",
        "",
        f"- candidate_count: **{int(review.get('candidate_count') or 0)}**",
        f"- raw_candidate_count: **{int(review.get('raw_candidate_count') or review.get('candidate_count') or 0)}**",
        f"- duplicate_count: **{int(review.get('duplicate_count') or 0)}**",
        f"- review_reason_count: **{int(review.get('review_reason_count') or 0)}**",
        f"- observed_review_candidate_count: **{int(review.get('observed_review_candidate_count') or 0)}**",
    ]
    rail = review.get("market_regime_rail") if isinstance(review.get("market_regime_rail"), Mapping) else {}
    if rail:
        lines.append(
            f"- market_regime_rail: `{rail.get('rail_id') or 'not_available'}` "
            f"({rail.get('rail_confidence') or 'none'})"
        )
        lines.append(f"- market_regime_rationale: {rail.get('rationale') or '-'}")
        focus = [str(x) for x in list(rail.get("q8_review_focus") or []) if str(x or "").strip()]
        if focus:
            lines.append(f"- market_regime_q8_focus: `{', '.join(focus)}`")
    lines += [
        "",
        "## Blocker Outcomes",
        "",
        "| Reason | Candidates | Observed | Avg Latest | Avg MFE | Avg MAE | Missed Opp | Adverse | Decision |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    groups = review.get("groups") if isinstance(review.get("groups"), list) else []
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        lines.append(
            f"| `{group.get('reason') or '-'}` "
            f"| {int(group.get('candidate_count') or 0)} "
            f"| {int(group.get('observed_count') or 0)} "
            f"| {float(group.get('avg_latest_return_pct') or 0.0):.4f}% "
            f"| {float(group.get('avg_max_favorable_pct') or 0.0):.4f}% "
            f"| {float(group.get('avg_max_adverse_pct') or 0.0):.4f}% "
            f"| {int(group.get('missed_opportunity_count') or 0)} "
            f"| {int(group.get('adverse_count') or 0)} "
            f"| `{group.get('decision') or 'retain_under_observation'}` |"
        )
    for group in groups:
        if not isinstance(group, Mapping) or not group.get("examples"):
            continue
        lines += ["", f"## Examples: {group.get('reason')}", ""]
        for example in list(group.get("examples") or [])[:5]:
            if not isinstance(example, Mapping):
                continue
            lines.append(
                f"- `{example.get('symbol') or '-'}` role `{example.get('role') or '-'}` "
                f"rank `{example.get('rank') if example.get('rank') is not None else '-'}` "
                f"latest {float(example.get('latest_return_pct') or 0.0):.4f}% "
                f"MFE {float(example.get('max_favorable_pct') or 0.0):.4f}% "
                f"MAE {float(example.get('max_adverse_pct') or 0.0):.4f}%"
            )
    return "\n".join(lines).rstrip() + "\n"


def generate_q8_shadow_blocker_review(
    *,
    reports_root: Path,
    day: str,
) -> Dict[str, Any]:
    payloads = load_quant_shadow_candidate_payloads(reports_root=reports_root, days=[day])
    market_regime_rail = classify_market_regime_rail(load_latest_macro_snapshot(day))
    review = build_q8_shadow_blocker_review(payloads, market_regime_rail=market_regime_rail)
    out_dir = Path(reports_root) / "operator_summary" / "daily" / day
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "q8_shadow_blocker_review.json"
    md_path = out_dir / "q8_shadow_blocker_review.md"
    json_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_q8_shadow_blocker_review_markdown(review, day=day), encoding="utf-8")
    return {**review, "report_json_path": str(json_path), "report_md_path": str(md_path)}


__all__ = [
    "DEFAULT_REVIEW_REASONS",
    "build_q8_shadow_blocker_review",
    "generate_q8_shadow_blocker_review",
    "render_q8_shadow_blocker_review_markdown",
]
