from __future__ import annotations

import os
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from libs.ai.intent_schema import normalize_intent
from libs.data_quality.signal_contract import (
    SIGNAL_STATUS_FALLBACK,
    make_signal,
)
from libs.runtime.exit_policy import evaluate_exit_policy
from libs.runtime.circuit_breaker import (
    gate_runtime_circuit,
    mark_runtime_circuit_failure,
    mark_runtime_circuit_success,
)

def _rule_intent(symbol: Any, price: Any, cash: Any, open_positions: Any) -> Dict[str, Any]:
    if cash and cash > 1_000_000 and price is not None and int(open_positions or 0) == 0 and symbol:
        return {
            "action": "BUY",
            "symbol": symbol,
            "qty": 1,
            "price": None,
            "order_type": "market",
            "order_api_id": "ORDER_SUBMIT",
            "rationale": "rule:cash_and_price_ok",
        }
    return {"action": "NOOP", "reason": "conditions_not_met", "rationale": "rule:no_trade"}


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _enforce_rationale_for_trade_intent(raw_intent: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(raw_intent or {})
    action = str(out.get("action") or "").strip().upper()
    if action not in ("BUY", "SELL"):
        return out
    rationale = str(out.get("rationale") or out.get("reason") or "").strip()
    if rationale:
        return out

    # Safety policy: no BUY/SELL without explicit rationale.
    out["action"] = "NOOP"
    out["qty"] = 0
    out["reason"] = "missing_rationale"
    out["rationale"] = "missing_rationale"
    return out


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clip(v: float, lo: float, hi: float) -> float:
    x = float(v)
    if x < lo:
        return float(lo)
    if x > hi:
        return float(hi)
    return x


def _read_env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name, str(default)) or str(default)).strip()
    try:
        return float(raw)
    except Exception:
        return float(default)


def _policy_thresholds() -> Dict[str, float]:
    return {
        "buy_threshold": _read_env_float("AI_STRATEGIST_BUY_THRESHOLD", 0.10),
        "sell_threshold": _read_env_float("AI_STRATEGIST_SELL_THRESHOLD", -0.10),
        "high_vol_abs_threshold": _read_env_float("AI_STRATEGIST_HIGH_VOL_ABS_THRESHOLD", 0.12),
        "news_buy_threshold": _read_env_float("AI_STRATEGIST_NEWS_BUY_THRESHOLD", 0.15),
        "news_sell_threshold": _read_env_float("AI_STRATEGIST_NEWS_SELL_THRESHOLD", -0.15),
    }


def _score_override_enabled() -> bool:
    return _is_trueish(os.getenv("AI_STRATEGIST_SCORE_OVERRIDE", "false"))


def _composite_score(technical: Dict[str, Any], news: Dict[str, Any]) -> float:
    signal = _to_float(technical.get("signal_score"), 0.0)
    ma_gap = _clip(_to_float(technical.get("ma20_gap"), 0.0), -0.20, 0.20)
    sym_news = _to_float(news.get("symbol_sentiment_score"), 0.0)
    global_news = _to_float(news.get("global_sentiment_score"), 0.0)
    score = (0.55 * signal) + (0.20 * ma_gap) + (0.20 * sym_news) + (0.05 * global_news)
    return float(_clip(score, -1.0, 1.0))


def _maybe_override_noop_by_score(
    *,
    intent: Dict[str, Any],
    llm_context: Dict[str, Any],
    symbol: Any,
    price: Any,
    open_positions: Any,
    portfolio: Dict[str, Any],
) -> tuple[Dict[str, Any], bool]:
    if not _score_override_enabled():
        return dict(intent or {}), False

    base = dict(intent or {})
    action = str(base.get("action") or "").strip().upper()
    reason = str(base.get("reason") or "").strip().lower()
    if action != "NOOP":
        return base, False
    if reason not in ("", "model_no_signal", "conditions_not_met"):
        return base, False

    technical = llm_context.get("technical") if isinstance(llm_context.get("technical"), dict) else {}
    news = llm_context.get("news") if isinstance(llm_context.get("news"), dict) else {}
    policy = llm_context.get("decision_policy") if isinstance(llm_context.get("decision_policy"), dict) else {}

    composite = _to_float(policy.get("composite_score"), _composite_score(technical, news))
    regime = str(technical.get("regime") or "").strip().lower() or "unknown"
    sym_news = _to_float(news.get("symbol_sentiment_score"), 0.0)
    th = _policy_thresholds()

    high_vol_ok = True
    if regime == "high_volatility":
        high_vol_ok = abs(composite) >= float(th["high_vol_abs_threshold"])

    sym = str(symbol or "").strip().upper()
    px = _to_float(price, 0.0) if price is not None else 0.0

    if int(open_positions or 0) <= 0:
        if high_vol_ok and (composite >= float(th["buy_threshold"]) or sym_news >= float(th["news_buy_threshold"])):
            return (
                {
                    "action": "BUY",
                    "symbol": sym,
                    "qty": 1,
                    "price": px if px > 0.0 else None,
                    "order_type": "market",
                    "order_api_id": "ORDER_SUBMIT",
                    "rationale": f"score_override:buy composite={composite:.4f} regime={regime}",
                },
                True,
            )
        return base, False

    pos = _extract_position_for_symbol(portfolio, sym)
    qty = int(pos.get("qty") or 0) if isinstance(pos, dict) else 0
    if qty <= 0:
        return base, False
    if high_vol_ok and (composite <= float(th["sell_threshold"]) or sym_news <= float(th["news_sell_threshold"])):
        return (
            {
                "action": "SELL",
                "symbol": sym,
                "qty": qty,
                "price": px if px > 0.0 else None,
                "order_type": "market",
                "order_api_id": "ORDER_SUBMIT",
                "rationale": f"score_override:sell composite={composite:.4f} regime={regime}",
            },
            True,
        )
    return base, False


def _extract_position_for_symbol(portfolio: Dict[str, Any], symbol: Any) -> Dict[str, Any]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {}
    rows = portfolio.get("positions")
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol") or "").strip().upper() == sym:
            return dict(row)
    return {}


def _resolve_exit_policy_enabled(state: Dict[str, Any]) -> bool:
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    if _is_trueish(state.get("use_exit_policy")):
        return True
    if _is_trueish(policy.get("use_exit_policy")):
        return True
    return _is_trueish(os.getenv("USE_EXIT_POLICY", "false"))


def _resolve_exit_policy_config(state: Dict[str, Any]) -> Dict[str, Any]:
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    cfg = policy.get("exit_policy") if isinstance(policy.get("exit_policy"), dict) else {}
    out = dict(cfg or {})

    sl_raw = str(os.getenv("EXIT_POLICY_STOP_LOSS_PCT", "") or "").strip()
    tp_raw = str(os.getenv("EXIT_POLICY_TAKE_PROFIT_PCT", "") or "").strip()
    mh_raw = str(os.getenv("EXIT_POLICY_MAX_HOLD_SEC", "") or "").strip()
    trail_raw = str(os.getenv("EXIT_POLICY_TRAILING_STOP_PCT", "") or "").strip()
    vol_exp_raw = str(os.getenv("EXIT_POLICY_VOL_EXPANSION_RATIO", "") or "").strip()
    news_shock_raw = str(os.getenv("EXIT_POLICY_NEWS_SHOCK_THRESHOLD", "") or "").strip()
    eod_flat_raw = str(os.getenv("EXIT_POLICY_USE_EOD_FLAT", "") or "").strip()
    eod_cutoff_raw = str(os.getenv("EXIT_POLICY_EOD_FLAT_CUTOFF_MIN", "") or "").strip()
    emergency_raw = str(os.getenv("EXIT_POLICY_EMERGENCY_HALT", "") or "").strip()

    if sl_raw:
        out["stop_loss_pct"] = _to_float(sl_raw, _to_float(out.get("stop_loss_pct"), 0.03))
    if tp_raw:
        out["take_profit_pct"] = _to_float(tp_raw, _to_float(out.get("take_profit_pct"), 0.05))
    if mh_raw:
        out["max_hold_sec"] = int(_to_float(mh_raw, _to_float(out.get("max_hold_sec"), 0.0)))
    if trail_raw:
        out["trailing_stop_pct"] = _to_float(trail_raw, _to_float(out.get("trailing_stop_pct"), 0.0))
    if vol_exp_raw:
        out["vol_expansion_ratio"] = _to_float(vol_exp_raw, _to_float(out.get("vol_expansion_ratio"), 0.0))
    if news_shock_raw:
        out["news_shock_threshold"] = _to_float(news_shock_raw, _to_float(out.get("news_shock_threshold"), 0.0))
    if eod_flat_raw:
        out["use_eod_flat"] = _is_trueish(eod_flat_raw)
    if eod_cutoff_raw:
        out["eod_flat_cutoff_min"] = int(_to_float(eod_cutoff_raw, _to_float(out.get("eod_flat_cutoff_min"), 10.0)))
    if emergency_raw:
        out["emergency_halt"] = _is_trueish(emergency_raw)
    return out


def _resolve_position_hold_sec(state: Dict[str, Any]) -> int | None:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    side = str((persisted or {}).get("last_trade_side") or "").strip().upper()
    if side != "BUY":
        return None
    try:
        last_epoch = int(float((persisted or {}).get("last_trade_epoch") or 0))
    except Exception:
        last_epoch = 0
    if last_epoch <= 0:
        return None
    now_epoch = int(time.time())
    return max(0, now_epoch - last_epoch)


def _resolve_post_exit_cooldown_sec(state: Dict[str, Any]) -> int:
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    raw = (
        policy.get("post_exit_cooldown_sec")
        if policy.get("post_exit_cooldown_sec") is not None
        else os.getenv("POST_EXIT_COOLDOWN_SEC", "300")
    )
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 300


def _resolve_min_hold_sec(state: Dict[str, Any]) -> int:
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    raw = policy.get("min_hold_seconds")
    if raw is None:
        raw = os.getenv("MIN_HOLD_SECONDS", "600")
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 600


def _resolve_sell_cooldown_sec(state: Dict[str, Any]) -> int:
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    raw = policy.get("sell_cooldown_sec")
    if raw is None:
        raw = os.getenv("SELL_COOLDOWN", "")
    if raw in (None, ""):
        raw = os.getenv("SELL_COOLDOWN_SEC", "300")
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 300


def _sell_timing_guard_exempt(raw_intent: Dict[str, Any]) -> bool:
    rationale = str(raw_intent.get("rationale") or raw_intent.get("reason") or "").strip().lower()
    if rationale.startswith("eod_force_liquidation"):
        return True
    if rationale.startswith("exit_policy:emergency_halt"):
        return True
    if rationale.startswith("exit_policy:stop_loss"):
        return True
    if rationale.startswith("exit_policy:news_shock"):
        return True
    return False


def _apply_sell_timing_guard(
    *,
    state: Dict[str, Any],
    intent: Dict[str, Any],
    raw_intent: Dict[str, Any],
) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
    out = dict(intent or {})
    action = str(out.get("action") or "").strip().upper()
    if action != "SELL":
        return out, str(out.get("rationale") or out.get("reason") or ""), {"applied": False}

    position_age_sec = _resolve_position_hold_sec(state)
    min_hold_sec = _resolve_min_hold_sec(state)
    sell_cooldown_sec = _resolve_sell_cooldown_sec(state)
    required_age_sec = max(min_hold_sec, sell_cooldown_sec)
    guard_info: Dict[str, Any] = {
        "applied": True,
        "blocked": False,
        "position_age_sec": position_age_sec,
        "min_hold_sec": int(min_hold_sec),
        "sell_cooldown_sec": int(sell_cooldown_sec),
        "required_age_sec": int(required_age_sec),
        "exempt": False,
        "reason": "",
    }

    if _sell_timing_guard_exempt(raw_intent):
        guard_info["exempt"] = True
        guard_info["reason"] = "sell_timing_guard_exempt"
        return out, str(out.get("rationale") or out.get("reason") or ""), guard_info

    if required_age_sec <= 0 or position_age_sec is None:
        return out, str(out.get("rationale") or out.get("reason") or ""), guard_info

    if int(position_age_sec) >= int(required_age_sec):
        return out, str(out.get("rationale") or out.get("reason") or ""), guard_info

    rationale = f"sell_guard_min_hold:{int(position_age_sec)}s<{int(required_age_sec)}s"
    blocked = {
        "action": "NOOP",
        "symbol": out.get("symbol"),
        "qty": 0,
        "price": None,
        "order_type": out.get("order_type") or "market",
        "order_api_id": out.get("order_api_id") or "ORDER_SUBMIT",
        "reason": "sell_guard_min_hold",
        "rationale": rationale,
    }
    guard_info["blocked"] = True
    guard_info["reason"] = "sell_guard_min_hold"
    return blocked, rationale, guard_info


KST = timezone(timedelta(hours=9))


def _parse_hhmm(raw: Any, *, default_hhmm: str) -> dt_time:
    src = str(raw or default_hhmm).strip()
    digits = "".join(ch for ch in src if ch.isdigit())
    if len(digits) != 4:
        digits = default_hhmm
    try:
        hh = int(digits[:2])
        mm = int(digits[2:])
    except Exception:
        hh, mm = int(default_hhmm[:2]), int(default_hhmm[2:])
    hh = min(23, max(0, hh))
    mm = min(59, max(0, mm))
    return dt_time(hour=hh, minute=mm)


def _resolve_now_kst(state: Dict[str, Any]) -> datetime:
    tick_ts = state.get("tick_ts")
    if tick_ts is not None:
        try:
            return datetime.fromtimestamp(float(tick_ts), tz=timezone.utc).astimezone(KST)
        except Exception:
            pass
    return datetime.now(timezone.utc).astimezone(KST)


def _pick_any_open_position_symbol(portfolio: Dict[str, Any]) -> str:
    rows = portfolio.get("positions")
    if not isinstance(rows, list):
        return ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = _norm_symbol(row.get("symbol"))
        qty = int(row.get("qty") or 0)
        if sym and qty > 0:
            return sym
    return ""


def _resolve_eod_force_liquidation_intent(
    *,
    state: Dict[str, Any],
    portfolio: Dict[str, Any],
    symbol: Any,
) -> Dict[str, Any] | None:
    if not _is_trueish(os.getenv("USE_EOD_FORCE_LIQUIDATION", "false")):
        return None

    now_kst = _resolve_now_kst(state)
    if now_kst.weekday() >= 5:
        return None

    start_t = _parse_hhmm(os.getenv("EOD_FORCE_LIQUIDATION_START_HHMM", "1520"), default_hhmm="1520")
    end_t = _parse_hhmm(os.getenv("EOD_FORCE_LIQUIDATION_END_HHMM", "1530"), default_hhmm="1530")
    now_t = now_kst.time().replace(second=0, microsecond=0)
    if now_t < start_t or now_t > end_t:
        return None

    sym = _norm_symbol(symbol)
    pos = _extract_position_for_symbol(portfolio, sym) if sym else {}
    if not pos:
        fallback_sym = _pick_any_open_position_symbol(portfolio)
        if fallback_sym:
            pos = _extract_position_for_symbol(portfolio, fallback_sym)
            sym = fallback_sym
    if not isinstance(pos, dict) or not pos:
        return None

    qty = int(pos.get("qty") or 0)
    if qty <= 0 or not sym:
        return None

    mkt = state.get("market_snapshot") if isinstance(state.get("market_snapshot"), dict) else {}
    px = mkt.get("price") if _norm_symbol(mkt.get("symbol")) == sym else None
    return {
        "action": "SELL",
        "symbol": sym,
        "qty": qty,
        "price": px,
        "order_type": "market",
        "order_api_id": "ORDER_SUBMIT",
        "rationale": f"eod_force_liquidation:{now_kst.strftime('%H:%M')}",
    }


def _norm_symbol(v: Any) -> str:
    return str(v or "").strip().upper()


def _extract_symbol_feature_row(state: Dict[str, Any], symbol: Any) -> Dict[str, Any]:
    sym = _norm_symbol(symbol)
    if not sym:
        return {}

    direct = state.get("scanner_features")
    if isinstance(direct, dict):
        row = direct.get(sym) or direct.get(str(symbol))
        if isinstance(row, dict):
            return dict(row)

    fe = state.get("feature_engine")
    if isinstance(fe, dict):
        by_symbol = fe.get("by_symbol")
        if isinstance(by_symbol, dict):
            row = by_symbol.get(sym) or by_symbol.get(str(symbol))
            if isinstance(row, dict):
                return dict(row)

    # Optional on-demand calculation when OHLCV is already injected.
    ohlcv = state.get("ohlcv_by_symbol")
    if isinstance(ohlcv, dict):
        rows = ohlcv.get(sym) or ohlcv.get(str(symbol))
        if isinstance(rows, list) and rows:
            try:
                from libs.runtime.feature_engine import build_feature_map

                out = build_feature_map({sym: rows})
                row = out.get(sym)
                if isinstance(row, dict):
                    return dict(row)
            except Exception:
                return {}
    return {}


def _extract_symbol_news_score(state: Dict[str, Any], symbol: Any) -> float:
    signal = _extract_symbol_news_signal(state, symbol)
    return _to_float(signal.get("score"), 0.0)


def _extract_global_sentiment_score(state: Dict[str, Any]) -> float:
    signal = _extract_global_sentiment_signal(state)
    return _to_float(signal.get("score"), 0.0)


def _coerce_signal_dict(raw: Any, *, default_source: str, default_reason: str) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return make_signal(
            score=raw.get("score", 0.0),
            status=str(raw.get("status") or SIGNAL_STATUS_FALLBACK),
            source=str(raw.get("source") or default_source),
            reason=str(raw.get("reason") or default_reason),
            ts=raw.get("ts"),
        )
    return make_signal(
        score=0.0,
        status=SIGNAL_STATUS_FALLBACK,
        source=default_source,
        reason=default_reason,
    )


def _extract_symbol_news_signal(state: Dict[str, Any], symbol: Any) -> Dict[str, Any]:
    sym = _norm_symbol(symbol)
    if not sym:
        return make_signal(
            score=0.0,
            status=SIGNAL_STATUS_FALLBACK,
            source="decision_context",
            reason="missing_symbol",
        )

    news_signal_root = state.get("news_sentiment_signal")
    if isinstance(news_signal_root, dict):
        raw_sig = news_signal_root.get(sym)
        if raw_sig is None:
            raw_sig = news_signal_root.get(str(symbol))
        if raw_sig is not None:
            return _coerce_signal_dict(
                raw_sig,
                default_source="news_sentiment_signal",
                default_reason="signal_missing_fields",
            )

    raw = state.get("news_sentiment")
    if not isinstance(raw, dict):
        raw = state.get("mock_news_sentiment")
    if isinstance(raw, dict):
        score = raw.get(sym) if sym in raw else raw.get(str(symbol))
        return make_signal(
            score=score if score is not None else 0.0,
            status=SIGNAL_STATUS_FALLBACK,
            source="legacy_news_sentiment",
            reason="signal_missing_using_legacy_score",
        )

    return make_signal(
        score=0.0,
        status=SIGNAL_STATUS_FALLBACK,
        source="legacy_news_sentiment",
        reason="signal_missing_no_score",
    )


def _extract_global_sentiment_signal(state: Dict[str, Any]) -> Dict[str, Any]:
    raw_sig = state.get("global_sentiment_signal")
    if raw_sig is not None:
        return _coerce_signal_dict(
            raw_sig,
            default_source="global_sentiment_signal",
            default_reason="signal_missing_fields",
        )

    gs = state.get("global_sentiment")
    if isinstance(gs, dict):
        return make_signal(
            score=gs.get("score", 0.0),
            status=SIGNAL_STATUS_FALLBACK,
            source="legacy_global_sentiment",
            reason="signal_missing_using_legacy_score",
        )
    if gs is not None:
        return make_signal(
            score=gs,
            status=SIGNAL_STATUS_FALLBACK,
            source="legacy_global_sentiment",
            reason="signal_missing_using_legacy_score",
        )
    pol = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    pgs = pol.get("global_sentiment")
    if isinstance(pgs, dict):
        return make_signal(
            score=pgs.get("score", 0.0),
            status=SIGNAL_STATUS_FALLBACK,
            source="legacy_policy_global_sentiment",
            reason="signal_missing_using_policy_score",
        )
    if pgs is not None:
        return make_signal(
            score=pgs,
            status=SIGNAL_STATUS_FALLBACK,
            source="legacy_policy_global_sentiment",
            reason="signal_missing_using_policy_score",
        )
    return make_signal(
        score=0.0,
        status=SIGNAL_STATUS_FALLBACK,
        source="legacy_global_sentiment",
        reason="signal_missing_no_score",
    )


def _build_llm_context(state: Dict[str, Any], symbol: Any) -> Dict[str, Any]:
    feat = _extract_symbol_feature_row(state, symbol)
    news_signal = _extract_symbol_news_signal(state, symbol)
    global_signal = _extract_global_sentiment_signal(state)
    news_score = _to_float(news_signal.get("score"), 0.0)
    global_score = _to_float(global_signal.get("score"), 0.0)

    def _v_float(name: str, default: float) -> float:
        val = feat.get(name)
        if val is None:
            return float(default)
        return _to_float(val, default)

    regime_raw = feat.get("regime")
    regime = str(regime_raw).strip().lower() if regime_raw is not None else "unknown"
    if not regime:
        regime = "unknown"

    technical = {
        "rsi14": _v_float("rsi14", 50.0),
        "ma20_gap": _v_float("ma20_gap", 0.0),
        "atr14": _v_float("atr14", 0.0),
        "volume_spike20": _v_float("volume_spike20", 1.0),
        "volatility20": _v_float("volatility20", 0.0),
        "regime": regime,
        "signal_score": _v_float("signal_score", 0.0),
    }
    news = {
        "symbol_sentiment_score": float(news_score),
        "global_sentiment_score": float(global_score),
        "symbol_sentiment_status": str(news_signal.get("status") or SIGNAL_STATUS_FALLBACK),
        "symbol_sentiment_source": str(news_signal.get("source") or ""),
        "symbol_sentiment_reason": str(news_signal.get("reason") or ""),
        "global_sentiment_status": str(global_signal.get("status") or SIGNAL_STATUS_FALLBACK),
        "global_sentiment_source": str(global_signal.get("source") or ""),
        "global_sentiment_reason": str(global_signal.get("reason") or ""),
    }
    policy = _policy_thresholds()
    composite = _composite_score(technical, news)
    return {
        "technical": technical,
        "news": news,
        "data_quality": {
            "news_signal": dict(news_signal),
            "global_signal": dict(global_signal),
        },
        "decision_policy": {
            **policy,
            "composite_score": float(composite),
        },
    }


def _build_packet_why(*, state: Dict[str, Any], llm_context: Dict[str, Any]) -> Dict[str, Any]:
    technical = llm_context.get("technical") if isinstance(llm_context.get("technical"), dict) else {}
    news = llm_context.get("news") if isinstance(llm_context.get("news"), dict) else {}
    decision_policy = llm_context.get("decision_policy") if isinstance(llm_context.get("decision_policy"), dict) else {}
    base = {
        "regime": str(technical.get("regime") or "unknown"),
        "technical": dict(technical),
        "news": dict(news),
        "policy": dict(decision_policy),
    }
    override = state.get("why")
    if isinstance(override, dict):
        for k in ("regime", "technical", "news", "policy"):
            if k in override:
                base[k] = override.get(k)
    return base


def _build_packet_invalidation(*, state: Dict[str, Any]) -> Dict[str, Any]:
    inv = state.get("invalidation")
    if isinstance(inv, dict):
        return {
            "triggered": bool(inv.get("triggered", False)),
            "reason": str(inv.get("reason") or ""),
            "conditions": list(inv.get("conditions") or []),
        }
    return {"triggered": False, "reason": "", "conditions": []}


def _strategy_v1_enabled(state: Dict[str, Any]) -> bool:
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    if policy.get("use_strategy_v1") is not None:
        return _is_trueish(policy.get("use_strategy_v1"))
    return _is_trueish(os.getenv("USE_STRATEGY_V1", "false"))


def _to_strategy_v1_input(
    *,
    symbol: Any,
    llm_context: Dict[str, Any],
    portfolio: Dict[str, Any],
    policy: Dict[str, Any],
    risk_context: Dict[str, Any],
):
    from libs.strategies.contracts import StrategyInput

    technical = llm_context.get("technical") if isinstance(llm_context.get("technical"), dict) else {}
    news = llm_context.get("news") if isinstance(llm_context.get("news"), dict) else {}
    rc = dict(risk_context or {})
    if not str(rc.get("regime") or "").strip():
        rc["regime"] = str(technical.get("regime") or "unknown")
    if rc.get("volatility_percentile") is None:
        vol = _to_float(technical.get("volatility20"), 0.0)
        vol_ref = max(1e-9, _to_float(policy.get("volatility_percentile_ref"), 0.20))
        rc["volatility_percentile"] = _clip(vol / vol_ref, 0.0, 1.0)
    if rc.get("portfolio_exposure") is None:
        rc["portfolio_exposure"] = _clip(
            _to_float(portfolio.get("exposure_ratio", portfolio.get("portfolio_exposure", 0.0)), 0.0),
            0.0,
            1.0,
        )
    if rc.get("daily_loss_state") is None:
        daily_pnl = _to_float(rc.get("daily_pnl_ratio", portfolio.get("daily_pnl_ratio", 0.0)), 0.0)
        daily_loss_cut = _to_float(policy.get("daily_loss_state_threshold"), -0.01)
        rc["daily_loss_state"] = bool(daily_pnl <= daily_loss_cut)
    if rc.get("degrade_mode") is None:
        rc["degrade_mode"] = _is_trueish(
            rc.get("safe_degrade_mode", policy.get("degrade_mode", policy.get("safe_degrade_mode", False)))
        )
    if rc.get("correlation_bucket") is None:
        rc["correlation_bucket"] = str(policy.get("correlation_bucket") or "medium").strip().lower() or "medium"
    return StrategyInput(
        symbol=_norm_symbol(symbol),
        regime=str(technical.get("regime") or "unknown"),
        technical=dict(technical),
        news=dict(news),
        portfolio=dict(portfolio or {}),
        policy=dict(policy or {}),
        risk_context=rc,
    )


def _raw_intent_from_strategy_decision(decision: Dict[str, Any], *, default_price: Any) -> Dict[str, Any]:
    action = str(decision.get("action") or "").strip().upper()
    symbol = _norm_symbol(decision.get("symbol"))
    qty = max(0, int(decision.get("qty") or 0))
    rationale = str(decision.get("rationale") or "").strip()
    if action == "BUY":
        return {
            "action": "BUY",
            "symbol": symbol,
            "qty": max(1, qty),
            "price": default_price,
            "order_type": "market",
            "order_api_id": "ORDER_SUBMIT",
            "rationale": rationale or "strategy_v1_buy",
        }
    if action == "SELL":
        return {
            "action": "SELL",
            "symbol": symbol,
            "qty": max(1, qty),
            "price": default_price,
            "order_type": "market",
            "order_api_id": "ORDER_SUBMIT",
            "rationale": rationale or "strategy_v1_sell",
        }
    return {
        "action": "NOOP",
        "reason": "strategy_v1_noop",
        "rationale": rationale or "strategy_v1_noop",
    }


def _post_exit_cooldown_remaining_sec(state: Dict[str, Any], open_positions: Any) -> int:
    if int(open_positions or 0) > 0:
        return 0
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    side = str((persisted or {}).get("last_trade_side") or "").strip().upper()
    if side != "SELL":
        return 0
    last_epoch = 0
    try:
        last_epoch = int(float((persisted or {}).get("last_trade_epoch") or 0))
    except Exception:
        last_epoch = 0
    if last_epoch <= 0:
        return 0
    cooldown = _resolve_post_exit_cooldown_sec(state)
    if cooldown <= 0:
        return 0
    now_epoch = int(time.time())
    remaining = (last_epoch + cooldown) - now_epoch
    return max(0, int(remaining))


def _import_event_logger():
    for mod in ("libs.event_logger", "libs.logging.event_logger", "libs.core.event_logger"):
        try:
            m = __import__(mod, fromlist=["EventLogger", "new_run_id"])
            return getattr(m, "EventLogger"), getattr(m, "new_run_id")
        except Exception:
            continue
    from libs.core.event_logger import EventLogger, new_run_id  # type: ignore
    return EventLogger, new_run_id


def _ensure_run_id(state: dict) -> str:
    _EventLogger, new_run_id = _import_event_logger()
    rid = str(state.get("run_id") or new_run_id())
    state["run_id"] = rid
    return rid


def _make_logger():
    EventLogger, _new_run_id = _import_event_logger()
    log_path = os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl")
    return EventLogger(log_path=Path(log_path))


def _log_decision(state: dict, packet: dict, trace: dict) -> None:
    try:
        logger = _make_logger()
        run_id = _ensure_run_id(state)
        logger.log(run_id=run_id, stage="decision", event="trace", payload={"decision_packet": packet, "trace": trace})
    except Exception:
        return


def _log_llm_call(state: dict, payload: Dict[str, Any]) -> None:
    try:
        logger = _make_logger()
        run_id = _ensure_run_id(state)
        logger.log(run_id=run_id, stage="strategist_llm", event="result", payload=payload)
    except Exception:
        return


def _sync_legacy_circuit_fields(state: dict, llm_meta: Dict[str, Any]) -> None:
    """Keep legacy top-level circuit fields in sync for compatibility."""
    if llm_meta.get("circuit_state") is not None:
        state["circuit_state"] = str(llm_meta.get("circuit_state") or "")
    if llm_meta.get("circuit_fail_count") is not None:
        try:
            state["circuit_fail_count"] = int(float(llm_meta.get("circuit_fail_count") or 0))
        except Exception:
            pass
    if llm_meta.get("circuit_open_until_epoch") is not None:
        try:
            state["circuit_open_until_epoch"] = int(float(llm_meta.get("circuit_open_until_epoch") or 0))
        except Exception:
            pass


def decide_trade(state: dict) -> dict:
    market: Dict[str, Any] = state.get("market_snapshot", {}) or {}
    portfolio: Dict[str, Any] = state.get("portfolio_snapshot", {}) or {}

    symbol = state.get("symbol") or state.get("selected_symbol") or market.get("symbol")

    risk = state.get("risk_context") or {
        "daily_pnl_ratio": portfolio.get("daily_pnl_ratio", 0.0),
        "open_positions": portfolio.get("open_positions", 0),
        "last_order_epoch": portfolio.get("last_order_epoch", 0),
        "per_trade_risk_ratio": 0.0,
    }
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}

    exec_context = state.get("exec_context") or {"mode": "mock"}

    strategist = state.get("strategist")
    if strategist is None:
        from libs.ai.strategist_factory import get_strategist_from_env
        strategist = get_strategist_from_env()
        state["strategist"] = strategist

    price = market.get("price")
    cash = portfolio.get("cash", 0)
    open_positions = risk.get("open_positions", portfolio.get("open_positions", 0))

    features = {
        "symbol": symbol,
        "price": price,
        "cash": cash,
        "open_positions": open_positions,
        "daily_pnl_ratio": risk.get("daily_pnl_ratio", 0.0),
    }
    signals = {
        "cash_gt_1m": bool(cash and cash > 1_000_000),
        "has_price": price is not None,
        "no_open_positions": bool(int(open_positions or 0) == 0),
    }
    llm_context = _build_llm_context(state, symbol)
    market_for_llm = dict(market)
    market_for_llm["llm_context"] = llm_context
    risk_for_llm = dict(risk)
    risk_for_llm["llm_context"] = {
        "regime": llm_context.get("technical", {}).get("regime"),
        "signal_score": llm_context.get("technical", {}).get("signal_score"),
        "symbol_sentiment_score": llm_context.get("news", {}).get("symbol_sentiment_score"),
        "global_sentiment_score": llm_context.get("news", {}).get("global_sentiment_score"),
        "symbol_sentiment_status": llm_context.get("news", {}).get("symbol_sentiment_status"),
        "global_sentiment_status": llm_context.get("news", {}).get("global_sentiment_status"),
    }

    strategy_name = strategist.__class__.__name__ if strategist is not None else "builtin_rule"
    raw_intent: Dict[str, Any]
    error: str | None = None
    llm_meta: Dict[str, Any] = {}
    static_intent: Dict[str, Any] | None = None
    score_override_applied = False
    strategy_v1_decision: Dict[str, Any] | None = None

    cooldown_remaining = _post_exit_cooldown_remaining_sec(state, open_positions)
    if cooldown_remaining > 0:
        static_intent = {
            "action": "NOOP",
            "reason": "post_exit_cooldown",
            "rationale": f"post_exit_cooldown:{cooldown_remaining}s",
        }
        strategy_name = "CooldownStrategist"

    eod_intent = _resolve_eod_force_liquidation_intent(state=state, portfolio=portfolio, symbol=symbol)
    if static_intent is None and isinstance(eod_intent, dict):
        static_intent = dict(eod_intent)
        strategy_name = "EODLiquidationStrategist"

    # Optional M29+ exit policy path for live loop:
    # when a position is already open and exit policy is enabled,
    # prefer deterministic hold/exit over repeated BUY intents.
    use_exit_policy = _resolve_exit_policy_enabled(state)
    position = _extract_position_for_symbol(portfolio, symbol)
    if static_intent is None and int(open_positions or 0) > 0 and use_exit_policy and isinstance(position, dict):
        qty_pos = int(position.get("qty") or 0)
        avg_price = _to_float(position.get("avg_price"), 0.0)
        px = _to_float(price, 0.0) if price is not None else 0.0
        if qty_pos > 0 and avg_price > 0.0 and px > 0.0:
            exit_policy_cfg = _resolve_exit_policy_config(state)
            news_ctx = llm_context.get("news") if isinstance(llm_context.get("news"), dict) else {}
            if news_ctx:
                exit_policy_cfg["symbol_sentiment_score"] = _to_float(news_ctx.get("symbol_sentiment_score"), 0.0)
                exit_policy_cfg["global_sentiment_score"] = _to_float(news_ctx.get("global_sentiment_score"), 0.0)
            exit_decision = evaluate_exit_policy(
                price=px,
                avg_price=avg_price,
                qty=qty_pos,
                hold_sec=_resolve_position_hold_sec(state),
                policy=exit_policy_cfg,
            )
            reason = str(exit_decision.get("reason") or "hold")
            if bool(exit_decision.get("triggered")):
                static_intent = {
                    "action": "SELL",
                    "symbol": symbol,
                    "qty": qty_pos,
                    "price": price,
                    "order_type": "market",
                    "order_api_id": "ORDER_SUBMIT",
                    "reason": f"exit_policy_{reason}",
                    "rationale": f"exit_policy:{reason}",
                }
            else:
                static_intent = {
                    "action": "NOOP",
                    "reason": "position_hold",
                    "rationale": f"exit_policy:{reason}",
                }
            strategy_name = "ExitPolicyStrategist"

    if static_intent is not None:
        raw_intent = dict(static_intent)
    elif _strategy_v1_enabled(state):
        strategy_v1_name = "regime_momentum_v1"
        try:
            from libs.strategies.v1.registry import build_strategy_v1, resolve_strategy_v1_name

            strategy_v1_name = resolve_strategy_v1_name(policy=policy, llm_context=llm_context)
            strategy, strategy_v1_name = build_strategy_v1(name=strategy_v1_name, policy=policy)
            pos = _extract_position_for_symbol(portfolio, symbol)
            held_qty = int(pos.get("qty") or 0) if isinstance(pos, dict) else 0
            decision = strategy.decide(
                _to_strategy_v1_input(
                    symbol=symbol,
                    llm_context=llm_context,
                    portfolio=portfolio,
                    policy=policy,
                    risk_context=risk,
                ),
                price=_to_float(price, 0.0) if price is not None else None,
                cash=_to_float(cash, 0.0),
                held_qty=held_qty,
            )
            strategy_v1_decision = decision.to_dict()
            raw_intent = _raw_intent_from_strategy_decision(strategy_v1_decision, default_price=price)
            state["strategy_v1_decision"] = dict(strategy_v1_decision)
            state["strategy_v1_name"] = str(strategy_v1_name)
            state["why"] = dict(strategy_v1_decision.get("evidence") or {})
            state["invalidation"] = dict(strategy_v1_decision.get("invalidation") or {})
            strategy_name = strategy.__class__.__name__
        except Exception as e:
            error = str(e)
            raw_intent = {
                "action": "NOOP",
                "reason": "strategy_v1_error",
                "rationale": "strategy_v1_error",
            }
            strategy_name = "StrategyV1"
    elif strategist is not None and hasattr(strategist, "decide"):
        llm_t0 = 0.0
        do_llm_log = strategy_name == "OpenAIStrategist"
        runtime_gate: Dict[str, Any] = {}
        runtime_gate_blocked = False
        runtime_circuit_update: Dict[str, Any] = {}
        if do_llm_log:
            llm_t0 = time.perf_counter()
            try:
                runtime_gate = gate_runtime_circuit(state, scope="strategist")
            except Exception:
                runtime_gate = {}

            if runtime_gate and not bool(runtime_gate.get("allowed", True)):
                runtime_gate_blocked = True
                raw_intent = {"action": "NOOP", "reason": "circuit_open", "rationale": "runtime_circuit_open"}
                llm_meta = {
                    "error": "circuit_open",
                    "error_type": "CircuitOpen",
                    "attempts": 0,
                    "circuit_state": str(runtime_gate.get("circuit_state") or "open"),
                    "circuit_fail_count": int(runtime_gate.get("fail_count") or 0),
                    "circuit_open_until_epoch": int(runtime_gate.get("open_until_epoch") or 0),
                }
        if not runtime_gate_blocked:
            try:
                # Accept both provider StrategyInput and libs.ai.strategist StrategyInput
                try:
                    from libs.ai.strategist import StrategyInput  # type: ignore
                    x = StrategyInput(
                        symbol=str(symbol),
                        market_snapshot=market_for_llm,
                        portfolio_snapshot=portfolio,
                        risk_context=risk_for_llm,
                    )
                except Exception:
                    from libs.ai.providers.openai_provider import StrategyInput  # type: ignore
                    x = StrategyInput(
                        symbol=str(symbol),
                        market_snapshot=market_for_llm,
                        portfolio_snapshot=portfolio,
                        risk_context=risk_for_llm,
                    )

                decision = strategist.decide(x)  # type: ignore[call-arg]
                raw_intent = dict(getattr(decision, "intent", {}) or {})
                m = getattr(decision, "meta", None)
                if isinstance(m, dict):
                    llm_meta = dict(m)
                dec_rationale = str(getattr(decision, "rationale", "") or "").strip()
                if dec_rationale and not str(raw_intent.get("rationale") or "").strip():
                    raw_intent["rationale"] = dec_rationale
            except Exception as e:
                error = str(e)
                # If this is OpenAIStrategist, keep it and return NOOP (do not swap strategy)
                if strategy_name == "OpenAIStrategist":
                    raw_intent = {"action": "NOOP", "reason": "strategist_error", "rationale": error}
                else:
                    from libs.ai.strategist import RuleStrategist
                    strategist = RuleStrategist()
                    state["strategist"] = strategist
                    strategy_name = "RuleStrategist"
                    raw_intent = _rule_intent(symbol, price, cash, open_positions)

        raw_intent = _enforce_rationale_for_trade_intent(raw_intent)

        if do_llm_log:
            # M23-3: runtime circuit integration for strategist path.
            if not runtime_gate_blocked:
                intent_reason_for_cb = str(raw_intent.get("reason") or "").strip().lower()
                meta_error_for_cb = str(llm_meta.get("error") or "").strip()
                llm_failed_for_cb = (
                    bool(error)
                    or bool(meta_error_for_cb)
                    or intent_reason_for_cb in ("strategist_error", "circuit_open", "missing_config")
                )
                try:
                    if llm_failed_for_cb:
                        runtime_circuit_update = mark_runtime_circuit_failure(
                            state,
                            scope="strategist",
                            error_type=str(llm_meta.get("error_type") or "StrategistError"),
                        )
                    else:
                        runtime_circuit_update = mark_runtime_circuit_success(state, scope="strategist")
                except Exception:
                    runtime_circuit_update = {}

                if runtime_circuit_update:
                    llm_meta["circuit_state"] = str(runtime_circuit_update.get("circuit_state") or "")
                    llm_meta["circuit_fail_count"] = int(runtime_circuit_update.get("fail_count") or 0)
                    llm_meta["circuit_open_until_epoch"] = int(runtime_circuit_update.get("open_until_epoch") or 0)

            _sync_legacy_circuit_fields(state, llm_meta)

            latency_ms = int((time.perf_counter() - llm_t0) * 1000)
            intent_reason = str(raw_intent.get("reason") or "")
            meta_error = str(llm_meta.get("error") or "")
            llm_ok = not bool(error) and not bool(meta_error) and intent_reason != "strategist_error"
            payload: Dict[str, Any] = {
                "strategy": strategy_name,
                "provider": str(os.getenv("AI_STRATEGIST_PROVIDER", "rule") or "rule"),
                "model": str(getattr(strategist, "model", "") or ""),
                "latency_ms": latency_ms,
                "ok": bool(llm_ok),
                "intent_action": str(raw_intent.get("action") or ""),
                "intent_reason": intent_reason,
                "intent_rationale": str(raw_intent.get("rationale") or ""),
                "context_regime": llm_context.get("technical", {}).get("regime"),
                "context_signal_score": llm_context.get("technical", {}).get("signal_score"),
                "context_symbol_sentiment_score": llm_context.get("news", {}).get("symbol_sentiment_score"),
                "context_global_sentiment_score": llm_context.get("news", {}).get("global_sentiment_score"),
                "context_symbol_sentiment_status": llm_context.get("news", {}).get("symbol_sentiment_status"),
                "context_symbol_sentiment_source": llm_context.get("news", {}).get("symbol_sentiment_source"),
                "context_symbol_sentiment_reason": llm_context.get("news", {}).get("symbol_sentiment_reason"),
                "context_global_sentiment_status": llm_context.get("news", {}).get("global_sentiment_status"),
                "context_global_sentiment_source": llm_context.get("news", {}).get("global_sentiment_source"),
                "context_global_sentiment_reason": llm_context.get("news", {}).get("global_sentiment_reason"),
                "context_composite_score": llm_context.get("decision_policy", {}).get("composite_score"),
            }
            if getattr(strategist, "endpoint", None):
                payload["endpoint"] = str(getattr(strategist, "endpoint"))
            if llm_meta.get("attempts") is not None:
                payload["attempts"] = int(llm_meta.get("attempts") or 0)
            if llm_meta.get("endpoint_type"):
                payload["endpoint_type"] = str(llm_meta.get("endpoint_type"))
            for tok_key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if llm_meta.get(tok_key) is not None:
                    try:
                        payload[tok_key] = int(float(llm_meta.get(tok_key) or 0))
                    except Exception:
                        pass
            if llm_meta.get("estimated_cost_usd") is not None:
                try:
                    payload["estimated_cost_usd"] = float(llm_meta.get("estimated_cost_usd"))
                except Exception:
                    pass
            if llm_meta.get("circuit_state") is not None:
                payload["circuit_state"] = str(llm_meta.get("circuit_state") or "")
            if llm_meta.get("circuit_fail_count") is not None:
                try:
                    payload["circuit_fail_count"] = int(float(llm_meta.get("circuit_fail_count") or 0))
                except Exception:
                    pass
            if llm_meta.get("circuit_open_until_epoch") is not None:
                try:
                    payload["circuit_open_until_epoch"] = int(float(llm_meta.get("circuit_open_until_epoch") or 0))
                except Exception:
                    pass
            prompt_version = str(
                llm_meta.get("prompt_version") or getattr(strategist, "prompt_version", "") or ""
            )
            if prompt_version:
                payload["prompt_version"] = prompt_version
            schema_version = str(
                llm_meta.get("schema_version") or getattr(strategist, "schema_version", "") or ""
            )
            if schema_version:
                payload["schema_version"] = schema_version
            if llm_meta.get("error_type"):
                payload["error_type"] = str(llm_meta.get("error_type"))
            elif error:
                payload["error_type"] = "Exception"
            _log_llm_call(state, payload)
    else:
        raw_intent = _rule_intent(symbol, price, cash, open_positions)

    raw_intent = _enforce_rationale_for_trade_intent(raw_intent)

    intent, rationale = normalize_intent(raw_intent, default_symbol=str(symbol) if symbol else None, default_price=price)

    if str(intent.get("action") or "").strip().upper() == "NOOP":
        if not str(intent.get("reason") or "").strip():
            if str(raw_intent.get("reason") or "").strip():
                intent["reason"] = str(raw_intent.get("reason") or "").strip()

    intent_overridden, score_override_applied = _maybe_override_noop_by_score(
        intent=intent,
        llm_context=llm_context,
        symbol=symbol,
        price=price,
        open_positions=open_positions,
        portfolio=portfolio,
    )
    if score_override_applied:
        intent, rationale = normalize_intent(intent_overridden, default_symbol=str(symbol) if symbol else None, default_price=price)
        raw_intent = dict(intent_overridden)

    intent, rationale, sell_timing_guard = _apply_sell_timing_guard(
        state=state,
        intent=intent,
        raw_intent=raw_intent,
    )

    # Safety: if a position is already open, block additional BUY intents.
    try:
        action = str(intent.get("action") or "").strip().upper()
        if action == "BUY" and int(open_positions or 0) > 0:
            intent["action"] = "NOOP"
            intent["qty"] = 0
            intent["reason"] = "position_already_open"
            rationale = "position_already_open"
    except Exception:
        pass

    if not str(intent.get("reason") or "").strip():
        fallback_reason = str(raw_intent.get("reason") or "").strip()
        if fallback_reason:
            intent["reason"] = fallback_reason
    intent["signal_source"] = str(strategy_name or "")
    pos_age = _resolve_position_hold_sec(state)
    if pos_age is not None:
        intent["position_age_sec"] = int(pos_age)
    intent.setdefault("intent_id", _ensure_run_id(state))

    packet_why = _build_packet_why(state=state, llm_context=llm_context)
    packet_invalidation = _build_packet_invalidation(state=state)
    packet_sizing_inputs = {}
    if strategy_v1_decision is not None and isinstance(strategy_v1_decision.get("sizing_inputs"), dict):
        packet_sizing_inputs = dict(strategy_v1_decision.get("sizing_inputs") or {})

    packet = {
        "intent": intent,
        "risk": risk,
        "exec_context": exec_context,
        # additive explainability aliases for operator-facing consumers
        "action": str(intent.get("action") or "").strip().upper(),
        "symbol": str(intent.get("symbol") or "").strip().upper(),
        "qty": int(intent.get("qty") or 0),
        "why": packet_why,
        "invalidation": packet_invalidation,
        "sizing_inputs": packet_sizing_inputs,
    }
    trace = {
        "features": features,
        "signals": signals,
        "rationale": rationale,
        "strategy": strategy_name,
        "raw_intent": raw_intent,
        "llm_context": llm_context,
        "score_override_applied": bool(score_override_applied),
        "sell_timing_guard": sell_timing_guard,
        "why": packet_why,
        "invalidation": packet_invalidation,
    }
    if strategy_v1_decision is not None:
        trace["strategy_v1_decision"] = dict(strategy_v1_decision)
        trace["strategy_v1_name"] = str(state.get("strategy_v1_name") or "")
    if error:
        trace["error"] = error

    state["decision_packet"] = packet
    state["decision_trace"] = trace
    _log_decision(state, packet, trace)
    return state
