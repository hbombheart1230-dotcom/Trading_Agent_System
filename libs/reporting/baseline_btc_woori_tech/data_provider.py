from __future__ import annotations

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
    ).get(TARGET_SYMBOL, [])


def _yf_rows(ticker: str, *, day: str) -> list[dict[str, Any]]:
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return []
    try:
        frame = yf.Ticker(ticker).history(period="1d", interval="1m")
    except Exception:
        return []
    if frame is None or getattr(frame, "empty", True):
        return []
    compact_day = day.replace("-", "")
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
            if kst.strftime("%Y%m%d") != compact_day:
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
    output: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if index < 5:
            continue
        current = float(row.get("close") or 0.0)
        prior = float(rows[index - 5].get("close") or 0.0)
        if current <= 0 or prior <= 0:
            continue
        output.append(
            {
                "ts": int(row.get("ts") or 0),
                "raw_ts": row.get("raw_ts"),
                "price": current,
                "momentum_5m_pct": round(((current / prior) - 1.0) * 100.0, 6),
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
        "schema_version": "baseline_btc_signal_rows.v1",
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
    positive = [float(row.get("momentum_5m_pct") or 0.0) for row in basis]
    momentum = sum(positive) / len(positive) if positive else None
    stale_sources = [str(row.get("name") or "") for row in observations if row.get("stale")]
    return {
        "available": momentum is not None,
        "momentum_5m_pct": round(momentum, 6) if momentum is not None else None,
        "positive": bool(momentum is not None and momentum > 0.0),
        "observations": observations,
        "source_count": len(observations),
        "fresh_source_count": sum(1 for row in observations if not row.get("stale")),
        "stale_sources": stale_sources,
        "freshness_warning": "stale_sources_present" if stale_sources else "",
        "reason": "" if observations else "btc_signal_unavailable",
    }
