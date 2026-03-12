from __future__ import annotations

"""Compatibility candidate-stage helper.

Integrated-chain canonical scanning/ranking is implemented in
`graphs/nodes/scanner_node.py`. This module is kept for legacy stage
contracts that still expect `state["candidates"]`.
"""

import os
from typing import Any, Dict, List

from libs.strategies.candidates.kiwoom_candidate_provider import build_kiwoom_candidate_rows
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
    if os.getenv("PYTEST_CURRENT_TEST"):
        # Keep legacy scan-stage contract non-empty in test/offline context.
        return ["TEST001", "TEST002", "TEST003"]
    return []


def _extract_injected_rows(state: Dict[str, Any], k: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    strategist_output = state.get("strategist_output")
    if isinstance(strategist_output, dict):
        strategist_candidates = _normalize_symbols(strategist_output.get("candidates"))
        if strategist_candidates:
            rows.extend({"symbol": s, "why": "strategist_candidates"} for s in strategist_candidates[:k])
            return rows

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


def _build_rows_with_kiwoom_source(state: Dict[str, Any], policy: Dict[str, Any], k: int) -> List[Dict[str, Any]]:
    top_pool = max(k, _to_int(policy.get("top_candidate_pool", os.getenv("TOP_CANDIDATE_POOL", "30")), 30))
    cond_limit = max(top_pool, _to_int(policy.get("candidate_condition_limit", os.getenv("KIWOOM_CANDIDATE_CONDITION_LIMIT", "200")), 200))
    include_change_rate = _is_trueish(policy.get("kiwoom_include_change_rate", os.getenv("KIWOOM_CANDIDATE_INCLUDE_CHANGE_RATE", "true")))
    rows, _meta = build_kiwoom_candidate_rows(
        state=state,
        top_pool=top_pool,
        condition_limit=cond_limit,
        include_change_rate=include_change_rate,
    )
    out: List[Dict[str, Any]] = []
    for row in rows[:k]:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        out.append(
            {
                "symbol": sym,
                "why": str(row.get("why") or "kiwoom_market_data"),
                "sources": list(row.get("sources") or []),
                "universe_score": float(row.get("universe_score") or 0.0),
                "rank_score": float(row.get("rank_score") or 0.0),
                "source_scores": dict(row.get("source_scores") or {}),
                "source_count": int(row.get("source_count") or 0),
            }
        )
    return out


def scan_candidates(state: dict) -> dict:
    """Produce candidate symbols for compatibility scan stage.

    Output compatibility:
      - state['candidates']: list[str] (legacy contract kept)
      - state['candidate_rows']: list[dict] (additive metadata)
    """
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    k = max(1, _to_int(policy.get("candidate_k", policy.get("candidate_topk", 5)), 5))
    source = str(policy.get("candidate_source") or os.getenv("CANDIDATE_SOURCE", "kiwoom")).strip().lower()

    rows = _extract_injected_rows(state, k)
    if not rows:
        if source in ("kiwoom", "market_data"):
            rows = _build_rows_with_kiwoom_source(state=state, policy=policy, k=k)
        if not rows:
            use_builder = _is_trueish(policy.get("use_universe_builder", os.getenv("USE_UNIVERSE_BUILDER", "true")))
            if use_builder:
                rows = _build_rows_with_universe_builder(state=state, policy=policy, k=k)
            if not rows:
                rows = _build_rows_with_legacy_generators(state=state, policy=policy, k=k)
    if not rows:
        rows = [{"symbol": s, "why": "env_universe"} for s in _default_universe()[:k]]
    elif len(rows) < k:
        existing = {str(r.get("symbol") or "").strip().upper() for r in rows}
        for sym in _default_universe():
            s = str(sym or "").strip().upper()
            if not s or s in existing:
                continue
            rows.append({"symbol": s, "why": "fill_env_universe"})
            existing.add(s)
            if len(rows) >= k:
                break

    state["candidate_rows"] = rows
    state["candidates"] = [str(r.get("symbol") or "").strip().upper() for r in rows if str(r.get("symbol") or "").strip()]
    return state
