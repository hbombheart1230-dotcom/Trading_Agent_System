from __future__ import annotations

from typing import Sequence, Dict, Any
import os

from .base import NewsItem, NewsProvider


class GoogleNewsProvider:
    """Placeholder provider.

    We deliberately do NOT implement network calls here yet.
    - When you want to go live, implement using your preferred approach (RSS, SerpAPI, GNews, etc.)
    - Keep tests deterministic by injecting mocks via state.

    Policy knobs (reserved):
      - news_live: bool (or env NEWS_LIVE=1)
      - google_news_* (api keys / endpoints)
    """

    name = "google_news"

    def fetch(self, symbol: str, *, state: Dict[str, Any] | None = None, policy: Dict[str, Any] | None = None) -> Sequence[NewsItem]:
        policy = policy or {}
        live = bool(policy.get("news_live")) or (os.getenv("NEWS_LIVE") == "1")
        if not live:
            return []
        # Intentionally unimplemented for safety/stability in early milestones.
        # Implement here when M19+ connects real sources.
        return []
