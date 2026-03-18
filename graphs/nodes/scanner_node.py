from __future__ import annotations

"""Canonical Scanner node for integrated runtime.

Role boundary:
- builds/reduces/ranks candidate pool (Kiwoom-first, strategist-guided)
- selects final Top-1 candidate for monitor stage within strategist frame
- does not create execution calls
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from graphs.nodes.skill_contracts import (
    CONTRACT_VERSION as SKILL_CONTRACT_VERSION,
    extract_account_orders_rows,
    extract_market_quotes,
    norm_symbol,
)
from libs.research.evidence_ledger import record_decision_bridge, record_raw_input
from libs.runtime.canonical_artifacts import write_scanner_artifact
from libs.runtime.decision_trace import append_decision_trace
from libs.strategies.candidates.kiwoom_candidate_provider import build_kiwoom_candidate_rows
from libs.strategies.candidates.fallback_pool import is_static_fallback_pool
from libs.runtime.feature_engine import build_feature_map
from libs.runtime.scanner_feature_hydration import hydrate_scanner_feature_map
from libs.strategies.contracts import coerce_strategist_output


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


def _resolve_scanner_repeat_guard_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    raw_policy = policy.get("scanner_repeat_guard") if isinstance(policy.get("scanner_repeat_guard"), dict) else {}
    lookback_sec = _to_int(
        raw_policy.get("lookback_sec", os.getenv("SCANNER_REPEAT_LOOKBACK_SEC", "1800")),
        1800,
    )
    per_hit_penalty = _to_float(
        raw_policy.get("per_hit_penalty", os.getenv("SCANNER_REPEAT_SYMBOL_PENALTY", "0.06"))
    )
    recent_trade_penalty = _to_float(
        raw_policy.get("recent_trade_penalty", os.getenv("SCANNER_RECENT_TRADE_SYMBOL_PENALTY", "0.10"))
    )
    trade_lookback_sec = _to_int(
        raw_policy.get("trade_lookback_sec", os.getenv("SCANNER_RECENT_TRADE_LOOKBACK_SEC", "5400")),
        5400,
    )
    max_penalty = _to_float(
        raw_policy.get("max_penalty", os.getenv("SCANNER_REPEAT_SYMBOL_MAX_PENALTY", "0.40"))
    )
    streak_threshold = _to_int(
        raw_policy.get("streak_threshold", os.getenv("SCANNER_REPEAT_STREAK_THRESHOLD", "3")),
        3,
    )
    streak_penalty = _to_float(
        raw_policy.get("streak_penalty", os.getenv("SCANNER_REPEAT_STREAK_PENALTY", "0.12"))
    )
    history_limit = _to_int(
        raw_policy.get("history_limit", os.getenv("SCANNER_REPEAT_HISTORY_LIMIT", "40")),
        40,
    )
    return {
        "lookback_sec": max(0, int(lookback_sec)),
        "per_hit_penalty": max(0.0, float(per_hit_penalty)),
        "recent_trade_penalty": max(0.0, float(recent_trade_penalty)),
        "trade_lookback_sec": max(0, int(trade_lookback_sec)),
        "max_penalty": max(0.0, float(max_penalty)),
        "streak_threshold": max(2, int(streak_threshold)),
        "streak_penalty": max(0.0, float(streak_penalty)),
        "history_limit": max(5, int(history_limit)),
    }


def _scanner_recent_selection_history(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    rows = persisted.get("recent_scanner_selected")
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = _norm_symbol(row.get("symbol"))
        epoch = _to_int(row.get("epoch"), 0)
        if sym and epoch > 0:
            out.append({"symbol": sym, "epoch": epoch})
    return out


def _resolve_now_epoch(state: Dict[str, Any]) -> int:
    for key in ("now_epoch", "ts_epoch", "epoch"):
        value = _to_int(state.get(key), 0)
        if value > 0:
            return value
    return int(time.time())


def _repeat_symbol_penalty(
    state: Dict[str, Any],
    *,
    symbol: str,
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    cfg = _resolve_scanner_repeat_guard_policy(policy)
    now_epoch = _resolve_now_epoch(state)
    history = _scanner_recent_selection_history(state)
    sel = _norm_symbol(symbol)
    repeat_count = 0
    streak_count = 0
    if cfg["lookback_sec"] > 0 and sel:
        cutoff = max(0, now_epoch - cfg["lookback_sec"])
        for row in history:
            if row.get("symbol") == sel and _to_int(row.get("epoch"), 0) >= cutoff:
                repeat_count += 1
        for row in reversed(history):
            if _to_int(row.get("epoch"), 0) < cutoff:
                break
            if row.get("symbol") != sel:
                break
            streak_count += 1

    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    last_trade_symbol = _norm_symbol(persisted.get("last_trade_symbol"))
    last_trade_epoch = _to_int(persisted.get("last_trade_epoch"), 0)
    recent_trade_same_symbol = False
    if (
        sel
        and last_trade_symbol == sel
        and last_trade_epoch > 0
        and cfg["trade_lookback_sec"] > 0
        and (now_epoch - last_trade_epoch) <= cfg["trade_lookback_sec"]
    ):
        recent_trade_same_symbol = True

    streak_extra = cfg["streak_penalty"] if streak_count >= cfg["streak_threshold"] else 0.0
    penalty = min(
        cfg["max_penalty"],
        (repeat_count * cfg["per_hit_penalty"])
        + streak_extra
        + (cfg["recent_trade_penalty"] if recent_trade_same_symbol else 0.0),
    )
    return {
        "penalty": float(max(0.0, penalty)),
        "repeat_count": int(repeat_count),
        "streak_count": int(streak_count),
        "recent_trade_same_symbol": bool(recent_trade_same_symbol),
        "now_epoch": int(now_epoch),
        "history_count": int(len(history)),
        "config": cfg,
    }


def _remember_selected_symbol(state: Dict[str, Any], selected_symbol: str, *, now_epoch: int, policy: Dict[str, Any]) -> None:
    symbol = _norm_symbol(selected_symbol)
    if not symbol:
        return
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    state["persisted_state"] = persisted
    cfg = _resolve_scanner_repeat_guard_policy(policy)
    history = _scanner_recent_selection_history(state)
    history.append({"symbol": symbol, "epoch": int(now_epoch)})
    if cfg["lookback_sec"] > 0:
        cutoff = max(0, int(now_epoch) - int(cfg["lookback_sec"]) * 2)
        history = [row for row in history if _to_int(row.get("epoch"), 0) >= cutoff]
    if len(history) > cfg["history_limit"]:
        history = history[-cfg["history_limit"] :]
    persisted["recent_scanner_selected"] = history


def _make_event_logger(state: Dict[str, Any]) -> Any:
    injected = state.get("event_logger")
    if injected is not None and hasattr(injected, "log"):
        return injected
    from libs.core.event_logger import EventLogger, resolve_event_log_path

    return EventLogger(log_path=resolve_event_log_path())


def _emit_scanner_event(
    state: Dict[str, Any],
    *,
    name: str,
    payload: Dict[str, Any],
    level: str = "info",
    symbol: str = "",
) -> None:
    try:
        logger = _make_event_logger(state)
        from libs.core.event_logger import log_state_event

        log_state_event(
            logger,
            state,
            stage="scanner",
            event=name,
            event_name=f"scanner.{name}",
            payload=dict(payload or {}),
            level=level,
            agent="scanner",
            symbol=str(symbol or ""),
        )
    except Exception:
        return


def _compact_selected_snapshot(selected: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(selected, dict):
        return {}
    candidate = selected.get("candidate") if isinstance(selected.get("candidate"), dict) else {}
    features = selected.get("features") if isinstance(selected.get("features"), dict) else {}
    components = selected.get("components") if isinstance(selected.get("components"), dict) else {}
    return {
        "symbol": str(selected.get("symbol") or ""),
        "why": str(selected.get("why") or ""),
        "sources": list(candidate.get("sources") or [])[:8],
        "source_scores": dict(candidate.get("source_scores") or {}),
        "rank_score": _to_float(candidate.get("rank_score") or 0.0),
        "universe_score": _to_float(candidate.get("universe_score") or 0.0),
        "score_total": _to_float(selected.get("score_total") or selected.get("score") or 0.0),
        "risk_score": _to_float(selected.get("risk_score") or 0.0),
        "confidence": _to_float(selected.get("confidence") or 0.0),
        "score_breakdown": dict(selected.get("score_breakdown") or {}),
        "feature_snapshot": {
            "quote_trading_value": features.get("quote_trading_value"),
            "quote_volume": features.get("quote_volume"),
            "intraday_change_pct": features.get("intraday_change_pct"),
            "skill_quote_price": features.get("skill_quote_price"),
            "engine_ma20_gap": features.get("engine_ma20_gap"),
            "engine_ma60": features.get("engine_ma60"),
            "engine_ma120": features.get("engine_ma120"),
            "engine_adx14": features.get("engine_adx14"),
            "engine_trend_strength": features.get("engine_trend_strength"),
            "engine_volume_spike20": features.get("engine_volume_spike20"),
            "engine_volatility20": features.get("engine_volatility20"),
            "engine_vwap_distance": features.get("engine_vwap_distance"),
            "engine_sector_relative_strength": features.get("engine_sector_relative_strength"),
            "engine_cross_section_rank": features.get("engine_cross_section_rank"),
            "engine_regime": features.get("engine_regime"),
            "engine_signal_score": features.get("engine_signal_score"),
        },
        "component_snapshot": {
            "news_sentiment": components.get("news_sentiment"),
            "global_sentiment": components.get("global_sentiment"),
            "trading_value_component": components.get("trading_value_component"),
            "momentum_component": components.get("momentum_component"),
            "trend_component": components.get("trend_component"),
            "volume_surge_component": components.get("volume_surge_component"),
            "intraday_strength_component": components.get("intraday_strength_component"),
            "theme_boost_component": components.get("theme_boost_component"),
            "sentiment_component": components.get("sentiment_component"),
            "volatility_penalty_component": components.get("volatility_penalty_component"),
            "gap_penalty_component": components.get("gap_penalty_component"),
            "avoid_theme_penalty_component": components.get("avoid_theme_penalty_component"),
        },
    }


def _feature_coverage_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    features = row.get("features") if isinstance(row.get("features"), dict) else {}
    if not isinstance(features, dict):
        return {"present": 0, "total": 0}
    interesting_keys = [
        "engine_ma20_gap",
        "engine_ma60",
        "engine_ma120",
        "engine_adx14",
        "engine_trend_strength",
        "engine_atr14",
        "engine_volume_spike20",
        "engine_volatility20",
        "engine_vwap_distance",
        "engine_sector_relative_strength",
        "engine_cross_section_rank",
        "engine_regime",
        "engine_signal_score",
    ]
    present = sum(1 for key in interesting_keys if features.get(key) not in (None, ""))
    return {"present": int(present), "total": int(len(interesting_keys))}


def _compact_feature_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    features = row.get("features") if isinstance(row.get("features"), dict) else {}
    if not isinstance(features, dict):
        return {}
    return {
        "skill_quote_price": features.get("skill_quote_price"),
        "quote_trading_value": features.get("quote_trading_value"),
        "quote_volume": features.get("quote_volume"),
        "intraday_change_pct": features.get("intraday_change_pct"),
        "engine_ma20_gap": features.get("engine_ma20_gap"),
        "engine_adx14": features.get("engine_adx14"),
        "engine_trend_strength": features.get("engine_trend_strength"),
        "engine_volume_spike20": features.get("engine_volume_spike20"),
        "engine_volatility20": features.get("engine_volatility20"),
        "engine_vwap_distance": features.get("engine_vwap_distance"),
        "engine_sector_relative_strength": features.get("engine_sector_relative_strength"),
        "engine_cross_section_rank": features.get("engine_cross_section_rank"),
        "engine_regime": features.get("engine_regime"),
        "engine_signal_score": features.get("engine_signal_score"),
    }


def _candidate_theme_match(row: Dict[str, Any]) -> Any:
    candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
    components = row.get("components") if isinstance(row.get("components"), dict) else {}
    sources = [str(x or "").strip() for x in list(candidate.get("sources") or []) if str(x or "").strip()]
    if "sector_theme" in sources:
        return True
    return bool(_to_float(components.get("theme_boost_component")) > 0.0)


def _ranking_table_rows(rows: List[Dict[str, Any]], *, max_rows: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(list(rows or [])[: max(0, int(max_rows))], start=1):
        candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
        out.append(
            {
                "rank": int(idx),
                "symbol": str(row.get("symbol") or ""),
                "score_total": float(_to_float(row.get("score_total") or row.get("score"))),
                "score_breakdown": dict(row.get("score_breakdown") or {}),
                "source_scores": dict(candidate.get("source_scores") or {}),
                "risk_score": float(_to_float(row.get("risk_score"))),
                "confidence": float(_to_float(row.get("confidence"))),
                "theme_match": _candidate_theme_match(row),
                "feature_coverage": _feature_coverage_summary(row),
                "status": "selected" if idx == 1 else "runner_up",
                "exclusion_reason": str(row.get("exclusion_reason") or ""),
                "compact_feature_snapshot": _compact_feature_snapshot(row),
            }
        )
    return out


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


def _is_live_equity_symbol(symbol: str) -> bool:
    sym = _norm_symbol(symbol)
    return bool(sym) and sym.isdigit() and len(sym) == 6


def _should_auto_hydrate_scanner_skills(state: Dict[str, Any], candidates: List[Any]) -> bool:
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    explicit = policy.get("enable_scanner_skill_hydration")
    if explicit is not None:
        enabled = _is_trueish(explicit)
    else:
        env_value = os.getenv("SCANNER_AUTO_SKILL_HYDRATION", "")
        if env_value:
            enabled = _is_trueish(env_value)
        else:
            enabled = not bool(os.getenv("PYTEST_CURRENT_TEST"))
    if not enabled:
        return False

    if state.get("skill_runner") is not None or callable(state.get("skill_runner_factory")):
        return True
    if _is_trueish(state.get("auto_skill_runner")) or _is_trueish(os.getenv("M22_AUTO_SKILL_RUNNER", "")):
        return True

    candidate_symbols: List[str] = []
    for item in candidates:
        if isinstance(item, dict):
            sym = _norm_symbol(item.get("symbol"))
        else:
            sym = _norm_symbol(item)
        if sym:
            candidate_symbols.append(sym)
    return any(_is_live_equity_symbol(sym) for sym in candidate_symbols)


def _maybe_hydrate_scanner_skill_results(state: Dict[str, Any], candidates: List[Any]) -> Dict[str, Any]:
    existing_quotes, _quote_meta = _extract_skill_quotes(state)
    existing_order_counts, existing_order_rows, _order_meta = _extract_account_open_order_counts(state)
    if existing_quotes or existing_order_counts or existing_order_rows > 0:
        return state
    if not _should_auto_hydrate_scanner_skills(state, candidates):
        return state

    try:
        from graphs.nodes.hydrate_skill_results_node import hydrate_skill_results_node
    except Exception:
        return state

    injected_auto = False
    previous_auto = state.get("auto_skill_runner")
    if (
        state.get("skill_runner") is None
        and not callable(state.get("skill_runner_factory"))
        and not _is_trueish(state.get("auto_skill_runner"))
    ):
        state["auto_skill_runner"] = True
        injected_auto = True
    try:
        return hydrate_skill_results_node(state)
    except Exception:
        return state
    finally:
        if injected_auto:
            if previous_auto is None:
                state.pop("auto_skill_runner", None)
            else:
                state["auto_skill_runner"] = previous_auto


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


def _extract_avoid_themes(state: Dict[str, Any]) -> List[str]:
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

    add_many(state.get("avoid_themes"))
    strategist_output = state.get("strategist_output")
    if isinstance(strategist_output, dict):
        add_many(strategist_output.get("avoid_themes"))
    scanner_guidance = state.get("scanner_guidance")
    if isinstance(scanner_guidance, dict):
        add_many(scanner_guidance.get("avoid_themes"))
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


def _apply_avoid_theme_filter(
    rows: List[Dict[str, Any]],
    *,
    avoid_themes: List[str],
    theme_symbol_index: Dict[str, set[str]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not rows:
        return rows, {"avoid_filter_applied": False, "avoid_filter_reason": "no_rows", "avoid_theme_count": 0}
    if not avoid_themes:
        return rows, {"avoid_filter_applied": False, "avoid_filter_reason": "no_avoid_themes", "avoid_theme_count": 0}
    if not theme_symbol_index:
        return rows, {"avoid_filter_applied": False, "avoid_filter_reason": "theme_index_missing", "avoid_theme_count": 0}

    excluded_symbols: set[str] = set()
    matched = 0
    for t in avoid_themes:
        key = str(t or "").strip().lower()
        syms = theme_symbol_index.get(key) or set()
        if syms:
            matched += 1
            excluded_symbols.update(set(syms))

    if not excluded_symbols:
        return rows, {
            "avoid_filter_applied": False,
            "avoid_filter_reason": "avoid_theme_not_mapped",
            "avoid_theme_count": int(matched),
            "avoid_matched_symbols": [],
        }

    filtered = [r for r in rows if _norm_symbol(r.get("symbol")) not in excluded_symbols]
    return filtered, {
        "avoid_filter_applied": True,
        "avoid_filter_reason": "",
        "avoid_theme_count": int(matched),
        "avoid_matched_symbols": sorted(list(excluded_symbols)),
        "avoid_filtered_out_count": int(max(0, len(rows) - len(filtered))),
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


def _resolve_block_static_fallback(policy: Dict[str, Any]) -> bool:
    raw = policy.get("block_static_fallback_when_kiwoom_empty")
    if raw in (None, ""):
        raw = os.getenv("BLOCK_STATIC_FALLBACK_WHEN_KIWOOM_EMPTY", "true")
    return _is_trueish(raw)


def _resolve_strict_kiwoom_only(policy: Dict[str, Any]) -> bool:
    raw = policy.get("strict_kiwoom_candidates_only")
    if raw in (None, ""):
        raw = os.getenv("STRICT_KIWOOM_CANDIDATES_ONLY", "false")
    return _is_trueish(raw)


def _resolve_candidate_limit(policy: Dict[str, Any]) -> int:
    raw = policy.get("candidate_k", policy.get("candidate_topk"))
    if raw not in (None, ""):
        return max(1, _to_int(raw, 10))

    # Preserve explicit TOP_N_CANDIDATES if set by operator.
    env_topn_raw = os.getenv("TOP_N_CANDIDATES")
    if env_topn_raw not in (None, ""):
        return max(1, _to_int(env_topn_raw, 10))

    # Default behavior: use full candidate pool size instead of fixed 5.
    env_pool = _to_int(os.getenv("TOP_CANDIDATE_POOL", "30"), 30)
    return max(1, env_pool)


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


def _extract_scanner_guidance(state: Dict[str, Any]) -> Dict[str, Any]:
    strategist_output_raw = state.get("strategist_output")
    strategist_output = coerce_strategist_output(strategist_output_raw) if isinstance(strategist_output_raw, dict) else {}
    strategy_policy = (
        dict(strategist_output.get("strategy_policy") or {})
        if isinstance(strategist_output.get("strategy_policy"), dict)
        else {}
    )
    scanner_policy = (
        dict(strategy_policy.get("scanner_policy") or {})
        if isinstance(strategy_policy.get("scanner_policy"), dict)
        else {}
    )
    raw_bias = strategist_output.get("scanner_bias")
    if isinstance(raw_bias, dict):
        raw_bias = str(raw_bias.get("style") or "")
    base = {
        "themes": list(strategist_output.get("themes") or []),
        "avoid_themes": list(strategist_output.get("avoid_themes") or []),
        "playbook": str(strategist_output.get("playbook") or ""),
        "scanner_priority": list(scanner_policy.get("priority_tilts") or strategist_output.get("scanner_priority") or []),
        "scanner_source_policy": dict(
            scanner_policy.get("candidate_sources")
            if isinstance(scanner_policy.get("candidate_sources"), dict)
            else strategist_output.get("scanner_source_policy")
            or {}
        ),
        "scanner_bias": str(raw_bias or "").strip().lower(),
        "trade_aggressiveness": strategist_output.get("trade_aggressiveness"),
        "risk_tone": strategist_output.get("risk_tone"),
        "score_weights": dict(scanner_policy.get("score_weights") or {}),
        "filters": dict(scanner_policy.get("filters") or {}),
        "ranking_rules": dict(scanner_policy.get("ranking_rules") or {}),
    }

    # Backward-compatible override hook; canonical source remains strategist_output.
    guidance = state.get("scanner_guidance")
    if isinstance(guidance, dict):
        out = dict(base)
        for key in (
            "themes",
            "avoid_themes",
            "playbook",
            "scanner_priority",
            "scanner_source_policy",
            "scanner_bias",
            "trade_aggressiveness",
            "risk_tone",
            "score_weights",
            "filters",
            "ranking_rules",
        ):
            if guidance.get(key) not in (None, ""):
                out[key] = guidance.get(key)
        raw_override_bias = out.get("scanner_bias")
        if isinstance(raw_override_bias, dict):
            out["scanner_bias"] = str(raw_override_bias.get("style") or "")
        return out

    return base


def _normalize_scanner_source_policy(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: Dict[str, Any] = {}
    for key in (
        "include_top_value",
        "include_top_volume",
        "include_change_rate",
        "include_condition_search",
        "include_sector_candidates",
        "include_watchlist",
    ):
        if value.get(key) is not None:
            out[key] = bool(value.get(key))
    for key in ("top_candidate_pool", "condition_limit"):
        if value.get(key) not in (None, ""):
            out[key] = max(0, _to_int(value.get(key), 0))
    if isinstance(value.get("preferred_sources"), list):
        out["preferred_sources"] = [str(x).strip() for x in list(value.get("preferred_sources") or []) if str(x).strip()]
    if isinstance(value.get("source_weights"), dict):
        out["source_weights"] = {
            str(k).strip(): float(_to_float(v))
            for k, v in dict(value.get("source_weights") or {}).items()
            if str(k).strip()
        }
    if value.get("reason") not in (None, ""):
        out["reason"] = str(value.get("reason") or "")
    return out


def _normalize_priority_list(values: Any) -> List[str]:
    out: List[str] = []
    seen = set()
    if not isinstance(values, list):
        return out
    for row in values:
        s = str(row or "").strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _apply_scanner_guidance_weights(
    weights: Dict[str, float],
    *,
    playbook: str,
    scanner_bias: str,
    scanner_priority: List[str],
    trade_aggressiveness: str,
    risk_tone: str,
) -> Dict[str, float]:
    out = dict(weights or {})
    bias = str(scanner_bias or "").strip().lower()
    priority_set = set(_normalize_priority_list(scanner_priority))
    playbook_norm = str(playbook or "").strip().lower()
    aggr = str(trade_aggressiveness or "").strip().lower()
    tone = str(risk_tone or "").strip().lower()

    if bias == "large_cap":
        out["trading_value"] = float(out.get("trading_value", 0.0) * 1.10)
        out["volatility_penalty"] = float(out.get("volatility_penalty", 0.0) * 1.12)
    elif bias == "leader":
        out["trend"] = float(out.get("trend", 0.0) * 1.08)
        out["theme_boost"] = float(out.get("theme_boost", 0.0) * 1.08)
    elif bias == "momentum":
        out["momentum"] = float(out.get("momentum", 0.0) * 1.12)
        out["volume_surge"] = float(out.get("volume_surge", 0.0) * 1.08)
    elif bias == "value":
        out["trading_value"] = float(out.get("trading_value", 0.0) * 1.10)
        out["momentum"] = float(out.get("momentum", 0.0) * 0.94)

    # Priority-driven mild boosts (additive-safe, scanner remains quantitative).
    if "liquidity" in priority_set:
        out["trading_value"] = float(out.get("trading_value", 0.0) * 1.10)
    if "momentum" in priority_set or "breakout" in priority_set:
        out["momentum"] = float(out.get("momentum", 0.0) * 1.12)
    if "trend_strength" in priority_set or "trend" in priority_set:
        out["trend"] = float(out.get("trend", 0.0) * 1.10)
    if "ma_alignment" in priority_set or "moving_average_trend" in priority_set:
        out["trend"] = float(out.get("trend", 0.0) * 1.08)
    if "vwap_reclaim" in priority_set or "vwap_distance" in priority_set:
        out["intraday_strength"] = float(out.get("intraday_strength", 0.0) * 1.08)
    if "cross_section_rank" in priority_set or "relative_strength" in priority_set:
        out["trend"] = float(out.get("trend", 0.0) * 1.06)
        out["theme_boost"] = float(out.get("theme_boost", 0.0) * 1.04)
    if "volume_surge" in priority_set or "volume_confirmation" in priority_set:
        out["volume_surge"] = float(out.get("volume_surge", 0.0) * 1.08)
    if "risk_penalty" in priority_set or "drawdown_control" in priority_set:
        out["volatility_penalty"] = float(out.get("volatility_penalty", 0.0) * 1.15)
        out["gap_penalty"] = float(out.get("gap_penalty", 0.0) * 1.15)

    # Playbook guidance remains additive (Scanner still does final quantitative ranking).
    if playbook_norm == "breakout":
        out["momentum"] = float(out.get("momentum", 0.0) * 1.10)
        out["volume_surge"] = float(out.get("volume_surge", 0.0) * 1.06)
    elif playbook_norm == "pullback":
        out["trend"] = float(out.get("trend", 0.0) * 1.08)
        out["intraday_strength"] = float(out.get("intraday_strength", 0.0) * 1.05)
    elif playbook_norm == "reversal":
        out["momentum"] = float(out.get("momentum", 0.0) * 0.92)
        out["gap_penalty"] = float(out.get("gap_penalty", 0.0) * 1.10)
    elif playbook_norm == "defensive":
        out["trading_value"] = float(out.get("trading_value", 0.0) * 1.08)
        out["volatility_penalty"] = float(out.get("volatility_penalty", 0.0) * 1.12)

    # Risk tone / aggressiveness final tuning.
    if aggr == "high" and tone in ("aggressive", "normal"):
        out["momentum"] = float(out.get("momentum", 0.0) * 1.05)
        out["intraday_strength"] = float(out.get("intraday_strength", 0.0) * 1.05)
    if aggr == "low" or tone == "conservative":
        out["volatility_penalty"] = float(out.get("volatility_penalty", 0.0) * 1.20)
        out["gap_penalty"] = float(out.get("gap_penalty", 0.0) * 1.20)
        out["intraday_strength"] = float(out.get("intraday_strength", 0.0) * 0.95)
        out["momentum"] = float(out.get("momentum", 0.0) * 0.95)

    return out


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

    raw_quote = quote.get("raw") if isinstance(quote.get("raw"), dict) else {}
    raw_rows = raw_quote.get("cntr_infr") if isinstance(raw_quote.get("cntr_infr"), list) else []
    raw_row = raw_rows[0] if raw_rows and isinstance(raw_rows[0], dict) else {}
    if volume <= 0.0:
        volume = _to_float(raw_row.get("acc_trde_qty"))
    if trading_value <= 0.0:
        trading_value = _to_float(raw_row.get("acc_trde_prica"))
    if change_pct == 0.0:
        change_pct = _to_float(raw_row.get("pre_rt"))

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
    scanner_guidance = _extract_scanner_guidance(state)
    source_policy = _normalize_scanner_source_policy(scanner_guidance.get("scanner_source_policy"))
    candidate_limit = _resolve_candidate_limit(policy)
    top_pool = _resolve_top_candidate_pool(policy, candidate_limit=candidate_limit)
    if source_policy.get("top_candidate_pool"):
        top_pool = max(candidate_limit, int(source_policy.get("top_candidate_pool") or top_pool))
    condition_limit = _resolve_condition_limit(policy, top_pool=top_pool)
    if source_policy.get("condition_limit") is not None:
        condition_limit = max(0, int(source_policy.get("condition_limit") or 0))
    include_change_rate = _resolve_include_change_rate(policy)
    if source_policy.get("include_change_rate") is not None:
        include_change_rate = bool(source_policy.get("include_change_rate"))
    enable_theme_filter = _resolve_enable_theme_filter(policy)
    include_top_value = bool(source_policy.get("include_top_value", True))
    include_top_volume = bool(source_policy.get("include_top_volume", True))
    include_condition_search = bool(source_policy.get("include_condition_search", True))
    include_sector_candidates = bool(source_policy.get("include_sector_candidates", True))
    include_watchlist = bool(source_policy.get("include_watchlist", True))

    rows, meta = build_kiwoom_candidate_rows(
        state=state,
        top_pool=top_pool,
        condition_limit=condition_limit,
        include_change_rate=include_change_rate,
        include_top_value=include_top_value,
        include_top_volume=include_top_volume,
        include_condition_search=include_condition_search,
        themes=_extract_themes(state),
        include_sector_candidates=include_sector_candidates,
        include_watchlist=include_watchlist,
        source_weights=dict(source_policy.get("source_weights") or {}),
    )
    raw_kiwoom_count = int(len(rows))
    themes = _extract_themes(state)
    avoid_themes = _extract_avoid_themes(state)
    theme_symbol_index = _extract_theme_symbol_index(state, policy)
    rows, filter_meta = _apply_theme_filter(
        rows,
        themes=themes,
        theme_symbol_index=theme_symbol_index,
        enable_theme_filter=enable_theme_filter,
    )
    rows, avoid_meta = _apply_avoid_theme_filter(
        rows,
        avoid_themes=avoid_themes,
        theme_symbol_index=theme_symbol_index,
    )
    rows = rows[:candidate_limit]
    backfill_count = 0
    backfill_skipped = ""
    if raw_kiwoom_count > 0 and len(rows) < candidate_limit and not _resolve_strict_kiwoom_only(policy):
        strategist_candidates = _extract_strategist_candidates(state)
        if strategist_candidates and _resolve_block_static_fallback(policy) and is_static_fallback_pool(strategist_candidates):
            strategist_candidates = []
            backfill_skipped = "static_fallback_blocked"
        existing = {_norm_symbol(r.get("symbol")) for r in rows if isinstance(r, dict)}
        for cand in strategist_candidates:
            if isinstance(cand, dict):
                sym = _norm_symbol(cand.get("symbol"))
                why = str(cand.get("why") or "strategist_backfill")
            else:
                sym = _norm_symbol(cand)
                why = "strategist_backfill"
            if not sym or sym in existing:
                continue
            rows.append(
                {
                    "symbol": sym,
                    "why": why,
                    "sources": ["strategist_backfill"],
                    "source_scores": {"strategist_backfill": 0.10},
                    "source_count": 1,
                    "rank_score": 0.0,
                    "universe_score": 0.0,
                    "trading_value_source_score": 0.0,
                    "trading_volume_source_score": 0.0,
                }
            )
            existing.add(sym)
            backfill_count += 1
            if len(rows) >= candidate_limit:
                break
    meta_out = dict(meta)
    meta_out.update(filter_meta)
    meta_out.update(avoid_meta)
    meta_out.update(
        {
            "themes": list(themes),
            "avoid_themes": list(avoid_themes),
            "candidate_limit": int(candidate_limit),
            "candidate_count": int(len(rows)),
            "condition_limit": int(condition_limit),
            "top_candidate_pool": int(top_pool),
            "enable_theme_filter": bool(enable_theme_filter),
            "scanner_source_policy": dict(source_policy),
            "raw_kiwoom_count": int(raw_kiwoom_count),
            "backfill_used": bool(backfill_count > 0),
            "backfill_count": int(backfill_count),
            "backfill_skipped_reason": str(backfill_skipped or ""),
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

    if source == "kiwoom" and _resolve_strict_kiwoom_only(policy):
        strict_meta = dict(kiwoom_meta)
        strict_meta.update(
            {
                "candidate_source": "kiwoom",
                "candidate_count": 0,
                "fallback_used": False,
                "fallback_reason": "kiwoom_candidate_pool_empty_strict_mode",
                "strict_kiwoom_only": True,
            }
        )
        return [], strict_meta

    if strategist_candidates:
        if _resolve_block_static_fallback(policy) and is_static_fallback_pool(strategist_candidates):
            blocked_meta = dict(kiwoom_meta)
            blocked_meta.update(
                {
                    "candidate_source": "kiwoom",
                    "candidate_count": 0,
                    "fallback_used": False,
                    "fallback_reason": "kiwoom_candidate_pool_empty_static_fallback_blocked",
                    "blocked_static_fallback": True,
                }
            )
            return [], blocked_meta
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
    run_id = str(state.get("run_id") or "").strip() or "scanner-unknown"

    mock: Optional[Mapping[str, Any]] = state.get("mock_scan_results")  # for tests
    mock_by_sym: Dict[str, Any] = {}
    if isinstance(mock, Mapping):
        for k, v in mock.items():
            mock_by_sym[_norm_symbol(k)] = v

    w = _get_scanner_weights(policy)
    practical_w = _resolve_scanner_score_weights(policy)
    scanner_guidance = _extract_scanner_guidance(state)
    playbook = str(scanner_guidance.get("playbook") or "").strip().lower()
    scanner_bias = str(scanner_guidance.get("scanner_bias") or "").strip().lower()
    scanner_priority = _normalize_priority_list(scanner_guidance.get("scanner_priority"))
    trade_aggressiveness = str(scanner_guidance.get("trade_aggressiveness") or "").strip().lower()
    risk_tone = str(scanner_guidance.get("risk_tone") or "").strip().lower()
    if isinstance(scanner_guidance.get("score_weights"), dict):
        for key, value in dict(scanner_guidance.get("score_weights") or {}).items():
            if key in practical_w and value not in (None, ""):
                practical_w[key] = _to_float(value)
    practical_w = _apply_scanner_guidance_weights(
        practical_w,
        playbook=playbook,
        scanner_bias=scanner_bias,
        scanner_priority=scanner_priority,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
    )
    state = _maybe_hydrate_scanner_skill_results(state, list(candidates))
    skill_quotes, quote_meta = _extract_skill_quotes(state)
    skill_order_counts, skill_order_rows, order_meta = _extract_account_open_order_counts(state)
    feature_map, feature_source, feature_errors = hydrate_scanner_feature_map(
        state=state,
        candidates=list(candidates),
        skill_quotes=skill_quotes,
        policy=policy,
    )
    if not feature_map:
        feature_map, feature_source, feature_errors = _extract_feature_engine_map(state)
    gs = _get_global_sentiment_score(state)
    gs_signal = _get_global_sentiment_signal(state)
    news_by_sym = _get_news_sentiment_map(state)
    news_signal_by_sym = _get_news_sentiment_signal_map(state)
    try:
        raw_candidates = []
        for item in list(candidates)[:50]:
            if isinstance(item, dict):
                raw_candidates.append(
                    {
                        "symbol": _norm_symbol(item.get("symbol")),
                        "why": str(item.get("why") or ""),
                        "sources": list(item.get("sources") or [])[:5],
                        "rank_score": _to_float(item.get("rank_score") or 0.0),
                    }
                )
            else:
                raw_candidates.append({"symbol": _norm_symbol(item), "why": "raw_candidate"})
        record_raw_input(
            run_id=run_id,
            agent="scanner",
            stage="symbol_selection",
            raw_input={
                "candidate_pool_before_filter": int(len(candidates)),
                "candidates": raw_candidates,
                "candidate_source": str(pool_meta.get("candidate_source") or ""),
                "strategist_guidance": {
                    "themes": list(scanner_guidance.get("themes") or []),
                    "avoid_themes": list(scanner_guidance.get("avoid_themes") or []),
                    "playbook": playbook,
                    "scanner_bias": scanner_bias,
                    "scanner_priority": list(scanner_priority),
                    "scanner_source_policy": dict(scanner_guidance.get("scanner_source_policy") or {}),
                    "trade_aggressiveness": trade_aggressiveness,
                    "risk_tone": risk_tone,
                },
                "global_sentiment_score": float(gs),
                "feature_source": str(feature_source),
                "feature_symbol_count": int(len(feature_map)),
                "feature_errors": list(feature_errors),
            },
            decision_link={"stage": "scanner_candidate_retrieval"},
        )
    except Exception:
        pass

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
        ma60_gap = _to_float(feature_row.get("ma60_gap"))
        ma120_gap = _to_float(feature_row.get("ma120_gap"))
        trend_strength = _to_float(feature_row.get("trend_strength"))
        adx14 = _to_float(feature_row.get("adx14"))
        volume_spike20 = _to_float(feature_row.get("volume_spike20"))
        volatility20 = _to_float(feature_row.get("volatility20"))
        vwap_distance = _to_float(feature_row.get("vwap_distance"))
        cross_section_rank = _to_float(feature_row.get("cross_section_rank"))
        gap_pct = abs(_to_float(feature_row.get("gap_pct")))

        trading_value_component = _norm01(_to_float(source_scores.get("top_value")), 0.0, 2.0)
        momentum_raw = (0.65 * _signed01(return20, 0.10)) + (0.35 * _signed01(ma20_gap, 0.03))
        momentum_component = max(0.0, momentum_raw)
        ma_alignment_component = max(
            0.0,
            (
                0.45 * _signed01(ma20_gap, 0.03)
                + 0.35 * _signed01(ma60_gap, 0.05)
                + 0.20 * _signed01(ma120_gap, 0.08)
            ),
        )
        adx_component = _norm01(adx14, 15.0, 35.0)
        trend_raw = trend_strength if trend_strength != 0.0 else feature_signal
        trend_component = max(
            0.0,
            (
                0.45 * max(0.0, _signed01(trend_raw, 1.0))
                + 0.35 * ma_alignment_component
                + 0.20 * adx_component
            ),
        )
        volume_surge_component = _norm01(volume_spike20, 1.0, 3.0)
        vwap_alignment_component = max(0.0, _signed01(vwap_distance, 0.02))
        intraday_strength_component = max(
            0.0,
            (
                0.70 * max(0.0, _signed01(_to_float(metrics.get("change_pct")), 5.0))
                + 0.30 * vwap_alignment_component
            ),
        )
        cross_section_rank_component = _norm01(cross_section_rank, 0.0, 1.0)

        theme_matched_symbols = set(_norm_symbol(x) for x in list(pool_meta.get("theme_matched_symbols") or []))
        avoid_theme_symbols = set(_norm_symbol(x) for x in list(pool_meta.get("avoid_matched_symbols") or []))
        theme_boost_component = 1.0 if (symbol in theme_matched_symbols and len(theme_matched_symbols) > 0) else 0.0
        sentiment_component = max(0.0, (0.7 * news_s) + (0.3 * gs))

        volatility_penalty = _norm01(volatility20, 0.03, 0.08)
        gap_penalty = _norm01(gap_pct, 0.03, 0.10)
        open_order_penalty = _norm01(float(order_penalty), 0.0, 3.0)
        avoid_theme_penalty = 1.0 if (symbol in avoid_theme_symbols and len(avoid_theme_symbols) > 0) else 0.0

        repeat_penalty_meta = _repeat_symbol_penalty(state, symbol=symbol, policy=policy)
        repeat_symbol_penalty = _to_float(repeat_penalty_meta.get("penalty"))

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
            + (0.05 * cross_section_rank_component)
        ) * practical_scale
        risk_penalty_score = (
            practical_w["volatility_penalty"] * volatility_penalty
            + practical_w["gap_penalty"] * gap_penalty
            + practical_w["open_order_penalty"] * open_order_penalty
            + (0.20 * avoid_theme_penalty)
        ) * practical_scale

        # Keep backward compatibility with previous additive sentiment/risk knobs.
        legacy_adjust = (
            w["weight_news"] * news_s
            + w["weight_global"] * gs
            + w["feature_score_weight"] * feature_signal
            - (0.03 * open_order_penalty)
        )
        rank_bonus = 0.01 * max(0.0, candidate_rank_score)
        score_total = base_score + positive_score + legacy_adjust - risk_penalty_score + rank_bonus - repeat_symbol_penalty

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
        if repeat_symbol_penalty > 0.0:
            adj_conf = _clamp(adj_conf - (0.40 * repeat_symbol_penalty), 0.0, 1.0)
            adj_risk = _clamp(adj_risk + (0.25 * repeat_symbol_penalty), 0.0, 1.0)

        score_breakdown = {
            "trading_value": float(practical_w["trading_value"] * trading_value_component),
            "momentum": float(practical_w["momentum"] * momentum_component),
            "trend": float(practical_w["trend"] * trend_component),
            "ma_alignment": float(practical_w["trend"] * 0.35 * ma_alignment_component),
            "adx_trend": float(practical_w["trend"] * 0.20 * adx_component),
            "volume_surge": float(practical_w["volume_surge"] * volume_surge_component),
            "intraday_strength": float(practical_w["intraday_strength"] * intraday_strength_component),
            "vwap_alignment": float(practical_w["intraday_strength"] * 0.30 * vwap_alignment_component),
            "theme_boost": float(practical_w["theme_boost"] * theme_boost_component),
            "sentiment": float(practical_w["sentiment"] * sentiment_component),
            "cross_section_rank": float(0.05 * cross_section_rank_component * practical_scale),
            "avoid_theme_penalty": float(-0.20 * avoid_theme_penalty * practical_scale),
            "repeat_symbol_penalty": float(-repeat_symbol_penalty),
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
                    "ma_alignment_component": ma_alignment_component,
                    "adx_component": adx_component,
                    "volume_surge_component": volume_surge_component,
                    "intraday_strength_component": intraday_strength_component,
                    "vwap_alignment_component": vwap_alignment_component,
                    "cross_section_rank_component": cross_section_rank_component,
                    "theme_boost_component": theme_boost_component,
                    "sentiment_component": sentiment_component,
                    "volatility_penalty_component": volatility_penalty,
                    "gap_penalty_component": gap_penalty,
                    "open_order_penalty_component": open_order_penalty,
                    "avoid_theme_penalty_component": avoid_theme_penalty,
                    "repeat_symbol_penalty_component": repeat_symbol_penalty,
                    "recent_selection_repeat_count": int(repeat_penalty_meta.get("repeat_count") or 0),
                    "recent_selection_streak_count": int(repeat_penalty_meta.get("streak_count") or 0),
                    "recent_trade_same_symbol": bool(repeat_penalty_meta.get("recent_trade_same_symbol")),
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
    now_epoch = _resolve_now_epoch(state)
    if isinstance(selected, dict):
        _remember_selected_symbol(state, str(selected.get("symbol") or ""), now_epoch=now_epoch, policy=policy)
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
        "fallback_reason": str(pool_meta.get("fallback_reason") or ""),
        "blocked_static_fallback": bool(pool_meta.get("blocked_static_fallback")),
        "strict_kiwoom_only": bool(pool_meta.get("strict_kiwoom_only")),
        "theme_filter_applied": bool(pool_meta.get("theme_filter_applied")),
        "backfill_used": bool(pool_meta.get("backfill_used")),
        "backfill_count": int(pool_meta.get("backfill_count") or 0),
        "backfill_skipped_reason": str(pool_meta.get("backfill_skipped_reason") or ""),
        "score_weights": dict(practical_w),
        "source_mix": dict(pool_meta.get("pool_source_mix") or {}),
        "condition_search_status": str(pool_meta.get("condition_search_status") or ""),
        "condition_search_source": str(pool_meta.get("condition_search_source") or ""),
        "condition_search_reason": str(pool_meta.get("condition_search_reason") or ""),
        "scanner_source_policy": dict(pool_meta.get("scanner_source_policy") or {}),
        "strategist_scanner_priority": list(scanner_priority),
        "strategist_playbook": playbook or None,
        "strategist_scanner_bias": scanner_bias or None,
        "strategist_avoid_themes": list(pool_meta.get("avoid_themes") or []),
        "strategist_trade_aggressiveness": trade_aggressiveness or None,
        "strategist_risk_tone": risk_tone or None,
        "repeat_guard": _resolve_scanner_repeat_guard_policy(policy),
        "recent_scanner_selected_count": int(len(_scanner_recent_selection_history(state))),
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
    ranking_table = _ranking_table_rows(scan_results_sorted, max_rows=5)
    selected_snapshot = _compact_selected_snapshot(selected if isinstance(selected, dict) else None)
    runner_up_reasons: List[Dict[str, Any]] = []
    if len(scan_results_sorted) > 1 and isinstance(selected, dict):
        selected_score = float(_to_float(selected.get("score_total") or selected.get("score")))
        selected_confidence = float(_to_float(selected.get("confidence")))
        selected_risk = float(_to_float(selected.get("risk_score")))
        for row in list(scan_results_sorted[1:3]):
            if not isinstance(row, dict):
                continue
            reasons: List[str] = []
            row_score = float(_to_float(row.get("score_total") or row.get("score")))
            row_conf = float(_to_float(row.get("confidence")))
            row_risk = float(_to_float(row.get("risk_score")))
            if row_score < selected_score:
                reasons.append(f"lower total score ({row_score:.3f} vs {selected_score:.3f})")
            if row_conf < selected_confidence:
                reasons.append(f"lower confidence ({row_conf:.2f} vs {selected_confidence:.2f})")
            if row_risk > selected_risk:
                reasons.append(f"higher risk ({row_risk:.2f} vs {selected_risk:.2f})")
            if not reasons:
                reasons.append("lost on tie-break after score, confidence, and risk comparison")
            runner_up_reasons.append(
                {
                    "symbol": str(row.get("symbol") or ""),
                    "why_lost": reasons,
                }
            )
    _emit_scanner_event(
        state,
        name="candidate_pool_snapshot",
        payload={
            "candidate_source": str(pool_meta.get("candidate_source") or ""),
            "candidate_pool_before_filter": int(pool_meta.get("candidate_pool_before_filter") or 0),
            "candidate_pool_after_filter": int(pool_meta.get("candidate_pool_after_filter") or len(scan_results_sorted)),
            "theme_filter_applied": bool(pool_meta.get("theme_filter_applied")),
            "avoid_filter_applied": bool(pool_meta.get("avoid_filter_applied")),
            "source_mix": dict(pool_meta.get("pool_source_mix") or {}),
            "scanner_source_policy": dict(pool_meta.get("scanner_source_policy") or {}),
            "candidate_symbols": [str((row or {}).get("symbol") or "") for row in list(scan_results_sorted or [])[:10] if isinstance(row, dict)],
            "fallback_reason": str(pool_meta.get("fallback_reason") or ""),
            "backfill_used": bool(pool_meta.get("backfill_used")),
            "backfill_count": int(pool_meta.get("backfill_count") or 0),
        },
    )
    _emit_scanner_event(
        state,
        name="candidate_ranking_table",
        payload={
            "tie_break_rule": "score_total desc -> confidence desc -> risk_score asc",
            "rows": ranking_table,
        },
        symbol=str((selected or {}).get("symbol") or ""),
    )
    _emit_scanner_event(
        state,
        name="candidate_selection_reason",
        payload={
            "selected_symbol": str((selected or {}).get("symbol") or ""),
            "why_selected": [
                f"highest total score ({float(_to_float((selected or {}).get('score_total') or (selected or {}).get('score'))):.3f})"
                if isinstance(selected, dict)
                else "no candidate selected",
                f"confidence {float(_to_float((selected or {}).get('confidence'))):.2f} and risk {float(_to_float((selected or {}).get('risk_score'))):.2f}"
                if isinstance(selected, dict)
                else "",
                f"source mix: {', '.join(list(((selected or {}).get('candidate') or {}).get('sources') or [])[:4])}"
                if isinstance(selected, dict)
                else "",
                f"playbook alignment: {playbook or 'not_captured'}",
            ],
            "runner_ups_lost": runner_up_reasons,
            "tie_break_rule": "score_total desc -> confidence desc -> risk_score asc",
            "final_decision_basis": "Scanner selected the highest-ranked candidate after strategist-guided weighting, source scoring, and risk penalties.",
        },
        symbol=str((selected or {}).get("symbol") or ""),
    )
    _emit_scanner_event(
        state,
        name="selection_output",
        payload={
            "selected_symbol": state.get("top_stock") or None,
            "candidate_count": int(len(scan_results_sorted)),
            "ranking_top_n": ranking_table,
            "selected_candidate": selected_snapshot,
        },
        symbol=str((selected or {}).get("symbol") or ""),
    )

    _log_scanner_summary(
        state,
        {
            "candidate_source": str(pool_meta.get("candidate_source") or ""),
            "candidate_pool_before_filter": int(pool_meta.get("candidate_pool_before_filter") or 0),
            "candidate_pool_after_filter": int(pool_meta.get("candidate_pool_after_filter") or len(scan_results_sorted)),
            "theme_filter_applied": bool(pool_meta.get("theme_filter_applied")),
            "fallback_reason": str(pool_meta.get("fallback_reason") or ""),
            "blocked_static_fallback": bool(pool_meta.get("blocked_static_fallback")),
            "strict_kiwoom_only": bool(pool_meta.get("strict_kiwoom_only")),
            "backfill_used": bool(pool_meta.get("backfill_used")),
            "backfill_count": int(pool_meta.get("backfill_count") or 0),
            "top_stock": state.get("top_stock"),
            "top_score": top_score,
            "top_ranked_symbols": [str(x.get("symbol") or "") for x in list(state.get("ranked_candidates") or [])[:5]],
            "strategist_scanner_priority": list(scanner_priority),
            "strategist_scanner_source_policy": dict(pool_meta.get("scanner_source_policy") or {}),
            "condition_search_status": str(pool_meta.get("condition_search_status") or ""),
            "condition_search_source": str(pool_meta.get("condition_search_source") or ""),
            "condition_search_reason": str(pool_meta.get("condition_search_reason") or ""),
            "strategist_playbook": playbook or "",
            "strategist_scanner_bias": scanner_bias or "",
            "strategist_avoid_themes": list(pool_meta.get("avoid_themes") or []),
            "strategist_trade_aggressiveness": trade_aggressiveness or "",
            "strategist_risk_tone": risk_tone or "",
            "recent_scanner_selected_count": int(len(_scanner_recent_selection_history(state))),
        },
    )

    top_candidates_summary: List[Dict[str, Any]] = []
    for row in list(state.get("ranked_candidates") or [])[:3]:
        if not isinstance(row, dict):
            continue
        top_candidates_summary.append(
            {
                "symbol": str(row.get("symbol") or ""),
                "score_total": float(_to_float(row.get("score_total"))),
                "risk_score": float(_to_float(row.get("risk_score"))),
            }
        )
    append_decision_trace(
        state,
        agent="scanner",
        event="candidate_selection",
        payload={
            "playbook": playbook or "",
            "scanner_priority": list(scanner_priority),
            "candidate_source": str(pool_meta.get("candidate_source") or ""),
            "kiwoom_pool_source_mix": dict(pool_meta.get("pool_source_mix") or {}),
            "condition_search_status": str(pool_meta.get("condition_search_status") or ""),
            "condition_search_source": str(pool_meta.get("condition_search_source") or ""),
            "condition_search_reason": str(pool_meta.get("condition_search_reason") or ""),
            "scanner_source_policy": dict(pool_meta.get("scanner_source_policy") or {}),
            "candidate_pool_size": int(len(scan_results_sorted)),
            "recent_scanner_selected_count": int(len(_scanner_recent_selection_history(state))),
            "top_candidates": top_candidates_summary,
            "selected_symbol": state.get("top_stock") or None,
            "score_breakdown_summary": (
                dict(selected.get("score_breakdown") or {})
                if isinstance(selected, dict)
                else {}
            ),
            "selected_candidate": _compact_selected_snapshot(selected if isinstance(selected, dict) else None),
        },
    )
    try:
        record_decision_bridge(
            run_id=run_id,
            agent="scanner",
            stage="decision_bridge",
            raw_input={
                "candidate_pool_size": int(len(scan_results_sorted)),
                "candidate_source": str(pool_meta.get("candidate_source") or ""),
                "theme_filter_applied": bool(pool_meta.get("theme_filter_applied")),
                "scanner_source_policy": dict(pool_meta.get("scanner_source_policy") or {}),
            },
            parsed_output={
                "selected_symbol": state.get("top_stock") or None,
                "top_score": float(_to_float(top_score) if top_score is not None else 0.0),
                "ranked_candidates": list(state.get("ranked_candidates") or [])[:5],
                "selected_candidate": _compact_selected_snapshot(selected if isinstance(selected, dict) else None),
            },
            decision_link={
                "decision_chain": {
                    "theme": str((state.get("themes") or [""])[0] if isinstance(state.get("themes"), list) and state.get("themes") else ""),
                    "scanner_selected": state.get("top_stock") or None,
                }
            },
        )
    except Exception:
        pass
    try:
        write_scanner_artifact(state)
    except Exception:
        pass

    return state
