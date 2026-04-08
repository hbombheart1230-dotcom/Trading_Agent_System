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
    "balanced_reasoning": {
        "name": "balanced_reasoning",
        "temperature": 0.1,
        "max_tokens": 8192,
        "timeout_sec": 15,
        "retry_max": 2,
    },
    "concise_review": {
        "name": "concise_review",
        "temperature": 0.2,
        "max_tokens": 8192,
    },
    "deep_review": {
        "name": "deep_review",
        "temperature": 0.2,
        "max_tokens": 8192,
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
    resolved["name"] = str(resolved.get("name") or chosen_profile or default_profile)
    resolved["requested_name"] = requested or str(default_profile or "")
    return resolved


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

    execution_slot = slot.get("execution_profile") if isinstance(slot.get("execution_profile"), dict) else {}
    if not execution_slot:
        execution_slot = {
            key: slot.get(key)
            for key in ("name", "temperature", "max_tokens", "timeout_sec", "retry_max")
            if slot.get(key) is not None
        }

    resolved = resolve_execution_profile(
        str(execution_slot.get("name") or ""),
        default_profile=default_profile,
        defaults=defaults,
    )
    merged = dict(resolved)
    for key in ("temperature", "max_tokens", "timeout_sec", "retry_max"):
        if execution_slot.get(key) is not None:
            merged[key] = execution_slot.get(key)
    merged["name"] = str(execution_slot.get("name") or merged.get("name") or default_profile)
    merged["requested_name"] = str(execution_slot.get("name") or merged.get("requested_name") or default_profile)
    merged["policy_source"] = str(execution_slot.get("policy_source") or slot.get("policy_source") or slot_source)
    merged["profile_source"] = slot_source
    return merged
