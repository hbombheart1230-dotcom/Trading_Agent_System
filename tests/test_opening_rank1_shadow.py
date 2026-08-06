from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from libs.reporting.opening_rank1_shadow.episodes import (
    build_opening_rank1_episodes,
)
from libs.reporting.opening_rank1_shadow.candle_provider import (
    load_opening_candles,
)
from libs.reporting.opening_rank1_shadow.extraction import (
    extract_opening_rank1_windows,
)
from libs.reporting.opening_rank1_shadow.metrics import evaluate_promotion
from libs.reporting.opening_rank1_shadow.latent_watch import (
    build_latent_reactivation_watch,
)
from libs.reporting.opening_rank1_shadow.five_session_review import (
    evaluate_five_session_review,
)
from libs.reporting.opening_rank1_shadow.pipeline import (
    build_opening_rank1_shadow,
)


KST = timezone(timedelta(hours=9))


def _epoch(day: str, hour: int, minute: int, second: int = 0) -> int:
    return int(
        datetime.fromisoformat(day)
        .replace(
            hour=hour,
            minute=minute,
            second=second,
            tzinfo=KST,
        )
        .timestamp()
    )


def _window(day: str, hour: int, minute: int, symbol: str) -> dict:
    return {
        "window_type": "scanner_selection",
        "decision_id": f"D_{hour}_{minute}_{symbol}",
        "decision_epoch": _epoch(day, hour, minute, 30),
        "scanner_pre_strategist_universe": {
            "intrinsic_ranked_top20": [
                {"rank": 2, "symbol": "000660", "score_total": 0.9},
                {
                    "rank": 1,
                    "symbol": symbol,
                    "score_total": 1.2,
                    "sources": ["top_value", "top_volume"],
                },
            ]
        },
    }


def _write_q9(reports_root: Path, day: str, windows: list[dict]) -> None:
    path = (
        reports_root
        / "operator_summary"
        / "daily"
        / day
        / "q9_decision_windows.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"windows": windows}),
        encoding="utf-8",
    )


def _candles(day: str, symbol: str, *, end_hour: int = 15, end_minute: int = 20) -> list[dict]:
    rows = []
    current = datetime.fromisoformat(day).replace(hour=9, tzinfo=KST)
    end = datetime.fromisoformat(day).replace(
        hour=end_hour,
        minute=end_minute,
        tzinfo=KST,
    )
    index = 0
    while current <= end:
        price = 100.0 + index * 0.02
        rows.append(
            {
                "ts": int(current.timestamp()),
                "raw_ts": current.strftime("%Y%m%d%H%M%S"),
                "open": price,
                "high": price + 0.1,
                "low": price - 0.1,
                "close": price,
                "volume": 1000 + index,
            }
        )
        current += timedelta(minutes=1)
        index += 1
    return rows


def test_extraction_keeps_only_opening_rank1(tmp_path: Path) -> None:
    day = "2026-08-03"
    reports_root = tmp_path / "reports"
    _write_q9(
        reports_root,
        day,
        [
            _window(day, 9, 0, "005930"),
            _window(day, 9, 19, "000660"),
            _window(day, 9, 20, "035420"),
        ],
    )

    result = extract_opening_rank1_windows(
        reports_root=reports_root,
        day=day,
    )

    assert result["opening_window_count"] == 2
    assert result["symbols"] == ["000660", "005930"]
    assert [
        row["candidates"][0]["symbol"]
        for row in result["windows"]
    ] == ["005930", "000660"]


def test_episode_spacing_and_next_minute_entry_are_deterministic() -> None:
    day = "2026-08-03"
    windows = [
        {
            "day": day,
            "decision_id": "D1",
            "decision_epoch": _epoch(day, 9, 0, 30),
            "candidates": [{"rank": 1, "symbol": "005930"}],
        },
        {
            "day": day,
            "decision_id": "D2",
            "decision_epoch": _epoch(day, 9, 5, 30),
            "candidates": [{"rank": 1, "symbol": "005930"}],
        },
        {
            "day": day,
            "decision_id": "D3",
            "decision_epoch": _epoch(day, 9, 16, 30),
            "candidates": [{"rank": 1, "symbol": "005930"}],
        },
    ]
    candles = {"005930": _candles(day, "005930")}

    episodes = build_opening_rank1_episodes(
        windows,
        minute_rows_by_symbol=candles,
    )

    assert len(episodes) == 2
    assert episodes[0]["baseline_epoch"] == _epoch(day, 9, 1)
    assert episodes[1]["baseline_epoch"] == _epoch(day, 9, 17)
    first_observation = episodes[0]["opening_observability"]
    assert first_observation["exact_opening_09_00_04"] is True
    assert first_observation["completed_bar_count_at_decision"] == 0
    assert first_observation["completed_volume_status"] == "UNAVAILABLE_FIRST_MINUTE"
    assert first_observation["reference_entry_delay_sec"] == 30
    assert first_observation["candidate_snapshot"]["score_total"] is None


def test_recurrent_rank_lane_uses_only_prior_windows_and_completed_bar() -> None:
    day = "2026-08-03"
    windows = [
        {
            "day": day,
            "decision_id": "D1",
            "decision_epoch": _epoch(day, 9, 0, 30),
            "candidates": [{"rank": 1, "symbol": "005930"}],
        },
        {
            "day": day,
            "decision_id": "D2",
            "decision_epoch": _epoch(day, 9, 14, 30),
            "candidates": [{"rank": 1, "symbol": "005930"}],
        },
        {
            "day": day,
            "decision_id": "D3",
            "decision_epoch": _epoch(day, 9, 16, 30),
            "candidates": [{"rank": 1, "symbol": "005930"}],
        },
    ]

    episodes = build_opening_rank1_episodes(
        windows,
        minute_rows_by_symbol={"005930": _candles(day, "005930")},
    )

    assert len(episodes) == 2
    lane = episodes[1]["opening_observability"]["conditional_lanes"][
        "CONFIRMED_RECURRENT_RANK"
    ]
    assert lane["eligible"] is True
    assert lane["evidence"]["prior_rank1_observations_5m"] == 1
    assert lane["evidence"]["completed_return_1m_pct"] > 0.0


def test_latent_watch_records_fresh_reappearance_without_behavior_effect(
    tmp_path: Path,
) -> None:
    reports_root = tmp_path / "reports"
    output_root = reports_root / "evaluation" / "opening_rank1_shadow"
    initial_day = "2026-08-03"
    next_day = "2026-08-04"
    initial_path = output_root / initial_day / "opening_rank1_shadow_daily.json"
    initial_path.parent.mkdir(parents=True)
    initial_path.write_text(
        json.dumps(
            {
                "day_status": "VALID",
                "episodes": [
                    {
                        "episode_id": "E1",
                        "day": initial_day,
                        "symbol": "005930",
                        "checkpoints": {
                            "+30m": {
                                "status": "observed",
                                "live_net_return_pct": -0.5,
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    reappearance = _window(next_day, 9, 5, "005930")
    candidate = reappearance["scanner_pre_strategist_universe"][
        "intrinsic_ranked_top20"
    ][1]
    candidate["score_breakdown"] = {
        "volume_surge": 0.1,
        "vwap_alignment": 0.1,
        "momentum": 0.1,
        "intraday_strength": 0.1,
    }
    later_reappearance = _window(next_day, 9, 6, "005930")
    _write_q9(reports_root, next_day, [reappearance, later_reappearance])

    paths = build_latent_reactivation_watch(
        reports_root=reports_root,
        opening_output_root=output_root,
        through_day=next_day,
    )
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))

    assert payload["behavior_effect"] == "observation_only"
    assert payload["summary"]["watch_count"] == 1
    assert payload["rows"][0]["watch_status"] == "REDETECTED_WITH_SIGNAL_EVIDENCE"
    assert payload["rows"][0]["redetections"][0]["rank"] == 1
    assert len(payload["rows"][0]["redetections"]) == 1
    assert payload["rows"][0]["redetections"][0]["observation_count"] == 2


def test_historical_cache_prevents_past_artifact_shrink(tmp_path: Path) -> None:
    day = "2026-08-03"
    state_path = tmp_path / "state.json"
    cache_root = tmp_path / "minute_cache"
    state_path.write_text("{}", encoding="utf-8")
    cache_root.mkdir(parents=True)
    cache_root.joinpath("005930.json").write_text(
        json.dumps({"rows": _candles(day, "005930")}),
        encoding="utf-8",
    )

    candles, meta = load_opening_candles(
        state_path=state_path,
        day=day,
        symbols=("005930",),
        allow_fresh_fetch=False,
        cache_root=cache_root,
    )

    assert len(candles["005930"]) > 300
    assert meta["complete_symbol_count"] == 1
    assert meta["historical_fallback"]["005930"]["source"] == "cache"


def test_five_session_review_selects_only_recurrent_rank_candidate() -> None:
    summary = {
        "conditional_lane_summaries": {
            "IMMEDIATE_OPENING_PROBE": {
                "eligible_episode_count": 8,
                "horizons": {"+15m": {"live_net": {"count": 8, "average_return_pct": 1.0}}},
            },
            "CONFIRMED_RECURRENT_RANK": {
                "eligible_episode_count": 5,
                "horizons": {"+30m": {"live_net": {"count": 5, "average_return_pct": 0.4}}},
            },
            "DISLOCATION_REBOUND": {
                "eligible_episode_count": 2,
                "horizons": {"+60m": {"live_net": {"count": 2, "average_return_pct": 2.0}}},
            },
        }
    }
    result = evaluate_five_session_review(
        through_day="2026-08-07",
        cumulative_summary=summary,
        session_rows=[
            {"day": f"2026-08-0{day}", "status": "VALID"}
            for day in range(3, 8)
        ],
        latent_summary={"watch_count": 6, "signal_evidence_count": 4},
    )

    assert result["status"] == "SELECT_BEHAVIOR_CANDIDATE"
    assert result["selected_behavior_candidate"] == "CONFIRMED_RECURRENT_RANK_PRESERVATION"
    assert result["lane_results"]["DISLOCATION_REBOUND"]["outcome"] == "RETAIN_LANE_SHADOW_ONLY"
    assert result["behavior_change_authorized"] is False


def test_eod_requires_close_window_observation() -> None:
    day = "2026-08-03"
    windows = [
        {
            "day": day,
            "decision_id": "D1",
            "decision_epoch": _epoch(day, 9, 0, 30),
            "candidates": [{"rank": 1, "symbol": "005930"}],
        }
    ]
    episodes = build_opening_rank1_episodes(
        windows,
        minute_rows_by_symbol={
            "005930": _candles(
                day,
                "005930",
                end_hour=9,
                end_minute=40,
            )
        },
    )

    assert episodes[0]["checkpoints"]["+30m"]["status"] == "observed"
    assert episodes[0]["checkpoints"]["EOD"] == {
        "status": "missing",
        "reason": "eod_close_window_not_reached",
        "latest_observed_epoch": _epoch(day, 9, 40),
    }


def test_pipeline_excludes_implementation_day_and_writes_artifacts(
    tmp_path: Path,
) -> None:
    day = "2026-07-31"
    reports_root = tmp_path / "reports"
    state_path = tmp_path / "state.json"
    _write_q9(reports_root, day, [_window(day, 9, 1, "005930")])
    state_path.write_text(
        json.dumps(
            {
                "recent_minute_ohlcv_by_symbol": {
                    "005930": _candles(day, "005930"),
                }
            }
        ),
        encoding="utf-8",
    )

    result = build_opening_rank1_shadow(
        day=day,
        reports_root=reports_root,
        state_path=state_path,
        allow_fresh_fetch=False,
    )

    daily = json.loads(Path(result["daily_json_path"]).read_text(encoding="utf-8"))
    cumulative = json.loads(
        Path(result["cumulative_json_path"]).read_text(encoding="utf-8")
    )
    assert daily["day_status"] == "IMPLEMENTATION_DAY_EXCLUDED"
    assert daily["episodes"][0]["prospective_eligible"] is False
    assert daily["summary"]["observed_30m_count"] == 1
    assert cumulative["summary"]["episode_count"] == 0
    assert cumulative["promotion_decision"]["status"] == "COLLECTING"


def test_incomplete_forward_day_is_not_added_to_cumulative(
    tmp_path: Path,
) -> None:
    day = "2026-08-03"
    reports_root = tmp_path / "reports"
    state_path = tmp_path / "state.json"
    _write_q9(reports_root, day, [_window(day, 9, 1, "005930")])
    state_path.write_text(
        json.dumps(
            {
                "recent_minute_ohlcv_by_symbol": {
                    "005930": _candles(
                        day,
                        "005930",
                        end_hour=9,
                        end_minute=20,
                    ),
                }
            }
        ),
        encoding="utf-8",
    )

    result = build_opening_rank1_shadow(
        day=day,
        reports_root=reports_root,
        state_path=state_path,
        allow_fresh_fetch=False,
    )
    cumulative = json.loads(
        Path(result["cumulative_json_path"]).read_text(encoding="utf-8")
    )

    assert result["day_status"] == "FORWARD_INCOMPLETE"
    assert cumulative["summary"]["episode_count"] == 0


def test_promotion_gate_is_fixed_and_requires_day_consistency() -> None:
    summary = {
        "observed_30m_count": 30,
        "observed_day_count": 10,
        "positive_day_ratio": 0.6,
        "largest_day_share": 0.2,
        "largest_symbol_share": 0.2,
        "horizons": {
            "+30m": {
                "coverage": 0.95,
                "live_net": {
                    "win_rate": 0.6,
                    "average_return_pct": 0.4,
                    "profit_factor": 1.5,
                },
            }
        },
    }

    passed = evaluate_promotion(summary)
    failed = evaluate_promotion({**summary, "positive_day_ratio": 0.4})

    assert passed["status"] == "ELIGIBLE_FOR_CONTROLLED_SHADOW"
    assert passed["behavior_change_authorized"] is False
    assert failed["status"] == "REJECTED"
    assert failed["checks"]["positive_day_ratio"] is False


def test_opening_rank1_shadow_has_no_execution_dependency() -> None:
    package = Path("libs/reporting/opening_rank1_shadow")
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in package.glob("*.py")
    )
    for prohibited in (
        "OrderIntent",
        "submit_order",
        "libs.execution",
        "graphs.nodes",
    ):
        assert prohibited not in source
