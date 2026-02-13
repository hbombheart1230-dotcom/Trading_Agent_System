"""Role-based LLM router.

Goal:
- Different agent roles can use different OpenRouter models.
- Switching providers later only requires swapping this router/client.

Env:
- OPENROUTER_DEFAULT_MODEL
- OPENROUTER_MODEL_<ROLE> e.g. OPENROUTER_MODEL_STRATEGIST
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from libs.llm.openrouter_client import OpenRouterClient


def _env_model_key(role: str) -> str:
    return f"OPENROUTER_MODEL_{role.upper()}"


@dataclass
class LLMRoute:
    role: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 512


class LLMRouter:
    def __init__(self, client: Optional[OpenRouterClient]):
        self.client = client

    @staticmethod
    def from_env() -> "LLMRouter":
        return LLMRouter(client=OpenRouterClient.from_env())

    def resolve(self, role: str, *, policy: Optional[Dict[str, Any]] = None) -> LLMRoute:
        policy = policy or {}
        # policy overrides env
        model = (policy.get("openrouter_model") or policy.get("model") or "").strip()
        if not model:
            model = (os.getenv(_env_model_key(role), "") or "").strip()
        if not model:
            model = (os.getenv("OPENROUTER_DEFAULT_MODEL", "") or "").strip()
        if not model:
            # conservative default (user can override)
            model = "openai/gpt-4o-mini"

        temperature = float(policy.get("temperature") or os.getenv("OPENROUTER_DEFAULT_TEMPERATURE", "0.2"))
        max_tokens = int(policy.get("max_tokens") or os.getenv("OPENROUTER_DEFAULT_MAX_TOKENS", "512"))
        return LLMRoute(role=role, model=model, temperature=temperature, max_tokens=max_tokens)

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Optional[Dict[str, Any]] = None) -> str:
        if self.client is None:
            return ""
        route = self.resolve(role, policy=policy)
        payload: Dict[str, Any] = {
            "model": route.model,
            "messages": messages,
            "temperature": route.temperature,
            "max_tokens": route.max_tokens,
        }
        # allow advanced OpenRouter passthrough fields
        if policy:
            for k in ("top_p", "presence_penalty", "frequency_penalty", "seed"):
                if k in policy:
                    payload[k] = policy[k]
        resp = self.client.chat_completions(payload)
        return self.client.extract_text(resp)
