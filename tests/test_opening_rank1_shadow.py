from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from libs.reporting.opening_rank1_shadow.episodes import (
    build_opening_rank1_episodes,
)
from libs.reporting.opening_rank1_shadow.extraction import (
    extract_opening_rank1_windows,
)
from libs.reporting.opening_rank1_shadow.metrics import evaluate_promotion
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
