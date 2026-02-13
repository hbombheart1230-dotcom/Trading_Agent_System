from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ConditionQuery:
    """Normalized condition-search query.

    Use either `condition_id` or `condition_name`.
    """

    condition_id: Optional[int] = None
    condition_name: Optional[str] = None


def _parse_symbols(x: Any) -> List[str]:
    if isinstance(x, list):
        raw = x
    elif isinstance(x, str):
        raw = [s.strip() for s in x.split(",")]
    else:
        raw = []

    out: List[str] = []
    for s in raw:
        if isinstance(s, str) and s.strip():
            out.append(s.strip())
    # de-dup while preserving order
    dedup: List[str] = []
    seen = set()
    for s in out:
        if s not in seen:
            dedup.append(s)
            seen.add(s)
    return dedup


class KiwoomConditionReader:
    """Condition-search symbols reader.

    M18-2 provides the contract and test-friendly fallback.
    Real Kiwoom REST wiring can be implemented later without changing callers.

    Injection points for tests/DRY_RUN:
      - state['mock_condition_symbols'] = ['005930', ...]
      - env MOCK_CONDITION_SYMBOLS='005930,000660,...'
    """

    def __init__(self) -> None:
        pass

    def get_symbols(
        self,
        state: Dict[str, Any],
        query: Optional[ConditionQuery] = None,
        limit: int = 200,
    ) -> List[str]:
        symbols = _parse_symbols(state.get("mock_condition_symbols"))
        if symbols:
            return symbols[:limit]

        env_symbols = os.getenv("MOCK_CONDITION_SYMBOLS", "")
        symbols = _parse_symbols(env_symbols)
        if symbols:
            return symbols[:limit]

        # No real API integration yet.
        return []
