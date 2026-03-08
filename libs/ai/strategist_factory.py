from __future__ import annotations

import os

from libs.ai.strategist import RuleStrategist, StrategyV1Strategist

def get_strategist_from_env():
    """Return a strategist instance based on env.

    Supported:
      - AI_STRATEGIST_PROVIDER=rule (default)
      - AI_STRATEGIST_PROVIDER=strategy_v1 (deterministic strategy package)
      - AI_STRATEGIST_PROVIDER=openai (HTTP endpoint wrapper)
        Requires: API key + endpoint
          - API key priority: AI_STRATEGIST_API_KEY -> OPENROUTER_API_KEY
          - Endpoint: AI_STRATEGIST_ENDPOINT
        Missing either -> fallback to RuleStrategist (never crash)
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
            return RuleStrategist()
        try:
            from libs.ai.providers.openai_provider import OpenAIStrategist
            return OpenAIStrategist.from_env()
        except Exception:
            return RuleStrategist()

    # Unknown provider -> safe fallback
    return RuleStrategist()
