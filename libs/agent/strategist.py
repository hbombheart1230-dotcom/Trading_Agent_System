from __future__ import annotations

"""Legacy strategist compatibility adapter.

Canonical strategist behavior lives in `graphs/nodes/strategist_node.py`.
This module keeps the old `libs.agent.Strategist` interface for M15/M20
compatibility (tests, legacy commander wiring, and thin DTO normalization).
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Plan:
    """Compatibility plan DTO used by legacy commander/scanner paths."""
    thesis: str
    constraints: Dict[str, Any]
    themes: List[str] = field(default_factory=list)
    candidates: List[str] = field(default_factory=list)


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _normalize_symbols(values: Any, *, limit: int) -> List[str]:
    out: List[str] = []
    seen = set()
    if not isinstance(values, list):
        return out
    for v in values:
        s = str(v or "").strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def _normalize_text_list(values: Any, *, limit: int) -> List[str]:
    out: List[str] = []
    seen = set()
    if not isinstance(values, list):
        return out
    for v in values:
        s = str(v or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= limit:
            break
    return out


class Strategist:
    """Thin compatibility wrapper for strategist output normalization.

    This class does not perform canonical candidate generation. It maps
    already-produced strategist fields into the legacy `Plan` contract.
    """

    def plan(self, *, context: Dict[str, Any]) -> Plan:
        thesis = str(context.get("thesis") or "default_thesis")
        constraints = dict(context.get("constraints") or {})
        topn = max(1, _to_int(context.get("top_n_candidates"), _to_int(os.getenv("TOP_N_CANDIDATES"), 5)))
        strategist_output = context.get("strategist_output") if isinstance(context.get("strategist_output"), dict) else {}

        themes = _normalize_text_list(strategist_output.get("themes"), limit=5)
        if not themes:
            themes = _normalize_text_list(context.get("themes"), limit=5)
        if not themes:
            themes = _normalize_text_list(context.get("top_themes"), limit=5)

        candidates = _normalize_symbols(strategist_output.get("candidates"), limit=topn)
        if not candidates:
            candidates = _normalize_symbols(context.get("candidates"), limit=topn)
        if not candidates:
            candidates = _normalize_symbols(context.get("candidate_symbols"), limit=topn)
        if not candidates:
            candidates = _normalize_symbols(context.get("watchlist_symbols"), limit=topn)
        if not candidates:
            candidates = _normalize_symbols(context.get("watchlist"), limit=topn)

        return Plan(
            thesis=thesis,
            constraints=constraints,
            themes=themes,
            candidates=candidates,
        )
