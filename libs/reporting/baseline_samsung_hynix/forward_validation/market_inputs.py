from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol


class LeadMarketProvider(Protocol):
    def capture(self, *, as_of: datetime) -> Mapping[str, Any]: ...


def _number(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _return_pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0.0):
        return None
    return round(((current / previous) - 1.0) * 100.0, 6)


class YFinanceLeadMarketProvider:
    DAILY_TICKERS = {
        "sox": "^SOX",
        "nvidia": "NVDA",
        "micron": "MU",
        "samsung": "005930.KS",
        "sk_hynix": "000660.KS",
        "nasdaq": "^IXIC",
        "sp500": "^GSPC",
        "us10y": "^TNX",
        "vix": "^VIX",
    }
    INTRADAY_TICKERS = {
        "nasdaq100_futures_0850": "NQ=F",
        "sp500_futures_0850": "ES=F",
        "usdkrw_0850": "KRW=X",
    }
    HYNIX_ADR_TICKERS = ("HXSCF", "HXSCL")
    MAX_INTRADAY_AGE_SEC = 15 * 60

    @staticmethod
    def _rows(ticker: str, *, period: str, interval: str, prepost: bool = False) -> list[dict[str, Any]]:
        try:
            import yfinance as yf  # type: ignore

            frame = yf.Ticker(ticker).history(
                period=period,
                interval=interval,
                auto_adjust=False,
                prepost=prepost,
            )
        except Exception:
            return []
        rows: list[dict[str, Any]] = []
        try:
            for index, row in frame.iterrows():
                close = _number(row.get("Close"))
                if close is None or close <= 0:
                    continue
                rows.append(
                    {
                        "timestamp": index.isoformat() if hasattr(index, "isoformat") else str(index),
                        "epoch": int(index.timestamp()) if hasattr(index, "timestamp") else 0,
                        "close": close,
                        "volume": _number(row.get("Volume")),
                    }
                )
        except Exception:
            return []
        return rows

    def _daily(self, ticker: str) -> dict[str, Any]:
        rows = self._rows(ticker, period="10d", interval="1d")
        if len(rows) < 2:
            return {"status": "UNAVAILABLE", "ticker": ticker, "source": "yfinance", "reason": "daily_history_missing"}
        latest, previous = rows[-1], rows[-2]
        three_day_base = rows[-4]["close"] if len(rows) >= 4 else None
        return {
            "status": "AVAILABLE",
            "ticker": ticker,
            "source": "yfinance",
            "as_of": latest["timestamp"],
            "current": latest["close"],
            "previous": previous["close"],
            "return_pct": _return_pct(latest["close"], previous["close"]),
            "three_day_return_pct": _return_pct(latest["close"], three_day_base),
            "observation_count": len(rows),
        }

    @staticmethod
    def _quote_previous_close(ticker: str) -> float | None:
        try:
            import yfinance as yf  # type: ignore

            return _number(yf.Ticker(ticker).fast_info.get("previous_close"))
        except Exception:
            return None

    def _intraday_vs_previous_close(self, ticker: str, *, as_of: datetime) -> dict[str, Any]:
        daily = self._daily(ticker)
        rows = [row for row in self._rows(ticker, period="5d", interval="5m", prepost=True) if int(row.get("epoch") or 0) <= int(as_of.timestamp())]
        if daily.get("status") != "AVAILABLE" or not rows:
            return {"status": "UNAVAILABLE", "ticker": ticker, "source": "yfinance", "reason": "point_in_time_quote_missing"}
        latest = rows[-1]
        snapshot_age_sec = max(0, int(as_of.timestamp()) - int(latest["epoch"] or 0))
        if snapshot_age_sec > self.MAX_INTRADAY_AGE_SEC:
            return {
                "status": "UNAVAILABLE",
                "ticker": ticker,
                "source": "yfinance",
                "reason": "point_in_time_quote_stale",
                "as_of": latest["timestamp"],
                "snapshot_age_sec": snapshot_age_sec,
                "max_snapshot_age_sec": self.MAX_INTRADAY_AGE_SEC,
            }
        quote_previous_close = self._quote_previous_close(ticker)
        previous_close = quote_previous_close or _number(daily.get("current"))
        return {
            "status": "AVAILABLE",
            "ticker": ticker,
            "source": "yfinance",
            "as_of": latest["timestamp"],
            "as_of_epoch": latest["epoch"],
            "current": latest["close"],
            "previous_close": previous_close,
            "return_pct": _return_pct(latest["close"], previous_close),
            "previous_close_source": "yfinance.fast_info" if quote_previous_close else "daily_latest_fallback",
            "snapshot_age_sec": snapshot_age_sec,
            "max_snapshot_age_sec": self.MAX_INTRADAY_AGE_SEC,
        }

    def capture(self, *, as_of: datetime) -> Mapping[str, Any]:
        observations = {key: self._daily(ticker) for key, ticker in self.DAILY_TICKERS.items()}
        adr = next(
            (row for ticker in self.HYNIX_ADR_TICKERS if (row := self._daily(ticker)).get("status") == "AVAILABLE"),
            {"status": "UNAVAILABLE", "source": "yfinance", "reason": "hynix_adr_unavailable", "tickers_tried": list(self.HYNIX_ADR_TICKERS)},
        )
        observations["hynix_adr"] = adr
        observations.update(
            {
                key: self._intraday_vs_previous_close(ticker, as_of=as_of)
                for key, ticker in self.INTRADAY_TICKERS.items()
            }
        )
        return observations


def _observation_return(observations: Mapping[str, Any], key: str) -> float | None:
    row = observations.get(key)
    return _number(row.get("return_pct")) if isinstance(row, Mapping) else None


def flatten_signal_inputs(observations: Mapping[str, Any]) -> dict[str, Any]:
    hynix = observations.get("sk_hynix") if isinstance(observations.get("sk_hynix"), Mapping) else {}
    samsung = observations.get("samsung") if isinstance(observations.get("samsung"), Mapping) else {}
    us10y = observations.get("us10y") if isinstance(observations.get("us10y"), Mapping) else {}
    us10y_current = _number(us10y.get("current"))
    us10y_previous = _number(us10y.get("previous"))
    us10y_divisor = 10.0 if max(abs(us10y_current or 0.0), abs(us10y_previous or 0.0)) > 10.0 else 1.0
    return {
        "sox_return_pct": _observation_return(observations, "sox"),
        "nvidia_return_pct": _observation_return(observations, "nvidia"),
        "micron_return_pct": _observation_return(observations, "micron"),
        "hynix_adr_return_pct": _observation_return(observations, "hynix_adr"),
        "nasdaq_return_pct": _observation_return(observations, "nasdaq"),
        "sp500_return_pct": _observation_return(observations, "sp500"),
        "nasdaq100_futures_0850_return_pct": _observation_return(observations, "nasdaq100_futures_0850"),
        "sp500_futures_0850_return_pct": _observation_return(observations, "sp500_futures_0850"),
        "usdkrw_0850_change_pct": _observation_return(observations, "usdkrw_0850"),
        "us10y_yield_change": (
            round((float(us10y_current) - float(us10y_previous)) / us10y_divisor, 6)
            if us10y_current is not None and us10y_previous is not None
            else None
        ),
        "us10y_yield_change_unit": "percentage_point",
        "vix_change_pct": _observation_return(observations, "vix"),
        "hynix_previous_day_return_pct": _number(hynix.get("return_pct")),
        "hynix_3d_cumulative_return_pct": _number(hynix.get("three_day_return_pct")),
        "hynix_previous_close": _number(hynix.get("current")),
        "samsung_previous_day_return_pct": _number(samsung.get("return_pct")),
        "samsung_previous_close": _number(samsung.get("current")),
    }


def detect_samsung_specific_event(state_path: Path, *, day: str) -> dict[str, Any]:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        state = {}
    items = []
    if isinstance(state, Mapping):
        raw = state.get("mock_news_items") or state.get("news_items") or []
        items = list(raw.values()) if isinstance(raw, Mapping) else list(raw) if isinstance(raw, list) else []
    event_terms = ("HBM", "파운드리", "실적", "earnings", "foundry")
    matches = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        title = str(item.get("title") or item.get("headline") or "")
        symbols = [str(value) for value in item.get("symbols") or []]
        symbol = str(item.get("symbol") or "")
        relevant = "005930" in symbols or symbol == "005930" or "삼성전자" in title
        if relevant and any(term.lower() in title.lower() for term in event_terms):
            matches.append(title)
    return {
        "samsung_specific_event": bool(matches),
        "matched_headlines": matches[:10],
        "event_terms": list(event_terms),
        "day": day,
        "source": "runtime_state_news",
    }
