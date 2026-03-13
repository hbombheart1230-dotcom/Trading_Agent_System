from __future__ import annotations

import os
from typing import Any, Dict, List, Set, Tuple

from libs.read.kiwoom_condition_reader import KiwoomConditionReader


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


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


def _parse_env_symbols(key: str) -> List[str]:
    raw = str(os.getenv(key, "") or "").strip()
    if not raw:
        return []
    return _unique_symbols([x.strip() for x in raw.split(",") if str(x).strip()])


def _extract_themes_from_state(state: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()

    def add_many(values: Any) -> None:
        if not isinstance(values, list):
            return
        for row in values:
            key = str(row or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(key)

    add_many(state.get("themes"))
    add_many(state.get("top_themes"))
    strategist_output = state.get("strategist_output")
    if isinstance(strategist_output, dict):
        add_many(strategist_output.get("themes"))
    return out


def _extract_theme_symbol_index(state: Dict[str, Any]) -> Dict[str, set[str]]:
    out: Dict[str, set[str]] = {}
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}

    def add_map(raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        for name, symbols in raw.items():
            key = str(name or "").strip().lower()
            if not key:
                continue
            bucket = out.setdefault(key, set())
            if isinstance(symbols, list):
                for sym in symbols:
                    s = _norm_symbol(sym)
                    if s:
                        bucket.add(s)

    add_map(state.get("theme_map"))
    add_map(policy.get("theme_map"))
    add_map(state.get("sector_map"))
    add_map(policy.get("sector_map"))
    return out


def _live_fetch_enabled() -> bool:
    # Keep network-safe default for tests/offline.
    # Operators can enable real Kiwoom candidate fetch explicitly.
    if os.getenv("PYTEST_CURRENT_TEST") and not _is_trueish(os.getenv("PYTEST_ALLOW_LIVE_KIWOOM_FETCH", "false")):
        return False
    return _is_trueish(os.getenv("KIWOOM_CANDIDATE_LIVE_FETCH", "false"))


def _fetch_rank_symbols(mode: str, topk: int) -> List[str]:
    if not _live_fetch_enabled():
        return []
    try:
        from libs.read.kiwoom_rank_reader import KiwoomRankReader
        from libs.read.kiwoom_rank_reader import RankMode
    except Exception:
        return []

    try:
        reader = KiwoomRankReader.from_env()
        mode_map = {
            "volume": RankMode.VOLUME,
            "value": RankMode.VALUE,
            "change_rate": RankMode.CHANGE_RATE,
            "change": RankMode.CHANGE_RATE,
        }
        rank_mode = mode_map.get(str(mode or "").strip().lower(), RankMode.VALUE)
        rows = reader.get_top_symbols(mode=rank_mode, topk=max(1, int(topk)))
        return _unique_symbols(rows)[: max(1, int(topk))]
    except Exception:
        return []


def get_top_volume_stocks(state: Dict[str, Any], topk: int = 30) -> List[str]:
    injected = _unique_symbols(state.get("mock_top_volume_symbols"))
    if injected:
        return injected[: max(1, int(topk))]
    env_rows = _parse_env_symbols("MOCK_TOP_VOLUME_SYMBOLS")
    if env_rows:
        return env_rows[: max(1, int(topk))]
    return _fetch_rank_symbols("volume", topk=max(1, int(topk)))


def get_top_value_stocks(state: Dict[str, Any], topk: int = 30) -> List[str]:
    injected = _unique_symbols(state.get("mock_top_value_symbols"))
    if injected:
        return injected[: max(1, int(topk))]
    env_rows = _parse_env_symbols("MOCK_TOP_VALUE_SYMBOLS")
    if env_rows:
        return env_rows[: max(1, int(topk))]
    return _fetch_rank_symbols("value", topk=max(1, int(topk)))


def get_top_change_rate_stocks(state: Dict[str, Any], topk: int = 30) -> List[str]:
    injected = _unique_symbols(state.get("mock_top_change_symbols"))
    if injected:
        return injected[: max(1, int(topk))]
    env_rows = _parse_env_symbols("MOCK_TOP_CHANGE_SYMBOLS")
    if env_rows:
        return env_rows[: max(1, int(topk))]
    return _fetch_rank_symbols("change_rate", topk=max(1, int(topk)))


def get_condition_search_results(state: Dict[str, Any], limit: int = 200) -> List[str]:
    injected = _unique_symbols(state.get("mock_condition_symbols"))
    if injected:
        return injected[: max(1, int(limit))]
    reader = KiwoomConditionReader()
    try:
        rows = reader.get_symbols(state=state, limit=max(1, int(limit)))
    except Exception:
        rows = []
    return _unique_symbols(rows)[: max(1, int(limit))]


def get_condition_search_results_with_meta(state: Dict[str, Any], limit: int = 200) -> Tuple[List[str], Dict[str, Any]]:
    injected = _unique_symbols(state.get("mock_condition_symbols"))
    if injected:
        return injected[: max(1, int(limit))], {
            "source": "state_mock",
            "status": "ok",
            "reason": "state.mock_condition_symbols",
        }
    reader = KiwoomConditionReader()
    try:
        rows, meta = reader.get_symbols_with_meta(state=state, limit=max(1, int(limit)))
    except Exception as e:
        rows, meta = [], {"source": "error", "status": "unavailable", "reason": f"{type(e).__name__}:{e}"}
    return _unique_symbols(rows)[: max(1, int(limit))], dict(meta or {})


def get_top_trading_value_stocks(state: Dict[str, Any], topk: int = 30) -> List[str]:
    """Practical alias: trading value ranking source."""
    return get_top_value_stocks(state, topk=topk)


def get_top_gainers(state: Dict[str, Any], topk: int = 30) -> List[str]:
    """Practical alias: top gainers source."""
    return get_top_change_rate_stocks(state, topk=topk)


def get_condition_candidates(state: Dict[str, Any], limit: int = 200) -> List[str]:
    """Practical alias: condition-search source."""
    return get_condition_search_results(state, limit=limit)


def get_sector_candidates(
    state: Dict[str, Any],
    *,
    themes: List[str] | None = None,
    limit: int = 200,
) -> List[str]:
    idx = _extract_theme_symbol_index(state)
    if not idx:
        return []

    selected_themes = [str(x).strip().lower() for x in (themes or _extract_themes_from_state(state)) if str(x).strip()]
    if not selected_themes:
        return []

    out: List[str] = []
    seen: Set[str] = set()
    for th in selected_themes:
        for sym in list(idx.get(th) or set()):
            s = _norm_symbol(sym)
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
            if len(out) >= max(1, int(limit)):
                return out
    return out


def get_watchlist_candidates(state: Dict[str, Any], limit: int = 200) -> List[str]:
    # Operator-managed shortlist path.
    candidates: List[str] = []
    if isinstance(state.get("watchlist_symbols"), list):
        candidates.extend(_unique_symbols(state.get("watchlist_symbols")))
    if isinstance(state.get("watchlist"), list):
        candidates.extend(_unique_symbols(state.get("watchlist")))
    if isinstance(state.get("operator_watchlist"), list):
        candidates.extend(_unique_symbols(state.get("operator_watchlist")))

    env_raw = _parse_env_symbols("OPERATOR_WATCHLIST")
    if env_raw:
        candidates.extend(env_raw)

    return _unique_symbols(candidates)[: max(1, int(limit))]


def _add_ranked_source(
    rows: Dict[str, Dict[str, Any]],
    *,
    symbols: List[str],
    source: str,
    weight: float,
    decay: float = 0.02,
) -> None:
    w = float(max(0.01, weight))
    d = float(max(0.0, decay))
    for idx, sym in enumerate(symbols):
        score_add = max(0.05, w - d * float(idx))
        row = rows.setdefault(sym, {"symbol": sym, "score": 0.0, "sources": [], "source_scores": {}})
        row["score"] = float(row.get("score") or 0.0) + score_add
        srcs = row.get("sources") if isinstance(row.get("sources"), list) else []
        if source not in srcs:
            srcs.append(source)
        row["sources"] = srcs
        src_score = row.get("source_scores") if isinstance(row.get("source_scores"), dict) else {}
        src_score[source] = float(src_score.get(source) or 0.0) + score_add
        row["source_scores"] = src_score


def build_kiwoom_candidate_rows(
    *,
    state: Dict[str, Any],
    top_pool: int,
    condition_limit: int,
    include_change_rate: bool = True,
    include_top_value: bool = True,
    include_top_volume: bool = True,
    include_condition_search: bool = True,
    themes: List[str] | None = None,
    include_sector_candidates: bool = True,
    include_watchlist: bool = True,
    source_weights: Dict[str, float] | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Build scanner candidate pool from Kiwoom market data sources."""
    pool_k = max(1, int(top_pool))
    cond_k = max(1, int(condition_limit))

    top_volume = get_top_volume_stocks(state, topk=pool_k) if bool(include_top_volume) else []
    top_value = get_top_trading_value_stocks(state, topk=pool_k) if bool(include_top_value) else []
    top_change = get_top_gainers(state, topk=pool_k) if bool(include_change_rate) else []
    condition_meta: Dict[str, Any] = {"source": "disabled", "status": "disabled", "reason": "condition_search_disabled"}
    if bool(include_condition_search) and cond_k > 0:
        cond_rows, condition_meta = get_condition_search_results_with_meta(state, limit=cond_k)
    else:
        cond_rows = []
    sector_rows = (
        get_sector_candidates(state, themes=themes, limit=pool_k)
        if bool(include_sector_candidates)
        else []
    )
    watch_rows = get_watchlist_candidates(state, limit=pool_k) if bool(include_watchlist) else []

    source_weight_map = dict(source_weights or {})
    rows: Dict[str, Dict[str, Any]] = {}
    if bool(include_top_value) and float(source_weight_map.get("top_value", 2.0)) > 0.0:
        _add_ranked_source(rows, symbols=top_value, source="top_value", weight=float(source_weight_map.get("top_value", 2.0)), decay=0.02)
    if bool(include_top_volume) and float(source_weight_map.get("top_volume", 1.7)) > 0.0:
        _add_ranked_source(rows, symbols=top_volume, source="top_volume", weight=float(source_weight_map.get("top_volume", 1.7)), decay=0.02)
    if bool(include_condition_search) and cond_k > 0 and float(source_weight_map.get("condition_search", 2.3)) > 0.0:
        _add_ranked_source(rows, symbols=cond_rows, source="condition_search", weight=float(source_weight_map.get("condition_search", 2.3)), decay=0.01)
    if bool(include_sector_candidates) and float(source_weight_map.get("sector_theme", 1.6)) > 0.0:
        _add_ranked_source(rows, symbols=sector_rows, source="sector_theme", weight=float(source_weight_map.get("sector_theme", 1.6)), decay=0.02)
    if bool(include_watchlist) and float(source_weight_map.get("operator_watchlist", 0.8)) > 0.0:
        _add_ranked_source(rows, symbols=watch_rows, source="operator_watchlist", weight=float(source_weight_map.get("operator_watchlist", 0.8)), decay=0.01)
    if bool(include_change_rate) and float(source_weight_map.get("top_change_rate", 1.3)) > 0.0:
        _add_ranked_source(rows, symbols=top_change, source="top_change_rate", weight=float(source_weight_map.get("top_change_rate", 1.3)), decay=0.02)

    out = list(rows.values())
    out.sort(
        key=lambda r: (
            -float(r.get("score") or 0.0),
            str(r.get("symbol") or ""),
        )
    )

    if out:
        max_score = float(max(float(r.get("score") or 0.0) for r in out))
    else:
        max_score = 0.0

    normalized: List[Dict[str, Any]] = []
    for row in out[:pool_k]:
        srcs = list(row.get("sources") or [])
        universe_score = float(row.get("score") or 0.0)
        rank_score = 0.0 if max_score <= 0.0 else min(1.0, universe_score / max_score)
        normalized.append(
            {
                "symbol": str(row.get("symbol") or ""),
                "why": "+".join(srcs[:3]) if srcs else "kiwoom_market_data",
                "sources": srcs,
                "source_scores": dict(row.get("source_scores") or {}),
                "source_count": len(srcs),
                "rank_score": float(rank_score),
                "universe_score": float(universe_score),
                "trading_value_source_score": _to_float((row.get("source_scores") or {}).get("top_value"), 0.0),
                "trading_volume_source_score": _to_float((row.get("source_scores") or {}).get("top_volume"), 0.0),
            }
        )

    meta = {
        "candidate_source": "kiwoom_market_data",
        "top_volume_count": len(top_volume),
        "top_value_count": len(top_value),
        "top_change_rate_count": len(top_change),
        "condition_count": len(cond_rows),
        "sector_theme_count": len(sector_rows),
        "watchlist_count": len(watch_rows),
        "pool_count": len(normalized),
        "live_fetch_enabled": bool(_live_fetch_enabled()),
        "pool_source_mix": {
            "top_value": len(top_value),
            "top_volume": len(top_volume),
            "top_change_rate": len(top_change),
            "condition_search": len(cond_rows),
            "sector_theme": len(sector_rows),
            "operator_watchlist": len(watch_rows),
        },
        "source_weights": {
            "top_value": float(source_weight_map.get("top_value", 2.0)),
            "top_volume": float(source_weight_map.get("top_volume", 1.7)),
            "condition_search": float(source_weight_map.get("condition_search", 2.3)),
            "sector_theme": float(source_weight_map.get("sector_theme", 1.6)),
            "operator_watchlist": float(source_weight_map.get("operator_watchlist", 0.8)),
            "top_change_rate": float(source_weight_map.get("top_change_rate", 1.3)),
        },
        "condition_search_status": str(condition_meta.get("status") or ""),
        "condition_search_source": str(condition_meta.get("source") or ""),
        "condition_search_reason": str(condition_meta.get("reason") or ""),
    }
    return normalized, meta
