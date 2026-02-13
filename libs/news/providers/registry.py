from __future__ import annotations

from typing import Dict, Any, Optional

from .base import NewsProvider


class NewsProviderRegistry:
    """Simple registry to select a news provider by name.

    This is intentionally minimal to keep wiring easy across agents/nodes.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, NewsProvider] = {}

    def register(self, provider: NewsProvider) -> None:
        self._providers[getattr(provider, "name")] = provider

    def get(self, name: str) -> Optional[NewsProvider]:
        return self._providers.get(name)

    def resolve(self, policy: Dict[str, Any] | None = None) -> Optional[NewsProvider]:
        policy = policy or {}
        name = str(policy.get("news_provider") or "").strip()
        if not name:
            return None
        return self.get(name)
