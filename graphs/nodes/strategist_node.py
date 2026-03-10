from __future__ import annotations

"""Canonical Strategist node for integrated runtime.

Role boundary:
- owns strategic framing (themes/sectors, sentiment context, candidate hints)
- prepares strategist outputs for scanner/monitor handoff
- does not execute orders
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, List

from libs.data_quality.signal_contract import SIGNAL_STATUS_FALLBACK, make_signal
from libs.market.global_sentiment import compute_global_sentiment_signal
from libs.news.news_pipeline import collect_news_items, score_news_sentiment_signal
from libs.runtime.decision_trace import append_decision_trace
from libs.strategies.contracts import StrategistOutput
from libs.strategies.candidates.market_rank import MarketRankCandidateGenerator
from libs.strategies.candidates.market_rank import TopPicksCandidateGenerator
from libs.strategies.universe_builder import build_candidate_universe


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _resolve_top_n_candidates(policy: Dict[str, Any]) -> int:
    raw = (
        policy.get("candidate_k")
        if policy.get("candidate_k") is not None
        else policy.get("candidate_topk")
    )
    if raw is None:
        raw = os.getenv("TOP_N_CANDIDATES", "5")
    return max(1, _to_int(raw, 5))


def _extract_themes(state: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    seen = set()

    def add_many(items: Any) -> None:
        if not isinstance(items, list):
            return
        for x in items:
            t = str(x or "").strip()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)

    add_many(state.get("themes"))
    add_many(state.get("top_themes"))
    add_many(state.get("sector_filter"))
    add_many(state.get("theme_filter"))
    add_many(policy.get("themes"))
    add_many(policy.get("top_themes"))
    add_many(policy.get("sector_filter"))
    add_many(policy.get("theme_filter"))

    theme_scores = state.get("theme_scores") if isinstance(state.get("theme_scores"), dict) else {}
    if theme_scores:
        ranked = sorted(
            ((str(k or "").strip(), float(v or 0.0)) for k, v in theme_scores.items()),
            key=lambda kv: kv[1],
            reverse=True,
        )
        for name, _score in ranked:
            if name and name not in seen:
                seen.add(name)
                out.append(name)

    theme_map = policy.get("theme_map") if isinstance(policy.get("theme_map"), dict) else {}
    for k in theme_map.keys():
        name = str(k or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)

    return out[:5]


def _default_policy(user_policy: Dict[str, Any] | None) -> Dict[str, Any]:
    p = dict(user_policy or {})
    default_topn = max(1, _to_int(os.getenv("TOP_N_CANDIDATES", "5"), 5))
    p.setdefault("use_universe_builder", _is_trueish(os.getenv("USE_UNIVERSE_BUILDER", "true")))
    p.setdefault("universe_require_condition", _is_trueish(os.getenv("UNIVERSE_REQUIRE_CONDITION", "false")))
    # candidate generation
    p.setdefault("candidate_source", "top_picks")  # top_picks | market_rank
    p.setdefault("candidate_k", int(p.get("candidate_topk", default_topn) or default_topn))
    p.setdefault("candidate_rank_mode", "value")
    p.setdefault("candidate_rank_topn", 30)
    # sentiment toggles
    p.setdefault("use_global_sentiment", True)
    p.setdefault("use_news_analysis", False)
    # news plugin
    p.setdefault("news_provider", "naver")
    p.setdefault("news_scorer", "simple")
    # rerank weights
    p.setdefault("candidate_news_weight", 0.2)
    p.setdefault("candidate_global_weight", 0.1)
    p.setdefault("candidate_negative_news_threshold", -0.7)
    p.setdefault("candidate_risk_off_threshold", -0.5)
    p.setdefault("candidate_risk_on_threshold", 0.5)
    p.setdefault("candidate_max_count_risk_off", 3)
    return p


def _candidates_from_state(state: Dict[str, Any], k: int) -> List[Dict[str, str]]:
    # Highest priority: explicit candidates provided
    if isinstance(state.get("candidates"), list) and state["candidates"]:
        out = []
        for x in state["candidates"][:k]:
            if isinstance(x, dict) and "symbol" in x:
                out.append({"symbol": str(x["symbol"]), "why": str(x.get("why") or "injected")})
        return out

    # Next: universe list (tests)
    if isinstance(state.get("universe"), list) and state["universe"]:
        syms = [str(s) for s in state["universe"][:k]]
        return [{"symbol": s, "why": "universe"} for s in syms]

    # Next: direct candidate symbols injection
    if isinstance(state.get("candidate_symbols"), list) and state["candidate_symbols"]:
        syms = [str(s) for s in state["candidate_symbols"][:k]]
        return [{"symbol": s, "why": "candidate_symbols"} for s in syms]

    return []


def _signal_score(sig: Any) -> float:
    if not isinstance(sig, dict):
        return 0.0
    try:
        return float(sig.get("score") or 0.0)
    except Exception:
        return 0.0


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _risk_regime_label(score: float) -> str:
    if score >= 0.20:
        return "risk_on"
    if score <= -0.20:
        return "risk_off"
    return "neutral"


def _market_sentiment_label(score: float) -> str:
    if score >= 0.15:
        return "bullish"
    if score <= -0.15:
        return "bearish"
    return "neutral"


def _market_structure_label(*, state: Dict[str, Any]) -> str:
    market_ctx = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    idx_trend = _to_float(market_ctx.get("index_trend"), 0.0)
    realized_vol = _to_float(market_ctx.get("realized_vol"), 0.0)
    breadth = _to_float(market_ctx.get("market_breadth"), 0.0)
    if realized_vol >= 0.040:
        return "high_volatility"
    elif abs(idx_trend) >= 0.25 and (breadth >= 0.50 or breadth <= -0.50):
        return "trend"
    return "range"


def _pick_playbook(*, market_structure: str, market_regime: str, market_sentiment: str) -> str:
    if str(market_structure).startswith("high_volatility") or market_regime == "risk_off":
        return "defensive"
    if str(market_structure).startswith("trend") and market_regime == "risk_on" and market_sentiment == "bullish":
        return "breakout"
    if str(market_structure).startswith("trend"):
        return "pullback"
    if str(market_structure).startswith("range") and market_regime == "risk_on":
        return "reversal"
    return "defensive"


def _scanner_priority(playbook: str, market_sentiment: str) -> List[str]:
    if playbook == "breakout":
        return ["momentum", "trend_strength", "volume_surge", "liquidity"]
    if playbook == "pullback":
        return ["trend_strength", "pullback_quality", "relative_strength", "liquidity"]
    if playbook == "reversal":
        return ["oversold_reversal", "volume_confirmation", "risk_reward", "liquidity"]
    # defensive
    base = ["liquidity", "risk_penalty", "low_volatility", "drawdown_control"]
    if market_sentiment == "risk_off":
        base.insert(0, "capital_preservation")
    return base


def _scanner_bias(*, playbook: str, market_regime: str) -> str:
    if market_regime == "risk_off":
        return "large_cap"
    if playbook == "breakout":
        return "momentum"
    if playbook == "pullback":
        return "leader"
    if playbook == "reversal":
        return "value"
    return "leader"


def _avoid_themes(*, market_sentiment: str, playbook: str) -> List[str]:
    if market_sentiment == "risk_off" or playbook == "defensive":
        return ["illiquid_microcap", "headline_only_momentum", "high_gap_speculative"]
    if playbook == "reversal":
        return ["overextended_breakout_without_volume", "late_chasing_moves"]
    if playbook == "pullback":
        return ["counter_trend_low_liquidity"]
    return ["thin_liquidity_names"]


def _trade_aggressiveness(*, market_regime: str, market_structure: str) -> str:
    if market_regime == "risk_off" or str(market_structure).startswith("high_volatility"):
        return "low"
    if market_regime == "risk_on" and str(market_structure).startswith("trend"):
        return "high"
    return "medium"


def _risk_tone(aggressiveness: str) -> str:
    if aggressiveness == "low":
        return "conservative"
    if aggressiveness == "high":
        return "aggressive"
    return "normal"


def _monitor_guidance(*, market_regime: str, playbook: str) -> str:
    if market_regime == "risk_off" or playbook == "defensive":
        return "defensive_exit"
    if playbook == "breakout":
        return "hold_through_noise"
    return "quick_take_profit"


def _monitor_policy(
    *,
    monitor_guidance: str,
    trade_aggressiveness: str,
    risk_tone: str,
) -> Dict[str, Any]:
    min_hold_sec = _to_int(os.getenv("MIN_HOLD_SECONDS", "600"), 600)
    sell_cooldown = _to_int(os.getenv("SELL_COOLDOWN", os.getenv("SELL_COOLDOWN_SEC", "300")), 300)
    confirm_ticks = _to_int(os.getenv("MONITOR_EXIT_CONFIRM_TICKS", "2"), 2)
    adjustments: List[str] = []

    mode = str(monitor_guidance or "").strip().lower()
    if mode == "hold_through_noise":
        min_hold_sec += 300
        confirm_ticks += 1
        sell_cooldown += 60
        adjustments.append("mode:hold_through_noise")
    elif mode == "defensive_exit":
        confirm_ticks = max(1, confirm_ticks - 1)
        min_hold_sec = max(0, min_hold_sec - 120)
        adjustments.append("mode:defensive_exit")
    elif mode == "quick_take_profit":
        confirm_ticks = 1
        min_hold_sec = max(0, min_hold_sec - 300)
        sell_cooldown = max(60, min(sell_cooldown, 180))
        adjustments.append("mode:quick_take_profit")

    tone = str(risk_tone or "").strip().lower()
    if tone == "conservative":
        confirm_ticks += 1
        min_hold_sec += 120
        adjustments.append("risk_tone:conservative")
    elif tone == "aggressive":
        confirm_ticks = max(1, confirm_ticks - 1)
        min_hold_sec = max(0, min_hold_sec - 60)
        adjustments.append("risk_tone:aggressive")

    aggr = str(trade_aggressiveness or "").strip().lower()
    if aggr == "low":
        confirm_ticks = max(confirm_ticks, 3)
        adjustments.append("trade_aggressiveness:low")
    elif aggr == "high":
        confirm_ticks = max(1, confirm_ticks - 1)
        adjustments.append("trade_aggressiveness:high")

    return {
        "min_hold_seconds": max(0, int(min_hold_sec)),
        "sell_cooldown_seconds": max(0, int(sell_cooldown)),
        "exit_confirm_ticks": max(1, min(6, int(confirm_ticks))),
        "adjustments": list(adjustments),
        "note": "monitor_manages_entry_exit_only",
    }


def _report_focus(*, playbook: str, themes: List[str]) -> List[str]:
    if playbook == "defensive":
        return ["theme_accuracy", "exit_quality", "overtrading", "guard_blocks"]
    if playbook == "breakout":
        return ["theme_accuracy", "scanner_fit", "exit_quality", "overtrading"]
    return ["theme_accuracy", "scanner_fit", "exit_quality", "overtrading"]


def _key_events(
    *,
    state: Dict[str, Any],
    global_signal: Dict[str, Any],
    news_signal_map: Dict[str, Dict[str, Any]],
    market_regime: str,
    playbook: str,
) -> List[str]:
    out: List[str] = []

    def add(x: Any) -> None:
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)

    # highest priority: explicit externally-provided macro/event list
    for key in ("macro_events", "global_events", "major_events"):
        vals = state.get(key)
        if isinstance(vals, list):
            for row in vals:
                add(row)
            if out:
                break

    if not out:
        add(
            "global_sentiment "
            f"score={_signal_score(global_signal):.3f} "
            f"status={str(global_signal.get('status') or '')} "
            f"source={str(global_signal.get('source') or '')}"
        )

        unavailable = 0
        fallback = 0
        for row in news_signal_map.values():
            if not isinstance(row, dict):
                continue
            st = str(row.get("status") or "").strip().lower()
            if st == "unavailable":
                unavailable += 1
            elif st == "fallback":
                fallback += 1
        add(f"news_signal_health unavailable={unavailable} fallback={fallback}")
        add(f"market_regime={market_regime}")
        add(f"playbook={playbook}")

    return out[:5]


def _extract_ai_overrides(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    # External LLM strategists can inject this shape without breaking node contract.
    for key in ("ai_strategist_output", "strategist_ai_output", "strategic_brief"):
        raw = state.get(key)
        if isinstance(raw, dict):
            return dict(raw)
    raw_policy = policy.get("strategist_ai_output") if isinstance(policy.get("strategist_ai_output"), dict) else {}
    return dict(raw_policy)


def _merge_override_text_list(base: List[str], override_values: Any, *, limit: int = 8) -> List[str]:
    if not isinstance(override_values, list):
        return list(base)[:limit]
    merged: List[str] = []
    seen = set()
    for row in list(override_values) + list(base):
        s = str(row or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        merged.append(s)
        if len(merged) >= limit:
            break
    return merged


def _build_strategic_answers(
    *,
    market_regime: str,
    market_sentiment: str,
    key_events: List[str],
    themes: List[str],
    avoid_themes: List[str],
    playbook: str,
    scanner_bias: str,
    scanner_priority: List[str],
    trade_aggressiveness: str,
    risk_tone: str,
    monitor_guidance: str,
    report_focus: List[str],
) -> Dict[str, Any]:
    return {
        "q1_market_mode": market_regime,
        "q2_global_macro_events": list(key_events),
        "q3_leading_themes": list(themes),
        "q4_theme_strength_check": "use_scanner_score_breakdown_and_theme_boost",
        "q5_preferred_playbook": playbook,
        "q6_scanner_priority_stocks": list(scanner_priority),
        "q7_avoid_conditions": list(avoid_themes),
        "q8_trade_aggressiveness": trade_aggressiveness,
        "q9_risk_tone": risk_tone,
        "q10_scanner_ranking_priority": list(scanner_priority),
        "q11_monitor_exit_guidance": monitor_guidance,
        "q12_reporter_focus": list(report_focus),
        "scanner_bias": scanner_bias,
    }


def _make_event_logger(state: Dict[str, Any]) -> Any:
    injected = state.get("event_logger")
    if injected is not None and hasattr(injected, "log"):
        return injected
    from libs.core.event_logger import EventLogger

    log_path = os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl")
    return EventLogger(log_path=Path(log_path))


def _log_strategist_summary(state: Dict[str, Any], payload: Dict[str, Any]) -> None:
    try:
        logger = _make_event_logger(state)
        run_id = str(state.get("run_id") or "strategist-node")
        logger.log(run_id=run_id, stage="strategist", event="summary", payload=dict(payload))
    except Exception:
        return


def strategist_node(state: Dict[str, Any]) -> Dict[str, Any]:
    policy = _default_policy(state.get("policy"))
    k = _resolve_top_n_candidates(policy)
    policy["candidate_k"] = int(k)

    # 1) candidates (injected or generated)
    candidates = _candidates_from_state(state, k)
    universe_candidates: List[Dict[str, Any]] = []

    if not candidates:
        if bool(policy.get("use_universe_builder", True)):
            universe_candidates = build_candidate_universe(state=state, policy=policy, topk=k)
            if universe_candidates:
                candidates = [
                    {
                        "symbol": str(r.get("symbol") or ""),
                        "why": str(r.get("why") or "universe_builder"),
                        "sources": list(r.get("sources") or []),
                        "universe_score": float(r.get("score") or 0.0),
                        "source_scores": dict(r.get("source_scores") or {}),
                        "source_count": int(r.get("source_count") or len(list(r.get("sources") or []))),
                    }
                    for r in universe_candidates
                    if str(r.get("symbol") or "").strip()
                ]

    if not candidates:
        source = str(policy.get("candidate_source") or "top_picks")
        if source == "market_rank":
            gen = MarketRankCandidateGenerator()
            # tolerate signature differences
            try:
                symbols = gen.generate(state=state, policy=policy, k=k)
            except TypeError:
                try:
                    symbols = gen.generate(state=state, k=k)
                except TypeError:
                    symbols = gen.generate(state=state)
            candidates = [{"symbol": str(s), "why": "market_rank"} for s in symbols[:k]]
        else:
            # top_picks (M18-2): generator signature is generate(state)
            gen = TopPicksCandidateGenerator(
                rank_mode=str(policy.get("candidate_rank_mode") or "value"),
                rank_topn=int(policy.get("candidate_rank_topn") or 30),
                topk=int(policy.get("candidate_topk") or k),
            )
            symbols = gen.generate(state=state)
            candidates = [{"symbol": str(s), "why": "top_picks"} for s in symbols[:k]]

    # absolute fallback: never return empty in DRY_RUN tests
    if not candidates:
        fallback = ["005930", "000660", "035420", "051910", "068270"][:k]
        candidates = [{"symbol": s, "why": "fallback"} for s in fallback]

    state["universe_candidates"] = universe_candidates
    symbols = [c["symbol"] for c in candidates]

    # 2) Global sentiment (score + data-quality signal)
    now = int(time.time())
    if bool(policy.get("use_global_sentiment", True)):
        try:
            global_signal = dict(compute_global_sentiment_signal(state=state, policy=policy))
        except Exception:
            global_signal = make_signal(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source="strategist_node",
                reason="global_sentiment_exception",
                ts=now,
            )
    else:
        global_signal = make_signal(
            score=0.0,
            status=SIGNAL_STATUS_FALLBACK,
            source="global_policy",
            reason="global_sentiment_disabled",
            ts=now,
        )
    gs = _signal_score(global_signal)
    policy["global_sentiment"] = float(gs)
    # Keep canonical state-level score and signal shape for downstream nodes.
    state["global_sentiment"] = {"score": float(gs)}
    state["global_sentiment_signal"] = dict(global_signal)

    # policy adjustment based on global sentiment
    # - risk-off: max_risk decreases, min_confidence increases
    # - risk-on : max_risk increases, min_confidence decreases
    base_max_risk = float(policy.get("max_risk", 0.7))
    base_min_conf = float(policy.get("min_confidence", 0.6))
    off_th = float(policy.get("candidate_risk_off_threshold", -0.5))
    on_th = float(policy.get("candidate_risk_on_threshold", 0.5))

    if gs <= off_th:
        policy["max_risk"] = max(0.05, base_max_risk - 0.1)
        policy["min_confidence"] = min(0.99, base_min_conf + 0.1)
    elif gs >= on_th:
        policy["max_risk"] = min(1.0, base_max_risk + 0.1)
        policy["min_confidence"] = max(0.01, base_min_conf - 0.1)
    else:
        policy["max_risk"] = base_max_risk
        policy["min_confidence"] = base_min_conf

    # 3) News analysis (score + data-quality signal)
    news_items_by_symbol = {s: [] for s in symbols}
    news_signal_map: Dict[str, Dict[str, Any]] = {}

    if bool(policy.get("use_news_analysis", False)) or state.get("mock_news_sentiment") is not None:
        # mock_news_sentiment path is handled inside score_news_sentiment_signal.
        if bool(policy.get("use_news_analysis", False)) or state.get("mock_news_items") is not None:
            news_items_by_symbol = collect_news_items(symbols, state=state, policy=policy)
        try:
            news_signal_map = score_news_sentiment_signal(
                news_items_by_symbol,
                state=state,
                policy=policy,
                symbols=symbols,
            )
        except Exception:
            news_signal_map = {
                s: make_signal(
                    score=0.0,
                    status=SIGNAL_STATUS_FALLBACK,
                    source="strategist_node",
                    reason="news_sentiment_exception",
                    ts=now,
                )
                for s in symbols
            }
    else:
        news_signal_map = {
            s: make_signal(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source="news_policy",
                reason="news_analysis_disabled",
                ts=now,
            )
            for s in symbols
        }

    news_sent = {s: _signal_score(news_signal_map.get(s)) for s in symbols}

    state["policy"] = policy
    state["candidates"] = candidates
    # store per-symbol news items (dict)
    state["news_items"] = news_items_by_symbol
    state["news_sentiment"] = news_sent
    state["news_sentiment_signal"] = news_signal_map

    # 4) Candidate rerank (M18-5): apply weights and negative-news filter, then risk-off count reduction
    w_news = float(policy.get("candidate_news_weight", 0.2))
    w_g = float(policy.get("candidate_global_weight", 0.1))
    neg_th = float(policy.get("candidate_negative_news_threshold", -0.7))

    # assign candidate_score
    scored = []
    candidate_meta = {str(c.get("symbol")): dict(c) for c in candidates if isinstance(c, dict)}
    for idx, c in enumerate(candidates):
        s = c["symbol"]
        rank_bias = (len(candidates) - idx) / max(len(candidates), 1) * 0.01  # small deterministic tie-break
        cs = rank_bias + (w_news * news_sent.get(s, 0.0)) + (w_g * gs)
        scored.append((s, cs, news_sent.get(s, 0.0), c.get("why") or ""))

    # filter overly negative news, but don't drop below 3 items if possible
    filtered = [t for t in scored if t[2] >= neg_th]
    if len(filtered) >= 3:
        scored = filtered

    scored.sort(key=lambda x: x[1], reverse=True)
    candidates = []
    for (s, cs, _ns, why) in scored:
        base = dict(candidate_meta.get(s) or {})
        base["symbol"] = s
        base["why"] = why
        base["rank_score"] = float(cs)
        candidates.append(base)

    # risk-off reduces count
    if gs <= float(policy.get("candidate_risk_off_threshold", -0.5)):
        max_cnt = int(policy.get("candidate_max_count_risk_off", 3))
        candidates = candidates[: max(1, max_cnt)]
    else:
        candidates = candidates[:k]

    state["candidates"] = candidates
    themes = _extract_themes(state, policy)
    ai_overrides = _extract_ai_overrides(state, policy)
    themes = _merge_override_text_list(themes, ai_overrides.get("themes"), limit=5)
    state["themes"] = themes
    state["candidate_symbols"] = [str(c.get("symbol") or "") for c in candidates if str(c.get("symbol") or "").strip()]

    market_regime = _risk_regime_label(gs)
    market_sentiment = _market_sentiment_label(gs)
    market_structure = _market_structure_label(state=state)
    playbook = _pick_playbook(
        market_structure=market_structure,
        market_regime=market_regime,
        market_sentiment=market_sentiment,
    )
    scanner_priority = _scanner_priority(playbook, market_regime)
    scanner_bias = _scanner_bias(playbook=playbook, market_regime=market_regime)
    avoid_themes = _avoid_themes(market_sentiment=market_sentiment, playbook=playbook)
    trade_aggressiveness = _trade_aggressiveness(market_regime=market_regime, market_structure=market_structure)
    risk_tone = _risk_tone(trade_aggressiveness)
    monitor_guidance = _monitor_guidance(market_regime=market_regime, playbook=playbook)
    monitor_policy = _monitor_policy(
        monitor_guidance=monitor_guidance,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
    )
    report_focus = _report_focus(playbook=playbook, themes=themes)
    key_events = _key_events(
        state=state,
        global_signal=global_signal,
        news_signal_map=news_signal_map,
        market_regime=market_regime,
        playbook=playbook,
    )

    # Optional AI overrides are additive and bounded to keep deterministic fallback.
    market_regime = str(ai_overrides.get("market_regime") or market_regime).strip() or market_regime
    market_sentiment = str(ai_overrides.get("market_sentiment") or market_sentiment).strip() or market_sentiment
    playbook = str(ai_overrides.get("playbook") or playbook).strip() or playbook
    trade_aggressiveness = str(ai_overrides.get("trade_aggressiveness") or trade_aggressiveness).strip() or trade_aggressiveness
    risk_tone = str(ai_overrides.get("risk_tone") or risk_tone).strip() or risk_tone
    key_events = _merge_override_text_list(key_events, ai_overrides.get("key_events"), limit=5)
    avoid_themes = _merge_override_text_list(avoid_themes, ai_overrides.get("avoid_themes"), limit=6)
    scanner_priority = _merge_override_text_list(scanner_priority, ai_overrides.get("scanner_priority"), limit=6)
    report_focus = _merge_override_text_list(report_focus, ai_overrides.get("report_focus"), limit=6)
    scanner_bias = str(ai_overrides.get("scanner_bias") or scanner_bias).strip().lower() or scanner_bias
    monitor_guidance = str(ai_overrides.get("monitor_guidance") or monitor_guidance).strip().lower() or monitor_guidance
    monitor_policy_override = ai_overrides.get("monitor_policy")
    if isinstance(monitor_policy_override, dict):
        monitor_policy = {**monitor_policy, **dict(monitor_policy_override)}
    else:
        monitor_policy = _monitor_policy(
            monitor_guidance=monitor_guidance,
            trade_aggressiveness=trade_aggressiveness,
            risk_tone=risk_tone,
        )

    strategic_answers = _build_strategic_answers(
        market_regime=market_regime,
        market_sentiment=market_sentiment,
        key_events=key_events,
        themes=themes,
        avoid_themes=avoid_themes,
        playbook=playbook,
        scanner_bias=scanner_bias,
        scanner_priority=scanner_priority,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
        monitor_guidance=monitor_guidance,
        report_focus=report_focus,
    )

    state["market_regime"] = market_regime
    state["market_sentiment"] = market_sentiment
    state["market_structure"] = market_structure
    state["key_events"] = list(key_events)
    state["avoid_themes"] = list(avoid_themes)
    state["playbook"] = playbook
    state["scanner_bias"] = scanner_bias
    state["scanner_priority"] = list(scanner_priority)
    state["trade_aggressiveness"] = trade_aggressiveness
    state["risk_tone"] = risk_tone
    state["monitor_guidance"] = monitor_guidance
    state["monitor_policy"] = dict(monitor_policy)
    state["report_focus"] = list(report_focus)
    state["scanner_guidance"] = {
        "themes": list(themes),
        "avoid_themes": list(avoid_themes),
        "scanner_bias": scanner_bias,
        "scanner_priority": list(scanner_priority),
        "trade_aggressiveness": trade_aggressiveness,
        "risk_tone": risk_tone,
    }
    strategist_output = StrategistOutput(
        market_regime=market_regime,
        market_sentiment=market_sentiment,
        key_events=list(key_events),
        themes=list(themes),
        avoid_themes=list(avoid_themes),
        playbook=playbook,
        scanner_bias=scanner_bias if scanner_bias in ("large_cap", "leader", "momentum", "value") else "leader",
        scanner_priority=list(scanner_priority),
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone if risk_tone in ("conservative", "normal", "aggressive") else "normal",
        monitor_guidance=(
            monitor_guidance
            if monitor_guidance in ("hold_through_noise", "defensive_exit", "quick_take_profit")
            else "defensive_exit"
        ),
        report_focus=list(report_focus),
        candidates=list(state["candidate_symbols"]),
        candidate_count=len(list(state["candidate_symbols"])),
        candidate_hints=list(state["candidate_symbols"]),
        strategic_answers=dict(strategic_answers),
        source="strategist_node",
    ).to_dict()
    strategist_output["monitor_policy"] = dict(monitor_policy)
    strategist_output["market_structure"] = market_structure
    state["strategist_output"] = strategist_output
    _log_strategist_summary(
        state,
        {
            "market_regime": market_regime,
            "market_sentiment": market_sentiment,
            "themes": list(themes),
            "avoid_themes": list(avoid_themes),
            "playbook": playbook,
            "scanner_bias": scanner_bias,
            "scanner_priority": list(scanner_priority),
            "trade_aggressiveness": trade_aggressiveness,
            "risk_tone": risk_tone,
            "monitor_guidance": monitor_guidance,
            "candidate_count": len(list(state["candidate_symbols"])),
            "report_focus": list(report_focus)[:3],
        },
    )
    append_decision_trace(
        state,
        agent="strategist",
        event="strategic_frame",
        payload={
            "market_regime": market_regime,
            "market_sentiment": market_sentiment,
            "themes": list(themes)[:5],
            "playbook": playbook,
            "scanner_bias": scanner_bias,
            "risk_tone": risk_tone,
            "monitor_guidance": monitor_guidance,
        },
    )
    return state
