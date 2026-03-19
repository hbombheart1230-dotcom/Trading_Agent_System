from __future__ import annotations

import os

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


def _strict_ai_strategist_enabled(provider: str) -> bool:
    normalized = str(provider or "").strip().lower()
    if normalized not in ("openai", "http", "api"):
        return False
    raw = str(os.getenv("AI_STRATEGIST_STRICT", "true") or "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _legacy_rule_runtime_enabled() -> bool:
    raw = str(os.getenv("ALLOW_LEGACY_RULE_RUNTIME", "false") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")

def get_strategist_from_env():
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
    provider = strategist_provider()
    runtime = strategist_runtime_settings()

    if strategist_uses_rule():
        if _legacy_rule_runtime_enabled():
            return RuleStrategist()
        return BlockedStrategist(
            reason="strategist_llm_required",
            error="legacy_rule_runtime_disabled",
        )

    if strategist_uses_legacy_v1():
        allow_legacy = str(os.getenv("ALLOW_LEGACY_STRATEGY_V1_RUNTIME", "false") or "").strip().lower()
        if allow_legacy not in ("1", "true", "yes", "on"):
            return BlockedStrategist(
                reason="strategist_llm_required",
                error="legacy_strategy_v1_runtime_disabled",
            )
        return StrategyV1Strategist()

    if strategist_uses_ai():
        api_key = strategist_api_key()
        endpoint = strategist_endpoint()
        if not api_key or not endpoint:
            return BlockedStrategist(reason="strategist_llm_required", error="missing_api_key_or_endpoint")
        try:
            from libs.ai.providers.openai_provider import OpenAIStrategist
            return OpenAIStrategist.from_env()
        except Exception as exc:
            return BlockedStrategist(reason="strategist_llm_failed", error=f"{type(exc).__name__}:{exc}")

    # Unknown provider -> safe fallback
    if runtime.get("requested") or _strict_ai_strategist_enabled(provider):
        return BlockedStrategist(reason="strategist_llm_required", error=f"unsupported_provider:{provider}")
    if _legacy_rule_runtime_enabled():
        return RuleStrategist()
    return BlockedStrategist(reason="strategist_llm_required", error=f"unsupported_provider:{provider}")
