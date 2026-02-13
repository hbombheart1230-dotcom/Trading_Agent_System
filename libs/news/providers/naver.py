from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Sequence, Optional

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

from .base import NewsItem, NewsProvider


def _is_dry_run(policy: Dict[str, Any]) -> bool:
    v = str(os.getenv("DRY_RUN", "")).strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    return bool(policy.get("dry_run") is True)


class NaverNewsProvider(NewsProvider):
    """Naver News Search API provider (best-effort).

    - Uses env NAVER_CLIENT_ID / NAVER_CLIENT_SECRET
    - Returns dict[symbol] -> list[NewsItem]
    - In DRY_RUN or missing creds, returns empty lists.
    """

    name = "naver"

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        self.client_id = client_id or os.getenv("NAVER_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("NAVER_CLIENT_SECRET", "")

    def fetch(self, symbols: Sequence[str], policy: Dict[str, Any]) -> Dict[str, List[NewsItem]]:
        out: Dict[str, List[NewsItem]] = {str(s): [] for s in symbols}

        # Guard rails
        if _is_dry_run(policy):
            return out
        if not self.client_id or not self.client_secret:
            return out
        if requests is None:  # pragma: no cover
            return out

        base_url = str(policy.get("naver_news_url") or "https://openapi.naver.com/v1/search/news.json")
        display = int(policy.get("news_max_items_per_symbol") or 5)
        sort = str(policy.get("naver_news_sort") or "date")  # date|sim
        timeout = float(policy.get("news_timeout_sec") or 3.0)
        throttle = float(policy.get("news_throttle_sec") or 0.0)

        # optional mapping from symbol -> query string (e.g., '005930' -> '삼성전자')
        query_map: Dict[str, str] = dict(policy.get("symbol_query_map") or {})

        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }

        for sym in symbols:
            sym = str(sym)
            query = query_map.get(sym) or sym
            params = {"query": query, "display": display, "start": 1, "sort": sort}

            try:
                resp = requests.get(base_url, headers=headers, params=params, timeout=timeout)
                if resp.status_code != 200:
                    continue
                data = resp.json() if resp.content else {}
                items = data.get("items") or []
            except Exception:
                continue

            parsed: List[NewsItem] = []
            for it in items:
                try:
                    title = str(it.get("title") or "")
                    url = str(it.get("link") or it.get("originallink") or "")
                    source = "naver"
                    published_at = str(it.get("pubDate") or "")
                    summary = str(it.get("description") or "")
                    parsed.append(
                        NewsItem(
                            title=title,
                            url=url,
                            source=source,
                            published_at=published_at,
                            summary=summary,
                            symbol=sym,
                        )
                    )
                except Exception:
                    continue

            out[sym] = parsed

            if throttle > 0:
                time.sleep(throttle)

        return out
