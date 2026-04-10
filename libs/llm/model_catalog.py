from __future__ import annotations

from typing import Any, Dict, List

from libs.llm.model_names import normalize_openrouter_model_name


MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "minimax/minimax-m2.5": {
        "name": "minimax/minimax-m2.5",
        "provider": "minimax",
        "tier": "budget",
        "cost": "free_or_low",
        "latency": "fast",
        "supports_json": True,
    },
    "deepseek/deepseek-v3.2": {
        "name": "deepseek/deepseek-v3.2",
        "provider": "deepseek",
        "tier": "standard",
        "cost": "low",
        "latency": "medium",
        "supports_json": True,
    },
    "moonshotai/kimi-k2.5": {
        "name": "moonshotai/kimi-k2.5",
        "provider": "kimi",
        "tier": "reasoning",
        "cost": "medium",
        "latency": "medium",
        "supports_json": True,
    },
}


MODEL_PROFILES: Dict[str, List[str]] = {
    "fast_free": [
        "minimax/minimax-m2.5",
        "deepseek/deepseek-v3.2",
    ],
    "balanced": [
        "deepseek/deepseek-v3.2",
        "minimax/minimax-m2.5",
    ],
    "strong_reasoning": [
        "moonshotai/kimi-k2.5",
        "deepseek/deepseek-v3.2",
    ],
}


EXECUTION_PROFILES: Dict[str, Dict[str, Any]] = {
    "default_intraday": {
        "profile_name": "default_intraday",
        "name": "default_intraday",
        "temperature": 0.2,
        "max_tokens": 8192,
        "timeout_sec": 15,
        "retry": {
            "max_attempts": 2,
            "backoff_sec": 0.0,
        },
        "retry_max": 2,
        "retry_backoff_sec": 0.0,
    },
    "balanced_reasoning": {
        "profile_name": "balanced_reasoning",
        "name": "balanced_reasoning",
        "temperature": 0.1,
        "max_tokens": 8192,
        "timeout_sec": 15,
        "retry": {
            "max_attempts": 2,
            "backoff_sec": 0.0,
        },
        "retry_max": 2,
        "retry_backoff_sec": 0.0,
    },
    "concise_review": {
        "profile_name": "concise_review",
        "name": "concise_review",
        "temperature": 0.2,
        "max_tokens": 8192,
        "timeout_sec": 15,
        "retry": {
            "max_attempts": 2,
            "backoff_sec": 0.0,
        },
        "retry_max": 2,
        "retry_backoff_sec": 0.0,
    },
    "deep_review": {
        "profile_name": "deep_review",
        "name": "deep_review",
        "temperature": 0.2,
        "max_tokens": 8192,
        "timeout_sec": 15,
        "retry": {
            "max_attempts": 2,
            "backoff_sec": 0.0,
        },
        "retry_max": 2,
        "retry_backoff_sec": 0.0,
    },
}


def _nested_get(obj: Any, *path: str) -> Any:
    cursor = obj
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def _dedupe_models(*models: str) -> List[str]:
    out: List[str] = []
    seen = set()
    for model in models:
        normalized = normalize_openrouter_model_name(model or "")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _has_execution_profile_payload(candidate: Any) -> bool:
    if not isinstance(candidate, dict) or not candidate:
        return False
    if isinstance(candidate.get("execution_profile"), dict) and candidate.get("execution_profile"):
        return True
    for key in ("profile_name", "name", "temperature", "max_tokens", "timeout_sec", "retry", "retry_max", "retry_backoff_sec"):
        if candidate.get(key) is not None:
            return True
    return False


def get_model_card(model: str) -> Dict[str, Any]:
    normalized = normalize_openrouter_model_name(model or "")
    card = MODEL_CATALOG.get(normalized)
    if isinstance(card, dict):
        return dict(card)
    return {
        "name": normalized,
        "provider": normalized.split("/", 1)[0] if "/" in normalized else "",
        "tier": "custom",
        "cost": "unknown",
        "latency": "unknown",
        "supports_json": True,
    }


def resolve_model_profile(profile: str | None, *, default_profile: str = "balanced") -> Dict[str, Any]:
    requested = str(profile or "").strip().lower() or str(default_profile or "balanced").strip().lower() or "balanced"
    chosen_profile = requested if requested in MODEL_PROFILES else str(default_profile or "balanced").strip().lower() or "balanced"
    models = list(MODEL_PROFILES.get(chosen_profile) or MODEL_PROFILES["balanced"])
    primary = normalize_openrouter_model_name(models[0] if models else "")
    fallback = normalize_openrouter_model_name(models[1] if len(models) > 1 else "")
    return {
        "profile": chosen_profile,
        "requested_profile": requested,
        "primary": primary,
        "fallback": fallback,
        "models": _dedupe_models(primary, fallback),
        "cards": [get_model_card(primary), get_model_card(fallback)] if fallback else [get_model_card(primary)],
    }


def resolve_execution_profile(
    profile: str | None,
    *,
    default_profile: str,
    defaults: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    base_defaults = dict(defaults or {})
    requested = str(profile or "").strip().lower() or str(default_profile or "").strip().lower()
    chosen_profile = requested if requested in EXECUTION_PROFILES else str(default_profile or "").strip().lower()
    resolved = dict(base_defaults)
    profile_row = EXECUTION_PROFILES.get(chosen_profile) or {}
    for key, value in profile_row.items():
        if value is not None:
            resolved[key] = value
    retry_defaults = base_defaults.get("retry") if isinstance(base_defaults.get("retry"), dict) else {}
    retry_row = profile_row.get("retry") if isinstance(profile_row.get("retry"), dict) else {}
    retry_payload = dict(retry_defaults)
    retry_payload.update(retry_row)
    raw_retry = resolved.get("retry") if isinstance(resolved.get("retry"), dict) else {}
    retry_payload.update(raw_retry)
    if resolved.get("retry_max") is not None:
        retry_payload["max_attempts"] = resolved.get("retry_max")
    if resolved.get("retry_backoff_sec") is not None:
        retry_payload["backoff_sec"] = resolved.get("retry_backoff_sec")
    if base_defaults.get("retry_max") is not None and retry_payload.get("max_attempts") is None:
        retry_payload["max_attempts"] = base_defaults.get("retry_max")
    if base_defaults.get("retry_backoff_sec") is not None and retry_payload.get("backoff_sec") is None:
        retry_payload["backoff_sec"] = base_defaults.get("retry_backoff_sec")
    try:
        retry_max = max(0, int(float(retry_payload.get("max_attempts") if retry_payload.get("max_attempts") is not None else 2)))
    except Exception:
        retry_max = 2
    try:
            retry_backoff = max(0.0, float(retry_payload.get("backoff_sec") if retry_payload.get("backoff_sec") is not None else 0.0))
    except Exception:
        retry_backoff = 0.0
    resolved["profile_name"] = str(
        resolved.get("profile_name")
        or resolved.get("name")
        or chosen_profile
        or default_profile
    )
    resolved["name"] = str(resolved.get("name") or resolved.get("profile_name") or chosen_profile or default_profile)
    resolved["requested_profile_name"] = requested or str(default_profile or "")
    resolved["requested_name"] = requested or str(default_profile or "")
    resolved["retry"] = {
        "max_attempts": retry_max,
        "backoff_sec": retry_backoff,
    }
    resolved["retry_max"] = retry_max
    resolved["retry_backoff_sec"] = retry_backoff
    return resolved


def classify_execution_profile_source(policy_source: Any, *, env_used: bool = False) -> str:
    raw = str(policy_source or "").strip().lower()
    if env_used:
        return "fallback_env"
    if raw and raw not in {"default_execution_profile", "default", "default_profile"}:
        return "applied_policy"
    return "default"


def build_execution_profile_observability(
    execution_slot: Dict[str, Any] | None,
    *,
    env_used: bool = False,
    effective_overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    slot = dict(execution_slot or {})
    retry_slot = slot.get("retry") if isinstance(slot.get("retry"), dict) else {}
    retry_max = retry_slot.get("max_attempts", slot.get("retry_max"))
    retry_backoff_sec = retry_slot.get("backoff_sec", slot.get("retry_backoff_sec"))
    effective = {
        "temperature": slot.get("temperature"),
        "max_tokens": slot.get("max_tokens"),
        "timeout_sec": slot.get("timeout_sec"),
        "retry": {
            "max_attempts": retry_max,
            "backoff_sec": retry_backoff_sec,
        },
    }
    if isinstance(effective_overrides, dict):
        for key in ("temperature", "max_tokens", "timeout_sec"):
            if effective_overrides.get(key) is not None:
                effective[key] = effective_overrides.get(key)
        retry_overrides = effective_overrides.get("retry") if isinstance(effective_overrides.get("retry"), dict) else {}
        if effective_overrides.get("retry_max") is not None:
            effective["retry"]["max_attempts"] = effective_overrides.get("retry_max")
        if effective_overrides.get("retry_backoff_sec") is not None:
            effective["retry"]["backoff_sec"] = effective_overrides.get("retry_backoff_sec")
        if retry_overrides.get("max_attempts") is not None:
            effective["retry"]["max_attempts"] = retry_overrides.get("max_attempts")
        if retry_overrides.get("backoff_sec") is not None:
            effective["retry"]["backoff_sec"] = retry_overrides.get("backoff_sec")
    return {
        "llm_execution_profile_name": str(slot.get("profile_name") or slot.get("name") or ""),
        "llm_execution_profile_source": classify_execution_profile_source(slot.get("policy_source"), env_used=env_used),
        "llm_execution_effective_config": effective,
    }


def resolve_policy_llm_slot(policy: Dict[str, Any] | None, *path: str, default_profile: str) -> Dict[str, Any]:
    container = policy if isinstance(policy, dict) else {}
    slot: Dict[str, Any] = {}
    slot_source = "default_profile"
    for candidate, source in (
        (_nested_get(container, "applied_policy", "llm", *path), "applied_policy.llm"),
        (_nested_get(container, "commander", "applied_policy", "llm", *path), "commander.applied_policy.llm"),
        (_nested_get(container, "reporter_output", "applied_policy", "llm", *path), "reporter_output.applied_policy.llm"),
        (_nested_get(container, "llm", *path), "llm"),
        (_nested_get(container, "reporter_policy", "llm", *path), "reporter_policy.llm"),
    ):
        if isinstance(candidate, dict) and candidate:
            slot = dict(candidate)
            slot_source = source
            break

    resolved = resolve_model_profile(str(slot.get("profile") or ""), default_profile=default_profile)
    primary = normalize_openrouter_model_name(
        str(slot.get("primary") or slot.get("model") or resolved.get("primary") or "")
    )
    fallback = normalize_openrouter_model_name(
        str(slot.get("fallback") or resolved.get("fallback") or "")
    )
    cards = [get_model_card(model) for model in _dedupe_models(primary, fallback)]
    return {
        "profile": str(slot.get("profile") or resolved.get("profile") or default_profile),
        "requested_profile": str(slot.get("profile") or resolved.get("requested_profile") or default_profile),
        "primary": primary,
        "fallback": fallback,
        "models": _dedupe_models(primary, fallback),
        "cards": cards,
        "policy_source": str(slot.get("policy_source") or slot_source or "default_profile"),
        "profile_source": slot_source,
    }


def resolve_policy_llm_execution_slot(
    policy: Dict[str, Any] | None,
    *path: str,
    default_profile: str,
    defaults: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    container = policy if isinstance(policy, dict) else {}
    slot: Dict[str, Any] = {}
    slot_source = "default_execution_profile"
    for candidate, source in (
        (_nested_get(container, "applied_policy", "llm", "execution_profile"), "applied_policy.llm.execution_profile"),
        (_nested_get(container, "applied_policy", "llm", *path), "applied_policy.llm"),
        (_nested_get(container, "commander", "applied_policy", "llm", "execution_profile"), "commander.applied_policy.llm.execution_profile"),
        (_nested_get(container, "commander", "applied_policy", "llm", *path), "commander.applied_policy.llm"),
        (_nested_get(container, "reporter_output", "applied_policy", "llm", "execution_profile"), "reporter_output.applied_policy.llm.execution_profile"),
        (_nested_get(container, "reporter_output", "applied_policy", "llm", *path), "reporter_output.applied_policy.llm"),
        (_nested_get(container, "llm", "execution_profile"), "llm.execution_profile"),
        (_nested_get(container, "llm", *path), "llm"),
        (_nested_get(container, "reporter_policy", "llm", "execution_profile"), "reporter_policy.llm.execution_profile"),
        (_nested_get(container, "reporter_policy", "llm", *path), "reporter_policy.llm"),
    ):
        if _has_execution_profile_payload(candidate):
            slot = dict(candidate)
            slot_source = source
            break

    execution_slot = slot.get("execution_profile") if isinstance(slot.get("execution_profile"), dict) else {}
    if not execution_slot:
        execution_slot = {
            key: slot.get(key)
            for key in ("profile_name", "name", "temperature", "max_tokens", "timeout_sec", "retry_max", "retry_backoff_sec")
            if slot.get(key) is not None
        }
        if isinstance(slot.get("retry"), dict):
            execution_slot["retry"] = dict(slot.get("retry") or {})

    resolved = resolve_execution_profile(
        str(execution_slot.get("profile_name") or execution_slot.get("name") or ""),
        default_profile=default_profile,
        defaults=defaults,
    )
    merged = dict(resolved)
    for key in ("temperature", "max_tokens", "timeout_sec", "retry_max", "retry_backoff_sec"):
        if execution_slot.get(key) is not None:
            merged[key] = execution_slot.get(key)
    if isinstance(execution_slot.get("retry"), dict):
        retry_payload = dict(merged.get("retry") or {})
        retry_payload.update(dict(execution_slot.get("retry") or {}))
        merged["retry"] = retry_payload
        if retry_payload.get("max_attempts") is not None:
            merged["retry_max"] = retry_payload.get("max_attempts")
        if retry_payload.get("backoff_sec") is not None:
            merged["retry_backoff_sec"] = retry_payload.get("backoff_sec")
    merged["profile_name"] = str(
        execution_slot.get("profile_name")
        or execution_slot.get("name")
        or merged.get("profile_name")
        or merged.get("name")
        or default_profile
    )
    merged["name"] = str(execution_slot.get("name") or merged.get("name") or merged.get("profile_name") or default_profile)
    merged["requested_profile_name"] = str(
        execution_slot.get("profile_name")
        or execution_slot.get("name")
        or merged.get("requested_profile_name")
        or default_profile
    )
    merged["requested_name"] = str(execution_slot.get("name") or merged.get("requested_name") or default_profile)
    retry_payload = merged.get("retry") if isinstance(merged.get("retry"), dict) else {}
    if merged.get("retry_max") is not None:
        retry_payload["max_attempts"] = merged.get("retry_max")
    if merged.get("retry_backoff_sec") is not None:
        retry_payload["backoff_sec"] = merged.get("retry_backoff_sec")
    merged["retry"] = retry_payload
    merged["retry_max"] = retry_payload.get("max_attempts")
    merged["retry_backoff_sec"] = retry_payload.get("backoff_sec")
    merged["policy_source"] = str(execution_slot.get("policy_source") or slot.get("policy_source") or slot_source)
    merged["profile_source"] = slot_source
    return merged
