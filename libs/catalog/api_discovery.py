# libs/api_discovery.py
from dataclasses import dataclass
from typing import List, Optional

from libs.catalog.api_catalog import ApiCatalog, ApiSpec


@dataclass(frozen=True)
class ApiMatch:
    spec: ApiSpec
    score: float
    reasons: List[str]


class ApiDiscovery:
    """
    Discovery-only module.
    - No execution
    - No side effects
    - Returns Top-K candidate APIs
    """

    def __init__(self, catalog: ApiCatalog):
        self.catalog = catalog

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        require_tags: Optional[List[str]] = None,
        method: Optional[str] = None,
        callable_only: bool = True,
    ) -> List[ApiMatch]:

        query_l = query.lower()
        matches: List[ApiMatch] = []

        for spec in self.catalog.list_specs():
            reasons = []
            score = 0.0

            # callable filter
            if callable_only:
                if spec.extra.get("_flags", {}).get("callable") is False:
                    continue

            # method filter
            if method and spec.method and spec.method != method:
                continue

            # tag filter
            if require_tags:
                if not set(require_tags).issubset(set(spec.tags)):
                    continue

            # simple lexical scoring
            if query_l in spec.api_id.lower():
                score += 0.4
                reasons.append("api_id match")

            if query_l in (spec.title or "").lower():
                score += 0.4
                reasons.append("title match")

            if query_l in (spec.description or "").lower():
                score += 0.2
                reasons.append("description match")

            if score > 0:
                matches.append(ApiMatch(spec=spec, score=score, reasons=reasons))

        matches.sort(key=lambda x: x.score, reverse=True)
        return matches[:top_k]
