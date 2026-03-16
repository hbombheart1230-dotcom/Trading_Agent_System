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
    cache = tmp_path / "data" / "operator_ui" / "brief_cache"

    _write_json(
        reports / "daily" / "daily_2026-03-13.json",
        {"day": "2026-03-13", "events": 10, "decision_actions": {"BUY": 1, "SELL": 1}, "approvals": 2, "blocks": 1},
    )
    _write_json(
        reports / "daily" / "daily_2026-03-16.json",
        {"day": "2026-03-16", "events": 11, "decision_actions": {"BUY": 1}, "approvals": 1, "blocks": 0},
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
        reports / "operator_summary" / "operator_summary_2026-03-16.json",
        {
            "day": "2026-03-16",
            "executive_summary": {"system_status": "GREEN", "summary_lines": ["today runs ok"]},
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
        reports / "dev" / "analysis" / "reporter_analysis" / "reporter_analysis_2026-03-16.json",
        {
            "day": "2026-03-16",
            "ai_review": {"status": "ok"},
            "ai_run_grade": "A-",
            "ai_summary": "Today reporter summary",
            "trade_summary": {"trade_count": 1, "symbols_traded": ["005930"]},
            "decision_trace_chain_summary": {"chains": [{"run_id": "run-1", "scanner": {"selected_symbol": "005930"}}]},
        },
    )
    _write_json(
        reports / "reconciliation" / "broker_trade_reconciliation_2026-03-13.json",
        {"summary": {"local_total": 1, "broker_total": 1, "matched_by_ord_no": 1, "broker_window_limited": False}},
    )
    _write_json(
        reports / "reconciliation" / "broker_trade_reconciliation_2026-03-16.json",
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
            {"run_id": "run-1", "ts": "2026-03-16T00:00:09+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"allowed": True, "order": {"action": "BUY", "symbol": "005930", "qty": 1, "ord_qty": "1"}, "payload": {"order_id": "A0001", "broker_message": "EXECUTED_OK", "response_payload": {"ord_no": "A0001", "return_msg": "EXECUTED_OK"}}}},
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
    story_id = "20260316_005930_buy_run-1"
    trade_root = reports / "trades" / "2026" / "03" / story_id
    _write_json(
        trade_root / "aggregated_execution_bundle.json",
        {
            "schema_version": "live_execution_bundle.v2",
            "run_id": "run-1",
            "trade_id": story_id,
            "story_id": story_id,
            "ts": "2026-03-16T00:00:10+00:00",
            "execution": {"run_id": "run-1", "action": "BUY", "symbol": "005930", "qty": 1, "status": "EXECUTED_OK", "ord_no": "A0001"},
            "linked_run_ids": ["run-1"],
            "trade_lifecycle_status": "closed",
            "trade_lifecycle_summary": "Trade lifecycle was closed with approved simulation execution.",
            "story_contract": {
                "story_available": True,
                "story_type": "simulation",
                "execution_mode_label": "simulation (mock broker)",
                "story_anchor": "BUY 005930 x1 | run run-1",
                "warnings": [],
            },
            "reporter_status_human": {
                "status": "linked",
                "grade": "A-",
                "summary": "A same-day reporter analysis was linked to this run.",
            },
            "operator_conclusion_human": {
                "summary": "Current action is BUY with approved simulation execution.",
                "current_action": "BUY",
                "watch_next": ["Watch volatility expansion"],
                "thesis_invalidation": ["Negative macro shift"],
            },
            "market_context_human": {
                "summary": "Market regime was neutral with defensive playbook.",
            },
            "scanner_reason_human": {
                "summary": "Scanner selected 005930 as rank #1 out of 5 candidates.",
            },
            "filters_human": {"summary": "Scanner and guard checks passed 6 of 8 visible gates."},
            "monitor_reason_human": {"summary": "BUY was triggered because no_position entry condition passed."},
            "guard_reason_human": {"summary": "Supervisor approved the order."},
            "execution_outcome_human": {"summary": "BUY order was recorded in simulation mode."},
            "timeline": [
                {"step": "strategist_frame", "summary": "Defensive frame with elevated VIX input."},
                {"step": "scanner_ranking", "summary": "005930 ranked #1."},
            ],
        },
    )
    _write_json(
        trade_root / "trade_lifecycle.json",
        {
            "trade_id": story_id,
            "symbol": "005930",
            "status": "closed",
            "execution_mode_label": "simulation (mock broker)",
            "story_type": "simulation",
            "entry": {"run_id": "run-1", "ts": "2026-03-16T00:00:00+00:00", "action": "BUY", "qty": 1, "reason_human": "scanner rank #1"},
            "holding": {"run_ids": [], "holding_events": [], "posture_history": [], "monitor_updates": [], "noteworthy_changes": []},
            "exit": {"run_id": "run-1", "ts": "2026-03-16T00:00:10+00:00", "action": "SELL", "qty": 1, "reason_human": "simulated closeout"},
            "summary": {
                "holding_duration": "10m",
                "entry_reason_human": "scanner rank #1",
                "exit_reason_human": "simulated closeout",
                "lifecycle_summary_human": "Trade lifecycle was closed with approved simulation execution.",
                "operator_conclusion_human": "Trade completed in simulation mode.",
            },
            "reporter": {"status_human": "linked", "summary": "linked", "grade": "A-", "improvement_points": []},
            "timeline": [{"event": "entry", "ts": "2026-03-16T00:00:00+00:00", "description": "entry"}],
            "run_ids_all": ["run-1"],
            "warnings": [],
        },
    )
    _write_json(
        trade_root / "trade_story_input.json",
        {
            "schema_version": "trade_story_input.v1",
            "story_id": story_id,
            "run_id": "run-1",
            "symbol": "005930",
            "action": "BUY",
            "story_type": "simulation",
            "execution_mode_label": "simulation (mock broker)",
        },
    )
    _write_json(
        trade_root / "trade_report.json",
        {
            "schema_version": "trade_report.v1",
            "trade_id": story_id,
            "story_id": story_id,
            "run_id": "run-1",
            "symbol": "005930",
            "action": "BUY",
            "status": "closed",
            "story_type": "simulation",
            "execution_mode_label": "simulation (mock broker)",
            "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free", "reason": ""},
            "executive_summary": {
                "headline": "BUY 005930",
                "action": "BUY",
                "symbol": "005930",
                "confidence": "medium",
                "summary": "Scanner rank #1 with robust chart coverage and approved execution.",
            },
            "market_context": {
                "summary": "Market regime was neutral with elevated volatility and defensive posture.",
                "bullets": ["Regime: neutral", "Global sentiment: -0.20", "VIX: 24.50"],
            },
            "why_this_symbol": {
                "summary": "Selected as top ranked symbol due to value/volume blend.",
                "bullets": ["Universe scanned: 5", "Selected rank: #1", "Runner-up symbols had weaker coverage"],
            },
            "scanner_logic_and_filters": {
                "summary": "Primary filters passed and chart completeness remained strong.",
                "bullets": ["liquidity filter: PASS", "turnover filter: PASS", "chart completeness filter: PASS (12/12)"],
            },
            "monitor_trigger_reasoning": {
                "summary": "Monitor allowed BUY because no position was open.",
                "bullets": ["Posture: BUY", "Trigger: no_position", "Exit trigger: no"],
            },
            "guard_approval_result": {
                "summary": "Supervisor approved execution in manual mode.",
                "bullets": ["Supervisor allow: yes", "Guard reason: Allowed"],
            },
            "execution_result": {
                "summary": "BUY order was recorded successfully in simulation mode.",
                "bullets": ["Outcome: recorded", "Quantity: 1", "Order status: EXECUTED_OK"],
            },
            "reporter_evaluation": {
                "summary": "Reporter linked and graded the run A-.",
                "status": "linked",
                "grade": "A-",
                "bullets": ["Strategy alignment: normal", "Execution quality: good"],
            },
            "errors_weaknesses_improvement_points": {
                "summary": "No critical issues, but continue monitoring volatility.",
                "bullets": ["Elevated macro volatility remains"],
            },
            "timeline": [
                {"step": "strategist_frame", "summary": "Defensive frame with global sentiment input."},
                {"step": "scanner_ranking", "summary": "005930 ranked #1 out of 5."},
                {"step": "monitor_signal", "summary": "Entry condition passed for no_position."},
            ],
            "final_operator_conclusion": {
                "summary": "Maintain position monitoring under defensive volatility assumptions.",
                "current_action": "BUY",
                "watch_next": ["Volatility expansion", "Theme drift"],
                "thesis_invalidation": ["Macro regime breakdown"],
            },
        },
    )
    (trade_root / "trade_report.md").write_text("# Trade report\n", encoding="utf-8")
    return OperatorUIConfig(
        repo_root=tmp_path,
        reports_root=reports,
        event_log_path=events,
        evidence_log_path=evidence,
        strategy_memory_path=memory,
        operator_ui_cache_path=cache,
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
    assert "Today reporter summary" in overview.text
    assert "Strategy Memory Timeline" in overview.text
    assert "monitor risk remained elevated" in overview.text
    assert "Today Traded Symbols" in overview.text
    assert "BUY 1" in overview.text
    assert "SELL 0" in overview.text
    assert "NET 1" in overview.text
    assert "Overtrading Warning" in overview.text
    assert "Trading pace is normal today." in overview.text
    assert "Executions today: 1" in overview.text
    assert "Today Trades" in overview.text
    assert "BUY" in overview.text
    assert "005930" in overview.text
    assert "x1" in overview.text
    assert "Daily Totals" in overview.text
    assert "Broker Reconciliation" in overview.text
    assert "Strategist Summary" in overview.text
    assert "strategist prompt" in overview.text
    assert "defensive" in overview.text

    runs = client.get("/runs")
    assert runs.status_code == 200
    assert "run-1" in runs.text
    assert "005930" in runs.text
    assert "AI Report Available" in runs.text
    assert "Simulation trade report" in runs.text
    assert "Open report" in runs.text
    assert "Lifecycle CLOSED" in runs.text
    assert "active elevated_vix" in runs.text
    assert "strong (100%)" in runs.text

    detail = client.get("/runs/run-1")
    assert detail.status_code == 200
    assert "운영자 브리프" in detail.text
    assert "stepfun/step-3.5-flash:free" in detail.text
    assert "전략가는 뉴스와 글로벌 감성을 읽고 defensive 프레임을 만들었습니다." in detail.text
    assert "현재 판단" in detail.text
    assert "판단 근거" in detail.text
    assert "Universe scanned: 5" in detail.text
    assert "Selected rank: #1" in detail.text
    assert "Market regime:" in detail.text
    assert "Global sentiment: -0.20" in detail.text
    assert "AI Report Status" in detail.text
    assert "AI Report Available" in detail.text
    assert "grade=A-" in detail.text
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
    assert "AI 리포트" in detail.text
    assert "Scanner rank #1 with robust chart coverage and approved execution." in detail.text
    assert "Open full report" in detail.text
    assert "Trade ID:" in detail.text
    assert "Lifecycle:" in detail.text

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
    assert "brief=repaired" in detail.text
    assert "repair 경로가 동작했습니다." in detail.text


def test_operator_ui_run_detail_uses_line_repair_for_free_model(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _LineRepairRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    app = create_app(_make_config(tmp_path))
    client = TestClient(app)

    detail = client.get("/runs/run-1")
    assert detail.status_code == 200
    assert "brief=line_repaired" in detail.text
    assert "line repair 동작" in detail.text


def test_operator_brief_input_prefers_canonical_trade_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)
    detail = data_access.load_run_detail(cfg, "run-1")
    detail["strategist"] = {"summary": {}, "evidence": {}, "llm": {}, "decision_trace": {}}
    detail["scanner"] = {"summary": {}, "decision_trace": {}, "feature_coverage": {}, "quote_metrics": {}}
    detail["monitor"] = {"summary": {}, "decision_trace": {}}
    detail["supervisor"] = {"verdict": {}}
    detail["executor"] = {"execution": {}}
    detail["reporter"] = {}

    compact = data_access._build_operator_brief_input(detail)

    canonical = compact["canonical_trade"]
    assert canonical["available"] is True
    assert canonical["trade_id"] == "20260316_005930_buy_run-1"
    assert canonical["market_context_summary"] == "Market regime was neutral with elevated volatility and defensive posture."
    assert canonical["selection_summary"] == "Selected as top ranked symbol due to value/volume blend."
    assert canonical["monitor_summary"] == "Monitor allowed BUY because no position was open."
    assert canonical["reporter_summary"] == "Reporter linked and graded the run A-."
    assert compact["scanner"]["selected_reason"] == "Selected as top ranked symbol due to value/volume blend."
    assert compact["monitor"]["monitor_reason"] == "Monitor allowed BUY because no position was open."
    assert compact["reporter"]["ai_summary"] == "Reporter linked and graded the run A-."


def test_fallback_operator_brief_uses_canonical_trade_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)
    detail = data_access.load_run_detail(cfg, "run-1")
    detail["strategist"] = {"summary": {}, "evidence": {}, "llm": {}, "decision_trace": {}}
    detail["scanner"] = {"summary": {}, "decision_trace": {}, "feature_coverage": {}, "quote_metrics": {}}
    detail["monitor"] = {"summary": {}, "decision_trace": {}}
    detail["supervisor"] = {"verdict": {}}
    detail["executor"] = {"execution": {}}
    detail["reporter"] = {}

    brief = data_access._fallback_operator_brief(detail)

    assert brief["headline"] == "BUY 005930"
    assert "elevated volatility and defensive posture" in brief["strategist_summary"]
    assert "value/volume blend" in brief["scanner_summary"]
    assert "simulation mode" in brief["executor_summary"]
    assert "A-" in brief["reporter_summary"]


def test_operator_brief_sections_prefer_canonical_trade_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)
    detail = data_access.load_run_detail(cfg, "run-1")
    detail["strategist"] = {"summary": {}, "evidence": {}, "llm": {}, "decision_trace": {}}
    detail["scanner"] = {"summary": {}, "decision_trace": {}, "feature_coverage": {}, "quote_metrics": {}}
    detail["monitor"] = {"summary": {}, "decision_trace": {}}
    detail["supervisor"] = {"verdict": {}}
    detail["executor"] = {"execution": {}}
    detail["reporter"] = {}

    sections = data_access._build_operator_brief_sections(detail)

    assert sections["executive_decision"]["reason"] == "Scanner rank #1 with robust chart coverage and approved execution."
    assert sections["market_context"]["market_regime"] == "neutral"
    assert sections["market_context"]["global_sentiment"] == "-0.20"
    assert sections["market_context"]["vix"] == "24.50"
    assert sections["why_symbol_chosen"]["selected_rank"] == 1
    assert sections["why_symbol_chosen"]["universe_size"] == 5
    assert "Selected as top ranked symbol due to value/volume blend." in sections["why_symbol_chosen"]["selection_reasons"]
    assert sections["filters_and_gates"][0]["status"] == "PASS"
    assert sections["position_monitor_reasoning"]["hold_reasons"][0] == "Posture: BUY"
    assert sections["reporter_evaluation"]["run_grade"] == "A-"
    assert sections["reporter_evaluation"]["key_finding"] == "Reporter linked and graded the run A-."


def test_operator_ui_overview_does_not_fallback_to_stale_reporter_for_latest_day(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    cfg = _make_config(tmp_path)
    (cfg.reports_root / "dev" / "analysis" / "reporter_analysis" / "reporter_analysis_2026-03-16.json").unlink()
    (cfg.reports_root / "operator_summary" / "operator_summary_2026-03-16.json").unlink()
    app = create_app(cfg)
    client = TestClient(app)

    overview = client.get("/")
    assert overview.status_code == 200
    assert "2026-03-16" in overview.text
    assert "Today reporter summary" not in overview.text
    assert "Reporter summary" not in overview.text
    assert "Same-day reporter analysis has not been generated yet." in overview.text
    assert "live event log fallback active for 2026-03-16" in overview.text


def test_operator_ui_run_detail_explains_missing_reporter_linkage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    cfg = _make_config(tmp_path)
    (cfg.reports_root / "dev" / "analysis" / "reporter_analysis" / "reporter_analysis_2026-03-16.json").unlink()
    app = create_app(cfg)
    client = TestClient(app)

    detail = client.get("/runs/run-1")
    assert detail.status_code == 200
    assert "status=pending" in detail.text
    assert "same-day reporter analysis file is not generated yet" in detail.text
    assert "found=False" not in detail.text


def test_operator_ui_trade_report_detail_page(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    app = create_app(_make_config(tmp_path))
    client = TestClient(app)

    page = client.get("/reports/trade/20260316_005930_buy_run-1")
    assert page.status_code == 200
    assert "Per-trade report" in page.text
    assert "Executive Summary" in page.text
    assert "Market Context" in page.text
    assert "Why This Symbol" in page.text
    assert "Scanner Logic and Filters" in page.text
    assert "Holding / Monitoring Story" in page.text
    assert "Entry Decision" in page.text
    assert "Exit Decision" in page.text
    assert "Guard / Approval Result" in page.text
    assert "Execution Quality" in page.text
    assert "Reporter Evaluation" in page.text
    assert "Errors / Weaknesses / Improvement Points" in page.text
    assert "Final Operator Conclusion" in page.text
    assert "Simulation trade report" in page.text
    assert "Lifecycle CLOSED" in page.text
    assert "AI Report Available" in page.text


def test_operator_ui_run_detail_explains_missing_trade_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    cfg = _make_config(tmp_path)
    trade_root = cfg.reports_root / "trades"
    if trade_root.exists():
        for path in sorted(trade_root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    app = create_app(cfg)
    client = TestClient(app)

    runs = client.get("/runs")
    assert runs.status_code == 200
    assert "AI Report Failed" in runs.text

    detail = client.get("/runs/run-1")
    assert detail.status_code == 200
    assert "AI Report Failed" in detail.text
    assert "A linked AI trade report could not be found for this run." in detail.text


def test_operator_ui_shows_pending_ai_report_status_for_open_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    cfg = _make_config(tmp_path)
    trade_root = cfg.reports_root / "trades" / "2026" / "03" / "20260316_005930_buy_run-1"
    bundle_path = trade_root / "aggregated_execution_bundle.json"
    lifecycle_path = trade_root / "trade_lifecycle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    lifecycle = json.loads(lifecycle_path.read_text(encoding="utf-8"))
    diagnostics = {
        "report_status": "pending",
        "report_reason_code": "awaiting_exit_for_full_report",
        "report_reason_human": "This trade is still open. The full AI report is generated after exit/closure.",
        "next_expected_step": "Generate the final AI report after exit/closure.",
        "generation_attempted": False,
        "story_input_available": True,
        "report_output_available": False,
        "llm_provider": "OpenRouter",
        "llm_model_used": "openrouter/free",
        "expected_generation_mode": "per-trade free model report",
    }
    bundle["trade_lifecycle_status"] = "open"
    bundle["ai_report_diagnostics"] = diagnostics
    lifecycle["status"] = "open"
    lifecycle["ai_report_diagnostics"] = diagnostics
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    lifecycle_path.write_text(json.dumps(lifecycle, ensure_ascii=False, indent=2), encoding="utf-8")
    report_json = trade_root / "trade_report.json"
    report_md = trade_root / "trade_report.md"
    if report_json.exists():
        report_json.unlink()
    if report_md.exists():
        report_md.unlink()

    app = create_app(cfg)
    client = TestClient(app)
    runs = client.get("/runs")
    assert runs.status_code == 200
    assert "AI Report Pending" in runs.text

    detail = client.get("/runs/run-1")
    assert detail.status_code == 200
    assert "AI Report Pending" in detail.text
    assert "full AI report is generated after exit/closure" in detail.text


def test_operator_ui_shows_skipped_status_for_hold_only_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    cfg = _make_config(tmp_path)
    with cfg.event_log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": "run-hold", "ts": "2026-03-16T00:30:00+00:00", "stage": "commander_router", "event": "route", "payload": {"mode": "integrated_chain", "phase": "session", "agents": ["strategist", "scanner", "monitor"]}}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"run_id": "run-hold", "ts": "2026-03-16T00:30:01+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "hold_position", "exit_reason": "hold"}}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"run_id": "run-hold", "ts": "2026-03-16T00:30:02+00:00", "stage": "commander_router", "event": "end", "payload": {"status": "ok", "path": "integrated_chain"}}, ensure_ascii=False) + "\n")

    app = create_app(cfg)
    client = TestClient(app)
    runs = client.get("/runs")
    assert runs.status_code == 200
    assert "run-hold" in runs.text
    assert "AI Report Skipped" in runs.text

    detail = client.get("/runs/run-hold")
    assert detail.status_code == 200
    assert "운영자 브리프" in detail.text
    assert "AI Report Skipped" in detail.text
    assert "only updated hold/monitor state" in detail.text
