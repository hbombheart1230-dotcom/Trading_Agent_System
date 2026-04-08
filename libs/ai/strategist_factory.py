from __future__ import annotations

from libs.ai.strategist_config import (
    strategist_api_key,
    strategist_endpoint,
    strategist_provider,
    strategist_runtime_settings,
    strategist_uses_ai,
    strategist_uses_legacy_v1,
    strategist_uses_rule,
)
from libs.ai.strategist import BlockedStrategist, RuleStrategist, StrategyV1Strategist


def _strict_ai_strategist_enabled(provider: str, policy: dict | None = None) -> bool:
    normalized = str(provider or "").strip().lower()
    if normalized not in ("openai", "http", "api"):
        return False
    return bool(strategist_runtime_settings(policy).get("strict", True))


def _legacy_rule_runtime_enabled(policy: dict | None = None) -> bool:
    runtime_policy = policy.get("strategist") if isinstance(policy, dict) and isinstance(policy.get("strategist"), dict) else {}
    runtime_policy = runtime_policy.get("runtime") if isinstance(runtime_policy.get("runtime"), dict) else {}
    if runtime_policy.get("allow_legacy_rule") is not None:
        return bool(runtime_policy.get("allow_legacy_rule"))
    if isinstance(policy, dict) and policy.get("allow_legacy_rule_runtime") is not None:
        return str(policy.get("allow_legacy_rule_runtime") or "").strip().lower() in ("1", "true", "yes", "on")
    return False

def get_strategist_from_env(policy: dict | None = None):
    """Return a strategist instance based on env.

    Supported:
      - AI_STRATEGIST_PROVIDER=rule (explicit legacy/manual mode)
      - AI_STRATEGIST_PROVIDER=strategy_v1 (legacy deterministic package; discouraged)
      - AI_STRATEGIST_PROVIDER=openai (canonical strategist LLM mode)
        Requires: API key + endpoint
          - API key priority: AI_STRATEGIST_API_KEY -> OPENROUTER_API_KEY
          - Endpoint: AI_STRATEGIST_ENDPOINT
        Missing either -> explicit blocked strategist when strict AI mode is enabled
    """
    provider = strategist_provider(policy)
    runtime = strategist_runtime_settings(policy)

    if strategist_uses_rule(policy):
        if _legacy_rule_runtime_enabled(policy):
            return RuleStrategist()
        return BlockedStrategist(
            reason="strategist_llm_required",
            error="legacy_rule_runtime_disabled",
        )

    if strategist_uses_legacy_v1(policy):
        runtime_policy = policy.get("strategist") if isinstance(policy, dict) and isinstance(policy.get("strategist"), dict) else {}
        runtime_policy = runtime_policy.get("runtime") if isinstance(runtime_policy.get("runtime"), dict) else {}
        allow_legacy = runtime_policy.get("allow_legacy_strategy_v1")
        if allow_legacy is None and isinstance(policy, dict):
            allow_legacy = policy.get("allow_legacy_strategy_v1_runtime")
        if str(allow_legacy or "").strip().lower() not in ("1", "true", "yes", "on"):
            return BlockedStrategist(
                reason="strategist_llm_required",
                error="legacy_strategy_v1_runtime_disabled",
            )
        return StrategyV1Strategist()

    if strategist_uses_ai(policy):
        api_key = strategist_api_key(policy)
        endpoint = strategist_endpoint(policy)
        if not api_key or not endpoint:
            return BlockedStrategist(reason="strategist_llm_required", error="missing_api_key_or_endpoint")
        try:
            from libs.ai.providers.openai_provider import OpenAIStrategist
            return OpenAIStrategist.from_env(policy)
        except Exception as exc:
            return BlockedStrategist(reason="strategist_llm_failed", error=f"{type(exc).__name__}:{exc}")

    # Unknown provider -> safe fallback
    if runtime.get("requested") or _strict_ai_strategist_enabled(provider, policy):
        return BlockedStrategist(reason="strategist_llm_required", error=f"unsupported_provider:{provider}")
    if _legacy_rule_runtime_enabled(policy):
        return RuleStrategist()
    return BlockedStrategist(reason="strategist_llm_required", error=f"unsupported_provider:{provider}")
