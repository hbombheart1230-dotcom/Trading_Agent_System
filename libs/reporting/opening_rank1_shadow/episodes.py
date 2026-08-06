from __future__ import annotations

from typing import Any, Mapping

from libs.research.post_reclaim_alpha.evaluator import evaluate_episodes
from libs.research.structural_alpha.features import entry_bar

from .contracts import COHORT_ID, EPISODE_GAP_SEC
from .observability import opening_observability


def build_opening_rank1_episodes(
    windows: list[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
    market_return_pct: float | None = None,
    volume_reference_rows_by_symbol: Mapping[
        str, list[Mapping[str, Any]]
    ] | None = None,
) -> list[dict[str, Any]]:
    volume_reference_rows_by_symbol = volume_reference_rows_by_symbol or {}
    timestamps = {
        symbol: [int(row.get("ts") or 0) for row in rows]
        for symbol, rows in minute_rows_by_symbol.items()
    }
    last_epoch: dict[tuple[str, str], int] = {}
    rank1_epochs: dict[tuple[str, str], list[int]] = {}
    episodes: list[dict[str, Any]] = []
    for window in windows:
        day = str(window.get("day") or "")
        decision_epoch = int(window.get("decision_epoch") or 0)
        candidate = next(
            (
                row
                for row in window.get("candidates") or []
                if isinstance(row, Mapping)
                and int(row.get("rank") or 999) == 1
            ),
            None,
        )
        if candidate is None:
            continue
        symbol = str(candidate.get("symbol") or "")
        key = (day, symbol)
        previous_rank1 = [
            epoch
            for epoch in rank1_epochs.get(key, [])
            if 0 < decision_epoch - epoch <= 5 * 60
        ]
        rank1_epochs.setdefault(key, []).append(decision_epoch)
        if not symbol or decision_epoch - int(last_epoch.get(key) or 0) < EPISODE_GAP_SEC:
            continue
        bar = entry_bar(
            minute_rows_by_symbol.get(symbol) or [],
            decision_epoch=decision_epoch,
            day=day,
            timestamps=timestamps.get(symbol),
        )
        if not bar:
            continue
        baseline_price = float(bar.get("open") or bar.get("close") or 0.0)
        if baseline_price <= 0.0:
            continue
        episode = {
                "episode_id": (
                    f"{COHORT_ID}:{day.replace('-', '')}:{symbol}:{decision_epoch}"
                ),
                "cohort_id": COHORT_ID,
                "day": day,
                "symbol": symbol,
                "decision_id": str(window.get("decision_id") or ""),
                "decision_epoch": decision_epoch,
                "baseline_epoch": int(bar.get("ts") or 0),
                "baseline_price": baseline_price,
                "rank": 1,
                "score_total": candidate.get("score_total"),
                "risk_score": candidate.get("risk_score"),
                "sources": [
                    str(value)
                    for value in candidate.get("sources") or []
                ],
                "score_breakdown": dict(candidate.get("score_breakdown") or {}),
                "evidence_class": "PROSPECTIVE_POINT_IN_TIME_Q9",
            }
        episode["opening_observability"] = opening_observability(
            candidate=candidate,
            day_rows=minute_rows_by_symbol.get(symbol) or [],
            decision_epoch=decision_epoch,
            baseline_epoch=int(bar.get("ts") or 0),
            baseline_price=baseline_price,
            prior_rank1_observations_5m=len(previous_rank1),
            market_return_pct=market_return_pct,
            volume_reference_rows=volume_reference_rows_by_symbol.get(symbol) or [],
        )
        episodes.append(episode)
        last_epoch[key] = decision_epoch
    return evaluate_episodes(
        episodes,
        minute_rows_by_symbol=minute_rows_by_symbol,
    )
