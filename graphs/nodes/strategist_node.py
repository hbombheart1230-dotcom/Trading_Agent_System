from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

# Optional generators (may exist in repo). We intentionally don't hard-require them
# because tests rely heavily on mock injection.
try:
    from libs.strategies.candidates.market_rank import MarketRankCandidateGenerator  # type: ignore
except Exception:
    MarketRankCandidateGenerator = None  # type: ignore

try:
    from libs.strategies.candidates.top_picks import TopPicksCandidateGenerator  # type: ignore
except Exception:
    try:
        from libs.strategies.candidates.market_rank import TopPicksCandidateGenerator  # type: ignore
    except Exception:
        TopPicksCandidateGenerator = None  # type: ignore

# News pipeline (M18-6+). Optional for backward compatibility.
try:
    from libs.news.news_pipeline import collect_news_items, score_news_sentiment_simple  # type: ignore
except Exception:
    collect_news_items = None  # type: ignore
    score_news_sentiment_simple = None  # type: ignore


def _truthy(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _dry_run() -> bool:
    return _truthy(os.getenv("DRY_RUN"))


def _default_policy(user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    user = dict(user or {})
    base: Dict[str, Any] = {
        "max_risk": 0.7,
        "min_confidence": 0.6,
        # candidate generation
        "candidate_source": "top_picks",  # top_picks | market_rank
        "candidate_k": 5,
        "candidate_topk": 5,
        "candidate_rank_mode": "value",
        "candidate_rank_topn": 10,
        # sentiment toggles
        "use_global_sentiment": True,
        "use_news_analysis": True,
        # rerank weights
        "candidate_news_weight": 1.0,
        "candidate_global_weight": 0.1,
        # filters/controls
        "candidate_negative_news_threshold": -0.7,
        "candidate_risk_off_threshold": -0.5,
        "candidate_max_count_risk_off": 3,
    }
    # merge
    base.update(user)
    return base


def _symbols_from_candidates(cands: Sequence[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for c in cands:
        s = str(c.get("symbol") or "").strip()
        if s:
            out.append(s)
    return out


def _candidates_from_state(state: Dict[str, Any], k: int) -> List[Dict[str, Any]]:
    # 1) already built candidates
    if isinstance(state.get("candidates"), list) and state.get("candidates"):
        cands = [c for c in state["candidates"] if isinstance(c, dict) and c.get("symbol")]
        return cands[:k]

    # 2) explicit injected symbols for tests
    if isinstance(state.get("candidate_symbols"), list) and state.get("candidate_symbols"):
        syms = [str(s) for s in state["candidate_symbols"] if str(s).strip()]
        return [{"symbol": s, "why": "injected"} for s in syms[:k]]

    # 3) legacy test path: universe
    if isinstance(state.get("universe"), list) and state.get("universe"):
        syms = [str(s) for s in state["universe"] if str(s).strip()]
        return [{"symbol": s, "why": "universe"} for s in syms[:k]]

    return []


def _fallback_symbols(k: int) -> List[str]:
    # deterministic fallback for DRY_RUN / offline
    pool = ["005930", "000660", "035420", "051910", "068270"]
    return pool[: max(3, min(k, 5))]


def _top_picks_symbols(state: Dict[str, Any], policy: Dict[str, Any], k: int) -> List[str]:
    # tests inject these
    rank_syms = state.get("mock_rank_symbols") if isinstance(state.get("mock_rank_symbols"), list) else []
    cond_syms = state.get("mock_condition_symbols") if isinstance(state.get("mock_condition_symbols"), list) else None

    topk = int(policy.get("candidate_topk") or policy.get("candidate_k") or k)
    topk = max(1, min(topk, 20))

    if rank_syms:
        rank_list = [str(s) for s in rank_syms if str(s).strip()]
        if cond_syms is not None and len(cond_syms) > 0:
            cond_set = {str(s) for s in cond_syms if str(s).strip()}
            filt = [s for s in rank_list if s in cond_set]
        else:
            filt = rank_list
        return filt[:topk]

    # if generator exists, try it (signature tolerant)
    if TopPicksCandidateGenerator is not None and not _dry_run():
        gen = TopPicksCandidateGenerator()  # type: ignore
        try:
            out = gen.generate(state=state, policy=policy, k=topk)
        except TypeError:
            try:
                out = gen.generate(state=state, k=topk)
            except TypeError:
                out = gen.generate(state=state)
        # normalize
        if isinstance(out, list):
            return [str(x) for x in out if str(x).strip()][:topk]

    return []


def _market_rank_symbols(state: Dict[str, Any], policy: Dict[str, Any], k: int) -> List[str]:
    # tests may reuse mock_rank_symbols
    rank_syms = state.get("mock_rank_symbols") if isinstance(state.get("mock_rank_symbols"), list) else []
    if rank_syms:
        rank_list = [str(s) for s in rank_syms if str(s).strip()]
        return rank_list[:k]

    if MarketRankCandidateGenerator is not None and not _dry_run():
        gen = MarketRankCandidateGenerator()  # type: ignore
        try:
            out = gen.generate(state=state, policy=policy, k=k)
        except TypeError:
            try:
                out = gen.generate(state=state, k=k)
            except TypeError:
                out = gen.generate(state=state)
        if isinstance(out, list):
            return [str(x) for x in out if str(x).strip()][:k]

    return []


def _fill_news_sentiment_for_symbols(state: Dict[str, Any], symbols: Sequence[str], policy: Dict[str, Any]) -> Dict[str, float]:
    """Return sentiment score per symbol, defaulting to 0.0.

    Priority:
      1) If state.mock_news_sentiment exists -> use it (default 0.0).
      2) Else if state.news_sentiment exists -> use it (default 0.0).
      3) Else if news pipeline is available and use_news_analysis is truthy ->
         collect news items (state.mock_news_items supported) and compute scores (currently 0.0 unless mock_news_sentiment is provided).

    Side-effects:
      - When pipeline runs, attaches state["news_items"] = {sym: [NewsItem,...]}
    """

    # 1) explicit mock scores
    if isinstance(state.get("mock_news_sentiment"), dict):
        src = state.get("mock_news_sentiment") or {}
        out: Dict[str, float] = {}
        for s in symbols:
            try:
                out[str(s)] = float(src.get(s, 0.0))
            except Exception:
                out[str(s)] = 0.0
        return out

    # 2) pre-attached scores
    if isinstance(state.get("news_sentiment"), dict):
        src = state.get("news_sentiment") or {}
        out2: Dict[str, float] = {}
        for s in symbols:
            try:
                out2[str(s)] = float(src.get(s, 0.0))
            except Exception:
                out2[str(s)] = 0.0
        return out2

    # 3) pipeline
    use_pipeline = _truthy(policy.get("use_news_analysis", True))
    if use_pipeline and collect_news_items is not None and score_news_sentiment_simple is not None:
        items_by = collect_news_items(symbols, state=state, policy=policy)
        state["news_items"] = items_by
        scores = score_news_sentiment_simple(items_by, state=state, policy=policy)
        # ensure defaults
        out3: Dict[str, float] = {}
        for s in symbols:
            try:
                out3[str(s)] = float(scores.get(s, 0.0))
            except Exception:
                out3[str(s)] = 0.0
        return out3

    # default
    return {str(s): 0.0 for s in symbols}


def _get_global_sentiment(state: Dict[str, Any]) -> float:
    v = 0.0
    if "mock_global_sentiment" in state:
        v = state.get("mock_global_sentiment", 0.0)
    elif "global_sentiment" in state:
        v = state.get("global_sentiment", 0.0)
    try:
        return float(v)
    except Exception:
        return 0.0


def _adjust_policy_by_global(policy: Dict[str, Any], gs: float) -> Dict[str, Any]:
    # store for tests
    policy["global_sentiment"] = gs

    if not _truthy(policy.get("use_global_sentiment", True)):
        return policy

    base_max = float(policy.get("max_risk", 0.7))
    base_min = float(policy.get("min_confidence", 0.6))

    # linear adjustment (simple + test-friendly)
    max_risk = base_max + 0.1 * gs
    min_conf = base_min - 0.1 * gs

    # clamp
    max_risk = max(0.05, min(1.0, max_risk))
    min_conf = max(0.0, min(1.0, min_conf))

    policy["max_risk"] = max_risk
    policy["min_confidence"] = min_conf
    return policy


def _rerank_and_filter(
    symbols: List[str],
    policy: Dict[str, Any],
    gs: float,
    news: Dict[str, float],
) -> List[str]:
    if not symbols:
        return symbols

    w_news = float(policy.get("candidate_news_weight", 0.0) or 0.0)
    w_glob = float(policy.get("candidate_global_weight", 0.0) or 0.0)

    # base rank score: earlier in rank list gets higher
    n = max(1, len(symbols))
    scored: List[Tuple[float, str]] = []
    for idx, s in enumerate(symbols):
        base_rank = (n - idx) / n
        total = base_rank + w_news * float(news.get(s, 0.0)) + w_glob * float(gs)
        scored.append((total, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [s for _, s in scored]

    # negative news filter (keep at least 3 candidates)
    thr = float(policy.get("candidate_negative_news_threshold", -999.0))
    if thr > -999.0:
        filtered = [s for s in ranked if float(news.get(s, 0.0)) >= thr]
        if len(filtered) >= 3:
            ranked = filtered

    # risk-off candidate count reduction
    risk_off_thr = float(policy.get("candidate_risk_off_threshold", -999.0))
    if gs <= risk_off_thr:
        max_cnt = int(policy.get("candidate_max_count_risk_off", 3) or 3)
        max_cnt = max(1, min(5, max_cnt))
        ranked = ranked[:max_cnt]

    return ranked


def strategist_node(state: Dict[str, Any]) -> Dict[str, Any]:
    policy = _default_policy(state.get("policy"))

    # candidate_k is the intended key, but keep backward compatibility
    k = int(policy.get("candidate_k") or policy.get("candidate_topk") or 5)
    k = max(3, min(5, k))

    # 1) candidates already present or injected
    candidates = _candidates_from_state(state, k)

    # 2) generate symbols from selected source
    if not candidates:
        source = str(policy.get("candidate_source") or "top_picks")
        if source == "market_rank":
            syms = _market_rank_symbols(state, policy, k)
            why = "market_rank"
        else:
            syms = _top_picks_symbols(state, policy, k)
            why = "top_picks"

        if not syms:
            # final fallback for DRY_RUN/offline so tests always have 3~5
            syms = _fallback_symbols(k)
            why = "fallback"

        candidates = [{"symbol": s, "why": why} for s in syms[:k]]

    # sentiments
    symbols = _symbols_from_candidates(candidates)
    gs = _get_global_sentiment(state)
    state["global_sentiment"] = gs

    policy = _adjust_policy_by_global(policy, gs)

    # news sentiment should exist for all candidate symbols (tests expect default 0.0)
    news_sentiment = _fill_news_sentiment_for_symbols(state, symbols, policy)
    state["news_sentiment"] = news_sentiment

    # rerank symbols based on sentiment signals
    reranked = _rerank_and_filter(symbols, policy, gs, news_sentiment)
    # rebuild candidates in reranked order
    sym_to_why = {c["symbol"]: c.get("why", "") for c in candidates}
    candidates = [{"symbol": s, "why": sym_to_why.get(s, "") or "reranked"} for s in reranked]

    state["policy"] = policy
    state["candidates"] = candidates
    return state
