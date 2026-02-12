from __future__ import annotations

import os
from typing import Optional

from libs.ai.strategist import RuleStrategist

def get_strategist_from_env():
    """Return a strategist instance based on env.

    Supported:
      - AI_STRATEGIST_PROVIDER=rule (default)
      - AI_STRATEGIST_PROVIDER=openai (HTTP endpoint wrapper)
        Requires: AI_STRATEGIST_API_KEY + AI_STRATEGIST_ENDPOINT
        Missing either -> fallback to RuleStrategist (never crash)
    """
    provider = (os.getenv("AI_STRATEGIST_PROVIDER") or "rule").strip().lower()

    if provider in ("rule", "rules", "local"):
        return RuleStrategist()

    if provider in ("openai", "http", "api"):
        api_key = (os.getenv("AI_STRATEGIST_API_KEY") or "").strip()
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
