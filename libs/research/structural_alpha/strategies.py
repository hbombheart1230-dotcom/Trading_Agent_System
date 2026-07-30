from __future__ import annotations

from typing import Any, Mapping

from .contracts import EPISODE_GAP_SEC
from .features import (
    contraction_breakout_features,
    entry_bar,
    relative_strength_features,
)


def _percentile_ranks(
    rows: list[dict[str, Any]],
    key: str,
) -> dict[str, float]:
    ordered = sorted(
        rows,
        key=lambda row: (float(row[key]), str(row["symbol"])),
    )
    denominator = max(1, len(ordered) - 1)
    return {
        str(row["symbol"]): index / denominator
        for index, row in enumerate(ordered)
    }


def _episode(
    *,
    strategy_id: str,
    window: Mapping[str, Any],
    symbol: str,
    bar: Mapping[str, Any],
    features: Mapping[str, Any],
    index: int,
) -> dict[str, Any]:
    price = float(bar.get("open") or bar.get("close") or 0.0)
    return {
        "episode_id": (
            f"{strategy_id}:{str(window.get('day') or '').replace('-', '')}:"
            f"{symbol}:{index}"
        ),
        "strategy_id": strategy_id,
        "day": str(window.get("day") or ""),
        "symbol": symbol,
        "decision_epoch": int(window.get("decision_epoch") or 0),
        "baseline_epoch": int(bar.get("ts") or 0),
        "baseline_price": price,
        "feature_snapshot": dict(features),
        "decision_id": str(window.get("decision_id") or ""),
    }


def build_cross_sectional_episodes(
    windows: list[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    last_epoch = 0
    timestamps_by_symbol = {
        symbol: [int(row.get("ts") or 0) for row in rows]
        for symbol, rows in minute_rows_by_symbol.items()
    }
    for window in windows:
        epoch = int(window.get("decision_epoch") or 0)
        day = str(window.get("day") or "")
        candidates: list[dict[str, Any]] = []
        for candidate in window.get("candidates") or []:
            symbol = str(candidate.get("symbol") or "")
            features = relative_strength_features(
                minute_rows_by_symbol.get(symbol) or [],
                decision_epoch=epoch,
                day=day,
                timestamps=timestamps_by_symbol.get(symbol),
            )
            if (
                features.get("available")
                and features.get("volume_ratio") is not None
            ):
                candidates.append({"symbol": symbol, **features})
        if len(candidates) < 3:
            continue
        component_ranks = [
            _percentile_ranks(candidates, key)
            for key in ("return_5m_pct", "volume_ratio", "turnover")
        ]
        for row in candidates:
            symbol = str(row["symbol"])
            row["composite_score"] = round(
                sum(ranks[symbol] for ranks in component_ranks) / 3.0,
                6,
            )
        selected = max(
            candidates,
            key=lambda row: (float(row["composite_score"]), str(row["symbol"])),
        )
        if (
            float(selected.get("return_5m_pct") or 0.0) <= 0.0
            or not bool(selected.get("above_vwap"))
            or (last_epoch and epoch - last_epoch < EPISODE_GAP_SEC)
        ):
            continue
        symbol = str(selected["symbol"])
        bar = entry_bar(
            minute_rows_by_symbol.get(symbol) or [],
            decision_epoch=epoch,
            day=day,
            timestamps=timestamps_by_symbol.get(symbol),
        )
        if not bar:
            continue
        episodes.append(
            _episode(
                strategy_id="H4_CROSS_SECTIONAL_RELATIVE_STRENGTH",
                window=window,
                symbol=symbol,
                bar=bar,
                features=selected,
                index=len(episodes) + 1,
            )
        )
        last_epoch = epoch
    return episodes


def build_contraction_breakout_episodes(
    windows: list[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    last_epoch = 0
    timestamps_by_symbol = {
        symbol: [int(row.get("ts") or 0) for row in rows]
        for symbol, rows in minute_rows_by_symbol.items()
    }
    for window in windows:
        epoch = int(window.get("decision_epoch") or 0)
        day = str(window.get("day") or "")
        candidates: list[dict[str, Any]] = []
        for candidate in window.get("candidates") or []:
            symbol = str(candidate.get("symbol") or "")
            features = contraction_breakout_features(
                minute_rows_by_symbol.get(symbol) or [],
                decision_epoch=epoch,
                day=day,
                timestamps=timestamps_by_symbol.get(symbol),
            )
            if (
                features.get("available")
                and features.get("contraction_ok")
                and features.get("breakout_ok")
                and features.get("volume_ok")
            ):
                candidates.append({"symbol": symbol, **features})
        if not candidates or (last_epoch and epoch - last_epoch < EPISODE_GAP_SEC):
            continue
        selected = max(
            candidates,
            key=lambda row: (float(row["breakout_pct"]), str(row["symbol"])),
        )
        symbol = str(selected["symbol"])
        bar = entry_bar(
            minute_rows_by_symbol.get(symbol) or [],
            decision_epoch=epoch,
            day=day,
            timestamps=timestamps_by_symbol.get(symbol),
        )
        if not bar:
            continue
        episodes.append(
            _episode(
                strategy_id="H6_VOLATILITY_CONTRACTION_BREAKOUT",
                window=window,
                symbol=symbol,
                bar=bar,
                features=selected,
                index=len(episodes) + 1,
            )
        )
        last_epoch = epoch
    return episodes
