from __future__ import annotations

import os
from typing import Any, Dict, List, Set, Tuple


# No built-in static symbols by default.
# Fallback must come from runtime/config input to avoid hidden fixed-universe bias.
DEFAULT_FALLBACK_SYMBOLS: List[str] = []


def _norm_symbol(v: Any) -> str:
    return str(v or "").strip().upper()


def _unique_symbols(items: Any) -> List[str]:
    if not isinstance(items, list):
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for row in items:
        s = _norm_symbol(row)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _from_csv(raw: str) -> List[str]:
    values = [x.strip() for x in str(raw or "").split(",")]
    return _unique_symbols(values)


def _watchlist_like_symbols(*, state: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    rows: List[str] = []
    rows.extend(_unique_symbols(state.get("watchlist_symbols")))
    rows.extend(_unique_symbols(state.get("watchlist")))
    rows.extend(_unique_symbols(state.get("operator_watchlist")))
    rows.extend(_unique_symbols(policy.get("watchlist_symbols")))
    rows.extend(_unique_symbols(policy.get("watchlist")))
    rows.extend(_unique_symbols(policy.get("operator_watchlist")))
    return _unique_symbols(rows)


def resolve_fallback_symbols(
    *,
    state: Dict[str, Any] | None = None,
    policy: Dict[str, Any] | None = None,
    limit: int = 5,
) -> Tuple[List[str], str]:
    """Resolve fallback symbols with deterministic precedence.

    Precedence:
      1) state['fallback_candidate_symbols']
      2) policy['fallback_candidate_symbols']
      3) state/policy watchlist-like symbols
      4) env FALLBACK_CANDIDATE_SYMBOLS (comma-separated)
      5) env OPERATOR_WATCHLIST (comma-separated)
      6) no fallback (empty)
    """

    k = max(1, int(limit))
    st = state if isinstance(state, dict) else {}
    pol = policy if isinstance(policy, dict) else {}

    st_syms = _unique_symbols(st.get("fallback_candidate_symbols"))
    if st_syms:
        return st_syms[:k], "state.fallback_candidate_symbols"

    pol_syms = _unique_symbols(pol.get("fallback_candidate_symbols"))
    if pol_syms:
        return pol_syms[:k], "policy.fallback_candidate_symbols"

    watch_syms = _watchlist_like_symbols(state=st, policy=pol)
    if watch_syms:
        return watch_syms[:k], "state_or_policy_watchlist"

    env_syms = _from_csv(os.getenv("FALLBACK_CANDIDATE_SYMBOLS", ""))
    if env_syms:
        return env_syms[:k], "env.FALLBACK_CANDIDATE_SYMBOLS"

    env_watch = _from_csv(os.getenv("OPERATOR_WATCHLIST", ""))
    if env_watch:
        return env_watch[:k], "env.OPERATOR_WATCHLIST"

    return [], "none"


def is_static_fallback_pool(candidates: List[Any]) -> bool:
    """Return True when candidate pool appears to be static fallback-only.

    We intentionally require dict-shaped rows and explicit fallback markers to
    avoid accidentally classifying strategist-provided dynamic candidates.
    """

    if not isinstance(candidates, list) or not candidates:
        return False

    saw_dict = False
    for row in candidates:
        if not isinstance(row, dict):
            return False
        saw_dict = True
        why = str(row.get("why") or "").strip().lower()
        sources = [str(x).strip().lower() for x in list(row.get("sources") or [])]
        fallback_source = str(row.get("fallback_source") or "").strip().lower()
        if (
            "fallback" not in why
            and "fallback" not in sources
            and "fallback" not in fallback_source
        ):
            return False

    return bool(saw_dict)
