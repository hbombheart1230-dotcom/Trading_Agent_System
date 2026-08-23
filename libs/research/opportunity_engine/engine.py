from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from .contracts import OPENING_WINDOW_END_MINUTE, OPENING_WINDOW_START_MINUTE
from .data_provider import market_pair_at
from .features import build_market_features, build_symbol_features, score_opportunity


KST = timezone(timedelta(hours=9))


def _in_opening_window(epoch: int) -> bool:
    if epoch <= 0:
        return False
    dt = datetime.fromtimestamp(epoch, tz=KST)
    minute = dt.hour * 60 + dt.minute
    return OPENING_WINDOW_START_MINUTE <= minute <= OPENING_WINDOW_END_MINUTE


def build_signal_timeline(
    *,
    day: str,
    candles: Mapping[str, list[Mapping[str, Any]]],
    market_timeline: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for symbol in sorted(candles):
        rows = list(candles.get(symbol) or [])
        for index in range(5, len(rows)):
            epoch = int(rows[index].get("ts") or 0)
            if not _in_opening_window(epoch):
                continue
            current_market, previous_market = market_pair_at(market_timeline, epoch=epoch)
            market_features = build_market_features(current_market, previous_market)
            market_source_epoch = int(market_features.get("source_ts") or 0)
            market_features["snapshot_age_sec"] = (
                max(0, epoch - market_source_epoch) if market_source_epoch > 0 else None
            )
            market_features["snapshot_stale"] = bool(
                market_features["snapshot_age_sec"] is not None
                and int(market_features["snapshot_age_sec"]) > 300
            )
            symbol_features = build_symbol_features(
                rows[: index + 1],
                as_of_epoch=epoch,
                market_features=market_features,
            )
            opportunity = score_opportunity(symbol_features, market_features)
            signals.append(
                {
                    "signal_id": f"OE_{day.replace('-', '')}_{symbol}_{epoch}",
                    "day": day,
                    "symbol": symbol,
                    "as_of_epoch": epoch,
                    "behavior_effect": "shadow_only",
                    "research_window": "09:00-10:00 KST",
                    "market": market_features,
                    "symbol_features": symbol_features,
                    "opportunity": opportunity,
                    "order_execution_allowed": False,
                }
            )
    signals.sort(key=lambda row: (int(row["as_of_epoch"]), str(row["symbol"])))
    return signals
