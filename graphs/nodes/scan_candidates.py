from __future__ import annotations

import os
from typing import Any, Dict, List

from libs.strategies.candidates.market_rank import (
    MarketRankCandidateGenerator,
    TopPicksCandidateGenerator,
)
from libs.strategies.universe_builder import build_candidate_universe


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _normalize_symbols(items: Any) -> List[str]:
    if not isinstance(items, list):
        return []
    out: List[str] = []
    seen = set()
    for row in items:
        s = str(row or "").strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _default_universe() -> List[str]:
    raw = os.getenv("UNIVERSE_SYMBOLS", "").strip()
    if raw:
        return _normalize_symbols([s.strip() for s in raw.split(",") if s.strip()])
    return ["005930", "000660"]


def _extract_injected_rows(state: Dict[str, Any], k: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    universe = _normalize_symbols(state.get("universe"))
    if universe:
        rows.extend({"symbol": s, "why": "state_universe"} for s in universe[:k])
        return rows

    candidates = state.get("candidates")
    if isinstance(candidates, list) and candidates:
        normalized = _normalize_symbols(candidates)
        if normalized:
            rows.extend({"symbol": s, "why": "state_candidates"} for s in normalized[:k])
            return rows

    env_raw = str(os.getenv("UNIVERSE_SYMBOLS", "") or "").strip()
    if env_raw:
        env_universe = _normalize_symbols([s.strip() for s in env_raw.split(",") if s.strip()])
        if env_universe:
            rows.extend({"symbol": s, "why": "env_universe"} for s in env_universe[:k])
            return rows

    return rows


def _build_rows_with_universe_builder(state: Dict[str, Any], policy: Dict[str, Any], k: int) -> List[Dict[str, Any]]:
    try:
        built = build_candidate_universe(state=state, policy=policy, topk=k)
    except Exception:
        built = []
    rows: List[Dict[str, Any]] = []
    for row in built:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        rows.append(
            {
                "symbol": sym,
                "why": str(row.get("why") or "universe_builder"),
                "sources": list(row.get("sources") or []),
                "universe_score": float(row.get("score") or 0.0),
            }
        )
    return rows[:k]


def _build_rows_with_legacy_generators(state: Dict[str, Any], policy: Dict[str, Any], k: int) -> List[Dict[str, Any]]:
    source = str(policy.get("candidate_source") or "top_picks").strip().lower()
    if source == "market_rank":
        gen = MarketRankCandidateGenerator()
        try:
            symbols = gen.generate(state=state, policy=policy, k=k)
        except TypeError:
            try:
                symbols = gen.generate(state=state, k=k)
            except TypeError:
                symbols = gen.generate(state=state)
        return [{"symbol": s, "why": "market_rank"} for s in _normalize_symbols(symbols)[:k]]

    gen = TopPicksCandidateGenerator(
        rank_mode=str(policy.get("candidate_rank_mode") or "value"),
        rank_topn=_to_int(policy.get("candidate_rank_topn"), 30),
        topk=max(1, int(k)),
    )
    symbols = _normalize_symbols(gen.generate(state=state))
    return [{"symbol": s, "why": "top_picks"} for s in symbols[:k]]


def scan_candidates(state: dict) -> dict:
    """Produce ranked candidate symbols for M11+ scan stage.

    Output compatibility:
      - state['candidates']: list[str] (legacy contract kept)
      - state['candidate_rows']: list[dict] (additive metadata)
    """
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    k = max(1, _to_int(policy.get("candidate_k", policy.get("candidate_topk", 5)), 5))

    rows = _extract_injected_rows(state, k)
    if not rows:
        use_builder = _is_trueish(policy.get("use_universe_builder", os.getenv("USE_UNIVERSE_BUILDER", "true")))
        if use_builder:
            rows = _build_rows_with_universe_builder(state=state, policy=policy, k=k)
        if not rows:
            rows = _build_rows_with_legacy_generators(state=state, policy=policy, k=k)
    if not rows:
        rows = [{"symbol": s, "why": "env_or_fallback"} for s in _default_universe()[:k]]
    elif len(rows) < k:
        existing = {str(r.get("symbol") or "").strip().upper() for r in rows}
        for sym in _default_universe():
            s = str(sym or "").strip().upper()
            if not s or s in existing:
                continue
            rows.append({"symbol": s, "why": "fill_default"})
            existing.add(s)
            if len(rows) >= k:
                break

    state["candidate_rows"] = rows
    state["candidates"] = [str(r.get("symbol") or "").strip().upper() for r in rows if str(r.get("symbol") or "").strip()]
    return state
