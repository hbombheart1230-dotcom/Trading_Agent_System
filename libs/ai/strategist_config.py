from __future__ import annotations

import os
from typing import Any, Dict

from libs.llm.model_catalog import build_execution_profile_observability, resolve_policy_llm_execution_slot, resolve_policy_llm_slot
from libs.llm.model_names import normalize_openrouter_model_name


AI_STRATEGIST_PROVIDER_NAMES = {"openai", "http", "api"}
RULE_STRATEGIST_PROVIDER_NAMES = {"rule", "rules", "local"}
LEGACY_V1_PROVIDER_NAMES = {"strategy_v1", "strategy-v1", "v1", "deterministic"}


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _first_env(*names: str) -> str:
    for name in names:
        value = _first_nonempty(os.getenv(name, ""))
        if value:
            return value
    return ""


def _env_bool(name: str) -> bool | None:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return None
    return _is_trueish(raw)


def _nested_get(mapping: Any, *path: str) -> Any:
    cursor = mapping if isinstance(mapping, dict) else {}
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


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


def strategist_provider(policy: Dict[str, Any] | None = None) -> str:
    policy = policy or {}
    provider = _first_nonempty(
        policy.get("ai_strategist_provider"),
        policy.get("strategist_provider"),
        os.getenv("AI_STRATEGIST_PROVIDER", ""),
    )
    if provider:
        return str(provider).strip().lower()
    if _first_nonempty(
        policy.get("ai_strategist_endpoint"),
        policy.get("endpoint"),
        _nested_get(policy, "applied_policy", "llm", "strategist", "primary"),
        _nested_get(policy, "applied_policy", "llm", "strategist", "profile"),
        _nested_get(policy, "llm", "strategist", "primary"),
        _nested_get(policy, "llm", "strategist", "profile"),
        os.getenv("AI_STRATEGIST_ENDPOINT", ""),
    ):
        return "openai"
    return "rule"


def strategist_uses_ai(policy: Dict[str, Any] | None = None) -> bool:
    return strategist_provider(policy) in AI_STRATEGIST_PROVIDER_NAMES


def strategist_uses_rule(policy: Dict[str, Any] | None = None) -> bool:
    return strategist_provider(policy) in RULE_STRATEGIST_PROVIDER_NAMES


def strategist_uses_legacy_v1(policy: Dict[str, Any] | None = None) -> bool:
    return strategist_provider(policy) in LEGACY_V1_PROVIDER_NAMES


def strategist_llm_requested(policy: Dict[str, Any] | None = None) -> bool:
    policy = policy or {}
    raw = policy.get("strategist_frame_use_llm")
    if raw is not None:
        return _is_trueish(raw)

    alias = _env_bool("STRATEGIST_FRAME_USE_LLM")
    if alias is not None:
        return bool(alias)

    return strategist_uses_ai(policy)


def strategist_llm_strict(policy: Dict[str, Any] | None = None) -> bool:
    policy = policy or {}
    nested_runtime = policy.get("strategist") if isinstance(policy.get("strategist"), dict) else {}
    nested_runtime = nested_runtime.get("runtime") if isinstance(nested_runtime.get("runtime"), dict) else {}
    if nested_runtime.get("strict_mode") is not None:
        return _is_trueish(nested_runtime.get("strict_mode"))
    runtime_policy = policy.get("strategist_runtime") if isinstance(policy.get("strategist_runtime"), dict) else {}
    if runtime_policy.get("strict_mode") is not None:
        return _is_trueish(runtime_policy.get("strict_mode"))
    raw = policy.get("strategist_frame_llm_strict")
    if raw is not None:
        return _is_trueish(raw)

    alias = _env_bool("STRATEGIST_FRAME_LLM_STRICT")
    if alias is not None:
        return bool(alias)
    return True


def strategist_api_key(policy: Dict[str, Any] | None = None) -> str:
    policy = policy or {}
    return _first_nonempty(
        policy.get("ai_strategist_api_key"),
        policy.get("api_key"),
        _first_env("AI_STRATEGIST_API_KEY", "OPENROUTER_API_KEY"),
    )


def strategist_endpoint(policy: Dict[str, Any] | None = None) -> str:
    policy = policy or {}
    return _first_nonempty(
        policy.get("ai_strategist_endpoint"),
        policy.get("endpoint"),
        _first_env("AI_STRATEGIST_ENDPOINT"),
    )


def strategist_model(policy: Dict[str, Any] | None = None) -> str:
    policy = policy or {}
    llm_slot = resolve_policy_llm_slot(policy, "strategist", default_profile="balanced")
    return normalize_openrouter_model_name(
        _first_nonempty(
            llm_slot.get("primary"),
            policy.get("ai_strategist_model"),
            policy.get("strategist_frame_llm_model"),
        )
    )


def strategist_fallback_model(policy: Dict[str, Any] | None = None) -> str:
    policy = policy or {}
    llm_slot = resolve_policy_llm_slot(policy, "strategist", default_profile="balanced")
    return normalize_openrouter_model_name(
        _first_nonempty(
            llm_slot.get("fallback"),
            policy.get("ai_strategist_model_fallback"),
            policy.get("strategist_frame_llm_fallback_model"),
        )
    )


def strategist_temperature(policy: Dict[str, Any] | None = None) -> float:
    policy = policy or {}
    execution_slot = resolve_policy_llm_execution_slot(
        policy,
        "strategist",
        default_profile="balanced_reasoning",
        defaults={
            "name": "balanced_reasoning",
            "temperature": 0.1,
            "max_tokens": 8192,
            "timeout_sec": 15,
            "retry_max": 2,
        },
    )
    raw = _first_nonempty(
        execution_slot.get("temperature"),
        policy.get("ai_strategist_temperature"),
        policy.get("strategist_frame_llm_temperature"),
        "0.1",
    )
    return _to_float(raw, 0.1)


def strategist_timeout_sec(policy: Dict[str, Any] | None = None) -> float:
    policy = policy or {}
    execution_slot = resolve_policy_llm_execution_slot(
        policy,
        "strategist",
        default_profile="balanced_reasoning",
        defaults={
            "name": "balanced_reasoning",
            "temperature": 0.1,
            "max_tokens": 8192,
            "timeout_sec": 15,
            "retry_max": 2,
        },
    )
    raw = _first_nonempty(
        execution_slot.get("timeout_sec"),
        policy.get("ai_strategist_timeout_sec"),
        policy.get("strategist_frame_llm_timeout_sec"),
        "15",
    )
    return max(1.0, _to_float(raw, 15.0))


def strategist_max_tokens(policy: Dict[str, Any] | None = None) -> int:
    policy = policy or {}
    execution_slot = resolve_policy_llm_execution_slot(
        policy,
        "strategist",
        default_profile="balanced_reasoning",
        defaults={
            "name": "balanced_reasoning",
            "temperature": 0.1,
            "max_tokens": 8192,
            "timeout_sec": 15,
            "retry_max": 2,
        },
    )
    raw = _first_nonempty(
        execution_slot.get("max_tokens"),
        policy.get("ai_strategist_max_tokens"),
        policy.get("strategist_frame_llm_max_tokens"),
        "8192",
    )
    return max(256, _to_int(raw, 8192))


def strategist_retry_max(policy: Dict[str, Any] | None = None) -> int:
    policy = policy or {}
    execution_slot = resolve_policy_llm_execution_slot(
        policy,
        "strategist",
        default_profile="balanced_reasoning",
        defaults={
            "name": "balanced_reasoning",
            "temperature": 0.1,
            "max_tokens": 8192,
            "timeout_sec": 15,
            "retry_max": 2,
        },
    )
    raw = _first_nonempty(
        execution_slot.get("retry_max"),
        policy.get("ai_strategist_retry_max"),
        policy.get("strategist_frame_llm_retry_max"),
        "2",
    )
    return max(0, _to_int(raw, 2))


def strategist_retry_backoff_sec(policy: Dict[str, Any] | None = None) -> float:
    policy = policy or {}
    execution_slot = resolve_policy_llm_execution_slot(
        policy,
        "strategist",
        default_profile="balanced_reasoning",
        defaults={
            "profile_name": "balanced_reasoning",
            "name": "balanced_reasoning",
            "temperature": 0.1,
            "max_tokens": 8192,
            "timeout_sec": 15,
            "retry": {"max_attempts": 2, "backoff_sec": 0.0},
            "retry_max": 2,
            "retry_backoff_sec": 0.0,
        },
    )
    raw = _first_nonempty(
        execution_slot.get("retry_backoff_sec"),
        (execution_slot.get("retry") or {}).get("backoff_sec") if isinstance(execution_slot.get("retry"), dict) else None,
        os.getenv("AI_STRATEGIST_RETRY_BACKOFF_SEC", ""),
        "0.0",
    )
    return max(0.0, _to_float(raw, 0.0))


def strategist_runtime_settings(policy: Dict[str, Any] | None = None) -> Dict[str, Any]:
    policy = policy or {}
    llm_slot = resolve_policy_llm_slot(policy, "strategist", default_profile="balanced")
    execution_slot = resolve_policy_llm_execution_slot(
        policy,
        "strategist",
        default_profile="balanced_reasoning",
        defaults={
            "profile_name": "balanced_reasoning",
            "name": "balanced_reasoning",
            "temperature": 0.1,
            "max_tokens": 8192,
            "timeout_sec": 15,
            "retry": {"max_attempts": 2, "backoff_sec": 0.0},
            "retry_max": 2,
            "retry_backoff_sec": 0.0,
        },
    )
    provider = strategist_provider(policy)
    env_profile_fallback_used = False
    if str(execution_slot.get("policy_source") or "").strip().lower() in {"", "default_execution_profile", "default"}:
        env_profile_fallback_used = bool(
            _first_nonempty(
                os.getenv("AI_STRATEGIST_TIMEOUT_SEC", ""),
                os.getenv("AI_STRATEGIST_MAX_TOKENS", ""),
                os.getenv("AI_STRATEGIST_RETRY_MAX", ""),
                os.getenv("AI_STRATEGIST_RETRY_BACKOFF_SEC", ""),
            )
        )
    execution_profile_observability = build_execution_profile_observability(
        execution_slot,
        env_used=env_profile_fallback_used,
        effective_overrides={
            "temperature": strategist_temperature(policy),
            "max_tokens": strategist_max_tokens(policy),
            "timeout_sec": strategist_timeout_sec(policy),
            "retry": {
                "max_attempts": strategist_retry_max(policy),
                "backoff_sec": strategist_retry_backoff_sec(policy),
            },
        },
    )
    return {
        "provider": provider,
        "requested": strategist_llm_requested(policy),
        "strict": strategist_llm_strict(policy),
        "uses_ai": provider in AI_STRATEGIST_PROVIDER_NAMES,
        "uses_rule": provider in RULE_STRATEGIST_PROVIDER_NAMES,
        "uses_legacy_v1": provider in LEGACY_V1_PROVIDER_NAMES,
        "api_key": strategist_api_key(policy),
        "endpoint": strategist_endpoint(policy),
        "model": strategist_model(policy),
        "fallback_model": strategist_fallback_model(policy),
        "llm_profile": str(llm_slot.get("profile") or "balanced"),
        "llm_policy_source": str(llm_slot.get("policy_source") or "default_profile"),
        "temperature": strategist_temperature(policy),
        "timeout_sec": strategist_timeout_sec(policy),
        "max_tokens": strategist_max_tokens(policy),
        "retry_max": strategist_retry_max(policy),
        "retry_backoff_sec": strategist_retry_backoff_sec(policy),
        "llm_execution_profile": execution_slot,
        "llm_execution_profile_name": str(execution_profile_observability.get("llm_execution_profile_name") or ""),
        "llm_execution_profile_source": str(execution_profile_observability.get("llm_execution_profile_source") or "default"),
        "llm_execution_effective_config": dict(execution_profile_observability.get("llm_execution_effective_config") or {}),
    }
