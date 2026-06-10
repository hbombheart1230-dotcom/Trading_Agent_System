"""Global sentiment computation.

- Priority:
  1) state['mock_global_sentiment'] if provided
  2) DRY_RUN => 0.0
  3) LIVE best-effort via yfinance (optional dependency)

The canonical output remains a normalized signal contract, but now includes
additive index-move evidence so Strategist can reason from:
- S&P500 daily change
- Nasdaq daily change
- Dow daily change
- VIX level / daily change
- DXY daily change
- US 10Y yield delta
"""

from __future__ import annotations

import math
import os
import time
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from libs.data_quality.signal_contract import (
    SIGNAL_STATUS_FALLBACK,
    SIGNAL_STATUS_OK,
    SIGNAL_STATUS_UNAVAILABLE,
    make_signal,
)


def _is_dry_run() -> bool:
    v = str(os.getenv("DRY_RUN", "")).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _tanh_norm(x: float, scale: float = 5.0) -> float:
    # Smoothly map to [-1, 1]
    return _clamp(math.tanh(scale * x), -1.0, 1.0)


@dataclass(frozen=True)
class SentimentInputs:
    sp500_ret: float
    nasdaq_ret: float
    dow_ret: float
    vix_ret: float
    vix_level: float
    dxy_ret: float
    tnx_delta: float  # change in 10Y yield (percentage points-ish)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _compute_raw(
    inputs: SentimentInputs,
    w_sp: float,
    w_nq: float,
    w_dow: float,
    w_vix: float,
    w_vix_level: float,
    w_dxy: float,
    w_tnx: float,
    vix_neutral_level: float,
) -> float:
    # Risk-on: equities up, DXY down, yields down
    # - VIX up / elevated => risk-off => subtract
    # - DXY up => risk-off => subtract
    # - TNX up => tighter => subtract
    vix_ret = float(getattr(inputs, "vix_ret", 0.0) or 0.0)
    vix_level = float(getattr(inputs, "vix_level", 0.0) or 0.0)
    neutral_vix = max(1.0, float(vix_neutral_level or 20.0))
    vix_level_pressure = max(0.0, min((vix_level - neutral_vix) / neutral_vix, 2.0))
    return (
        w_sp * inputs.sp500_ret
        + w_nq * inputs.nasdaq_ret
        + w_dow * inputs.dow_ret
        - w_vix * vix_ret
        - w_vix_level * vix_level_pressure
        - w_dxy * inputs.dxy_ret
        - w_tnx * inputs.tnx_delta
    )


def _compute_korea_raw(korea_indices: Optional[Dict[str, Any]], *, w_kospi: float, w_kosdaq: float) -> float:
    packet = korea_indices if isinstance(korea_indices, dict) else {}
    indices = packet.get("indices") if isinstance(packet.get("indices"), dict) else {}
    kospi = indices.get("KOSPI") if isinstance(indices.get("KOSPI"), dict) else {}
    kosdaq = indices.get("KOSDAQ") if isinstance(indices.get("KOSDAQ"), dict) else {}
    kospi_ret = _as_float(kospi.get("change_pct"), 0.0) / 100.0
    kosdaq_ret = _as_float(kosdaq.get("change_pct"), 0.0) / 100.0
    return (float(w_kospi) * kospi_ret) + (float(w_kosdaq) * kosdaq_ret)


def _normalize_korea_index_packet(raw: Any) -> Optional[Dict[str, Any]]:
    packet = raw if isinstance(raw, dict) else {}
    indices = packet.get("indices") if isinstance(packet.get("indices"), dict) else {}
    if not indices:
        return None
    out_indices: Dict[str, Dict[str, Any]] = {}
    change_values = []
    rising = falling = unchanged = 0
    for name in ("KOSPI", "KOSDAQ", "KOSPI200"):
        row = indices.get(name) if isinstance(indices.get(name), dict) else {}
        if not row:
            continue
        item = dict(row)
        if item.get("change_pct") not in (None, ""):
            change_values.append(_as_float(item.get("change_pct"), 0.0))
        rising += int(_as_float(item.get("rising"), 0.0))
        falling += int(_as_float(item.get("falling"), 0.0))
        unchanged += int(_as_float(item.get("unchanged"), 0.0))
        out_indices[name] = item
    if not out_indices:
        return None
    breadth_total = rising + falling + unchanged
    normalized = dict(packet)
    normalized["indices"] = out_indices
    normalized.setdefault("source", "provided")
    normalized.setdefault("status", "ok")
    normalized["average_change_pct"] = (
        float(sum(change_values) / len(change_values)) if change_values else packet.get("average_change_pct")
    )
    normalized["breadth"] = (
        float((rising - falling) / breadth_total) if breadth_total > 0 else packet.get("breadth")
    )
    normalized["rising"] = rising
    normalized["falling"] = falling
    normalized["unchanged"] = unchanged
    return normalized


def _fetch_korea_index_inputs(state: Dict[str, Any], policy: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for key in ("mock_korea_indices", "korea_index_context", "korea_indices", "kiwoom_market_indices"):
        packet = _normalize_korea_index_packet(state.get(key))
        if packet:
            return packet

    enabled = policy.get("use_korea_indices")
    if enabled is None:
        enabled = os.getenv("KOREA_INDEX_CONTEXT_ENABLED", "true")
    if str(enabled).strip().lower() in {"0", "false", "no", "n", "off"}:
        return None

    try:
        from libs.read.kiwoom_market_index_reader import KiwoomMarketIndexReader

        return _normalize_korea_index_packet(KiwoomMarketIndexReader.from_env().get_index_packet())
    except Exception:
        return None


def _fetch_last2_closes_yfinance(ticker: str) -> Optional[Tuple[float, float]]:
    """Return (prev_close, last_close) for ticker, or None on failure."""
    try:
        import yfinance as yf  # optional
    except Exception:
        return None

    try:
        # 5d window to be resilient to holidays; use Close series
        hist = yf.Ticker(ticker).history(period="5d", interval="1d")
        if hist is None or hist.empty:
            return None
        closes = hist["Close"].dropna().tolist()
        if len(closes) < 2:
            return None
        return float(closes[-2]), float(closes[-1])
    except Exception:
        return None


def _pct_change(pair: Optional[Tuple[float, float]]) -> Optional[float]:
    if not pair:
        return None
    prev, last = pair
    if float(prev or 0.0) == 0.0:
        return None
    return float((float(last) / float(prev)) - 1.0)


def _indicator_from_pair(
    *,
    key: str,
    label: str,
    category: str,
    source: str,
    ticker: str,
    pair: Optional[Tuple[float, float]],
    unit: str,
    role: str,
    transform: str = "pct",
) -> Dict[str, Any]:
    if not pair:
        return {
            "key": key,
            "label": label,
            "category": category,
            "source": source,
            "ticker": ticker,
            "status": "unavailable",
            "reason": "fetch_failed_or_not_configured",
            "unit": unit,
            "role": role,
        }
    prev, last = float(pair[0]), float(pair[1])
    row: Dict[str, Any] = {
        "key": key,
        "label": label,
        "category": category,
        "source": source,
        "ticker": ticker,
        "status": "ok",
        "previous": prev,
        "current": last,
        "unit": unit,
        "role": role,
    }
    if transform == "yield_delta":
        scale = 10.0 if max(abs(last), abs(prev)) > 20.0 else 1.0
        row["delta"] = float((last - prev) / scale)
        row["current_yield_pct"] = float(last / scale)
        row["previous_yield_pct"] = float(prev / scale)
    else:
        pct = _pct_change(pair)
        row["change_pct"] = float(pct * 100.0) if pct is not None else None
    return row


def _indicator_from_korea_index(key: str, label: str, row: Dict[str, Any]) -> Dict[str, Any]:
    if not row:
        return {
            "key": key,
            "label": label,
            "category": "equity_index",
            "source": "kiwoom.ka20009",
            "status": "unavailable",
            "reason": "korea_index_missing",
            "unit": "index_point",
            "role": "korea_equity_market_direction",
        }
    return {
        "key": key,
        "label": label,
        "category": "equity_index",
        "source": str(row.get("source") or "kiwoom.ka20009"),
        "ticker": str(row.get("code") or ""),
        "status": "ok",
        "current": row.get("current"),
        "previous": row.get("previous_close"),
        "change": row.get("change"),
        "change_pct": row.get("change_pct"),
        "unit": "index_point",
        "role": "korea_equity_market_direction",
        "current_date": str(row.get("current_date") or ""),
        "previous_date": str(row.get("previous_date") or ""),
    }


def _indicator_from_override(key: str, base: Dict[str, Any], override: Any) -> Dict[str, Any]:
    if not isinstance(override, dict):
        return base
    out = dict(base)
    for field in (
        "source",
        "ticker",
        "status",
        "reason",
        "previous",
        "current",
        "change",
        "change_pct",
        "delta",
        "current_yield_pct",
        "previous_yield_pct",
        "asof",
    ):
        if override.get(field) not in (None, ""):
            out[field] = override.get(field)
    if out.get("current") not in (None, "") or out.get("current_yield_pct") not in (None, ""):
        out["status"] = str(override.get("status") or "ok")
        if str(out.get("reason") or "") in {"no_provider_configured", "fetch_failed_or_not_configured"}:
            out["reason"] = str(override.get("reason") or "override")
        else:
            out["reason"] = str(out.get("reason") or override.get("reason") or "override")
    out["key"] = key
    return out


def _fetch_extended_macro_indicators(
    state: Dict[str, Any],
    policy: Dict[str, Any],
    *,
    inputs: Optional[SentimentInputs],
    korea_indices: Optional[Dict[str, Any]],
    krx_night_futures: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    tickers = dict(policy.get("macro_indicator_tickers") or {})
    defaults = {
        "us_2y_yield": "^IRX",
        "us_10y_yield": "^TNX",
        "dxy": "DX-Y.NYB",
        "usdkrw": "KRW=X",
        "eurusd": "EURUSD=X",
        "usdcny": "CNY=X",
        "usdjpy": "JPY=X",
        "sp500": "^GSPC",
        "nasdaq": "^IXIC",
    }
    defaults.update({k: str(v) for k, v in tickers.items() if str(v or "").strip()})
    korea_rows = (
        (korea_indices or {}).get("indices")
        if isinstance((korea_indices or {}).get("indices"), dict)
        else {}
    )
    indicators: Dict[str, Any] = {
        "kr_3y_yield": {
            "key": "kr_3y_yield",
            "label": "Korea 3Y government bond yield",
            "category": "interest_rate",
            "source": "not_configured",
            "status": "unavailable",
            "reason": "no_provider_configured",
            "unit": "yield_pct",
            "role": "korea_policy_rate_expectation",
        },
        "kr_10y_yield": {
            "key": "kr_10y_yield",
            "label": "Korea 10Y government bond yield",
            "category": "interest_rate",
            "source": "not_configured",
            "status": "unavailable",
            "reason": "no_provider_configured",
            "unit": "yield_pct",
            "role": "korea_inflation_and_duration_expectation",
        },
        "kospi": _indicator_from_korea_index("kospi", "KOSPI", korea_rows.get("KOSPI") if isinstance(korea_rows, dict) else {}),
        "kosdaq": _indicator_from_korea_index("kosdaq", "KOSDAQ", korea_rows.get("KOSDAQ") if isinstance(korea_rows, dict) else {}),
        "kospi200": _indicator_from_korea_index("kospi200", "KOSPI200", korea_rows.get("KOSPI200") if isinstance(korea_rows, dict) else {}),
    }
    night = krx_night_futures if isinstance(krx_night_futures, dict) else {}
    indicators["krx_night_futures"] = {
        "key": "krx_night_futures",
        "label": "KRX KOSPI200 night futures",
        "category": "derivatives",
        "source": str(night.get("source") or "not_configured"),
        "status": str(night.get("status") or "unavailable"),
        "reason": str(night.get("reason") or ""),
        "current": night.get("current"),
        "previous": night.get("previous"),
        "change": night.get("change"),
        "change_pct": night.get("change_pct"),
        "basis": night.get("basis"),
        "direction_pressure": str(night.get("direction_pressure") or ""),
        "unit": "index_point",
        "role": "preopen_korea_derivatives_pressure",
        "behavior_effect": "observation_only",
        "trading_action_allowed": False,
    }
    overrides = {}
    for source in (
        state.get("macro_indicators"),
        state.get("macro_indicator_overrides"),
        policy.get("macro_indicators"),
        policy.get("macro_indicator_overrides"),
    ):
        if isinstance(source, dict):
            nested = source.get("indicators") if isinstance(source.get("indicators"), dict) else source
            overrides.update({str(k): v for k, v in nested.items() if isinstance(v, dict)})
    try:
        from libs.market.korea_bond_yields import fetch_korea_bond_yield_overrides

        for key, value in fetch_korea_bond_yield_overrides(policy).items():
            if isinstance(value, dict) and not isinstance(overrides.get(key), dict):
                overrides[key] = value
    except Exception:
        pass
    for key in ("kr_3y_yield", "kr_10y_yield"):
        indicators[key] = _indicator_from_override(key, indicators[key], overrides.get(key))

    for key, label, category, unit, role, transform in (
        ("us_2y_yield", "US 2Y Treasury yield", "interest_rate", "yield_pct", "us_policy_rate_expectation", "yield_delta"),
        ("us_10y_yield", "US 10Y Treasury yield", "interest_rate", "yield_pct", "us_inflation_and_duration_expectation", "yield_delta"),
        ("dxy", "Dollar Index", "fx", "index_point", "global_dollar_strength", "pct"),
        ("usdkrw", "USD/KRW", "fx", "fx_rate", "won_vs_dollar_pressure", "pct"),
        ("eurusd", "EUR/USD", "fx", "fx_rate", "euro_cross_rate", "pct"),
        ("usdcny", "USD/CNY", "fx", "fx_rate", "yuan_cross_rate", "pct"),
        ("usdjpy", "USD/JPY", "fx", "fx_rate", "yen_cross_rate", "pct"),
        ("sp500", "S&P 500", "equity_index", "index_point", "us_equity_market_direction", "pct"),
        ("nasdaq", "NASDAQ Composite", "equity_index", "index_point", "us_tech_risk_appetite", "pct"),
    ):
        ticker = str(defaults.get(key) or "").strip()
        pair: Optional[Tuple[float, float]]
        if key == "us_10y_yield" and inputs is not None:
            pair = _fetch_last2_closes_yfinance(ticker)
        elif key == "dxy" and inputs is not None:
            pair = _fetch_last2_closes_yfinance(ticker)
        elif key == "sp500" and inputs is not None:
            pair = _fetch_last2_closes_yfinance(ticker)
        elif key == "nasdaq" and inputs is not None:
            pair = _fetch_last2_closes_yfinance(ticker)
        else:
            pair = _fetch_last2_closes_yfinance(ticker) if ticker else None
        indicators[key] = _indicator_from_pair(
            key=key,
            label=label,
            category=category,
            source="yfinance" if ticker else "not_configured",
            ticker=ticker,
            pair=pair,
            unit=unit,
            role=role,
            transform=transform,
        )
        if key == "us_2y_yield" and ticker == "^IRX":
            indicators[key]["source_note"] = "default_yfinance_proxy; override macro_indicator_tickers.us_2y_yield for a true 2Y source"
        indicators[key] = _indicator_from_override(key, indicators[key], overrides.get(key))

    return {
        "schema_version": "macro_indicators.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "kiwoom.ka20009+yfinance",
        "indicators": indicators,
    }


def _write_macro_indicator_log(payload: Dict[str, Any], *, policy: Dict[str, Any]) -> None:
    enabled = policy.get("macro_indicator_log_enabled")
    if enabled is None:
        enabled = os.getenv("MACRO_INDICATOR_LOG_ENABLED", "true")
    if str(enabled).strip().lower() in {"0", "false", "no", "n", "off"}:
        return
    if os.getenv("PYTEST_CURRENT_TEST"):
        return
    try:
        root = Path(str(policy.get("macro_indicator_log_root") or "data/logs/macro_indicators"))
        now = datetime.now(timezone(timedelta(hours=9)))
        day_dir = root / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        (day_dir / f"{now.strftime('%H%M%S')}_macro_indicators.json").write_text(content, encoding="utf-8")
        (day_dir / "latest.json").write_text(content, encoding="utf-8")
    except Exception:
        return


def _fetch_inputs(policy: Dict[str, Any]) -> Optional[SentimentInputs]:
    tick_sp = str(policy.get("sentiment_ticker_sp500") or "^GSPC")
    tick_nq = str(policy.get("sentiment_ticker_nasdaq") or "^IXIC")
    tick_dow = str(policy.get("sentiment_ticker_dow") or "^DJI")
    tick_vix = str(policy.get("sentiment_ticker_vix") or "^VIX")
    tick_dxy = str(policy.get("sentiment_ticker_dxy") or "DX-Y.NYB")
    tick_tnx = str(policy.get("sentiment_ticker_tnx") or "^TNX")

    sp = _fetch_last2_closes_yfinance(tick_sp)
    nq = _fetch_last2_closes_yfinance(tick_nq)
    dow = _fetch_last2_closes_yfinance(tick_dow)
    vix = _fetch_last2_closes_yfinance(tick_vix)
    dxy = _fetch_last2_closes_yfinance(tick_dxy)
    tnx = _fetch_last2_closes_yfinance(tick_tnx)

    if not (sp and nq and dow and dxy and tnx):
        return None

    sp_ret = (sp[1] / sp[0]) - 1.0 if sp[0] != 0 else 0.0
    nq_ret = (nq[1] / nq[0]) - 1.0 if nq[0] != 0 else 0.0
    dow_ret = (dow[1] / dow[0]) - 1.0 if dow[0] != 0 else 0.0
    vix_ret = (vix[1] / vix[0]) - 1.0 if vix and vix[0] != 0 else 0.0
    vix_level = float(vix[1]) if vix else 0.0
    dxy_ret = (dxy[1] / dxy[0]) - 1.0 if dxy[0] != 0 else 0.0

    # ^TNX is typically 10Y yield * 10 (e.g., 45 => 4.5%).
    # Convert delta to "percentage points" approx: delta / 10.
    tnx_delta = (tnx[1] - tnx[0]) / 10.0

    return SentimentInputs(
        sp500_ret=sp_ret,
        nasdaq_ret=nq_ret,
        dow_ret=dow_ret,
        vix_ret=vix_ret,
        vix_level=vix_level,
        dxy_ret=dxy_ret,
        tnx_delta=tnx_delta,
    )


def _sentiment_evidence(
    inputs: Optional[SentimentInputs],
    weights: Dict[str, float],
    raw: float,
    *,
    korea_indices: Optional[Dict[str, Any]] = None,
    macro_indicators: Optional[Dict[str, Any]] = None,
    krx_night_futures: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    korea_packet = korea_indices if isinstance(korea_indices, dict) else {}
    korea_rows = korea_packet.get("indices") if isinstance(korea_packet.get("indices"), dict) else {}
    kospi = korea_rows.get("KOSPI") if isinstance(korea_rows.get("KOSPI"), dict) else {}
    kosdaq = korea_rows.get("KOSDAQ") if isinstance(korea_rows.get("KOSDAQ"), dict) else {}
    kospi200 = korea_rows.get("KOSPI200") if isinstance(korea_rows.get("KOSPI200"), dict) else {}
    night = krx_night_futures if isinstance(krx_night_futures, dict) else {}
    components = {
        "sp500_ret": float(inputs.sp500_ret) if inputs is not None else 0.0,
        "nasdaq_ret": float(inputs.nasdaq_ret) if inputs is not None else 0.0,
        "dow_ret": float(inputs.dow_ret) if inputs is not None else 0.0,
        "vix_ret": float(getattr(inputs, "vix_ret", 0.0) or 0.0) if inputs is not None else 0.0,
        "vix_level": float(getattr(inputs, "vix_level", 0.0) or 0.0) if inputs is not None else 0.0,
        "dxy_ret": float(inputs.dxy_ret) if inputs is not None else 0.0,
        "tnx_delta": float(inputs.tnx_delta) if inputs is not None else 0.0,
        "kospi_ret": _as_float(kospi.get("change_pct"), 0.0) / 100.0 if kospi else 0.0,
        "kosdaq_ret": _as_float(kosdaq.get("change_pct"), 0.0) / 100.0 if kosdaq else 0.0,
        "kospi200_ret": _as_float(kospi200.get("change_pct"), 0.0) / 100.0 if kospi200 else 0.0,
        "krx_night_futures_ret": _as_float(night.get("change_pct"), 0.0) / 100.0 if night else 0.0,
    }
    equity_avg = (components["sp500_ret"] + components["nasdaq_ret"] + components["dow_ret"]) / 3.0
    neutral_vix = max(1.0, float(weights.get("vix_neutral_level", 20.0) or 20.0))
    vix_level_pressure = max(0.0, min((components["vix_level"] - neutral_vix) / neutral_vix, 2.0))
    return {
        "weights": {
            "sp500": float(weights.get("sp500", 0.0)),
            "nasdaq": float(weights.get("nasdaq", 0.0)),
            "dow": float(weights.get("dow", 0.0)),
            "vix": float(weights.get("vix", 0.0)),
            "vix_level": float(weights.get("vix_level", 0.0)),
            "dxy": float(weights.get("dxy", 0.0)),
            "tnx": float(weights.get("tnx", 0.0)),
            "kospi": float(weights.get("kospi", 0.0)),
            "kosdaq": float(weights.get("kosdaq", 0.0)),
            "vix_neutral_level": float(weights.get("vix_neutral_level", 20.0)),
        },
        "components": dict(components),
        "index_moves": {
            "sp500_pct": float(components["sp500_ret"] * 100.0),
            "nasdaq_pct": float(components["nasdaq_ret"] * 100.0),
            "dow_pct": float(components["dow_ret"] * 100.0),
            "kospi_pct": float(components["kospi_ret"] * 100.0),
            "kosdaq_pct": float(components["kosdaq_ret"] * 100.0),
            "kospi200_pct": float(components["kospi200_ret"] * 100.0),
            "krx_night_futures_pct": float(components["krx_night_futures_ret"] * 100.0),
        },
        "macro_moves": {
            "vix_pct": float(components["vix_ret"] * 100.0),
            "vix_level": float(components["vix_level"]),
            "vix_level_pressure": float(vix_level_pressure),
            "dxy_pct": float(components["dxy_ret"] * 100.0),
            "tnx_delta": float(components["tnx_delta"]),
        },
        "fear_index": {
            "provider": "yfinance",
            "ticker": "^VIX",
            "level": float(components["vix_level"]),
            "change_pct": float(components["vix_ret"] * 100.0),
            "neutral_level": float(neutral_vix),
            "level_pressure": float(vix_level_pressure),
        },
        "equity_breadth": {
            "equity_index_average_pct": float(equity_avg * 100.0),
            "equity_advancing": int(sum(1 for v in (components["sp500_ret"], components["nasdaq_ret"], components["dow_ret"]) if v > 0.0)),
        },
        "raw_score": float(raw),
        "korea_indices": dict(korea_packet or {}),
        "krx_night_futures": dict(night or {}),
        "macro_indicators": dict(macro_indicators or {}),
    }


def _signal_with_evidence(
    *,
    score: float,
    status: str,
    source: str,
    reason: str,
    ts: int,
    inputs: Optional[SentimentInputs],
    weights: Dict[str, float],
    raw_score: float,
    korea_indices: Optional[Dict[str, Any]] = None,
    macro_indicators: Optional[Dict[str, Any]] = None,
    krx_night_futures: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    signal = make_signal(score=score, status=status, source=source, reason=reason, ts=ts)
    signal.update(
        _sentiment_evidence(
            inputs,
            weights,
            raw_score,
            korea_indices=korea_indices,
            macro_indicators=macro_indicators,
            krx_night_futures=krx_night_futures,
        )
    )
    _write_macro_indicator_log(
        {
            "schema_version": "global_sentiment_macro_snapshot.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "global_sentiment": {
                "score": signal.get("score"),
                "status": signal.get("status"),
                "source": signal.get("source"),
                "reason": signal.get("reason"),
                "ts": signal.get("ts"),
            },
            "index_moves": signal.get("index_moves"),
            "macro_moves": signal.get("macro_moves"),
            "korea_indices": signal.get("korea_indices"),
            "krx_night_futures": signal.get("krx_night_futures"),
            "macro_indicators": signal.get("macro_indicators"),
        },
        policy=weights.get("_policy", {}) if isinstance(weights.get("_policy"), dict) else {},
    )
    return signal


def compute_global_sentiment(state: Dict[str, Any], policy: Optional[Dict[str, Any]] = None) -> float:
    """Compute global sentiment in [-1, 1].

    Policy knobs (all optional):
      - sentiment_weights: dict with keys {sp500, nasdaq, dow, vix, vix_level, dxy, tnx, vix_neutral_level}
        defaults: 0.30, 0.35, 0.20, 0.10, 0.08, 0.075, 0.075, 20.0
    - sentiment_norm: dict with key {scale} for tanh scale (default 5.0)
    - sentiment_ticker_sp500 / nasdaq / dow / vix / dxy / tnx: override tickers
    """
    signal = compute_global_sentiment_signal(state=state, policy=policy)
    status = str(signal.get("status") or "").strip().lower()
    # Do not silently collapse unavailable data into neutral value.
    if status == SIGNAL_STATUS_UNAVAILABLE:
        return float("nan")
    try:
        return _clamp(float(signal.get("score", 0.0)))
    except Exception:
        return 0.0


def compute_global_sentiment_signal(state: Dict[str, Any], policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compute global sentiment as normalized signal contract.

    Contract:
      {
        "score": float [-1, +1],
        "status": "ok" | "fallback" | "unavailable",
        "source": str,
        "reason": str,
        "ts": int(epoch)
      }
    """
    policy = dict(policy or {})
    now = int(time.time())

    # 1) explicit mock (tests)
    if state.get("mock_global_sentiment") is not None:
        try:
            weights = {"sp500": 0.30, "nasdaq": 0.35, "dow": 0.20, "vix": 0.10, "vix_level": 0.08, "dxy": 0.075, "tnx": 0.075, "kospi": 0.30, "kosdaq": 0.25, "vix_neutral_level": 20.0}
            weights["_policy"] = policy
            return _signal_with_evidence(
                score=_clamp(float(state["mock_global_sentiment"])),
                status=SIGNAL_STATUS_OK,
                source="mock_global_sentiment",
                reason="",
                ts=now,
                inputs=None,
                weights=weights,
                raw_score=float(state["mock_global_sentiment"]),
            )
        except Exception:
            weights = {"sp500": 0.30, "nasdaq": 0.35, "dow": 0.20, "vix": 0.10, "vix_level": 0.08, "dxy": 0.075, "tnx": 0.075, "kospi": 0.30, "kosdaq": 0.25, "vix_neutral_level": 20.0}
            weights["_policy"] = policy
            return _signal_with_evidence(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source="mock_global_sentiment",
                reason="invalid_mock_value",
                ts=now,
                inputs=None,
                weights=weights,
                raw_score=0.0,
            )

    # 2) DRY_RUN => no network
    if _is_dry_run():
        weights = {"sp500": 0.30, "nasdaq": 0.35, "dow": 0.20, "vix": 0.10, "vix_level": 0.08, "dxy": 0.075, "tnx": 0.075, "kospi": 0.30, "kosdaq": 0.25, "vix_neutral_level": 20.0}
        weights["_policy"] = policy
        return _signal_with_evidence(
            score=0.0,
            status=SIGNAL_STATUS_FALLBACK,
            source="dry_run_policy",
            reason="dry_run_neutral",
            ts=now,
            inputs=None,
            weights=weights,
            raw_score=0.0,
        )

    weights = dict(policy.get("sentiment_weights") or {})
    w_sp = float(weights.get("sp500", 0.30))
    w_nq = float(weights.get("nasdaq", 0.35))
    w_dow = float(weights.get("dow", 0.20))
    w_vix = float(weights.get("vix", 0.10))
    w_vix_level = float(weights.get("vix_level", 0.08))
    w_dxy = float(weights.get("dxy", 0.075))
    w_tnx = float(weights.get("tnx", 0.075))
    w_kospi = float(weights.get("kospi", 0.30))
    w_kosdaq = float(weights.get("kosdaq", 0.25))
    vix_neutral_level = float(weights.get("vix_neutral_level", 20.0))
    resolved_weights = {
        "sp500": w_sp,
        "nasdaq": w_nq,
        "dow": w_dow,
        "vix": w_vix,
        "vix_level": w_vix_level,
        "dxy": w_dxy,
        "tnx": w_tnx,
        "kospi": w_kospi,
        "kosdaq": w_kosdaq,
        "vix_neutral_level": vix_neutral_level,
        "_policy": policy,
    }

    norm = dict(policy.get("sentiment_norm") or {})
    scale = float(norm.get("scale", 5.0))

    korea_indices = _fetch_korea_index_inputs(state, policy)
    inputs = _fetch_inputs(policy)
    try:
        from libs.read.krx_night_futures_reader import fetch_krx_night_futures_packet

        krx_night_futures = fetch_krx_night_futures_packet()
    except Exception as exc:
        krx_night_futures = {
            "schema_version": "krx_night_futures.v1",
            "behavior_effect": "observation_only",
            "status": "unavailable",
            "source": "exception",
            "reason": str(exc),
            "trading_action_allowed": False,
        }
    macro_indicators = _fetch_extended_macro_indicators(
        state,
        policy,
        inputs=inputs,
        korea_indices=korea_indices,
        krx_night_futures=krx_night_futures,
    )
    if inputs is None:
        if korea_indices:
            korea_raw = _compute_korea_raw(korea_indices, w_kospi=w_kospi, w_kosdaq=w_kosdaq)
            return _signal_with_evidence(
                score=_tanh_norm(korea_raw, scale=scale),
                status=SIGNAL_STATUS_OK,
                source=str(korea_indices.get("source") or "kiwoom.ka20009"),
                reason="us_fetch_failed_korea_indices_available",
                ts=now,
                inputs=None,
                weights=resolved_weights,
                raw_score=korea_raw,
                korea_indices=korea_indices,
                macro_indicators=macro_indicators,
                krx_night_futures=krx_night_futures,
            )
        return _signal_with_evidence(
            score=0.0,
            status=SIGNAL_STATUS_UNAVAILABLE,
            source="yfinance",
            reason="fetch_failed",
            ts=now,
            inputs=None,
            weights=resolved_weights,
            raw_score=0.0,
            korea_indices=korea_indices,
            macro_indicators=macro_indicators,
            krx_night_futures=krx_night_futures,
        )

    raw = _compute_raw(
        inputs,
        w_sp=w_sp,
        w_nq=w_nq,
        w_dow=w_dow,
        w_vix=w_vix,
        w_vix_level=w_vix_level,
        w_dxy=w_dxy,
        w_tnx=w_tnx,
        vix_neutral_level=vix_neutral_level,
    )
    raw += _compute_korea_raw(korea_indices, w_kospi=w_kospi, w_kosdaq=w_kosdaq)
    return _signal_with_evidence(
        score=_tanh_norm(raw, scale=scale),
        status=SIGNAL_STATUS_OK,
        source="yfinance+kiwoom.ka20009" if korea_indices else "yfinance",
        reason="",
        ts=now,
        inputs=inputs,
        weights=resolved_weights,
        raw_score=raw,
        korea_indices=korea_indices,
        macro_indicators=macro_indicators,
        krx_night_futures=krx_night_futures,
    )


# Backward/alias (in case older code imports these names)
get_global_sentiment = compute_global_sentiment
