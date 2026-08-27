from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import fmean
from typing import Any, Mapping

from .contracts import HYPOTHESIS_BTC_THRESHOLDS_PCT


KST = timezone(timedelta(hours=9))


def _epoch(day: str, hour: int, minute: int) -> int:
    return int(
        datetime.strptime(day, "%Y-%m-%d")
        .replace(hour=hour, minute=minute, tzinfo=KST)
        .timestamp()
    )


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _latest_at(
    rows: list[Mapping[str, Any]], *, epoch: int, max_age_sec: int = 300
) -> Mapping[str, Any] | None:
    eligible = [row for row in rows if 0 < int(row.get("ts") or 0) <= epoch]
    if not eligible:
        return None
    latest = max(eligible, key=lambda row: int(row.get("ts") or 0))
    return latest if epoch - int(latest.get("ts") or 0) <= max_age_sec else None


def _btc_0855(signal_payload: Mapping[str, Any], *, day: str) -> dict[str, Any]:
    target_epoch = _epoch(day, 8, 55)
    observations = []
    sources = signal_payload.get("sources")
    sources = sources if isinstance(sources, Mapping) else {}
    for source_name in ("btc_krw", "btc_usd"):
        rows = sources.get(source_name)
        rows = rows if isinstance(rows, list) else []
        latest = _latest_at(rows, epoch=target_epoch)
        if latest is None:
            continue
        momentum = _number(latest.get("momentum_24h_pct"))
        price = _number(latest.get("price") or latest.get("close"))
        if momentum is None or price is None:
            continue
        observations.append(
            {
                "source": source_name,
                "ts": int(latest.get("ts") or 0),
                "raw_ts": latest.get("raw_ts"),
                "price": price,
                "return_24h_pct": momentum,
            }
        )
    if not observations:
        return {
            "status": "MISSING",
            "reason": "btc_0855_point_in_time_observation_missing",
            "target_epoch": target_epoch,
            "return_24h_pct": None,
            "thresholds": {
                f"gte_{int(value)}pct": None
                for value in HYPOTHESIS_BTC_THRESHOLDS_PCT
            },
            "observations": [],
        }
    value = round(fmean(row["return_24h_pct"] for row in observations), 6)
    return {
        "status": "OBSERVED",
        "reason": "",
        "target_epoch": target_epoch,
        "return_definition": "24h point-in-time return observed at or before 08:55 KST",
        "return_24h_pct": value,
        "thresholds": {
            f"gte_{int(threshold)}pct": value >= threshold
            for threshold in HYPOTHESIS_BTC_THRESHOLDS_PCT
        },
        "observations": observations,
    }


def _closed_daily_rows(
    rows: list[Mapping[str, Any]], *, as_of_epoch: int
) -> list[dict[str, Any]]:
    cutoff = as_of_epoch - 24 * 60 * 60
    return sorted(
        (
            dict(row)
            for row in rows
            if 0 < int(row.get("ts") or 0) <= cutoff
            and (_number(row.get("close")) or 0.0) > 0.0
        ),
        key=lambda row: int(row.get("ts") or 0),
    )


def _daily_context(
    signal_payload: Mapping[str, Any], *, btc_0855: Mapping[str, Any]
) -> dict[str, Any]:
    research = signal_payload.get("research_context")
    research = research if isinstance(research, Mapping) else {}
    rows = research.get("btc_usd_daily")
    rows = rows if isinstance(rows, list) else []
    as_of_epoch = int(btc_0855.get("target_epoch") or 0)
    current_price = None
    for row in btc_0855.get("observations") or []:
        if row.get("source") == "btc_usd":
            current_price = _number(row.get("price"))
            break
    closed = _closed_daily_rows(rows, as_of_epoch=as_of_epoch)
    if current_price is None or len(closed) < 20:
        return {
            "status": "MISSING",
            "reason": "btc_daily_history_or_usd_price_missing",
            "closed_daily_count": len(closed),
            "surge_state": None,
            "breakout_state": None,
        }
    returns = []
    for prior, current in zip(closed, closed[1:]):
        prior_close = _number(prior.get("close"))
        close = _number(current.get("close"))
        if prior_close and close:
            returns.append(((close / prior_close) - 1.0) * 100.0)
    prior_7 = returns[-7:]
    prior_strong_days = sum(value >= 3.0 for value in prior_7)
    btc_return = _number(btc_0855.get("return_24h_pct"))
    surge_state = (
        "FIRST_SURGE"
        if btc_return is not None and btc_return >= 3.0 and prior_strong_days == 0
        else "REPEATED_SURGE"
        if btc_return is not None and btc_return >= 3.0 and prior_strong_days > 0
        else "NO_STRONG_SURGE"
    )

    def breakout(window: int | None) -> bool | None:
        basis = closed if window is None else closed[-window:]
        highs = [_number(row.get("high")) for row in basis]
        observed = [value for value in highs if value is not None and value > 0.0]
        return current_price > max(observed) if observed else None

    breakout_20d = breakout(20)
    breakout_60d = breakout(60) if len(closed) >= 60 else None
    breakout_ath = breakout(None)
    breakout_state = (
        "ATH_BREAKOUT"
        if breakout_ath
        else "60D_BREAKOUT"
        if breakout_60d
        else "20D_BREAKOUT"
        if breakout_20d
        else "NO_BREAKOUT"
    )
    return {
        "status": "OBSERVED",
        "reason": "",
        "closed_daily_count": len(closed),
        "prior_7d_strong_up_day_count": prior_strong_days,
        "surge_state": surge_state,
        "breakout_20d": breakout_20d,
        "breakout_60d": breakout_60d,
        "breakout_ath": breakout_ath,
        "breakout_state": breakout_state,
        "lookahead_policy": "only daily bars closed at least 24h before 08:55 KST",
    }


def _woori_previous_close(signal_payload: Mapping[str, Any], *, day: str) -> float | None:
    research = signal_payload.get("research_context")
    research = research if isinstance(research, Mapping) else {}
    rows = research.get("woori_daily")
    rows = rows if isinstance(rows, list) else []
    target = datetime.strptime(day, "%Y-%m-%d").date()
    eligible = []
    for row in rows:
        epoch = int(row.get("ts") or 0)
        if epoch <= 0:
            continue
        row_day = datetime.fromtimestamp(epoch, tz=KST).date()
        if row_day < target and (_number(row.get("close")) or 0.0) > 0.0:
            eligible.append(row)
    if not eligible:
        return None
    return _number(max(eligible, key=lambda row: int(row.get("ts") or 0)).get("close"))


def _gap_band(value: float | None) -> str:
    if value is None:
        return "MISSING"
    if value < 0.0:
        return "NEGATIVE"
    if value < 3.0:
        return "0_TO_3"
    if value < 5.0:
        return "3_TO_5"
    if value < 10.0:
        return "5_TO_10"
    return "GTE_10"


def _local_snapshot(
    candles: list[Mapping[str, Any]], *, day: str, hour: int, minute: int
) -> dict[str, Any]:
    entry_epoch = _epoch(day, hour, minute)
    entry_row = next(
        (row for row in candles if int(row.get("ts") or 0) == entry_epoch), None
    )
    completed = [row for row in candles if int(row.get("ts") or 0) < entry_epoch]
    if entry_row is None:
        return {
            "status": "MISSING",
            "reason": "entry_minute_candle_missing",
            "entry_epoch": entry_epoch,
        }
    entry_price = _number(entry_row.get("open") or entry_row.get("close"))
    if entry_price is None:
        return {
            "status": "MISSING",
            "reason": "entry_price_missing",
            "entry_epoch": entry_epoch,
        }
    if not completed:
        return {
            "status": "OBSERVED",
            "reason": "opening_auction_entry_has_no_local_confirmation",
            "entry_epoch": entry_epoch,
            "entry_price": entry_price,
            "volume_ratio": None,
            "price_confirmation": None,
            "local_confirmation": None,
        }
    recent = completed[-5:]
    volumes = [_number(row.get("volume")) or 0.0 for row in recent]
    prior_volumes = volumes[:-1]
    volume_ratio = (
        volumes[-1] / fmean(prior_volumes)
        if prior_volumes and fmean(prior_volumes) > 0.0
        else None
    )
    first_open = _number(candles[0].get("open") or candles[0].get("close"))
    last_close = _number(completed[-1].get("close"))
    prior_highs = [_number(row.get("high") or row.get("close")) for row in completed[:-1]]
    prior_highs = [value for value in prior_highs if value is not None]
    price_confirmation = bool(
        last_close is not None
        and (
            (first_open is not None and last_close > first_open)
            or (prior_highs and last_close > max(prior_highs))
        )
    )
    volume_confirmation = bool(volume_ratio is not None and volume_ratio >= 1.2)
    return {
        "status": "OBSERVED",
        "reason": "",
        "entry_epoch": entry_epoch,
        "entry_price": entry_price,
        "confirmation_cutoff_epoch": entry_epoch - 60,
        "volume_ratio": round(volume_ratio, 6) if volume_ratio is not None else None,
        "volume_confirmation": volume_confirmation,
        "price_confirmation": price_confirmation,
        "local_confirmation": bool(volume_confirmation or price_confirmation),
    }


def _pullback_snapshot(candles: list[Mapping[str, Any]], *, day: str) -> dict[str, Any]:
    start = _epoch(day, 9, 5)
    end = _epoch(day, 9, 30)
    ordered = sorted(candles, key=lambda row: int(row.get("ts") or 0))
    for index, row in enumerate(ordered):
        epoch = int(row.get("ts") or 0)
        if not (start <= epoch < end) or index + 1 >= len(ordered):
            continue
        history = ordered[: index + 1]
        volume_sum = sum(_number(value.get("volume")) or 0.0 for value in history)
        if volume_sum <= 0.0:
            continue
        vwap = sum(
            (_number(value.get("close")) or 0.0)
            * (_number(value.get("volume")) or 0.0)
            for value in history
        ) / volume_sum
        low = _number(row.get("low") or row.get("close"))
        close = _number(row.get("close"))
        next_row = ordered[index + 1]
        if (
            low is not None
            and close is not None
            and low <= vwap
            and close >= vwap
            and int(next_row.get("ts") or 0) <= end
        ):
            return {
                "status": "OBSERVED",
                "reason": "first_vwap_touch_and_reclaim_then_next_minute_entry",
                "trigger_epoch": epoch,
                "entry_epoch": int(next_row.get("ts") or 0),
                "entry_price": _number(next_row.get("open") or next_row.get("close")),
                "trigger_vwap": round(vwap, 6),
                "local_confirmation": True,
            }
    return {
        "status": "MISSING",
        "reason": "deterministic_pullback_trigger_not_observed",
        "entry_epoch": None,
        "entry_price": None,
    }


def build_hypothesis_features(
    *,
    day: str,
    candles: list[Mapping[str, Any]],
    btc_signals: Mapping[str, Any],
) -> dict[str, Any]:
    btc_0855 = _btc_0855(btc_signals, day=day)
    previous_close = _woori_previous_close(btc_signals, day=day)
    first = next((row for row in candles if int(row.get("ts") or 0) == _epoch(day, 9, 0)), None)
    opening_price = _number((first or {}).get("open") or (first or {}).get("close"))
    opening_gap = (
        ((opening_price / previous_close) - 1.0) * 100.0
        if opening_price is not None and previous_close is not None and previous_close > 0.0
        else None
    )
    entries = {
        label: _local_snapshot(
            list(candles),
            day=day,
            hour=9,
            minute=int(label.split(":")[1]),
        )
        for label in ("09:00", "09:03", "09:05", "09:10")
    }
    entries["PULLBACK"] = _pullback_snapshot(list(candles), day=day)
    return {
        "btc_0855": btc_0855,
        "btc_daily_context": _daily_context(btc_signals, btc_0855=btc_0855),
        "woori_opening": {
            "status": "OBSERVED" if opening_gap is not None else "MISSING",
            "reason": "" if opening_gap is not None else "previous_close_or_opening_price_missing",
            "previous_close": previous_close,
            "opening_price": opening_price,
            "opening_gap_pct": round(opening_gap, 6) if opening_gap is not None else None,
            "opening_gap_band": _gap_band(opening_gap),
        },
        "entry_methods": entries,
        "definitions": {
            "first_surge": "08:55 BTC 24h return >=3% and no prior closed daily gain >=3% in seven sessions",
            "repeated_surge": "08:55 BTC 24h return >=3% and at least one prior closed daily gain >=3% in seven sessions",
            "local_confirmation": "last completed minute volume ratio >=1.2 or price above opening/prior intraday high",
            "pullback": "first 09:05-09:30 VWAP touch-and-reclaim, entered at next minute open",
        },
    }
