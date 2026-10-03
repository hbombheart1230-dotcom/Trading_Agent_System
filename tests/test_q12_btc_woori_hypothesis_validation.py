from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from libs.reporting.baseline_btc_woori_tech.hypothesis_features import (
    build_hypothesis_features,
)
from libs.reporting.baseline_btc_woori_tech.hypothesis_forward import (
    entry_forward_outcomes,
)
from libs.reporting.baseline_btc_woori_tech.hypothesis_pipeline import (
    build_cumulative_hypothesis,
    build_hypothesis_validation_artifacts,
)
from libs.reporting.baseline_btc_woori_tech.strategy import build_decision_snapshot


KST = timezone(timedelta(hours=9))


def _epoch(day: str, hour: int, minute: int) -> int:
    return int(
        datetime.strptime(day, "%Y-%m-%d")
        .replace(hour=hour, minute=minute, tzinfo=KST)
        .timestamp()
    )


def _candles(day: str) -> list[dict]:
    start = _epoch(day, 9, 0)
    rows = []
    for index in range(71):
        price = 1000.0 + index
        rows.append(
            {
                "ts": start + index * 60,
                "raw_ts": datetime.fromtimestamp(start + index * 60, tz=KST).strftime("%Y%m%d%H%M%S"),
                "open": price,
                "high": price + 2.0,
                "low": price - 1.0,
                "close": price + 1.0,
                "volume": 100.0 + index * 10.0,
            }
        )
    return rows


def _signals(day: str, btc_return: float = 5.0) -> dict:
    target = _epoch(day, 8, 55)
    minute_rows = [
        {
            "ts": target - (5 - index) * 60,
            "raw_ts": "fixture",
            "price": 100.0 + index,
            "momentum_5m_pct": 0.5,
            "momentum_15m_pct": 1.0,
            "momentum_60m_pct": 2.0,
            "momentum_24h_pct": btc_return,
            "source": "fixture",
        }
        for index in range(6)
    ]
    btc_daily = []
    woori_daily = []
    for index in range(70):
        epoch = target - (80 - index) * 86400
        btc_daily.append(
            {
                "ts": epoch,
                "open": 70.0 + index * 0.2,
                "high": 71.0 + index * 0.2,
                "low": 69.0 + index * 0.2,
                "close": 70.5 + index * 0.2,
            }
        )
        woori_daily.append(
            {
                "ts": epoch,
                "open": 900.0,
                "high": 1000.0,
                "low": 850.0,
                "close": 990.0,
            }
        )
    return {
        "available": True,
        "available_sources": ["btc_usd"],
        "sources": {"btc_usd": minute_rows},
        "research_context": {
            "behavior_effect": "observation_only",
            "btc_usd_daily": btc_daily,
            "woori_daily": woori_daily,
        },
    }


def test_five_variable_features_are_point_in_time_and_deterministic() -> None:
    kwargs = {
        "day": "2026-08-28",
        "candles": _candles("2026-08-28"),
        "btc_signals": _signals("2026-08-28"),
    }
    first = build_hypothesis_features(**kwargs)
    second = build_hypothesis_features(**kwargs)

    assert first == second
    assert first["btc_0855"]["return_24h_pct"] == 5.0
    assert first["btc_0855"]["thresholds"]["gte_5pct"] is True
    assert first["btc_daily_context"]["surge_state"] == "FIRST_SURGE"
    assert first["woori_opening"]["opening_gap_band"] == "0_TO_3"
    assert first["entry_methods"]["09:03"]["confirmation_cutoff_epoch"] == _epoch("2026-08-28", 9, 2)


def test_missing_0855_is_not_approximated_from_0905() -> None:
    signals = _signals("2026-08-28")
    for row in signals["sources"]["btc_usd"]:
        row["ts"] = _epoch("2026-08-28", 9, 5)
    features = build_hypothesis_features(
        day="2026-08-28",
        candles=_candles("2026-08-28"),
        btc_signals=signals,
    )

    assert features["btc_0855"]["status"] == "MISSING"
    assert features["btc_0855"]["return_24h_pct"] is None


def test_forward_outcome_applies_cost_and_slippage() -> None:
    candles = _candles("2026-08-28")
    outcomes = entry_forward_outcomes(
        {
            "09:05": {
                "status": "OBSERVED",
                "entry_epoch": _epoch("2026-08-28", 9, 5),
                "entry_price": 1005.0,
            }
        },
        candles=candles,
        drag_pct=0.28,
    )
    row = outcomes["09:05"]["returns"]["+5m"]

    assert row["status"] == "OBSERVED"
    assert row["net_return_pct"] == round(row["gross_return_pct"] - 0.28, 6)
    assert row["mfe_pct"] > 0
    assert row["mae_pct"] <= 0


def test_daily_artifact_is_shadow_only_and_phase_separated(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    for day in ("2026-08-27", "2026-08-28"):
        build_hypothesis_validation_artifacts(
            day=day,
            reports_root=reports,
            candles=_candles(day),
            btc_signals=_signals(day),
            cost_pct=0.23,
            slippage_pct=0.05,
        )
    root = reports / "evaluation" / "baseline_btc_woori_tech"
    cumulative = build_cumulative_hypothesis(root=root, through_day="2026-08-28")
    daily = json.loads(
        (root / "2026-08-28" / "q12_btc_woori_hypothesis_validation.json").read_text(encoding="utf-8")
    )

    assert cumulative["phase_day_counts"] == {"BACKCHECK": 1, "PROSPECTIVE": 1}
    assert {row["evidence_phase"] for row in cumulative["rows"]} == {"BACKCHECK", "PROSPECTIVE"}
    assert daily["behavior_effect"] == "observation_only"
    assert daily["order_execution_allowed"] is False
    assert daily["order_intent"] is None


def test_research_context_does_not_change_existing_q12_decision() -> None:
    day = "2026-08-28"
    signals = _signals(day)
    without_research = {key: value for key, value in signals.items() if key != "research_context"}
    kwargs = {
        "day": day,
        "as_of_epoch": _epoch(day, 9, 10),
        "woori_candles": _candles(day),
    }
    before = build_decision_snapshot(**kwargs, btc_signals=without_research)
    after = build_decision_snapshot(**kwargs, btc_signals=signals)

    assert before["entry_conditions"] == after["entry_conditions"]
    assert before["eligible"] == after["eligible"]
    assert before["action"] == after["action"]
