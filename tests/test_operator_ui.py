from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import apps.operator_ui.data_access as data_access
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


class _FakeRouter:
    def __init__(self) -> None:
        self.client = object()

    def chat(self, role: str, messages: list[dict], *, policy: dict | None = None) -> str:
        model = (policy or {}).get("model") or ""
        return json.dumps(
            {
                "headline": "run-1 운영 요약",
                "commander_summary": "지휘자는 integrated_chain 세션을 실행했습니다.",
                "strategist_summary": f"전략가는 뉴스와 글로벌 감성을 읽고 defensive 프레임을 만들었습니다. model={model}",
                "scanner_summary": "스캐너는 Kiwoom 후보 중 005930을 1등으로 골랐습니다.",
                "monitor_summary": "모니터는 no_position 상태를 보고 진입 가능 상태로 판단했습니다.",
                "supervisor_summary": "감독관은 주문을 허용했습니다.",
                "executor_summary": "수행자는 BUY 005930 1주를 실행했습니다.",
                "reporter_summary": "리포터는 오늘 run을 정상으로 요약했습니다.",
                "operator_takeaways": [
                    "뉴스/거시 입력이 포함됐습니다.",
                    "차트/feature coverage가 strong입니다.",
                ],
            },
            ensure_ascii=False,
        )


class _RepairRouter:
    def __init__(self) -> None:
        self.client = object()
        self.calls = 0

    def chat(self, role: str, messages: list[dict], *, policy: dict | None = None) -> str:
        self.calls += 1
        if self.calls == 1:
            return "생각: 먼저 요약을 정리한다. JSON은 아래에 적겠다."
        return json.dumps(
            {
                "headline": "run-1 운영 요약",
                "commander_summary": "지휘자는 integrated_chain 세션을 실행했습니다.",
                "strategist_summary": "전략가는 뉴스와 글로벌 감성을 읽었습니다.",
                "scanner_summary": "스캐너는 Kiwoom 후보 중 005930을 골랐습니다.",
                "monitor_summary": "모니터는 no_position을 확인했습니다.",
                "supervisor_summary": "감독관은 주문을 허용했습니다.",
                "executor_summary": "수행자는 BUY 005930 1주를 실행했습니다.",
                "reporter_summary": "리포터는 정상 run으로 평가했습니다.",
                "operator_takeaways": ["repair 경로가 동작했습니다."],
            },
            ensure_ascii=False,
        )


class _LineRepairRouter:
    def __init__(self) -> None:
        self.client = object()
        self.calls = 0

    def chat(self, role: str, messages: list[dict], *, policy: dict | None = None) -> str:
        self.calls += 1
        if self.calls == 1:
            return "생각: 먼저 운영 브리프를 정리한다."
        if self.calls == 2:
            return "여전히 JSON 대신 설명문을 이어간다."
        return (
            "headline: run-1 운영 요약\n"
            "commander_summary: 지휘자는 integrated_chain 세션을 실행했습니다.\n"
            "strategist_summary: 전략가는 뉴스와 글로벌 감성을 읽었습니다.\n"
            "scanner_summary: 스캐너는 Kiwoom 후보 중 005930을 골랐습니다.\n"
            "monitor_summary: 모니터는 no_position을 확인했습니다.\n"
            "supervisor_summary: 감독관은 주문을 허용했습니다.\n"
            "executor_summary: 수행자는 BUY 005930 1주를 실행했습니다.\n"
            "reporter_summary: 리포터는 정상 run으로 평가했습니다.\n"
            "operator_takeaways: line repair 동작 | 무료 모델 경로 복구\n"
        )


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
    _write_json(
        memory / "2026-03-13.json",
        {
            "day": "2026-03-13",
            "updated_at": "2026-03-13T13:22:14+09:00",
            "latest_run_id": "reporter-2026-03-13",
            "latest_feedback": {
                "trade_summary": {"trade_count": 3},
                "monitor_evaluation": {"monitor_status": "overtrading_risk"},
                "strategist_evaluation": {"theme_alignment_status": "aligned"},
                "ai_findings": ["monitor risk remained elevated"],
            },
        },
    )
    _write_jsonl(
        events,
        [
            {"run_id": "run-1", "ts": "2026-03-16T00:00:00+00:00", "stage": "commander_router", "event": "route", "payload": {"mode": "integrated_chain", "phase": "session", "agents": ["strategist", "scanner", "monitor"]}},
            {"run_id": "run-1", "ts": "2026-03-16T00:00:01+00:00", "stage": "strategist_llm", "event": "result", "payload": {"status": "ok", "model": "minimax/minimax-m2.5"}},
            {"run_id": "run-1", "ts": "2026-03-16T00:00:02+00:00", "stage": "strategist", "event": "summary", "payload": {"playbook": "defensive", "risk_tone": "conservative", "news_query_targets": ["코스피", "미국 증시"], "themes": ["quality"]}},
            {"run_id": "run-1", "ts": "2026-03-16T00:00:03+00:00", "stage": "decision_trace", "event": "strategic_frame", "payload": {"agent": "strategist", "payload": {"themes": ["quality"], "playbook": "defensive", "macro_stress_overlay": {"active": True, "stress_flags": ["elevated_vix"]}}}},
            {"run_id": "run-1", "ts": "2026-03-16T00:00:04+00:00", "stage": "scanner", "event": "summary", "payload": {"top_stock": "005930", "top_score": 0.91, "candidate_pool_after_filter": 5}},
            {"run_id": "run-1", "ts": "2026-03-16T00:00:05+00:00", "stage": "decision_trace", "event": "candidate_selection", "payload": {"agent": "scanner", "payload": {"selected_symbol": "005930", "candidate_pool_size": 5, "kiwoom_pool_source_mix": {"top_value": 5, "top_volume": 5}, "selected_candidate": {"symbol": "005930", "why": "top_value+trend", "feature_snapshot": {"skill_quote_price": 70500, "quote_volume": 1234567, "quote_trading_value": 89012345678, "intraday_change_pct": 2.15, "engine_ma20_gap": 0.1, "engine_ma60": 1.0, "engine_ma120": 1.0, "engine_adx14": 20.0, "engine_trend_strength": 0.7, "engine_volume_spike20": 1.4, "engine_volatility20": 0.2, "engine_vwap_distance": 0.01, "engine_sector_relative_strength": 0.3, "engine_cross_section_rank": 0.8, "engine_regime": "trend", "engine_signal_score": 0.9}}}}},
            {"run_id": "run-1", "ts": "2026-03-16T00:00:06+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "no_position", "exit_reason": "no_position"}},
            {"run_id": "run-1", "ts": "2026-03-16T00:00:07+00:00", "stage": "decision_trace", "event": "entry_exit_decision", "payload": {"agent": "monitor", "payload": {"entry_reason": "no_position"}}},
            {"run_id": "run-1", "ts": "2026-03-16T00:00:08+00:00", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": True, "reason": "Allowed"}},
            {"run_id": "run-1", "ts": "2026-03-16T00:00:09+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"action": "BUY", "symbol": "005930", "qty": 1, "fill_status_summary": "EXECUTED_OK"}},
            {"run_id": "run-1", "ts": "2026-03-16T00:00:10+00:00", "stage": "commander_router", "event": "end", "payload": {"status": "ok", "path": "integrated_chain"}},
        ],
    )
    _write_jsonl(
        evidence,
        [
            {
                "run_id": "run-1",
                "timestamp": "2026-03-16T00:00:02+00:00",
                "agent": "strategist",
                "stage": "theme_selection",
                "raw_input": {
                    "global_sentiment_inputs": {
                        "score": -0.2,
                        "fear_index": {"level": 24.5},
                        "macro_moves": {"dxy_pct": 0.3},
                    },
                    "news_query_targets": ["코스피", "미국 증시"],
                    "collected_market_news": [{"title": "코스피 장중 흐름 점검"}],
                    "collected_candidate_news": [{"title": "삼성전자 수급 집중"}],
                },
                "llm_prompt": "strategist prompt",
                "llm_response": '{"themes":["quality"],"playbook":"defensive","market_regime":"neutral"}',
                "parsed_output": {"themes": ["quality"], "playbook": "defensive", "market_regime": "neutral"},
            }
        ],
    )
    return OperatorUIConfig(
        repo_root=tmp_path,
        reports_root=reports,
        event_log_path=events,
        evidence_log_path=evidence,
        strategy_memory_path=memory,
    )


def test_operator_ui_overview_and_run_pages(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    app = create_app(_make_config(tmp_path))
    client = TestClient(app)

    overview = client.get("/")
    assert overview.status_code == 200
    assert "Operator Console" in overview.text
    assert "2026-03-16" in overview.text
    assert "Reporter summary" in overview.text
    assert "Strategy Memory Timeline" in overview.text
    assert "monitor risk remained elevated" in overview.text
    assert "Today Traded Symbols" in overview.text
    assert "buy=1 sell=0 net=1" in overview.text
    assert "Overtrading Warning" in overview.text
    assert "level=normal total_executions=1" in overview.text
    assert "Today Trades" in overview.text
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
    assert "운영자 브리프" in detail.text
    assert "stepfun/step-3.5-flash:free" in detail.text
    assert "전략가는 뉴스와 글로벌 감성을 읽고 defensive 프레임을 만들었습니다." in detail.text
    assert "grade=B" in detail.text
    assert "strategist prompt" in detail.text
    assert "EXECUTED_OK" in detail.text
    assert "Feature Coverage" in detail.text
    assert "Quote Metrics" in detail.text
    assert "price=70500" in detail.text
    assert "2.15" in detail.text
    assert "Same-Day Symbol Trade History" in detail.text
    assert "trade_count=1" in detail.text
    assert "Recent Same-Symbol Run Chain" in detail.text
    assert "run_count=1" in detail.text

    health = client.get("/healthz")
    assert health.status_code == 200
    obj = health.json()
    assert obj["status"] == "ok"
    assert obj["system_status"] == "GREEN"
    assert obj["latest_day"] == "2026-03-16"


def test_operator_ui_run_detail_repairs_non_json_llm_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _RepairRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    app = create_app(_make_config(tmp_path))
    client = TestClient(app)

    detail = client.get("/runs/run-1")
    assert detail.status_code == 200
    assert "status=repaired" in detail.text
    assert "repair 경로가 동작했습니다." in detail.text


def test_operator_ui_run_detail_uses_line_repair_for_free_model(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _LineRepairRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    app = create_app(_make_config(tmp_path))
    client = TestClient(app)

    detail = client.get("/runs/run-1")
    assert detail.status_code == 200
    assert "status=line_repaired" in detail.text
    assert "line repair 동작" in detail.text
