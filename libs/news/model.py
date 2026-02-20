from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class NewsItem:
    """
    Minimal, stable contract for news pipeline.

    Tests expect:
      NewsItem(title=..., url=..., source=..., published_at=..., symbol=..., summary=...)
    """
    title: str
    url: str
    source: str
    published_at: str
    symbol: str
    summary: str = ""
    raw: Optional[Dict[str, Any]] = None