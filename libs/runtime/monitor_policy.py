from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Tuple


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
        "volume_priority": str(raw.get("volume_priority") or "").strip() or None,
        "reclaim_priority": str(raw.get("reclaim_priority") or "").strip() or None,
        "breakout_priority": str(raw.get("breakout_priority") or "").strip() or None,
        "pullback_priority": str(raw.get("pullback_priority") or "").strip() or None,
    }


def _normalize_evidence_focus(value: Any) -> Dict[str, Any]:
    raw = dict(value or {}) if isinstance(value, Mapping) else {}
    return {
        "primary": _dedupe_text_list(raw.get("primary")),
        "secondary": _dedupe_text_list(raw.get("secondary")),
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
    for key in ("monitor_entry_policy", "entry_policy"):
        nested = raw.get(key)
        if isinstance(nested, dict):
            merged = dict(raw)
            merged.update(dict(nested or {}))
            return merged
    return raw


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
    return {
        "contract_version": "monitor_entry_policy_contract.v1",
        "available": bool(selected_policy),
        "selected_source": str(selected_source),
        "selected_policy": dict(selected_policy),
        "selected_policy_schema": normalize_monitor_entry_policy_schema(selected_policy),
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
    raw_keys = sorted(str(k) for k in list(selected_policy.keys()))
    entry_style = str(selected_policy.get("entry_style") or selected_policy.get("playbook") or "").strip().lower() or None
    required_checks = _dedupe_text_list(selected_policy.get("required_checks"))
    preferred_checks = _dedupe_text_list(selected_policy.get("preferred_checks"))
    relaxable_checks = _dedupe_text_list(selected_policy.get("relaxable_checks"))
    blockers = _dedupe_text_list(selected_policy.get("blockers"))
    priority_hints = _normalize_priority_hints(selected_policy.get("priority_hints"))
    evidence_focus = _normalize_evidence_focus(selected_policy.get("evidence_focus"))
    policy_adjustments = _normalize_policy_adjustments(
        selected_policy.get("policy_adjustments", selected_policy.get("adjustments"))
    )
    notes = _dedupe_text_list(selected_policy.get("notes", selected_policy.get("policy_notes")))
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
