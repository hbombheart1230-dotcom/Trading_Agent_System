from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.baseline_samsung_hynix.data_provider import load_existing_candles

from .contracts import TARGET_SYMBOL


KST = timezone(timedelta(hours=9))


def load_woori_candles(
    *,
    day: str,
    state_path: Path = Path("data/state.json"),
    allow_fresh_fetch: bool = True,
) -> list[dict[str, Any]]:
    return load_existing_candles(
        state_path=state_path,
        day=day,
        symbols=(TARGET_SYMBOL,),
        allow_fresh_fetch=allow_fresh_fetch,
        run_id_prefix="baseline_btc_woori_tech",
    ).get(TARGET_SYMBOL, [])


def _yf_rows(ticker: str, *, day: str) -> list[dict[str, Any]]:
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return []
    try:
        # Two calendar days are required for the 24-hour regime observation.
        frame = yf.Ticker(ticker).history(period="2d", interval="1m")
    except Exception:
        return []
    if frame is None or getattr(frame, "empty", True):
        return []
    target_day = datetime.strptime(day, "%Y-%m-%d").date()
    allowed_days = {
        target_day.strftime("%Y%m%d"),
        (target_day - timedelta(days=1)).strftime("%Y%m%d"),
    }
    rows: list[dict[str, Any]] = []
    try:
        for index, row in frame.iterrows():
            dt = index.to_pydatetime() if hasattr(index, "to_pydatetime") else index
            if not isinstance(dt, datetime):
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            epoch = int(dt.timestamp())
            kst = datetime.fromtimestamp(epoch, tz=KST)
            if kst.strftime("%Y%m%d") not in allowed_days:
                continue
            close = float(row.get("Close") or 0.0)
            if close <= 0:
                continue
            rows.append(
                {
                    "ts": epoch,
                    "raw_ts": kst.strftime("%Y%m%d%H%M%S"),
                    "close": close,
                    "volume": float(row.get("Volume") or 0.0),
                }
            )
    except Exception:
        return []
    return sorted({int(row["ts"]): row for row in rows}.values(), key=lambda row: int(row["ts"]))


def _momentum_rows(rows: list[Mapping[str, Any]], *, source: str) -> list[dict[str, Any]]:
    epochs = [int(row.get("ts") or 0) for row in rows]

    def prior_price(index: int, seconds: int) -> float | None:
        target = epochs[index] - seconds
        prior_index = bisect_right(epochs, target, hi=index) - 1
        if prior_index < 0:
            return None
        value = float(rows[prior_index].get("close") or 0.0)
        return value if value > 0.0 else None

    def change(current: float, prior: float | None) -> float | None:
        if current <= 0.0 or prior is None or prior <= 0.0:
            return None
        return round(((current / prior) - 1.0) * 100.0, 6)

    output: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if index < 5:
            continue
        current = float(row.get("close") or 0.0)
        prior = prior_price(index, 5 * 60)
        if current <= 0 or prior is None:
            continue
        current_kst = datetime.fromtimestamp(epochs[index], tz=KST)
        krx_open = current_kst.replace(hour=9, minute=0, second=0, microsecond=0)
        krx_open_price = None
        if current_kst >= krx_open:
            open_index = bisect_left(epochs, int(krx_open.timestamp()), hi=index + 1)
            if 0 <= open_index <= index:
                candidate_kst = datetime.fromtimestamp(epochs[open_index], tz=KST)
                if candidate_kst.date() == current_kst.date():
                    krx_open_price = float(rows[open_index].get("close") or 0.0) or None
        output.append(
            {
                "ts": int(row.get("ts") or 0),
                "raw_ts": row.get("raw_ts"),
                "price": current,
                "momentum_5m_pct": change(current, prior),
                "momentum_15m_pct": change(current, prior_price(index, 15 * 60)),
                "momentum_60m_pct": change(current, prior_price(index, 60 * 60)),
                "momentum_24h_pct": change(current, prior_price(index, 24 * 60 * 60)),
                "momentum_since_krx_open_pct": change(current, krx_open_price),
                "source": source,
            }
        )
    return output


def load_btc_signal_rows(*, day: str) -> dict[str, Any]:
    btc_usd_rows = _yf_rows("BTC-USD", day=day)
    coin_rows = _yf_rows("COIN", day=day)
    krw_rows = _yf_rows("KRW=X", day=day)
    btc_krw_rows: list[dict[str, Any]] = []
    krw_by_ts = {int(row["ts"]): row for row in krw_rows}
    for row in btc_usd_rows:
        fx = krw_by_ts.get(int(row["ts"]))
        if not fx:
            continue
        btc_krw_rows.append(
            {
                "ts": row["ts"],
                "raw_ts": row.get("raw_ts"),
                "close": float(row["close"]) * float(fx["close"]),
                "volume": row.get("volume") or 0.0,
            }
        )
    sources = {
        "btc_krw": _momentum_rows(btc_krw_rows, source="derived:BTC-USD*KRW=X"),
        "btc_usd": _momentum_rows(btc_usd_rows, source="yfinance:BTC-USD"),
        "coinbase_proxy": _momentum_rows(coin_rows, source="yfinance:COIN"),
    }
    available = [key for key, rows in sources.items() if rows]
    return {
        "schema_version": "baseline_btc_signal_rows.v2",
        "day": day,
        "available": bool(available),
        "available_sources": available,
        "sources": sources,
        "fallback_reason": "" if available else "btc_and_crypto_proxy_unavailable",
    }


def signal_at(payload: Mapping[str, Any], *, epoch: int) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    stale_after_sec = 15 * 60
    for source_name, rows in (payload.get("sources") or {}).items():
        eligible = [row for row in rows if int(row.get("ts") or 0) <= epoch]
        if eligible:
            observation = {"name": source_name, **dict(eligible[-1])}
            age_sec = max(0, epoch - int(observation.get("ts") or 0))
            observation["age_sec"] = age_sec
            observation["stale"] = age_sec > stale_after_sec
            observations.append(observation)
    direct = [
        row
        for row in observations
        if row.get("name") in {"btc_krw", "btc_usd"}
    ]
    basis = direct or observations
    def aggregate(field: str) -> float | None:
        values = [float(row[field]) for row in basis if row.get(field) is not None]
        return round(sum(values) / len(values), 6) if values else None

    momentum = aggregate("momentum_5m_pct")
    momentum_15m = aggregate("momentum_15m_pct")
    momentum_60m = aggregate("momentum_60m_pct")
    momentum_24h = aggregate("momentum_24h_pct")
    momentum_krx = aggregate("momentum_since_krx_open_pct")
    regime_basis = momentum_60m if momentum_60m is not None else momentum_15m
    if regime_basis is None:
        regime = "insufficient_evidence"
    elif regime_basis >= 1.0 or (momentum_24h is not None and momentum_24h >= 3.0):
        regime = "strong_bull"
    elif regime_basis >= 0.25:
        regime = "bull"
    elif regime_basis <= -1.0 or (momentum_24h is not None and momentum_24h <= -3.0):
        regime = "strong_bear"
    elif regime_basis <= -0.25:
        regime = "bear"
    else:
        regime = "neutral"
    short_pullback_with_bull_regime = bool(
        regime in {"bull", "strong_bull"}
        and momentum_15m is not None
        and momentum_15m > 0.0
        and momentum is not None
        and momentum > -0.3
    )
    leading_positive = bool(momentum is not None and (momentum > 0.0 or short_pullback_with_bull_regime))
    stale_sources = [str(row.get("name") or "") for row in observations if row.get("stale")]
    return {
        "available": momentum is not None,
        "momentum_5m_pct": round(momentum, 6) if momentum is not None else None,
        "momentum_15m_pct": momentum_15m,
        "momentum_60m_pct": momentum_60m,
        "momentum_24h_pct": momentum_24h,
        "momentum_since_krx_open_pct": momentum_krx,
        "market_regime": regime,
        "market_regime_behavior_effect": "observation_only",
        "positive": bool(momentum is not None and momentum > 0.0),
        "leading_positive": leading_positive,
        "leading_signal_policy": "q12_btc_multihorizon_leading_signal.v2",
        "leading_signal_reason": (
            "positive_5m_momentum"
            if momentum is not None and momentum > 0.0
            else "bull_regime_short_pullback"
            if short_pullback_with_bull_regime
            else "btc_leading_signal_not_confirmed"
        ),
        "observations": observations,
        "source_count": len(observations),
        "fresh_source_count": sum(1 for row in observations if not row.get("stale")),
        "stale_sources": stale_sources,
        "freshness_warning": "stale_sources_present" if stale_sources else "",
        "reason": "" if observations else "btc_signal_unavailable",
    }
