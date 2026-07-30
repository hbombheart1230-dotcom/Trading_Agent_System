from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from libs.reporting.evaluation.metrics import performance_metrics

from .contracts import (
    EVIDENCE_GATES,
    FORWARD_MAX_DELAY_SEC,
    HORIZONS_MINUTES,
    LIVE_COST_PCT,
    MOCK_COST_PCT,
    PERFORMANCE_GATES,
)


KST = timezone(timedelta(hours=9))


def _same_day(epoch: int, day: str) -> bool:
    return datetime.fromtimestamp(epoch, tz=KST).date().isoformat() == day


def _checkpoint(
    *,
    rows: list[Mapping[str, Any]],
    baseline_epoch: int,
    baseline_price: float,
    day: str,
    minutes: int,
) -> dict[str, Any]:
    target_epoch = baseline_epoch + int(minutes) * 60
    same_day = [
        row
        for row in rows
        if _same_day(int(row.get("ts") or 0), day)
        and int(row.get("ts") or 0) >= baseline_epoch
    ]
    observed = next(
        (row for row in same_day if int(row.get("ts") or 0) >= target_epoch),
        None,
    )
    if observed is None:
        return {"status": "missing", "reason": "forward_price_missing"}
    observed_epoch = int(observed.get("ts") or 0)
    delay = observed_epoch - target_epoch
    if delay > FORWARD_MAX_DELAY_SEC:
        return {
            "status": "missing",
            "reason": "forward_observation_delay_exceeded",
            "delay_sec": delay,
        }
    window = [
        row
        for row in same_day
        if baseline_epoch <= int(row.get("ts") or 0) <= observed_epoch
    ] or [observed]
    close = float(observed.get("close") or 0.0)
    high = max(float(row.get("high") or row.get("close") or 0.0) for row in window)
    low = min(float(row.get("low") or row.get("close") or 0.0) for row in window)
    return {
        "status": "observed",
        "observed_epoch": observed_epoch,
        "delay_sec": delay,
        "price": close,
        "gross_return_pct": round((close / baseline_price - 1.0) * 100.0, 4),
        "live_net_return_pct": round(
            (close / baseline_price - 1.0) * 100.0 - LIVE_COST_PCT,
            4,
        ),
        "mock_net_return_pct": round(
            (close / baseline_price - 1.0) * 100.0 - MOCK_COST_PCT,
            4,
        ),
        "mfe_pct": round((high / baseline_price - 1.0) * 100.0, 4),
        "mae_pct": round((low / baseline_price - 1.0) * 100.0, 4),
    }


def _eod_checkpoint(
    *,
    rows: list[Mapping[str, Any]],
    baseline_epoch: int,
    baseline_price: float,
    day: str,
) -> dict[str, Any]:
    same_day = [
        row
        for row in rows
        if _same_day(int(row.get("ts") or 0), day)
        and int(row.get("ts") or 0) >= baseline_epoch
        and datetime.fromtimestamp(int(row.get("ts") or 0), tz=KST).time()
        <= datetime.strptime("15:30", "%H:%M").time()
    ]
    if not same_day:
        return {"status": "missing", "reason": "eod_price_missing"}
    observed = same_day[-1]
    close = float(observed.get("close") or 0.0)
    high = max(float(row.get("high") or row.get("close") or 0.0) for row in same_day)
    low = min(float(row.get("low") or row.get("close") or 0.0) for row in same_day)
    return {
        "status": "observed",
        "observed_epoch": int(observed.get("ts") or 0),
        "price": close,
        "gross_return_pct": round((close / baseline_price - 1.0) * 100.0, 4),
        "live_net_return_pct": round(
            (close / baseline_price - 1.0) * 100.0 - LIVE_COST_PCT,
            4,
        ),
        "mock_net_return_pct": round(
            (close / baseline_price - 1.0) * 100.0 - MOCK_COST_PCT,
            4,
        ),
        "mfe_pct": round((high / baseline_price - 1.0) * 100.0, 4),
        "mae_pct": round((low / baseline_price - 1.0) * 100.0, 4),
    }


def evaluate_episodes(
    episodes: list[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in episodes:
        row = dict(raw)
        symbol = str(row.get("symbol") or "")
        baseline_epoch = int(row.get("baseline_epoch") or 0)
        baseline_price = float(row.get("baseline_price") or 0.0)
        day = str(row.get("day") or "")
        candles = list(minute_rows_by_symbol.get(symbol) or [])
        checkpoints: dict[str, Any] = {}
        if baseline_epoch <= 0 or baseline_price <= 0:
            row["evaluation_status"] = "INVALID_BASELINE"
        elif not candles:
            row["evaluation_status"] = "MINUTE_HISTORY_MISSING"
        else:
            for minutes in HORIZONS_MINUTES:
                checkpoints[f"+{minutes}m"] = _checkpoint(
                    rows=candles,
                    baseline_epoch=baseline_epoch,
                    baseline_price=baseline_price,
                    day=day,
                    minutes=minutes,
                )
            checkpoints["EOD"] = _eod_checkpoint(
                rows=candles,
                baseline_epoch=baseline_epoch,
                baseline_price=baseline_price,
                day=day,
            )
            row["evaluation_status"] = (
                "OBSERVED"
                if any(value.get("status") == "observed" for value in checkpoints.values())
                else "FORWARD_HISTORY_MISSING"
            )
        row["checkpoints"] = checkpoints
        output.append(row)
    return output


def summarize_horizon(
    episodes: list[Mapping[str, Any]],
    horizon: str,
) -> dict[str, Any]:
    observed = [
        checkpoint
        for row in episodes
        for checkpoint in [
            (
                row.get("checkpoints")
                if isinstance(row.get("checkpoints"), Mapping)
                else {}
            ).get(horizon)
        ]
        if isinstance(checkpoint, Mapping) and checkpoint.get("status") == "observed"
    ]
    gross = [float(row["gross_return_pct"]) for row in observed]
    live = [float(row["live_net_return_pct"]) for row in observed]
    mock = [float(row["mock_net_return_pct"]) for row in observed]
    return {
        "horizon": horizon,
        "episode_count": len(episodes),
        "observed_count": len(observed),
        "coverage": round(len(observed) / len(episodes), 4) if episodes else 0.0,
        "gross": performance_metrics(gross),
        "live_net": performance_metrics(live),
        "mock_net": performance_metrics(mock),
        "average_mfe_pct": round(
            sum(float(row["mfe_pct"]) for row in observed) / len(observed),
            4,
        )
        if observed
        else None,
        "average_mae_pct": round(
            sum(float(row["mae_pct"]) for row in observed) / len(observed),
            4,
        )
        if observed
        else None,
    }


def _positive_day_ratio(episodes: list[Mapping[str, Any]], horizon: str) -> float:
    by_day: dict[str, list[float]] = {}
    for row in episodes:
        checkpoint = (
            row.get("checkpoints")
            if isinstance(row.get("checkpoints"), Mapping)
            else {}
        ).get(horizon)
        if not isinstance(checkpoint, Mapping) or checkpoint.get("status") != "observed":
            continue
        by_day.setdefault(str(row.get("day") or ""), []).append(
            float(checkpoint.get("live_net_return_pct") or 0.0)
        )
    if not by_day:
        return 0.0
    positive = sum(1 for values in by_day.values() if sum(values) / len(values) > 0)
    return round(positive / len(by_day), 4)


def scanner_baseline_for_days(
    cumulative_review: Mapping[str, Any],
    *,
    days: set[str],
) -> dict[str, Any]:
    scanner = cumulative_review.get("episode_scanner_review")
    scanner = scanner if isinstance(scanner, Mapping) else {}
    episodes = scanner.get("episodes") if isinstance(scanner.get("episodes"), list) else []
    output: dict[str, Any] = {}
    for horizon in ("+5m", "+15m", "+30m", "EOD"):
        gross = [
            float((row.get("returns") or {}).get(horizon))
            for row in episodes
            if isinstance(row, Mapping)
            and str(row.get("day") or "") in {day.replace("-", "") for day in days}
            and row.get("rank_bucket") == "rank1"
            and isinstance(row.get("returns"), Mapping)
            and (row.get("returns") or {}).get(horizon) is not None
        ]
        output[horizon] = {
            "gross": performance_metrics(gross),
            "live_net": performance_metrics(
                [value - LIVE_COST_PCT for value in gross]
            ),
        }
    return {
        "source": "cumulative_improvement_review.episode_scanner_review",
        "day_count": len(days),
        "horizons": output,
    }


def build_decision(
    *,
    episodes: list[Mapping[str, Any]],
    summaries: list[Mapping[str, Any]],
    scanner_baseline: Mapping[str, Any],
) -> dict[str, Any]:
    day_counts = Counter(str(row.get("day") or "") for row in episodes)
    symbol_counts = Counter(str(row.get("symbol") or "") for row in episodes)
    episode_count = len(episodes)
    largest_day_share = max(day_counts.values(), default=0) / episode_count if episode_count else 0.0
    largest_symbol_share = max(symbol_counts.values(), default=0) / episode_count if episode_count else 0.0
    by_horizon = {str(row.get("horizon") or ""): row for row in summaries}
    row15 = by_horizon.get("+15m") or {}
    row30 = by_horizon.get("+30m") or {}
    live15 = row15.get("live_net") if isinstance(row15.get("live_net"), Mapping) else {}
    live30 = row30.get("live_net") if isinstance(row30.get("live_net"), Mapping) else {}
    baseline30 = (
        (
            scanner_baseline.get("horizons")
            if isinstance(scanner_baseline.get("horizons"), Mapping)
            else {}
        ).get("+30m")
        or {}
    )
    baseline30_live = (
        baseline30.get("live_net")
        if isinstance(baseline30, Mapping)
        and isinstance(baseline30.get("live_net"), Mapping)
        else {}
    )
    positive_day_ratio = _positive_day_ratio(episodes, "+30m")

    evidence = {
        "episode_count": episode_count >= EVIDENCE_GATES["minimum_episode_count"],
        "day_count": len(day_counts) >= EVIDENCE_GATES["minimum_day_count"],
        "symbol_count": len(symbol_counts) >= EVIDENCE_GATES["minimum_symbol_count"],
        "forward_coverage_30m": float(row30.get("coverage") or 0.0)
        >= EVIDENCE_GATES["minimum_forward_coverage"],
        "single_day_concentration": largest_day_share
        <= EVIDENCE_GATES["maximum_single_day_share"],
        "single_symbol_concentration": largest_symbol_share
        <= EVIDENCE_GATES["maximum_single_symbol_share"],
    }
    performance = {
        "live_expectancy_15m_positive": float(live15.get("expectancy_pct") or 0.0)
        > PERFORMANCE_GATES["minimum_live_net_expectancy_15m_pct"],
        "live_expectancy_30m_positive": float(live30.get("expectancy_pct") or 0.0)
        > PERFORMANCE_GATES["minimum_live_net_expectancy_30m_pct"],
        "live_profit_factor_30m": float(live30.get("profit_factor") or 0.0)
        >= PERFORMANCE_GATES["minimum_live_net_profit_factor_30m"],
        "positive_day_ratio_30m": positive_day_ratio
        >= PERFORMANCE_GATES["minimum_positive_day_ratio_30m"],
        "live_mdd_30m": float(live30.get("maximum_drawdown_pct") or 0.0)
        >= PERFORMANCE_GATES["minimum_live_net_mdd_30m_pct"],
        "beats_scanner_rank1_30m": float(live30.get("expectancy_pct") or 0.0)
        > float(baseline30_live.get("expectancy_pct") or 0.0),
    }
    if all(evidence.values()) and all(performance.values()):
        decision = "PROMOTE"
    elif all(evidence.values()) and (
        not performance["live_expectancy_30m_positive"]
        or float(live30.get("profit_factor") or 0.0) <= 1.0
        or not performance["beats_scanner_rank1_30m"]
    ):
        decision = "REJECT"
    else:
        decision = "RETAIN_SHADOW"
    return {
        "decision": decision,
        "evidence_gates": evidence,
        "performance_gates": performance,
        "episode_count": episode_count,
        "day_count": len(day_counts),
        "symbol_count": len(symbol_counts),
        "largest_single_day_share": round(largest_day_share, 4),
        "largest_single_symbol_share": round(largest_symbol_share, 4),
        "positive_day_ratio_30m": positive_day_ratio,
    }
