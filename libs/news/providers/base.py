from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, Optional, Dict, Any


@dataclass(frozen=True)
class NewsItem:
    title: str
    # Optional metadata (kept flexible for providers/scorers)
    url: Optional[str] = None
    source: Optional[str] = None
    published_at: Optional[str] = None
    summary: Optional[str] = None
    symbol: Optional[str] = None  # provider may tag the related symbol


class NewsProvider(Protocol):
    """Provider interface for fetching news items.

    We fetch in *batch* to avoid per-symbol network chatter.
    Providers MUST be best-effort and may return an empty list.
    """

    name: str

    def fetch(
        self,
        symbols: Sequence[str],
        *,
        state: Dict[str, Any] | None = None,
        policy: Dict[str, Any] | None = None,
    ) -> Sequence[NewsItem]:
        ...
