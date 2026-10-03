from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from libs.reporting.opening_rank1_shadow.market_snapshot import (
    load_market_snapshot_timeline,
    select_market_snapshot,
)
from libs.research.rank1_feature_mart.builder import build_episode
from libs.research.rank1_feature_mart.integrity import audit


def _epoch(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp())


def _write_snapshot(path: Path, *, generated_at: str, kospi: float, kosdaq: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "index_moves": {
                    "kospi_pct": kospi,
                    "kosdaq_pct": kosdaq,
                    "kospi200_pct": kospi + 0.1,
                    "krx_night_futures_pct": -0.2,
                },
            }
        ),
        encoding="utf-8",
    )


def test_market_snapshot_uses_latest_observation_at_or_before_decision(tmp_path: Path) -> None:
    day = "2026-08-21"
    root = tmp_path / "macro"
    _write_snapshot(
        root / day / "090100_macro_indicators.json",
        generated_at="2026-08-21T00:01:00+00:00",
        kospi=0.5,
        kosdaq=-0.2,
    )
    _write_snapshot(
        root / day / "090300_macro_indicators.json",
        generated_at="2026-08-21T00:03:00+00:00",
        kospi=9.9,
        kosdaq=9.9,
    )
    decision_epoch = _epoch("2026-08-21T09:02:00+09:00")

    result = select_market_snapshot(
        load_market_snapshot_timeline(day=day, macro_root=root),
        decision_epoch=decision_epoch,
    )

    assert result["evidence_status"] == "OBSERVED_POINT_IN_TIME"
    assert result["selection_policy"] == "LATEST_AT_OR_BEFORE_DECISION"
    assert result["kospi_pct"] == 0.5
    assert result["kosdaq_pct"] == -0.2
    assert result["snapshot_age_sec"] == 60
    assert result["freshness_status"] == "FRESH"
    assert result["timeline_snapshot_count"] == 2
    assert result["eligible_snapshot_count"] == 1
    assert result["next_snapshot_delay_sec"] == 60
    assert result["next_snapshot_usage"] == "POST_DECISION_OBSERVABILITY_ONLY"
    assert result["snapshot_epoch"] <= decision_epoch
    assert result["source_path"].endswith("090100_macro_indicators.json")


def test_market_snapshot_does_not_use_future_observation() -> None:
    decision_epoch = _epoch("2026-08-21T09:02:00+09:00")
    result = select_market_snapshot(
        [{"snapshot_epoch": decision_epoch + 1, "source_path": "future.json", "payload": {}}],
        decision_epoch=decision_epoch,
    )
    assert result["evidence_status"] == "MISSING_NO_SNAPSHOT_AT_OR_BEFORE_DECISION"
    assert result["snapshot_epoch"] is None
    assert result["next_snapshot_delay_sec"] == 1
    assert result["freshness_status"] == "MISSING"


def test_feature_mart_persists_point_in_time_market_provenance() -> None:
    decision_epoch = _epoch("2026-08-21T09:02:00+09:00")
    snapshot = {
        "evidence_status": "OBSERVED_POINT_IN_TIME",
        "selection_policy": "LATEST_AT_OR_BEFORE_DECISION",
        "snapshot_epoch": decision_epoch - 30,
        "snapshot_time_kst": "2026-08-21T09:01:30+09:00",
        "snapshot_age_sec": 30,
        "source_path": "macro/090130_macro_indicators.json",
        "kospi_pct": 1.1,
        "kosdaq_pct": -0.4,
        "kospi200_pct": 1.3,
        "krx_night_futures_pct": -0.2,
    }
    row = {
        "day": "2026-08-21",
        "symbol": "005930",
        "decision_epoch": decision_epoch,
        "baseline_epoch": decision_epoch,
        "baseline_price": 100.0,
        "market_snapshot": snapshot,
        "opening_observability": {"market_return_pct": 99.0},
    }
    result = build_episode(
        row=row,
        prospective=True,
        window={},
        minute_rows=[],
        daily_rows=[],
        longitudinal={},
    )

    assert result["market"]["market_return_pct"] == 1.1
    assert result["market"]["kosdaq_pct"] == -0.4
    assert result["market"]["snapshot_epoch"] == decision_epoch - 30
    assert result["market"]["snapshot_age_sec"] == 30
    assert result["market"]["snapshot_selection_policy"] == "LATEST_AT_OR_BEFORE_DECISION"
    assert result["market"]["snapshot_evidence_status"] == "OBSERVED_POINT_IN_TIME"


def test_integrity_rejects_future_market_snapshot() -> None:
    row = {
        "identity": {
            "episode_id": "future-market",
            "cohort_source": "PROSPECTIVE_OPENING_SHADOW",
            "decision_epoch": 100,
            "symbol": "005930",
            "day": "2026-08-21",
        },
        "market": {
            "snapshot_epoch": 101,
            "snapshot_evidence_status": "OBSERVED_POINT_IN_TIME",
        },
        "chart": {},
        "outcomes": {"checkpoints": {}},
    }
    result = audit([row])
    assert result["status"] == "FAIL"
    assert result["market_snapshot_time_violations"] == ["future-market"]
