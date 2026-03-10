from __future__ import annotations

"""Canonical Scanner node for integrated runtime.

Role boundary:
- builds/reduces/ranks candidate pool (Kiwoom-first, strategist-guided)
- selects Top-1 candidate for monitor stage
- does not create execution calls
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from graphs.nodes.skill_contracts import (
    CONTRACT_VERSION as SKILL_CONTRACT_VERSION,
    extract_account_orders_rows,
    extract_market_quotes,
    norm_symbol,
)
from libs.strategies.candidates.kiwoom_candidate_provider import build_kiwoom_candidate_rows
from libs.runtime.feature_engine import build_feature_map


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _norm_symbol(v: Any) -> str:
    return norm_symbol(v)


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _make_event_logger(state: Dict[str, Any]) -> Any:
    injected = state.get("event_logger")
    if injected is not None and hasattr(injected, "log"):
        return injected
    from libs.core.event_logger import EventLogger

    log_path = os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl")
    return EventLogger(log_path=Path(log_path))


def _log_scanner_summary(state: Dict[str, Any], payload: Dict[str, Any]) -> None:
    try:
        logger = _make_event_logger(state)
        run_id = str(state.get("run_id") or "scanner-node")
        logger.log(run_id=run_id, stage="scanner", event="summary", payload=dict(payload))
    except Exception:
        return


def _extract_skill_quotes(state: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    return extract_market_quotes(state)


def _extract_account_open_order_counts(state: Dict[str, Any]) -> Tuple[Dict[str, int], int, Dict[str, Any]]:
    rows, meta = extract_account_orders_rows(state)

    out: Dict[str, int] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        symbol = _norm_symbol(r.get("symbol") or r.get("stk_cd") or r.get("code"))
        if not symbol:
            continue
        out[symbol] = int(out.get(symbol, 0)) + 1
    return out, len(rows), meta


def _get_global_sentiment_score(state: Dict[str, Any]) -> float:
    """Return global sentiment score in [-1, +1].

    Priority:
      1) state['global_sentiment_signal']['score'] (normalized signal)
      2) state['mock_global_sentiment'] (tests)
      3) state['global_sentiment']['score'] (precomputed)
      4) state['policy']['global_sentiment']['score'] (set by strategist)
      5) default 0.0
    """
    gsig = state.get("global_sentiment_signal")
    if isinstance(gsig, dict):
        try:
            return _clamp(float(gsig.get("score") or 0.0), -1.0, 1.0)
        except Exception:
            return 0.0

    if "mock_global_sentiment" in state:
        try:
            return _clamp(float(state.get("mock_global_sentiment") or 0.0), -1.0, 1.0)
        except Exception:
            return 0.0

    gs = state.get("global_sentiment")
    if isinstance(gs, dict) and "score" in gs:
        try:
            return _clamp(float(gs.get("score") or 0.0), -1.0, 1.0)
        except Exception:
            return 0.0
    if isinstance(gs, (int, float, str)):
        try:
            return _clamp(float(gs), -1.0, 1.0)
        except Exception:
            return 0.0

    pol = state.get("policy")
    if isinstance(pol, dict):
        pgs = pol.get("global_sentiment")
        if isinstance(pgs, dict) and "score" in pgs:
            try:
                return _clamp(float(pgs.get("score") or 0.0), -1.0, 1.0)
            except Exception:
                return 0.0
        if isinstance(pgs, (int, float, str)):
            try:
                return _clamp(float(pgs), -1.0, 1.0)
            except Exception:
                return 0.0

    return 0.0


def _get_news_sentiment_map(state: Dict[str, Any]) -> Dict[str, float]:
    """Return per-symbol news sentiment map in [-1, +1].

    Priority:
      1) state['news_sentiment_signal'][symbol]['score']
      2) state['news_sentiment'][symbol]
      3) state['mock_news_sentiment'][symbol]
    """
    raw_sig = state.get("news_sentiment_signal")
    if isinstance(raw_sig, dict):
        out_sig: Dict[str, float] = {}
        for k, v in raw_sig.items():
            if isinstance(v, dict):
                try:
                    out_sig[str(k)] = _clamp(float(v.get("score") or 0.0), -1.0, 1.0)
                except Exception:
                    out_sig[str(k)] = 0.0
        if out_sig:
            return out_sig

    raw = state.get("news_sentiment")
    if not isinstance(raw, dict):
        raw = state.get("mock_news_sentiment") if isinstance(state.get("mock_news_sentiment"), dict) else {}
    out: Dict[str, float] = {}
    for k, v in (raw or {}).items():
        try:
            out[str(k)] = _clamp(float(v), -1.0, 1.0)
        except Exception:
            out[str(k)] = 0.0
    return out


def _get_global_sentiment_signal(state: Dict[str, Any]) -> Dict[str, Any]:
    sig = state.get("global_sentiment_signal")
    if isinstance(sig, dict):
        return dict(sig)
    if "mock_global_sentiment" in state:
        return {"status": "ok", "source": "mock_global_sentiment", "reason": ""}
    gs = state.get("global_sentiment")
    if isinstance(gs, dict) and gs.get("score") is not None:
        return {"status": "fallback", "source": "legacy_global_sentiment", "reason": "signal_missing"}
    return {"status": "fallback", "source": "scanner_node", "reason": "missing_global_signal"}


def _get_news_sentiment_signal_map(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = state.get("news_sentiment_signal")
    if not isinstance(raw, dict):
        raw_scores = state.get("news_sentiment")
        if not isinstance(raw_scores, dict):
            raw_scores = state.get("mock_news_sentiment") if isinstance(state.get("mock_news_sentiment"), dict) else {}
        out_legacy: Dict[str, Dict[str, Any]] = {}
        for k, _v in (raw_scores or {}).items():
            source = "legacy_news_sentiment"
            status = "fallback"
            if isinstance(state.get("mock_news_sentiment"), dict) and str(k) in state.get("mock_news_sentiment", {}):
                source = "mock_news_sentiment"
                status = "ok"
            out_legacy[str(k)] = {"status": status, "source": source, "reason": "signal_missing"}
        return out_legacy
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[str(k)] = dict(v)
    return out


def _get_scanner_weights(policy: Any) -> Dict[str, float]:
    """Scanner weighting policy for M18-4.

    Defaults are conservative (small influence), and should not change behavior
    when sentiments are missing (both default to 0.0).
    """
    pol = policy if isinstance(policy, dict) else {}
    return {
        "weight_news": float(pol.get("weight_news", 0.20)),
        "weight_global": float(pol.get("weight_global", 0.10)),
        "risk_news_penalty": float(pol.get("risk_news_penalty", 0.30)),
        "risk_global_penalty": float(pol.get("risk_global_penalty", 0.20)),
        "confidence_news_boost": float(pol.get("confidence_news_boost", 0.05)),
        "feature_score_weight": float(pol.get("feature_score_weight", 0.0)),
        "feature_risk_penalty": float(pol.get("feature_risk_penalty", 0.0)),
        "high_vol_risk_penalty": float(pol.get("high_vol_risk_penalty", 0.0)),
    }


def _stable_unit_hash(text: str) -> float:
    """Return a deterministic pseudo-random float in [0, 1).

    We avoid Python's built-in hash() because it is salted per-process.
    """
    # A tiny, deterministic rolling hash
    h = 0
    for ch in text:
        h = (h * 131 + ord(ch)) % 10_000
    return (h % 10_000) / 10_000.0


def _extract_feature_engine_map(state: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], str, List[str]]:
    errors: List[str] = []

    # Priority 1: explicit features map injection.
    direct = state.get("scanner_features")
    if isinstance(direct, dict):
        out: Dict[str, Dict[str, Any]] = {}
        for k, v in direct.items():
            if not isinstance(v, dict):
                continue
            sym = _norm_symbol(k)
            if sym:
                out[sym] = dict(v)
        return out, "state.scanner_features", errors

    # Priority 2: precomputed feature engine output.
    fe = state.get("feature_engine")
    if isinstance(fe, dict) and isinstance(fe.get("by_symbol"), dict):
        out2: Dict[str, Dict[str, Any]] = {}
        by_symbol = fe.get("by_symbol") or {}
        for k, v in by_symbol.items():
            if not isinstance(v, dict):
                continue
            sym = _norm_symbol(k)
            if sym:
                out2[sym] = dict(v)
        return out2, "state.feature_engine.by_symbol", errors

    # Priority 3: compute from OHLCV data if available.
    ohlcv = state.get("ohlcv_by_symbol")
    if isinstance(ohlcv, dict):
        try:
            policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
            trend_gap_threshold = float(policy.get("feature_trend_gap_threshold", 0.01))
            high_vol_threshold = float(policy.get("feature_high_vol_threshold", 0.03))
            ctx: Dict[str, Any] = {
                "global_sentiment": _get_global_sentiment_score(state),
            }
            # Optional context hooks (already normalized in state when available).
            if isinstance(state.get("market_context"), dict):
                mc = state.get("market_context") or {}
                if mc.get("market_breadth") is not None:
                    ctx["market_breadth"] = mc.get("market_breadth")
                if mc.get("index_trend") is not None:
                    ctx["index_trend"] = mc.get("index_trend")
                if mc.get("realized_vol") is not None:
                    ctx["realized_vol"] = mc.get("realized_vol")
            built = build_feature_map(
                ohlcv,
                trend_gap_threshold=trend_gap_threshold,
                high_vol_threshold=high_vol_threshold,
                context=ctx,
            )
            return {_norm_symbol(k): v for k, v in built.items() if _norm_symbol(k)}, "state.ohlcv_by_symbol", errors
        except Exception as e:
            errors.append(f"feature_engine:error:{type(e).__name__}")

    return {}, "none", errors


def _extract_strategist_candidates(state: Dict[str, Any]) -> List[Any]:
    candidates = state.get("candidates")
    if isinstance(candidates, list) and candidates:
        return list(candidates)

    strategist_output = state.get("strategist_output")
    if isinstance(strategist_output, dict):
        from_output = strategist_output.get("candidates")
        if isinstance(from_output, list):
            return list(from_output)
    return []


def _extract_themes(state: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    seen = set()

    def add_many(values: Any) -> None:
        if not isinstance(values, list):
            return
        for row in values:
            t = str(row or "").strip().lower()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)

    add_many(state.get("themes"))
    add_many(state.get("top_themes"))
    strategist_output = state.get("strategist_output")
    if isinstance(strategist_output, dict):
        add_many(strategist_output.get("themes"))
    return out


def _extract_theme_symbol_index(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, set[str]]:
    idx: Dict[str, set[str]] = {}

    def add_map(raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        for theme_name, symbols in raw.items():
            key = str(theme_name or "").strip().lower()
            if not key:
                continue
            bucket = idx.setdefault(key, set())
            if isinstance(symbols, list):
                for sym in symbols:
                    s = _norm_symbol(sym)
                    if s:
                        bucket.add(s)

    add_map(state.get("theme_map"))
    add_map(policy.get("theme_map"))
    add_map(state.get("sector_map"))
    add_map(policy.get("sector_map"))
    return idx


def _apply_theme_filter(
    rows: List[Dict[str, Any]],
    *,
    themes: List[str],
    theme_symbol_index: Dict[str, set[str]],
    enable_theme_filter: bool,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not rows:
        return rows, {"theme_filter_applied": False, "theme_filter_reason": "no_rows", "matched_theme_count": 0}
    if not themes:
        return rows, {"theme_filter_applied": False, "theme_filter_reason": "no_themes", "matched_theme_count": 0}
    if not theme_symbol_index:
        return rows, {"theme_filter_applied": False, "theme_filter_reason": "theme_index_missing", "matched_theme_count": 0}

    matched_theme_count = 0
    allowed: set[str] = set()
    for theme in themes:
        syms = theme_symbol_index.get(str(theme or "").strip().lower()) or set()
        if syms:
            matched_theme_count += 1
            allowed.update(set(syms))

    if not allowed:
        return rows, {
            "theme_filter_applied": False,
            "theme_filter_reason": "theme_not_mapped",
            "matched_theme_count": int(matched_theme_count),
            "theme_matched_symbols": [],
        }

    if not bool(enable_theme_filter):
        return rows, {
            "theme_filter_applied": False,
            "theme_filter_reason": "disabled",
            "matched_theme_count": int(matched_theme_count),
            "theme_matched_symbols": sorted(list(allowed)),
        }

    filtered = [r for r in rows if _norm_symbol(r.get("symbol")) in allowed]
    if not filtered:
        return rows, {
            "theme_filter_applied": False,
            "theme_filter_reason": "empty_after_filter_fallback",
            "matched_theme_count": int(matched_theme_count),
            "theme_matched_symbols": sorted(list(allowed)),
        }

    return filtered, {
        "theme_filter_applied": True,
        "theme_filter_reason": "",
        "matched_theme_count": int(matched_theme_count),
        "theme_matched_symbols": sorted(list(allowed)),
    }


def _resolve_candidate_source(state: Dict[str, Any], policy: Dict[str, Any]) -> str:
    raw = state.get("candidate_source")
    if raw in (None, ""):
        raw = policy.get("candidate_source")
    if raw in (None, ""):
        raw = os.getenv("CANDIDATE_SOURCE", "kiwoom")
    v = str(raw or "").strip().lower()
    if v in ("strategist", "strategist_candidates", "provided"):
        return "strategist"
    if v in ("auto", "hybrid"):
        return "auto"
    return "kiwoom"


def _resolve_candidate_limit(policy: Dict[str, Any]) -> int:
    env_topn = _to_int(os.getenv("TOP_N_CANDIDATES", "5"), 5)
    return max(1, _to_int(policy.get("candidate_k", policy.get("candidate_topk", env_topn)), env_topn))


def _resolve_top_candidate_pool(policy: Dict[str, Any], *, candidate_limit: int) -> int:
    env_pool = _to_int(os.getenv("TOP_CANDIDATE_POOL", "30"), 30)
    return max(candidate_limit, _to_int(policy.get("top_candidate_pool", env_pool), env_pool))


def _resolve_condition_limit(policy: Dict[str, Any], *, top_pool: int) -> int:
    env_cond = _to_int(os.getenv("KIWOOM_CANDIDATE_CONDITION_LIMIT", "200"), 200)
    return max(top_pool, _to_int(policy.get("candidate_condition_limit", env_cond), env_cond))


def _resolve_include_change_rate(policy: Dict[str, Any]) -> bool:
    if policy.get("kiwoom_include_change_rate") is not None:
        return _is_trueish(policy.get("kiwoom_include_change_rate"))
    return _is_trueish(os.getenv("KIWOOM_CANDIDATE_INCLUDE_CHANGE_RATE", "true"))


def _resolve_enable_theme_filter(policy: Dict[str, Any]) -> bool:
    if policy.get("enable_theme_filter") is not None:
        return _is_trueish(policy.get("enable_theme_filter"))
    return _is_trueish(os.getenv("ENABLE_THEME_FILTER", "true"))


def _resolve_min_trading_value(policy: Dict[str, Any]) -> float:
    raw = policy.get("min_trading_value")
    if raw in (None, ""):
        raw = os.getenv("MIN_TRADING_VALUE", "0")
    return max(0.0, _to_float(raw))


def _resolve_min_volume(policy: Dict[str, Any]) -> float:
    raw = policy.get("min_volume")
    if raw in (None, ""):
        raw = os.getenv("MIN_VOLUME", "0")
    return max(0.0, _to_float(raw))


def _resolve_exclude_halted(policy: Dict[str, Any]) -> bool:
    if policy.get("exclude_halted") is not None:
        return _is_trueish(policy.get("exclude_halted"))
    return _is_trueish(os.getenv("EXCLUDE_HALTED_STOCKS", "true"))


def _resolve_scanner_score_weights(policy: Dict[str, Any]) -> Dict[str, float]:
    def pf(key: str, env_key: str, default: float) -> float:
        raw = policy.get(key)
        if raw in (None, ""):
            raw = os.getenv(env_key, str(default))
        return _to_float(raw)

    return {
        "trading_value": pf("score_weight_trading_value", "SCORE_WEIGHTS_TRADING_VALUE", 0.20),
        "momentum": pf("score_weight_momentum", "SCORE_WEIGHTS_MOMENTUM", 0.22),
        "trend": pf("score_weight_trend", "SCORE_WEIGHTS_TREND", 0.20),
        "volume_surge": pf("score_weight_volume_surge", "SCORE_WEIGHTS_VOLUME_SURGE", 0.14),
        "intraday_strength": pf("score_weight_intraday_strength", "SCORE_WEIGHTS_INTRADAY_STRENGTH", 0.12),
        "theme_boost": pf("score_weight_theme_boost", "SCORE_WEIGHTS_THEME_BOOST", 0.06),
        "sentiment": pf("score_weight_sentiment", "SCORE_WEIGHTS_SENTIMENT", 0.06),
        "volatility_penalty": pf("score_weight_volatility_penalty", "SCORE_WEIGHTS_VOLATILITY_PENALTY", 0.10),
        "gap_penalty": pf("score_weight_gap_penalty", "SCORE_WEIGHTS_GAP_PENALTY", 0.07),
        "open_order_penalty": pf("score_weight_open_order_penalty", "SCORE_WEIGHTS_OPEN_ORDER_PENALTY", 0.04),
    }


def _candidate_quote_metrics(
    symbol: str,
    *,
    skill_quotes: Dict[str, Dict[str, Any]],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    quote = skill_quotes.get(_norm_symbol(symbol), {})
    if not isinstance(quote, dict):
        quote = {}
    fallback = state.get("mock_candidate_metrics")
    if isinstance(fallback, dict) and isinstance(fallback.get(symbol), dict):
        merged = dict(fallback.get(symbol) or {})
        merged.update(quote)
        quote = merged

    volume = _to_float(quote.get("volume") or quote.get("vol") or quote.get("trading_volume"))
    trading_value = _to_float(
        quote.get("value")
        or quote.get("trading_value")
        or quote.get("trade_value")
        or quote.get("amount")
    )
    change_pct = _to_float(quote.get("change_pct") or quote.get("chg_rate") or quote.get("changeRate"))

    halted = False
    if quote.get("halted") is not None:
        halted = bool(quote.get("halted"))
    elif str(quote.get("status") or "").strip().lower() in ("halted", "suspended", "stop"):
        halted = True

    abnormal = False
    if quote.get("abnormal") is not None:
        abnormal = bool(quote.get("abnormal"))
    if str(quote.get("risk_flag") or "").strip().lower() in ("abnormal", "warning", "danger"):
        abnormal = True

    return {
        "volume": float(max(0.0, volume)),
        "trading_value": float(max(0.0, trading_value)),
        "change_pct": float(change_pct),
        "halted": bool(halted),
        "abnormal": bool(abnormal),
    }


def _reduce_candidates_by_practical_filters(
    rows: List[Any],
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    skill_quotes: Dict[str, Dict[str, Any]],
) -> Tuple[List[Any], Dict[str, Any]]:
    min_value = _resolve_min_trading_value(policy)
    min_volume = _resolve_min_volume(policy)
    exclude_halted = _resolve_exclude_halted(policy)
    before = len(rows)

    if before <= 0:
        return rows, {
            "candidate_pool_before_filter": 0,
            "candidate_pool_after_filter": 0,
            "filtered_out_count": 0,
            "min_trading_value": float(min_value),
            "min_volume": float(min_volume),
            "exclude_halted": bool(exclude_halted),
            "excluded_halted": 0,
            "excluded_illiquid": 0,
            "excluded_abnormal": 0,
            "reduction_fallback_used": False,
            "reduction_filter_applied": False,
        }

    kept: List[Any] = []
    excluded_halted = 0
    excluded_illiquid = 0
    excluded_abnormal = 0
    for row in rows:
        symbol = _norm_symbol(row.get("symbol") if isinstance(row, dict) else row)
        if not symbol:
            continue
        metrics = _candidate_quote_metrics(symbol, skill_quotes=skill_quotes, state=state)
        halted = bool(metrics.get("halted"))
        abnormal = bool(metrics.get("abnormal"))
        trading_value = _to_float(metrics.get("trading_value"))
        volume = _to_float(metrics.get("volume"))

        drop = False
        if exclude_halted and halted:
            excluded_halted += 1
            drop = True
        elif abnormal:
            excluded_abnormal += 1
            drop = True
        else:
            low_value = min_value > 0.0 and trading_value > 0.0 and trading_value < min_value
            low_volume = min_volume > 0.0 and volume > 0.0 and volume < min_volume
            if low_value or low_volume:
                excluded_illiquid += 1
                drop = True
        if not drop:
            kept.append(row)

    reduction_fallback_used = False
    if not kept:
        # If strict filter empties the pool, keep original candidates to avoid scanner NOOP collapse.
        kept = list(rows)
        reduction_fallback_used = True

    return kept, {
        "candidate_pool_before_filter": int(before),
        "candidate_pool_after_filter": int(len(kept)),
        "filtered_out_count": int(max(0, before - len(kept))),
        "min_trading_value": float(min_value),
        "min_volume": float(min_volume),
        "exclude_halted": bool(exclude_halted),
        "excluded_halted": int(excluded_halted),
        "excluded_illiquid": int(excluded_illiquid),
        "excluded_abnormal": int(excluded_abnormal),
        "reduction_fallback_used": bool(reduction_fallback_used),
        "reduction_filter_applied": bool(min_value > 0.0 or min_volume > 0.0 or exclude_halted),
    }


def _norm01(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return _clamp((float(x) - float(lo)) / (float(hi) - float(lo)), 0.0, 1.0)


def _signed01(x: float, scale: float = 1.0) -> float:
    s = max(1e-9, float(scale))
    return _clamp(float(x) / s, -1.0, 1.0)


def _build_kiwoom_candidates(
    state: Dict[str, Any],
    *,
    policy: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    candidate_limit = _resolve_candidate_limit(policy)
    top_pool = _resolve_top_candidate_pool(policy, candidate_limit=candidate_limit)
    condition_limit = _resolve_condition_limit(policy, top_pool=top_pool)
    include_change_rate = _resolve_include_change_rate(policy)
    enable_theme_filter = _resolve_enable_theme_filter(policy)

    rows, meta = build_kiwoom_candidate_rows(
        state=state,
        top_pool=top_pool,
        condition_limit=condition_limit,
        include_change_rate=include_change_rate,
        themes=_extract_themes(state),
        include_sector_candidates=True,
        include_watchlist=True,
    )
    themes = _extract_themes(state)
    theme_symbol_index = _extract_theme_symbol_index(state, policy)
    rows, filter_meta = _apply_theme_filter(
        rows,
        themes=themes,
        theme_symbol_index=theme_symbol_index,
        enable_theme_filter=enable_theme_filter,
    )
    rows = rows[:candidate_limit]
    meta_out = dict(meta)
    meta_out.update(filter_meta)
    meta_out.update(
        {
            "themes": list(themes),
            "candidate_limit": int(candidate_limit),
            "candidate_count": int(len(rows)),
            "condition_limit": int(condition_limit),
            "top_candidate_pool": int(top_pool),
            "enable_theme_filter": bool(enable_theme_filter),
        }
    )
    return rows, meta_out


def _resolve_scanner_candidates(state: Dict[str, Any], policy: Dict[str, Any]) -> Tuple[List[Any], Dict[str, Any]]:
    source = _resolve_candidate_source(state, policy)
    strategist_candidates = _extract_strategist_candidates(state)

    if source == "strategist":
        return strategist_candidates, {
            "candidate_source": "strategist",
            "candidate_count": int(len(strategist_candidates)),
            "fallback_used": False,
        }

    kiwoom_rows, kiwoom_meta = _build_kiwoom_candidates(state, policy=policy)
    if kiwoom_rows:
        return kiwoom_rows, dict(kiwoom_meta)

    if strategist_candidates:
        fallback_meta = dict(kiwoom_meta)
        fallback_meta.update(
            {
                "candidate_source": "strategist_fallback",
                "candidate_count": int(len(strategist_candidates)),
                "fallback_used": True,
                "fallback_reason": "kiwoom_candidate_pool_empty",
            }
        )
        return strategist_candidates, fallback_meta

    if source == "auto":
        return strategist_candidates, {
            "candidate_source": "auto",
            "candidate_count": int(len(strategist_candidates)),
            "fallback_used": False,
            "fallback_reason": "no_kiwoom_and_no_strategist_candidates",
        }

    empty_meta = dict(kiwoom_meta)
    empty_meta.update(
        {
            "candidate_source": "kiwoom",
            "candidate_count": 0,
            "fallback_used": False,
            "fallback_reason": "kiwoom_candidate_pool_empty",
        }
    )
    return [], empty_meta


def scanner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Graph node: Scanner (Data + feature extraction).

    M17-3 contract (additive):
      - Builds candidate pool from Kiwoom market data (default)
      - Applies strategist theme hints when mapping data exists
      - Falls back to strategist candidates when Kiwoom pool is empty
      - Computes per-candidate features/risk/confidence
      - Selects exactly 1 candidate into state['selected'] (or None)

    Writes:
      - state['scan_results'] : list[dict]
      - state['selected'] : dict | None
      - state['risk'] : dict (risk_score/confidence for selected)

    Test hooks:
      - state['mock_scan_results'] : {symbol: {score, risk_score, confidence, features?}}
        If present, Scanner will use these values instead of generating.
    """
    # M18-4: sentiment-aware scoring (offline-friendly)
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    candidates, pool_meta = _resolve_scanner_candidates(state, policy)

    mock: Optional[Mapping[str, Any]] = state.get("mock_scan_results")  # for tests
    mock_by_sym: Dict[str, Any] = {}
    if isinstance(mock, Mapping):
        for k, v in mock.items():
            mock_by_sym[_norm_symbol(k)] = v

    w = _get_scanner_weights(policy)
    practical_w = _resolve_scanner_score_weights(policy)
    gs = _get_global_sentiment_score(state)
    gs_signal = _get_global_sentiment_signal(state)
    news_by_sym = _get_news_sentiment_map(state)
    news_signal_by_sym = _get_news_sentiment_signal_map(state)
    skill_quotes, quote_meta = _extract_skill_quotes(state)
    skill_order_counts, skill_order_rows, order_meta = _extract_account_open_order_counts(state)
    feature_map, feature_source, feature_errors = _extract_feature_engine_map(state)

    # Practical pool reduction before scoring.
    reduced_candidates, reduction_meta = _reduce_candidates_by_practical_filters(
        candidates,
        state=state,
        policy=policy,
        skill_quotes=skill_quotes,
    )
    candidates = list(reduced_candidates)
    pool_meta = dict(pool_meta)
    pool_meta.update(dict(reduction_meta))
    state["scanner_candidate_pool"] = dict(pool_meta)
    practical_enabled = str(pool_meta.get("candidate_source") or "").strip().lower() == "kiwoom_market_data"
    if policy.get("enable_practical_scoring") is not None:
        practical_enabled = _is_trueish(policy.get("enable_practical_scoring"))
    practical_scale = 1.0 if practical_enabled else 0.0

    scan_results: List[Dict[str, Any]] = []

    for item in candidates:
        candidate_meta: Dict[str, Any] = {}
        if isinstance(item, dict):
            symbol = _norm_symbol(item.get("symbol"))
            candidate_meta = dict(item)
        else:
            symbol = _norm_symbol(item)

        if not symbol:
            continue

        if symbol in mock_by_sym:
            row = dict(mock_by_sym[symbol])
            row.setdefault("symbol", symbol)
        else:
            base = _stable_unit_hash(symbol)
            # Simple deterministic defaults (placeholder)
            score = 1.0 - base  # higher is better
            risk_score = base  # higher is riskier
            confidence = max(0.0, min(1.0, 0.9 - base * 0.4))
            row = {
                "symbol": symbol,
                "score": float(score),
                "risk_score": float(risk_score),
                "confidence": float(confidence),
                "features": {
                    "unit_hash": float(base),
                },
            }

        # ---- Practical scoring model (additive, deterministic) ----
        base_score = _to_float(row.get("score") or 0.0)
        base_risk = _to_float(row.get("risk_score") or 0.35)
        base_conf = _to_float(row.get("confidence") or 0.55)
        candidate_rank_score = _clamp(_to_float(candidate_meta.get("rank_score") or 0.0), -1.0, 1.0)
        candidate_universe_score = _clamp(_to_float(candidate_meta.get("universe_score") or 0.0), 0.0, 10.0)
        source_scores = dict(candidate_meta.get("source_scores") or {})

        news_s = _to_float(news_by_sym.get(symbol, news_by_sym.get(_norm_symbol(symbol), 0.0)))
        news_sig = (
            news_signal_by_sym.get(symbol)
            if isinstance(news_signal_by_sym.get(symbol), dict)
            else news_signal_by_sym.get(_norm_symbol(symbol), {})
        )
        metrics = _candidate_quote_metrics(symbol, skill_quotes=skill_quotes, state=state)
        quote = skill_quotes.get(_norm_symbol(symbol), {}) if isinstance(skill_quotes.get(_norm_symbol(symbol)), dict) else {}
        quote_price = quote.get("price")
        if quote_price is None:
            quote_price = quote.get("cur")
        quote_price_num = _to_float(quote_price) if quote_price is not None else None
        open_orders = int(skill_order_counts.get(_norm_symbol(symbol), 0))
        order_penalty = min(open_orders, 3)

        feature_row = feature_map.get(_norm_symbol(symbol), {})
        if not isinstance(feature_row, dict):
            feature_row = {}
        feature_signal = _clamp(_to_float(feature_row.get("signal_score") or 0.0), -1.0, 1.0)
        feature_regime = str(feature_row.get("regime") or "").strip().lower()
        return20 = _to_float(feature_row.get("return20"))
        ma20_gap = _to_float(feature_row.get("ma20_gap"))
        trend_strength = _to_float(feature_row.get("trend_strength"))
        volume_spike20 = _to_float(feature_row.get("volume_spike20"))
        volatility20 = _to_float(feature_row.get("volatility20"))
        gap_pct = abs(_to_float(feature_row.get("gap_pct")))

        trading_value_component = _norm01(_to_float(source_scores.get("top_value")), 0.0, 2.0)
        momentum_raw = (0.65 * _signed01(return20, 0.10)) + (0.35 * _signed01(ma20_gap, 0.03))
        momentum_component = max(0.0, momentum_raw)
        trend_raw = trend_strength if trend_strength != 0.0 else feature_signal
        trend_component = max(0.0, _signed01(trend_raw, 1.0))
        volume_surge_component = _norm01(volume_spike20, 1.0, 3.0)
        intraday_strength_component = max(0.0, _signed01(_to_float(metrics.get("change_pct")), 5.0))

        theme_matched_symbols = set(_norm_symbol(x) for x in list(pool_meta.get("theme_matched_symbols") or []))
        theme_boost_component = 1.0 if (symbol in theme_matched_symbols and len(theme_matched_symbols) > 0) else 0.0
        sentiment_component = max(0.0, (0.7 * news_s) + (0.3 * gs))

        volatility_penalty = _norm01(volatility20, 0.03, 0.08)
        gap_penalty = _norm01(gap_pct, 0.03, 0.10)
        open_order_penalty = _norm01(float(order_penalty), 0.0, 3.0)

        positive_score = (
            practical_w["trading_value"] * trading_value_component
            + practical_w["momentum"] * momentum_component
            + practical_w["trend"] * trend_component
            + practical_w["volume_surge"] * volume_surge_component
            + practical_w["intraday_strength"] * intraday_strength_component
            + practical_w["theme_boost"] * theme_boost_component
            + practical_w["sentiment"] * sentiment_component
            + (0.06 * max(0.0, candidate_rank_score))
            + (0.02 * _norm01(candidate_universe_score, 0.0, 10.0))
        ) * practical_scale
        risk_penalty_score = (
            practical_w["volatility_penalty"] * volatility_penalty
            + practical_w["gap_penalty"] * gap_penalty
            + practical_w["open_order_penalty"] * open_order_penalty
        ) * practical_scale

        # Keep backward compatibility with previous additive sentiment/risk knobs.
        legacy_adjust = (
            w["weight_news"] * news_s
            + w["weight_global"] * gs
            + w["feature_score_weight"] * feature_signal
            - (0.03 * open_order_penalty)
        )
        rank_bonus = 0.01 * max(0.0, candidate_rank_score)
        score_total = base_score + positive_score + legacy_adjust - risk_penalty_score + rank_bonus

        neg_news = max(-news_s, 0.0)
        neg_global = max(-gs, 0.0)
        feature_risk = w["feature_risk_penalty"] * max(-feature_signal, 0.0)
        if feature_regime == "high_volatility":
            feature_risk += w["high_vol_risk_penalty"]
        adj_risk = (
            base_risk
            + w["risk_news_penalty"] * neg_news
            + w["risk_global_penalty"] * neg_global
            + feature_risk
            + (0.35 * volatility_penalty * practical_scale)
            + (0.25 * gap_penalty * practical_scale)
            + (0.10 * open_order_penalty)
        )
        adj_conf = _clamp(
            base_conf
            + w["confidence_news_boost"] * max(news_s, 0.0)
            + 0.15 * (positive_score - risk_penalty_score)
            - 0.08 * open_order_penalty,
            0.0,
            1.0,
        )

        score_breakdown = {
            "trading_value": float(practical_w["trading_value"] * trading_value_component),
            "momentum": float(practical_w["momentum"] * momentum_component),
            "trend": float(practical_w["trend"] * trend_component),
            "volume_surge": float(practical_w["volume_surge"] * volume_surge_component),
            "intraday_strength": float(practical_w["intraday_strength"] * intraday_strength_component),
            "theme_boost": float(practical_w["theme_boost"] * theme_boost_component),
            "sentiment": float(practical_w["sentiment"] * sentiment_component),
            "risk_penalty": float(-risk_penalty_score),
            "rank_bonus": float(rank_bonus),
        }

        row["score"] = float(score_total)
        row["score_total"] = float(score_total)
        row["score_breakdown"] = dict(score_breakdown)
        row["risk_score"] = float(_clamp(adj_risk, 0.0, 1.0))
        row["confidence"] = float(adj_conf)
        row["why"] = str(candidate_meta.get("why") or row.get("why") or "")
        row["candidate"] = {
            "source_why": str(candidate_meta.get("why") or ""),
            "sources": list(candidate_meta.get("sources") or []),
            "rank_score": float(candidate_rank_score),
            "universe_score": float(candidate_universe_score),
            "source_scores": dict(candidate_meta.get("source_scores") or {}),
            "source_count": int(candidate_meta.get("source_count") or len(list(candidate_meta.get("sources") or []))),
        }
        row.setdefault("features", {})
        if isinstance(row.get("features"), dict):
            row["features"].update(
                {
                    "skill_quote_price": quote_price_num,
                    "skill_open_orders": open_orders,
                    "engine_rsi14": feature_row.get("rsi14"),
                    "engine_ma20_gap": feature_row.get("ma20_gap"),
                    "engine_ma60": feature_row.get("ma60"),
                    "engine_ma120": feature_row.get("ma120"),
                    "engine_adx14": feature_row.get("adx14"),
                    "engine_trend_strength": feature_row.get("trend_strength"),
                    "engine_atr14": feature_row.get("atr14"),
                    "engine_volume_spike20": feature_row.get("volume_spike20"),
                    "engine_volatility20": feature_row.get("volatility20"),
                    "engine_realized_volatility": feature_row.get("realized_volatility"),
                    "engine_vwap_distance": feature_row.get("vwap_distance"),
                    "engine_rolling_drawdown20": feature_row.get("rolling_drawdown20"),
                    "engine_sector_relative_strength": feature_row.get("sector_relative_strength"),
                    "engine_cross_section_rank": feature_row.get("cross_section_rank"),
                    "engine_regime": feature_row.get("regime"),
                    "engine_signal_score": feature_signal,
                    "intraday_change_pct": _to_float(metrics.get("change_pct")),
                    "quote_trading_value": _to_float(metrics.get("trading_value")),
                    "quote_volume": _to_float(metrics.get("volume")),
                }
            )
        row.setdefault("components", {})
        if isinstance(row.get("components"), dict):
            row["components"].update(
                {
                    "base_score": base_score,
                    "base_risk": base_risk,
                    "base_confidence": base_conf,
                    "news_sentiment": news_s,
                    "global_sentiment": gs,
                    "weight_news": w["weight_news"],
                    "weight_global": w["weight_global"],
                    "risk_news_penalty": w["risk_news_penalty"],
                    "risk_global_penalty": w["risk_global_penalty"],
                    "feature_signal": feature_signal,
                    "feature_regime": feature_regime,
                    "feature_score_weight": w["feature_score_weight"],
                    "feature_risk_penalty": w["feature_risk_penalty"],
                    "high_vol_risk_penalty": w["high_vol_risk_penalty"],
                    "practical_positive_score": float(positive_score),
                    "practical_risk_penalty_score": float(risk_penalty_score),
                    "skill_open_orders": open_orders,
                    "candidate_rank_score": candidate_rank_score,
                    "candidate_universe_score": candidate_universe_score,
                    "trading_value_component": trading_value_component,
                    "momentum_component": momentum_component,
                    "trend_component": trend_component,
                    "volume_surge_component": volume_surge_component,
                    "intraday_strength_component": intraday_strength_component,
                    "theme_boost_component": theme_boost_component,
                    "sentiment_component": sentiment_component,
                    "volatility_penalty_component": volatility_penalty,
                    "gap_penalty_component": gap_penalty,
                    "open_order_penalty_component": open_order_penalty,
                    "news_sentiment_status": str(news_sig.get("status") or "fallback"),
                    "news_sentiment_source": str(news_sig.get("source") or ""),
                    "news_sentiment_reason": str(news_sig.get("reason") or ""),
                    "global_sentiment_status": str(gs_signal.get("status") or "fallback"),
                    "global_sentiment_source": str(gs_signal.get("source") or ""),
                    "global_sentiment_reason": str(gs_signal.get("reason") or ""),
                }
            )

        scan_results.append(row)

    # Sort by score desc, then confidence desc, then risk asc
    scan_results_sorted = sorted(
        scan_results,
        key=lambda r: (
            float(r.get("score") or 0.0),
            float(r.get("confidence") or 0.0),
            -float(r.get("risk_score") or 0.0),
        ),
        reverse=True,
    )

    selected = scan_results_sorted[0] if scan_results_sorted else None
    state["scan_results"] = scan_results_sorted
    state["ranked_candidates"] = [
        {
            "symbol": str(r.get("symbol") or ""),
            "score_total": float(r.get("score_total") if r.get("score_total") is not None else _to_float(r.get("score"))),
            "score_breakdown": dict(r.get("score_breakdown") or {}),
            "risk_score": float(_to_float(r.get("risk_score"))),
            "confidence": float(_to_float(r.get("confidence"))),
        }
        for r in scan_results_sorted
        if isinstance(r, dict)
    ]
    state["selected"] = selected
    state["top_stock"] = str(selected.get("symbol") or "") if isinstance(selected, dict) else ""
    top_score = (
        float(selected.get("score_total"))
        if isinstance(selected, dict) and selected.get("score_total") is not None
        else (
            float(selected.get("score"))
            if isinstance(selected, dict) and selected.get("score") is not None
            else None
        )
    )
    state["scanner_output"] = {
        "top_stock": state["top_stock"] or None,
        "score": (
            float(selected.get("score"))
            if isinstance(selected, dict) and selected.get("score") is not None
            else None
        ),
        "top_score": top_score,
        "risk_score": (
            float(selected.get("risk_score"))
            if isinstance(selected, dict) and selected.get("risk_score") is not None
            else None
        ),
        "confidence": (
            float(selected.get("confidence"))
            if isinstance(selected, dict) and selected.get("confidence") is not None
            else None
        ),
        "candidate_count": int(len(scan_results_sorted)),
        "candidate_pool_size": int(len(scan_results_sorted)),
        "ranked_candidates": list(state.get("ranked_candidates") or [])[:5],
        "candidate_source": str(pool_meta.get("candidate_source") or ""),
        "theme_filter_applied": bool(pool_meta.get("theme_filter_applied")),
        "score_weights": dict(practical_w),
        "source_mix": dict(pool_meta.get("pool_source_mix") or {}),
    }

    # Provide a normalized risk snapshot for Decision Node.
    if isinstance(selected, dict):
        state["risk"] = {
            "risk_score": float(selected.get("risk_score") or 0.0),
            "confidence": float(selected.get("confidence") or 0.0),
        }
    else:
        state["risk"] = {"risk_score": 0.0, "confidence": 0.0}
    fallback_reasons: List[str] = list(quote_meta.get("errors") or []) + list(order_meta.get("errors") or [])
    state["scanner_skill"] = {
        "contract_version": SKILL_CONTRACT_VERSION,
        "used": bool(skill_quotes) or bool(skill_order_counts),
        "quote_symbols": len(skill_quotes),
        "account_open_order_symbols": len(skill_order_counts),
        "account_order_rows": int(skill_order_rows),
        "quote_present": bool(quote_meta.get("present")),
        "account_orders_present": bool(order_meta.get("present")),
        "fallback": bool(fallback_reasons),
        "fallback_reasons": fallback_reasons,
        "error_count": len(fallback_reasons),
    }
    state["scanner_feature"] = {
        "used": bool(feature_map),
        "source": feature_source,
        "symbol_count": len(feature_map),
        "fallback": bool(feature_errors),
        "fallback_reasons": list(feature_errors),
        "error_count": len(feature_errors),
    }

    _log_scanner_summary(
        state,
        {
            "candidate_source": str(pool_meta.get("candidate_source") or ""),
            "candidate_pool_before_filter": int(pool_meta.get("candidate_pool_before_filter") or 0),
            "candidate_pool_after_filter": int(pool_meta.get("candidate_pool_after_filter") or len(scan_results_sorted)),
            "theme_filter_applied": bool(pool_meta.get("theme_filter_applied")),
            "top_stock": state.get("top_stock"),
            "top_score": top_score,
            "top_ranked_symbols": [str(x.get("symbol") or "") for x in list(state.get("ranked_candidates") or [])[:5]],
        },
    )

    return state
