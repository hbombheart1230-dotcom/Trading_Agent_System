from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from libs.research.conditional_alpha_diagnosis.reactivation import (
    build_reactivation_lineage,
)


def _event() -> dict[str, object]:
    return {
        "episode_id": "E1",
        "day": "2026-07-01",
        "symbol": "A",
        "selection_horizon_label": "DELAYED_HIGH_ONLY",
        "first_plus_5pct_day": "2026-07-02",
        "first_plus_5pct_epoch": int(datetime(2026, 7, 2, 1, 0, tzinfo=timezone.utc).timestamp()),
    }


def _write_window(root: Path, *, commander_decision: str = "reject") -> None:
    day = root / "2026-07-02"
    day.mkdir(parents=True)
    payload = {
        "day": "2026-07-02",
        "windows": [
            {
                "generated_at": "2026-07-02T00:30:00+00:00",
                "decision_id": "D1",
                "scanner_pre_strategist_universe": {"intrinsic_ranked_top20": [{"symbol": "A", "rank": 1}]},
                "scanner_control": {"top10": [{"symbol": "A", "rank": 1, "score_total": 1.2}]},
                "strategist_selection": {"post_strategist_top10": [{"symbol": "A"}], "selected_symbol": "A"},
                "commander_final": {"decision": commander_decision, "reason": "risk_too_high", "monitor_intent": "NOOP"},
            }
        ],
    }
    (day / "q9_decision_windows.json").write_text(json.dumps(payload), encoding="utf-8")


def test_reactivation_classifies_commander_rejection(tmp_path: Path) -> None:
    _write_window(tmp_path)
    row = build_reactivation_lineage([_event()], operator_daily_root=tmp_path)[0]
    assert row["classification"] == "COMMANDER_REJECTED"
    assert row["pre_threshold_occurrence_count"] == 1


def test_reactivation_distinguishes_scanner_miss(tmp_path: Path) -> None:
    day = tmp_path / "2026-07-02"
    day.mkdir()
    (day / "q9_decision_windows.json").write_text(
        json.dumps({"day": "2026-07-02", "windows": [{"generated_at": "2026-07-02T00:30:00+00:00"}]}),
        encoding="utf-8",
    )
    row = build_reactivation_lineage([_event()], operator_daily_root=tmp_path)[0]
    assert row["classification"] == "CANDIDATE_NOT_REDETECTED"
    assert row["source_universe_symbol_list_available"] is False
