from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


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

    pol = state.get("policy")
    if isinstance(pol, dict):
        pgs = pol.get("global_sentiment")
        if isinstance(pgs, dict) and "score" in pgs:
            try:
                return _clamp(float(pgs.get("score") or 0.0), -1.0, 1.0)
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

        # Score boost: positive news & risk-on regime lift score.
        adj_score = base_score + w["weight_news"] * news_s + w["weight_global"] * gs

        # Risk penalty: negative news and risk-off (global<0) increase risk.
        neg_news = max(-news_s, 0.0)
        neg_global = max(-gs, 0.0)
        adj_risk = base_risk + w["risk_news_penalty"] * neg_news + w["risk_global_penalty"] * neg_global

        # Confidence: small boost from positive news (kept tiny by default).
        adj_conf = _clamp(base_conf + w["confidence_news_boost"] * max(news_s, 0.0), 0.0, 1.0)

        row["score"] = float(adj_score)
        row["risk_score"] = float(_clamp(adj_risk, 0.0, 1.0))
        row["confidence"] = float(adj_conf)
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

    return state
