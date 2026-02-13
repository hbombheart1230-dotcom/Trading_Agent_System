from __future__ import annotations

from typing import Sequence, Dict, Any
import os

from .base import NewsItem


class GoogleNewsProvider:
    """Placeholder provider for Google News / RSS.

    Interface is batch-based: fetch(symbols=[...]).
    """

    name = "google_news"

    def fetch(
        self,
        symbols: Sequence[str],
        *,
        state: Dict[str, Any] | None = None,
        policy: Dict[str, Any] | None = None,
    ) -> Sequence[NewsItem]:
        policy = policy or {}
        live = bool(policy.get("news_live")) or (os.getenv("NEWS_LIVE") == "1")
        if not live:
            return []
        # TODO: implement real Google News collection
        return []
