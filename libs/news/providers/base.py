from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, Optional, Dict, Any


@dataclass(frozen=True)
class NewsItem:
    title: str
    published_at: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None


class NewsProvider(Protocol):
    """Provider interface for fetching news items per symbol/keyword.

    IMPORTANT:
      - Providers should be best-effort and may return an empty list.
      - Providers MUST NOT raise for normal 'no data' conditions.
      - Network access should be opt-in via policy/env; tests should inject mocks.
    """

    name: str

    def fetch(self, symbol: str, *, state: Dict[str, Any] | None = None, policy: Dict[str, Any] | None = None) -> Sequence[NewsItem]:
        ...
