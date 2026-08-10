from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.same_symbol_sequences.builder import build_day_sequences
from libs.reporting.evaluation.same_symbol_sequences.pipeline import build_same_symbol_sequence_artifacts


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _trade(reports: Path, day: str, trade_id: str, entry: str, exit_time: str, value: float, decision: str) -> None:
    _write(reports / "evaluation" / "trades" / day / trade_id / "trade_read_model.json", {
        "trade_id": trade_id, "day": day, "symbol": "005930", "status": "closed",
        "entry": {"timestamp": entry, "price": 100, "quantity": 1},
        "exit": {"timestamp": exit_time, "price": 101, "quantity": 1, "broker_authoritative": True},
        "outcome": {"net_return_pct": value, "realized_pnl": value * 100},
        "selection": {"q9_decision_id": decision},
    })


def test_sequence_preserves_profit_giveback_and_unknown_episode(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-08-03"
    _trade(reports, day, "T1", "2026-08-03T00:00:00+00:00", "2026-08-03T00:10:00+00:00", 2.0, "D1")
    _trade(reports, day, "T2", "2026-08-03T00:20:00+00:00", "2026-08-03T00:30:00+00:00", -1.5, "D2")
    _write(reports / "operator_summary" / "daily" / day / "q9_decision_windows.json", {
        "windows": [{"decision_id": "D2", "scanner_pre_strategist_universe": {"intrinsic_ranked_top20": [{"symbol": "005930", "rank": 1, "score_breakdown": {"volume_surge": 1}}]}}]
    })
    row = build_day_sequences(reports_root=reports, day=day)[0]
    assert row["cumulative_return_pct"] == 0.5
    assert row["profit_giveback_pct"] == 1.5
    assert row["clean_profit_exit_reentry_count"] == 1
    assert row["trades"][1]["new_independent_episode"] == "UNKNOWN"
    assert row["trades"][1]["point_in_time_fresh_evidence"]["fresh_volume_confirmation"] is True


def test_cumulative_status_waits_for_ten_clean_profit_reentries(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    result = build_same_symbol_sequence_artifacts(reports_root=reports, day="2026-08-03")
    assert result["summary"]["status"] == "COLLECTING"
    assert Path(result["daily_json"]).exists()


def test_profit_reentry_after_prior_day_symbol_loss_is_not_policy_relevant(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-08-03"
    _trade(reports, day, "T1", "2026-08-03T00:00:00+00:00", "2026-08-03T00:05:00+00:00", -1.0, "D1")
    _trade(reports, day, "T2", "2026-08-03T00:10:00+00:00", "2026-08-03T00:15:00+00:00", 1.0, "D2")
    _trade(reports, day, "T3", "2026-08-03T00:20:00+00:00", "2026-08-03T00:25:00+00:00", -0.5, "D3")
    row = build_day_sequences(reports_root=reports, day=day)[0]
    assert row["clean_profit_exit_reentry_count"] == 0
    assert row["trades"][2]["current_loss_reentry_policy_would_have_blocked"] is True
