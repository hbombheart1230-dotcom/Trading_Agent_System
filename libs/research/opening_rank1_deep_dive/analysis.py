from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median, pstdev
from typing import Any


NUMERIC_FEATURES = (
    "scanner_score",
    "risk_score",
    "confidence",
    "entry_compatibility_score",
    "scanner_chart_fit_score",
    "scanner_macro_chart_fit_score",
    "intraday_change_pct",
    "scanner_observed_return_5m_pct",
    "scanner_observed_turnover",
    "vwap_distance_pct",
    "volume_ratio",
    "volume_spike20",
    "trend_strength",
    "adx14",
    "volatility20",
    "sector_relative_strength",
    "cross_section_rank",
    "global_sentiment_score",
    "kospi_pct",
    "kosdaq_pct",
    "krx_night_futures_pct",
    "nasdaq_pct",
    "vix_level",
    "score_trading_value",
    "score_momentum",
    "score_trend",
    "score_ma_alignment",
    "score_adx_trend",
    "score_volume_surge",
    "score_intraday_strength",
    "score_vwap_alignment",
    "score_theme_boost",
    "score_sentiment",
    "score_cross_section_rank",
    "score_repeat_symbol_penalty",
    "score_symbol_prior",
    "score_entry_compatibility_bias",
    "score_macro_chart_fit_bias",
    "score_risk_penalty",
    "baseline_delay_sec",
    "opening_gap_pct",
    "entry_vs_prior_close_pct",
    "path_high_vs_prior_close_pct",
    "open_to_entry_pct",
    "precompleted_return_1m_pct",
    "precompleted_return_3m_pct",
    "precompleted_return_5m_pct",
    "opening_relative_volume",
    "entry_bar_volume",
    "rank1_rank2_gap",
    "rank1_rank2_confidence_delta",
    "rank1_rank2_risk_delta",
    "rank1_score_rank",
    "rank_candidate_count",
    "rank1_age_sec",
    "rank1_forward_persistence_sec",
    "rank1_prev5m_observations",
    "rank1_next5m_observations",
    "rank1_score_change_from_prior",
)


def _values(rows: list[dict[str, Any]], field: str) -> list[float]:
    return [float(row[field]) for row in rows if row.get(field) is not None]


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    returns = _values(rows, "net_return_30m_pct")
    gains = sum(value for value in returns if value > 0)
    losses = abs(sum(value for value in returns if value < 0))
    return {
        "count": len(rows),
        "win_rate": round(sum(value > 0 for value in returns) / len(returns), 4) if returns else None,
        "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else None,
        "median_return_pct": round(median(returns), 4) if returns else None,
        "profit_factor": round(gains / losses, 4) if losses else (999.0 if gains else None),
        "avg_mfe_pct": _mean(rows, "mfe_30m_pct"),
        "avg_mae_pct": _mean(rows, "mae_30m_pct"),
    }


def _mean(rows: list[dict[str, Any]], field: str) -> float | None:
    values = _values(rows, field)
    return round(sum(values) / len(values), 4) if values else None


def grouped(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row.get(field)
        if isinstance(value, list):
            key = "|".join(value) if value else "MISSING"
        else:
            key = "MISSING" if value in (None, "") else str(value)
        groups[key].append(row)
    return {
        key: _summary(value)
        for key, value in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    }


def _return_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "avg_return_pct": None}
    return {
        "count": len(values),
        "avg_return_pct": round(sum(values) / len(values), 4),
        "median_return_pct": round(median(values), 4),
        "positive_ratio": round(sum(value > 0 for value in values) / len(values), 4),
    }


def outlier_sensitivity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    returns = sorted(_values(rows, "net_return_30m_pct"))
    result: dict[str, Any] = {"all": _return_summary(returns)}
    for count in (1, 3, 5):
        result[f"remove_top_{count}"] = _return_summary(returns[:-count])
        result[f"remove_bottom_{count}"] = _return_summary(returns[count:])
        result[f"remove_both_{count}"] = _return_summary(returns[count:-count])
    result["winsorize_5pct"] = _return_summary(
        [max(-5.0, min(5.0, value)) for value in returns]
    )
    total = sum(returns)
    descending = sorted(returns, reverse=True)
    positive = sum(value for value in returns if value > 0)
    result["contribution"] = {
        "total_net_return_sum_pct": round(total, 4),
        "top1_return_pct": round(descending[0], 4),
        "top3_return_sum_pct": round(sum(descending[:3]), 4),
        "top5_return_sum_pct": round(sum(descending[:5]), 4),
        "top3_share_of_positive_gains": round(sum(descending[:3]) / positive, 4) if positive else None,
    }
    return result


def daily_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_day: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.get("net_return_30m_pct") is not None:
            by_day[str(row.get("day") or "")].append(float(row["net_return_30m_pct"]))
    day_means = [sum(values) / len(values) for values in by_day.values()]
    return {
        "day_count": len(day_means),
        "positive_day_ratio": round(sum(value > 0 for value in day_means) / len(day_means), 4)
        if day_means
        else None,
        "avg_daily_mean_return_pct": round(sum(day_means) / len(day_means), 4) if day_means else None,
        "median_daily_mean_return_pct": round(median(day_means), 4) if day_means else None,
        "days": {day: _return_summary(values) for day, values in sorted(by_day.items())},
    }


def hypothesis_screens(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def minute(row: dict[str, Any]) -> int:
        try:
            return int(str(row.get("decision_time_kst") or "")[14:16])
        except ValueError:
            return -1

    predicates = {
        "OPENING_09_00_04": lambda row: 0 <= minute(row) < 5,
        "EARLY_RELATIVE_VOLUME_1X_NOT_OVEREXTENDED": lambda row: (
            1 <= minute(row) < 5
            and row.get("opening_relative_volume") is not None
            and float(row["opening_relative_volume"]) >= 1.0
            and row.get("entry_vs_prior_close_pct") is not None
            and float(row["entry_vs_prior_close_pct"]) < 20.0
        ),
        "EARLY_RELATIVE_VOLUME_2X_NOT_OVEREXTENDED": lambda row: (
            1 <= minute(row) < 5
            and row.get("opening_relative_volume") is not None
            and float(row["opening_relative_volume"]) >= 2.0
            and row.get("entry_vs_prior_close_pct") is not None
            and float(row["entry_vs_prior_close_pct"]) < 20.0
        ),
        "LATE_09_15_19_NO_CHASE": lambda row: (
            15 <= minute(row) < 20
            and row.get("open_to_entry_pct") is not None
            and float(row["open_to_entry_pct"]) < 7.0
        ),
        "PRIOR_RANK_CONFIRMATION_NO_CHASE": lambda row: (
            int(row.get("rank1_prev5m_observations") or 0) >= 1
            and row.get("open_to_entry_pct") is not None
            and float(row["open_to_entry_pct"]) < 7.0
        ),
        "CRASH_DISLOCATION_ENTRY": lambda row: (
            row.get("entry_vs_prior_close_pct") is not None
            and float(row["entry_vs_prior_close_pct"]) <= -10.0
        ),
    }
    result: dict[str, Any] = {}
    for name, predicate in predicates.items():
        selected = [row for row in rows if predicate(row)]
        returns = sorted(_values(selected, "net_return_30m_pct"), reverse=True)
        days = {str(row.get("day") or "") for row in selected}
        symbols = {str(row.get("symbol") or "") for row in selected}
        summary = _summary(selected)
        summary.update(
            {
                "day_count": len(days),
                "symbol_count": len(symbols),
                "avg_without_top3_pct": round(sum(returns[3:]) / len(returns[3:]), 4)
                if len(returns) > 3
                else None,
                "winsorized_5pct_avg": round(
                    sum(max(-5.0, min(5.0, value)) for value in returns) / len(returns),
                    4,
                )
                if returns
                else None,
                "evidence_status": "SCREENABLE"
                if len(selected) >= 15 and len(days) >= 10
                else "INSUFFICIENT_EVIDENCE",
            }
        )
        result[name] = summary
    return result


def winner_loser_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    winners = [row for row in rows if row.get("outcome") == "WIN"]
    losers = [row for row in rows if row.get("outcome") == "LOSS"]
    features = {}
    for field in NUMERIC_FEATURES:
        win_mean = _mean(winners, field)
        loss_mean = _mean(losers, field)
        all_values = _values(rows, field)
        scale = pstdev(all_values) if len(all_values) >= 2 else 0.0
        features[field] = {
            "winner_mean": win_mean,
            "loser_mean": loss_mean,
            "delta": round(win_mean - loss_mean, 4)
            if win_mean is not None and loss_mean is not None
            else None,
            "winner_n": len(_values(winners, field)),
            "loser_n": len(_values(losers, field)),
            "standardized_effect": round((win_mean - loss_mean) / scale, 4)
            if win_mean is not None and loss_mean is not None and scale > 0
            else None,
        }
    return {"winners": _summary(winners), "losers": _summary(losers), "features": features}


def _minute_bucket(value: str) -> str:
    try:
        minute = int(value[14:16])
    except (TypeError, ValueError):
        return "MISSING"
    start = (minute // 5) * 5
    return f"09:{start:02d}-{start + 4:02d}"


def _market_bucket(row: dict[str, Any]) -> str:
    kospi = row.get("kospi_pct")
    kosdaq = row.get("kosdaq_pct")
    values = [float(value) for value in (kospi, kosdaq) if value is not None]
    if not values:
        return "MISSING"
    average = sum(values) / len(values)
    if average >= 1.0:
        return "STRONG_UP"
    if average >= 0.0:
        return "UP_OR_FLAT"
    if average > -1.0:
        return "MILD_DOWN"
    return "SHARP_DOWN"


def _numeric_bucket(value: Any, cuts: tuple[float, ...], labels: tuple[str, ...]) -> str:
    if value is None:
        return "MISSING"
    number = float(value)
    for cut, label in zip(cuts, labels):
        if number < cut:
            return label
    return labels[-1]


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    enriched = []
    for row in rows:
        copy = dict(row)
        copy["decision_5m_bucket"] = _minute_bucket(str(row.get("decision_time_kst") or ""))
        copy["market_bucket"] = _market_bucket(row)
        copy["baseline_delay_bucket"] = _numeric_bucket(
            row.get("baseline_delay_sec"),
            (31, 61, 121, float("inf")),
            ("<=30s", "31-60s", "61-120s", ">120s"),
        )
        copy["open_to_entry_bucket"] = _numeric_bucket(
            row.get("open_to_entry_pct"),
            (-1.0, 1.0, 3.0, 7.0, float("inf")),
            ("<-1%", "-1~1%", "1~3%", "3~7%", ">=7%"),
        )
        copy["opening_gap_bucket"] = _numeric_bucket(
            row.get("opening_gap_pct"),
            (-2.0, 0.0, 2.0, 5.0, float("inf")),
            ("<-2%", "-2~0%", "0~2%", "2~5%", ">=5%"),
        )
        copy["opening_relative_volume_bucket"] = _numeric_bucket(
            row.get("opening_relative_volume"),
            (0.75, 1.25, 2.0, 4.0, float("inf")),
            ("<0.75x", "0.75~1.25x", "1.25~2x", "2~4x", ">=4x"),
        )
        copy["rank_gap_bucket"] = _numeric_bucket(
            row.get("rank1_rank2_gap"),
            (0.05, 0.15, 0.30, float("inf")),
            ("<0.05", "0.05~0.15", "0.15~0.30", ">=0.30"),
        )
        copy["rank_age_bucket"] = _numeric_bucket(
            row.get("rank1_age_sec"),
            (1, 61, 181, float("inf")),
            ("new", "<=60s", "61~180s", ">180s"),
        )
        enriched.append(copy)
    fade = [
        row
        for row in enriched
        if float(row.get("mfe_30m_pct") or 0) >= 1.0 and float(row.get("net_return_30m_pct") or 0) <= 0
    ]
    shakeout = [
        row
        for row in enriched
        if float(row.get("mae_30m_pct") or 0) <= -1.0 and float(row.get("net_return_30m_pct") or 0) > 0
    ]
    late_payoff = [
        row
        for row in enriched
        if float(row.get("return_5m_pct") or 0) <= 0 and float(row.get("net_return_30m_pct") or 0) > 0
    ]
    early_fade = [
        row
        for row in enriched
        if float(row.get("return_5m_pct") or 0) > 0 and float(row.get("net_return_30m_pct") or 0) <= 0
    ]
    return {
        "overall": _summary(enriched),
        "winner_loser": winner_loser_comparison(enriched),
        "by_decision_5m_bucket": grouped(enriched, "decision_5m_bucket"),
        "by_source_class": grouped(enriched, "source_class"),
        "by_source_combination": grouped(enriched, "sources"),
        "by_tactic": grouped(enriched, "tactic_id"),
        "by_playbook": grouped(enriched, "playbook"),
        "by_scenario": grouped(enriched, "strategist_scenario"),
        "by_market_bucket": grouped(enriched, "market_bucket"),
        "by_above_vwap": grouped(enriched, "above_vwap"),
        "by_path_type": grouped(enriched, "path_type"),
        "by_price_arc": grouped(enriched, "price_arc"),
        "by_baseline_delay": grouped(enriched, "baseline_delay_bucket"),
        "by_open_to_entry": grouped(enriched, "open_to_entry_bucket"),
        "by_opening_gap": grouped(enriched, "opening_gap_bucket"),
        "by_opening_relative_volume": grouped(enriched, "opening_relative_volume_bucket"),
        "by_rank_gap": grouped(enriched, "rank_gap_bucket"),
        "by_rank1_highest_score": grouped(enriched, "rank1_is_highest_score"),
        "by_rank_age": grouped(enriched, "rank_age_bucket"),
        "by_symbol": grouped(enriched, "symbol"),
        "by_theme": grouped(
            [{**row, "primary_theme": (row.get("themes") or ["MISSING"])[0]} for row in enriched],
            "primary_theme",
        ),
        "path_patterns": {
            "profit_fade": _summary(fade),
            "deep_shakeout_then_win": _summary(shakeout),
            "negative_5m_then_30m_win": _summary(late_payoff),
            "positive_5m_then_30m_loss": _summary(early_fade),
        },
        "outlier_sensitivity": outlier_sensitivity(enriched),
        "daily": daily_summary(enriched),
        "hypothesis_screens": hypothesis_screens(enriched),
        "concentration": {
            "symbol_counts": dict(Counter(str(row.get("symbol") or "") for row in enriched).most_common()),
            "day_counts": dict(Counter(str(row.get("day") or "") for row in enriched).most_common()),
        },
        "top_winners": sorted(enriched, key=lambda row: float(row.get("net_return_30m_pct") or -999), reverse=True)[:10],
        "top_losers": sorted(enriched, key=lambda row: float(row.get("net_return_30m_pct") or 999))[:10],
    }
