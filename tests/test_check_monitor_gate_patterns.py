from __future__ import annotations

import json
from pathlib import Path

from scripts.check_monitor_gate_patterns import (
    _build_stale_groups,
    _followup_from_rows,
    analyze_monitor_gate_patterns,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_stale_groups_flags_repeated_old_minute_snapshot() -> None:
    rows = [
        {
            "run_id": "r1",
            "symbol": "003280",
            "evaluation_summary": "too_extended_from_vwap",
            "minute_source_present": True,
            "latest_candle_ts": 1774317180,
            "artifact_age_minutes": 9.0,
        },
        {
            "run_id": "r2",
            "symbol": "003280",
            "evaluation_summary": "too_extended_from_vwap",
            "minute_source_present": True,
            "latest_candle_ts": 1774317180,
            "artifact_age_minutes": 15.0,
        },
    ]
    groups = _build_stale_groups(rows, stale_age_min=3.0)
    assert len(groups) == 1
    assert groups[0]["symbol"] == "003280"
    assert groups[0]["repeat_count"] == 2
    assert groups[0]["max_artifact_age_minutes"] == 15.0


def test_followup_from_rows_detects_breakout_without_reclaim() -> None:
    case = {
        "latest_candle_ts": 100,
        "current_price": 100.0,
        "breakout_level": 101.0,
        "reclaim_price": 110.0,
    }
    rows = [
        {"ts": 101, "high": 101.5, "low": 99.8, "close": 101.0},
        {"ts": 102, "high": 103.0, "low": 100.5, "close": 102.5},
    ]
    out = _followup_from_rows(case, rows)
    assert out["later_bars"] == 2
    assert out["crossed_breakout_after"] is True
    assert out["crossed_reclaim_after"] is False
    assert round(float(out["move_to_max_pct"]), 3) == 3.0


def test_analyze_monitor_gate_patterns_collects_rows_and_repeated_states(tmp_path: Path) -> None:
    day_root = tmp_path / "reports" / "canonical" / "2026-03-24"
    monitor_payload = {
        "ts": "2026-03-24T02:04:03+00:00",
        "symbol": "003280",
        "evaluation_summary": "too_extended_from_vwap",
        "primary_reason_code": "too_extended_from_vwap",
        "decision_status": "blocked",
    }
    shadow_payload = {
        "monitor_gate_details": {
            "entry_block_reason": "too_extended_from_vwap",
            "used_thresholds": {"reclaim_tolerance_pct": 0.0015},
            "observed_features": {
                "minute_source_present": True,
                "minute_source_used": "state.minute_ohlcv_by_symbol",
                "latest_candle_ts": 1774317180,
                "inferred_spacing_minutes": 1.0,
                "series_class": "intraday",
                "current_price": 4150.0,
                "vwap_distance": 0.1614,
                "volume_ratio": 0.015,
                "pullback_pct": 0.0259,
                "breakout_level": 4240.0,
            },
            "failed_gates": ["breakout_ok", "volume_ok", "extension_ok"],
            "passed_gates": [],
        }
    }
    _write_json(day_root / "run-a" / "monitor.json", monitor_payload)
    _write_json(day_root / "run-a" / "commander_shadow.json", shadow_payload)
    monitor_payload_2 = dict(monitor_payload, ts="2026-03-24T02:19:55+00:00")
    _write_json(day_root / "run-b" / "monitor.json", monitor_payload_2)
    _write_json(day_root / "run-b" / "commander_shadow.json", shadow_payload)

    out = analyze_monitor_gate_patterns(tmp_path / "reports" / "canonical", day="2026-03-24", reason_filter="too_extended_from_vwap")
    assert out["row_count"] == 2
    assert out["reason_counts"]["too_extended_from_vwap"] == 2
    assert out["symbol_counts"]["003280"] == 2
    assert out["stale_groups"]
    assert out["stale_groups"][0]["symbol"] == "003280"
    assert out["repeated_states"][0]["repeat_count"] == 2
