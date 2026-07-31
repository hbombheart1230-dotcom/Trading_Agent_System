from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from libs.research.post_reclaim_alpha.evaluator import evaluate_episodes
from libs.research.structural_alpha.features import entry_bar, relative_strength_features

from .contracts import EPISODE_GAP_SEC, MARKET_NATIVE_SOURCES


KST = timezone(timedelta(hours=9))


def source_class(sources: list[str]) -> str:
    normalized = {str(source or "").strip() for source in sources if str(source or "").strip()}
    native = normalized.intersection(MARKET_NATIVE_SOURCES)
    has_theme = "sector_theme" in normalized
    if native and has_theme:
        return "mixed_market_theme"
    if len(native) >= 2:
        return "market_native_multi"
    if len(native) == 1:
        return "market_native_single"
    if normalized == {"sector_theme"}:
        return "sector_theme_only"
    if "strategist_backfill" in normalized:
        return "strategist_backfill"
    return "other"


def rank_bucket(rank: int) -> str:
    if rank <= 1:
        return "rank1"
    if rank <= 3:
        return "rank2_3"
    if rank <= 5:
        return "rank4_5"
    return "rank6_10"


def time_bucket(epoch: int) -> str:
    value = datetime.fromtimestamp(epoch, tz=KST)
    minute = value.hour * 60 + value.minute
    if minute < 9 * 60 + 20:
        return "open_0_20m"
    if minute < 10 * 60:
        return "open_20_60m"
    if minute < 12 * 60:
        return "morning_10_12"
    if minute < 14 * 60:
        return "midday_12_14"
    return "late_14_close"


def build_candidate_episodes(
    windows: list[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    timestamps = {
        symbol: [int(row.get("ts") or 0) for row in rows]
        for symbol, rows in minute_rows_by_symbol.items()
    }
    last_epoch: dict[tuple[str, str], int] = {}
    episodes: list[dict[str, Any]] = []
    for window in windows:
        day = str(window.get("day") or "")
        epoch = int(window.get("decision_epoch") or 0)
        for candidate in window.get("candidates") or []:
            symbol = str(candidate.get("symbol") or "")
            if not symbol:
                continue
            key = (day, symbol)
            if epoch - int(last_epoch.get(key) or 0) < EPISODE_GAP_SEC:
                continue
            rows = minute_rows_by_symbol.get(symbol) or []
            bar = entry_bar(
                rows,
                decision_epoch=epoch,
                day=day,
                timestamps=timestamps.get(symbol),
            )
            if not bar:
                continue
            features = relative_strength_features(
                rows,
                decision_epoch=epoch,
                day=day,
                timestamps=timestamps.get(symbol),
            )
            rank = int(candidate.get("rank") or 999)
            sources = [str(value) for value in candidate.get("sources") or []]
            baseline_price = float(bar.get("open") or bar.get("close") or 0.0)
            if baseline_price <= 0.0:
                continue
            episodes.append(
                {
                    "episode_id": f"existing:{day.replace('-', '')}:{symbol}:{epoch}",
                    "day": day,
                    "symbol": symbol,
                    "decision_id": str(window.get("decision_id") or ""),
                    "decision_epoch": epoch,
                    "baseline_epoch": int(bar.get("ts") or 0),
                    "baseline_price": baseline_price,
                    "rank": rank,
                    "rank_bucket": rank_bucket(rank),
                    "sources": sources,
                    "source_count": len(set(sources)),
                    "source_class": source_class(sources),
                    "time_bucket": time_bucket(epoch),
                    "score_total": candidate.get("score_total"),
                    "risk_score": candidate.get("risk_score"),
                    "score_breakdown": dict(candidate.get("score_breakdown") or {}),
                    "feature_snapshot": features,
                    "evidence_class": "RECONSTRUCTED_FROM_POINT_IN_TIME_Q9",
                }
            )
            last_epoch[key] = epoch
    return evaluate_episodes(episodes, minute_rows_by_symbol=minute_rows_by_symbol)


def candidate_integrity(windows: list[Mapping[str, Any]]) -> dict[str, Any]:
    candidates = [
        candidate
        for window in windows
        for candidate in window.get("candidates") or []
        if isinstance(candidate, Mapping)
    ]
    source_counts: Counter[str] = Counter()
    source_class_counts: Counter[str] = Counter()
    zero_components: Counter[str] = Counter()
    present_components: Counter[str] = Counter()
    sector_only_windows = 0
    market_native_windows = 0
    missing_source_candidate_count = 0
    for window in windows:
        classes = []
        for candidate in window.get("candidates") or []:
            sources = [str(value) for value in candidate.get("sources") or []]
            if not sources:
                missing_source_candidate_count += 1
            classes.append(source_class(sources))
            source_counts.update(set(sources))
            source_class_counts[source_class(sources)] += 1
            for name, value in dict(candidate.get("score_breakdown") or {}).items():
                present_components[str(name)] += 1
                try:
                    if float(value) == 0.0:
                        zero_components[str(name)] += 1
                except Exception:
                    continue
        if classes and all(value == "sector_theme_only" for value in classes):
            sector_only_windows += 1
        if any(value.startswith("market_native") or value == "mixed_market_theme" for value in classes):
            market_native_windows += 1
    total = len(candidates)
    component_quality = {
        name: {
            "present_count": count,
            "zero_count": zero_components[name],
            "zero_rate": round(zero_components[name] / count, 4) if count else 0.0,
        }
        for name, count in sorted(present_components.items())
    }
    return {
        "window_count": len(windows),
        "candidate_row_count": total,
        "source_counts": dict(source_counts.most_common()),
        "source_class_counts": dict(source_class_counts.most_common()),
        "sector_theme_only_window_count": sector_only_windows,
        "sector_theme_only_window_rate": round(sector_only_windows / len(windows), 4) if windows else 0.0,
        "market_native_window_count": market_native_windows,
        "market_native_window_rate": round(market_native_windows / len(windows), 4) if windows else 0.0,
        "missing_source_candidate_count": missing_source_candidate_count,
        "missing_source_candidate_rate": round(missing_source_candidate_count / total, 4)
        if total
        else 0.0,
        "score_component_quality": component_quality,
    }
