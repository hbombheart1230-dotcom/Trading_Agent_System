"""
Candidate generators based on market ranking ("market_rank") and "top picks" logic.

This module is intentionally **network-safe**:
- In DRY_RUN (env DRY_RUN=1) it will never call external APIs and will use fallbacks.
- In tests, callers typically inject `state["mock_rank_symbols"]` and optionally
  `state["mock_condition_symbols"]`.

Notes
-----
Some parts of the project import `TopPicksCandidateGenerator` from this module.
Earlier milestones introduced the class but later refactors could accidentally remove it.
This file keeps both generators to preserve backward compatibility.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def _is_dry_run() -> bool:
    return str(os.getenv("DRY_RUN", "")).strip() in {"1", "true", "True", "YES", "yes"}


def _fallback_universe() -> List[str]:
    # Reasonable KR equities examples (kept small for tests).
    # Using strings so both "AAA/BBB" tests and real tickers can coexist.
    return ["005930", "000660", "035420", "051910", "068270"]


def _get_policy(state: Dict[str, Any]) -> Dict[str, Any]:
    p = state.get("policy") or {}
    return p if isinstance(p, dict) else {}


def _take_unique(seq: List[str], k: int) -> List[str]:
    out: List[str] = []
    seen = set()
    for s in seq:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= k:
            break
    return out


@dataclass
class MarketRankCandidateGenerator:
    """
    Generate candidate symbols from market ranking.

    Priority:
    1) state["mock_rank_symbols"] if present
    2) DRY_RUN fallback universe
    3) best-effort KiwoomRankReader (if available)
    """
    def generate(self, state: Dict[str, Any]) -> List[str]:
        policy = _get_policy(state)
        topn = int(policy.get("candidate_rank_topn", 20))
        symbols = state.get("mock_rank_symbols")
        if isinstance(symbols, list) and symbols:
            return _take_unique([str(x) for x in symbols], topn)

        if _is_dry_run():
            return _take_unique(_fallback_universe(), min(topn, 20))

        # Best-effort live fetch (kept tolerant; if anything fails, fallback)
        try:
            # This module exists from M18-1 in this project
            from libs.read.kiwoom_rank_reader import KiwoomRankReader  # type: ignore
            reader = KiwoomRankReader.from_env()  # type: ignore[attr-defined]
            mode = str(policy.get("candidate_rank_mode", "value"))
            # reader.get_top_symbols should be implemented in the reader;
            # if not, this will raise and we fallback.
            live_syms = reader.get_top_symbols(mode=mode, topn=topn)  # type: ignore
            if isinstance(live_syms, list) and live_syms:
                return _take_unique([str(x) for x in live_syms], topn)
        except Exception:
            pass

        return _take_unique(_fallback_universe(), min(topn, 20))


@dataclass
class TopPicksCandidateGenerator:
    rank_mode: str = "value"
    rank_topn: int = 20
    topk: int = 5

    """
    Generate "Top Picks" candidates by intersecting:
    - market rank list (e.g., value/volume/return ranking)
    - condition search result list (optional)
    preserving rank order.

    Priority:
    1) state["mock_rank_symbols"] + state["mock_condition_symbols"] (tests)
    2) DRY_RUN fallback universe
    3) best-effort MarketRankCandidateGenerator + (optional) live condition results (not mandatory)
    """
    def generate(self, state: Dict[str, Any]) -> List[str]:
        policy = _get_policy(state)
        topk = int(policy.get("candidate_topk", policy.get("candidate_k", self.topk)))
        topn = int(policy.get("candidate_rank_topn", self.rank_topn))

        rank_syms = state.get("mock_rank_symbols")
        cond_syms = state.get("mock_condition_symbols")

        if isinstance(rank_syms, list) and rank_syms:
            rank_list = _take_unique([str(x) for x in rank_syms], topn)
            if isinstance(cond_syms, list) and len(cond_syms) > 0:
                cond_set = {str(x) for x in cond_syms}
                picked = [s for s in rank_list if s in cond_set]
            else:
                picked = rank_list
            return _take_unique(picked, topk)

        if _is_dry_run():
            return _take_unique(_fallback_universe(), topk)

        # Live best-effort: rank list from MarketRank generator
        rank_list = MarketRankCandidateGenerator().generate(state)
        rank_list = _take_unique(rank_list, topn)

        # Condition symbols: optional. If caller injected none, we won't fetch.
        if isinstance(cond_syms, list) and len(cond_syms) > 0:
            cond_set = {str(x) for x in cond_syms}
            picked = [s for s in rank_list if s in cond_set]
        else:
            picked = rank_list

        return _take_unique(picked, topk)


__all__ = ["MarketRankCandidateGenerator", "TopPicksCandidateGenerator"]
