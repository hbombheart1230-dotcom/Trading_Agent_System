from __future__ import annotations

from typing import Any, Dict, List

from libs.strategies.candidates.market_rank import MarketRankCandidateGenerator
from libs.strategies.candidates.top_picks import TopPicksCandidateGenerator
from libs.read.kiwoom_condition_reader import ConditionQuery
from libs.read.kiwoom_rank_reader import RankMode


def _normalize_universe(universe: Any) -> List[str]:
    if not isinstance(universe, list):
        return []
    out: List[str] = []
    for x in universe:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out


def strategist_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Strategist node (M18+).

    Responsibilities:
      - Build trade plan policy (risk thresholds, retry counts, etc.)
      - Produce 3~5 candidate symbols (auto-scan by default)

    Produces:
      - state['candidates']: list[dict] each having {symbol, why}
      - state['policy']: risk/decision policy

    Notes:
      - For tests/experiments, you can inject:
        * state['candidates'] (highest priority)
        * state['universe'] (next priority, will take top-k)
      - Otherwise it will auto-generate candidates from market rank scan.
    """
    # Ensure policy defaults
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    policy.setdefault("max_risk", 0.7)
    policy.setdefault("min_confidence", 0.6)
    policy.setdefault("max_scan_retries", 1)

    # Candidate generation policy
    policy.setdefault("candidate_topk", 5)
    # candidate_source: market_rank | top_picks
    policy.setdefault("candidate_source", "top_picks")
    policy.setdefault("candidate_rank_mode", "value")  # volume|value|change_rate
    policy.setdefault("candidate_rank_topn", 30)
    # optional condition filter
    policy.setdefault("condition_id", None)
    policy.setdefault("condition_name", None)
    state["policy"] = policy

    # 1) Allow injection for tests / experiments
    if isinstance(state.get("candidates"), list) and state["candidates"]:
        return state

    # 2) Universe injection (used by unit tests like test_m17_candidates_to_selected)
    universe = _normalize_universe(state.get("universe"))
    if universe:
        topk = int(policy.get("candidate_topk") or 5)
        state["candidates"] = [{"symbol": s, "why": "universe_injected"} for s in universe[:topk]]
        return state

    # 3) Default: auto-generate from market rank scan (no manual allowlist)
    mode_str = str(policy.get("candidate_rank_mode") or "volume").lower()
    mode = RankMode.VOLUME
    if mode_str in ("value", "trade_value", "amount"):
        mode = RankMode.VALUE
    elif mode_str in ("change_rate", "rate", "pct"):
        mode = RankMode.CHANGE_RATE

    source = str(policy.get("candidate_source") or "top_picks").lower()
    topk = int(policy.get("candidate_topk") or 5)

    if source == "market_rank":
        gen = MarketRankCandidateGenerator(mode=mode, topk=topk)
    else:
        cq: ConditionQuery | None = None
        try:
            cid = policy.get("condition_id")
            cname = policy.get("condition_name")
            if cid is not None or cname:
                cid_int = int(cid) if cid not in (None, "", False) else None
                cname_str = str(cname).strip() if cname else None
                cq = ConditionQuery(condition_id=cid_int, condition_name=cname_str)
        except Exception:
            cq = None

        gen = TopPicksCandidateGenerator(
            topk=topk,
            rank_topn=int(policy.get("candidate_rank_topn") or 30),
            rank_mode=mode,
            condition=cq,
        )
    candidates = gen.generate(state)

    # Normalize to list[dict] contract
    state["candidates"] = [{"symbol": c.symbol, "why": c.why} for c in candidates][:5]
    return state
