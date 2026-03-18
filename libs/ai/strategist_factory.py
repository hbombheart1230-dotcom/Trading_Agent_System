from __future__ import annotations

import os

from libs.ai.strategist import BlockedStrategist, RuleStrategist, StrategyV1Strategist


def _strict_ai_strategist_enabled(provider: str) -> bool:
    normalized = str(provider or "").strip().lower()
    if normalized not in ("openai", "http", "api"):
        return False
    raw = str(os.getenv("AI_STRATEGIST_STRICT", "true") or "").strip().lower()
    return raw not in ("0", "false", "no", "off")

def get_strategist_from_env():
    """Return a strategist instance based on env.

    Supported:
      - AI_STRATEGIST_PROVIDER=rule (default)
      - AI_STRATEGIST_PROVIDER=strategy_v1 (deterministic strategy package)
      - AI_STRATEGIST_PROVIDER=openai (HTTP endpoint wrapper)
        Requires: API key + endpoint
          - API key priority: AI_STRATEGIST_API_KEY -> OPENROUTER_API_KEY
          - Endpoint: AI_STRATEGIST_ENDPOINT
        Missing either -> explicit blocked strategist when strict AI mode is enabled
    """
    provider = (os.getenv("AI_STRATEGIST_PROVIDER") or "rule").strip().lower()

    if provider in ("rule", "rules", "local"):
        return RuleStrategist()

    if provider in ("strategy_v1", "strategy-v1", "v1", "deterministic"):
        return StrategyV1Strategist()

    if provider in ("openai", "http", "api"):
        api_key = (
            (os.getenv("AI_STRATEGIST_API_KEY") or "").strip()
            or (os.getenv("OPENROUTER_API_KEY") or "").strip()
        )
        endpoint = (os.getenv("AI_STRATEGIST_ENDPOINT") or "").strip()
        if not api_key or not endpoint:
            if _strict_ai_strategist_enabled(provider):
                return BlockedStrategist(reason="strategist_llm_required", error="missing_api_key_or_endpoint")
            return RuleStrategist()
        try:
            from libs.ai.providers.openai_provider import OpenAIStrategist
            return OpenAIStrategist.from_env()
        except Exception as exc:
            if _strict_ai_strategist_enabled(provider):
                return BlockedStrategist(reason="strategist_llm_failed", error=f"{type(exc).__name__}:{exc}")
            return RuleStrategist()

    # Unknown provider -> safe fallback
    if _strict_ai_strategist_enabled(provider):
        return BlockedStrategist(reason="strategist_llm_required", error=f"unsupported_provider:{provider}")
    return RuleStrategist()
