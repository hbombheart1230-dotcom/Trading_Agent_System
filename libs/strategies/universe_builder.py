from __future__ import annotations

import os
from typing import Any, Dict, List, Set

from libs.read.kiwoom_condition_reader import KiwoomConditionReader
from libs.strategies.candidates.market_rank import MarketRankCandidateGenerator


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


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


def _unique_strings(items: Any) -> List[str]:
    if not isinstance(items, list):
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for row in items:
        s = str(row or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _to_float(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _source_weight_map(policy: Dict[str, Any]) -> Dict[str, float]:
    raw = policy.get("candidate_source_weights")
    src = dict(raw) if isinstance(raw, dict) else {}
    return {
        "held_position": _to_float(src.get("held_position"), 4.0),
        "watchlist": _to_float(src.get("watchlist"), 3.0),
        "sector": _to_float(src.get("sector"), 2.0),
        "theme": _to_float(src.get("theme"), 2.0),
        "condition": _to_float(src.get("condition"), 2.2),
        "liquidity": _to_float(src.get("liquidity"), 1.2),
        "market_rank": _to_float(src.get("market_rank"), 1.5),
    }


def _extract_held_symbols(state: Dict[str, Any]) -> List[str]:
    portfolio = state.get("portfolio_snapshot") if isinstance(state.get("portfolio_snapshot"), dict) else {}
    positions = portfolio.get("positions")
    if not isinstance(positions, list):
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for row in positions:
        if not isinstance(row, dict):
            continue
        s = _norm_symbol(row.get("symbol") or row.get("code"))
        qty = _to_int(row.get("qty"), 0)
        if not s or qty <= 0 or s in seen:
            continue
        seen.add(s)
        out.append(s)
    # Optional aliases for integration flexibility.
    out.extend(_unique_symbols(state.get("held_symbols")))
    out.extend(_unique_symbols(state.get("held_positions")))
    return _unique_symbols(out)


def _extract_watchlist_symbols(state: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    out.extend(_unique_symbols(state.get("watchlist_symbols")))
    out.extend(_unique_symbols(state.get("watchlist")))
    out.extend(_unique_symbols(state.get("manual_watchlist")))
    out.extend(_unique_symbols(policy.get("watchlist_symbols")))
    out.extend(_unique_symbols(policy.get("watchlist")))
    out.extend(_unique_symbols(policy.get("manual_watchlist")))
    return _unique_symbols(out)


def _extract_theme_symbols(state: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    out.extend(_unique_symbols(state.get("theme_symbols")))
    out.extend(_unique_symbols(policy.get("theme_symbols")))
    ptheme = policy.get("theme_map")
    if isinstance(ptheme, dict):
        for rows in ptheme.values():
            out.extend(_unique_symbols(rows))
    return _unique_symbols(out)


def _extract_sector_symbols(state: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    out.extend(_unique_symbols(state.get("sector_symbols")))
    out.extend(_unique_symbols(policy.get("sector_symbols")))
    out.extend(_unique_symbols(state.get("sector_or_theme_symbols")))
    out.extend(_unique_symbols(policy.get("sector_or_theme_symbols")))

    selected_sectors = _unique_strings(state.get("sector_filter"))
    if not selected_sectors:
        selected_sectors = _unique_strings(policy.get("sector_filter"))

    # Use raw sector names as keys; do not normalize by upper-case symbols.
    selected_sector_names = {str(x).strip() for x in selected_sectors if str(x).strip()}
    sector_map = {}
    if isinstance(state.get("sector_map"), dict):
        sector_map.update(dict(state.get("sector_map") or {}))
    if isinstance(policy.get("sector_map"), dict):
        sector_map.update(dict(policy.get("sector_map") or {}))

    if isinstance(sector_map, dict):
        for sec_name, symbols in sector_map.items():
            sec = str(sec_name or "").strip()
            if selected_sector_names and sec not in selected_sector_names:
                continue
            out.extend(_unique_symbols(symbols))

    return _unique_symbols(out)


def _extract_rank_symbols(state: Dict[str, Any], policy: Dict[str, Any], topn: int) -> List[str]:
    injected = _unique_symbols(state.get("mock_rank_symbols"))
    if injected:
        return injected[:topn]
    gen = MarketRankCandidateGenerator()
    try:
        syms = gen.generate(state=state)
    except Exception:
        syms = []
    return _unique_symbols(syms)[:topn]


def _extract_liquidity_symbols(state: Dict[str, Any], topn: int) -> List[str]:
    injected = _unique_symbols(state.get("mock_liquidity_symbols"))
    if injected:
        return injected[:topn]
    injected2 = _unique_symbols(state.get("liquidity_symbols"))
    if injected2:
        return injected2[:topn]
    return []


def _extract_condition_symbols(state: Dict[str, Any], limit: int) -> List[str]:
    injected = _unique_symbols(state.get("mock_condition_symbols"))
    if injected:
        return injected[:limit]
    reader = KiwoomConditionReader()
    try:
        return _unique_symbols(reader.get_symbols(state=state, limit=limit))
    except Exception:
        return []


def build_candidate_universe(
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    topk: int,
) -> List[Dict[str, Any]]:
    """Build ranked candidate universe from multiple source groups.

    Output rows:
      {
        "symbol": str,
        "score": float,
        "sources": [str, ...],
        "why": str,
      }
    """
    k = max(1, int(topk))
    source_mode = str(policy.get("candidate_source") or "top_picks").strip().lower()
    topn = max(k, _to_int(policy.get("candidate_rank_topn"), 30))
    cond_limit = max(k, _to_int(policy.get("candidate_condition_limit"), 200))
    require_condition = _is_trueish(policy.get("universe_require_condition"))
    src_weight = _source_weight_map(policy)

    rows: Dict[str, Dict[str, Any]] = {}

    def add(sym: str, source: str, score_add: float) -> None:
        if not sym:
            return
        row = rows.setdefault(sym, {"symbol": sym, "score": 0.0, "sources": [], "source_scores": {}})
        row["score"] = float(row.get("score") or 0.0) + float(score_add)
        srcs = row.get("sources")
        if isinstance(srcs, list) and source not in srcs:
            srcs.append(source)
        row["sources"] = srcs if isinstance(srcs, list) else [source]
        source_scores = row.get("source_scores")
        if not isinstance(source_scores, dict):
            source_scores = {}
        source_scores[source] = float(source_scores.get(source) or 0.0) + float(score_add)
        row["source_scores"] = source_scores

    held = _extract_held_symbols(state)
    watch = _extract_watchlist_symbols(state, policy)
    sectors = _extract_sector_symbols(state, policy)
    themes = _extract_theme_symbols(state, policy)
    ranked = _extract_rank_symbols(state, policy, topn)
    liquid = _extract_liquidity_symbols(state, topn)
    cond = _extract_condition_symbols(state, cond_limit)
    rank_for_scoring = list(ranked)
    if source_mode == "top_picks" and cond:
        cond_set = set(cond)
        rank_for_scoring = [s for s in ranked if s in cond_set]

    # Strong precedence to already-held symbols and operator watchlist.
    for sym in held:
        add(sym, "held_position", src_weight["held_position"])
    for sym in watch:
        add(sym, "watchlist", src_weight["watchlist"])
    for sym in sectors:
        add(sym, "sector", src_weight["sector"])
    for sym in themes:
        add(sym, "theme", src_weight["theme"])
    for idx, sym in enumerate(cond):
        add(sym, "condition", max(0.25, src_weight["condition"] - (0.01 * idx)))
    for idx, sym in enumerate(liquid):
        add(sym, "liquidity", max(0.10, src_weight["liquidity"] - (0.02 * idx)))
    for idx, sym in enumerate(rank_for_scoring):
        add(sym, "market_rank", max(0.10, src_weight["market_rank"] - (0.02 * idx)))

    if require_condition and cond:
        cond_set = set(cond)
        rows = {k: v for k, v in rows.items() if k in cond_set}

    if not rows:
        # Never return empty in DRY_RUN / no-source scenarios.
        fallback = _unique_symbols(["005930", "000660", "035420", "051910", "068270"])
        for idx, sym in enumerate(fallback):
            add(sym, "fallback", max(0.1, 1.0 - 0.1 * idx))

    out = list(rows.values())
    out.sort(
        key=lambda r: (
            -float(r.get("score") or 0.0),
            str(r.get("symbol") or ""),
        )
    )

    result: List[Dict[str, Any]] = []
    for row in out[:k]:
        srcs = list(row.get("sources") or [])
        result.append(
            {
                "symbol": str(row.get("symbol") or ""),
                "score": float(row.get("score") or 0.0),
                "sources": srcs,
                "source_scores": dict(row.get("source_scores") or {}),
                "source_count": len(srcs),
                "why": "+".join(srcs[:3]) if srcs else "universe",
            }
        )
    return result
