from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from apps.operator_ui.data_access import OperatorUIConfig
from apps.operator_ui.main import create_app


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _make_config(tmp_path: Path) -> OperatorUIConfig:
    reports = tmp_path / "reports"
    events = tmp_path / "data" / "logs" / "events.jsonl"
    evidence = tmp_path / "data" / "evidence_ledger" / "events.jsonl"
    memory = tmp_path / "data" / "strategy_memory" / "daily"

    _write_json(
        reports / "daily" / "daily_2026-03-13.json",
        {"day": "2026-03-13", "events": 10, "decision_actions": {"BUY": 1, "SELL": 1}, "approvals": 2, "blocks": 1},
    )
    _write_json(
        reports / "operator_summary" / "operator_summary_2026-03-13.json",
        {
            "day": "2026-03-13",
            "executive_summary": {"system_status": "GREEN", "summary_lines": ["runs ok"]},
            "system_health_status": {"system_health_level": "GREEN", "recommended_action": ["continue"]},
            "trading_activity_summary": {"run_total": 1, "executions_total": 1, "blocked_total": 0},
        },
    )
    _write_json(
        reports / "dev" / "analysis" / "reporter_analysis" / "reporter_analysis_2026-03-13.json",
        {
            "day": "2026-03-13",
            "ai_review": {"status": "ok"},
            "ai_run_grade": "B",
            "ai_summary": "Reporter summary",
            "trade_summary": {"trade_count": 1, "symbols_traded": ["005930"]},
            "decision_trace_chain_summary": {"chains": [{"run_id": "run-1", "scanner": {"selected_symbol": "005930"}}]},
        },
    )
    _write_json(
        reports / "reconciliation" / "broker_trade_reconciliation_2026-03-13.json",
        {"summary": {"local_total": 1, "broker_total": 1, "matched_by_ord_no": 1, "broker_window_limited": False}},
    )
    _write_jsonl(
        events,
        [
            {"run_id": "run-1", "ts": "2026-03-13T00:00:00+00:00", "stage": "commander_router", "event": "route", "payload": {"mode": "integrated_chain", "phase": "session", "agents": ["strategist", "scanner", "monitor"]}},
            {"run_id": "run-1", "ts": "2026-03-13T00:00:01+00:00", "stage": "strategist_llm", "event": "result", "payload": {"status": "ok", "model": "minimax/minimax-m2.5"}},
            {"run_id": "run-1", "ts": "2026-03-13T00:00:02+00:00", "stage": "strategist", "event": "summary", "payload": {"playbook": "defensive", "risk_tone": "conservative"}},
            {"run_id": "run-1", "ts": "2026-03-13T00:00:03+00:00", "stage": "decision_trace", "event": "strategic_frame", "payload": {"agent": "strategist", "payload": {"themes": ["quality"], "playbook": "defensive", "macro_stress_overlay": {"active": True, "stress_flags": ["elevated_vix"]}}}},
            {"run_id": "run-1", "ts": "2026-03-13T00:00:04+00:00", "stage": "scanner", "event": "summary", "payload": {"top_stock": "005930", "top_score": 0.91}},
            {"run_id": "run-1", "ts": "2026-03-13T00:00:05+00:00", "stage": "decision_trace", "event": "candidate_selection", "payload": {"agent": "scanner", "payload": {"selected_symbol": "005930", "candidate_pool_size": 5, "selected_candidate": {"feature_snapshot": {"engine_ma20_gap": 0.1, "engine_ma60": 1.0, "engine_ma120": 1.0, "engine_adx14": 20.0, "engine_trend_strength": 0.7, "engine_volume_spike20": 1.4, "engine_volatility20": 0.2, "engine_vwap_distance": 0.01, "engine_sector_relative_strength": 0.3, "engine_cross_section_rank": 0.8, "engine_regime": "trend", "engine_signal_score": 0.9}}}}},
            {"run_id": "run-1", "ts": "2026-03-13T00:00:06+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "no_position", "exit_reason": "no_position"}},
            {"run_id": "run-1", "ts": "2026-03-13T00:00:07+00:00", "stage": "decision_trace", "event": "entry_exit_decision", "payload": {"agent": "monitor", "payload": {"entry_reason": "no_position"}}},
            {"run_id": "run-1", "ts": "2026-03-13T00:00:08+00:00", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": True, "reason": "Allowed"}},
            {"run_id": "run-1", "ts": "2026-03-13T00:00:09+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"action": "BUY", "symbol": "005930", "qty": 1, "fill_status_summary": "EXECUTED_OK"}},
            {"run_id": "run-1", "ts": "2026-03-13T00:00:10+00:00", "stage": "commander_router", "event": "end", "payload": {"status": "ok", "path": "integrated_chain"}},
        ],
    )
    _write_jsonl(
        evidence,
        [
            {
                "run_id": "run-1",
                "timestamp": "2026-03-13T00:00:02+00:00",
                "agent": "strategist",
                "stage": "theme_selection",
                "raw_input": {"global_sentiment": {"score": -0.2}, "news_query_targets": ["코스피", "미국 증시"]},
                "llm_prompt": "strategist prompt",
                "llm_response": "{\"themes\":[\"quality\"],\"playbook\":\"defensive\",\"market_regime\":\"neutral\"}",
                "parsed_output": {"themes": ["quality"], "playbook": "defensive", "market_regime": "neutral"},
            }
        ],
    )
    _write_json(
        memory / "2026-03-13.json",
        {
            "day": "2026-03-13",
            "updated_at": "2026-03-13T13:22:14+00:00",
            "latest_run_id": "reporter-2026-03-13",
            "latest_feedback": {
                "trade_summary": {"trade_count": 3},
                "monitor_evaluation": {"monitor_status": "overtrading_risk"},
                "strategist_evaluation": {"theme_alignment_status": "aligned"},
                "ai_findings": ["monitor risk remained elevated"],
            },
        },
    )
    return OperatorUIConfig(
        repo_root=tmp_path,
        reports_root=reports,
        event_log_path=events,
        evidence_log_path=evidence,
        strategy_memory_path=memory,
    )


def test_operator_ui_overview_and_run_pages(tmp_path: Path) -> None:
    app = create_app(_make_config(tmp_path))
    client = TestClient(app)

    overview = client.get("/")
    assert overview.status_code == 200
    assert "Operator Console" in overview.text
    assert "Reporter summary" in overview.text
    assert "Strategy Memory Timeline" in overview.text
    assert "monitor risk remained elevated" in overview.text
    assert "Today Trades" in overview.text
    assert "BUY 005930 x0" not in overview.text
    assert "BUY 005930 x1" in overview.text
    assert "Latest Strategist Prompt" in overview.text
    assert "strategist prompt" in overview.text
    assert "defensive" in overview.text

    runs = client.get("/runs")
    assert runs.status_code == 200
    assert "run-1" in runs.text
    assert "005930" in runs.text
    assert "active elevated_vix" in runs.text
    assert "strong (100%)" in runs.text

    detail = client.get("/runs/run-1")
    assert detail.status_code == 200
    assert "strategist prompt" in detail.text
    assert "EXECUTED_OK" in detail.text
    assert "Feature Coverage" in detail.text

    health = client.get("/healthz")
    assert health.status_code == 200
    obj = health.json()
    assert obj["status"] == "ok"
    assert obj["system_status"] == "GREEN"
