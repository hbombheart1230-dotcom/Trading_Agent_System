from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from graphs.pipelines.m13_eod_report import run_m13_eod_report
import libs.reporting.operator_visibility as operator_visibility
from libs.runtime.market_hours import MarketHours
from scripts.run_decision_story_report import main as decision_story_main
from scripts.run_operator_daily_summary import main as operator_summary_main
from scripts.run_run_card_report import main as run_card_main

KST = timezone(timedelta(hours=9))


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_operator_daily_summary_script_generates_red_status(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-06"
    events = tmp_path / "events.jsonl"
    metrics_dir = tmp_path / "metrics"
    m30_post = tmp_path / "m30_post"
    m30_go = tmp_path / "m30_go"
    m31_dir = tmp_path / "m31"
    out_dir = tmp_path / "operator_summary"
    _write_json(
        tmp_path / "data" / "logs" / "controlled_mock_lanes" / day / "lane_evaluations.json",
        {
            "evaluations": [
                {
                    "lane_id": "Q10_INDEX",
                    "status": "INPUT_MISSING",
                    "reason": "q10_preopen_snapshot_missing",
                    "observation_count": 1,
                }
            ]
        },
    )

    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "005930", "qty": 1}}, "trace": {"strategy": "RuleStrategist"}},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:01+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "MAX_NOTIONAL exceeded"},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:02+00:00",
                "stage": "execute_from_packet",
                "event": "error",
                "payload": {"reason": "duplicate_execution"},
            },
            {
                "run_id": "r2",
                "ts": f"{day}T01:10:00+00:00",
                "stage": "commander_router",
                "event": "intervention",
                "payload": {"type": "operator_resume"},
            },
        ],
    )

    _write_json(
        metrics_dir / f"metrics_{day}.json",
        {
            "execution": {"intents_created": 6, "intents_blocked": 4},
            "broker_api": {"api_429_rate": 0.10},
            "strategist_llm": {"total": 5, "success_rate": 0.80},
            "commander_resilience": {"total": 1},
        },
    )
    _write_json(
        m30_post / f"m30_post_golive_policy_{day}.json",
        {"escalation_level": "normal", "policy": {"manual_approval_only": False}},
    )
    _write_json(
        m30_go / f"m30_final_golive_signoff_{day}.json",
        {"approved": True, "go_live_decision": "approve_go_live"},
    )
    _write_json(
        m31_dir / f"m31_slo_incident_{day}.json",
        {"ok": True, "failure_total": 0},
    )
    daily_dir = out_dir / "daily" / day
    daily_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        daily_dir / "daily_report.json",
        {
            "policy_surface_quality_executive_summary": {"headline": "stale-file-should-not-be-read"},
        },
    )
    _write_json(
        daily_dir / "q9_decision_windows.json",
        {
            "windows": [
                {"commander_final": {"decision": "reject", "reason": "risk_too_high"}},
                {"commander_final": {"decision": "noop", "reason": "no_candidate"}},
            ]
        },
    )

    monkeypatch.setattr(
        operator_visibility,
        "build_policy_surface_quality_snapshot",
        lambda *args, **kwargs: {
            "summary": {"schema_version": "policy_surface_quality_summary.v1", "run_count": 8},
            "executive_summary": {
                "schema_version": "policy_surface_quality_executive_summary.v1",
                "status": "good",
                "headline": "Policy surface healthy: schema 0.82, invalid spec 0.01",
            },
            "chart_structure_summary": {
                "schema_version": "chart_structure_decision_hint_summary.v1",
                "run_count": 8,
                "available_run_count": 3,
                "applied_count": 1,
                "applied_examples": [
                    {
                        "run_id": "r3",
                        "symbol": "005930",
                        "entry_style": "breakout",
                        "mode": "block",
                        "legacy_decision": "BUY",
                        "legacy_reason": "breakout_above_recent_high_with_vwap_structure_confirmation",
                        "final_decision": "WAIT",
                        "final_reason": "breakout_continuation_structure_guard_blocked",
                        "reason_transition": "breakout_above_recent_high_with_vwap_structure_confirmation -> breakout_continuation_structure_guard_blocked",
                        "blocking_features": ["failed_breakout=confirmed"],
                        "matched_features": [],
                    }
                ],
            },
            "chart_structure_executive_summary": {
                "schema_version": "chart_structure_decision_hint_executive_summary.v1",
                "status": "active",
                "run_count": 8,
                "available_run_count": 3,
                "applied_count": 1,
                "applied_rate": 0.3333,
                "top_blocking_features": ["failed_breakout"],
                "headline": "Chart structure guard active: applied 1 times (rate 0.33), top blockers: failed_breakout",
                "applied_examples": [
                    {
                        "run_id": "r3",
                        "reason_transition": "breakout_above_recent_high_with_vwap_structure_confirmation -> breakout_continuation_structure_guard_blocked",
                        "blocking_features": ["failed_breakout=confirmed"],
                        "entry_style": "breakout",
                    }
                ],
            },
            "source": {"run_count": 8, "source": "daily_monitor_artifacts"},
        },
    )

    rc = operator_summary_main(
        [
            "--event-log-path",
            str(events),
            "--metrics-report-dir",
            str(metrics_dir),
            "--m30-post-golive-dir",
            str(m30_post),
            "--m30-golive-dir",
            str(m30_go),
            "--m31-slo-incident-dir",
            str(m31_dir),
            "--report-dir",
            str(out_dir),
            "--day",
            day,
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert obj["executive_summary"]["system_status"] == "RED"
    assert obj["policy_surface_quality_executive_summary"]["status"] == "good"
    assert obj["chart_structure_decision_hint_executive_summary"]["status"] == "active"
    assert obj["chart_structure_decision_hint_executive_summary"]["applied_examples"][0]["run_id"] == "r3"
    assert any("Policy surface healthy: schema 0.82, invalid spec 0.01" in line for line in obj["executive_summary"]["summary_lines"])
    assert any("Chart structure guard active: applied 1 times" in line for line in obj["executive_summary"]["summary_lines"])
    assert any("LLM success_rate=80.00% (5 calls)" in line for line in obj["executive_summary"]["summary_lines"])
    assert Path(obj["report_json_path"]).exists()
    assert Path(obj["report_md_path"]).exists()
    assert Path(obj["report_json_path"]) == tmp_path / "operator_summary" / "daily" / day / "operator_summary.json"
    assert Path(obj["report_md_path"]) == tmp_path / "operator_summary" / "daily" / day / "operator_summary.md"
    assert obj["route_summary"]["route_source"] == "canonical_commander_preferred"
    assert obj["data_freshness"]["freshness_status"] == "fresh"
    assert obj["route_provenance"]["route_source"] == "canonical_commander_preferred"
    assert obj["narrative_axis_policy"]["entry_primary_for"] == ["BUY", "WAIT", "NOOP", "NO_TRADE"]
    assert obj["trading_activity_summary"]["execution_guard_blocked_total"] == 1
    assert obj["trading_activity_summary"]["commander_candidate_rejected_total"] == 1
    assert obj["candidate_decision_summary"]["candidate_noop_total"] == 1
    assert obj["controlled_validation"]["lanes"][1]["reason"] == "q10_preopen_snapshot_missing"
    md_body = Path(obj["report_md_path"]).read_text(encoding="utf-8")
    assert "Data Freshness" in md_body
    assert "Executive Summary" in md_body
    assert "Narrative Axis Policy" in md_body
    assert "Policy Surface Executive Summary" in md_body
    assert "Chart Structure Decision Hint Executive Summary" in md_body
    assert "Chart Structure Decision Hint Applied Examples" in md_body
    assert "breakout_above_recent_high_with_vwap_structure_confirmation -> breakout_continuation_structure_guard_blocked" in md_body
    assert "System Health Status" in md_body
    assert "Trading Activity Summary" in md_body
    assert "Safety Guard Interventions" in md_body
    assert "Commander Candidate Decisions" in md_body
    assert "Controlled Validation Lanes" in md_body
    assert "Q10 Index: `INPUT_MISSING`" in md_body
    assert "candidate rejection occurs before OrderIntent" in md_body
    assert "Top Issues" in md_body
    assert "Recommended Operator Actions" in md_body


def test_operator_daily_summary_treats_unmeasurable_slo_artifact_as_stale_diagnostic(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    day = "2026-05-13"
    events = tmp_path / "events.jsonl"
    metrics_dir = tmp_path / "metrics"
    m30_post = tmp_path / "m30_post"
    m30_go = tmp_path / "m30_go"
    m31_dir = tmp_path / "m31"
    out_dir = tmp_path / "operator_summary"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T00:00:00+00:00",
                "stage": "commander_router",
                "event": "end",
                "payload": {"status": "ok"},
            }
        ],
    )
    _write_json(metrics_dir / f"metrics_{day}.json", {"execution": {}, "broker_api": {}, "strategist_llm": {}})
    _write_json(m30_post / f"m30_post_golive_policy_{day}.json", {"escalation_level": "normal"})
    _write_json(m30_go / f"m30_final_golive_signoff_{day}.json", {"approved": True})
    _write_json(
        m31_dir / f"m31_slo_incident_{day}.json",
        {
            "ok": False,
            "failure_total": 2,
            "slo": {"event_total": 0, "run_total": 0, "availability_rate": 0.0},
        },
    )
    monkeypatch.setattr(
        operator_visibility,
        "build_policy_surface_quality_snapshot",
        lambda *args, **kwargs: {
            "summary": {},
            "executive_summary": {"status": "good", "headline": "Policy surface healthy"},
            "chart_structure_summary": {},
            "chart_structure_executive_summary": {"status": "inactive", "headline": "Chart inactive"},
            "source": {},
        },
    )

    rc = operator_summary_main(
        [
            "--event-log-path",
            str(events),
            "--metrics-report-dir",
            str(metrics_dir),
            "--m30-post-golive-dir",
            str(m30_post),
            "--m30-golive-dir",
            str(m30_go),
            "--m31-slo-incident-dir",
            str(m31_dir),
            "--report-dir",
            str(out_dir),
            "--day",
            day,
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert obj["executive_summary"]["system_status"] == "YELLOW"
    assert obj["top_issues"][0]["code"] == "slo_incident_artifact_unmeasurable"
    assert not any(issue["code"] == "slo_incident_gate_failed" for issue in obj["top_issues"])


def test_decision_story_report_script_outputs_story_per_run(tmp_path: Path, capsys) -> None:
    day = "2026-03-06"
    events = tmp_path / "events.jsonl"
    out_dir = tmp_path / "decision_story"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"ok": True, "intent_action": "BUY", "intent_reason": "momentum_positive"},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:01+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {
                    "decision_packet": {
                        "intent": {"action": "BUY", "symbol": "005930", "qty": 3, "reason": "momentum_positive"},
                        "why": {
                            "technical": {"regime": "trend_up", "rsi14": 61},
                            "news": {"symbol_sentiment_score": 0.4},
                            "policy": {"max_risk": 0.7},
                        },
                    },
                    "trace": {"strategy": "RegimeMomentumV1", "rationale": "trend breakout"},
                },
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:02+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "MAX_NOTIONAL exceeded"},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:03+00:00",
                "stage": "commander_router",
                "event": "intervention",
                "payload": {"type": "operator_resume"},
            },
        ],
    )

    rc = decision_story_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(out_dir),
            "--day",
            day,
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert obj["story_total"] == 1
    md_path = Path(obj["report_md_path"])
    assert md_path.exists()
    md_body = md_path.read_text(encoding="utf-8")
    assert "Run r1" in md_body
    assert "execution_status: **BLOCKED**" in md_body
    assert "guard_intervention: MAX_NOTIONAL exceeded" in md_body


def test_run_card_report_script_outputs_cards(tmp_path: Path, capsys) -> None:
    day = "2026-03-06"
    events = tmp_path / "events.jsonl"
    out_dir = tmp_path / "run_cards"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "005930", "qty": 1, "reason": "breakout"}}},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:01+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "BUY", "symbol": "005930", "qty": 1}, "payload": {"broker_code": "0"}},
            },
            {
                "run_id": "r2",
                "ts": f"{day}T01:05:00+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "000660", "qty": 2, "reason": "signal"}}},
            },
            {
                "run_id": "r2",
                "ts": f"{day}T01:05:01+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "allowlist_blocked"},
            },
        ],
    )

    rc = run_card_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(out_dir),
            "--day",
            day,
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert obj["card_total"] == 2
    md_body = Path(obj["report_md_path"]).read_text(encoding="utf-8")
    assert "Run: r1" in md_body
    assert "Status: EXECUTED_OK" in md_body
    assert "Run: r2" in md_body
    assert "Status: BLOCKED" in md_body


def test_run_card_report_trade_only_filters_unknown_utility_runs(tmp_path: Path, capsys) -> None:
    day = "2026-03-06"
    events = tmp_path / "events.jsonl"
    out_dir = tmp_path / "run_cards"
    _write_jsonl(
        events,
        [
            {
                "run_id": "utility-1",
                "ts": f"{day}T00:59:00+00:00",
                "stage": "commander_router",
                "event": "transition",
                "payload": {"transition": "cooldown"},
            },
            {
                "run_id": "trade-1",
                "ts": f"{day}T01:05:00+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "005930", "qty": 1, "reason": "signal"}}},
            },
            {
                "run_id": "trade-1",
                "ts": f"{day}T01:05:01+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "allowlist_blocked"},
            },
        ],
    )

    rc = run_card_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(out_dir),
            "--day",
            day,
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert obj["trade_only"] is True
    assert obj["card_total"] == 1
    md_body = Path(obj["report_md_path"]).read_text(encoding="utf-8")
    assert "Run: trade-1" in md_body
    assert "Run: utility-1" not in md_body
    assert "Status: UNKNOWN" not in md_body


def test_decision_story_report_supports_new_decision_trace_events(tmp_path: Path, capsys) -> None:
    day = "2026-03-13"
    events = tmp_path / "events.jsonl"
    out_dir = tmp_path / "decision_story"
    _write_jsonl(
        events,
        [
            {
                "run_id": "trace-1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "decision_trace",
                "event": "strategic_frame",
                "payload": {
                    "agent": "strategist",
                    "payload": {"playbook": "pullback", "key_events": ["risk_off_session"]},
                },
            },
            {
                "run_id": "trace-1",
                "ts": f"{day}T01:00:01+00:00",
                "stage": "decision_trace",
                "event": "candidate_selection",
                "payload": {
                    "agent": "scanner",
                    "payload": {
                        "selected_symbol": "032820",
                        "playbook": "pullback",
                        "candidate_pool_size": 5,
                        "selected_candidate": {
                            "symbol": "032820",
                            "why": "top_value+sector_theme",
                            "score_total": 1.12,
                            "risk_score": 0.18,
                        },
                    },
                },
            },
            {
                "run_id": "trace-1",
                "ts": f"{day}T01:00:02+00:00",
                "stage": "decision_trace",
                "event": "entry_exit_decision",
                "payload": {
                    "agent": "monitor",
                    "payload": {
                        "selected_symbol": "032820",
                        "entry_reason": "pullback_entry",
                        "exit_reason": "stop_loss",
                        "thresholds": {"stop_loss_pct": 0.01, "take_profit_pct": 0.02},
                    },
                },
            },
            {
                "run_id": "trace-1",
                "ts": f"{day}T01:00:03+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "SELL", "symbol": "032820", "qty": 1}, "payload": {"broker_code": "0"}},
            },
        ],
    )

    rc = decision_story_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(out_dir),
            "--day",
            day,
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert obj["story_total"] == 1
    md_body = Path(obj["report_md_path"]).read_text(encoding="utf-8")
    assert "Run trace-1" in md_body
    assert "symbol: **032820**" in md_body
    assert "decision_reason_summary: stop_loss" in md_body


def test_operator_daily_summary_supports_new_decision_trace_events(tmp_path: Path, capsys) -> None:
    day = "2026-03-13"
    events = tmp_path / "events.jsonl"
    metrics_dir = tmp_path / "metrics"
    out_dir = tmp_path / "operator_summary"
    _write_json(
        metrics_dir / f"metrics_{day}.json",
        {
            "execution": {"intents_created": 2, "intents_blocked": 0},
            "broker_api": {"api_429_rate": 0.0},
            "strategist_llm": {"success_rate": 1.0},
            "commander_resilience": {"total": 0},
        },
    )
    _write_jsonl(
        events,
        [
            {
                "run_id": "trace-2",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "decision_trace",
                "event": "strategic_frame",
                "payload": {"agent": "strategist", "payload": {"playbook": "defensive"}},
            },
            {
                "run_id": "trace-2",
                "ts": f"{day}T01:00:01+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "BUY", "symbol": "005930", "qty": 1}, "payload": {"broker_code": "0"}},
            },
        ],
    )

    rc = operator_summary_main(
        [
            "--event-log-path",
            str(events),
            "--metrics-report-dir",
            str(metrics_dir),
            "--report-dir",
            str(out_dir),
            "--day",
            day,
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert obj["trading_activity_summary"]["run_total"] == 1
    assert obj["trading_activity_summary"]["decision_action_counts"]["BUY"] == 1
    assert obj["trading_activity_summary"]["strategy_counts"]["defensive"] == 1
    assert Path(obj["report_json_path"]) == tmp_path / "operator_summary" / "daily" / day / "operator_summary.json"


def test_m13_eod_report_auto_attaches_operator_visibility_bundle(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    day = "2026-02-13"
    epoch = int(datetime(2026, 2, 13, 6, 30, tzinfo=timezone.utc).timestamp())
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": epoch,
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True},
            }
        ],
    )

    monkeypatch.setenv("EVENT_LOG_PATH", str(events))
    monkeypatch.setenv("REPORT_DIR", str(reports))

    called = {"n": 0}

    def fake_bundle(*, events_path: Path, report_root: Path, day: str | None = None):
        called["n"] += 1
        assert events_path == events
        assert report_root == reports
        return {"day": day, "operator_summary_md": "ok.md"}

    dt = datetime(2026, 2, 13, 15, 40, tzinfo=KST)
    out = run_m13_eod_report(
        {},
        dt=dt,
        market_hours=MarketHours(),
        generate_operator_reports=fake_bundle,
        grace_minutes=0,
    )

    assert out["eod_skipped"] is False
    assert called["n"] == 1
    assert out["daily_report"]["day"] == day
    assert out["daily_report"]["operator_visibility"]["day"] == day


def test_decision_story_and_run_cards_render_observability_for_no_trade_run(tmp_path: Path, capsys) -> None:
    day = "2026-04-06"
    events = tmp_path / "events.jsonl"
    decision_dir = tmp_path / "decision_story"
    cards_dir = tmp_path / "run_cards"
    _write_jsonl(
        events,
        [
            {
                "run_id": "no-trade-1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "strategist",
                "event": "policy_resolution",
                "payload": {
                    "strategy_generation_mode": "fallback",
                    "fallback_used": True,
                    "fallback_source": "cached_strategy",
                    "llm_ok": False,
                },
            },
            {
                "run_id": "no-trade-1",
                "ts": f"{day}T01:00:01+00:00",
                "stage": "commander_router",
                "event": "route_selected",
                "payload": {
                    "route_selected": "monitor_only",
                    "strategist_call_decision": "skip",
                    "strategist_skip_reason": "position already open",
                },
            },
            {
                "run_id": "no-trade-1",
                "ts": f"{day}T01:00:02+00:00",
                "stage": "scanner",
                "event": "selection_output",
                "payload": {
                    "scanner_selected_symbol": "005930",
                    "scanner_rank": 1,
                    "scanner_score_total": 0.91,
                    "scanner_top_candidates": [{"rank": 1, "symbol": "005930", "score_total": 0.91}],
                },
            },
            {
                "run_id": "no-trade-1",
                "ts": f"{day}T01:00:03+00:00",
                "stage": "monitor",
                "event": "entry_decision_detail",
                "payload": {
                    "decision": "WAIT",
                    "reason": "below_vwap_reclaim_not_ready",
                    "no_trade_surface": {
                        "decision_outcome": "WAIT",
                        "pre_intent_decision": "WAIT",
                        "no_trade_stage": "pre_intent_wait",
                        "no_trade_reason_code": "below_vwap_reclaim_not_ready",
                        "no_trade_reason_summary": "below vwap reclaim not ready",
                        "dominant_blocker": "below_vwap_reclaim_not_ready",
                        "near_ready_flag": True,
                        "distance_to_ready": {"reclaim_score_gap": 0.03, "confidence_gap": 0.01},
                    },
                    "scanner_monitor_handoff": {
                        "scanner_selected_symbol": "005930",
                        "scanner_rank": 1,
                        "scanner_vs_monitor_alignment": "partial_mismatch",
                        "monitor_rejection_reason_code": "below_vwap_reclaim_not_ready",
                    },
                },
            },
        ],
    )

    rc_story = decision_story_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(decision_dir),
            "--day",
            day,
            "--json",
        ]
    )
    story_obj = json.loads(capsys.readouterr().out.strip())
    assert rc_story == 0
    assert story_obj["story_total"] == 1
    story_md = Path(story_obj["report_md_path"]).read_text(encoding="utf-8")
    assert "decision_axis: entry" in story_md
    assert "primary_explanation: below vwap reclaim not ready" in story_md
    assert "entry_narrative: below vwap reclaim not ready" in story_md
    assert "exit_narrative: -" in story_md
    assert "narrative_order: entry" in story_md
    assert "why_not_buy_summary: below vwap reclaim not ready" in story_md
    assert "dominant_blocker: below_vwap_reclaim_not_ready" in story_md
    assert "distance_to_ready: reclaim_score_gap=0.0300, confidence_gap=0.0100" in story_md
    assert "scanner_monitor_handoff: top1=005930" in story_md
    assert "strategist_provenance: mode=fallback" in story_md
    assert "commander_route_provenance: route=monitor_only" in story_md

    rc_cards = run_card_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(cards_dir),
            "--day",
            day,
            "--json",
        ]
    )
    cards_obj = json.loads(capsys.readouterr().out.strip())
    assert rc_cards == 0
    assert cards_obj["card_total"] == 1
    cards_md = Path(cards_obj["report_md_path"]).read_text(encoding="utf-8")
    assert "Route: monitor_only" in cards_md
    assert "Route Source: event_fallback" in cards_md
    assert "Decision Axis: entry" in cards_md
    assert "Primary Explanation: below vwap reclaim not ready" in cards_md
    assert "Narrative Order: entry" in cards_md
    assert "Entry Narrative: below vwap reclaim not ready" in cards_md
    assert "Exit Narrative: -" in cards_md
    assert "Scanner Top-1: 005930/0.91" in cards_md
    assert "Monitor Outcome: WAIT" in cards_md
    assert "Dominant Blocker: below_vwap_reclaim_not_ready" in cards_md
    assert "Near Ready: True" in cards_md
    assert "Strategist Mode: fallback" in cards_md


def test_decision_story_and_run_cards_separate_exit_narrative_for_sell_run(tmp_path: Path, capsys) -> None:
    day = "2026-04-08"
    events = tmp_path / "events.jsonl"
    decision_dir = tmp_path / "decision_story"
    cards_dir = tmp_path / "run_cards"
    _write_jsonl(
        events,
        [
            {
                "run_id": "sell-1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "decision_trace",
                "event": "entry_exit_decision",
                "payload": {
                    "agent": "monitor",
                    "payload": {
                        "selected_symbol": "069500",
                        "exit_reason": "peak_drawdown",
                        "thresholds": {"hard_stop_pct": 0.03},
                    },
                },
            },
            {
                "run_id": "sell-1",
                "ts": f"{day}T01:00:01+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {
                    "order": {"action": "SELL", "symbol": "069500", "qty": 1},
                    "payload": {"broker_code": "0"},
                },
            },
        ],
    )

    rc_story = decision_story_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(decision_dir),
            "--day",
            day,
            "--json",
        ]
    )
    story_obj = json.loads(capsys.readouterr().out.strip())
    assert rc_story == 0
    assert story_obj["data_freshness"]["freshness_status"] == "fresh"
    assert story_obj["route_provenance"]["route_source"] == "canonical_commander_preferred"
    story_md = Path(story_obj["report_md_path"]).read_text(encoding="utf-8")
    assert "## Data Freshness" in story_md
    assert "decision_axis: exit" in story_md
    assert "primary_explanation: peak_drawdown" in story_md
    assert "entry_narrative: -" in story_md
    assert "exit_narrative: peak_drawdown" in story_md
    assert "narrative_order: exit" in story_md
    assert "why_exit_summary: peak_drawdown" in story_md
    assert "why_not_buy_summary: -" in story_md

    rc_cards = run_card_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(cards_dir),
            "--day",
            day,
            "--json",
        ]
    )
    cards_obj = json.loads(capsys.readouterr().out.strip())
    assert rc_cards == 0
    assert cards_obj["data_freshness"]["freshness_status"] == "fresh"
    assert cards_obj["route_provenance"]["route_source"] == "canonical_commander_preferred"
    cards_md = Path(cards_obj["report_md_path"]).read_text(encoding="utf-8")
    assert "## Data Freshness" in cards_md
    assert "Decision Axis: exit" in cards_md
    assert "Primary Explanation: peak_drawdown" in cards_md
    assert "Narrative Order: exit" in cards_md
    assert "Entry Narrative: -" in cards_md
    assert "Exit Narrative: peak_drawdown" in cards_md
    assert "Dominant Blocker: -" in cards_md


def test_run_cards_prefers_canonical_commander_route_source(tmp_path: Path, capsys) -> None:
    day = "2026-04-08"
    events = tmp_path / "events.jsonl"
    cards_dir = tmp_path / "dev" / "manual" / "run_cards"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "005930", "qty": 1, "reason": "signal"}}},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:01+00:00",
                "stage": "commander_router",
                "event": "route_selected",
                "payload": {"route_selected": "full_cycle"},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:02+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "blocked"},
            },
        ],
    )
    commander_path = tmp_path / "canonical" / day / "r1" / "commander.json"
    commander_path.parent.mkdir(parents=True, exist_ok=True)
    commander_path.write_text(
        json.dumps({"route_selected": "monitor_only", "strategy_generation_mode": "cached"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rc_cards = run_card_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(cards_dir),
            "--day",
            day,
            "--json",
        ]
    )
    cards_obj = json.loads(capsys.readouterr().out.strip())
    assert rc_cards == 0
    cards_md = Path(cards_obj["report_md_path"]).read_text(encoding="utf-8")
    assert "Route: monitor_only" in cards_md
    assert "Route Source: canonical_commander" in cards_md
