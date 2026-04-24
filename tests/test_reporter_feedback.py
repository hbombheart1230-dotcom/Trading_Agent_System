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


def test_strategist_feedback_packet_can_use_trade_explain_payload_directly(tmp_path: Path) -> None:
    day = "2026-04-08"
    reports_root = tmp_path / "reports"
    trade_explain_payload = {
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
    }

    packet = build_strategist_feedback_packet(
        mode="trade_explain",
        payload=trade_explain_payload,
        reports_root=reports_root,
        day=day,
    )

    assert packet["route_analysis"]["route_selected_total"] == {"monitor_only": 5, "full_cycle": 3}
    assert packet["blocker_analysis"][0]["blocker"] == "below_vwap_reclaim_not_ready"
    assert any("Top blocker is below_vwap_reclaim_not_ready" in line for line in packet["recommendation"])


def test_strategist_feedback_packet_falls_back_to_same_day_reporter_analysis(tmp_path: Path) -> None:
    day = "2026-04-08"
    reports_root = tmp_path / "reports"
    _write_json(
        reports_root / "dev" / "analysis" / "reporter_analysis" / f"reporter_analysis_{day}.json",
        {
            "day": day,
            "generated_at": f"{day}T10:12:00+09:00",
            "report_focus_targets": ["exit_quality", "guard_blocks"],
            "monitor_evaluation": {
                "monitor_reason_top": {
                    "too_extended_from_vwap": 7,
                    "volume_insufficient": 3,
                }
            },
            "supervisor_activity": {
                "blocked_reason_top": {
                    "noop_intent_skipped": 9
                }
            },
            "intent_flow_analysis": {
                "reason_top": {
                    "noop_intent_skipped": 9,
                    "monitor:too_extended_from_vwap": 7,
                }
            },
            "operator_facing_summary": {
                "recommended_actions": [
                    "Tighten extended-entry tolerance before widening selection.",
                ]
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
    assert packet["source_reports"]["metrics"] is False
    assert packet["source_reports"]["reporter_analysis"] is True
    assert packet["blocker_analysis"][0]["blocker"] == "noop_intent_skipped"
    assert packet["data_freshness"]["generated_at"] == f"{day}T10:12:00+09:00"
    assert packet["recommendation"][0] == "Tighten extended-entry tolerance before widening selection."


def test_strategist_feedback_packet_generates_same_day_metrics_from_event_log_when_missing(tmp_path: Path) -> None:
    day = "2026-04-24"
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": f"{day}T00:01:00+00:00",
                        "run_id": "r1",
                        "stage": "strategist",
                        "event": "policy_resolution",
                        "payload": {"strategy_generation_mode": "fallback", "fallback_used": True},
                    }
                ),
                json.dumps(
                    {
                        "ts": f"{day}T00:01:01+00:00",
                        "run_id": "r1",
                        "stage": "commander_router",
                        "event": "route_selected",
                        "payload": {"route_selected": "monitor_only"},
                    }
                ),
                json.dumps(
                    {
                        "ts": f"{day}T00:01:02+00:00",
                        "run_id": "r1",
                        "stage": "monitor",
                        "event": "entry_decision_detail",
                        "payload": {
                            "no_trade_surface": {
                                "dominant_blocker": "below_vwap_reclaim_not_ready",
                            }
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    packet = build_strategist_feedback_packet(
        mode="daily_report",
        payload={"day": day},
        reports_root=reports_root,
        day=day,
    )

    assert packet["available"] is True
    assert packet["source_reports"]["metrics"] is True
    assert packet["source_reports"]["reporter_analysis"] is False
    assert packet["route_analysis"]["route_selected_total"] == {"monitor_only": 1}
    assert packet["blocker_analysis"][0]["blocker"] == "below_vwap_reclaim_not_ready"
    assert (reports_root / "metrics" / f"metrics_{day}.json").exists()


def test_strategist_feedback_packet_falls_back_to_same_day_trade_reports(tmp_path: Path) -> None:
    day = "2026-04-23"
    reports_root = tmp_path / "reports"
    trade_dir = reports_root / "trades" / day / "TRD_20260423_005930_01" / "reports"
    trade_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        trade_dir / "ai_trade_report.json",
        {
            "trade_id": "TRD_20260423_005930_01",
            "symbol": "005930",
            "truth_surface": {
                "status": {
                    "symbol": "005930",
                    "status": "closed",
                    "exit_reason": "SELL was triggered because peak_drawdown.",
                },
                "price": {
                    "broker_buy_price": 224500.0,
                    "broker_fill_price": 226000.0,
                },
                "pnl": {
                    "value": -522.0,
                    "pct": -0.0023,
                    "broker_fee": 1570,
                    "broker_tax": 452,
                },
                "availability": {
                    "broker_fill_present": True,
                    "broker_pnl_present": True,
                },
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
    assert packet["source_reports"]["metrics"] is False
    assert packet["source_reports"]["reporter_analysis"] is False
    assert packet["source_reports"]["trade_reports"] is True
    assert packet["confidence"] == "medium"
    assert packet["trade_report_analysis"]["closed_trade_count"] == 1
    assert packet["trade_report_analysis"]["broker_truth_count"] == 1
    assert "Same-day closed trade reports show 1 trades" in packet["insight_summary"]
    assert any("loss-heavy" in line for line in packet["recommendation"])


def test_strategist_feedback_packet_falls_back_to_misplaced_same_day_trade_reports(tmp_path: Path) -> None:
    day = "2026-04-23"
    reports_root = tmp_path / "reports"
    trade_dir = tmp_path / day / "TRD_20260423_047040_01" / "reports"
    trade_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        trade_dir / "ai_trade_report.json",
        {
            "trade_id": "TRD_20260423_047040_01",
            "symbol": "047040",
            "truth_surface": {
                "status": {
                    "symbol": "047040",
                    "status": "closed",
                    "exit_reason": "SELL was triggered because peak_drawdown.",
                },
                "price": {
                    "broker_buy_price": 3320.0,
                    "broker_fill_price": 3235.0,
                },
                "pnl": {
                    "value": -110.0,
                    "pct": -0.0033,
                    "broker_fee": 20,
                    "broker_tax": 5,
                },
                "availability": {
                    "broker_fill_present": True,
                    "broker_pnl_present": True,
                },
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
    assert packet["source_reports"]["trade_reports"] is True
    assert packet["trade_report_analysis"]["closed_trade_count"] == 1
    assert packet["trade_report_analysis"]["broker_truth_count"] == 1
