from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from libs.runtime.quant.enforcement import build_entry_quant_enforcement


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"", "-", "none", "null", "unknown", "not_captured"} else text


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def shadow_candidate_root_for_reports(reports_root: Path) -> Path:
    return Path(reports_root).parent / "data" / "logs" / "quant_shadow_candidates"


def _iter_days(start: str, end: str) -> Iterable[str]:
    start_date = date.fromisoformat(str(start)[:10])
    end_date = date.fromisoformat(str(end)[:10])
    current = start_date
    while current <= end_date:
        yield current.isoformat()
        current += timedelta(days=1)


def _json_paths_for_day(root: Path, day: str) -> List[Path]:
    day_dir = root / str(day)[:10]
    if not day_dir.exists():
        return []
    return sorted(path for path in day_dir.glob("*.json") if path.name != "latest.json")


def load_quant_shadow_candidate_payloads(
    *,
    reports_root: Path,
    days: Sequence[str],
) -> List[Dict[str, Any]]:
    root = shadow_candidate_root_for_reports(reports_root)
    payloads: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for day in days:
        for path in _json_paths_for_day(root, day):
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            payload = _read_json(path)
            if isinstance(payload, dict):
                payloads.append(dict(payload))
    return payloads


def load_quant_shadow_candidate_payloads_for_range(
    *,
    reports_root: Path,
    start: str,
    end: str,
) -> List[Dict[str, Any]]:
    return load_quant_shadow_candidate_payloads(
        reports_root=reports_root,
        days=list(_iter_days(start, end)),
    )


def _top_counter(counter: Counter[str], *, limit: int = 8) -> List[Dict[str, Any]]:
    return [
        {"name": name, "count": count}
        for name, count in counter.most_common(limit)
        if name
    ]


def _row_blockers(row: Mapping[str, Any]) -> List[str]:
    blockers: List[str] = []
    for value in (row.get("blockers"),):
        if isinstance(value, list):
            blockers.extend(_text(item) for item in value if _text(item))
    decision = row.get("entry_quant_decision")
    if isinstance(decision, Mapping):
        value = decision.get("blockers")
        if isinstance(value, list):
            blockers.extend(_text(item) for item in value if _text(item))
    return blockers


def _cost_floor_state(row: Mapping[str, Any]) -> str:
    direct = _text(row.get("entry_quant_cost_floor_state"))
    if direct:
        return direct
    decision = row.get("entry_quant_decision")
    if isinstance(decision, Mapping):
        cost_edge = decision.get("cost_edge")
        if isinstance(cost_edge, Mapping):
            state = _text(cost_edge.get("cost_floor_state"))
            if state:
                return state
    snapshot = row.get("quant_factor_snapshot")
    if isinstance(snapshot, Mapping):
        factors = snapshot.get("factors")
        if isinstance(factors, Mapping):
            return _text(factors.get("cost_floor_state"))
    return ""


def _entry_quant_decision(row: Mapping[str, Any]) -> str:
    decision = row.get("entry_quant_decision")
    if isinstance(decision, Mapping):
        return _text(decision.get("decision"))
    return ""


def _opening_probe(row: Mapping[str, Any]) -> Dict[str, Any]:
    probe = row.get("opening_momentum_probe_shadow")
    return dict(probe) if isinstance(probe, Mapping) else {}


def _opening_probe_would_enter(row: Mapping[str, Any]) -> bool:
    if row.get("opening_momentum_probe_would_enter") not in (None, ""):
        return _bool(row.get("opening_momentum_probe_would_enter"))
    return _bool(_opening_probe(row).get("would_probe"))


def _largecap_surge_probe(row: Mapping[str, Any]) -> Dict[str, Any]:
    probe = row.get("opening_largecap_surge_shadow")
    return dict(probe) if isinstance(probe, Mapping) else {}


def _largecap_surge_would_enter(row: Mapping[str, Any]) -> bool:
    if row.get("opening_largecap_surge_would_enter") not in (None, ""):
        return _bool(row.get("opening_largecap_surge_would_enter"))
    return _bool(_largecap_surge_probe(row).get("would_probe"))


def _actionable_entry_guard_block(row: Mapping[str, Any]) -> bool:
    if not _bool(row.get("guard_blocked")):
        return False
    primary = _text(row.get("primary_failure_axis"))
    decision = _entry_quant_decision(row)
    blockers = _row_blockers(row)
    guard_reason = _text(row.get("guard_reason"))
    if primary == "confirmed_entry" and decision == "entry_ready" and not blockers and not guard_reason:
        return False
    return True


def _count_reason(candidates: Sequence[Mapping[str, Any]], names: set[str]) -> int:
    total = 0
    for row in candidates:
        reason = _text(row.get("reason"))
        primary = _text(row.get("primary_failure_axis"))
        cost_floor = _cost_floor_state(row)
        if reason in names or primary in names or cost_floor in names:
            total += 1
            continue
        blockers = _row_blockers(row)
        if any(blocker in names for blocker in blockers):
            total += 1
    return total


def _runner_up_risk_count(candidates: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for row in candidates:
        if _text(row.get("shadow_role")) != "runner_up_evaluated":
            continue
        if _bool(row.get("would_enter")):
            total += 1
            continue
        if _bool(row.get("runner_up_quality_blocked")) or _bool(row.get("weak_fallback_blocked")):
            total += 1
            continue
        reason = _text(row.get("reason"))
        if reason in {"runner_up_quality_gate_failed", "weak_fallback_pullback"}:
            total += 1
    return total


def _entry_shape(row: Mapping[str, Any]) -> str:
    reason = _text(row.get("reason"))
    primary = _text(row.get("primary_failure_axis"))
    if reason in {
        "pullback_not_mature",
        "pullback_below_vwap_reclaim_not_ready",
        "pullback_structure_above_vwap_with_volume_confirmation",
    } or primary == "pullback_structure":
        return "pullback"
    if reason in {
        "below_vwap_reclaim_not_ready",
        "pullback_below_vwap_reclaim_not_ready",
    } or primary == "vwap_relationship":
        return "vwap_reclaim"
    if reason in {
        "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation",
        "breakout_above_recent_high_with_vwap_structure_confirmation",
        "breakout_not_ready",
    } or primary == "breakout_readiness":
        return "breakout"
    if reason in {"volume_confirmation_missing", "volume_insufficient"} or primary == "volume_confirmation":
        return "volume_confirmation"
    if reason == "human_chart_sanity_guard_blocked" or primary == "human_chart_sanity":
        return "human_chart_sanity"
    return "other"


def _entry_shape_payload(candidates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    shapes = Counter(_entry_shape(row) for row in candidates)
    pullback_blocked = sum(
        1
        for row in candidates
        if _entry_shape(row) in {"pullback", "vwap_reclaim"}
        and not _bool(row.get("would_enter"))
    )
    breakout_ready = sum(
        1
        for row in candidates
        if _entry_shape(row) == "breakout"
        and (
            _bool(row.get("would_enter"))
            or _text(row.get("reason"))
            in {
                "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation",
                "breakout_above_recent_high_with_vwap_structure_confirmation",
            }
        )
    )
    breakout_not_ready = sum(
        1
        for row in candidates
        if _entry_shape(row) == "breakout" and not _bool(row.get("would_enter"))
    )
    return {
        "behavior_effect": "diagnostic_only",
        "by_shape": _top_counter(shapes),
        "pullback_or_vwap_blocked_count": pullback_blocked,
        "breakout_ready_like_count": breakout_ready,
        "breakout_not_ready_count": breakout_not_ready,
    }


def _promotion_candidate(candidates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not candidates:
        return {
            "candidate": "hold",
            "confidence": "none",
            "reason": "no_shadow_candidates",
            "counts": {},
            "promotion_scope": "none",
            "recommended_action": "hold",
        }
    cost_edge = _count_reason(
        candidates,
        {"cost_edge_fail", "cost_filter_failed", "not_met", "cost_floor_not_met", "cost"},
    )
    entry_guard = sum(1 for row in candidates if _actionable_entry_guard_block(row))
    runner_up = _runner_up_risk_count(candidates)
    counts = {
        "cost_edge": cost_edge,
        "runner_up": runner_up,
        "entry_guard": entry_guard,
    }
    candidate, count = max(counts.items(), key=lambda item: item[1])
    if count <= 0:
        return {
            "candidate": "hold",
            "confidence": "low",
            "reason": "no_dominant_shadow_blocker",
            "counts": counts,
            "promotion_scope": "none",
            "recommended_action": "hold",
        }
    total = max(1, len(candidates))
    share = float(count) / float(total)
    confidence = "high" if count >= 5 and share >= 0.35 else "medium" if count >= 3 else "low"
    reason_by_candidate = {
        "cost_edge": "cost_edge_or_cost_floor_is_the_largest_shadow_blocker",
        "runner_up": "runner_up_fallback_quality_is_the_largest_shadow_issue",
        "entry_guard": "entry_guard_blocks_are_the_largest_shadow_issue",
    }
    promotion_scope = "pre_entry_filter" if candidate == "cost_edge" else "candidate_selection"
    recommended_action = "manual_review_before_live_change"
    promotion_state = "candidate_review"
    behavior_effect = "recommendation_only"
    active_guard_reason = ""
    if candidate == "cost_edge" and confidence in {"high", "medium"}:
        enforcement = build_entry_quant_enforcement(
            {"decision": "block_recommended", "blockers": ["cost_edge_fail"]}
        )
        if bool(enforcement.get("blocked")):
            recommended_action = "already_promoted_monitor_hard_gate"
            promotion_state = "active"
            behavior_effect = str(enforcement.get("behavior_effect") or "entry_guard_enforced")
            active_guard_reason = "quant_entry_block:cost_edge_fail"
        else:
            recommended_action = "promote_shadow_validated_guard"
            promotion_state = "recommended"
    return {
        "candidate": candidate,
        "confidence": confidence,
        "reason": reason_by_candidate.get(candidate, "dominant_shadow_blocker"),
        "counts": counts,
        "share": share,
        "behavior_effect": behavior_effect,
        "promotion_scope": promotion_scope,
        "recommended_action": recommended_action,
        "promotion_state": promotion_state,
        "active_guard_reason": active_guard_reason,
    }


def _shadow_readiness(candidates: Sequence[Mapping[str, Any]], promotion: Mapping[str, Any]) -> Dict[str, Any]:
    candidate_count = len(candidates)
    evaluated_count = sum(1 for row in candidates if _bool(row.get("evaluated")))
    evaluated_ratio = float(evaluated_count) / float(candidate_count) if candidate_count else 0.0
    candidate = _text(promotion.get("candidate"))
    confidence = _text(promotion.get("confidence"))
    action = _text(promotion.get("recommended_action")) or "hold"
    ready = bool(
        candidate_count >= 100
        and evaluated_count >= 50
        and evaluated_ratio >= 0.70
        and candidate not in {"", "hold"}
        and confidence in {"medium", "high"}
    )
    if not candidate_count:
        status = "hold_no_shadow_candidates"
    elif ready:
        status = "ready"
    elif evaluated_count < 50:
        status = "hold_shadow_sample_insufficient"
    elif evaluated_ratio < 0.70:
        status = "hold_shadow_coverage_insufficient"
    else:
        status = "review_shadow_signal_weak"
    return {
        "status": status,
        "action": action if ready else "hold",
        "candidate_count": candidate_count,
        "evaluated_count": evaluated_count,
        "evaluated_ratio": evaluated_ratio,
        "sample_floor": 100,
        "evaluated_floor": 50,
        "coverage_floor": 0.70,
        "candidate": candidate or "hold",
        "confidence": confidence or "none",
        "promotion_scope": _text(promotion.get("promotion_scope")) or "none",
    }


def build_quant_shadow_candidate_evaluation(
    payloads: Iterable[Mapping[str, Any]],
    *,
    symbol: str = "",
) -> Dict[str, Any]:
    symbol_filter = _text(symbol).upper()
    payload_count = 0
    candidates: List[Dict[str, Any]] = []
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        payload_count += 1
        for row in list(payload.get("candidates") or []):
            if not isinstance(row, Mapping):
                continue
            row_symbol = _text(row.get("symbol")).upper()
            if symbol_filter and row_symbol != symbol_filter:
                continue
            candidates.append(dict(row))

    roles = Counter(_text(row.get("shadow_role")) for row in candidates)
    reasons = Counter(_text(row.get("reason")) for row in candidates)
    tactics = Counter(_text(row.get("quant_tactic_id")) for row in candidates)
    suitability = Counter(_text(row.get("tactic_suitability_tier")) for row in candidates)
    cost_floor = Counter(_cost_floor_state(row) for row in candidates)
    blockers = Counter(_text(row.get("primary_failure_axis")) for row in candidates)
    opening_probe_rows = [row for row in candidates if _opening_probe(row)]
    opening_probe_reasons = Counter(_text(_opening_probe(row).get("reason")) for row in opening_probe_rows)
    opening_probe_symbols = Counter(_text(row.get("symbol")) for row in opening_probe_rows if _opening_probe_would_enter(row))
    largecap_probe_rows = [row for row in candidates if _largecap_surge_probe(row)]
    largecap_probe_reasons = Counter(_text(_largecap_surge_probe(row).get("reason")) for row in largecap_probe_rows)
    largecap_probe_symbols = Counter(
        _text(row.get("symbol")) for row in largecap_probe_rows if _largecap_surge_would_enter(row)
    )
    would_enter = sum(1 for row in candidates if _bool(row.get("would_enter")))
    opening_probe_would_enter = sum(1 for row in candidates if _opening_probe_would_enter(row))
    largecap_probe_would_enter = sum(1 for row in candidates if _largecap_surge_would_enter(row))
    guard_blocked = sum(1 for row in candidates if _bool(row.get("guard_blocked")))
    actionable_guard_blocked = sum(1 for row in candidates if _actionable_entry_guard_block(row))
    evaluated = sum(1 for row in candidates if _bool(row.get("evaluated")))
    entry_shape = _entry_shape_payload(candidates)
    promotion = _promotion_candidate(candidates)
    shadow_readiness = _shadow_readiness(candidates, promotion)

    return {
        "schema_version": "quant_shadow_candidate_evaluation.v1",
        "behavior_effect": "observation_only",
        "shadow_readiness": shadow_readiness,
        "payload_count": payload_count,
        "candidate_count": len(candidates),
        "evaluated_count": evaluated,
        "would_enter_count": would_enter,
        "opening_momentum_probe_count": len(opening_probe_rows),
        "opening_momentum_probe_would_enter_count": opening_probe_would_enter,
        "opening_largecap_surge_count": len(largecap_probe_rows),
        "opening_largecap_surge_would_enter_count": largecap_probe_would_enter,
        "guard_blocked_count": guard_blocked,
        "actionable_guard_blocked_count": actionable_guard_blocked,
        "by_role": _top_counter(roles),
        "by_reason": _top_counter(reasons),
        "by_tactic_id": _top_counter(tactics),
        "by_tactic_suitability_tier": _top_counter(suitability),
        "by_cost_floor_state": _top_counter(cost_floor),
        "by_primary_failure_axis": _top_counter(blockers),
        "opening_momentum_probe": {
            "behavior_effect": "observation_only",
            "candidate_count": len(opening_probe_rows),
            "would_enter_count": opening_probe_would_enter,
            "by_reason": _top_counter(opening_probe_reasons),
            "by_would_enter_symbol": _top_counter(opening_probe_symbols),
        },
        "opening_largecap_surge": {
            "behavior_effect": "observation_only",
            "candidate_count": len(largecap_probe_rows),
            "would_enter_count": largecap_probe_would_enter,
            "by_reason": _top_counter(largecap_probe_reasons),
            "by_would_enter_symbol": _top_counter(largecap_probe_symbols),
        },
        "entry_shape_diagnostics": entry_shape,
        "promotion_candidate": promotion,
    }


def _format_rows(rows: Sequence[Mapping[str, Any]], *, limit: int = 4) -> str:
    parts: List[str] = []
    for row in list(rows)[:limit]:
        name = _text(row.get("name"))
        if not name:
            continue
        parts.append(f"{name} ({row.get('count') or 0})")
    return ", ".join(parts) if parts else "none"


def render_quant_shadow_candidate_evaluation_lines(payload: Mapping[str, Any] | None) -> List[str]:
    evaluation = dict(payload or {})
    if not evaluation or int(evaluation.get("candidate_count") or 0) <= 0:
        return []
    lines = [
        "",
        "## Quant Shadow Candidates",
        "",
        "- Q8 shadow candidates: "
        f"{evaluation.get('candidate_count') or 0} candidates / "
        f"{evaluation.get('payload_count') or 0} payloads / "
        f"evaluated {evaluation.get('evaluated_count') or 0} / "
        f"would-enter {evaluation.get('would_enter_count') or 0} / "
        f"opening-probe {evaluation.get('opening_momentum_probe_would_enter_count') or 0} / "
        f"largecap-surge {evaluation.get('opening_largecap_surge_would_enter_count') or 0} / "
        f"guard-blocked {evaluation.get('guard_blocked_count') or 0} "
        f"(actionable {evaluation.get('actionable_guard_blocked_count') or 0})",
        f"- Roles: {_format_rows(list(evaluation.get('by_role') or []))}",
        f"- Reasons: {_format_rows(list(evaluation.get('by_reason') or []))}",
        f"- Tactics: {_format_rows(list(evaluation.get('by_tactic_id') or []))}",
        f"- Suitability: {_format_rows(list(evaluation.get('by_tactic_suitability_tier') or []))}",
        f"- Cost floor: {_format_rows(list(evaluation.get('by_cost_floor_state') or []))}",
        f"- Failure axis: {_format_rows(list(evaluation.get('by_primary_failure_axis') or []))}",
    ]
    readiness = evaluation.get("shadow_readiness") if isinstance(evaluation.get("shadow_readiness"), Mapping) else {}
    if readiness:
        lines.append(
            "- Q8 shadow readiness: "
            f"`{readiness.get('status') or 'not_available'}` / "
            f"action `{readiness.get('action') or 'hold'}` / "
            f"scope `{readiness.get('promotion_scope') or 'none'}` / "
            f"sample {readiness.get('evaluated_count') or 0}/"
            f"{readiness.get('candidate_count') or 0}"
        )
    promotion = evaluation.get("promotion_candidate") if isinstance(evaluation.get("promotion_candidate"), Mapping) else {}
    if promotion:
        lines.append(
            "- Q8 promotion candidate: "
            f"{promotion.get('candidate') or 'hold'} / "
            f"confidence {promotion.get('confidence') or 'none'} / "
            f"{promotion.get('reason') or '-'} / "
            f"action {promotion.get('recommended_action') or 'hold'}"
        )
        if promotion.get("promotion_state"):
            lines.append(
                "- Q8 promotion state: "
                f"{promotion.get('promotion_state') or 'unknown'} / "
                f"effect {promotion.get('behavior_effect') or 'unknown'} / "
                f"guard {promotion.get('active_guard_reason') or '-'}"
            )
        counts = promotion.get("counts") if isinstance(promotion.get("counts"), Mapping) else {}
        if counts:
            lines.append(
                "- Q8 promotion counts: "
                f"cost-edge {counts.get('cost_edge') or 0}, "
                f"runner-up {counts.get('runner_up') or 0}, "
                f"entry-guard {counts.get('entry_guard') or 0}"
            )
    opening_probe = evaluation.get("opening_momentum_probe") if isinstance(evaluation.get("opening_momentum_probe"), Mapping) else {}
    if opening_probe:
        lines += [
            "- Opening momentum probe shadow: "
            f"{opening_probe.get('would_enter_count') or 0}/"
            f"{opening_probe.get('candidate_count') or 0} would-probe "
            f"(observation only)",
            f"- Opening probe reasons: {_format_rows(list(opening_probe.get('by_reason') or []))}",
            f"- Opening probe symbols: {_format_rows(list(opening_probe.get('by_would_enter_symbol') or []))}",
        ]
    largecap_probe = evaluation.get("opening_largecap_surge") if isinstance(evaluation.get("opening_largecap_surge"), Mapping) else {}
    if largecap_probe:
        lines += [
            "- Opening largecap surge shadow: "
            f"{largecap_probe.get('would_enter_count') or 0}/"
            f"{largecap_probe.get('candidate_count') or 0} would-probe "
            f"(observation only)",
            f"- Opening largecap reasons: {_format_rows(list(largecap_probe.get('by_reason') or []))}",
            f"- Opening largecap symbols: {_format_rows(list(largecap_probe.get('by_would_enter_symbol') or []))}",
        ]
    entry_shape = evaluation.get("entry_shape_diagnostics") if isinstance(evaluation.get("entry_shape_diagnostics"), Mapping) else {}
    if entry_shape:
        lines += [
            "- Entry shape diagnostics: "
            f"pullback/vwap blocked {entry_shape.get('pullback_or_vwap_blocked_count') or 0}, "
            f"breakout ready-like {entry_shape.get('breakout_ready_like_count') or 0}, "
            f"breakout not-ready {entry_shape.get('breakout_not_ready_count') or 0}",
            f"- Entry shapes: {_format_rows(list(entry_shape.get('by_shape') or []))}",
        ]
    return lines
