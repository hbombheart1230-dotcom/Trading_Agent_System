from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from libs.reporting.quant_shadow_forward_outcomes import attach_forward_outcomes
from libs.runtime.quant.enforcement import build_entry_quant_enforcement
from libs.runtime.quant.entry_lane_observation import build_entry_lane_observation
from libs.runtime.quant.vwap_reclaim_observation import classify_below_vwap_reclaim_observation


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


def _tactic_id(row: Mapping[str, Any]) -> str:
    direct = _text(row.get("quant_tactic_id") or row.get("tactic_id"))
    if direct:
        return direct
    decision = row.get("entry_quant_decision")
    if isinstance(decision, Mapping):
        tactic = _text(decision.get("tactic_id"))
        if tactic:
            return tactic
    snapshot = row.get("quant_factor_snapshot")
    if isinstance(snapshot, Mapping):
        return _text(snapshot.get("tactic_id"))
    return ""


def _tactic_suitability_tier(row: Mapping[str, Any]) -> str:
    direct = _text(row.get("tactic_suitability_tier"))
    if direct:
        return direct
    decision = row.get("entry_quant_decision")
    if isinstance(decision, Mapping):
        suitability = decision.get("tactic_suitability")
        if isinstance(suitability, Mapping):
            tier = _text(suitability.get("tier"))
            if tier:
                return tier
    return ""


def _forward_base(row: Mapping[str, Any]) -> Dict[str, Any]:
    base = row.get("shadow_forward_base")
    return dict(base) if isinstance(base, Mapping) else {}


def _forward_outcome(row: Mapping[str, Any]) -> Dict[str, Any]:
    outcome = row.get("shadow_forward_outcome")
    return dict(outcome) if isinstance(outcome, Mapping) else {}


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


def _below_vwap_reclaim_observation(row: Mapping[str, Any]) -> Dict[str, Any]:
    payload = row.get("below_vwap_reclaim_observation")
    if isinstance(payload, Mapping):
        return dict(payload)
    return classify_below_vwap_reclaim_observation(row)


def _below_vwap_reclaim_observation_payload(candidates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    subtype_counter: Counter[str] = Counter()
    subtype_v2_counter: Counter[str] = Counter()
    total = 0
    for row in candidates:
        observation = _below_vwap_reclaim_observation(row)
        if not _bool(observation.get("applies")):
            continue
        total += 1
        subtype_counter[_text(observation.get("subtype"))] += 1
        subtype_v2_counter[_text(observation.get("subtype_v2"))] += 1
    return {
        "behavior_effect": "observation_only",
        "candidate_count": int(total),
        "by_subtype": _top_counter(subtype_counter, limit=8),
        "by_subtype_v2": _top_counter(subtype_v2_counter, limit=10),
    }


def _entry_lane_observation(row: Mapping[str, Any]) -> Dict[str, Any]:
    payload = row.get("entry_lane_observation")
    if isinstance(payload, Mapping):
        return dict(payload)
    return build_entry_lane_observation(row)


def _entry_lane_observation_payload(candidates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    lane_counter: Counter[str] = Counter()
    subtype_counter: Counter[str] = Counter()
    subtype_v2_counter: Counter[str] = Counter()
    lane_subtype_counter: Counter[str] = Counter()
    lane_subtype_v2_counter: Counter[str] = Counter()
    time_bucket_counter: Counter[str] = Counter()
    market_regime_counter: Counter[str] = Counter()
    market_rail_counter: Counter[str] = Counter()
    total = 0
    for row in candidates:
        observation = _entry_lane_observation(row)
        lane = _text(observation.get("primary_lane")) or "unknown"
        subtype = _text(observation.get("subtype")) or "unknown"
        subtype_v2 = _text(observation.get("subtype_v2")) or subtype
        time_bucket = _text(observation.get("time_bucket")) or "unknown"
        market_regime = _text(observation.get("market_regime")) or "unknown"
        market_rail = _text(observation.get("market_regime_rail")) or "unknown"
        total += 1
        lane_counter[lane] += 1
        subtype_counter[subtype] += 1
        subtype_v2_counter[subtype_v2] += 1
        lane_subtype_counter[f"{lane}:{subtype}"] += 1
        lane_subtype_v2_counter[f"{lane}:{subtype_v2}"] += 1
        time_bucket_counter[time_bucket] += 1
        market_regime_counter[market_regime] += 1
        market_rail_counter[market_rail] += 1
    return {
        "behavior_effect": "observation_only",
        "candidate_count": int(total),
        "by_primary_lane": _top_counter(lane_counter, limit=10),
        "by_subtype": _top_counter(subtype_counter, limit=10),
        "by_subtype_v2": _top_counter(subtype_v2_counter, limit=10),
        "by_lane_subtype": _top_counter(lane_subtype_counter, limit=12),
        "by_lane_subtype_v2": _top_counter(lane_subtype_v2_counter, limit=12),
        "by_time_bucket": _top_counter(time_bucket_counter, limit=8),
        "by_market_regime": _top_counter(market_regime_counter, limit=8),
        "by_market_regime_rail": _top_counter(market_rail_counter, limit=8),
    }


def _mean(values: Sequence[float]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    return round(sum(clean) / float(len(clean)), 4)


def _checkpoint_value(row: Mapping[str, Any], checkpoint: str, metric: str) -> float | None:
    outcome = _forward_outcome(row)
    checkpoints = outcome.get("checkpoints")
    if not isinstance(checkpoints, Mapping):
        return None
    payload = checkpoints.get(checkpoint)
    if not isinstance(payload, Mapping) or _text(payload.get("status")) != "observed":
        return None
    value = payload.get(metric)
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _forward_outcome_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    observed_rows = [row for row in rows if _bool(_forward_outcome(row).get("available"))]
    return {
        "candidate_count": len(rows),
        "observed_count": len(observed_rows),
        "avg_return_3m_pct": _mean([_checkpoint_value(row, "+3m", "return_pct") for row in rows]),
        "avg_return_5m_pct": _mean([_checkpoint_value(row, "+5m", "return_pct") for row in rows]),
        "avg_return_15m_pct": _mean([_checkpoint_value(row, "+15m", "return_pct") for row in rows]),
        "avg_return_30m_pct": _mean([_checkpoint_value(row, "+30m", "return_pct") for row in rows]),
        "avg_return_60m_pct": _mean([_checkpoint_value(row, "+60m", "return_pct") for row in rows]),
        "avg_mfe_5m_pct": _mean([_checkpoint_value(row, "+5m", "mfe_pct") for row in rows]),
        "avg_mae_5m_pct": _mean([_checkpoint_value(row, "+5m", "mae_pct") for row in rows]),
        "coverage": (float(len(observed_rows)) / float(len(rows))) if rows else 0.0,
    }


def _top_forward_groups(groups: Mapping[str, List[Mapping[str, Any]]], *, limit: int = 10) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    for name, rows in groups.items():
        summary = _forward_outcome_summary(rows)
        if int(summary.get("observed_count") or 0) <= 0:
            continue
        summary["name"] = name
        summaries.append(summary)
    summaries.sort(
        key=lambda item: (
            float(item.get("avg_return_5m_pct") or item.get("avg_return_3m_pct") or -999.0),
            int(item.get("observed_count") or 0),
        ),
        reverse=True,
    )
    return summaries[:limit]


def _entry_lane_forward_outcomes(candidates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    by_lane: Dict[str, List[Mapping[str, Any]]] = {}
    by_subtype: Dict[str, List[Mapping[str, Any]]] = {}
    by_subtype_v2: Dict[str, List[Mapping[str, Any]]] = {}
    by_lane_subtype: Dict[str, List[Mapping[str, Any]]] = {}
    by_lane_subtype_v2: Dict[str, List[Mapping[str, Any]]] = {}
    by_time_bucket: Dict[str, List[Mapping[str, Any]]] = {}
    by_market_rail: Dict[str, List[Mapping[str, Any]]] = {}
    for row in candidates:
        observation = _entry_lane_observation(row)
        lane = _text(observation.get("primary_lane")) or "unknown"
        subtype = _text(observation.get("subtype")) or "unknown"
        subtype_v2 = _text(observation.get("subtype_v2")) or subtype
        time_bucket = _text(observation.get("time_bucket")) or "unknown"
        market_rail = _text(observation.get("market_regime_rail")) or "unknown"
        by_lane.setdefault(lane, []).append(row)
        by_subtype.setdefault(subtype, []).append(row)
        by_subtype_v2.setdefault(subtype_v2, []).append(row)
        by_lane_subtype.setdefault(f"{lane}:{subtype}", []).append(row)
        by_lane_subtype_v2.setdefault(f"{lane}:{subtype_v2}", []).append(row)
        by_time_bucket.setdefault(time_bucket, []).append(row)
        by_market_rail.setdefault(market_rail, []).append(row)
    return {
        "behavior_effect": "evaluation_only",
        "by_primary_lane": _top_forward_groups(by_lane, limit=10),
        "by_subtype": _top_forward_groups(by_subtype, limit=10),
        "by_subtype_v2": _top_forward_groups(by_subtype_v2, limit=10),
        "by_lane_subtype": _top_forward_groups(by_lane_subtype, limit=12),
        "by_lane_subtype_v2": _top_forward_groups(by_lane_subtype_v2, limit=12),
        "by_time_bucket": _top_forward_groups(by_time_bucket, limit=8),
        "by_market_regime_rail": _top_forward_groups(by_market_rail, limit=8),
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
            enriched = dict(row)
            enriched.setdefault("_payload_generated_at", payload.get("generated_at"))
            candidates.append(enriched)
    candidates = attach_forward_outcomes(candidates)

    roles = Counter(_text(row.get("shadow_role")) for row in candidates)
    reasons = Counter(_text(row.get("reason")) for row in candidates)
    tactics = Counter(_tactic_id(row) for row in candidates)
    suitability = Counter(_tactic_suitability_tier(row) for row in candidates)
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
    forward_base_available = sum(1 for row in candidates if _bool(_forward_base(row).get("available")))
    forward_outcome_available = sum(1 for row in candidates if _bool(_forward_outcome(row).get("available")))
    entry_shape = _entry_shape_payload(candidates)
    below_vwap_reclaim = _below_vwap_reclaim_observation_payload(candidates)
    entry_lane_observation = _entry_lane_observation_payload(candidates)
    entry_lane_forward_outcomes = _entry_lane_forward_outcomes(candidates)
    promotion = _promotion_candidate(candidates)
    shadow_readiness = _shadow_readiness(candidates, promotion)

    return {
        "schema_version": "quant_shadow_candidate_evaluation.v1",
        "behavior_effect": "observation_only",
        "shadow_readiness": shadow_readiness,
        "payload_count": payload_count,
        "candidate_count": len(candidates),
        "evaluated_count": evaluated,
        "forward_base_available_count": forward_base_available,
        "forward_base_coverage": (float(forward_base_available) / float(len(candidates))) if candidates else 0.0,
        "forward_outcome_available_count": forward_outcome_available,
        "forward_outcome_coverage": (float(forward_outcome_available) / float(len(candidates))) if candidates else 0.0,
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
        "below_vwap_reclaim_observation": below_vwap_reclaim,
        "entry_lane_observation": entry_lane_observation,
        "entry_lane_forward_outcomes": entry_lane_forward_outcomes,
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


def _format_forward_rows(rows: Sequence[Mapping[str, Any]], *, limit: int = 4) -> str:
    parts: List[str] = []
    for row in list(rows)[:limit]:
        name = _text(row.get("name"))
        if not name:
            continue
        observed = int(row.get("observed_count") or 0)
        count = int(row.get("candidate_count") or 0)
        ret5 = row.get("avg_return_5m_pct")
        ret15 = row.get("avg_return_15m_pct")
        mfe5 = row.get("avg_mfe_5m_pct")
        mae5 = row.get("avg_mae_5m_pct")
        parts.append(
            f"{name} ({observed}/{count}, "
            f"+5m {float(ret5):.4f}%"
            if ret5 is not None
            else f"{name} ({observed}/{count}, +5m n/a"
        )
        if parts:
            last = parts[-1]
            if ret15 is not None:
                last += f", +15m {float(ret15):.4f}%"
            if mfe5 is not None:
                last += f", mfe5 {float(mfe5):.4f}%"
            if mae5 is not None:
                last += f", mae5 {float(mae5):.4f}%"
            parts[-1] = last + ")"
    return "; ".join(parts) if parts else "none"


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
        f"- Q8 shadow forward base: {evaluation.get('forward_base_available_count') or 0}/"
        f"{evaluation.get('candidate_count') or 0} candidates have baseline minute price "
        f"(coverage {float(evaluation.get('forward_base_coverage') or 0.0):.1%})",
        f"- Q8 shadow forward outcome: {evaluation.get('forward_outcome_available_count') or 0}/"
        f"{evaluation.get('candidate_count') or 0} candidates have at least one forward checkpoint "
        f"(coverage {float(evaluation.get('forward_outcome_coverage') or 0.0):.1%})",
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
    entry_lane = (
        evaluation.get("entry_lane_observation")
        if isinstance(evaluation.get("entry_lane_observation"), Mapping)
        else {}
    )
    if entry_lane and int(entry_lane.get("candidate_count") or 0) > 0:
        lines += [
            "- Entry lane observation: "
            f"{entry_lane.get('candidate_count') or 0} candidates / "
            f"{_format_rows(list(entry_lane.get('by_primary_lane') or []), limit=8)}",
            f"- Entry lane subtypes: {_format_rows(list(entry_lane.get('by_lane_subtype') or []), limit=8)}",
            f"- Entry lane time buckets: {_format_rows(list(entry_lane.get('by_time_bucket') or []), limit=6)}",
            f"- Entry lane market rails: {_format_rows(list(entry_lane.get('by_market_regime_rail') or []), limit=6)}",
        ]
    lane_forward = (
        evaluation.get("entry_lane_forward_outcomes")
        if isinstance(evaluation.get("entry_lane_forward_outcomes"), Mapping)
        else {}
    )
    if lane_forward:
        lines += [
            "- Entry lane forward outcomes: "
            f"{_format_forward_rows(list(lane_forward.get('by_primary_lane') or []), limit=5)}",
            "- Entry lane subtype forward outcomes: "
            f"{_format_forward_rows(list(lane_forward.get('by_lane_subtype') or []), limit=5)}",
            "- Entry lane market-rail forward outcomes: "
            f"{_format_forward_rows(list(lane_forward.get('by_market_regime_rail') or []), limit=5)}",
        ]
    below_vwap = (
        evaluation.get("below_vwap_reclaim_observation")
        if isinstance(evaluation.get("below_vwap_reclaim_observation"), Mapping)
        else {}
    )
    if below_vwap and int(below_vwap.get("candidate_count") or 0) > 0:
        lines.append(
            "- Below-VWAP reclaim observation: "
            f"{below_vwap.get('candidate_count') or 0} candidates / "
            f"{_format_rows(list(below_vwap.get('by_subtype') or []), limit=8)}"
        )
    return lines
