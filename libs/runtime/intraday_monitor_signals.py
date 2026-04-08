from __future__ import annotations

import statistics
from dataclasses import replace
from typing import Any, Dict, List, Mapping, Sequence

from libs.runtime.chart_structure_features import (
    build_chart_structure_features,
    empty_chart_structure_features,
)
from libs.runtime.monitor_policy import (
    MonitorEntryPolicy,
    extract_monitor_entry_policy_mapping,
    normalize_monitor_entry_policy_schema,
    normalize_policy_check_spec,
)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _clamp_score(value: float) -> float:
    try:
        return float(max(0.0, min(1.0, float(value))))
    except Exception:
        return 0.0


def _min_threshold_score(actual: float, threshold: float) -> float:
    actual_value = float(actual)
    threshold_value = float(threshold)
    if threshold_value <= 0.0:
        return 1.0 if actual_value > 0.0 else 0.0
    return _clamp_score(actual_value / threshold_value)


def _range_threshold_score(actual: float, minimum: float, maximum: float) -> float:
    actual_value = float(actual)
    minimum_value = float(minimum)
    maximum_value = float(maximum)
    if minimum_value <= actual_value <= maximum_value:
        return 1.0
    if actual_value < minimum_value:
        return _min_threshold_score(actual_value, minimum_value)
    if actual_value <= 0.0:
        return 0.0
    return _clamp_score(maximum_value / actual_value if maximum_value > 0.0 else 0.0)


def _empty_entry_transition_trace() -> Dict[str, Any]:
    return {
        "reclaim_distance_to_ready": None,
        "vwap_reclaim_progress": None,
        "rebound_progress": None,
        "volume_distance_to_ready": None,
        "breakout_distance_to_ready": None,
        "transition_readiness_score": None,
        "last_blocking_axis": "",
        "became_ready_this_cycle": False,
        "extended_from_vwap_improvement": None,
        "volume_ratio_improvement": None,
        "breakout_gap_improvement": None,
        "transition_happening_now": False,
        "volume_recovery_slope": None,
        "volume_recovery_recent": False,
    }


def _env_trueish(value: Any, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    return text in ("1", "true", "yes", "y", "on")


def _resolve_monitor_scoring_settings(scoring: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    raw = dict(scoring or {}) if isinstance(scoring, Mapping) else {}
    enabled = _env_trueish(raw.get("enabled"), False)
    shadow_mode = _env_trueish(raw.get("shadow_mode"), False)
    threshold = _to_float(raw.get("threshold") if raw.get("threshold") not in (None, "") else raw.get("entry_threshold"), 3.0)
    threshold = float(threshold if threshold > 0.0 else 3.0)
    if enabled:
        mode = "enabled"
    elif shadow_mode:
        mode = "shadow"
    else:
        mode = "disabled"
    return {
        "enabled": bool(enabled),
        "shadow_mode": bool(shadow_mode),
        "entry_threshold": threshold,
        "scoring_mode": mode,
    }


def _build_monitor_score_breakdown(
    *,
    vwap_reclaim_ok: bool,
    breakout_ok: bool,
    pullback_mature: bool,
    volume_ok: bool,
    confidence_gate_ok: bool,
) -> Dict[str, float]:
    return {
        "vwap_reclaim_ok": 2.0 if bool(vwap_reclaim_ok) else 0.0,
        "breakout_ok": 2.0 if bool(breakout_ok) else 0.0,
        "pullback_mature": 1.0 if bool(pullback_mature) else 0.0,
        "volume_ok": 1.0 if bool(volume_ok) else 0.0,
        "confidence_gate_ok": 1.0 if bool(confidence_gate_ok) else 0.0,
    }


def _build_monitor_signal_evidence(
    *,
    reclaim_score: float,
    volume_score: float,
    pullback_score: float,
    breakout_score: float,
    confidence_score: float,
    confidence_threshold: float,
    reclaim_ok: bool,
    volume_ok: bool,
    pullback_ok: bool,
    breakout_ok: bool,
    rebound_ok: bool,
    reclaim_gate_ok: bool,
    breakout_path_ok: bool,
    pullback_volume_path_ok: bool,
    extension_ok: bool,
    too_extended: bool,
    reclaim_strength: float,
    rebound_strength: float,
    transition_readiness_score: float,
    reclaim_distance_to_ready: float | None,
    volume_distance_to_ready: float | None,
    breakout_distance_to_ready: float | None,
    score_breakdown: Mapping[str, Any] | None = None,
    score_threshold: float = 3.0,
) -> Dict[str, Any]:
    weighted_scores = dict(score_breakdown or {})
    total_weighted_score = round(sum(_to_float(v) for v in weighted_scores.values()), 4) if weighted_scores else 0.0
    threshold_value = float(score_threshold if score_threshold > 0.0 else 3.0)
    return {
        "scores": {
            "reclaim_score": round(_clamp_score(reclaim_score), 4),
            "volume_score": round(_clamp_score(volume_score), 4),
            "pullback_score": round(_clamp_score(pullback_score), 4),
            "breakout_score": round(_clamp_score(breakout_score), 4),
            "confidence_score": round(_clamp_score(confidence_score), 4),
        },
        "checks": {
            "reclaim_ok": bool(reclaim_ok),
            "volume_ok": bool(volume_ok),
            "pullback_ok": bool(pullback_ok),
            "breakout_ok": bool(breakout_ok),
            "rebound_ok": bool(rebound_ok),
            "reclaim_gate_ok": bool(reclaim_gate_ok),
            "breakout_path_ok": bool(breakout_path_ok),
            "pullback_volume_path_ok": bool(pullback_volume_path_ok),
            "extension_ok": bool(extension_ok),
            "confidence_ok": bool(confidence_score >= confidence_threshold),
        },
        "derived": {
            "too_extended": bool(too_extended),
            "reclaim_strength": round(_clamp_score(reclaim_strength), 4),
            "rebound_strength": round(_clamp_score(rebound_strength), 4),
            "transition_readiness_score": round(_clamp_score(transition_readiness_score), 4),
            "reclaim_distance_to_ready": reclaim_distance_to_ready,
            "volume_distance_to_ready": volume_distance_to_ready,
            "breakout_distance_to_ready": breakout_distance_to_ready,
            "confidence_threshold": round(float(confidence_threshold), 4),
            "weighted_score_total": total_weighted_score,
            "weighted_score_threshold": threshold_value,
            "weighted_score_passed": bool(total_weighted_score >= threshold_value),
        },
        "weighted_scores": weighted_scores,
    }


def _empty_monitor_signal_evidence(*, score_threshold: float = 3.0) -> Dict[str, Any]:
    return _build_monitor_signal_evidence(
        reclaim_score=0.0,
        volume_score=0.0,
        pullback_score=0.0,
        breakout_score=0.0,
        confidence_score=0.0,
        confidence_threshold=0.55,
        reclaim_ok=False,
        volume_ok=False,
        pullback_ok=False,
        breakout_ok=False,
        rebound_ok=False,
        reclaim_gate_ok=False,
        breakout_path_ok=False,
        pullback_volume_path_ok=False,
        extension_ok=False,
        too_extended=False,
        reclaim_strength=0.0,
        rebound_strength=0.0,
        transition_readiness_score=0.0,
        reclaim_distance_to_ready=None,
        volume_distance_to_ready=None,
        breakout_distance_to_ready=None,
        score_breakdown={},
        score_threshold=score_threshold,
    )


def _dedupe_non_empty(values: Sequence[Any]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in list(values or []):
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _volume_priority_hint(volume_ratio_min: float) -> str:
    if float(volume_ratio_min) >= 1.0:
        return "high"
    if float(volume_ratio_min) <= 0.75:
        return "low"
    return "normal"


def _empty_monitor_policy_interpretation() -> Dict[str, Any]:
    return {
        "policy_available": False,
        "entry_style": None,
        "contract_source": None,
        "policy_schema_available": False,
        "policy_schema_version": None,
        "policy_schema_raw_keys": [],
        "interpretation_basis": "none",
        "explicit_fields_used": [],
        "required_checks": [],
        "preferred_checks": [],
        "relaxable_checks": [],
        "blockers": [],
        "priority_hints": {
            "volume_priority": None,
            "reclaim_priority": None,
            "breakout_priority": None,
            "pullback_priority": None,
        },
        "evidence_focus": {
            "primary": [],
            "secondary": [],
        },
        "policy_source": None,
        "policy_adjustments": [],
        "spec_validation_notes": [],
        "notes": [],
    }


def _empty_monitor_policy_interpreter_trace() -> Dict[str, Any]:
    return {
        "available": False,
        "policy_available": False,
        "entry_style": None,
        "focus_alignment": {
            "primary_focus": [],
            "secondary_focus": [],
        },
        "check_status": {
            "required": [],
            "preferred": [],
            "relaxable": [],
            "blockers": [],
        },
        "alignment_summary": {
            "policy_alignment_state": None,
            "primary_blocker": None,
            "secondary_blockers": [],
        },
        "notes": [],
    }


def _empty_monitor_policy_alignment_summary() -> Dict[str, Any]:
    return {
        "available": False,
        "policy_available": False,
        "entry_style": None,
        "alignment_state": None,
        "primary_blocker": None,
        "secondary_blockers": [],
        "focus_mismatch": [],
        "top_failed_required_checks": [],
        "top_failed_preferred_checks": [],
        "top_relaxable_gaps": [],
        "summary_notes": [],
    }


def _empty_monitor_policy_aware_gating() -> Dict[str, Any]:
    return {
        "available": False,
        "applied": False,
        "applied_hints": [],
        "required_failures": [],
        "relaxations_considered": [],
        "relaxations_applied": [],
        "blocked_by_required": [],
        "notes": [],
    }


def _empty_chart_structure_decision_hint() -> Dict[str, Any]:
    return {
        "available": False,
        "applied": False,
        "mode": "none",
        "entry_style": None,
        "considered_features": [],
        "matched_features": [],
        "blocking_features": [],
        "notes": [],
    }


def _extract_explicit_policy_interpretation_fields(
    policy_contract: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    contract = dict(policy_contract or {}) if isinstance(policy_contract, Mapping) else {}
    selected_policy = (
        dict(contract.get("selected_policy") or {})
        if isinstance(contract.get("selected_policy"), Mapping)
        else {}
    )
    schema_candidate = (
        dict(contract.get("selected_policy_schema") or {})
        if isinstance(contract.get("selected_policy_schema"), Mapping)
        else normalize_monitor_entry_policy_schema(selected_policy)
    )
    explicit_fields_used: List[str] = list(
        _dedupe_non_empty(schema_candidate.get("explicit_fields_used") or [])
    )

    def _optional_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _optional_list(value: Any) -> List[str]:
        if isinstance(value, str):
            return _dedupe_non_empty([value])
        if isinstance(value, (list, tuple, set)):
            return _dedupe_non_empty(list(value))
        return []

    def _optional_mapping(value: Any) -> Dict[str, Any]:
        return dict(value or {}) if isinstance(value, Mapping) else {}

    entry_style = _optional_text(schema_candidate.get("entry_style"))
    required_checks = _optional_list(schema_candidate.get("required_checks"))
    preferred_checks = _optional_list(schema_candidate.get("preferred_checks"))
    relaxable_checks = _optional_list(schema_candidate.get("relaxable_checks"))
    blockers = _optional_list(schema_candidate.get("blockers"))
    priority_hints = _optional_mapping(schema_candidate.get("priority_hints"))
    if not any(priority_hints.values()):
        priority_hints = {}
    evidence_focus = _optional_mapping(schema_candidate.get("evidence_focus"))
    notes = _optional_list(schema_candidate.get("notes"))
    policy_adjustments = list(schema_candidate.get("policy_adjustments") or [])
    spec_validation_notes = _optional_list(schema_candidate.get("spec_validation_notes"))

    policy_source = _optional_text(selected_policy.get("policy_source"))

    return {
        "contract_source": _optional_text(contract.get("selected_source")),
        "selected_policy": selected_policy,
        "policy_schema_available": bool(schema_candidate.get("available")),
        "policy_schema_version": _optional_text(schema_candidate.get("schema_version")),
        "policy_schema_raw_keys": _optional_list(schema_candidate.get("raw_keys")),
        "entry_style": entry_style.lower() if isinstance(entry_style, str) else None,
        "required_checks": required_checks,
        "preferred_checks": preferred_checks,
        "relaxable_checks": relaxable_checks,
        "blockers": blockers,
        "priority_hints": priority_hints,
        "evidence_focus": {
            "primary": _optional_list(evidence_focus.get("primary")),
            "secondary": _optional_list(evidence_focus.get("secondary")),
        },
        "notes": notes,
        "policy_adjustments": policy_adjustments,
        "policy_source": policy_source,
        "explicit_fields_used": explicit_fields_used,
        "spec_validation_notes": spec_validation_notes,
    }


def _build_monitor_policy_interpretation(
    *,
    received_policy: Mapping[str, Any] | MonitorEntryPolicy | None = None,
    effective_policy: Mapping[str, Any] | MonitorEntryPolicy | None = None,
    frame: Mapping[str, Any] | None = None,
    policy_contract: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    frame_obj = dict(frame or {}) if isinstance(frame, Mapping) else {}
    playbook = str(frame_obj.get("playbook") or "").strip().lower()
    explicit_fields = _extract_explicit_policy_interpretation_fields(policy_contract)
    explicit_entry_style = str(explicit_fields.get("entry_style") or "").strip().lower()
    source_mapping = (
        extract_monitor_entry_policy_mapping(received_policy)
        if isinstance(received_policy, Mapping)
        else {}
    )
    policy_obj = (
        effective_policy
        if isinstance(effective_policy, MonitorEntryPolicy)
        else MonitorEntryPolicy.from_mapping(effective_policy)
        if isinstance(effective_policy, Mapping) and effective_policy
        else None
    )
    policy_available = bool(source_mapping) or bool(playbook) or bool(explicit_fields.get("selected_policy"))
    interpretation = _empty_monitor_policy_interpretation()
    interpretation["policy_available"] = bool(policy_available)
    interpretation["entry_style"] = explicit_entry_style or playbook or None
    interpretation["contract_source"] = explicit_fields.get("contract_source")
    interpretation["policy_schema_available"] = bool(explicit_fields.get("policy_schema_available"))
    interpretation["policy_schema_version"] = explicit_fields.get("policy_schema_version")
    interpretation["policy_schema_raw_keys"] = list(explicit_fields.get("policy_schema_raw_keys") or [])
    interpretation["explicit_fields_used"] = list(explicit_fields.get("explicit_fields_used") or [])
    interpretation["spec_validation_notes"] = list(explicit_fields.get("spec_validation_notes") or [])
    if not policy_available:
        return interpretation

    required_checks: List[str] = []
    preferred_checks: List[str] = []
    relaxable_checks: List[str] = []
    blockers: List[str] = []
    primary_focus: List[str] = []
    secondary_focus: List[str] = []
    notes: List[str] = []
    volume_ratio_min = 0.68
    policy_enabled = True
    require_vwap_reclaim = False
    require_rebound = False
    interpretation_style = explicit_entry_style or playbook

    if policy_obj is not None:
        volume_ratio_min = float(policy_obj.volume_ratio_min)
        policy_enabled = bool(policy_obj.enabled)
        require_vwap_reclaim = bool(policy_obj.require_vwap_reclaim)
        require_rebound = bool(policy_obj.require_rebound)
        interpretation["policy_source"] = str(policy_obj.policy_source or "") or None
        interpretation["policy_adjustments"] = list(policy_obj.adjustments or [])
    if explicit_fields.get("policy_source"):
        interpretation["policy_source"] = str(explicit_fields.get("policy_source") or "")
    if explicit_fields.get("policy_adjustments"):
        interpretation["policy_adjustments"] = list(explicit_fields.get("policy_adjustments") or [])
    interpretation["priority_hints"] = {
        "volume_priority": _volume_priority_hint(volume_ratio_min),
        "reclaim_priority": "high" if require_vwap_reclaim else "normal",
        "breakout_priority": (
            "high" if interpretation_style == "breakout" else "low" if interpretation_style in ("pullback", "reversal") else "normal"
        ),
        "pullback_priority": (
            "high" if interpretation_style in ("pullback", "reversal") else "low" if interpretation_style == "breakout" else "normal"
        ),
    }
    if not policy_enabled:
        blockers.append("policy_disabled")
    if require_vwap_reclaim and interpretation_style != "breakout":
        required_checks.append("reclaim_gate_ok")
        notes.append("vwap_reclaim_required")
    elif require_vwap_reclaim and interpretation_style == "breakout":
        preferred_checks.append("reclaim_gate_ok")
        relaxable_checks.append("reclaim_gate_ok")
        notes.append("vwap_reclaim_near_ready_relaxable_for_breakout_style")
    if require_rebound and interpretation_style in ("pullback", "reversal"):
        required_checks.append("rebound_ok")
        notes.append("rebound_required_for_pullback_style")
    if volume_ratio_min >= 1.0:
        notes.append("volume_threshold_emphasized")
    elif volume_ratio_min <= 0.75:
        notes.append("volume_threshold_relatively_loose")
        relaxable_checks.append("volume_ok")
    if interpretation_style == "breakout":
        preferred_checks.extend(["breakout_ok", "volume_ok", "reclaim_gate_ok"])
        relaxable_checks.extend(["pullback_ok"])
        primary_focus.extend(["breakout_ok", "volume_ok"])
        secondary_focus.extend(["reclaim_gate_ok", "confidence_ok", "structure_hh_hl", "momentum_follow_through"])
    elif interpretation_style in ("pullback", "reversal"):
        preferred_checks.extend(["pullback_ok", "volume_ok", "vwap_reclaim_ok"])
        relaxable_checks.extend(["breakout_ok"])
        primary_focus.extend(["pullback_ok", "volume_ok"])
        secondary_focus.extend(["reclaim_gate_ok", "rebound_ok", "support_holding", "trend_regime"])
    elif interpretation_style == "defensive":
        preferred_checks.extend(["reclaim_gate_ok", "extension_ok", "confidence_ok"])
        relaxable_checks.extend(["breakout_ok", "pullback_ok"])
        primary_focus.extend(["reclaim_gate_ok", "extension_ok"])
        secondary_focus.extend(["volume_ok", "confidence_ok", "failed_breakout", "momentum_decay"])
    else:
        preferred_checks.extend(["reclaim_gate_ok", "confidence_ok"])
        primary_focus.extend(["reclaim_gate_ok"])
        secondary_focus.extend(["volume_ok", "breakout_ok", "pullback_ok", "trend_regime"])

    fallback_used = False
    if explicit_fields.get("required_checks"):
        required_checks = list(explicit_fields.get("required_checks") or [])
    elif required_checks:
        fallback_used = True
    if explicit_fields.get("preferred_checks"):
        preferred_checks = list(explicit_fields.get("preferred_checks") or [])
    elif preferred_checks:
        fallback_used = True
    if explicit_fields.get("relaxable_checks"):
        relaxable_checks = list(explicit_fields.get("relaxable_checks") or [])
    elif relaxable_checks:
        fallback_used = True
    if explicit_fields.get("blockers"):
        blockers = list(explicit_fields.get("blockers") or [])
    elif blockers:
        fallback_used = True
    if (explicit_fields.get("priority_hints") or {}):
        merged_priority_hints = dict(interpretation.get("priority_hints") or {})
        merged_priority_hints.update(dict(explicit_fields.get("priority_hints") or {}))
        interpretation["priority_hints"] = merged_priority_hints
    elif any((interpretation.get("priority_hints") or {}).values()):
        fallback_used = True
    explicit_focus = dict(explicit_fields.get("evidence_focus") or {})
    if explicit_focus.get("primary") or explicit_focus.get("secondary"):
        primary_focus = list(explicit_focus.get("primary") or primary_focus)
        secondary_focus = list(explicit_focus.get("secondary") or secondary_focus)
    elif primary_focus or secondary_focus:
        fallback_used = True
    if explicit_fields.get("notes"):
        notes = list(explicit_fields.get("notes") or [])
    elif notes:
        fallback_used = True

    explicit_fields_used = list(explicit_fields.get("explicit_fields_used") or [])
    if explicit_fields_used and fallback_used:
        interpretation["interpretation_basis"] = "mixed"
    elif explicit_fields_used:
        interpretation["interpretation_basis"] = "explicit_policy"
    elif policy_available and interpretation_style:
        interpretation["interpretation_basis"] = "fallback_playbook"
    else:
        interpretation["interpretation_basis"] = "none"

    interpretation["required_checks"] = _dedupe_non_empty(required_checks)
    interpretation["preferred_checks"] = _dedupe_non_empty(preferred_checks)
    interpretation["relaxable_checks"] = _dedupe_non_empty(relaxable_checks)
    interpretation["blockers"] = _dedupe_non_empty(blockers)
    interpretation["evidence_focus"] = {
        "primary": _dedupe_non_empty(primary_focus),
        "secondary": _dedupe_non_empty(secondary_focus),
    }
    interpretation["notes"] = _dedupe_non_empty(notes)
    return interpretation


_CHART_FEATURE_GROUP_PATHS: Dict[str, str] = {
    "structure_hh_hl": "structure",
    "structure_range_compression": "structure",
    "structure_breakout_attempt": "structure",
    "ma_alignment_state": "trend_alignment",
    "ma_slope_strength": "trend_alignment",
    "trend_regime": "trend_alignment",
    "support_holding": "support_resistance",
    "resistance_break_confirmed": "support_resistance",
    "failed_breakout": "support_resistance",
    "momentum_follow_through": "continuity_momentum",
    "volume_sustain": "continuity_momentum",
    "momentum_decay": "continuity_momentum",
}


_CHART_FEATURE_STATUS_RULES: Dict[str, Dict[str, set[str]]] = {
    "structure_hh_hl": {
        "pass": {"intact"},
        "fail": {"weakening", "broken"},
        "blocker_active": {"broken"},
        "blocker_inactive": {"intact", "weakening"},
    },
    "structure_range_compression": {
        "pass": {"moderate", "tight"},
        "fail": {"none"},
        "blocker_active": set(),
        "blocker_inactive": {"none", "moderate", "tight"},
    },
    "structure_breakout_attempt": {
        "pass": {"confirmed"},
        "fail": {"rejected"},
        "blocker_active": {"rejected"},
        "blocker_inactive": {"forming", "attempting", "confirmed", "none"},
    },
    "ma_alignment_state": {
        "pass": {"bullish"},
        "fail": {"bearish"},
        "blocker_active": {"bearish"},
        "blocker_inactive": {"bullish", "neutral", "mixed"},
    },
    "ma_slope_strength": {
        "pass": {"rising_strong", "rising_weak"},
        "fail": {"falling_weak", "falling_strong"},
        "blocker_active": {"falling_strong"},
        "blocker_inactive": {"rising_strong", "rising_weak", "flat", "falling_weak"},
    },
    "trend_regime": {
        "pass": {"trending"},
        "fail": set(),
        "blocker_active": set(),
        "blocker_inactive": {"trending", "ranging", "transition"},
    },
    "support_holding": {
        "pass": {"holding"},
        "fail": {"lost"},
        "blocker_active": {"lost"},
        "blocker_inactive": {"holding", "testing"},
    },
    "resistance_break_confirmed": {
        "pass": {"confirmed"},
        "fail": {"failed"},
        "blocker_active": {"failed"},
        "blocker_inactive": {"confirmed", "attempting", "none"},
    },
    "failed_breakout": {
        "pass": {"none"},
        "fail": {"suspected", "confirmed"},
        "blocker_active": {"confirmed"},
        "blocker_inactive": {"none", "suspected"},
    },
    "momentum_follow_through": {
        "pass": {"strong", "moderate"},
        "fail": {"weak", "none"},
        "blocker_active": {"none"},
        "blocker_inactive": {"strong", "moderate", "weak"},
    },
    "volume_sustain": {
        "pass": {"strong", "adequate"},
        "fail": {"fading", "absent"},
        "blocker_active": {"absent"},
        "blocker_inactive": {"strong", "adequate", "fading"},
    },
    "momentum_decay": {
        "pass": {"none"},
        "fail": {"strong"},
        "blocker_active": {"strong"},
        "blocker_inactive": {"none", "mild"},
    },
}


def _flatten_chart_structure_feature_states(
    chart_structure_features: Mapping[str, Any] | None,
) -> Dict[str, Dict[str, Any]]:
    payload = dict(chart_structure_features or {}) if isinstance(chart_structure_features, Mapping) else {}
    if not bool(payload.get("available")):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for name, group in _CHART_FEATURE_GROUP_PATHS.items():
        group_payload = dict(payload.get(group) or {}) if isinstance(payload.get(group), Mapping) else {}
        state = group_payload.get(name)
        if state is None:
            continue
        state_text = str(state or "").strip()
        if not state_text:
            continue
        out[name] = {
            "state": state_text,
            "group": group,
            "source": f"chart_structure_features.{group}.{name}",
        }
    return out


def _parse_policy_signal_spec(spec: Any) -> Dict[str, Any]:
    normalized = normalize_policy_check_spec(spec)
    return {
        "name": str(normalized.get("feature_name") or normalized.get("raw") or "").strip(),
        "expected_state": normalized.get("expected_state"),
        "raw": str(normalized.get("raw") or "").strip(),
        "feature_level": normalized.get("feature_level"),
        "is_valid": bool(normalized.get("is_valid")),
        "validation_notes": list(normalized.get("validation_notes") or []),
    }


def _chart_feature_status_item(
    *,
    spec: Mapping[str, Any],
    chart_states: Mapping[str, Any],
    blocker: bool = False,
) -> Dict[str, Any] | None:
    name = str(spec.get("name") or "").strip()
    expected_state = str(spec.get("expected_state") or "").strip() or None
    feature = dict(chart_states.get(name) or {}) if isinstance(chart_states.get(name), Mapping) else {}
    if not feature:
        return None
    actual_state = str(feature.get("state") or "").strip() or None
    source = feature.get("source")
    status = "unknown"
    if expected_state is not None:
        if actual_state is None:
            status = "unknown"
        elif blocker:
            status = "active" if actual_state == expected_state else "inactive"
        else:
            status = "pass" if actual_state == expected_state else "fail"
    else:
        rules = _CHART_FEATURE_STATUS_RULES.get(name) or {}
        active_states = {str(value).strip() for value in list(rules.get("blocker_active") or set()) if str(value).strip()}
        inactive_states = {str(value).strip() for value in list(rules.get("blocker_inactive") or set()) if str(value).strip()}
        pass_states = {str(value).strip() for value in list(rules.get("pass") or set()) if str(value).strip()}
        fail_states = {str(value).strip() for value in list(rules.get("fail") or set()) if str(value).strip()}
        if blocker:
            if actual_state in active_states:
                status = "active"
            elif actual_state in inactive_states:
                status = "inactive"
        else:
            if actual_state in pass_states:
                status = "pass"
            elif actual_state in fail_states:
                status = "fail"
    return {
        "name": name,
        "expected_state": expected_state,
        "actual_state": actual_state,
        "status": status,
        "source": source,
        "feature_level": "high_level_feature",
        "spec_valid": bool(spec.get("is_valid", True)),
        "validation_notes": list(spec.get("validation_notes") or []),
    }


def _build_monitor_policy_interpreter_trace(
    *,
    policy_interpretation: Mapping[str, Any] | None = None,
    signal_evidence: Mapping[str, Any] | None = None,
    chart_structure_features: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    interpretation = dict(policy_interpretation or {}) if isinstance(policy_interpretation, Mapping) else {}
    evidence = dict(signal_evidence or {}) if isinstance(signal_evidence, Mapping) else {}
    chart_states = _flatten_chart_structure_feature_states(chart_structure_features)
    trace = _empty_monitor_policy_interpreter_trace()

    policy_available = bool(interpretation.get("policy_available"))
    trace["policy_available"] = policy_available
    trace["entry_style"] = interpretation.get("entry_style")
    trace["focus_alignment"] = {
        "primary_focus": _dedupe_non_empty(((interpretation.get("evidence_focus") or {}).get("primary")) or []),
        "secondary_focus": _dedupe_non_empty(((interpretation.get("evidence_focus") or {}).get("secondary")) or []),
    }
    if not policy_available:
        return trace

    checks = dict(evidence.get("checks") or {}) if isinstance(evidence.get("checks"), Mapping) else {}
    derived = dict(evidence.get("derived") or {}) if isinstance(evidence.get("derived"), Mapping) else {}

    def _status_item(spec_value: Any, *, blocker: bool = False) -> Dict[str, Any]:
        spec = _parse_policy_signal_spec(spec_value)
        name = str(spec.get("name") or "").strip()
        if name in checks:
            return {
                "name": str(name),
                "expected_state": None,
                "actual_state": None,
                "status": ("active" if not bool(checks.get(name)) else "inactive") if blocker else ("pass" if bool(checks.get(name)) else "fail"),
                "source": f"signal_evidence.checks.{name}",
                "feature_level": "low_level_signal",
                "spec_valid": bool(spec.get("is_valid", True)),
                "validation_notes": list(spec.get("validation_notes") or []),
            }
        if name in derived:
            value = derived.get(name)
            if isinstance(value, bool):
                return {
                    "name": str(name),
                    "expected_state": None,
                    "actual_state": None,
                    "status": ("active" if bool(value) else "inactive") if blocker else ("pass" if bool(value) else "fail"),
                    "source": f"signal_evidence.derived.{name}",
                    "feature_level": "low_level_signal",
                    "spec_valid": bool(spec.get("is_valid", True)),
                    "validation_notes": list(spec.get("validation_notes") or []),
                }
        feature_item = _chart_feature_status_item(spec=spec, chart_states=chart_states, blocker=blocker)
        if feature_item is not None:
            return feature_item
        return {
            "name": str(name),
            "expected_state": spec.get("expected_state"),
            "actual_state": None,
            "status": "unknown",
            "source": None,
            "feature_level": spec.get("feature_level") or "unknown",
            "spec_valid": bool(spec.get("is_valid")),
            "validation_notes": list(spec.get("validation_notes") or []),
        }

    required_rows = [_status_item(name) for name in _dedupe_non_empty(interpretation.get("required_checks") or [])]
    preferred_rows = [_status_item(name) for name in _dedupe_non_empty(interpretation.get("preferred_checks") or [])]
    relaxable_rows = [_status_item(name) for name in _dedupe_non_empty(interpretation.get("relaxable_checks") or [])]
    blocker_names = _dedupe_non_empty([
        *(interpretation.get("blockers") or []),
        "too_extended" if "too_extended" in derived else "",
    ])
    blocker_rows = [_status_item(name, blocker=True) for name in blocker_names]

    trace["available"] = True
    trace["check_status"] = {
        "required": required_rows,
        "preferred": preferred_rows,
        "relaxable": relaxable_rows,
        "blockers": blocker_rows,
    }

    failed_required = [row["name"] for row in required_rows if row.get("status") == "fail"]
    active_blockers = [row["name"] for row in blocker_rows if row.get("status") == "active"]
    failed_preferred = [row["name"] for row in preferred_rows if row.get("status") == "fail"]

    alignment_state: str | None
    if active_blockers or failed_required:
        alignment_state = "misaligned"
    elif failed_preferred:
        alignment_state = "partial"
    elif required_rows or preferred_rows or relaxable_rows:
        alignment_state = "aligned"
    else:
        alignment_state = "unknown"

    primary_blocker = None
    secondary_blockers: List[str] = []
    blocker_order = [*active_blockers, *failed_required, *failed_preferred]
    if blocker_order:
        primary_blocker = blocker_order[0]
        secondary_blockers = blocker_order[1:]

    trace["alignment_summary"] = {
        "policy_alignment_state": alignment_state,
        "primary_blocker": primary_blocker,
        "secondary_blockers": _dedupe_non_empty(secondary_blockers),
    }
    higher_level_used = any(
        str((row or {}).get("feature_level") or "") == "high_level_feature"
        for row in [*required_rows, *preferred_rows, *relaxable_rows, *blocker_rows]
        if isinstance(row, Mapping)
    )
    notes = list(interpretation.get("notes") or [])
    if higher_level_used:
        notes.append("chart_structure_features_consumed")
    trace["notes"] = _dedupe_non_empty(notes)
    return trace


def _build_monitor_policy_alignment_summary(
    *,
    policy_interpreter_trace: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    trace = dict(policy_interpreter_trace or {}) if isinstance(policy_interpreter_trace, Mapping) else {}
    summary = _empty_monitor_policy_alignment_summary()

    available = bool(trace.get("available"))
    policy_available = bool(trace.get("policy_available"))
    summary["policy_available"] = policy_available
    summary["entry_style"] = trace.get("entry_style")
    if not available:
        return summary

    check_status = dict(trace.get("check_status") or {}) if isinstance(trace.get("check_status"), Mapping) else {}
    alignment_summary = dict(trace.get("alignment_summary") or {}) if isinstance(trace.get("alignment_summary"), Mapping) else {}
    focus_alignment = dict(trace.get("focus_alignment") or {}) if isinstance(trace.get("focus_alignment"), Mapping) else {}

    def _failed(rows: Any, *, statuses: Sequence[str] = ("fail",)) -> List[str]:
        out: List[str] = []
        for row in list(rows or []):
            if not isinstance(row, Mapping):
                continue
            status = str(row.get("status") or "").strip().lower()
            if status not in {str(x).strip().lower() for x in list(statuses or [])}:
                continue
            out.append(str(row.get("name") or "").strip())
        return _dedupe_non_empty(out)

    primary_focus = _dedupe_non_empty(focus_alignment.get("primary_focus") or [])
    secondary_focus = _dedupe_non_empty(focus_alignment.get("secondary_focus") or [])
    failed_required = _failed(check_status.get("required"), statuses=("fail",))
    failed_preferred = _failed(check_status.get("preferred"), statuses=("fail",))
    failed_relaxable = _failed(check_status.get("relaxable"), statuses=("fail",))
    active_blockers = _failed(check_status.get("blockers"), statuses=("active",))
    focus_mismatch = _dedupe_non_empty(
        [
            *(name for name in primary_focus if name in failed_required or name in failed_preferred or name in failed_relaxable),
            *(name for name in secondary_focus if name in failed_required or name in failed_preferred),
        ]
    )

    summary["available"] = True
    summary["alignment_state"] = alignment_summary.get("policy_alignment_state")
    summary["primary_blocker"] = alignment_summary.get("primary_blocker")
    summary["secondary_blockers"] = _dedupe_non_empty(
        [*list(alignment_summary.get("secondary_blockers") or []), *active_blockers]
    )
    summary["focus_mismatch"] = focus_mismatch
    summary["top_failed_required_checks"] = failed_required[:3]
    summary["top_failed_preferred_checks"] = failed_preferred[:3]
    summary["top_relaxable_gaps"] = failed_relaxable[:3]
    summary_notes = list(trace.get("notes") or [])
    high_level_mismatch_present = any(
        str((row or {}).get("feature_level") or "") == "high_level_feature"
        and str((row or {}).get("status") or "") in {"fail", "active"}
        for section in ("required", "preferred", "relaxable", "blockers")
        for row in list(check_status.get(section) or [])
        if isinstance(row, Mapping)
    )
    if high_level_mismatch_present:
        summary_notes.append("higher_level_feature_mismatch_present")
    summary["summary_notes"] = _dedupe_non_empty(summary_notes)
    return summary


def _build_monitor_policy_aware_gating(
    *,
    policy_interpretation: Mapping[str, Any] | None = None,
    signal_evidence: Mapping[str, Any] | None = None,
    policy_interpreter_trace: Mapping[str, Any] | None = None,
    policy_alignment_summary: Mapping[str, Any] | None = None,
    legacy_triggered: bool = False,
    legacy_reason: str | None = None,
) -> Dict[str, Any]:
    interpretation = dict(policy_interpretation or {}) if isinstance(policy_interpretation, Mapping) else {}
    evidence = dict(signal_evidence or {}) if isinstance(signal_evidence, Mapping) else {}
    trace = dict(policy_interpreter_trace or {}) if isinstance(policy_interpreter_trace, Mapping) else {}
    summary = dict(policy_alignment_summary or {}) if isinstance(policy_alignment_summary, Mapping) else {}

    out = _empty_monitor_policy_aware_gating()
    policy_available = bool(interpretation.get("policy_available"))
    if not policy_available:
        return out

    out["available"] = True
    relaxable_checks = _dedupe_non_empty(interpretation.get("relaxable_checks") or [])
    out["relaxations_considered"] = list(relaxable_checks)
    failed_required = _dedupe_non_empty(summary.get("top_failed_required_checks") or [])
    out["required_failures"] = list(failed_required)

    checks = dict(evidence.get("checks") or {}) if isinstance(evidence.get("checks"), Mapping) else {}
    derived = dict(evidence.get("derived") or {}) if isinstance(evidence.get("derived"), Mapping) else {}
    entry_style = str(interpretation.get("entry_style") or "").strip().lower()
    alignment_state = str(summary.get("alignment_state") or "").strip().lower()
    legacy_reason_code = str(legacy_reason or "").strip()

    if failed_required:
        out["blocked_by_required"] = list(failed_required)
        out["notes"] = _dedupe_non_empty(
            [
                *list(out.get("notes") or []),
                "required_checks_failed",
            ]
        )
        return out
    if bool(legacy_triggered):
        out["notes"] = _dedupe_non_empty([*list(out.get("notes") or []), "legacy_gate_already_triggered"])
        return out

    can_consider_reclaim_relax = (
        entry_style == "breakout"
        and "reclaim_gate_ok" in relaxable_checks
    )
    if not can_consider_reclaim_relax:
        return out

    reclaim_distance = derived.get("reclaim_distance_to_ready")
    near_ready = reclaim_distance is not None and -0.0015 <= float(reclaim_distance) < 0.0
    safe_to_relax = (
        bool(checks.get("breakout_path_ok"))
        and bool(checks.get("confidence_ok"))
        and not bool(derived.get("too_extended"))
        and alignment_state in {"aligned", "partial"}
    )
    relaxable_reason = legacy_reason_code in {
        "",
        "below_vwap_reclaim_not_ready",
    }
    if not relaxable_reason:
        out["notes"] = _dedupe_non_empty([*list(out.get("notes") or []), "legacy_reason_not_relaxable"])
        return out
    if bool(checks.get("reclaim_gate_ok")):
        out["notes"] = _dedupe_non_empty([*list(out.get("notes") or []), "reclaim_gate_already_passed"])
        return out
    if not near_ready:
        out["notes"] = _dedupe_non_empty([*list(out.get("notes") or []), "reclaim_not_near_ready"])
        return out
    if not safe_to_relax:
        out["notes"] = _dedupe_non_empty([*list(out.get("notes") or []), "safe_relaxation_conditions_not_met"])
        return out
    if not (bool(checks.get("volume_ok")) or bool(checks.get("breakout_path_ok"))):
        out["notes"] = _dedupe_non_empty([*list(out.get("notes") or []), "supporting_path_not_ready"])
        return out

    out["applied"] = True
    out["applied_hints"] = ["reclaim_relaxed_near_ready"]
    out["relaxations_applied"] = ["reclaim_gate_ok"]
    out["notes"] = _dedupe_non_empty([*list(out.get("notes") or []), "breakout_reclaim_near_ready_relaxation_applied"])
    return out


def _build_chart_structure_decision_hint(
    *,
    policy_interpretation: Mapping[str, Any] | None = None,
    signal_evidence: Mapping[str, Any] | None = None,
    chart_structure_features: Mapping[str, Any] | None = None,
    legacy_triggered: bool = False,
    legacy_decision: str | None = None,
    legacy_reason: str | None = None,
    legacy_entry_condition_path: str | None = None,
) -> Dict[str, Any]:
    interpretation = dict(policy_interpretation or {}) if isinstance(policy_interpretation, Mapping) else {}
    evidence = dict(signal_evidence or {}) if isinstance(signal_evidence, Mapping) else {}
    chart_payload = dict(chart_structure_features or {}) if isinstance(chart_structure_features, Mapping) else {}
    out = _empty_chart_structure_decision_hint()

    policy_available = bool(interpretation.get("policy_available"))
    if not policy_available:
        return out

    out["available"] = True
    entry_style = str(interpretation.get("entry_style") or "").strip().lower() or None
    out["entry_style"] = entry_style
    if entry_style == "breakout":
        out["considered_features"] = [
            "structure_hh_hl",
            "momentum_follow_through",
            "failed_breakout",
        ]
    elif entry_style in {"pullback", "reversal"}:
        out["considered_features"] = [
            "support_holding",
            "trend_regime",
            "ma_alignment_state",
        ]
    else:
        out["notes"] = ["entry_style_not_chart_structure_guard_target"]
        return out

    if not bool(chart_payload.get("available")):
        out["notes"] = ["chart_structure_features_unavailable"]
        return out

    if not bool(legacy_triggered) or str(legacy_decision or "").strip().upper() != "BUY":
        out["notes"] = ["legacy_decision_not_structure_guard_target_buy"]
        return out

    chart_states = _flatten_chart_structure_feature_states(chart_payload)
    checks = dict(evidence.get("checks") or {}) if isinstance(evidence.get("checks"), Mapping) else {}
    if entry_style == "breakout":
        if str(legacy_entry_condition_path or "").strip() != "breakout_path":
            out["notes"] = ["legacy_entry_path_not_breakout"]
            return out

        structure_state = str(((chart_states.get("structure_hh_hl") or {}).get("state")) or "").strip().lower()
        follow_through_state = str(((chart_states.get("momentum_follow_through") or {}).get("state")) or "").strip().lower()
        failed_breakout_state = str(((chart_states.get("failed_breakout") or {}).get("state")) or "").strip().lower()

        if structure_state == "intact":
            out["matched_features"].append("structure_hh_hl=intact")
        elif structure_state:
            out["blocking_features"].append(f"structure_hh_hl={structure_state}")
        if follow_through_state == "strong":
            out["matched_features"].append("momentum_follow_through=strong")
        elif follow_through_state:
            out["blocking_features"].append(f"momentum_follow_through={follow_through_state}")
        if failed_breakout_state == "none":
            out["matched_features"].append("failed_breakout=none")
        elif failed_breakout_state:
            out["blocking_features"].append(f"failed_breakout={failed_breakout_state}")

        if not bool(checks.get("breakout_path_ok")):
            out["notes"] = _dedupe_non_empty([*list(out.get("notes") or []), "breakout_path_not_confirmed"])
            return out
        if not bool(checks.get("confidence_ok")):
            out["notes"] = _dedupe_non_empty([*list(out.get("notes") or []), "confidence_not_confirmed"])
            return out

        should_block = False
        if failed_breakout_state == "confirmed":
            should_block = True
        elif structure_state == "weakening" and follow_through_state in {"moderate", "weak", "none"}:
            should_block = True

        if not should_block:
            out["notes"] = _dedupe_non_empty([*list(out.get("notes") or []), "continuation_quality_not_blocking"])
            return out

        out["applied"] = True
        out["mode"] = "block"
        out["notes"] = _dedupe_non_empty(
            [
                *list(out.get("notes") or []),
                "breakout_continuation_structure_guard_applied",
                str(legacy_reason or "").strip() or "legacy_reason_not_provided",
            ]
        )
        return out

    if str(legacy_entry_condition_path or "").strip() != "pullback_volume_path":
        out["notes"] = ["legacy_entry_path_not_pullback"]
        return out

    support_state = str(((chart_states.get("support_holding") or {}).get("state")) or "").strip().lower()
    trend_regime_state = str(((chart_states.get("trend_regime") or {}).get("state")) or "").strip().lower()
    ma_alignment_state = str(((chart_states.get("ma_alignment_state") or {}).get("state")) or "").strip().lower()

    if support_state == "holding":
        out["matched_features"].append("support_holding=holding")
    elif support_state:
        out["blocking_features"].append(f"support_holding={support_state}")
    if trend_regime_state == "trending":
        out["matched_features"].append("trend_regime=trending")
    elif trend_regime_state:
        out["blocking_features"].append(f"trend_regime={trend_regime_state}")
    if ma_alignment_state == "bullish":
        out["matched_features"].append("ma_alignment_state=bullish")
    elif ma_alignment_state:
        out["blocking_features"].append(f"ma_alignment_state={ma_alignment_state}")

    if not bool(checks.get("pullback_volume_path_ok")):
        out["notes"] = _dedupe_non_empty([*list(out.get("notes") or []), "pullback_path_not_confirmed"])
        return out
    if not bool(checks.get("confidence_ok")):
        out["notes"] = _dedupe_non_empty([*list(out.get("notes") or []), "confidence_not_confirmed"])
        return out

    should_block = False
    if support_state == "lost":
        should_block = True
    elif ma_alignment_state == "bearish" and trend_regime_state in {"transition", "ranging"}:
        should_block = True

    if not should_block:
        out["notes"] = _dedupe_non_empty([*list(out.get("notes") or []), "pullback_structure_not_blocking"])
        return out

    out["applied"] = True
    out["mode"] = "block"
    out["notes"] = _dedupe_non_empty(
        [
            *list(out.get("notes") or []),
            "pullback_reversal_structure_guard_applied",
            str(legacy_reason or "").strip() or "legacy_reason_not_provided",
        ]
    )
    return out


def _apply_monitor_scoring_fields(
    out: Dict[str, Any],
    *,
    scoring_settings: Dict[str, Any],
    hard_filter_passed: bool,
    hard_filter_fail_reasons: Sequence[str] | None,
    score_breakdown: Mapping[str, Any] | None = None,
    legacy_entry_decision: str = "WAIT",
    scoring_entry_decision: str = "WAIT",
) -> Dict[str, Any]:
    breakdown = dict(score_breakdown or {})
    total_score = round(sum(_to_float(v) for v in breakdown.values()), 4) if breakdown else 0.0
    threshold = float(scoring_settings.get("entry_threshold") or 3.0)
    score_passed = bool(hard_filter_passed) and total_score >= threshold
    fail_reasons = [str(x or "").strip() for x in list(hard_filter_fail_reasons or []) if str(x or "").strip()]
    out["hard_filter_passed"] = bool(hard_filter_passed)
    out["hard_filter_fail_reasons"] = fail_reasons
    out["total_score"] = total_score
    out["score_breakdown"] = breakdown
    out["entry_threshold"] = threshold
    out["score_passed"] = bool(score_passed)
    out["scoring_mode"] = str(scoring_settings.get("scoring_mode") or "disabled")
    out["legacy_entry_decision"] = str(legacy_entry_decision or "WAIT")
    out["scoring_entry_decision"] = str(scoring_entry_decision or ("BUY" if score_passed else "WAIT"))
    return out


def _candles_from_rows(rows: Sequence[Mapping[str, Any]] | None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in list(rows or []):
        if not isinstance(raw, Mapping):
            continue
        open_px = _to_float(raw.get("open"))
        high_px = _to_float(raw.get("high"))
        low_px = _to_float(raw.get("low"))
        close_px = _to_float(raw.get("close"))
        volume = _to_float(raw.get("volume"))
        if high_px <= 0.0 and low_px <= 0.0 and close_px <= 0.0:
            continue
        out.append(
            {
                "ts": raw.get("ts"),
                "open": open_px or close_px,
                "high": max(high_px, open_px, close_px),
                "low": min(low_px if low_px > 0.0 else close_px or open_px, open_px or close_px, close_px or open_px),
                "close": close_px or open_px,
                "volume": max(0.0, volume),
                "vwap": raw.get("vwap"),
            }
        )
    return out


def _merge_candle_group(group: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = [row for row in group if isinstance(row, Mapping)]
    if not rows:
        return {}
    open_px = _to_float(rows[0].get("open"))
    close_px = _to_float(rows[-1].get("close"))
    high_px = max(_to_float(row.get("high"), close_px) for row in rows)
    low_px = min(_to_float(row.get("low"), open_px if open_px > 0.0 else close_px) for row in rows)
    volume = sum(max(0.0, _to_float(row.get("volume"))) for row in rows)
    weighted_vwap_num = 0.0
    weighted_vwap_den = 0.0
    for row in rows:
        row_volume = max(0.0, _to_float(row.get("volume")))
        row_vwap = _to_float(row.get("vwap"))
        if row_volume > 0.0 and row_vwap > 0.0:
            weighted_vwap_num += row_vwap * row_volume
            weighted_vwap_den += row_volume
    merged: Dict[str, Any] = {
        "ts": rows[-1].get("ts"),
        "open": open_px or close_px,
        "high": high_px,
        "low": low_px,
        "close": close_px or open_px,
        "volume": volume,
    }
    if weighted_vwap_den > 0.0:
        merged["vwap"] = weighted_vwap_num / weighted_vwap_den
    return merged


def _compress_candles(rows: Sequence[Mapping[str, Any]], timeframe_minutes: int) -> List[Dict[str, Any]]:
    candles = _candles_from_rows(rows)
    bucket = max(1, int(timeframe_minutes or 1))
    if bucket <= 1 or len(candles) <= 1:
        return candles
    out: List[Dict[str, Any]] = []
    chunk: List[Mapping[str, Any]] = []
    for row in candles:
        chunk.append(row)
        if len(chunk) >= bucket:
            merged = _merge_candle_group(chunk)
            if merged:
                out.append(merged)
            chunk = []
    if chunk:
        merged = _merge_candle_group(chunk)
        if merged:
            out.append(merged)
    return out


def _session_vwap(candles: Sequence[Mapping[str, Any]]) -> float | None:
    weighted_num = 0.0
    weighted_den = 0.0
    for row in candles:
        volume = max(0.0, _to_float(row.get("volume")))
        if volume <= 0.0:
            continue
        vwap = _to_float(row.get("vwap"))
        if vwap <= 0.0:
            high_px = _to_float(row.get("high"))
            low_px = _to_float(row.get("low"))
            close_px = _to_float(row.get("close"))
            vwap = (high_px + low_px + close_px) / 3.0
        if vwap <= 0.0:
            continue
        weighted_num += vwap * volume
        weighted_den += volume
    if weighted_den <= 0.0:
        return None
    return weighted_num / weighted_den


def _infer_spacing_seconds(candles: Sequence[Mapping[str, Any]]) -> float | None:
    ts_values: List[int] = []
    for row in candles:
        ts = _to_int(row.get("ts"), 0)
        if ts > 0:
            ts_values.append(ts)
    if len(ts_values) < 4:
        return None
    diffs: List[int] = []
    for prev_ts, cur_ts in zip(ts_values, ts_values[1:]):
        diff = int(cur_ts) - int(prev_ts)
        if diff > 0:
            diffs.append(diff)
    if len(diffs) < 3:
        return None
    try:
        return float(statistics.median(diffs))
    except Exception:
        return None


def _classify_series_quality(
    candles: Sequence[Mapping[str, Any]],
    *,
    timeframe_minutes: int,
) -> Dict[str, Any]:
    spacing_seconds = _infer_spacing_seconds(candles)
    if spacing_seconds is None:
        return {
            "intraday_compatible": True,
            "inferred_spacing_seconds": None,
            "inferred_spacing_minutes": None,
            "series_class": "unknown",
            "compatibility_reason": "timestamp_missing",
        }

    spacing_minutes = spacing_seconds / 60.0
    max_intraday_spacing_seconds = max(1800.0, float(max(1, timeframe_minutes)) * 60.0 * 6.0)
    intraday_compatible = spacing_seconds <= max_intraday_spacing_seconds
    if intraday_compatible:
        series_class = "intraday"
        compatibility_reason = "intraday_spacing_detected"
    elif spacing_seconds >= 12 * 3600:
        series_class = "daily_or_higher"
        compatibility_reason = "non_intraday_spacing_detected"
    else:
        series_class = "higher_timeframe"
        compatibility_reason = "non_intraday_spacing_detected"
    return {
        "intraday_compatible": intraday_compatible,
        "inferred_spacing_seconds": round(spacing_seconds, 3),
        "inferred_spacing_minutes": round(spacing_minutes, 3),
        "series_class": series_class,
        "compatibility_reason": compatibility_reason,
    }


def resolve_intraday_entry_policy(
    policy: Mapping[str, Any] | MonitorEntryPolicy | None = None,
    *,
    frame: Mapping[str, Any] | None = None,
) -> MonitorEntryPolicy:
    resolved = policy if isinstance(policy, MonitorEntryPolicy) else MonitorEntryPolicy.from_mapping(policy)
    adjustments: List[str] = []
    playbook = str((frame or {}).get("playbook") or "").strip().lower()
    guidance = str((frame or {}).get("monitor_guidance") or "").strip().lower()
    risk_tone = str((frame or {}).get("risk_tone") or "").strip().lower()
    aggressiveness = str((frame or {}).get("trade_aggressiveness") or "").strip().lower()

    if playbook == "breakout":
        resolved = replace(
            resolved,
            volume_ratio_min=max(1.0, float(resolved.volume_ratio_min)),
            max_extended_from_vwap_pct=min(0.03, max(float(resolved.max_extended_from_vwap_pct), 0.02)),
            pullback_max_pct=min(0.04, max(float(resolved.pullback_max_pct), 0.03)),
        )
        adjustments.append("playbook:breakout")
    elif playbook in ("pullback", "reversal"):
        resolved = replace(
            resolved,
            breakout_lookback=max(3, int(resolved.breakout_lookback) - 1),
            volume_ratio_min=max(0.68, min(float(resolved.volume_ratio_min), 0.9)),
            min_extended_from_vwap_pct=min(float(resolved.min_extended_from_vwap_pct), -0.005),
            max_extended_from_vwap_pct=max(float(resolved.max_extended_from_vwap_pct), 0.05),
            pullback_min_pct=max(0.008, float(resolved.pullback_min_pct) - 0.004),
            pullback_max_pct=max(float(resolved.pullback_max_pct), 0.06),
        )
        # Keep shallow pullback entries available during live pullback monitoring.
        adjustments.append(f"playbook:{playbook}")
    elif playbook == "defensive":
        resolved = replace(
            resolved,
            volume_ratio_min=min(1.1, float(resolved.volume_ratio_min) + 0.03),
            max_extended_from_vwap_pct=max(0.03, min(float(resolved.max_extended_from_vwap_pct), 0.05)),
            pullback_max_pct=min(float(resolved.pullback_max_pct), 0.05),
        )
        adjustments.append("playbook:defensive")

    if guidance == "hold_through_noise":
        resolved = replace(
            resolved,
            pullback_max_pct=min(0.07, float(resolved.pullback_max_pct) + 0.005),
        )
        adjustments.append("guidance:hold_through_noise")
    elif guidance == "defensive_exit":
        if playbook in ("pullback", "reversal"):
            resolved = replace(
                resolved,
                volume_ratio_min=max(0.68, min(1.0, float(resolved.volume_ratio_min) - 0.04)),
                max_extended_from_vwap_pct=max(0.05, float(resolved.max_extended_from_vwap_pct)),
            )
            adjustments.append("guidance:defensive_exit_pullback")
        else:
            next_max_extended = float(resolved.max_extended_from_vwap_pct)
            if playbook != "defensive":
                next_max_extended = max(0.03, float(resolved.max_extended_from_vwap_pct) - 0.0025)
            resolved = replace(
                resolved,
                volume_ratio_min=min(1.1, float(resolved.volume_ratio_min) + 0.01),
                max_extended_from_vwap_pct=next_max_extended,
            )
            adjustments.append("guidance:defensive_exit")

    if risk_tone == "conservative":
        if playbook in ("pullback", "reversal"):
            resolved = replace(
                resolved,
                volume_ratio_min=min(1.0, float(resolved.volume_ratio_min)),
                max_extended_from_vwap_pct=max(0.05, float(resolved.max_extended_from_vwap_pct)),
            )
            adjustments.append("risk_tone:conservative_pullback")
        else:
            next_max_extended = float(resolved.max_extended_from_vwap_pct)
            if playbook != "defensive":
                next_max_extended = max(0.03, float(resolved.max_extended_from_vwap_pct) - 0.0025)
            resolved = replace(
                resolved,
                volume_ratio_min=min(1.1, float(resolved.volume_ratio_min) + 0.01),
                max_extended_from_vwap_pct=next_max_extended,
            )
            adjustments.append("risk_tone:conservative")
    elif risk_tone == "aggressive":
        resolved = replace(
            resolved,
            volume_ratio_min=max(0.9, float(resolved.volume_ratio_min) - 0.05),
            max_extended_from_vwap_pct=min(0.08, float(resolved.max_extended_from_vwap_pct) + 0.01),
        )
        adjustments.append("risk_tone:aggressive")

    if aggressiveness == "low":
        if playbook in ("pullback", "reversal"):
            resolved = replace(
                resolved,
                volume_ratio_min=min(1.1, float(resolved.volume_ratio_min) + 0.02),
            )
            adjustments.append("trade_aggressiveness:low_pullback")
        else:
            resolved = replace(
                resolved,
                volume_ratio_min=min(1.2, float(resolved.volume_ratio_min) + 0.02),
            )
            adjustments.append("trade_aggressiveness:low")
    elif aggressiveness == "high":
        resolved = replace(
            resolved,
            volume_ratio_min=max(0.9, float(resolved.volume_ratio_min) - 0.05),
            max_extended_from_vwap_pct=min(0.08, float(resolved.max_extended_from_vwap_pct) + 0.005),
        )
        adjustments.append("trade_aggressiveness:high")

    return replace(resolved, adjustments=tuple(adjustments))


def evaluate_intraday_entry_signal(
    rows: Sequence[Mapping[str, Any]] | None,
    *,
    current_price: Any = None,
    features: Mapping[str, Any] | None = None,
    policy: Mapping[str, Any] | MonitorEntryPolicy | None = None,
    frame: Mapping[str, Any] | None = None,
    scoring: Mapping[str, Any] | None = None,
    policy_contract: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    # When monitor passes a MonitorEntryPolicy instance, it has already resolved
    # the strategy frame for this cycle. Re-applying the frame here would tighten
    # thresholds a second time and drift away from the commander-confirmed baseline.
    resolved_policy = (
        policy
        if isinstance(policy, MonitorEntryPolicy)
        else resolve_intraday_entry_policy(policy, frame=frame)
    )
    applied_policy = resolved_policy.to_dict()
    scoring_settings = _resolve_monitor_scoring_settings(scoring)
    timeframe_minutes = int(resolved_policy.timeframe_minutes or 1)
    candles = _compress_candles(rows or [], timeframe_minutes)
    out: Dict[str, Any] = {
        "enabled": bool(resolved_policy.enabled),
        "evaluated": False,
        "triggered": False,
        "decision": "WAIT",
        "reason": "",
        "pattern": "",
        "signal_chain": [],
        "metrics": {},
        "thresholds": dict(applied_policy),
        "applied_policy": dict(applied_policy),
    }
    out.update(_empty_entry_transition_trace())
    out["entry_transition_trace"] = _empty_entry_transition_trace()
    out["signal_evidence"] = _empty_monitor_signal_evidence(
        score_threshold=float(scoring_settings.get("entry_threshold") or 3.0)
    )
    out["chart_structure_features"] = empty_chart_structure_features()
    out["policy_interpretation"] = _build_monitor_policy_interpretation(
        received_policy=policy if isinstance(policy, (Mapping, MonitorEntryPolicy)) else None,
        effective_policy=resolved_policy,
        frame=frame,
        policy_contract=policy_contract,
    )
    out["policy_interpreter_trace"] = _empty_monitor_policy_interpreter_trace()
    out["policy_alignment_summary"] = _empty_monitor_policy_alignment_summary()
    out["policy_aware_gating"] = _empty_monitor_policy_aware_gating()
    out["chart_structure_decision_hint"] = _empty_chart_structure_decision_hint()
    _apply_monitor_scoring_fields(
        out,
        scoring_settings=scoring_settings,
        hard_filter_passed=False,
        hard_filter_fail_reasons=[],
        score_breakdown={},
        legacy_entry_decision="WAIT",
        scoring_entry_decision="WAIT",
    )
    if not out["enabled"]:
        out["reason"] = "intraday_entry_disabled"
        return out
    if not candles:
        out["reason"] = "minute_candle_missing"
        out["metrics"] = {
            "bar_count": 0,
            "min_required_bars": 0,
            "timeframe_minutes": timeframe_minutes,
            "price": _to_float(current_price) if _to_float(current_price) > 0.0 else None,
            "vwap": None,
            "vwap_distance": None,
            "volume_ratio": None,
            "recent_high": None,
            "pullback_pct": None,
        }
        _apply_monitor_scoring_fields(
            out,
            scoring_settings=scoring_settings,
            hard_filter_passed=False,
            hard_filter_fail_reasons=["minute_candle_missing"],
            score_breakdown={},
            legacy_entry_decision="WAIT",
            scoring_entry_decision="WAIT",
        )
        return out
    min_required_bars = max(
        int(resolved_policy.breakout_lookback or 5) + 1,
        int(resolved_policy.volume_lookback or 5) + 1,
        4,
    )
    series_quality = _classify_series_quality(candles, timeframe_minutes=timeframe_minutes)
    out["series_quality"] = dict(series_quality)
    if not bool(series_quality.get("intraday_compatible")):
        out["reason"] = "minute_candle_missing"
        out["metrics"] = {
            "bar_count": len(candles),
            "min_required_bars": min_required_bars,
            "timeframe_minutes": timeframe_minutes,
            "price": _to_float(current_price) if _to_float(current_price) > 0.0 else None,
            "vwap": _to_float(_session_vwap(candles), 0.0) or None,
            "vwap_distance": None,
            "volume_ratio": None,
            "recent_high": None,
            "pullback_pct": None,
            "inferred_spacing_minutes": series_quality.get("inferred_spacing_minutes"),
            "series_class": series_quality.get("series_class"),
            "compatibility_reason": series_quality.get("compatibility_reason"),
        }
        _apply_monitor_scoring_fields(
            out,
            scoring_settings=scoring_settings,
            hard_filter_passed=False,
            hard_filter_fail_reasons=["minute_candle_missing"],
            score_breakdown={},
            legacy_entry_decision="WAIT",
            scoring_entry_decision="WAIT",
        )
        return out
    if len(candles) < min_required_bars:
        out["reason"] = "data_incomplete"
        out["metrics"] = {
            "bar_count": len(candles),
            "min_required_bars": min_required_bars,
            "timeframe_minutes": timeframe_minutes,
            "price": _to_float(current_price) if _to_float(current_price) > 0.0 else None,
            "vwap": _to_float(_session_vwap(candles), 0.0) or None,
            "vwap_distance": None,
            "volume_ratio": None,
            "recent_high": None,
            "pullback_pct": None,
            "inferred_spacing_minutes": series_quality.get("inferred_spacing_minutes"),
            "series_class": series_quality.get("series_class"),
        }
        _apply_monitor_scoring_fields(
            out,
            scoring_settings=scoring_settings,
            hard_filter_passed=False,
            hard_filter_fail_reasons=["data_incomplete"],
            score_breakdown={},
            legacy_entry_decision="WAIT",
            scoring_entry_decision="WAIT",
        )
        return out

    out["evaluated"] = True
    last = candles[-1]
    prior = candles[-2]
    lookback = int(resolved_policy.breakout_lookback or 5)
    volume_lookback = int(resolved_policy.volume_lookback or 5)
    breakout_window = candles[-(lookback + 1):-1]
    volume_window = candles[-(volume_lookback + 1):-1]
    recent_high = max(_to_float(row.get("high")) for row in breakout_window)
    prior_bar_high = _to_float(prior.get("high"))
    prior_bar_low = _to_float(prior.get("low"))
    current_close = _to_float(current_price, _to_float(last.get("close")))
    current_high = _to_float(last.get("high"))
    current_low = _to_float(last.get("low"))
    current_volume = max(0.0, _to_float(last.get("volume")))
    average_volume = 0.0
    if volume_window:
        average_volume = sum(max(0.0, _to_float(row.get("volume"))) for row in volume_window) / float(len(volume_window))
    volume_ratio = (current_volume / average_volume) if average_volume > 0.0 else 0.0

    current_vwap = _to_float(last.get("vwap"))
    if current_vwap <= 0.0:
        current_vwap = _to_float(_session_vwap(candles), 0.0)
    previous_vwap = _to_float(prior.get("vwap"))
    if previous_vwap <= 0.0:
        previous_vwap = current_vwap

    extended_from_vwap_pct = 0.0
    if current_vwap > 0.0 and current_close > 0.0:
        extended_from_vwap_pct = (current_close / current_vwap) - 1.0

    prior_close = _to_float(prior.get("close"))
    reclaim_tolerance_pct = _to_float(resolved_policy.reclaim_tolerance_pct)
    breakout_buffer_pct = _to_float(resolved_policy.breakout_buffer_pct)
    breakout_level = recent_high * (1.0 + breakout_buffer_pct) if recent_high > 0.0 else 0.0
    breakout_ok = breakout_level > 0.0 and current_close >= breakout_level and current_high >= recent_high
    vwap_hold_ok = current_vwap > 0.0 and current_close >= current_vwap * (1.0 - reclaim_tolerance_pct)
    vwap_reclaim_ok = (
        current_vwap > 0.0
        and prior_close < previous_vwap * (1.0 - reclaim_tolerance_pct)
        and current_close >= current_vwap * (1.0 - reclaim_tolerance_pct)
    )
    pullback_lows = [max(0.0, _to_float(row.get("low"))) for row in candles[-4:-1]]
    pullback_floor = min([px for px in pullback_lows if px > 0.0], default=0.0)
    pullback_depth_pct = ((recent_high - pullback_floor) / recent_high) if recent_high > 0.0 and pullback_floor > 0.0 else 0.0
    rebound_ok = current_close > prior_bar_high and current_close >= prior_close
    volume_ok = volume_ratio >= _to_float(resolved_policy.volume_ratio_min)
    min_extended_from_vwap_pct = _to_float(resolved_policy.min_extended_from_vwap_pct)
    max_extended_from_vwap_pct = _to_float(resolved_policy.max_extended_from_vwap_pct)
    extension_ok = min_extended_from_vwap_pct <= extended_from_vwap_pct <= max_extended_from_vwap_pct
    pullback_min_pct = _to_float(resolved_policy.pullback_min_pct)
    pullback_max_pct = _to_float(resolved_policy.pullback_max_pct)
    pullback_mature = pullback_depth_pct >= pullback_min_pct
    pullback_not_too_deep = pullback_depth_pct <= pullback_max_pct
    pullback_ok = pullback_mature and pullback_not_too_deep
    vwap_structure_ok = vwap_hold_ok or vwap_reclaim_ok
    confirmation_ok = volume_ok or rebound_ok or vwap_reclaim_ok
    reclaim_gate_ok = bool(vwap_structure_ok) if bool(resolved_policy.require_vwap_reclaim) else True
    breakout_path_ok = bool(breakout_ok)
    pullback_volume_path_ok = bool(pullback_ok and volume_ok)
    breakout_score = 1.0 if breakout_ok else _clamp_score((current_close / breakout_level) if breakout_level > 0.0 and current_close > 0.0 else 0.0)
    volume_score = _min_threshold_score(volume_ratio, _to_float(resolved_policy.volume_ratio_min))
    pullback_score = min(
        _min_threshold_score(pullback_depth_pct, pullback_min_pct if pullback_min_pct > 0.0 else 1e-9),
        _range_threshold_score(pullback_depth_pct, 0.0, pullback_max_pct if pullback_max_pct > 0.0 else max(pullback_depth_pct, 1e-9)),
    )
    breakout_path_score = round(0.55 * breakout_score, 4)
    pullback_volume_path_score = round((0.30 * pullback_score) + (0.25 * volume_score), 4)
    confidence_threshold = 0.55
    confidence_score = round(max(breakout_path_score, pullback_volume_path_score), 4)
    confidence_gate_ok = confidence_score >= confidence_threshold
    breakout_gap_pct = ((current_close / recent_high) - 1.0) if recent_high > 0.0 and current_close > 0.0 else None
    reclaim_ready_level_pct = -reclaim_tolerance_pct
    reclaim_distance_to_ready = (
        extended_from_vwap_pct - reclaim_ready_level_pct
        if current_vwap > 0.0 and current_close > 0.0
        else None
    )
    reclaim_progress_band = max(1e-6, abs(reclaim_ready_level_pct - min_extended_from_vwap_pct))
    vwap_reclaim_progress = _clamp_score(
        (extended_from_vwap_pct - min_extended_from_vwap_pct) / reclaim_progress_band
    )
    rebound_high_progress = _clamp_score((current_close / prior_bar_high) if prior_bar_high > 0.0 and current_close > 0.0 else 0.0)
    rebound_close_progress = _clamp_score((current_close / prior_close) if prior_close > 0.0 and current_close > 0.0 else 0.0)
    rebound_progress = round(min(rebound_high_progress, rebound_close_progress), 4)
    volume_distance_to_ready = volume_ratio - _to_float(resolved_policy.volume_ratio_min)
    breakout_distance_to_ready = (
        breakout_gap_pct - breakout_buffer_pct
        if breakout_gap_pct is not None
        else None
    )
    transition_readiness_score = round(
        _clamp_score(
            (0.35 * vwap_reclaim_progress)
            + (0.25 * volume_score)
            + (0.20 * breakout_score)
            + (0.20 * rebound_progress)
        ),
        4,
    )

    if current_close <= 0.0 or recent_high <= 0.0 or current_vwap <= 0.0:
        out["reason"] = "data_incomplete"
        out["metrics"] = {
            "timeframe_minutes": timeframe_minutes,
            "bar_count": len(candles),
            "price": current_close if current_close > 0.0 else None,
            "vwap": current_vwap if current_vwap > 0.0 else None,
            "vwap_distance": extended_from_vwap_pct if current_vwap > 0.0 and current_close > 0.0 else None,
            "volume_ratio": volume_ratio if volume_ratio > 0.0 else None,
            "recent_high": recent_high if recent_high > 0.0 else None,
            "pullback_pct": pullback_depth_pct,
            "inferred_spacing_minutes": series_quality.get("inferred_spacing_minutes"),
            "series_class": series_quality.get("series_class"),
        }
        _apply_monitor_scoring_fields(
            out,
            scoring_settings=scoring_settings,
            hard_filter_passed=False,
            hard_filter_fail_reasons=["data_incomplete"],
            score_breakdown={},
            legacy_entry_decision="WAIT",
            scoring_entry_decision="WAIT",
        )
        return out

    signal_chain: List[str] = []
    if breakout_ok:
        signal_chain.append("recent_high_breakout")
    if vwap_hold_ok:
        signal_chain.append("vwap_hold")
    if vwap_reclaim_ok:
        signal_chain.append("vwap_reclaim")
    if volume_ok:
        signal_chain.append("volume_confirmation")
    if rebound_ok:
        signal_chain.append("pullback_rebound")
    if pullback_ok:
        signal_chain.append("pullback_structure")
    if confirmation_ok:
        signal_chain.append("confirmation_ready")
    if extension_ok:
        signal_chain.append("not_extended")
    if reclaim_gate_ok:
        signal_chain.append("reclaim_gate_ready")
    if breakout_path_ok:
        signal_chain.append("breakout_path_ready")
    if pullback_volume_path_ok:
        signal_chain.append("pullback_volume_path_ready")

    playbook = str((frame or {}).get("playbook") or "").strip().lower()
    checks = {
        "breakout_ok": bool(breakout_ok),
        "vwap_hold_ok": bool(vwap_hold_ok),
        "vwap_reclaim_ok": bool(vwap_reclaim_ok),
        "vwap_structure_ok": bool(vwap_structure_ok),
        "reclaim_gate_ok": bool(reclaim_gate_ok),
        "volume_ok": bool(volume_ok),
        "rebound_ok": bool(rebound_ok),
        "confirmation_ok": bool(confirmation_ok),
        "extension_ok": bool(extension_ok),
        "pullback_mature": bool(pullback_mature),
        "pullback_not_too_deep": bool(pullback_not_too_deep),
        "pullback_structure_ok": bool(pullback_ok),
        "breakout_path_ok": bool(breakout_path_ok),
        "pullback_volume_path_ok": bool(pullback_volume_path_ok),
        "confidence_gate_ok": bool(confidence_gate_ok),
    }
    if playbook in ("pullback", "reversal"):
        relevant_checks = [
            "reclaim_gate_ok",
            "vwap_structure_ok",
            "pullback_mature",
            "pullback_not_too_deep",
            "volume_ok",
            "pullback_volume_path_ok",
            "breakout_ok",
            "breakout_path_ok",
            "extension_ok",
            "confidence_gate_ok",
            "vwap_reclaim_ok",
            "vwap_hold_ok",
            "rebound_ok",
        ]
    else:
        relevant_checks = [
            "reclaim_gate_ok",
            "breakout_ok",
            "breakout_path_ok",
            "vwap_hold_ok",
            "volume_ok",
            "pullback_structure_ok",
            "pullback_volume_path_ok",
            "extension_ok",
            "rebound_ok",
            "confidence_gate_ok",
        ]
    passed_checks = [name for name in relevant_checks if checks.get(name)]
    failed_checks = [name for name in relevant_checks if not checks.get(name)]
    threshold_margins = {
        "volume_ratio": {
            "actual": volume_ratio,
            "min": _to_float(resolved_policy.volume_ratio_min),
            "distance_to_min": volume_ratio - _to_float(resolved_policy.volume_ratio_min),
        },
        "extended_from_vwap_pct": {
            "actual": extended_from_vwap_pct,
            "min": min_extended_from_vwap_pct,
            "max": max_extended_from_vwap_pct,
            "distance_to_min": extended_from_vwap_pct - min_extended_from_vwap_pct,
            "distance_to_max": max_extended_from_vwap_pct - extended_from_vwap_pct,
        },
        "pullback_depth_pct": {
            "actual": pullback_depth_pct,
            "min": pullback_min_pct,
            "max": pullback_max_pct,
            "distance_to_min": pullback_depth_pct - pullback_min_pct,
            "distance_to_max": pullback_max_pct - pullback_depth_pct,
        },
        "breakout_gap_pct": {
            "actual": breakout_gap_pct,
            "min": breakout_buffer_pct,
            "distance_to_breakout": (current_close - breakout_level) if breakout_level > 0.0 else None,
        },
    }

    pattern = ""
    reason = ""
    triggered = False
    primary_failure_axis = ""
    entry_condition_path = ""
    entry_condition_paths_passed: List[str] = []
    if breakout_path_ok:
        entry_condition_paths_passed.append("breakout_path")
    if pullback_volume_path_ok:
        entry_condition_paths_passed.append("pullback_volume_path")
    grouped_logic_trace = {
        "logic_mode": "reclaim_and_grouped_paths_v1",
        "reclaim_gate_required": bool(resolved_policy.require_vwap_reclaim),
        "reclaim_gate_ok": bool(reclaim_gate_ok),
        "extension_required": True,
        "extension_ok": bool(extension_ok),
        "breakout_path_ok": bool(breakout_path_ok),
        "pullback_volume_path_ok": bool(pullback_volume_path_ok),
        "paths_passed": list(entry_condition_paths_passed),
        "confidence_gate_ok": bool(confidence_gate_ok),
        "triggered_path": "",
    }
    if playbook in ("pullback", "reversal"):
        if reclaim_gate_ok and extension_ok and confidence_gate_ok and (breakout_path_ok or pullback_volume_path_ok):
            triggered = True
            if breakout_path_ok:
                entry_condition_path = "breakout_path"
                pattern = "breakout_vwap_hold"
                if vwap_reclaim_ok and not vwap_hold_ok:
                    reason = "breakout_above_recent_high_with_vwap_reclaim_confirmation"
                elif volume_ok and vwap_hold_ok:
                    reason = "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation"
                else:
                    reason = "breakout_above_recent_high_with_vwap_structure_confirmation"
            elif vwap_reclaim_ok and rebound_ok:
                entry_condition_path = "pullback_volume_path"
                pattern = "pullback_vwap_reclaim"
                reason = "pullback_reclaim_above_vwap_with_rebound_confirmation"
            elif rebound_ok:
                entry_condition_path = "pullback_volume_path"
                pattern = "pullback_rebound"
                reason = "pullback_rebound_above_vwap_with_confirmation"
            else:
                entry_condition_path = "pullback_volume_path"
                pattern = "pullback_vwap_hold"
                reason = "pullback_structure_above_vwap_with_volume_confirmation"
        else:
            if not extension_ok:
                if extended_from_vwap_pct > max_extended_from_vwap_pct:
                    reason = "still_overextended_after_pullback"
                    primary_failure_axis = "overextension"
                else:
                    # Pullback setup is still too weak below VWAP band; wait for reclaim/structure.
                    reason = "pullback_below_vwap_reclaim_not_ready"
                    primary_failure_axis = "vwap_relationship"
            elif not reclaim_gate_ok:
                reason = "below_vwap_reclaim_not_ready"
                primary_failure_axis = "vwap_relationship"
            elif not pullback_mature:
                reason = "pullback_not_mature"
                primary_failure_axis = "pullback_structure"
            elif not pullback_not_too_deep:
                reason = "no_valid_pullback_structure"
                primary_failure_axis = "pullback_structure"
            elif pullback_ok and not volume_ok:
                reason = "volume_confirmation_missing"
                primary_failure_axis = "volume_confirmation"
            elif not breakout_ok:
                reason = "breakout_not_ready"
                primary_failure_axis = "breakout_readiness"
            else:
                reason = "entry_signal_not_confirmed"
                primary_failure_axis = "entry_confirmation"
    else:
        if reclaim_gate_ok and extension_ok and confidence_gate_ok and (breakout_path_ok or pullback_volume_path_ok):
            triggered = True
            if breakout_path_ok:
                entry_condition_path = "breakout_path"
                pattern = "breakout_vwap_hold"
                if volume_ok and vwap_hold_ok:
                    reason = "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation"
                elif vwap_reclaim_ok and not vwap_hold_ok:
                    reason = "breakout_above_recent_high_with_vwap_reclaim_confirmation"
                else:
                    reason = "breakout_above_recent_high_with_vwap_structure_confirmation"
            else:
                entry_condition_path = "pullback_volume_path"
                pattern = "pullback_rebound" if rebound_ok else "pullback_vwap_hold"
                reason = (
                    "pullback_rebound_above_vwap_with_volume_confirmation"
                    if rebound_ok
                    else "pullback_structure_above_vwap_with_volume_confirmation"
                )
        else:
            if not extension_ok:
                if extended_from_vwap_pct > max_extended_from_vwap_pct:
                    reason = "too_extended_from_vwap"
                    primary_failure_axis = "overextension"
                else:
                    reason = "below_vwap_reclaim_not_ready"
                    primary_failure_axis = "vwap_relationship"
            elif not reclaim_gate_ok:
                reason = "below_vwap_reclaim_not_ready"
                primary_failure_axis = "vwap_relationship"
            elif pullback_ok and not volume_ok:
                reason = "volume_insufficient"
                primary_failure_axis = "volume_confirmation"
            elif not breakout_ok and not pullback_ok:
                reason = "breakout_not_ready"
                primary_failure_axis = "breakout_readiness"
            elif not pullback_ok:
                reason = "pullback_too_deep"
                primary_failure_axis = "pullback_structure"
            elif not breakout_ok:
                reason = "breakout_not_ready"
                primary_failure_axis = "breakout_readiness"
            else:
                reason = "entry_signal_not_confirmed"
                primary_failure_axis = "entry_confirmation"

    if triggered and not primary_failure_axis:
        primary_failure_axis = "confirmed_entry"
    grouped_logic_trace["triggered_path"] = entry_condition_path
    legacy_triggered = bool(triggered)
    legacy_decision = "BUY" if legacy_triggered else "WAIT"
    legacy_reason = str(reason or "")
    legacy_pattern = str(pattern or "")
    legacy_entry_condition_path = str(entry_condition_path or "")
    score_breakdown = _build_monitor_score_breakdown(
        vwap_reclaim_ok=bool(vwap_reclaim_ok),
        breakout_ok=bool(breakout_ok),
        pullback_mature=bool(pullback_mature),
        volume_ok=bool(volume_ok),
        confidence_gate_ok=bool(confidence_gate_ok),
    )
    scoring_entry_decision = "BUY" if sum(_to_float(v) for v in score_breakdown.values()) >= float(scoring_settings.get("entry_threshold") or 3.0) else "WAIT"
    signal_evidence = _build_monitor_signal_evidence(
        reclaim_score=vwap_reclaim_progress,
        volume_score=volume_score,
        pullback_score=pullback_score,
        breakout_score=breakout_score,
        confidence_score=confidence_score,
        confidence_threshold=confidence_threshold,
        reclaim_ok=vwap_reclaim_ok,
        volume_ok=volume_ok,
        pullback_ok=pullback_ok,
        breakout_ok=breakout_ok,
        rebound_ok=rebound_ok,
        reclaim_gate_ok=reclaim_gate_ok,
        breakout_path_ok=breakout_path_ok,
        pullback_volume_path_ok=pullback_volume_path_ok,
        extension_ok=extension_ok,
        too_extended=bool(not extension_ok and extended_from_vwap_pct > max_extended_from_vwap_pct),
        reclaim_strength=vwap_reclaim_progress,
        rebound_strength=rebound_progress,
        transition_readiness_score=transition_readiness_score,
        reclaim_distance_to_ready=reclaim_distance_to_ready,
        volume_distance_to_ready=volume_distance_to_ready,
        breakout_distance_to_ready=breakout_distance_to_ready,
        score_breakdown=score_breakdown,
        score_threshold=float(scoring_settings.get("entry_threshold") or 3.0),
    )
    chart_structure_features = build_chart_structure_features(
        candles,
        current_price=current_close,
        current_vwap=current_vwap,
        recent_high=recent_high,
        breakout_ok=breakout_ok,
        pullback_ok=pullback_ok,
        reclaim_ok=vwap_reclaim_ok,
        volume_ok=volume_ok,
        confidence_ok=confidence_gate_ok,
        volume_ratio=volume_ratio,
        too_extended=bool(not extension_ok and extended_from_vwap_pct > max_extended_from_vwap_pct),
    )
    policy_interpreter_trace = _build_monitor_policy_interpreter_trace(
        policy_interpretation=out.get("policy_interpretation"),
        signal_evidence=signal_evidence,
        chart_structure_features=chart_structure_features,
    )
    policy_alignment_summary = _build_monitor_policy_alignment_summary(
        policy_interpreter_trace=policy_interpreter_trace,
    )
    policy_aware_gating = _build_monitor_policy_aware_gating(
        policy_interpretation=out.get("policy_interpretation"),
        signal_evidence=signal_evidence,
        policy_interpreter_trace=policy_interpreter_trace,
        policy_alignment_summary=policy_alignment_summary,
        legacy_triggered=legacy_triggered,
        legacy_reason=legacy_reason,
    )
    chart_structure_decision_hint = _build_chart_structure_decision_hint(
        policy_interpretation=out.get("policy_interpretation"),
        signal_evidence=signal_evidence,
        chart_structure_features=chart_structure_features,
        legacy_triggered=legacy_triggered,
        legacy_decision=legacy_decision,
        legacy_reason=legacy_reason,
        legacy_entry_condition_path=legacy_entry_condition_path,
    )
    if bool(chart_structure_decision_hint.get("available")):
        policy_interpreter_trace["notes"] = _dedupe_non_empty(
            [
                *list(policy_interpreter_trace.get("notes") or []),
                "chart_structure_decision_hint_evaluated",
            ]
        )
    if bool(chart_structure_decision_hint.get("applied")):
        policy_alignment_summary["summary_notes"] = _dedupe_non_empty(
            [
                *list(policy_alignment_summary.get("summary_notes") or []),
                "chart_structure_decision_hint_applied",
            ]
        )
    if bool(policy_aware_gating.get("applied")):
        triggered = True
        pattern = "breakout_policy_reclaim_near_ready"
        reason = "breakout_above_recent_high_with_policy_reclaim_near_ready"
        entry_condition_path = "breakout_path"
        primary_failure_axis = "confirmed_entry"
        if "breakout_path" not in entry_condition_paths_passed:
            entry_condition_paths_passed.append("breakout_path")
        if "policy_reclaim_near_ready" not in signal_chain:
            signal_chain.append("policy_reclaim_near_ready")
    elif bool(chart_structure_decision_hint.get("applied")):
        triggered = False
        hint_entry_style = str(chart_structure_decision_hint.get("entry_style") or "").strip().lower()
        if hint_entry_style in {"pullback", "reversal"}:
            reason = "pullback_reversal_structure_guard_blocked"
            primary_failure_axis = "chart_structure_support"
            if "chart_structure_pullback_reversal_guard" not in signal_chain:
                signal_chain.append("chart_structure_pullback_reversal_guard")
        else:
            reason = "breakout_continuation_structure_guard_blocked"
            primary_failure_axis = "chart_structure_continuation"
            if "chart_structure_breakout_continuation_guard" not in signal_chain:
                signal_chain.append("chart_structure_breakout_continuation_guard")

    metrics = {
        "timeframe_minutes": timeframe_minutes,
        "bar_count": len(candles),
        "price": current_close if current_close > 0.0 else None,
        "current_price": current_close if current_close > 0.0 else None,
        "current_high": current_high if current_high > 0.0 else None,
        "current_low": current_low if current_low > 0.0 else None,
        "recent_high": recent_high if recent_high > 0.0 else None,
        "breakout_level": breakout_level if breakout_level > 0.0 else None,
        "prior_bar_high": prior_bar_high if prior_bar_high > 0.0 else None,
        "prior_bar_low": prior_bar_low if prior_bar_low > 0.0 else None,
        "vwap": current_vwap if current_vwap > 0.0 else None,
        "vwap_distance": extended_from_vwap_pct,
        "volume_ratio": volume_ratio if volume_ratio > 0.0 else None,
        "pullback_pct": pullback_depth_pct,
        "pullback_depth_pct": pullback_depth_pct,
        "extended_from_vwap_pct": extended_from_vwap_pct,
        "reclaim_distance_to_ready": reclaim_distance_to_ready,
        "vwap_reclaim_progress": vwap_reclaim_progress,
        "rebound_progress": rebound_progress,
        "volume_distance_to_ready": volume_distance_to_ready,
        "breakout_gap_pct": breakout_gap_pct,
        "breakout_distance_to_ready": breakout_distance_to_ready,
        "transition_readiness_score": transition_readiness_score,
        "breakout_ok": bool(breakout_ok),
        "vwap_hold_ok": bool(vwap_hold_ok),
        "vwap_reclaim_ok": bool(vwap_reclaim_ok),
        "rebound_ok": bool(rebound_ok),
        "volume_ok": bool(volume_ok),
        "extension_ok": bool(extension_ok),
        "pullback_ok": bool(pullback_ok),
        "pullback_mature": bool(pullback_mature),
        "pullback_not_too_deep": bool(pullback_not_too_deep),
        "confirmation_ok": bool(confirmation_ok),
        "vwap_structure_ok": bool(vwap_structure_ok),
        "reclaim_gate_ok": bool(reclaim_gate_ok),
        "breakout_path_ok": bool(breakout_path_ok),
        "pullback_volume_path_ok": bool(pullback_volume_path_ok),
        "breakout_score": breakout_score,
        "volume_score": volume_score,
        "pullback_score": pullback_score,
        "breakout_path_score": breakout_path_score,
        "pullback_volume_path_score": pullback_volume_path_score,
        "confidence_score": confidence_score,
        "confidence_threshold": confidence_threshold,
        "confidence_gate_ok": bool(confidence_gate_ok),
        "engine_vwap_distance": (features or {}).get("engine_vwap_distance"),
        "engine_volume_spike20": (features or {}).get("engine_volume_spike20"),
        "engine_trend_strength": (features or {}).get("engine_trend_strength"),
        "inferred_spacing_minutes": series_quality.get("inferred_spacing_minutes"),
        "series_class": series_quality.get("series_class"),
    }
    transition_trace = _empty_entry_transition_trace()
    transition_trace.update(
        {
            "reclaim_distance_to_ready": reclaim_distance_to_ready,
            "vwap_reclaim_progress": round(vwap_reclaim_progress, 4),
            "rebound_progress": rebound_progress,
            "volume_distance_to_ready": volume_distance_to_ready,
            "breakout_distance_to_ready": breakout_distance_to_ready,
            "transition_readiness_score": transition_readiness_score,
            "last_blocking_axis": primary_failure_axis if not triggered else "",
            "became_ready_this_cycle": bool(policy_aware_gating.get("applied")),
        }
    )
    grouped_logic_trace["triggered_path"] = entry_condition_path
    grouped_logic_trace["scoring_mode"] = str(scoring_settings.get("scoring_mode") or "disabled")
    grouped_logic_trace["score_passed"] = bool(sum(_to_float(v) for v in score_breakdown.values()) >= float(scoring_settings.get("entry_threshold") or 3.0))
    grouped_logic_trace["signal_evidence_ready"] = True
    grouped_logic_trace["policy_aware_gating_available"] = bool(policy_aware_gating.get("available"))
    grouped_logic_trace["policy_aware_gating_applied"] = bool(policy_aware_gating.get("applied"))
    grouped_logic_trace["policy_aware_gating_hints"] = list(policy_aware_gating.get("applied_hints") or [])
    grouped_logic_trace["policy_aware_gating_blocked_by_required"] = list(policy_aware_gating.get("blocked_by_required") or [])
    grouped_logic_trace["chart_structure_decision_hint_available"] = bool(chart_structure_decision_hint.get("available"))
    grouped_logic_trace["chart_structure_decision_hint_applied"] = bool(chart_structure_decision_hint.get("applied"))
    grouped_logic_trace["chart_structure_decision_hint_mode"] = str(chart_structure_decision_hint.get("mode") or "none")
    grouped_logic_trace["chart_structure_decision_hint_blocking_features"] = list(chart_structure_decision_hint.get("blocking_features") or [])
    _apply_monitor_scoring_fields(
        out,
        scoring_settings=scoring_settings,
        hard_filter_passed=True,
        hard_filter_fail_reasons=[],
        score_breakdown=score_breakdown,
        legacy_entry_decision=legacy_decision,
        scoring_entry_decision="BUY" if sum(_to_float(v) for v in score_breakdown.values()) >= float(scoring_settings.get("entry_threshold") or 3.0) else "WAIT",
    )
    out.update(
        {
            "triggered": bool(triggered),
            "decision": "BUY" if triggered else "WAIT",
            "pattern": pattern,
            "reason": reason,
            "signal_chain": signal_chain,
            "metrics": metrics,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "primary_failure_axis": primary_failure_axis,
            "threshold_margins": threshold_margins,
            "entry_condition_path": entry_condition_path,
            "entry_condition_paths_passed": entry_condition_paths_passed,
            "condition_scores": {
                "breakout_score": breakout_score,
                "volume_score": volume_score,
                "pullback_score": pullback_score,
                "breakout_path_score": breakout_path_score,
                "pullback_volume_path_score": pullback_volume_path_score,
                "confidence_score": confidence_score,
                "confidence_threshold": confidence_threshold,
                "confidence_gate_ok": bool(confidence_gate_ok),
                "transition_readiness_score": transition_readiness_score,
            },
            "grouped_logic_trace": grouped_logic_trace,
            "legacy_entry_reason": legacy_reason,
            "legacy_entry_pattern": legacy_pattern,
            "legacy_entry_condition_path": legacy_entry_condition_path,
            "signal_evidence": signal_evidence,
            "chart_structure_features": chart_structure_features,
            "policy_interpreter_trace": policy_interpreter_trace,
            "policy_alignment_summary": policy_alignment_summary,
            "policy_aware_gating": policy_aware_gating,
            "chart_structure_decision_hint": chart_structure_decision_hint,
            "reclaim_distance_to_ready": reclaim_distance_to_ready,
            "vwap_reclaim_progress": round(vwap_reclaim_progress, 4),
            "rebound_progress": rebound_progress,
            "volume_distance_to_ready": volume_distance_to_ready,
            "breakout_distance_to_ready": breakout_distance_to_ready,
            "transition_readiness_score": transition_readiness_score,
            "last_blocking_axis": str(primary_failure_axis or "") if not triggered else "",
            "became_ready_this_cycle": False,
            "entry_transition_trace": transition_trace,
        }
    )
    return out
