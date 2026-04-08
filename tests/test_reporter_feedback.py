from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.reporter_feedback import build_strategist_feedback_packet


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_strategist_feedback_packet_builds_from_existing_report_layer(tmp_path: Path) -> None:
    day = "2026-04-08"
    reports_root = tmp_path / "reports"
    _write_json(
        reports_root / "metrics" / f"metrics_{day}.json",
        {
            "day": day,
            "generated_at": f"{day}T10:00:00+09:00",
            "source_run_count": 20,
            "latest_run_id": "r20",
            "latest_run_ts": f"{day}T09:59:00+09:00",
            "route_selected_total": {"monitor_only": 12, "cached_strategist": 5, "full_cycle": 3},
            "strategist_mode_total": {"fallback": 14, "cached": 5, "default_safe": 1},
            "strategist_fallback_total": 4,
            "route_source": "canonical_commander_preferred",
            "route_source_run_count": 20,
            "route_source_missing_count": 0,
            "route_source_breakdown": {"canonical_commander": 20},
            "dominant_blocker_total": {
                "pullback_ok": 9,
                "below_vwap_reclaim_not_ready": 6,
                "structure_hh_hl": 3,
            },
            "data_freshness": {
                "generated_at": f"{day}T10:00:00+09:00",
                "source_run_count": 20,
                "latest_run_id": "r20",
                "latest_run_ts": f"{day}T09:59:00+09:00",
                "freshness_status": "fresh",
                "stale": False,
                "stale_reason": "aligned_with_source_window",
                "source_window_summary": "runs=20",
            },
        },
    )

    packet = build_strategist_feedback_packet(
        mode="daily_report",
        payload={"day": day},
        reports_root=reports_root,
        day=day,
    )

    assert packet["available"] is True
    assert packet["feedback_mode"] == "deterministic"
    assert packet["route_analysis"]["route_selected_total"] == {"monitor_only": 12, "cached_strategist": 5, "full_cycle": 3}
    assert packet["route_analysis"]["monitor_only_ratio"] == 0.6
    assert packet["route_analysis"]["cached_strategist_ratio"] == 0.25
    assert packet["blocker_analysis"][0]["blocker"] == "pullback_ok"
    pattern_names = {item["name"] for item in packet["dominant_patterns"]}
    assert "monitor_only_ratio" in pattern_names
    assert "cached_strategist_ratio" in pattern_names
    assert "reclaim_blocked_ratio" in pattern_names
    assert packet["confidence"] == "medium"
    assert packet["data_freshness"]["freshness_status"] == "fresh"


def test_strategist_feedback_packet_can_fall_back_to_trade_explain_summary(tmp_path: Path) -> None:
    day = "2026-04-08"
    reports_root = tmp_path / "reports"
    _write_json(
        reports_root / "dev" / "analysis" / "trade_explain" / f"trade_explain_{day}.json",
        {
            "day": day,
            "generated_at": f"{day}T10:10:00+09:00",
            "source_run_count": 8,
            "latest_run_id": "r8",
            "latest_run_ts": f"{day}T10:09:00+09:00",
            "route_summary": {
                "route_source": "canonical_commander_preferred",
                "route_source_run_count": 8,
                "route_source_missing_count": 0,
                "route_source_breakdown": {"canonical_commander": 8},
                "route_selected_total": {"monitor_only": 5, "full_cycle": 3},
                "strategy_generation_mode_total": {"fallback": 5, "live_llm": 3},
                "strategist_fallback_total": 2,
            },
            "no_trade_summary": {
                "dominant_blocker_topN": [
                    {"reason": "below_vwap_reclaim_not_ready", "count": 4},
                    {"reason": "structure_hh_hl", "count": 2},
                ]
            },
            "data_freshness": {
                "generated_at": f"{day}T10:10:00+09:00",
                "source_run_count": 8,
                "latest_run_id": "r8",
                "latest_run_ts": f"{day}T10:09:00+09:00",
                "freshness_status": "fresh",
                "stale": False,
                "stale_reason": "aligned_with_source_window",
                "source_window_summary": "runs=8",
            },
        },
    )

    packet = build_strategist_feedback_packet(
        mode="operator_summary",
        payload={"day": day},
        reports_root=reports_root,
        day=day,
    )

    assert packet["route_analysis"]["route_selected_total"] == {"monitor_only": 5, "full_cycle": 3}
    assert packet["blocker_analysis"][0]["blocker"] == "below_vwap_reclaim_not_ready"
    assert any("Top blocker is below_vwap_reclaim_not_ready" in line for line in packet["recommendation"])
