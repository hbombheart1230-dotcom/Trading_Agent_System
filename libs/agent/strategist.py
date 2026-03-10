from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Plan:
    """Strategist output: describes what to look for, not how to execute."""
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
    """Produces a high-level plan for a run.

    In M15 we keep this deterministic/minimal by default.
    You can later plug in LLM reasoning, news context, etc.
    """

    def plan(self, *, context: Dict[str, Any]) -> Plan:
        thesis = str(context.get("thesis") or "default_thesis")
        constraints = dict(context.get("constraints") or {})
        topn = max(1, _to_int(context.get("top_n_candidates"), _to_int(os.getenv("TOP_N_CANDIDATES"), 5)))
        themes = _normalize_text_list(context.get("themes"), limit=5)
        if not themes:
            themes = _normalize_text_list(context.get("top_themes"), limit=5)

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
