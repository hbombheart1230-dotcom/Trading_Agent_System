from __future__ import annotations

import os
from typing import Any, Dict

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
    return str(provider or "rule").strip().lower()


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
    raw = policy.get("strategist_frame_llm_strict")
    if raw is not None:
        return _is_trueish(raw)

    alias = _env_bool("STRATEGIST_FRAME_LLM_STRICT")
    if alias is not None:
        return bool(alias)

    env_value = _env_bool("AI_STRATEGIST_STRICT")
    if env_value is not None:
        return bool(env_value)
    return True


def strategist_api_key() -> str:
    return _first_env("AI_STRATEGIST_API_KEY", "OPENROUTER_API_KEY")


def strategist_endpoint() -> str:
    return _first_env("AI_STRATEGIST_ENDPOINT")


def strategist_model(policy: Dict[str, Any] | None = None) -> str:
    policy = policy or {}
    return normalize_openrouter_model_name(
        _first_nonempty(
            policy.get("ai_strategist_model"),
            policy.get("strategist_frame_llm_model"),
            os.getenv("AI_STRATEGIST_MODEL", ""),
            os.getenv("OPENROUTER_DEFAULT_MODEL", ""),
            os.getenv("STRATEGIST_FRAME_LLM_MODEL", ""),
        )
    )


def strategist_temperature(policy: Dict[str, Any] | None = None) -> float:
    policy = policy or {}
    raw = _first_nonempty(
        policy.get("ai_strategist_temperature"),
        policy.get("strategist_frame_llm_temperature"),
        os.getenv("AI_STRATEGIST_TEMPERATURE", ""),
        os.getenv("STRATEGIST_FRAME_LLM_TEMPERATURE", ""),
        os.getenv("OPENROUTER_DEFAULT_TEMPERATURE", ""),
        "0.1",
    )
    return _to_float(raw, 0.1)


def strategist_timeout_sec(policy: Dict[str, Any] | None = None) -> float:
    policy = policy or {}
    raw = _first_nonempty(
        policy.get("ai_strategist_timeout_sec"),
        policy.get("strategist_frame_llm_timeout_sec"),
        os.getenv("AI_STRATEGIST_TIMEOUT_SEC", ""),
        os.getenv("STRATEGIST_FRAME_LLM_TIMEOUT_SEC", ""),
        os.getenv("OPENROUTER_TIMEOUT_SEC", ""),
        "15",
    )
    return max(1.0, _to_float(raw, 15.0))


def strategist_max_tokens(policy: Dict[str, Any] | None = None) -> int:
    policy = policy or {}
    raw = _first_nonempty(
        policy.get("ai_strategist_max_tokens"),
        policy.get("strategist_frame_llm_max_tokens"),
        os.getenv("AI_STRATEGIST_MAX_TOKENS", ""),
        os.getenv("OPENROUTER_DEFAULT_MAX_TOKENS", ""),
        os.getenv("STRATEGIST_FRAME_LLM_MAX_TOKENS", ""),
        "320",
    )
    return max(256, _to_int(raw, 320))


def strategist_runtime_settings(policy: Dict[str, Any] | None = None) -> Dict[str, Any]:
    policy = policy or {}
    provider = strategist_provider(policy)
    return {
        "provider": provider,
        "requested": strategist_llm_requested(policy),
        "strict": strategist_llm_strict(policy),
        "uses_ai": provider in AI_STRATEGIST_PROVIDER_NAMES,
        "uses_rule": provider in RULE_STRATEGIST_PROVIDER_NAMES,
        "uses_legacy_v1": provider in LEGACY_V1_PROVIDER_NAMES,
        "api_key": strategist_api_key(),
        "endpoint": strategist_endpoint(),
        "model": strategist_model(policy),
        "temperature": strategist_temperature(policy),
        "timeout_sec": strategist_timeout_sec(policy),
        "max_tokens": strategist_max_tokens(policy),
    }
