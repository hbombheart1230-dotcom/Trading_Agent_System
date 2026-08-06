from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable, Mapping

from .metrics import evidence_profile, evidence_status, number, performance, positive_day_rate

HORIZONS = {
    "5m": "return_5m_pct",
    "15m": "return_15m_pct",
    "30m": "net_return_30m_pct",
    "60m": "return_60m_pct",
    "EOD": "return_eod_pct",
}


def _bucket(value: Any, cuts: tuple[float, ...], labels: tuple[str, ...]) -> str:
    observed = number(value)
    if observed is None:
        return "MISSING"
    for cut, label in zip(cuts, labels):
        if observed < cut:
            return label
    return labels[-1]


def _decision_bucket(row: Mapping[str, Any]) -> str:
    seconds = number(row.get("decision_from_open_sec"))
    if seconds is None:
        return "MISSING"
    if seconds < 300:
        return "09:00-09:04"
    if seconds < 600:
        return "09:05-09:09"
    if seconds < 900:
        return "09:10-09:14"
    return "09:15-09:19"


def _market_bucket(row: Mapping[str, Any]) -> str:
    kospi = number(row.get("kospi_pct"))
    sentiment = number(row.get("global_sentiment_score"))
    if kospi is not None:
        if kospi <= -1.5:
            return "SHARP_RISK_OFF"
        if kospi < -0.3:
            return "RISK_OFF"
        if kospi >= 1.0:
            return "RISK_ON"
        return "NEUTRAL"
    if sentiment is not None:
        if sentiment <= -0.35:
            return "RISK_OFF_PROXY"
        if sentiment >= 0.35:
            return "RISK_ON_PROXY"
        return "NEUTRAL_PROXY"
    return "MISSING"


DIMENSIONS: dict[str, Callable[[Mapping[str, Any]], str]] = {
    "decision_time": _decision_bucket,
    "source_class": lambda row: str(row.get("source_class") or "MISSING"),
    "tactic": lambda row: str(row.get("tactic_id") or "MISSING"),
    "playbook": lambda row: str(row.get("playbook") or "MISSING"),
    "scenario": lambda row: str(row.get("strategist_scenario") or "MISSING"),
    "path_type": lambda row: str(row.get("path_type") or "MISSING"),
    "price_arc": lambda row: str(row.get("price_arc") or "MISSING"),
    "above_vwap": lambda row: str(row.get("above_vwap") if row.get("above_vwap") is not None else "MISSING"),
    "market_regime": lambda row: str(row.get("engine_regime") or "MISSING"),
    "market_state": _market_bucket,
    "opening_gap": lambda row: _bucket(row.get("opening_gap_pct"), (-2, 0, 2, 5), ("<-2%", "-2~0%", "0~2%", "2~5%", ">=5%")),
    "entry_extension": lambda row: _bucket(row.get("entry_vs_prior_close_pct"), (0, 2, 5, 10), ("<0%", "0~2%", "2~5%", "5~10%", ">=10%")),
    "relative_volume": lambda row: _bucket(row.get("opening_relative_volume"), (1, 1.5, 2, 4), ("<1x", "1~1.5x", "1.5~2x", "2~4x", ">=4x")),
    "scanner_score": lambda row: _bucket(row.get("scanner_score"), (0.5, 0.75, 1.0, 1.25), ("<0.50", "0.50~0.75", "0.75~1.00", "1.00~1.25", ">=1.25")),
    "risk_score": lambda row: _bucket(row.get("risk_score"), (0.4, 0.7), ("LOW", "MEDIUM", "HIGH")),
    "chart_fit": lambda row: _bucket(row.get("scanner_chart_fit_score"), (0.35, 0.65), ("LOW", "MEDIUM", "HIGH")),
    "macro_chart_fit": lambda row: _bucket(row.get("scanner_macro_chart_fit_score"), (0.35, 0.65), ("LOW", "MEDIUM", "HIGH")),
}

OUTCOME_DERIVED_DIMENSIONS = {"path_type", "price_arc"}


def _group_summary(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    metrics = performance(row.get(field) for row in rows)
    profile = evidence_profile(rows)
    values = sorted(
        [value for row in rows if (value := number(row.get(field))) is not None],
        reverse=True,
    )
    without_top3 = values[3:] if len(values) > 3 else []
    positive_sum = sum(value for value in values if value > 0)
    top3_positive = sum(value for value in values[:3] if value > 0)
    return {
        **metrics,
        **profile,
        "positive_day_rate": positive_day_rate(rows, field),
        "average_without_top3_pct": round(sum(without_top3) / len(without_top3), 4)
        if without_top3
        else None,
        "top3_positive_profit_share": round(top3_positive / positive_sum, 4)
        if positive_sum
        else None,
        "evidence_status": evidence_status(metrics, profile),
    }


def opening_cross_sections(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for dimension, resolver in DIMENSIONS.items():
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[resolver(row)].append(row)
        for value, group in sorted(grouped.items()):
            for horizon, field in HORIZONS.items():
                summary = _group_summary(group, field)
                output.append(
                    {
                        "dimension": dimension,
                        "value": value,
                        "horizon": horizon,
                        "point_in_time_eligible": dimension not in OUTCOME_DERIVED_DIMENSIONS,
                        **summary,
                    }
                )
    return output


def themes_cross_sections(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        themes = row.get("themes")
        if isinstance(themes, list):
            for theme in {str(item) for item in themes if str(item)}:
                grouped[theme].append(row)
    result = []
    for theme, group in sorted(grouped.items()):
        for horizon, field in HORIZONS.items():
            result.append(
                {
                    "dimension": "theme",
                    "value": theme,
                    "horizon": horizon,
                    "point_in_time_eligible": True,
                    **_group_summary(group, field),
                }
            )
    return result


def research_candidates(cross_sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for row in cross_sections:
        if not row.get("point_in_time_eligible") or row.get("value") == "MISSING":
            continue
        if row.get("evidence_status") != "SCREENABLE":
            continue
        if number(row.get("average_pct")) is None or number(row.get("average_pct")) <= 0:
            continue
        if number(row.get("profit_factor")) is None or number(row.get("profit_factor")) <= 1:
            continue
        if number(row.get("positive_day_rate")) is None or number(row.get("positive_day_rate")) < 0.5:
            continue
        if number(row.get("average_without_top3_pct")) is None or number(row.get("average_without_top3_pct")) <= 0:
            continue
        if number(row.get("largest_day_share")) and number(row.get("largest_day_share")) > 0.4:
            continue
        if number(row.get("largest_symbol_share")) and number(row.get("largest_symbol_share")) > 0.4:
            continue
        candidates.append(dict(row))
    return sorted(
        candidates,
        key=lambda row: (number(row.get("average_pct")) or -999, int(row.get("count") or 0)),
        reverse=True,
    )


def predefined_opening_screens(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def observed(row: Mapping[str, Any], key: str, default: float) -> float:
        value = number(row.get(key))
        return default if value is None else value

    def rank_positive_1m(row: Mapping[str, Any]) -> bool:
        return (
            observed(row, "rank1_prev5m_observations", 0) >= 1
            and observed(row, "precompleted_return_1m_pct", 0) > 0
        )

    def moderate_relative_volume(row: Mapping[str, Any]) -> bool:
        value = number(row.get("opening_relative_volume"))
        return value is not None and 0.5 <= value <= 4.0

    def dislocation(row: Mapping[str, Any]) -> bool:
        kospi = number(row.get("kospi_pct"))
        extension = number(row.get("entry_vs_prior_close_pct"))
        return bool(
            (kospi is not None and kospi <= -3)
            or (extension is not None and extension <= -8)
        )

    screens: dict[str, Callable[[Mapping[str, Any]], bool]] = {
        "OPEN_0_5_ALL": lambda row: observed(row, "decision_from_open_sec", 9999) < 300,
        "OPEN_0_5_ABOVE_VWAP": lambda row: observed(row, "decision_from_open_sec", 9999) < 300 and row.get("above_vwap") is True,
        "OPEN_0_5_SCORE_GE_1_25": lambda row: observed(row, "decision_from_open_sec", 9999) < 300 and observed(row, "scanner_score", -999) >= 1.25,
        "OPEN_0_5_GAP_0_5": lambda row: observed(row, "decision_from_open_sec", 9999) < 300 and 0 <= observed(row, "opening_gap_pct", -999) < 5,
        "OPEN_0_10_NOT_EXTENDED": lambda row: observed(row, "decision_from_open_sec", 9999) < 600 and observed(row, "entry_vs_prior_close_pct", 999) < 5,
        "OPEN_PRIOR_RANK_CONFIRMATION": lambda row: int(observed(row, "rank1_prev5m_observations", 0)) >= 1 and observed(row, "entry_vs_prior_close_pct", 999) < 5,
        "CONFIRMED_RANK_POSITIVE_1M": rank_positive_1m,
        "CONFIRMED_RANK_POSITIVE_1M_MODERATE_VOLUME": lambda row: rank_positive_1m(row) and moderate_relative_volume(row),
        "CONFIRMED_RANK_POSITIVE_1M_ABOVE_VWAP": lambda row: rank_positive_1m(row) and row.get("above_vwap") is True,
        "DISLOCATION_MODERATE_VOLUME": lambda row: dislocation(row) and moderate_relative_volume(row),
    }
    result = []
    for name, predicate in screens.items():
        group = [row for row in rows if predicate(row)]
        for horizon, field in HORIZONS.items():
            result.append(
                {
                    "screen": name,
                    "horizon": horizon,
                    "point_in_time_eligible": True,
                    **_group_summary(group, field),
                }
            )
    return result


def _scenario_value(row: Mapping[str, Any], scenario: str) -> float | None:
    scenarios = row.get("scenario_returns")
    scenarios = scenarios if isinstance(scenarios, Mapping) else {}
    payload = scenarios.get(scenario)
    payload = payload if isinstance(payload, Mapping) else {}
    return number(payload.get("live_net_return_pct"))


def horizon_reversals(
    horizon_rows: list[dict[str, Any]], contexts: Mapping[str, Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = []
    scenario_names = sorted(
        {
            str(name)
            for row in horizon_rows
            for name in (row.get("scenario_returns") or {})
            if str(name) != "actual_exit"
        }
    )
    grouped_values: dict[str, list[float]] = defaultdict(list)
    for row in horizon_rows:
        trade_id = str(row.get("trade_id") or "")
        context = dict(contexts.get(trade_id) or {})
        actual = _scenario_value(row, "actual_exit")
        broker = number(row.get("broker_realized_net_return_pct"))
        scenarios = []
        for scenario in scenario_names:
            alternative = _scenario_value(row, scenario)
            if alternative is None or actual is None:
                continue
            delta = round(alternative - actual, 4)
            grouped_values[scenario].append(delta)
            scenarios.append({"scenario": scenario, "return_pct": alternative, "delta_vs_actual_pct": delta})
        best = max(scenarios, key=lambda item: item["return_pct"], default=None)
        result.append(
            {
                **context,
                "trade_id": trade_id,
                "day": row.get("day") or context.get("day"),
                "symbol": row.get("symbol") or context.get("symbol"),
                "entry_horizon": row.get("entry_horizon") or context.get("strategy_horizon"),
                "holding_seconds": row.get("holding_seconds") or context.get("holding_seconds"),
                "exit_reason": row.get("exit_reason") or context.get("exit_reason"),
                "broker_realized_net_return_pct": broker,
                "actual_live_net_return_pct": actual,
                "alternatives": scenarios,
                "best_alternative": best,
                "loss_to_win": bool(actual is not None and actual <= 0 and best and best["return_pct"] > 0),
                "winner_giveback_risk": bool(actual is not None and actual > 0 and best and best["return_pct"] <= 0),
            }
        )
    summary = {
        scenario: performance(values)
        for scenario, values in grouped_values.items()
    }
    return result, summary


def _holding_bucket(value: Any) -> str:
    seconds = number(value)
    if seconds is None:
        return "MISSING"
    if seconds < 60:
        return "<1m"
    if seconds < 300:
        return "1~5m"
    if seconds < 900:
        return "5~15m"
    if seconds < 1800:
        return "15~30m"
    return ">=30m"


def _exit_class(value: Any) -> str:
    text = str(value or "").lower()
    for key in ("hard_stop", "stop_loss", "trend_breakdown", "vwap_breakdown", "intraday_low_break", "eod_flat"):
        if key in text:
            return key
    if "reconciled" in text:
        return "broker_reconciled"
    return "other"


def horizon_cross_sections(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dimensions: dict[str, Callable[[Mapping[str, Any]], str]] = {
        "strategy_horizon": lambda row: str(row.get("strategy_horizon") or row.get("entry_horizon") or "MISSING"),
        "playbook": lambda row: str(row.get("playbook") or "MISSING"),
        "exit_reason": lambda row: _exit_class(row.get("exit_reason")),
        "holding_time": lambda row: _holding_bucket(row.get("holding_seconds")),
        "selected_rank": lambda row: str(row.get("selected_rank") if row.get("selected_rank") is not None else "MISSING"),
        "chart_fit": lambda row: _bucket(row.get("chart_fit_score"), (0.35, 0.65), ("LOW", "MEDIUM", "HIGH")),
        "scanner_score": lambda row: _bucket(row.get("scanner_score"), (0.5, 0.75, 1.0, 1.25), ("<0.50", "0.50~0.75", "0.75~1.00", "1.00~1.25", ">=1.25")),
        "risk_score": lambda row: _bucket(row.get("risk_score"), (0.4, 0.7), ("LOW", "MEDIUM", "HIGH")),
    }
    result = []
    for dimension, resolver in dimensions.items():
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[resolver(row)].append(row)
        for value, group in sorted(grouped.items()):
            scenarios = sorted(
                {
                    str(item.get("scenario"))
                    for row in group
                    for item in (row.get("alternatives") or [])
                }
            )
            for scenario in scenarios:
                observations = []
                for row in group:
                    item = next(
                        (
                            item
                            for item in (row.get("alternatives") or [])
                            if item.get("scenario") == scenario
                        ),
                        None,
                    )
                    if item:
                        observations.append(
                            {
                                "day": row.get("day"),
                                "symbol": row.get("symbol"),
                                "delta_vs_actual_pct": item.get("delta_vs_actual_pct"),
                            }
                        )
                metrics = performance(row.get("delta_vs_actual_pct") for row in observations)
                profile = evidence_profile(observations)
                result.append(
                    {
                        "dimension": dimension,
                        "value": value,
                        "scenario": scenario,
                        "alternative_observation_count": len(observations),
                        "delta_metrics": metrics,
                        **profile,
                        "evidence_status": evidence_status(metrics, profile),
                    }
                )
    return result


def actual_live_cost_cross_sections(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dimensions: dict[str, Callable[[Mapping[str, Any]], str]] = {
        "strategy_horizon": lambda row: str(row.get("strategy_horizon") or row.get("entry_horizon") or "MISSING"),
        "playbook": lambda row: str(row.get("playbook") or "MISSING"),
        "exit_reason": lambda row: _exit_class(row.get("exit_reason")),
        "holding_time": lambda row: _holding_bucket(row.get("holding_seconds")),
        "selected_rank": lambda row: str(row.get("selected_rank") if row.get("selected_rank") is not None else "MISSING"),
        "chart_fit": lambda row: _bucket(row.get("chart_fit_score"), (0.35, 0.65), ("LOW", "MEDIUM", "HIGH")),
        "scanner_score": lambda row: _bucket(row.get("scanner_score"), (0.5, 0.75, 1.0, 1.25), ("<0.50", "0.50~0.75", "0.75~1.00", "1.00~1.25", ">=1.25")),
        "risk_score": lambda row: _bucket(row.get("risk_score"), (0.4, 0.7), ("LOW", "MEDIUM", "HIGH")),
    }
    result = []
    for dimension, resolver in dimensions.items():
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[resolver(row)].append(row)
        for value, group in sorted(grouped.items()):
            metrics = performance(row.get("actual_live_net_return_pct") for row in group)
            profile = evidence_profile(group)
            result.append(
                {
                    "dimension": dimension,
                    "value": value,
                    **metrics,
                    **profile,
                    "evidence_status": evidence_status(metrics, profile),
                }
            )
    return result


def delayed_reactivation(events: list[dict[str, Any]]) -> dict[str, Any]:
    labels: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in events:
        labels[str(row.get("selection_horizon_label") or "MISSING")].append(row)
    return {
        label: {
            "count": len(group),
            "30m": performance(row.get("net_return_30m_pct") for row in group),
            "same_day_close": performance(row.get("same_day_close_net_pct") for row in group),
            "d1_close": performance(row.get("d1_close_net_pct") for row in group),
            "d5_close": performance(row.get("d5_close_net_pct") for row in group),
            "d5_high": performance(row.get("d5_max_high_net_pct") for row in group),
            "playbooks": dict(sorted(Counter(str(row.get("playbook") or "MISSING") for row in group).items())),
            "scenarios": dict(sorted(Counter(str(row.get("strategist_scenario") or "MISSING") for row in group).items())),
        }
        for label, group in sorted(labels.items())
    }


def casebook(opening_rows: list[dict[str, Any]], horizon_rows: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in opening_rows if number(row.get("net_return_30m_pct")) is not None]
    winners = sorted(valid, key=lambda row: number(row.get("net_return_30m_pct")) or -999, reverse=True)[:15]
    losers = sorted(valid, key=lambda row: number(row.get("net_return_30m_pct")) or 999)[:15]
    reversals = sorted(
        [row for row in horizon_rows if row.get("loss_to_win")],
        key=lambda row: number((row.get("best_alternative") or {}).get("delta_vs_actual_pct")) or -999,
        reverse=True,
    )[:20]
    delayed = sorted(
        [row for row in events if row.get("delayed_high_opportunity")],
        key=lambda row: number(row.get("d5_max_high_net_pct")) or -999,
        reverse=True,
    )[:20]
    return {"opening_winners": winners, "opening_losers": losers, "hold_loss_to_win": reversals, "delayed_reactivation": delayed}


def precursor_profiles(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def observed_return(row: Mapping[str, Any], default: float) -> float:
        value = number(row.get("net_return_30m_pct"))
        return default if value is None else value

    cohorts = {
        "STRONG_30M": [row for row in rows if observed_return(row, -999) >= 2],
        "MODEST_WIN_30M": [row for row in rows if 0 < observed_return(row, -999) < 2],
        "NON_POSITIVE_30M": [row for row in rows if observed_return(row, 999) <= 0],
    }
    numeric_fields = (
        "scanner_score",
        "risk_score",
        "confidence",
        "rank1_rank2_gap",
        "rank1_prev5m_observations",
        "opening_gap_pct",
        "entry_vs_prior_close_pct",
        "open_to_entry_pct",
        "precompleted_return_1m_pct",
        "opening_relative_volume",
        "scanner_chart_fit_score",
        "scanner_macro_chart_fit_score",
        "kospi_pct",
        "kosdaq_pct",
        "krx_night_futures_pct",
        "nasdaq_pct",
        "vix_level",
    )
    output = {}
    for name, group in cohorts.items():
        numeric = {}
        for field in numeric_fields:
            values = [value for row in group if (value := number(row.get(field))) is not None]
            numeric[field] = {
                "count": len(values),
                "average": round(sum(values) / len(values), 4) if values else None,
            }
        output[name] = {
            "count": len(group),
            "numeric": numeric,
            "playbooks": dict(sorted(Counter(str(row.get("playbook") or "MISSING") for row in group).items())),
            "scenarios": dict(sorted(Counter(str(row.get("strategist_scenario") or "MISSING") for row in group).items())),
            "sources": dict(sorted(Counter(str(row.get("source_class") or "MISSING") for row in group).items())),
        }
    return output


def _archetype(row: Mapping[str, Any]) -> str:
    kospi = number(row.get("kospi_pct"))
    extension = number(row.get("entry_vs_prior_close_pct"))
    seconds = number(row.get("decision_from_open_sec"))
    if (kospi is not None and kospi <= -3) or (
        extension is not None and extension <= -8
    ):
        return "DISLOCATION_REBOUND"
    if seconds is not None and seconds < 60:
        return "IMMEDIATE_0_1M"
    if seconds is not None and seconds < 300:
        return "EARLY_1_5M"
    if seconds is not None and seconds < 1200:
        return "MATURED_5_20M"
    return "OTHER"


def opening_archetype_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_archetype(row)].append(row)
    result = {}
    for name, group in sorted(grouped.items()):
        values = sorted(
            [value for row in group if (value := number(row.get("net_return_30m_pct"))) is not None],
            reverse=True,
        )
        metrics = performance(values)
        result[name] = {
            **metrics,
            "strong_30m_count": sum(value >= 2 for value in values),
            "average_without_top1_pct": round(sum(values[1:]) / len(values[1:]), 4)
            if len(values) > 1
            else None,
            "average_without_top3_pct": round(sum(values[3:]) / len(values[3:]), 4)
            if len(values) > 3
            else None,
            "playbooks": dict(
                sorted(Counter(str(row.get("playbook") or "MISSING") for row in group).items())
            ),
            "scenarios": dict(
                sorted(Counter(str(row.get("strategist_scenario") or "MISSING") for row in group).items())
            ),
            "scanner_score_average": _mean(group, "scanner_score"),
            "risk_score_average": _mean(group, "risk_score"),
            "confidence_average": _mean(group, "confidence"),
            "opening_gap_average_pct": _mean(group, "opening_gap_pct"),
            "entry_extension_average_pct": _mean(group, "entry_vs_prior_close_pct"),
            "opening_relative_volume_average": _mean(group, "opening_relative_volume"),
            "kospi_average_pct": _mean(group, "kospi_pct"),
        }
    return result


def _mean(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [value for row in rows if (value := number(row.get(field))) is not None]
    return round(sum(values) / len(values), 4) if values else None
