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


def _live_fetch_enabled() -> bool:
    # Keep network-safe default for tests/offline.
    # Operators can enable real Kiwoom candidate fetch explicitly.
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
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Build scanner candidate pool from Kiwoom market data sources."""
    pool_k = max(1, int(top_pool))
    cond_k = max(1, int(condition_limit))

    top_volume = get_top_volume_stocks(state, topk=pool_k)
    top_value = get_top_value_stocks(state, topk=pool_k)
    top_change = get_top_change_rate_stocks(state, topk=pool_k) if bool(include_change_rate) else []
    cond_rows = get_condition_search_results(state, limit=cond_k)

    rows: Dict[str, Dict[str, Any]] = {}
    _add_ranked_source(rows, symbols=top_value, source="top_value", weight=2.0, decay=0.02)
    _add_ranked_source(rows, symbols=top_volume, source="top_volume", weight=1.7, decay=0.02)
    _add_ranked_source(rows, symbols=cond_rows, source="condition_search", weight=2.3, decay=0.01)
    if bool(include_change_rate):
        _add_ranked_source(rows, symbols=top_change, source="top_change_rate", weight=1.3, decay=0.02)

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
            }
        )

    meta = {
        "candidate_source": "kiwoom_market_data",
        "top_volume_count": len(top_volume),
        "top_value_count": len(top_value),
        "top_change_rate_count": len(top_change),
        "condition_count": len(cond_rows),
        "pool_count": len(normalized),
        "live_fetch_enabled": bool(_live_fetch_enabled()),
    }
    return normalized, meta

