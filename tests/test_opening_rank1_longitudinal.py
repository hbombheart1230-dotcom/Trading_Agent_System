from __future__ import annotations

from datetime import datetime, timedelta, timezone

from libs.research.opening_rank1_longitudinal.analysis import (
    analyze_longitudinal,
    analyze_stage_fates,
)
from libs.research.opening_rank1_longitudinal.delayed_outcomes import (
    delayed_path,
)
from libs.research.opening_rank1_longitudinal.pipeline import (
    _daily_trading_calendar,
)
from libs.research.opening_rank1_longitudinal.stage_fate import stage_fate
from libs.research.opening_rank1_longitudinal.universe_control import (
    analyze_universe_paths,
    build_universe_paths,
    universe_candidates,
)


KST = timezone(timedelta(hours=9))


def _epoch(day: str, hour: int, minute: int) -> int:
    return int(
        datetime.fromisoformat(day)
        .replace(hour=hour, minute=minute, tzinfo=KST)
        .timestamp()
    )


def _row(day: str, hour: int, minute: int, price: float) -> dict:
    return {
        "ts": _epoch(day, hour, minute),
        "raw_ts": day.replace("-", "") + f"{hour:02d}{minute:02d}00",
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": 100,
    }


def test_delayed_path_uses_market_calendar_without_skipping_missing_day() -> None:
    case = {
        "day": "2026-07-01",
        "virtual_buy_time_kst": datetime.fromtimestamp(
            _epoch("2026-07-01", 9, 1),
            tz=KST,
        ).isoformat(),
        "virtual_buy_price": 100.0,
        "net_return_30m_pct": -1.0,
    }
    rows = [
        _row("2026-07-01", 9, 31, 99.0),
        _row("2026-07-01", 15, 20, 99.0),
        _row("2026-07-02", 9, 0, 102.0),
        _row("2026-07-02", 15, 20, 101.0),
        _row("2026-07-06", 9, 0, 110.0),
        _row("2026-07-06", 15, 20, 109.0),
    ]
    result = delayed_path(
        case,
        rows,
        trading_calendar=[
            "2026-07-01",
            "2026-07-02",
            "2026-07-03",
            "2026-07-06",
        ],
    )

    assert result["d1_status"] == "OBSERVED"
    assert result["d3_status"] == "INSUFFICIENT_FUTURE_DAYS"
    assert result["d3_missing_days"] == ["2026-07-03"]


def test_daily_cache_dates_are_the_authoritative_trading_calendar() -> None:
    calendar = _daily_trading_calendar(
        {
            "A": [
                {"day": "2026-07-23"},
                {"day": "2026-07-24"},
                {"day": "2026-07-27"},
            ],
            "B": [
                {"day": "2026-07-24"},
                {"day": "2026-07-27"},
            ],
        }
    )

    assert calendar == [
        "2026-07-23",
        "2026-07-24",
        "2026-07-27",
    ]


def test_delayed_path_distinguishes_high_and_close_confirmation() -> None:
    days = [
        "2026-07-01",
        "2026-07-02",
        "2026-07-03",
        "2026-07-06",
        "2026-07-07",
        "2026-07-08",
    ]
    rows = [
        _row("2026-07-01", 9, 31, 99.0),
        _row("2026-07-01", 15, 20, 99.0),
    ]
    for index, day in enumerate(days[1:], start=1):
        rows.extend(
            [
                _row(day, 9, 0, 100.0 + index),
                _row(day, 10, 0, 102.0 + index),
                _row(day, 15, 20, 99.0 + index),
            ]
        )
    result = delayed_path(
        {
            "day": "2026-07-01",
            "virtual_buy_time_kst": datetime.fromtimestamp(
                _epoch("2026-07-01", 9, 1),
                tz=KST,
            ).isoformat(),
            "virtual_buy_price": 100.0,
            "net_return_30m_pct": -1.0,
        },
        rows,
        trading_calendar=days,
    )

    assert result["d5_status"] == "OBSERVED"
    assert result["delayed_high_opportunity"] is True
    assert result["delayed_close_confirmation"] is True
    assert result["selection_horizon_label"] == "HORIZON_TOO_SHORT_CONFIRMED"


def test_stage_fate_tracks_strategist_and_monitor_switch() -> None:
    day = "2026-07-01"
    rows_a = [
        _row(day, 9, 1, 100.0),
        _row(day, 9, 31, 110.0),
    ]
    rows_b = [
        _row(day, 9, 1, 100.0),
        _row(day, 9, 31, 95.0),
    ]
    result = stage_fate(
        {
            "day": day,
            "symbol": "A",
            "net_return_30m_pct": 9.72,
        },
        window={
            "decision_epoch": _epoch(day, 9, 0),
            "strategist_selection": {
                "selected_symbol": "B",
                "post_strategist_top10": [
                    {"rank": 1, "symbol": "B"},
                    {"rank": 2, "symbol": "A"},
                ],
            },
            "commander_final": {
                "candidate_symbol": "B",
                "monitor_intent": "BUY",
                "decision": "approve",
            },
        },
        minute_rows_by_symbol={"A": rows_a, "B": rows_b},
        execution={
            "trade_id": "T1",
            "symbol": "B",
            "realized_return_pct": -1.0,
        },
    )

    assert result["strategist_relation"] == "DEMOTED"
    assert result["monitor_relation"] == "SWITCHED_SYMBOL"
    assert result["strategist_selected_30m_net_pct"] == -5.28
    assert result["intrinsic_preserved_to_execution"] is False


def test_stage_analysis_uses_paired_deltas() -> None:
    result = analyze_stage_fates(
        [
            {
                "intrinsic_30m_net_pct": 2.0,
                "strategist_selected_30m_net_pct": 1.0,
                "monitor_candidate_30m_net_pct": 1.5,
                "strategist_relation": "DEMOTED",
                "monitor_relation": "SWITCHED_SYMBOL",
                "commander_decision": "approve",
            },
            {
                "intrinsic_30m_net_pct": -1.0,
                "strategist_selected_30m_net_pct": 0.0,
                "monitor_candidate_30m_net_pct": 0.0,
                "strategist_relation": "KEPT_TOP1",
                "monitor_relation": "PRESERVED_INTRINSIC",
                "commander_decision": "reject",
            },
        ]
    )

    paired = result["paired_stage_delta"]["strategist_vs_intrinsic"]
    assert paired["count"] == 2
    assert paired["average_pct"] == 0.0
    assert paired["improved_count"] == 1
    assert paired["degraded_count"] == 1


def test_longitudinal_analysis_separates_high_from_close_retention() -> None:
    result = analyze_longitudinal(
        [
            {
                "d5_status": "OBSERVED",
                "net_return_30m_pct": -1.0,
                "delayed_high_opportunity": True,
                "delayed_close_confirmation": False,
                "d1_max_high_net_pct": 6.0,
                "selection_horizon_label": "DELAYED_HIGH_ONLY",
            },
            {
                "d5_status": "OBSERVED",
                "net_return_30m_pct": -2.0,
                "delayed_high_opportunity": True,
                "delayed_close_confirmation": True,
                "d1_max_high_net_pct": 1.0,
                "selection_horizon_label": "HORIZON_TOO_SHORT_CONFIRMED",
            },
            {
                "d5_status": "OBSERVED",
                "net_return_30m_pct": -3.0,
                "delayed_high_opportunity": False,
                "delayed_close_confirmation": False,
                "selection_horizon_label": "NO_LATER_EDGE",
            },
        ]
    )

    assert result["negative_d5_complete_count"] == 3
    assert result["delayed_high_rate_among_negative"] == 0.6667
    assert result["delayed_close_rate_among_negative"] == 0.3333
    assert result["delayed_close_retention_rate"] == 0.5
    assert result["delayed_next_day_high_count"] == 1


def test_universe_control_is_deterministic_and_compares_rank1() -> None:
    candidates = universe_candidates(
        {
            "D1": {
                "decision_epoch": _epoch("2026-07-01", 9, 0),
                "scanner_pre_strategist_universe": {
                    "intrinsic_ranked_top20": [
                        {"rank": 1, "symbol": "A"},
                        {"rank": 2, "symbol": "B"},
                    ]
                },
            }
        },
        {"D1"},
    )
    rows = {
        "A": [
            _row("2026-07-01", 9, 1, 100.0),
            _row("2026-07-01", 9, 31, 105.0),
            *[
                _row(day, 15, 20, 110.0)
                for day in (
                    "2026-07-02",
                    "2026-07-03",
                    "2026-07-06",
                    "2026-07-07",
                    "2026-07-08",
                )
            ],
        ],
        "B": [
            _row("2026-07-01", 9, 1, 100.0),
            _row("2026-07-01", 9, 31, 99.0),
            *[
                _row(day, 15, 20, 90.0)
                for day in (
                    "2026-07-02",
                    "2026-07-03",
                    "2026-07-06",
                    "2026-07-07",
                    "2026-07-08",
                )
            ],
        ],
    }
    paths = build_universe_paths(
        candidates,
        decision_days={"D1": "2026-07-01"},
        rows_by_symbol=rows,
        trading_calendar=[
            "2026-07-01",
            "2026-07-02",
            "2026-07-03",
            "2026-07-06",
            "2026-07-07",
            "2026-07-08",
        ],
    )
    result = analyze_universe_paths(paths)

    assert [row["rank"] for row in paths] == [1, 2]
    paired = result["paired_top1_minus_alternative_mean"]
    assert paired["net_return_30m_pct"]["average_pct"] == 6.0
    assert paired["d5_close_net_pct"]["average_pct"] == 20.0
