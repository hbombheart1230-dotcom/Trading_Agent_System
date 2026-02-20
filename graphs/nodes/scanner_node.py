from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

from graphs.nodes.skill_contracts import (
    CONTRACT_VERSION as SKILL_CONTRACT_VERSION,
    extract_account_orders_rows,
    extract_market_quotes,
    norm_symbol,
)
from libs.runtime.feature_engine import build_feature_map


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _norm_symbol(v: Any) -> str:
    return norm_symbol(v)


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
      1) state['mock_global_sentiment'] (tests)
      2) state['global_sentiment']['score'] (precomputed)
      3) state['policy']['global_sentiment']['score'] (set by strategist)
      4) default 0.0
    """
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
    """Return per-symbol news sentiment map in [-1, +1]."""
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
            built = build_feature_map(
                ohlcv,
                trend_gap_threshold=trend_gap_threshold,
                high_vol_threshold=high_vol_threshold,
            )
            return {_norm_symbol(k): v for k, v in built.items() if _norm_symbol(k)}, "state.ohlcv_by_symbol", errors
        except Exception as e:
            errors.append(f"feature_engine:error:{type(e).__name__}")

    return {}, "none", errors


def scanner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Graph node: Scanner (Data + feature extraction).

    M17-3 contract:
      - Reads state['candidates'] produced by strategist_node
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
    candidates = state.get("candidates") or []
    if not isinstance(candidates, list):
        candidates = []

    mock: Optional[Mapping[str, Any]] = state.get("mock_scan_results")  # for tests

    # M18-4: sentiment-aware scoring (offline-friendly)
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    w = _get_scanner_weights(policy)
    gs = _get_global_sentiment_score(state)
    news_by_sym = _get_news_sentiment_map(state)
    skill_quotes, quote_meta = _extract_skill_quotes(state)
    skill_order_counts, skill_order_rows, order_meta = _extract_account_open_order_counts(state)
    feature_map, feature_source, feature_errors = _extract_feature_engine_map(state)

    scan_results: List[Dict[str, Any]] = []

    for item in candidates:
        if isinstance(item, dict):
            symbol = str(item.get("symbol") or "")
        else:
            symbol = str(item)

        if not symbol:
            continue

        if isinstance(mock, Mapping) and symbol in mock:
            row = dict(mock[symbol])
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

        # ---- M18-4: apply sentiment adjustments ----
        base_score = float(row.get("score") or 0.0)
        base_risk = float(row.get("risk_score") or 0.0)
        base_conf = float(row.get("confidence") or 0.0)

        news_s = float(news_by_sym.get(symbol, 0.0))
        quote = skill_quotes.get(_norm_symbol(symbol), {})
        quote_price = quote.get("price")
        if quote_price is None:
            quote_price = quote.get("cur")
        try:
            quote_price_num = float(quote_price) if quote_price is not None else None
        except Exception:
            quote_price_num = None
        open_orders = int(skill_order_counts.get(_norm_symbol(symbol), 0))
        order_penalty = min(open_orders, 3)
        quote_bonus = 0.02 if (quote_price_num is not None and quote_price_num > 0) else 0.0
        feature_row = feature_map.get(_norm_symbol(symbol), {})
        if not isinstance(feature_row, dict):
            feature_row = {}
        try:
            feature_signal = _clamp(float(feature_row.get("signal_score") or 0.0), -1.0, 1.0)
        except Exception:
            feature_signal = 0.0
        feature_regime = str(feature_row.get("regime") or "").strip().lower()

        # Score boost: positive news & risk-on regime lift score.
        adj_score = (
            base_score
            + w["weight_news"] * news_s
            + w["weight_global"] * gs
            + w["feature_score_weight"] * feature_signal
            + quote_bonus
            - 0.05 * order_penalty
        )

        # Risk penalty: negative news and risk-off (global<0) increase risk.
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
            + 0.10 * order_penalty
        )

        # Confidence: small boost from positive news (kept tiny by default).
        adj_conf = _clamp(base_conf + w["confidence_news_boost"] * max(news_s, 0.0) - 0.05 * order_penalty, 0.0, 1.0)

        row["score"] = float(adj_score)
        row["risk_score"] = float(_clamp(adj_risk, 0.0, 1.0))
        row["confidence"] = float(adj_conf)
        row.setdefault("features", {})
        if isinstance(row.get("features"), dict):
            row["features"].update(
                {
                    "skill_quote_price": quote_price_num,
                    "skill_open_orders": open_orders,
                    "engine_rsi14": feature_row.get("rsi14"),
                    "engine_ma20_gap": feature_row.get("ma20_gap"),
                    "engine_atr14": feature_row.get("atr14"),
                    "engine_volume_spike20": feature_row.get("volume_spike20"),
                    "engine_volatility20": feature_row.get("volatility20"),
                    "engine_regime": feature_row.get("regime"),
                    "engine_signal_score": feature_signal,
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
                    "skill_quote_bonus": quote_bonus,
                    "skill_open_orders": open_orders,
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
    state["selected"] = selected

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

    return state
