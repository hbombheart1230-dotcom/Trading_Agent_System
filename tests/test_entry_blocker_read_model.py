from __future__ import annotations

import json
from pathlib import Path

from libs.contracts.agent_outputs import build_monitor_output_artifact
from libs.reporting.entry_blocker_read_model import (
    build_entry_blocker_day_summary,
    build_symbol_entry_blocker_sequence,
    classify_entry_time_bucket,
    explain_blocker_family,
    explain_raw_blocker,
    load_entry_blocker_rows,
    render_entry_blocker_summary_markdown,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _make_run(root: Path, run_id: str, *, monitor: dict, scanner: dict) -> None:
    run_dir = root / run_id
    _write_json(run_dir / "monitor.json", monitor)
    _write_json(run_dir / "scanner.json", scanner)


def test_monitor_artifact_includes_entry_blocker_surface() -> None:
    state = {
        "run_id": "run-entry-surface",
        "started_at": "2026-04-10T00:05:00+00:00",
        "runtime_phase": "session",
        "monitor": {
            "open_position_count": 0,
            "buy_blocked_open_position": False,
            "buy_blocked_post_exit_cooldown": True,
            "post_exit_cooldown_remaining_sec": 120,
        },
        "monitor_output": {
            "selected_symbol": "000660",
            "intent_side": "NOOP",
            "entry_exit_reason": "pullback_not_mature",
        },
        "monitor_entry": {
            "evaluated": True,
            "triggered": False,
            "reason": "pullback_not_mature",
            "primary_failure_axis": "pullback_structure",
            "metrics": {
                "rebound_ok": False,
                "pullback_ok": False,
                "pullback_mature": False,
                "pullback_depth_pct": 0.0015,
                "volume_ok": False,
                "volume_ratio": 0.72,
                "confidence_score": 0.51,
                "confidence_threshold": 0.55,
                "rebound_progress": 0.33,
            },
            "policy_interpretation": {"entry_style": "pullback"},
            "chart_structure_features": {"structure": {"structure_hh_hl": "weakening"}},
            "passed_checks": [],
            "failed_checks": ["rebound_ok", "pullback_ok", "volume_ok", "structure_hh_hl=intact"],
        },
        "monitor_exit": {
            "symbol": "000660",
            "price": 1000000,
            "reason": "no_position",
            "thresholds": {},
            "watch_axes": [],
        },
        "monitor_action_decision": {
            "entry_blockers": ["pullback_not_mature", "rebound_ok"],
        },
    }

    artifact = build_monitor_output_artifact(state)
    surface = artifact.get("entry_blocker_surface") or {}

    assert surface["pullback_not_mature"] is True
    assert surface["cooldown_blocked"] is True
    assert surface["post_exit_cooldown_remaining_sec"] == 120
    assert surface["structure_hh_hl"] == "weakening"
    assert surface["primary_blockers"][:2] == ["pullback_not_mature", "rebound_ok"]


def test_entry_blocker_read_model_aggregates_rows_symbols_and_time_buckets(tmp_path: Path) -> None:
    canonical_root = tmp_path / "reports" / "canonical"
    day_root = canonical_root / "2026-04-10"

    _make_run(
        day_root,
        "run-1",
        monitor={
            "ts": "2026-04-10T00:05:00+00:00",
            "symbol": "000660",
            "decision": "NOOP",
            "no_trade_reason_code": "pullback_not_mature",
            "entry_blockers": ["pullback_not_mature", "rebound_ok"],
            "entry_blocker_surface": {
                "final_decision": "WAIT",
                "no_trade_code": "pullback_not_mature",
                "dominant_blocker": "pullback_not_mature",
                "primary_blockers": ["pullback_not_mature", "rebound_ok"],
                "entry_style": "pullback",
                "rebound_ok": False,
                "pullback_ok": False,
                "pullback_not_mature": True,
                "volume_ok": True,
                "volume_confirmation_missing": False,
                "structure_hh_hl": "intact",
                "open_position_blocked": False,
                "cooldown_blocked": False,
                "confidence_score": 0.52,
                "confidence_threshold": 0.55,
                "pullback_depth_pct": 0.0014,
                "volume_ratio": 1.05,
            },
            "scanner_rank": 1,
            "scanner_score_total": 0.91,
        },
        scanner={
            "selected_candidate": {
                "symbol": "000660",
                "why": "leader with reclaim setup",
                "asset_class_detected": "common_stock",
                "detection_source": "name_heuristic",
                "score_total": 0.91,
                "confidence": 0.82,
                "sources": ["strategist_manual"],
            },
            "candidate_pool_snapshot": {
                "total_candidates_before_filter": 5,
                "total_candidates_after_filter": 3,
                "unknown_asset_candidate_count": 0,
            },
        },
    )
    _make_run(
        day_root,
        "run-2",
        monitor={
            "ts": "2026-04-10T02:00:00+00:00",
            "symbol": "000660",
            "decision": "NOOP",
            "no_trade_reason_code": "volume_confirmation_missing",
            "entry_blockers": ["volume_confirmation_missing", "volume_ok"],
            "entry_blocker_surface": {
                "final_decision": "WAIT",
                "no_trade_code": "volume_confirmation_missing",
                "dominant_blocker": "volume_confirmation_missing",
                "primary_blockers": ["volume_confirmation_missing", "volume_ok"],
                "entry_style": "pullback",
                "rebound_ok": True,
                "pullback_ok": True,
                "pullback_not_mature": False,
                "volume_ok": False,
                "volume_confirmation_missing": True,
                "structure_hh_hl": "intact",
                "open_position_blocked": False,
                "cooldown_blocked": False,
                "confidence_score": 0.57,
                "confidence_threshold": 0.55,
                "pullback_depth_pct": 0.0021,
                "volume_ratio": 0.64,
            },
            "scanner_rank": 1,
            "scanner_score_total": 0.88,
        },
        scanner={
            "selected_candidate": {
                "symbol": "000660",
                "why": "quality pullback candidate",
                "asset_class_detected": "common_stock",
                "detection_source": "metadata",
                "score_total": 0.72,
                "confidence": 0.68,
                "sources": ["kiwoom_live"],
            },
            "candidate_pool_snapshot": {
                "total_candidates_before_filter": 4,
                "total_candidates_after_filter": 2,
                "unknown_asset_candidate_count": 0,
            },
        },
    )
    _make_run(
        day_root,
        "run-3",
        monitor={
            "ts": "2026-04-10T05:40:00+00:00",
            "symbol": "005930",
            "decision": "BUY",
            "entry_blockers": [],
            "entry_blocker_surface": {
                "final_decision": "BUY",
                "no_trade_code": "",
                "dominant_blocker": "",
                "primary_blockers": [],
                "entry_style": "breakout",
                "rebound_ok": True,
                "pullback_ok": True,
                "pullback_not_mature": False,
                "volume_ok": True,
                "volume_confirmation_missing": False,
                "structure_hh_hl": "intact",
                "open_position_blocked": False,
                "cooldown_blocked": False,
                "confidence_score": 0.63,
                "confidence_threshold": 0.55,
                "pullback_depth_pct": 0.0011,
                "volume_ratio": 1.45,
            },
            "scanner_rank": 1,
            "scanner_score_total": 0.94,
        },
        scanner={
            "selected_candidate": {
                "symbol": "005930",
                "why": "breakout continuation",
                "asset_class_detected": "common_stock",
                "detection_source": "name_heuristic",
                "score_total": 0.94,
                "confidence": 0.84,
                "sources": ["strategist_manual", "kiwoom_live"],
            },
            "candidate_pool_snapshot": {
                "total_candidates_before_filter": 6,
                "total_candidates_after_filter": 4,
                "unknown_asset_candidate_count": 1,
            },
        },
    )

    rows = load_entry_blocker_rows(canonical_root, day="2026-04-10")
    assert len(rows) == 3
    assert rows[0]["time_bucket"] == "open_window"
    assert rows[1]["time_bucket"] == "mid_session"
    assert rows[2]["time_bucket"] == "late_session"
    assert rows[0]["scanner_selected_summary"]["why"] == "leader with reclaim setup"
    assert rows[1]["volume_confirmation_missing"] is True
    assert "pullback_timing" in rows[0]["blocker_families"]
    assert "volume_confirmation" in rows[1]["blocker_families"]
    assert rows[1]["scanner_quality_suspected"] is True
    assert rows[1]["scanner_quality_reason"] == "volume_confirmation_missing_low_score"
    assert rows[1]["raw_blocker_explanations"]["volume_confirmation_missing"] == "거래량 확인 부족"
    assert rows[0]["blocker_family_explanations"]["pullback_timing"].startswith("눌림")

    filtered = load_entry_blocker_rows(canonical_root, day="2026-04-10", symbol="000660")
    assert len(filtered) == 2
    assert {row["symbol"] for row in filtered} == {"000660"}
    family_filtered = load_entry_blocker_rows(canonical_root, day="2026-04-10", family="pullback_timing")
    assert len(family_filtered) == 1
    assert family_filtered[0]["run_id"] == "run-1"

    summary = build_entry_blocker_day_summary(canonical_root, day="2026-04-10")
    assert summary["decision_frequency"]["WAIT"] == 2
    assert summary["decision_frequency"]["BUY"] == 1
    assert summary["blocker_family_frequency"]["pullback_timing"] == 1
    assert summary["blocker_family_frequency"]["volume_confirmation"] == 1
    assert summary["blocker_family_raw_breakdown"]["pullback_timing"]["pullback_not_mature"] == 1
    assert summary["blocker_family_raw_breakdown"]["rebound_confirmation"]["rebound_ok"] == 1
    assert summary["blocker_frequency"]["pullback_not_mature"] == 1
    assert summary["blocker_frequency"]["volume_confirmation_missing"] == 1
    assert summary["no_trade_code_frequency"]["pullback_not_mature"] == 1
    assert summary["no_trade_code_frequency"]["volume_confirmation_missing"] == 1
    assert summary["scanner_quality_suspected_count"] == 1
    assert summary["scanner_quality_reason_frequency"]["volume_confirmation_missing_low_score"] == 1
    assert summary["by_time_bucket"]["open_window"]["blocker_family_frequency"]["pullback_timing"] == 1
    assert summary["by_time_bucket"]["mid_session"]["blocker_family_frequency"]["volume_confirmation"] == 1
    assert summary["by_time_bucket"]["mid_session"]["blocker_family_raw_breakdown"]["volume_confirmation"]["volume_confirmation_missing"] == 1
    assert summary["by_time_bucket"]["open_window"]["decision_frequency"]["WAIT"] == 1
    assert summary["by_time_bucket"]["mid_session"]["decision_frequency"]["WAIT"] == 1
    assert summary["by_time_bucket"]["late_session"]["decision_frequency"]["BUY"] == 1
    assert summary["by_symbol"]["000660"]["blocker_family_raw_breakdown"]["pullback_timing"]["pullback_not_mature"] == 1

    sequence = build_symbol_entry_blocker_sequence(rows, symbol="000660")
    assert len(sequence) == 2
    assert sequence[0]["no_trade_code"] == "pullback_not_mature"
    assert sequence[1]["no_trade_code"] == "volume_confirmation_missing"
    assert sequence[0]["blocker_families"] == ["pullback_timing", "rebound_confirmation"]
    assert sequence[0]["family_explanations"]["pullback_timing"].startswith("눌림")
    assert sequence[1]["raw_blocker_explanations"]["volume_confirmation_missing"] == "거래량 확인 부족"
    assert sequence[1]["scanner_quality_suspected"] is True

    focused_summary = build_entry_blocker_day_summary(canonical_root, day="2026-04-10", family="pullback_timing")
    assert focused_summary["row_count"] == 1
    assert focused_summary["family_filter"] == "pullback_timing"
    assert focused_summary["blocker_family_raw_breakdown"]["pullback_timing"]["pullback_not_mature"] == 1

    markdown = render_entry_blocker_summary_markdown(build_entry_blocker_day_summary(canonical_root, day="2026-04-10", symbol="000660"))
    assert "Family -> Raw Blocker Breakdown" in markdown
    assert "raw_blocker_explanations" in markdown
    assert "scanner_quality_suspected=true" in markdown
    focused_markdown = render_entry_blocker_summary_markdown(
        build_entry_blocker_day_summary(canonical_root, day="2026-04-10", family="pullback_timing")
    )
    assert "Focused Family Raw Blockers" in focused_markdown
    assert "Focused Family by Final Decision" in focused_markdown


def test_blocker_explanation_mapping_is_stable() -> None:
    assert explain_raw_blocker("pullback_not_mature") == "눌림이 아직 충분히 성숙하지 않음"
    assert explain_raw_blocker("entry_guard_cooldown:28s_remaining").startswith("엔트리 가드 쿨다운")
    assert explain_blocker_family("reclaim_readiness").startswith("VWAP")


def test_classify_entry_time_bucket_is_deterministic() -> None:
    assert classify_entry_time_bucket("2026-04-10T00:10:00+00:00") == "open_window"
    assert classify_entry_time_bucket("2026-04-10T03:00:00+00:00") == "mid_session"
    assert classify_entry_time_bucket("2026-04-10T06:00:00+00:00") == "late_session"
