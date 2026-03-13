from __future__ import annotations

import json
from pathlib import Path

from libs.agent.reporter import Reporter
import libs.reporting.reporter_analysis as reporter_analysis_module
from libs.research.strategy_memory_store import load_recent_strategy_feedback
from scripts.run_reporter_analysis_report import main as reporter_analysis_main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_reporter_analysis_script_builds_structured_sections(tmp_path: Path, capsys) -> None:
    day = "2026-03-10"
    events = tmp_path / "events.jsonl"
    intents = tmp_path / "intents.jsonl"
    reports_root = tmp_path / "reports"
    out_dir = reports_root / "reporter_analysis"

    _write_jsonl(
        events,
        [
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:00+00:00",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"provider": "openrouter", "model": "minimax/minimax-m2.5", "themes": ["semiconductor", "AI"]},
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:00+00:00",
                "stage": "strategist",
                "event": "summary",
                "payload": {
                    "themes": ["semiconductor", "AI"],
                    "scanner_priority": ["momentum", "trend_strength", "liquidity"],
                    "report_focus": ["Validate theme follow-through", "Check monitor exit quality"],
                },
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "scanner",
                "event": "summary",
                "payload": {"candidate_source": "kiwoom_market_data", "top_stock": "005930", "top_score": 0.91},
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "decision_trace",
                "event": "snapshot",
                "payload": {
                    "agent": "strategist",
                    "payload": {
                        "market_regime": "risk_on",
                        "themes": ["semiconductor"],
                        "playbook": "breakout",
                        "scanner_bias": "leader",
                        "risk_tone": "normal",
                        "monitor_guidance": "hold_through_noise",
                    },
                },
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "decision_trace",
                "event": "snapshot",
                "payload": {
                    "agent": "scanner",
                    "payload": {
                        "candidate_pool_size": 12,
                        "selected_symbol": "005930",
                        "top_candidates": ["005930", "000660"],
                        "score_breakdown_summary": {"momentum": 0.4, "trend": 0.3},
                    },
                },
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "decision_trace",
                "event": "snapshot",
                "payload": {
                    "agent": "monitor",
                    "payload": {
                        "entry_reason": "entry_signal",
                        "exit_reason": "hold",
                        "monitor_reason": "hold",
                        "min_hold_blocked": False,
                        "sell_cooldown_blocked": False,
                    },
                },
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:03+00:00",
                "stage": "decision_trace",
                "event": "verdict",
                "payload": {"agent": "supervisor", "payload": {"verdict": "APPROVED", "guard_reason": ""}},
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:04+00:00",
                "stage": "decision_trace",
                "event": "result",
                "payload": {
                    "agent": "executor",
                    "payload": {"execution_attempted": True, "fill_status_summary": "executed"},
                },
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:02+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {
                    "decision_packet": {
                        "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "reason": "entry_signal"},
                        "why": {"news": {"global_sentiment_score": 0.2, "symbol_sentiment_score": 0.3}},
                    },
                    "trace": {"strategy": "RegimeMomentumV1", "rationale": "entry"},
                },
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:03+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True},
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:04+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 100}},
            },
            {
                "run_id": "r_sell",
                "ts": f"{day}T00:01:00+00:00",
                "stage": "monitor",
                "event": "summary",
                "payload": {"exit_reason": "volatility_spike", "monitor_reason": "confirmed_exit_signal"},
            },
            {
                "run_id": "r_sell",
                "ts": f"{day}T00:01:01+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {
                    "decision_packet": {"intent": {"action": "SELL", "symbol": "005930", "qty": 1, "reason": "exit_signal"}},
                    "trace": {"strategy": "ExitPolicyStrategist", "rationale": "exit"},
                },
            },
            {
                "run_id": "r_sell",
                "ts": f"{day}T00:01:02+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True},
            },
            {
                "run_id": "r_sell",
                "ts": f"{day}T00:01:03+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "SELL", "symbol": "005930", "qty": 1, "price": 101}},
            },
            {
                "run_id": "r_block",
                "ts": f"{day}T00:02:00+00:00",
                "stage": "monitor",
                "event": "summary",
                "payload": {"min_hold_blocked": True, "sell_cooldown_blocked": True, "monitor_reason": "cooldown_active"},
            },
            {
                "run_id": "r_block",
                "ts": f"{day}T00:02:01+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "risk_guard"},
            },
            {
                "run_id": "r_fail",
                "ts": f"{day}T00:02:11+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"ok": False, "payload": {"broker_code": "500"}},
            },
        ],
    )
    _write_jsonl(
        intents,
        [
            {"ts": f"{day}T00:00:05+00:00", "intent_id": "i1", "intent": {"intent_id": "i1", "action": "BUY", "symbol": "005930", "qty": 1}},
            {"ts": f"{day}T00:00:06+00:00", "intent_id": "i1", "status": "approved", "reason": "manual", "intent": {"intent_id": "i1"}},
            {"ts": f"{day}T00:00:07+00:00", "intent_id": "i1", "status": "executed", "reason": None, "intent": {"intent_id": "i1"}},
            {"ts": f"{day}T00:02:02+00:00", "intent_id": "i2", "status": "rejected", "reason": "supervisor_reject", "intent": {"intent_id": "i2"}},
        ],
    )

    rc = reporter_analysis_main(
        [
            "--event-log-path",
            str(events),
            "--intents-path",
            str(intents),
            "--report-dir",
            str(out_dir),
            "--reports-root",
            str(reports_root),
            "--day",
            day,
            "--rapid-cycle-threshold-sec",
            "120",
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert obj["day"] == day
    assert int(obj["trade_decision_summaries"]["trade_summary_total"]) >= 1
    assert int((obj.get("trade_summary") or {}).get("trade_count") or 0) >= 1
    assert "005930" in ((obj.get("trade_summary") or {}).get("symbols_traded") or [])
    assert int((obj.get("decision_chains") or {}).get("run_total") or 0) >= 1
    assert int((obj.get("decision_trace_chain_summary") or {}).get("run_total") or 0) >= 1
    assert int((obj.get("decision_trace_chain_summary") or {}).get("complete_chain_total") or 0) >= 1
    assert isinstance((obj.get("strategist_evaluation") or {}).get("themes_proposed"), list)
    assert isinstance((obj.get("scanner_evaluation") or {}).get("selected_symbol_top"), dict)
    assert isinstance((obj.get("monitor_evaluation") or {}).get("monitor_reason_top"), dict)
    assert int((obj.get("supervisor_activity") or {}).get("blocked_total") or 0) >= 1
    assert isinstance(obj.get("improvement_suggestions"), list)
    assert isinstance(obj.get("ai_review"), dict)
    assert str((obj.get("ai_review") or {}).get("status") or "") in ("disabled", "dry_run", "unavailable", "ok", "parse_error", "error")
    assert "ai_summary" in obj
    assert "ai_findings" in obj
    assert "ai_root_causes" in obj
    assert "ai_improvement_suggestions" in obj
    assert "ai_run_grade" in obj
    assert "ai_agent_evaluations" in obj
    flow = obj["intent_flow_analysis"]
    assert int(flow["intents_created"]) >= 1
    assert int(flow["intents_blocked"]) >= 1
    assert "min_hold_blocked" in (flow.get("reason_top") or {})
    assert int(obj["overtrading_diagnostics"]["rapid_buy_sell_cycles"]) >= 1
    assert isinstance((obj.get("operator_facing_summary") or {}).get("summary_lines"), list)
    assert isinstance((obj.get("developer_facing_summary") or {}).get("summary_lines"), list)
    incident_types = [str(x.get("type") or "") for x in (obj.get("incident_postmortem") or {}).get("incidents", []) if isinstance(x, dict)]
    assert "execution_anomaly" in incident_types
    strategy_effectiveness = obj.get("strategy_effectiveness") or {}
    assert (strategy_effectiveness.get("report_focus_counts") or {}).get("Validate theme follow-through") == 1
    assert (strategy_effectiveness.get("scanner_priority_counts") or {}).get("momentum") == 1


def test_reporter_analysis_persists_compact_strategy_memory(monkeypatch, tmp_path: Path) -> None:
    day = "2026-03-10"
    events = tmp_path / "events.jsonl"
    reports_root = tmp_path / "reports"
    out_dir = reports_root / "reporter_analysis"
    memory_path = tmp_path / "strategy_memory" / "feedback.jsonl"
    monkeypatch.setenv("STRATEGY_MEMORY_PATH", str(memory_path))

    _write_jsonl(
        events,
        [
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:00+00:00",
                "stage": "strategist",
                "event": "summary",
                "payload": {
                    "themes": ["semiconductor"],
                    "playbook": "breakout",
                    "risk_tone": "aggressive",
                    "monitor_guidance": "hold_through_noise",
                    "report_focus": ["theme_accuracy"],
                },
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "scanner",
                "event": "summary",
                "payload": {"candidate_source": "kiwoom_market_data", "top_stock": "005930", "top_score": 0.91},
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:02+00:00",
                "stage": "monitor",
                "event": "summary",
                "payload": {"monitor_reason": "hold", "exit_reason": "hold"},
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:03+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True},
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:04+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 100}},
            },
            {
                "run_id": "r_sell",
                "ts": f"{day}T00:05:00+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {
                    "decision_packet": {"intent": {"action": "SELL", "symbol": "005930", "qty": 1, "reason": "exit_signal"}},
                },
            },
            {
                "run_id": "r_sell",
                "ts": f"{day}T00:05:01+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "SELL", "symbol": "005930", "qty": 1, "price": 101}},
            },
        ],
    )

    md_path, js_path, out = reporter_analysis_module.generate_reporter_analysis_report(
        events,
        out_dir,
        day=day,
        reports_root=reports_root,
    )

    assert md_path.exists() is True
    assert js_path.exists() is True
    assert (out.get("strategy_memory_record") or {}).get("strategy_memory_path") == str(memory_path)
    rows = load_recent_strategy_feedback(10, path=memory_path)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "reporter-2026-03-10"
    assert rows[0]["strategist_evaluation"]["themes_proposed"] == ["semiconductor"]
    assert rows[0]["strategy_frame_summary"]["playbook_top"]["breakout"] == 1
    assert Path(out["report_json_path"]).exists()
    assert Path(out["report_md_path"]).exists()


def test_reporter_agent_can_run_passive_log_analysis(tmp_path: Path) -> None:
    day = "2026-03-10"
    events = tmp_path / "events.jsonl"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T00:00:00+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "risk_guard"},
            }
        ],
    )
    reporter = Reporter()
    out = reporter.analyze_event_logs(
        event_log_path=events,
        report_dir=tmp_path / "reporter_analysis",
        day=day,
        intents_path=tmp_path / "missing_intents.jsonl",
        reports_root=tmp_path / "reports",
    )
    assert out["schema_version"] == "reporter_analysis.v1"
    assert out["day"] == day
    assert "intent_flow_analysis" in out


def test_reporter_analysis_ai_review_enabled_integration(monkeypatch, tmp_path: Path, capsys) -> None:
    day = "2026-03-10"
    events = tmp_path / "events.jsonl"
    reports_root = tmp_path / "reports"
    out_dir = reports_root / "reporter_analysis"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T00:00:00+00:00",
                "stage": "scanner",
                "event": "summary",
                "payload": {"top_stock": "005930", "top_score": 0.91},
            }
        ],
    )

    def _fake_ai_review(**kwargs):
        return {
            "enabled": True,
            "status": "ok",
            "model": "fake/reporter-model",
            "reason": "",
            "ai_summary": "AI review summary",
            "ai_findings": ["finding_1"],
            "ai_root_causes": ["root_1"],
            "ai_improvement_suggestions": ["improve_1"],
            "ai_run_grade": "B+",
            "ai_agent_evaluations": {"strategist": "good", "scanner": "good", "monitor": "needs_improvement"},
        }

    monkeypatch.setattr(reporter_analysis_module, "build_ai_reporter_review", _fake_ai_review)

    rc = reporter_analysis_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(out_dir),
            "--reports-root",
            str(reports_root),
            "--day",
            day,
            "--ai-review",
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert (obj.get("ai_review") or {}).get("status") == "ok"
    assert obj.get("ai_summary") == "AI review summary"
    assert obj.get("ai_run_grade") == "B+"
    assert (obj.get("ai_agent_evaluations") or {}).get("monitor") == "needs_improvement"


def test_reporter_analysis_ai_review_failure_fallback(monkeypatch, tmp_path: Path, capsys) -> None:
    day = "2026-03-10"
    events = tmp_path / "events.jsonl"
    reports_root = tmp_path / "reports"
    out_dir = reports_root / "reporter_analysis"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T00:00:00+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "risk_guard"},
            }
        ],
    )

    def _raise_ai_review(**kwargs):
        raise RuntimeError("ai boom")

    monkeypatch.setattr(reporter_analysis_module, "build_ai_reporter_review", _raise_ai_review)

    rc = reporter_analysis_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(out_dir),
            "--reports-root",
            str(reports_root),
            "--day",
            day,
            "--ai-review",
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert (obj.get("ai_review") or {}).get("status") == "error"
    assert "trade_summary" in obj
    assert "intent_flow_analysis" in obj
