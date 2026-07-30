from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from libs.research.alpha_competition.candidates import (
    build_hypothesis_episodes,
    load_candidate_snapshots,
)
from libs.research.alpha_competition.evaluator import evaluate_hypothesis
from libs.research.alpha_competition.hypotheses import (
    confirmed_volume_breakout,
    confirmed_vwap_pullback,
    opening_risk_off_reclaim,
)


KST = timezone(timedelta(hours=9))


def _epoch(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=KST).timestamp())


def _candidate(
    *,
    day: str,
    epoch: int,
    symbol: str = "005930",
    factors: dict | None = None,
    rail: str = "",
) -> dict:
    return {
        "symbol": symbol,
        "_payload_day": day,
        "shadow_forward_base": {
            "baseline_epoch": epoch,
            "baseline_price": 100.0,
            "baseline_raw_ts": datetime.fromtimestamp(epoch, tz=KST).strftime(
                "%Y%m%d%H%M%S"
            ),
        },
        "quant_factor_snapshot": {"factors": dict(factors or {})},
        "entry_lane_observation": {"market_regime_rail": rail},
    }


def test_frozen_hypotheses_use_candidate_time_fields() -> None:
    opening = _candidate(
        day="2026-07-10",
        epoch=_epoch("2026-07-10T09:10:00"),
        factors={"vwap_reclaim_progress": 0.95, "volume_ratio": 0.8},
        rail="krx_night_futures_gap_down",
    )
    breakout = _candidate(
        day="2026-07-10",
        epoch=_epoch("2026-07-10T11:00:00"),
        factors={
            "breakout_ok": True,
            "volume_ratio": 1.2,
            "vwap_distance_pct": 0.0,
        },
    )
    pullback = _candidate(
        day="2026-07-10",
        epoch=_epoch("2026-07-10T11:00:00"),
        factors={"reclaim_ok": True, "pullback_ok": True, "volume_ratio": 0.8},
    )

    assert opening_risk_off_reclaim(opening) is True
    assert confirmed_volume_breakout(breakout) is True
    assert confirmed_vwap_pullback(pullback) is True


def test_hypothesis_boundaries_do_not_relax() -> None:
    opening = _candidate(
        day="2026-07-10",
        epoch=_epoch("2026-07-10T09:04:00"),
        factors={"vwap_reclaim_progress": 0.9499, "volume_ratio": 0.7999},
        rail="krx_night_futures_gap_down",
    )
    breakout = _candidate(
        day="2026-07-10",
        epoch=_epoch("2026-07-10T11:00:00"),
        factors={
            "breakout_ok": True,
            "volume_ratio": 1.1999,
            "vwap_distance_pct": -0.0001,
        },
    )

    assert opening_risk_off_reclaim(opening) is False
    assert confirmed_volume_breakout(breakout) is False


def test_episode_builder_is_deterministic_and_applies_gap() -> None:
    factors = {
        "breakout_ok": True,
        "volume_ratio": 1.5,
        "vwap_distance_pct": 0.1,
    }
    rows = [
        _candidate(
            day="2026-07-10",
            epoch=_epoch("2026-07-10T10:00:00"),
            factors=factors,
        ),
        _candidate(
            day="2026-07-10",
            epoch=_epoch("2026-07-10T10:01:00"),
            factors=factors,
        ),
        _candidate(
            day="2026-07-10",
            epoch=_epoch("2026-07-10T10:20:00"),
            factors=factors,
        ),
    ]

    first = build_hypothesis_episodes(rows)
    second = build_hypothesis_episodes(list(reversed(rows)))

    assert first == second
    assert len(first["H2_CONFIRMED_VOLUME_BREAKOUT"]) == 2


def test_loader_keeps_richer_duplicate_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "candidates"
    day_root = root / "2026-07-10"
    day_root.mkdir(parents=True)
    epoch = _epoch("2026-07-10T10:00:00")
    sparse = _candidate(day="2026-07-10", epoch=epoch, factors={})
    rich = _candidate(
        day="2026-07-10",
        epoch=epoch,
        factors={
            "breakout_ok": True,
            "volume_ratio": 1.5,
            "vwap_distance_pct": 0.1,
        },
    )
    (day_root / "a.json").write_text(
        json.dumps({"candidates": [sparse]}),
        encoding="utf-8",
    )
    (day_root / "b.json").write_text(
        json.dumps({"candidates": [rich]}),
        encoding="utf-8",
    )

    result = load_candidate_snapshots(
        root=root,
        start="2026-07-10",
        end="2026-07-10",
    )

    factors = result["rows"][0]["quant_factor_snapshot"]["factors"]
    assert result["canonical_candidate_count"] == 1
    assert factors["volume_ratio"] == 1.5


def test_evaluator_applies_fixed_cost_and_rejects_small_sample() -> None:
    epoch = _epoch("2026-07-10T10:00:00")
    episodes = [
        {
            "episode_id": "e1",
            "day": "2026-07-10",
            "symbol": "005930",
            "baseline_epoch": epoch,
            "baseline_price": 100.0,
        }
    ]
    candles = {
        "005930": [
            {
                "ts": epoch + minute * 60,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 101.0 if minute >= 30 else 100.0,
                "volume": 100.0,
            }
            for minute in range(61)
        ]
    }

    result = evaluate_hypothesis(
        episodes,
        minute_rows_by_symbol=candles,
    )
    primary = result["splits"]["validation"]["+30m"]

    assert primary["metrics"]["expectancy_pct"] == 0.72
    assert result["decision"] == "REJECT"
    assert result["gate_results"]["validation_observed_count"] is False


def test_research_package_has_no_execution_dependency() -> None:
    package = Path("libs/research/alpha_competition")
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in package.glob("*.py")
    )

    assert "libs.runtime.execution" not in source
    assert "graphs.nodes" not in source
    assert "OrderIntent" not in source
