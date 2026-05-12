from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Tuple

from libs.runtime.chart_structure_features import CHART_STRUCTURE_FEATURE_ALLOWED_STATES


LOW_LEVEL_POLICY_FEATURE_NAMES = {
    "breakout_ok",
    "pullback_ok",
    "reclaim_ok",
    "reclaim_gate_ok",
    "rebound_ok",
    "vwap_reclaim_ok",
    "volume_ok",
    "confidence_ok",
    "too_extended",
    "extension_ok",
    "policy_disabled",
}
HIGH_LEVEL_POLICY_FEATURE_STATE_MAP = {
    str(name): tuple(str(state) for state in list(states or ()))
    for name, states in dict(CHART_STRUCTURE_FEATURE_ALLOWED_STATES).items()
}
ALL_POLICY_FEATURE_NAMES = set(LOW_LEVEL_POLICY_FEATURE_NAMES) | set(HIGH_LEVEL_POLICY_FEATURE_STATE_MAP.keys())


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _to_bool(value: Any, default: bool) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return bool(value)
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _normalize_pct_unit_if_needed(field_name: str, parsed: float, lower: float, upper: float) -> tuple[float, str]:
    if not str(field_name or "").endswith("_pct"):
        return parsed, ""
    if lower <= parsed <= upper:
        return parsed, ""
    converted = parsed / 100.0
    if lower <= converted <= upper:
        return converted, f"{field_name}:percent_unit_normalized:{parsed}->{converted}"
    return parsed, ""


def _dedupe_text_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        items = [values]
    elif isinstance(values, (list, tuple, set)):
        items = list(values)
    else:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _normalize_priority_hints(value: Any) -> Dict[str, Any]:
    raw = dict(value or {}) if isinstance(value, Mapping) else {}
    return {
        "volume_priority": str(raw.get("volume_priority") or raw.get("volume") or "").strip() or None,
        "reclaim_priority": str(raw.get("reclaim_priority") or raw.get("reclaim") or "").strip() or None,
        "breakout_priority": str(raw.get("breakout_priority") or raw.get("breakout") or "").strip() or None,
        "pullback_priority": str(raw.get("pullback_priority") or raw.get("pullback") or "").strip() or None,
    }


def _normalize_evidence_focus(value: Any) -> Dict[str, Any]:
    raw = dict(value or {}) if isinstance(value, Mapping) else {}
    return {
        "primary": normalize_policy_feature_references(raw.get("primary")),
        "secondary": normalize_policy_feature_references(raw.get("secondary")),
    }


def _normalize_policy_adjustments(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, str):
        text = str(value).strip()
        return [text] if text else []
    if not isinstance(value, (list, tuple, set)):
        return []
    out: list[Any] = []
    for item in list(value):
        if isinstance(item, Mapping):
            out.append(dict(item))
            continue
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _volume_priority_hint(volume_ratio_min: float) -> str:
    if float(volume_ratio_min) >= 1.0:
        return "high"
    if float(volume_ratio_min) <= 0.75:
        return "low"
    return "normal"


def _normalize_interpretation_priority_hints(value: Any) -> Dict[str, Any]:
    raw = dict(value or {}) if isinstance(value, Mapping) else {}
    return {
        "reclaim": str(raw.get("reclaim") or raw.get("reclaim_priority") or "").strip() or None,
        "volume": str(raw.get("volume") or raw.get("volume_priority") or "").strip() or None,
        "breakout": str(raw.get("breakout") or raw.get("breakout_priority") or "").strip() or None,
        "pullback": str(raw.get("pullback") or raw.get("pullback_priority") or "").strip() or None,
    }


def _extract_monitor_entry_interpretation_mapping(policy: Mapping[str, Any] | None) -> Dict[str, Any]:
    raw = dict(policy or {}) if isinstance(policy, Mapping) else {}
    nested = raw.get("interpretation_policy")
    if isinstance(nested, Mapping):
        return dict(nested or {})
    return raw


def normalize_policy_check_spec(spec: Any) -> Dict[str, Any]:
    raw = str(spec or "").strip()
    out = {
        "raw": raw,
        "feature_name": None,
        "expected_state": None,
        "normalized_spec": None,
        "feature_level": "unknown",
        "is_valid": False,
        "validation_notes": [],
    }
    if not raw:
        out["validation_notes"] = ["empty_spec"]
        return out

    name_text = raw
    expected_state = None
    if "=" in raw:
        name_text, expected = raw.split("=", 1)
        expected_state = str(expected or "").strip().lower() or None
    feature_name = str(name_text or "").strip().lower()
    out["feature_name"] = feature_name or None
    out["expected_state"] = expected_state
    if not feature_name:
        out["validation_notes"] = ["empty_feature_name"]
        return out

    if feature_name in LOW_LEVEL_POLICY_FEATURE_NAMES:
        out["feature_level"] = "low_level"
        if expected_state is not None:
            out["validation_notes"] = ["state_not_supported_for_low_level_feature"]
            return out
        out["is_valid"] = True
        out["normalized_spec"] = feature_name
        return out

    allowed_states = tuple(HIGH_LEVEL_POLICY_FEATURE_STATE_MAP.get(feature_name) or ())
    if allowed_states:
        out["feature_level"] = "high_level"
        if expected_state is None:
            out["is_valid"] = True
            out["normalized_spec"] = feature_name
            return out
        if expected_state not in allowed_states:
            out["validation_notes"] = ["invalid_state"]
            return out
        out["is_valid"] = True
        out["normalized_spec"] = f"{feature_name}={expected_state}"
        return out

    out["validation_notes"] = ["invalid_feature"]
    return out


def normalize_policy_check_specs(values: Any, *, field_name: str = "") -> Dict[str, Any]:
    normalized_specs: list[str] = []
    invalid_specs: list[Dict[str, Any]] = []
    validation_notes: list[str] = []
    for raw_value in _dedupe_text_list(values):
        spec = normalize_policy_check_spec(raw_value)
        normalized = str(spec.get("normalized_spec") or "").strip()
        if bool(spec.get("is_valid")) and normalized:
            if normalized not in normalized_specs:
                normalized_specs.append(normalized)
            continue
        invalid_specs.append(
            {
                "raw": str(spec.get("raw") or raw_value),
                "feature_name": spec.get("feature_name"),
                "expected_state": spec.get("expected_state"),
                "feature_level": spec.get("feature_level"),
                "validation_notes": list(spec.get("validation_notes") or []),
            }
        )
        reason = ",".join(str(item).strip() for item in list(spec.get("validation_notes") or []) if str(item).strip())
        note_prefix = f"{field_name}:" if field_name else ""
        validation_notes.append(f"{note_prefix}{str(spec.get('raw') or raw_value)}:{reason or 'invalid_spec'}")
    return {
        "normalized_specs": normalized_specs,
        "invalid_specs": invalid_specs,
        "validation_notes": validation_notes,
    }


def normalize_policy_feature_references(values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw_value in _dedupe_text_list(values):
        spec = normalize_policy_check_spec(raw_value)
        feature_name = str(spec.get("feature_name") or "").strip()
        if not feature_name or feature_name not in ALL_POLICY_FEATURE_NAMES or feature_name in seen:
            continue
        seen.add(feature_name)
        out.append(feature_name)
    return out


def build_monitor_entry_interpretation_policy(
    *,
    playbook: str = "",
    threshold_policy: Mapping[str, Any] | MonitorEntryPolicy | None = None,
    monitor_guidance: str = "",
    risk_tone: str = "",
    trade_aggressiveness: str = "",
    interpretation_policy: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    threshold = (
        threshold_policy
        if isinstance(threshold_policy, MonitorEntryPolicy)
        else MonitorEntryPolicy.from_mapping(threshold_policy)
    )
    explicit = _extract_monitor_entry_interpretation_mapping(interpretation_policy)

    entry_style = str(
        explicit.get("entry_style")
        or playbook
        or ""
    ).strip().lower() or None
    guidance = str(monitor_guidance or "").strip().lower()
    tone = str(risk_tone or "").strip().lower()
    aggressiveness = str(trade_aggressiveness or "").strip().lower()

    required_checks: list[str] = []
    preferred_checks: list[str] = []
    relaxable_checks: list[str] = []
    blockers: list[str] = []
    primary_focus: list[str] = []
    secondary_focus: list[str] = []
    notes: list[str] = []

    if not bool(threshold.enabled):
        blockers.append("policy_disabled")
    if bool(threshold.require_vwap_reclaim) and entry_style != "breakout":
        required_checks.append("reclaim_gate_ok")
        notes.append("vwap_reclaim_required")
    elif bool(threshold.require_vwap_reclaim) and entry_style == "breakout":
        preferred_checks.append("reclaim_gate_ok")
        relaxable_checks.append("reclaim_gate_ok")
        notes.append("vwap_reclaim_near_ready_relaxable_for_breakout_style")
    if bool(threshold.require_rebound) and entry_style in ("pullback", "reversal"):
        required_checks.append("rebound_ok")
        notes.append("rebound_required_for_pullback_style")
    if float(threshold.volume_ratio_min) >= 1.0:
        notes.append("volume_threshold_emphasized")
    elif float(threshold.volume_ratio_min) <= 0.75:
        notes.append("volume_threshold_relatively_loose")
        relaxable_checks.append("volume_ok")

    if entry_style == "breakout":
        preferred_checks.extend(["breakout_ok", "volume_ok", "reclaim_gate_ok"])
        preferred_checks.extend(["structure_hh_hl=intact", "momentum_follow_through=strong"])
        relaxable_checks.extend(["pullback_ok"])
        blockers.extend(["failed_breakout=confirmed", "momentum_decay=strong"])
        primary_focus.extend(["breakout_ok", "volume_ok", "structure_hh_hl", "momentum_follow_through"])
        secondary_focus.extend(["reclaim_gate_ok", "confidence_ok", "failed_breakout", "momentum_decay"])
        notes.append("structure_aware_breakout_policy")
    elif entry_style in ("pullback", "reversal"):
        preferred_checks.extend(["pullback_ok", "volume_ok", "vwap_reclaim_ok"])
        preferred_checks.extend(["support_holding=holding", "trend_regime=trending", "ma_alignment_state=bullish"])
        relaxable_checks.extend(["breakout_ok"])
        blockers.extend(["structure_hh_hl=broken", "support_holding=lost"])
        primary_focus.extend(["pullback_ok", "volume_ok", "support_holding", "trend_regime"])
        secondary_focus.extend(["reclaim_gate_ok", "rebound_ok", "ma_alignment_state", "structure_hh_hl"])
        notes.append("structure_aware_pullback_policy")
    elif entry_style == "defensive":
        preferred_checks.extend(["reclaim_gate_ok", "extension_ok", "confidence_ok"])
        preferred_checks.extend(["trend_regime=transition", "structure_range_compression=moderate"])
        relaxable_checks.extend(["breakout_ok", "pullback_ok"])
        blockers.extend(["failed_breakout=confirmed", "momentum_decay=strong"])
        primary_focus.extend(["reclaim_gate_ok", "extension_ok", "confidence_ok", "trend_regime"])
        secondary_focus.extend(["volume_ok", "structure_range_compression", "failed_breakout", "momentum_decay"])
        notes.append("structure_aware_defensive_policy")
    else:
        preferred_checks.extend(["reclaim_gate_ok", "confidence_ok"])
        primary_focus.extend(["reclaim_gate_ok"])
        secondary_focus.extend(["volume_ok", "breakout_ok", "pullback_ok"])

    if tone == "conservative":
        notes.append("risk_tone_conservative")
    elif tone == "aggressive":
        notes.append("risk_tone_aggressive")
    if guidance:
        notes.append(f"monitor_guidance:{guidance}")
    if aggressiveness:
        notes.append(f"trade_aggressiveness:{aggressiveness}")

    priority_hints = {
        "reclaim": "high" if bool(threshold.require_vwap_reclaim) else "normal",
        "volume": _volume_priority_hint(float(threshold.volume_ratio_min)),
        "breakout": (
            "high" if entry_style == "breakout" else "low" if entry_style in ("pullback", "reversal") else "normal"
        ),
        "pullback": (
            "high" if entry_style in ("pullback", "reversal") else "low" if entry_style == "breakout" else "normal"
        ),
    }

    if explicit.get("required_checks") is not None:
        required_checks = _dedupe_text_list(explicit.get("required_checks"))
    if explicit.get("preferred_checks") is not None:
        preferred_checks = _dedupe_text_list(explicit.get("preferred_checks"))
    if explicit.get("relaxable_checks") is not None:
        relaxable_checks = _dedupe_text_list(explicit.get("relaxable_checks"))
    if explicit.get("blockers") is not None:
        blockers = _dedupe_text_list(explicit.get("blockers"))
    explicit_priority_hints = _normalize_interpretation_priority_hints(explicit.get("priority_hints"))
    if any(explicit_priority_hints.values()):
        priority_hints.update({key: value for key, value in explicit_priority_hints.items() if value})
    explicit_focus = _normalize_evidence_focus(explicit.get("evidence_focus"))
    if explicit_focus.get("primary") or explicit_focus.get("secondary"):
        primary_focus = list(explicit_focus.get("primary") or primary_focus)
        secondary_focus = list(explicit_focus.get("secondary") or secondary_focus)
    explicit_notes = _dedupe_text_list(explicit.get("notes"))
    if explicit_notes:
        notes = explicit_notes

    required_checks_meta = normalize_policy_check_specs(required_checks, field_name="required_checks")
    preferred_checks_meta = normalize_policy_check_specs(preferred_checks, field_name="preferred_checks")
    relaxable_checks_meta = normalize_policy_check_specs(relaxable_checks, field_name="relaxable_checks")
    blockers_meta = normalize_policy_check_specs(blockers, field_name="blockers")
    spec_validation_notes = _dedupe_text_list(
        [
            *list(required_checks_meta.get("validation_notes") or []),
            *list(preferred_checks_meta.get("validation_notes") or []),
            *list(relaxable_checks_meta.get("validation_notes") or []),
            *list(blockers_meta.get("validation_notes") or []),
        ]
    )
    invalid_policy_specs = [
        *list(required_checks_meta.get("invalid_specs") or []),
        *list(preferred_checks_meta.get("invalid_specs") or []),
        *list(relaxable_checks_meta.get("invalid_specs") or []),
        *list(blockers_meta.get("invalid_specs") or []),
    ]

    return {
        "entry_style": entry_style,
        "required_checks": list(required_checks_meta.get("normalized_specs") or []),
        "preferred_checks": list(preferred_checks_meta.get("normalized_specs") or []),
        "relaxable_checks": list(relaxable_checks_meta.get("normalized_specs") or []),
        "blockers": list(blockers_meta.get("normalized_specs") or []),
        "priority_hints": _normalize_interpretation_priority_hints(priority_hints),
        "evidence_focus": {
            "primary": normalize_policy_feature_references(primary_focus),
            "secondary": normalize_policy_feature_references(secondary_focus),
        },
        "notes": _dedupe_text_list(notes),
        "spec_validation_notes": spec_validation_notes,
        "invalid_policy_specs": invalid_policy_specs,
    }


def build_monitor_entry_policy_bundle(
    *,
    threshold_policy: Mapping[str, Any] | MonitorEntryPolicy | None = None,
    playbook: str = "",
    monitor_guidance: str = "",
    risk_tone: str = "",
    trade_aggressiveness: str = "",
    interpretation_policy: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    threshold_obj = (
        threshold_policy
        if isinstance(threshold_policy, MonitorEntryPolicy)
        else MonitorEntryPolicy.from_mapping(threshold_policy)
    )
    threshold_dict = threshold_obj.to_dict()
    raw_policy = dict(threshold_policy or {}) if isinstance(threshold_policy, Mapping) else {}
    bundled: Dict[str, Any] = dict(threshold_dict)
    bundled["threshold_policy"] = dict(threshold_dict)
    bundled["interpretation_policy"] = build_monitor_entry_interpretation_policy(
        playbook=playbook,
        threshold_policy=threshold_dict,
        monitor_guidance=monitor_guidance,
        risk_tone=risk_tone,
        trade_aggressiveness=trade_aggressiveness,
        interpretation_policy=(
            interpretation_policy
            if isinstance(interpretation_policy, Mapping)
            else raw_policy.get("interpretation_policy")
            if isinstance(raw_policy.get("interpretation_policy"), Mapping)
            else None
        ),
    )
    for key, value in raw_policy.items():
        if key in bundled or key in ("threshold_policy", "interpretation_policy"):
            continue
        bundled[key] = value
    return bundled


@dataclass(frozen=True)
class MonitorEntryPolicy:
    enabled: bool = True
    timeframe_minutes: int = 1
    breakout_lookback: int = 5
    volume_lookback: int = 5
    volume_ratio_min: float = 0.68
    min_extended_from_vwap_pct: float = -0.02
    max_extended_from_vwap_pct: float = 0.13
    pullback_min_pct: float = 0.008
    pullback_max_pct: float = 0.07
    reclaim_tolerance_pct: float = 0.0015
    breakout_buffer_pct: float = 0.0
    intent_cooldown_sec: int = 60
    require_vwap_reclaim: bool = True
    require_rebound: bool = True
    adjustments: Tuple[str, ...] = field(default_factory=tuple)
    policy_source: str = "monitor_entry_policy.v1"

    @classmethod
    def from_mapping(cls, policy: Mapping[str, Any] | None = None) -> "MonitorEntryPolicy":
        cfg = extract_monitor_entry_policy_mapping(policy)
        return cls(
            enabled=_to_bool(cfg.get("enabled", cfg.get("intraday_entry_enabled")), True),
            timeframe_minutes=max(1, _to_int(cfg.get("timeframe_minutes", cfg.get("entry_timeframe_minutes")), 1)),
            breakout_lookback=max(3, _to_int(cfg.get("breakout_lookback", cfg.get("entry_breakout_lookback")), 5)),
            volume_lookback=max(3, _to_int(cfg.get("volume_lookback", cfg.get("entry_volume_lookback")), 5)),
            volume_ratio_min=max(0.1, _to_float(cfg.get("volume_ratio_min", cfg.get("entry_volume_ratio_min")), 0.68)),
            min_extended_from_vwap_pct=_to_float(
                cfg.get("min_extended_from_vwap_pct", cfg.get("entry_min_extended_from_vwap_pct")),
                -0.02,
            ),
            max_extended_from_vwap_pct=max(
                0.0,
                _to_float(cfg.get("max_extended_from_vwap_pct", cfg.get("entry_max_extended_from_vwap_pct")), 0.13),
            ),
            pullback_min_pct=max(0.0, _to_float(cfg.get("pullback_min_pct", cfg.get("entry_pullback_min_pct")), 0.008)),
            pullback_max_pct=max(0.0, _to_float(cfg.get("pullback_max_pct", cfg.get("entry_pullback_max_pct")), 0.07)),
            reclaim_tolerance_pct=max(
                0.0,
                _to_float(cfg.get("reclaim_tolerance_pct", cfg.get("entry_reclaim_tolerance_pct")), 0.0015),
            ),
            breakout_buffer_pct=max(
                0.0,
                _to_float(cfg.get("breakout_buffer_pct", cfg.get("entry_breakout_buffer_pct")), 0.0),
            ),
            intent_cooldown_sec=max(0, _to_int(cfg.get("intent_cooldown_sec", cfg.get("entry_intent_cooldown_sec")), 60)),
            require_vwap_reclaim=_to_bool(cfg.get("require_vwap_reclaim"), True),
            require_rebound=_to_bool(cfg.get("require_rebound"), True),
            adjustments=tuple(str(x or "").strip() for x in list(cfg.get("adjustments") or []) if str(x or "").strip()),
            policy_source=str(cfg.get("policy_source") or "monitor_entry_policy.v1"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "timeframe_minutes": int(self.timeframe_minutes),
            "breakout_lookback": int(self.breakout_lookback),
            "volume_lookback": int(self.volume_lookback),
            "volume_ratio_min": float(self.volume_ratio_min),
            "min_extended_from_vwap_pct": float(self.min_extended_from_vwap_pct),
            "max_extended_from_vwap_pct": float(self.max_extended_from_vwap_pct),
            "pullback_min_pct": float(self.pullback_min_pct),
            "pullback_max_pct": float(self.pullback_max_pct),
            "reclaim_tolerance_pct": float(self.reclaim_tolerance_pct),
            "breakout_buffer_pct": float(self.breakout_buffer_pct),
            "intent_cooldown_sec": int(self.intent_cooldown_sec),
            "require_vwap_reclaim": bool(self.require_vwap_reclaim),
            "require_rebound": bool(self.require_rebound),
            "adjustments": list(self.adjustments),
            "policy_source": str(self.policy_source),
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(str(key), default)


def build_default_monitor_entry_policy() -> MonitorEntryPolicy:
    return MonitorEntryPolicy()


_POLICY_DELTA_FIELDS: Tuple[str, ...] = (
    "enabled",
    "timeframe_minutes",
    "breakout_lookback",
    "volume_lookback",
    "volume_ratio_min",
    "min_extended_from_vwap_pct",
    "max_extended_from_vwap_pct",
    "pullback_min_pct",
    "pullback_max_pct",
    "reclaim_tolerance_pct",
    "breakout_buffer_pct",
    "intent_cooldown_sec",
    "require_vwap_reclaim",
    "require_rebound",
)


def summarize_monitor_policy_deltas(
    received_policy: Mapping[str, Any] | MonitorEntryPolicy | None,
    effective_policy: Mapping[str, Any] | MonitorEntryPolicy | None,
) -> list[Dict[str, Any]]:
    received = (
        received_policy.to_dict()
        if isinstance(received_policy, MonitorEntryPolicy)
        else MonitorEntryPolicy.from_mapping(received_policy).to_dict()
    )
    effective = (
        effective_policy.to_dict()
        if isinstance(effective_policy, MonitorEntryPolicy)
        else MonitorEntryPolicy.from_mapping(effective_policy).to_dict()
    )
    deltas: list[Dict[str, Any]] = []
    for field_name in _POLICY_DELTA_FIELDS:
        before = received.get(field_name)
        after = effective.get(field_name)
        if before == after:
            continue
        deltas.append(
            {
                "field": str(field_name),
                "from": before,
                "to": after,
            }
        )
    return deltas


def extract_monitor_entry_policy_mapping(policy: Mapping[str, Any] | None) -> Dict[str, Any]:
    raw = dict(policy or {})
    for key in ("threshold_policy", "monitor_entry_policy", "entry_policy"):
        nested = raw.get(key)
        if isinstance(nested, dict):
            merged = dict(raw)
            merged.update(dict(nested or {}))
            return merged
    return raw


def _summarize_selected_policy_schema(schema: Mapping[str, Any] | None) -> Dict[str, Any]:
    row = dict(schema or {}) if isinstance(schema, Mapping) else {}
    normalized_policy_spec_count = sum(
        len(_dedupe_text_list(row.get(key)))
        for key in ("required_checks", "preferred_checks", "relaxable_checks", "blockers")
    )
    invalid_policy_specs = list(row.get("invalid_policy_specs") or [])
    return {
        "schema_available": bool(row.get("available")),
        "normalized_policy_spec_count": int(normalized_policy_spec_count),
        "invalid_policy_spec_count": int(len(invalid_policy_specs)),
        "spec_validation_notes": _dedupe_text_list(row.get("spec_validation_notes")),
        "explicit_fields_used": _dedupe_text_list(row.get("explicit_fields_used")),
        "raw_keys": _dedupe_text_list(row.get("raw_keys")),
    }


def build_monitor_entry_policy_contract(
    *,
    commander_applied_policy: Mapping[str, Any] | None = None,
    strategist_monitor_entry_policy: Mapping[str, Any] | None = None,
    state_monitor_entry_policy: Mapping[str, Any] | None = None,
    strategy_monitor_entry_policy: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    source_priority = [
        "commander_applied_policy",
        "strategist_output.monitor_entry_policy",
        "state.monitor_entry_policy",
        "strategy_policy.monitor_policy.entry_policy",
    ]
    source_payloads = {
        "commander_applied_policy": dict(commander_applied_policy or {}) if isinstance(commander_applied_policy, Mapping) else {},
        "strategist_output.monitor_entry_policy": (
            dict(strategist_monitor_entry_policy or {})
            if isinstance(strategist_monitor_entry_policy, Mapping)
            else {}
        ),
        "state.monitor_entry_policy": (
            dict(state_monitor_entry_policy or {})
            if isinstance(state_monitor_entry_policy, Mapping)
            else {}
        ),
        "strategy_policy.monitor_policy.entry_policy": (
            dict(strategy_monitor_entry_policy or {})
            if isinstance(strategy_monitor_entry_policy, Mapping)
            else {}
        ),
    }
    selected_source = "monitor_policy"
    selected_policy: Dict[str, Any] = {}
    for source_name in source_priority:
        candidate = dict(source_payloads.get(source_name) or {})
        if candidate:
            selected_source = str(source_name)
            selected_policy = dict(candidate)
            break
    selected_policy_schema = normalize_monitor_entry_policy_schema(selected_policy)
    return {
        "contract_version": "monitor_entry_policy_contract.v1",
        "available": bool(selected_policy),
        "selected_source": str(selected_source),
        "selected_policy": dict(selected_policy),
        "selected_policy_schema": dict(selected_policy_schema),
        "selected_policy_spec_health": _summarize_selected_policy_schema(selected_policy_schema),
        "source_priority": list(source_priority),
        "sources": {
            name: {
                "available": bool(payload),
                "policy_source": str((payload or {}).get("policy_source") or ""),
                "keys": sorted(str(k) for k in list((payload or {}).keys())),
            }
            for name, payload in source_payloads.items()
        },
    }


def normalize_monitor_entry_policy_schema(policy: Mapping[str, Any] | None) -> Dict[str, Any]:
    selected_policy = dict(policy or {}) if isinstance(policy, Mapping) else {}
    interpretation_policy = _extract_monitor_entry_interpretation_mapping(selected_policy)
    schema_source = interpretation_policy if interpretation_policy else selected_policy
    raw_keys = sorted(str(k) for k in list(schema_source.keys()))
    entry_style = str(schema_source.get("entry_style") or schema_source.get("playbook") or "").strip().lower() or None
    required_checks_meta = normalize_policy_check_specs(schema_source.get("required_checks"), field_name="required_checks")
    preferred_checks_meta = normalize_policy_check_specs(schema_source.get("preferred_checks"), field_name="preferred_checks")
    relaxable_checks_meta = normalize_policy_check_specs(schema_source.get("relaxable_checks"), field_name="relaxable_checks")
    blockers_meta = normalize_policy_check_specs(schema_source.get("blockers"), field_name="blockers")
    required_checks = list(required_checks_meta.get("normalized_specs") or [])
    preferred_checks = list(preferred_checks_meta.get("normalized_specs") or [])
    relaxable_checks = list(relaxable_checks_meta.get("normalized_specs") or [])
    blockers = list(blockers_meta.get("normalized_specs") or [])
    priority_hints = _normalize_priority_hints(schema_source.get("priority_hints"))
    evidence_focus = _normalize_evidence_focus(schema_source.get("evidence_focus"))
    policy_adjustments = _normalize_policy_adjustments(
        schema_source.get("policy_adjustments", schema_source.get("adjustments"))
    )
    notes = _dedupe_text_list(schema_source.get("notes", schema_source.get("policy_notes")))
    spec_validation_notes = _dedupe_text_list(
        [
            *list(required_checks_meta.get("validation_notes") or []),
            *list(preferred_checks_meta.get("validation_notes") or []),
            *list(relaxable_checks_meta.get("validation_notes") or []),
            *list(blockers_meta.get("validation_notes") or []),
        ]
    )
    invalid_policy_specs = [
        *list(required_checks_meta.get("invalid_specs") or []),
        *list(preferred_checks_meta.get("invalid_specs") or []),
        *list(relaxable_checks_meta.get("invalid_specs") or []),
        *list(blockers_meta.get("invalid_specs") or []),
    ]
    explicit_fields_used = [
        name
        for name, active in [
            ("entry_style", bool(entry_style)),
            ("required_checks", bool(required_checks)),
            ("preferred_checks", bool(preferred_checks)),
            ("relaxable_checks", bool(relaxable_checks)),
            ("blockers", bool(blockers)),
            ("priority_hints", any(priority_hints.values())),
            ("evidence_focus", bool(evidence_focus.get("primary") or evidence_focus.get("secondary"))),
            ("policy_adjustments", bool(policy_adjustments)),
            ("notes", bool(notes)),
        ]
        if active
    ]
    return {
        "schema_version": "monitor_entry_policy_schema_candidate.v1",
        "available": bool(explicit_fields_used),
        "entry_style": entry_style,
        "required_checks": required_checks,
        "preferred_checks": preferred_checks,
        "relaxable_checks": relaxable_checks,
        "blockers": blockers,
        "priority_hints": priority_hints,
        "evidence_focus": evidence_focus,
        "policy_adjustments": policy_adjustments,
        "notes": notes,
        "raw_keys": raw_keys,
        "explicit_fields_used": explicit_fields_used,
        "spec_validation_notes": spec_validation_notes,
        "invalid_policy_specs": invalid_policy_specs,
    }


def normalize_monitor_entry_policy(
    policy: Mapping[str, Any] | MonitorEntryPolicy | None,
    *,
    fallback_policy: MonitorEntryPolicy | None = None,
    policy_source: str = "monitor_entry_policy.v1",
) -> tuple[MonitorEntryPolicy, Dict[str, Any]]:
    default_policy = fallback_policy if isinstance(fallback_policy, MonitorEntryPolicy) else build_default_monitor_entry_policy()
    if isinstance(policy, MonitorEntryPolicy):
        normalized = policy
        if str(normalized.policy_source or "").strip() != str(policy_source or "").strip():
            normalized = MonitorEntryPolicy.from_mapping({**normalized.to_dict(), "policy_source": str(policy_source or normalized.policy_source)})
        return normalized, {
            "status": "ok",
            "fallback_used": False,
            "partial_normalized": False,
            "fallback_reason": "",
            "default_filled_fields": [],
            "missing_fields": [],
            "invalid_fields": [],
            "policy_validation_missing_fields": [],
            "policy_validation_invalid_fields": [],
            "issues": [],
            "policy_source": str(normalized.policy_source or policy_source),
        }

    source_mapping = extract_monitor_entry_policy_mapping(policy)
    source_mapping = dict(source_mapping or {})
    baseline = default_policy.to_dict()
    issues: list[str] = []
    missing_fields: list[str] = []
    invalid_fields: list[str] = []

    bounds: Dict[str, Tuple[float, float]] = {
        "timeframe_minutes": (1, 5),
        "breakout_lookback": (2, 20),
        "volume_lookback": (2, 20),
        "volume_ratio_min": (0.4, 1.5),
        "min_extended_from_vwap_pct": (-0.20, 0.0),
        "max_extended_from_vwap_pct": (0.03, 0.25),
        "pullback_min_pct": (0.0, 0.03),
        "pullback_max_pct": (0.01, 0.15),
        "reclaim_tolerance_pct": (0.0, 0.02),
        "breakout_buffer_pct": (0.0, 0.02),
        "intent_cooldown_sec": (0, 600),
    }
    bool_fields = ("enabled", "require_vwap_reclaim", "require_rebound")
    normalized: Dict[str, Any] = {}

    for field_name, default_value in baseline.items():
        if field_name == "adjustments":
            normalized[field_name] = list(source_mapping.get(field_name) or [])
            continue
        if field_name == "policy_source":
            normalized[field_name] = str(source_mapping.get(field_name) or policy_source or default_value)
            continue
        if field_name in bool_fields:
            if field_name in source_mapping:
                normalized[field_name] = _to_bool(source_mapping.get(field_name), bool(default_value))
            else:
                normalized[field_name] = bool(default_value)
                missing_fields.append(field_name)
            continue
        if field_name not in source_mapping:
            normalized[field_name] = default_value
            missing_fields.append(field_name)
            continue
        value = source_mapping.get(field_name)
        parsed = _to_int(value, int(default_value)) if isinstance(default_value, int) else _to_float(value, float(default_value))
        lower, upper = bounds.get(field_name, (float("-inf"), float("inf")))
        if not isinstance(default_value, int):
            parsed, unit_issue = _normalize_pct_unit_if_needed(field_name, float(parsed), float(lower), float(upper))
            if unit_issue:
                issues.append(unit_issue)
        if field_name == "min_extended_from_vwap_pct" and parsed > upper:
            normalized[field_name] = float(upper)
            issues.append(f"{field_name}:clamped_to_upper_bound:{parsed}->{upper}")
            continue
        if parsed < lower or parsed > upper:
            normalized[field_name] = default_value
            invalid_fields.append(field_name)
            issues.append(f"{field_name}:out_of_bounds:{parsed}")
        else:
            normalized[field_name] = parsed

    if float(normalized.get("pullback_max_pct") or 0.0) < float(normalized.get("pullback_min_pct") or 0.0):
        normalized["pullback_max_pct"] = baseline["pullback_max_pct"]
        invalid_fields.append("pullback_max_pct")
        issues.append("pullback_max_pct:below_pullback_min_pct")

    if float(normalized.get("max_extended_from_vwap_pct") or 0.0) < max(0.03, float(normalized.get("breakout_buffer_pct") or 0.0)):
        normalized["max_extended_from_vwap_pct"] = baseline["max_extended_from_vwap_pct"]
        invalid_fields.append("max_extended_from_vwap_pct")
        issues.append("max_extended_from_vwap_pct:below_minimum_viable_extension")

    default_filled_fields = list(dict.fromkeys([str(x) for x in [*missing_fields, *invalid_fields] if str(x or "").strip()]))
    fallback_used = not bool(source_mapping) or bool(invalid_fields)
    partial_normalized = bool(source_mapping) and bool(default_filled_fields) and not bool(invalid_fields)
    status = "ok"
    if not source_mapping:
        status = "fallback_default"
    elif invalid_fields:
        status = "fallback_invalid"
    elif missing_fields:
        status = "partial_normalized"
    reason_parts = []
    if not source_mapping:
        reason_parts.append("no_policy_provided")
    if missing_fields:
        reason_parts.append(f"missing_fields={','.join(missing_fields)}")
    if invalid_fields:
        reason_parts.append(f"invalid_fields={','.join(invalid_fields)}")

    policy_obj = MonitorEntryPolicy.from_mapping(normalized)
    return policy_obj, {
        "status": status,
        "fallback_used": fallback_used,
        "partial_normalized": partial_normalized,
        "fallback_reason": "; ".join(reason_parts),
        "default_filled_fields": default_filled_fields,
        "missing_fields": missing_fields,
        "invalid_fields": invalid_fields,
        "policy_validation_missing_fields": list(missing_fields),
        "policy_validation_invalid_fields": list(invalid_fields),
        "issues": issues,
        "policy_source": str(policy_obj.policy_source or policy_source),
    }
