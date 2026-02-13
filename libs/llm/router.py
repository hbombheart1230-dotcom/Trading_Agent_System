"""Backward-compatible LLM router module.

Historical note:
- Earlier milestones introduced `libs.llm.router.LLMRouter` returning raw provider responses.
- Newer milestones standardized on `libs.llm.llm_router.LLMRouter` returning plain text.

To avoid import churn, we keep this module and provide:
- `TextLLMRouter` (preferred): alias of the new text-returning router
- `LLMRouter` (legacy): thin wrapper that returns raw JSON-like responses via OpenRouterClient

New code should use:
    from libs.llm import LLMRouter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from libs.llm.llm_router import LLMRouter as TextLLMRouter
from libs.llm.openrouter_client import ChatMessage, OpenRouterClient


@dataclass(frozen=True)
class ModelSpec:
    model: str
    temperature: float = 0.2
    max_tokens: int = 256


class LLMRouter:
    """Legacy router that returns raw provider responses.

This is kept only for compatibility with older code paths.
"""

    def __init__(self, client: Optional[OpenRouterClient] = None) -> None:
        self.client = client or OpenRouterClient.from_env()

    def chat(
        self,
        *,
        role: str,
        policy: Dict[str, Any],
        messages: Sequence[ChatMessage],
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self.client is None:
            return {}

        # Reuse the new router to resolve model/temperature/max_tokens consistently
        t = TextLLMRouter(client=self.client)
        route = t.resolve(role=role, policy=policy)

        payload: Dict[str, Any] = {
            "model": route.model,
            "messages": list(messages),
            "temperature": route.temperature,
            "max_tokens": route.max_tokens,
        }
        if extra:
            payload.update(extra)
        return self.client.chat_completions(payload)


__all__ = ["LLMRouter", "TextLLMRouter", "ModelSpec"]
