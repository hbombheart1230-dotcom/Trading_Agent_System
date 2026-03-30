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
                "executive_summary": "삼성전자(005930) 후보 감시 후 진입이 승인되어 현재 보유 상태로 관리 중입니다.",
                "commander_summary": "지휘자는 integrated_chain 세션을 실행했습니다.",
                "strategist_summary": f"전략가는 뉴스와 글로벌 감성을 읽고 defensive 프레임을 만들었습니다. model={model}",
                "scanner_summary": "스캐너는 Kiwoom 후보 중 005930을 1등으로 골랐습니다.",
                "scanner_reason": "후보 5개 중 1위로 선정됐고, 거래대금과 추세 점수가 가장 안정적으로 결합됐습니다.",
                "monitor_summary": "모니터는 분봉 조건을 확인하며 현재 보유 상태를 관리하고 있습니다.",
                "entry_summary": "3분봉 기준 전고점 돌파와 VWAP 상회 유지, 거래량 증가가 확인되어 진입했습니다.",
                "holding_summary": "현재 포지션은 보유 유지 상태이며, 가격 흐름은 VWAP 위에서 관리되고 있습니다.",
                "exit_plan_summary": "VWAP 이탈이나 직전 저점 훼손이 나오면 청산을 우선 검토합니다.",
                "risk_summary": "거시 변동성이 남아 있어 추격 매수 재발은 경계해야 합니다.",
                "supervisor_summary": "감독관은 주문을 허용했습니다.",
                "executor_summary": "수행자는 BUY 005930 1주를 실행했습니다.",
                "reporter_summary": "리포터는 오늘 run을 정상으로 요약했습니다.",
                "next_checkpoints": ["VWAP 유지 여부", "직전 저점 방어 여부"],
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
                "executive_summary": "복구 경로에서도 삼성전자(005930) 보유 판단을 이어갑니다.",
                "commander_summary": "지휘자는 integrated_chain 세션을 실행했습니다.",
                "strategist_summary": "전략가는 뉴스와 글로벌 감성을 읽었습니다.",
                "scanner_summary": "스캐너는 Kiwoom 후보 중 005930을 골랐습니다.",
                "scanner_reason": "후보 중 점수와 유동성이 가장 안정적이었습니다.",
                "monitor_summary": "모니터는 현재 보유 상태를 기준으로 감시 중입니다.",
                "entry_summary": "분봉 조건을 확인한 뒤 진입했습니다.",
                "holding_summary": "현재 포지션은 보유 상태입니다.",
                "exit_plan_summary": "VWAP 이탈 시 청산을 검토합니다.",
                "risk_summary": "단기 변동성 확대는 주의가 필요합니다.",
                "supervisor_summary": "감독관은 주문을 허용했습니다.",
                "executor_summary": "수행자는 BUY 005930 1주를 실행했습니다.",
                "reporter_summary": "리포터는 정상 run으로 평가했습니다.",
                "next_checkpoints": ["VWAP 유지 여부"],
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
            "executive_summary: 삼성전자 보유 판단 요약입니다.\n"
            "scanner_reason: 후보 중 1위였습니다.\n"
            "entry_summary: 분봉 돌파가 확인되어 진입했습니다.\n"
            "holding_summary: 현재 보유 상태입니다.\n"
            "exit_plan_summary: VWAP 이탈 시 청산합니다.\n"
            "risk_summary: 변동성 확대 주의가 필요합니다.\n"
            "next_checkpoints: VWAP 유지 | 직전 저점 방어\n"
            "operator_takeaways: line repair 동작 | 무료 모델 경로 복구\n"
        )


class _AlwaysEmptyRouter:
    def __init__(self) -> None:
        self.client = object()

    def chat(self, role: str, messages: list[dict], *, policy: dict | None = None) -> str:
        return ""


class _TimeoutThenEmptyRouter:
    def __init__(self) -> None:
        self.client = object()
        self.calls = 0

    def chat(self, role: str, messages: list[dict], *, policy: dict | None = None) -> str:
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("operator brief timed out")
        return ""


class _CaptureBriefPolicyRouter:
    policies: list[dict] = []

    def __init__(self) -> None:
        self.client = object()

    def chat(self, role: str, messages: list[dict], *, policy: dict | None = None) -> str:
        _CaptureBriefPolicyRouter.policies.append(dict(policy or {}))
        model = (policy or {}).get("model") or ""
        return json.dumps(
            {
                "headline": "run-1 운영 요약",
                "executive_summary": "운영 요약입니다.",
                "commander_summary": "지휘자는 integrated_chain 세션을 실행했습니다.",
                "strategist_summary": f"전략가는 뉴스와 글로벌 감성을 읽고 defensive 프레임을 만들었습니다. model={model}",
                "scanner_summary": "스캐너는 Kiwoom 후보 중 005930을 1등으로 골랐습니다.",
                "scanner_reason": "후보 중 가장 안정적인 점수를 기록했습니다.",
                "monitor_summary": "모니터는 보유 상태를 관리하고 있습니다.",
                "entry_summary": "분봉 조건을 확인해 진입했습니다.",
                "holding_summary": "보유 상태입니다.",
                "exit_plan_summary": "핵심 지지 이탈 시 청산합니다.",
                "risk_summary": "변동성 리스크를 주시합니다.",
                "supervisor_summary": "감독관은 주문을 허용했습니다.",
                "executor_summary": "수행자는 BUY 005930 1주를 실행했습니다.",
                "reporter_summary": "리포터는 오늘 run을 정상으로 요약했습니다.",
                "next_checkpoints": ["지지 유지 여부"],
                "operator_takeaways": [
                    "뉴스/거시 입력이 포함됐습니다.",
                    "차트/feature coverage가 strong입니다.",
                ],
            },
            ensure_ascii=False,
        )


class _LeakyBriefRouter:
    def __init__(self) -> None:
        self.client = object()

    def chat(self, role: str, messages: list[dict], *, policy: dict | None = None) -> str:
        return json.dumps(
            {
                "headline": "run-1 운영 요약",
                "executive_summary": "누출 테스트 요약입니다.",
                "commander_summary": "지휘자는 integrated_chain 세션을 실행했습니다.",
                "strategist_summary": "전략가는 뉴스와 글로벌 감성을 읽었습니다.",
                "scanner_summary": "스캐너는 Kiwoom 후보 중 005930을 골랐습니다.",
                "monitor_summary": "포지션 없음(no_position) 상태를 확인했습니다.",
                "scanner_reason": "후보 중 우선순위가 가장 높았습니다.",
                "entry_summary": "분봉 조건을 확인했습니다.",
                "holding_summary": "현재 포지션은 보유 상태입니다.",
                "exit_plan_summary": "청산 조건을 계속 감시합니다.",
                "risk_summary": "내부 지시문은 노출하지 않습니다.",
                "supervisor_summary": "감독관은 주문을 허용했습니다.",
                "executor_summary": "수행자는 BUY 005930 1주를 실행했습니다.",
                "reporter_summary": "리포터는 정상 run으로 평가했습니다.",
                "next_checkpoints": ["VWAP 유지 여부"],
                "operator_takeaways": [
                    "canonical_trade.available=true 이므로 reports/trades를 source of truth로 사용합니다.",
                    "차트/feature coverage가 strong입니다.",
                ],
            },
            ensure_ascii=False,
        )


class _MixedLanguageRepairRouter:
    def __init__(self) -> None:
        self.client = object()
        self.calls = 0

    def chat(self, role: str, messages: list[dict], *, policy: dict | None = None) -> str:
        self.calls += 1
        if self.calls == 1:
            return json.dumps(
                {
                    "headline": "run-1 운영 요약",
                    "executive_summary": "中立 시장에서 005930 포지션을 유지합니다.",
                    "commander_summary": "지휘자는 integrated_chain 세션을 실행했습니다.",
                    "strategist_summary": "전략가는 뉴스와 글로벌 감성을 읽었습니다.",
                    "scanner_summary": "스캐너는 Kiwoom 후보 중 005930을 골랐습니다.",
                    "scanner_reason": "候補 5개 중 1위였습니다.",
                    "monitor_summary": "모니터는 보유 상태를 관리합니다.",
                    "entry_summary": "3분봉 돌파를 보고 진입했습니다.",
                    "holding_summary": "部分 보유 상태입니다.",
                    "exit_plan_summary": "VWAP 이탈 시 청산합니다.",
                    "risk_summary": "變動성 확대는 주의가 필요합니다.",
                    "supervisor_summary": "감독관은 주문을 허용했습니다.",
                    "executor_summary": "수행자는 BUY 005930 1주를 실행했습니다.",
                    "reporter_summary": "리포터는 정상 run으로 평가했습니다.",
                    "next_checkpoints": ["VWAP 유지 여부"],
                    "operator_takeaways": ["시장 심리는 아직 중립입니다."],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "headline": "run-1 운영 요약",
                "executive_summary": "중립 시장에서 005930 보유 전략을 유지합니다.",
                "commander_summary": "지휘자는 integrated_chain 세션을 실행했습니다.",
                "strategist_summary": "전략가는 뉴스와 글로벌 감성을 읽었습니다.",
                "scanner_summary": "스캐너는 Kiwoom 후보 중 005930을 골랐습니다.",
                "scanner_reason": "후보 5개 중 1위였고, 거래대금과 추세 점수가 가장 안정적이었습니다.",
                "monitor_summary": "모니터는 보유 상태를 관리하고 있습니다.",
                "entry_summary": "3분봉 돌파와 VWAP 상회 유지가 확인되어 진입했습니다.",
                "holding_summary": "현재 포지션은 보유 상태이며 가격 흐름을 계속 점검 중입니다.",
                "exit_plan_summary": "VWAP 이탈이나 직전 저점 훼손 시 청산합니다.",
                "risk_summary": "단기 변동성 확대와 거래대금 둔화는 계속 주의해야 합니다.",
                "supervisor_summary": "감독관은 주문을 허용했습니다.",
                "executor_summary": "수행자는 BUY 005930 1주를 실행했습니다.",
                "reporter_summary": "리포터는 정상 run으로 평가했습니다.",
                "next_checkpoints": ["VWAP 유지 여부", "직전 저점 방어 여부"],
                "operator_takeaways": ["시장 심리는 아직 중립이지만 변동성은 확인이 필요합니다."],
            },
            ensure_ascii=False,
        )


class _AlwaysMixedLanguageRouter:
    def __init__(self) -> None:
        self.client = object()

    def chat(self, role: str, messages: list[dict], *, policy: dict | None = None) -> str:
        return json.dumps(
            {
                "headline": "run-1 운영 요약",
                "executive_summary": "中立 시장에서 005930 포지션을 유지합니다.",
                "commander_summary": "지휘자는 integrated_chain 세션을 실행했습니다.",
                "strategist_summary": "전략가는 뉴스와 글로벌 감성을 읽었습니다.",
                "scanner_summary": "스캐너는 Kiwoom 후보 중 005930을 골랐습니다.",
                "scanner_reason": "候補 5개 중 1위였습니다.",
                "monitor_summary": "모니터는 보유 상태를 관리합니다.",
                "entry_summary": "3分봉 돌파를 보고 진입했습니다.",
                "holding_summary": "部分 보유 상태입니다.",
                "exit_plan_summary": "VWAP 이탈 시 청산합니다.",
                "risk_summary": "變動성 확대는 주의가 필요합니다.",
                "supervisor_summary": "감독관은 주문을 허용했습니다.",
                "executor_summary": "수행자는 BUY 005930 1주를 실행했습니다.",
                "reporter_summary": "리포터는 정상 run으로 평가했습니다.",
                "next_checkpoints": ["VWAP 유지 여부"],
                "operator_takeaways": ["시장 심리는 아직 중립입니다."],
            },
            ensure_ascii=False,
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
            {"run_id": "run-1", "ts": "2026-03-16T00:00:08+00:00", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": True, "reason": "Allowed", "portfolio_guard": {"reader_ok": True, "positions_source": "reader_positions_authoritative_empty", "reconciliation_status": "reader_aligned", "reader_positions_authoritative": True, "positions_mismatch_detected": False, "reconciliation_applied": False, "reader_positions_count": 0, "persisted_positions_count": 0}}},
            {"run_id": "run-1", "ts": "2026-03-16T00:00:09+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"allowed": True, "order": {"action": "BUY", "symbol": "005930", "qty": 1, "ord_qty": "1"}, "portfolio_guard": {"reader_ok": True, "positions_source": "reader_positions_authoritative_empty", "reconciliation_status": "reader_aligned", "reader_positions_authoritative": True, "positions_mismatch_detected": False, "reconciliation_applied": False, "reader_positions_count": 0, "persisted_positions_count": 0}, "payload": {"order_id": "A0001", "broker_message": "EXECUTED_OK", "response_payload": {"ord_no": "A0001", "return_msg": "EXECUTED_OK"}}}},
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
            "shared_facts": {
                "action": "BUY",
                "status": "closed",
                "holding_duration": "10m",
                "exit_reason": "simulated closeout",
                "pnl": "unavailable",
                "pnl_pct": "unavailable",
                "data_source": {
                    "action": "lifecycle",
                    "status": "lifecycle",
                    "holding_duration": "lifecycle",
                    "exit_reason": "lifecycle",
                    "pnl": "unavailable",
                    "pnl_pct": "unavailable",
                },
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
    assert "Portfolio Sync" in overview.text
    assert "Portfolio Sync OK" in overview.text
    assert "1 aligned" in overview.text
    assert "0 reconciled" in overview.text
    assert "0 alerts" in overview.text
    assert "Today Trades" in overview.text
    assert "BUY" in overview.text
    assert "005930" in overview.text
    assert "x1" in overview.text
    assert "axis No position" in overview.text
    assert "stop -" in overview.text
    assert "Daily Totals" in overview.text
    assert "Broker Reconciliation" in overview.text
    assert "Strategist Summary" in overview.text
    assert "strategist prompt" in overview.text
    assert "defensive" in overview.text


def test_operator_ui_overview_prefers_live_intraday_counts_over_stale_reports(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    cfg = _make_config(tmp_path)

    events_path = cfg.event_log_path
    rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows.extend(
        [
            {"run_id": "run-2", "ts": "2026-03-16T00:10:00+00:00", "stage": "commander_router", "event": "route", "payload": {"mode": "integrated_chain", "phase": "session", "agents": ["monitor", "executor"]}},
            {"run_id": "run-2", "ts": "2026-03-16T00:10:01+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "peak_drawdown", "exit_reason": "peak_drawdown", "selected_symbol": "005930"}},
            {"run_id": "run-2", "ts": "2026-03-16T00:10:02+00:00", "stage": "decision_trace", "event": "entry_exit_decision", "payload": {"agent": "monitor", "payload": {"selected_symbol": "005930", "entry_reason": "peak_drawdown", "exit_reason": "peak_drawdown", "thresholds": {"effective_stop_loss_pct": 0.01, "effective_stop_reason": "hard_stop"}}}},
            {"run_id": "run-2", "ts": "2026-03-16T00:10:03+00:00", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": True, "reason": "Allowed"}},
            {"run_id": "run-2", "ts": "2026-03-16T00:10:04+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"allowed": True, "order": {"action": "SELL", "symbol": "005930", "qty": 1, "ord_qty": "1"}, "payload": {"order_id": "A0002", "broker_message": "EXECUTED_OK", "response_payload": {"ord_no": "A0002", "return_msg": "EXECUTED_OK"}}}},
            {"run_id": "run-2", "ts": "2026-03-16T00:10:05+00:00", "stage": "commander_router", "event": "end", "payload": {"status": "ok", "path": "integrated_chain_monitor_only"}},
            {"run_id": "run-3", "ts": "2026-03-16T00:11:00+00:00", "stage": "commander_router", "event": "route", "payload": {"mode": "integrated_chain", "phase": "session", "agents": ["monitor", "executor"]}},
            {"run_id": "run-3", "ts": "2026-03-16T00:11:01+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "no_position", "exit_reason": "no_position", "selected_symbol": "000660"}},
            {"run_id": "run-3", "ts": "2026-03-16T00:11:02+00:00", "stage": "decision_trace", "event": "entry_exit_decision", "payload": {"agent": "monitor", "payload": {"selected_symbol": "000660", "entry_reason": "no_position", "exit_reason": "no_position", "thresholds": {}}}},
            {"run_id": "run-3", "ts": "2026-03-16T00:11:03+00:00", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": True, "reason": "Allowed"}},
            {"run_id": "run-3", "ts": "2026-03-16T00:11:04+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"allowed": True, "order": {"action": "BUY", "symbol": "000660", "qty": 1, "ord_qty": "1"}, "payload": {"order_id": "A0003", "broker_message": "EXECUTED_OK", "response_payload": {"ord_no": "A0003", "return_msg": "EXECUTED_OK"}}}},
            {"run_id": "run-3", "ts": "2026-03-16T00:11:05+00:00", "stage": "commander_router", "event": "end", "payload": {"status": "ok", "path": "integrated_chain_monitor_only"}},
        ]
    )
    _write_jsonl(events_path, rows)

    app = create_app(cfg)
    client = TestClient(app)

    overview = client.get("/")
    assert overview.status_code == 200
    assert "3 executions today." in overview.text
    assert "Approved today: 3" in overview.text
    assert "BUY 2" in overview.text
    assert "SELL 1" in overview.text
    assert "Intraday reconciliation has not been generated yet." in overview.text
    assert "Portfolio Sync OK" in overview.text
    assert "Sync status unavailable" not in overview.text
    assert "snapshot" in overview.text
    assert "000660" in overview.text

    runs = client.get("/runs")
    assert runs.status_code == 200
    assert "run-1" in runs.text
    assert "005930" in runs.text
    assert "AI Report Available" in runs.text
    assert "Simulation trade report" in runs.text
    assert "Open report" in runs.text
    assert "Open brief" in runs.text
    assert "Lifecycle CLOSED" in runs.text
    assert "Portfolio Sync OK" in runs.text
    assert "axis: No position" in runs.text
    assert "stop: -" in runs.text
    assert "Mismatch only" in runs.text
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
    assert "계좌 동기화" in detail.text
    assert "Portfolio Sync OK" in detail.text
    assert "계좌 보유 종목과 로컬 상태가 일치했습니다." in detail.text
    assert "AI Report Available" in detail.text
    assert "grade=A-" in detail.text
    assert "strategist prompt" in detail.text
    assert "EXECUTED_OK" in detail.text
    assert "Feature Coverage" in detail.text
    assert "Quote Metrics" in detail.text
    assert "price=70500" in detail.text
    assert "2.15" in detail.text
    assert "Same-Day Symbol Trade History" in detail.text
    assert "trade_count=2" in detail.text
    assert "Recent Same-Symbol Run Chain" in detail.text
    assert "run_count=2" in detail.text
    assert "AI 리포트" in detail.text
    assert "Scanner rank #1 with robust chart coverage and approved execution." in detail.text
    assert "Open full report" in detail.text
    assert "Open saved brief" in detail.text
    assert "Trade ID:" in detail.text
    assert "Lifecycle:" in detail.text

    health = client.get("/healthz")
    assert health.status_code == 200
    obj = health.json()
    assert obj["status"] == "ok"
    assert obj["system_status"] == "GREEN"
    assert obj["latest_day"] == "2026-03-16"


def test_operator_ui_runs_support_trade_and_monitoring_filters(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    cfg = _make_config(tmp_path)
    events_path = cfg.event_log_path
    rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows.extend(
        [
            {"run_id": "run-monitor", "ts": "2026-03-16T00:12:00+00:00", "stage": "commander_router", "event": "route", "payload": {"mode": "integrated_chain", "phase": "session", "agents": ["monitor", "executor"]}},
            {"run_id": "run-monitor", "ts": "2026-03-16T00:12:01+00:00", "stage": "commander_router", "event": "fast_path", "payload": {"path": "integrated_chain_monitor_only", "enabled": True, "open_position_count": 1}},
            {"run_id": "run-monitor", "ts": "2026-03-16T00:12:02+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "hold", "exit_reason": "hold", "selected_symbol": "005930"}},
            {"run_id": "run-monitor", "ts": "2026-03-16T00:12:03+00:00", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": False, "reason": "noop_intent_skipped"}},
            {"run_id": "run-monitor", "ts": "2026-03-16T00:12:04+00:00", "stage": "commander_router", "event": "end", "payload": {"status": "ok", "path": "integrated_chain_monitor_only"}},
        ]
    )
    _write_jsonl(events_path, rows)

    app = create_app(cfg)
    client = TestClient(app)

    all_runs = client.get("/runs")
    assert all_runs.status_code == 200
    assert "Trades" in all_runs.text
    assert "Monitoring" in all_runs.text

    trades = client.get("/runs?activity_view=trades")
    assert trades.status_code == 200
    assert "run-1" in trades.text
    assert "run-monitor" not in trades.text
    assert "Trade" in trades.text

    monitoring = client.get("/runs?activity_view=monitoring")
    assert monitoring.status_code == 200
    assert "run-monitor" in monitoring.text
    assert "run-1" not in monitoring.text
    assert "Monitoring" in monitoring.text
    assert "integrated_chain_monitor_only" in monitoring.text


def test_operator_ui_trades_filter_looks_across_latest_day_not_just_latest_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    cfg = _make_config(tmp_path)
    events_path = cfg.event_log_path
    rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows.extend(
        [
            {"run_id": "run-trade", "ts": "2026-03-16T00:05:00+00:00", "stage": "commander_router", "event": "route", "payload": {"mode": "integrated_chain", "phase": "session", "agents": ["monitor", "executor"]}},
            {"run_id": "run-trade", "ts": "2026-03-16T00:05:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"allowed": True, "order": {"action": "BUY", "symbol": "000660", "qty": 1, "ord_qty": "1"}, "payload": {"order_id": "A0004", "broker_message": "EXECUTED_OK", "response_payload": {"ord_no": "A0004", "return_msg": "EXECUTED_OK"}}}},
        ]
    )
    for idx in range(60):
        rid = f"run-monitor-{idx:02d}"
        minute = 10 + idx
        rows.extend(
            [
                {"run_id": rid, "ts": f"2026-03-16T01:{minute:02d}:00+00:00", "stage": "commander_router", "event": "route", "payload": {"mode": "integrated_chain", "phase": "session", "agents": ["monitor", "executor"]}},
                {"run_id": rid, "ts": f"2026-03-16T01:{minute:02d}:01+00:00", "stage": "commander_router", "event": "fast_path", "payload": {"path": "integrated_chain_monitor_only", "enabled": True, "open_position_count": 1}},
                {"run_id": rid, "ts": f"2026-03-16T01:{minute:02d}:02+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "hold", "exit_reason": "hold", "selected_symbol": "005930"}},
                {"run_id": rid, "ts": f"2026-03-16T01:{minute:02d}:03+00:00", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": False, "reason": "noop_intent_skipped"}},
                {"run_id": rid, "ts": f"2026-03-16T01:{minute:02d}:04+00:00", "stage": "commander_router", "event": "end", "payload": {"status": "ok", "path": "integrated_chain_monitor_only"}},
            ]
        )
    _write_jsonl(events_path, rows)

    app = create_app(cfg)
    client = TestClient(app)

    trades = client.get("/runs?activity_view=trades&limit=10")
    assert trades.status_code == 200
    assert "run-trade" in trades.text
    assert "BUY EXECUTED_OK" in trades.text


def test_operator_ui_run_detail_repairs_non_json_llm_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _RepairRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    app = create_app(_make_config(tmp_path))
    client = TestClient(app)

    detail = client.get("/runs/run-1")
    assert detail.status_code == 200
    assert "brief=repaired" in detail.text
    assert "brief=fallback" not in detail.text


def test_operator_ui_run_detail_uses_line_repair_for_free_model(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _LineRepairRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    app = create_app(_make_config(tmp_path))
    client = TestClient(app)

    detail = client.get("/runs/run-1")
    assert detail.status_code == 200
    assert "brief=salvaged" in detail.text
    assert "brief=fallback" not in detail.text


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

    llm_compact = data_access._compact_operator_brief_input_for_llm(compact)
    assert llm_compact["strategist"]["canonical_summary"] == ""
    assert llm_compact["scanner"]["canonical_bullets"] == []
    assert llm_compact["compact_kr_facts"]["strategist"]
    assert "Market regime was neutral" not in json.dumps(llm_compact["strategist"], ensure_ascii=False)
    assert "Scanner selected the highest-ranked candidate" not in json.dumps(llm_compact["scanner"], ensure_ascii=False)


def test_operator_brief_shared_facts_match_ai_trade_report_core_facts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)
    detail = data_access.load_run_detail(cfg, "run-1")

    brief = detail.get("operator_brief") if isinstance(detail.get("operator_brief"), dict) else {}
    brief_facts = brief.get("shared_facts") if isinstance(brief.get("shared_facts"), dict) else {}
    report_data = (detail.get("trade_report") or {}).get("report_data") if isinstance(detail.get("trade_report"), dict) else {}
    ai_facts = report_data.get("shared_facts") if isinstance(report_data, dict) and isinstance(report_data.get("shared_facts"), dict) else {}

    assert brief_facts.get("action") == ai_facts.get("action")
    assert brief_facts.get("holding_duration") == ai_facts.get("holding_duration")
    assert brief_facts.get("exit_reason") == ai_facts.get("exit_reason")
    assert isinstance(brief_facts.get("data_source"), dict)


def test_operator_brief_shared_facts_use_lifecycle_precedence_when_report_shared_facts_missing() -> None:
    trade_report = {
        "story_input_data": {
            "action": "BUY",
            "status": "closed",
            "entry_summary": {"action": "BUY"},
            "exit_summary": {"action": "BUY", "reason_human": "entry_side_reason"},
            "canonical_agent_artifacts": {
                "monitor": {
                    "decision_action": "sell",
                    "decision_status": "ok",
                    "primary_reason_text": "monitor_exit_reason",
                }
            },
        },
        "lifecycle_data": {
            "status": "closed",
            "action": "SELL",
            "summary": {
                "holding_duration": "00:31:00",
                "exit_reason_human": "lifecycle_exit_reason",
            },
        },
        "report_data": {},
    }

    canonical = data_access._build_canonical_trade_brief_input(trade_report)
    facts = canonical.get("shared_facts") if isinstance(canonical.get("shared_facts"), dict) else {}

    assert facts.get("action") == "SELL"
    assert facts.get("holding_duration") == "00:31:00"
    assert facts.get("exit_reason") == "lifecycle_exit_reason"
    assert (facts.get("data_source") or {}).get("action") == "lifecycle"


def test_operator_brief_shared_facts_mark_unavailable_when_inputs_missing() -> None:
    canonical = data_access._build_canonical_trade_brief_input({})
    facts = canonical.get("shared_facts") if isinstance(canonical.get("shared_facts"), dict) else {}

    assert facts.get("action") == "unavailable"
    assert facts.get("status") == "unavailable"
    assert facts.get("holding_duration") == "unavailable"
    assert facts.get("exit_reason") == "unavailable"


def test_operator_brief_input_surfaces_route_and_monitor_blockers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)
    detail = data_access.load_run_detail(cfg, "run-1")
    detail["strategist"]["artifact"] = {
        "candidate_symbols_hint": ["122630", "233740", "005930"],
        "news_evidence_ranked": {
            "market_news_ranked": [
                {"title": "KOSPI opens firmer on chip optimism."},
                {"title": "US futures steady ahead of macro prints."},
            ],
            "candidate_news_ranked": [
                {"symbol": "000660", "title": "000660 extends gains on AI memory demand."},
                {"symbol": "000660", "title": "Foreign flows return to semiconductor leaders."},
            ],
        },
    }
    detail["commander"]["artifact"] = {
        "commander_decision": {
            "command_intent": "OBSERVE_ONLY",
            "strategist_invocation": "SKIP",
            "llm_policy": "SKIP",
        },
        "selected_route": "cached_strategist",
        "route_reason_text": "commander_skip_cached_strategist",
        "strategist_cache_used": True,
        "strategist_called": False,
        "cooldown_applied": False,
        "applied_policy": {
            "timeframe_minutes": 1,
            "volume_ratio_min": 0.68,
            "pullback_min_pct": 0.008,
        },
        "policy_source": "strategist",
        "policy_validation_status": "ok",
        "policy_fallback_used": False,
        "policy_fallback_reason": "",
        "policy_partial_normalized": True,
        "policy_default_filled_fields": ["enabled"],
        "policy_validation_missing_fields": ["enabled"],
        "policy_validation_invalid_fields": [],
        "override_reason": "",
        "applied_policy_source_chain": ["strategist", "validation", "commander_confirmed"],
    }
    detail["scanner"]["artifact"] = {
        "score_breakdown_by_symbol": {
            "000660": {
                "trading_value": 0.22,
                "momentum": 0.19,
                "trend": 0.17,
            }
        }
    }
    detail["monitor"]["summary"] = {
        "monitor_reason": "reclaim_not_confirmed",
        "entry_metrics": {
            "volume_ratio": 0.10,
            "extended_from_vwap_pct": 0.19,
            "pullback_depth_pct": 0.00,
        },
        "entry_thresholds": {
            "volume_ratio_min": 0.75,
            "max_extended_from_vwap_pct": 0.05,
            "pullback_min_pct": 0.012,
        },
    }
    detail["monitor"]["decision_trace"] = {
        "entry_check_summary": "mission=wait_for_confirmation | reason=reclaim_not_confirmed",
        "entry_blockers": ["volume_ok", "vwap_reclaim_ok"],
        "policy_ref": {
            "monitor_mission": "Wait for cleaner reclaim confirmation.",
            "flow_instruction": "observe_only",
            "policy_source": "strategist",
            "policy_validation_status": "ok",
            "policy_fallback_used": False,
        },
        "timing_assessment": {
            "entry_reason": "reclaim_not_confirmed",
            "entry_pattern": "pullback_reclaim",
        },
        "thresholds_guards_used": {
            "thresholds": {
                "volume_ratio_min": 0.75,
                "max_extended_from_vwap_pct": 0.05,
                "pullback_min_pct": 0.012,
            }
        },
        "applied_policy": {
            "timeframe_minutes": 1,
            "volume_ratio_min": 0.68,
            "pullback_min_pct": 0.008,
        },
        "received_policy": {
            "timeframe_minutes": 1,
            "volume_ratio_min": 0.68,
            "pullback_min_pct": 0.008,
            "max_extended_from_vwap_pct": 0.13,
        },
        "received_policy_source": "commander_applied_policy",
        "effective_policy": {
            "timeframe_minutes": 1,
            "volume_ratio_min": 0.75,
            "pullback_min_pct": 0.008,
            "max_extended_from_vwap_pct": 0.05,
        },
        "effective_policy_source": "monitor_frame_adjusted",
        "effective_policy_source_chain": ["commander_applied_policy", "strategy_frame_adjustment", "monitor_effective_policy"],
        "policy_adjustments": {
            "inputs": {
                "playbook": "defensive",
                "monitor_guidance": "defensive_exit",
                "risk_tone": "conservative",
                "trade_aggressiveness": "low",
            },
            "applied_rules": ["playbook:defensive"],
            "changed_fields": ["volume_ratio_min", "max_extended_from_vwap_pct"],
        },
        "policy_adjustment_summary": "defensive + conservative adjusted volume_ratio_min, max_extended_from_vwap_pct",
        "effective_policy_deltas": [
            {"field": "volume_ratio_min", "from": 0.68, "to": 0.75},
            {"field": "max_extended_from_vwap_pct", "from": 0.13, "to": 0.05},
        ],
        "policy_source": "strategist",
        "policy_validation_status": "ok",
        "policy_fallback_used": False,
        "policy_fallback_reason": "",
        "policy_partial_normalized": True,
        "policy_default_filled_fields": ["enabled"],
        "policy_validation_missing_fields": ["enabled"],
        "policy_validation_invalid_fields": [],
        "override_reason": "",
        "applied_policy_source_chain": ["strategist", "validation", "commander_confirmed"],
    }
    detail["monitor"]["artifact"] = {
        "hard_stop_pct": 0.03,
        "adaptive_exit": {"stop_loss_pct": 0.0092},
        "trailing_stop_pct": 0.012,
        "take_profit_pct": 0.025,
    }
    detail["scanner"]["decision_trace"] = {
        "selected_symbol": "000660",
        "playbook": "pullback",
        "policy_source": "strategist",
        "applied_policy_present": True,
        "monitor_entry_policy_summary": {
            "volume_ratio_min": 0.68,
            "pullback_min_pct": 0.008,
        },
        "scanner_bias_applied": True,
        "scanner_bias_summary": {
            "summary": "prefer_shallow_pullback_candidates, penalize_overextended (low)",
            "bias_strength": "low",
        },
        "candidate_bias_adjustments": [
            {
                "symbol": "000660",
                "bias_adjustment": 0.003,
                "bias_adjustments": [{"reason": "shallow pullback preference applied"}],
            }
        ],
        "selection_reason_with_bias": "selected with shallow pullback preference applied",
    }
    detail["trade_report"]["report_data"]["trade_story_input"] = {
        "strategist_candidate_hints": ["122630", "233740", "005930"],
        "strategist_market_headlines": [
            "KOSPI opens firmer on chip optimism.",
            "US futures steady ahead of macro prints.",
        ],
        "strategist_symbol_headlines": [
            "000660 extends gains on AI memory demand.",
            "Foreign flows return to semiconductor leaders.",
        ],
        "scanner_selection_trace": {
            "ranked_candidates": [
                {"rank": 1, "symbol": "000660", "score_total": 1.1776},
                {"rank": 2, "symbol": "005930", "score_total": 1.1519},
            ],
            "selected_symbol": "000660",
            "selected_rank": 1,
            "selection_reason": "top_value + sector_theme",
            "selected_symbol_score_drivers": {
                "trading_value": 0.22,
                "momentum": 0.19,
                "trend": 0.17,
            },
        },
        "monitor_stop_policy_trace": {
            "hard_stop_pct": 0.03,
            "adaptive_stop_loss_pct": 0.0092,
            "effective_stop_loss_pct": 0.0092,
            "trailing_stop_pct": 0.012,
            "take_profit_pct": 0.025,
        },
    }

    prepared = data_access._build_operator_brief_input(detail)
    compact = data_access._compact_operator_brief_input_for_llm(prepared)

    assert prepared["commander"]["selected_route"] == "cached_strategist"
    assert prepared["commander"]["strategist_called"] is False
    assert prepared["commander"]["policy_source"] == "strategist"
    assert prepared["commander"]["applied_policy"]["volume_ratio_min"] == 0.68
    assert prepared["commander"]["policy_partial_normalized"] is True
    assert prepared["strategist"]["candidate_hints"] == ["122630", "233740", "005930"]
    assert prepared["strategist"]["market_headlines"][0] == "KOSPI opens firmer on chip optimism."
    assert prepared["strategist"]["symbol_headlines"][0] == "000660 extends gains on AI memory demand."
    assert prepared["scanner"]["playbook"] == "pullback"
    assert prepared["scanner"]["policy_source"] == "strategist"
    assert prepared["scanner"]["selection_trace"]["selected_symbol"] == "000660"
    assert prepared["scanner"]["selected_symbol_score_drivers"]["trading_value"] == 0.22
    assert prepared["scanner"]["scanner_bias_applied"] is True
    assert prepared["scanner"]["candidate_bias_adjustments"][0]["symbol"] == "000660"
    assert prepared["monitor"]["entry_blockers"] == ["volume_ok", "vwap_reclaim_ok"]
    assert prepared["monitor"]["threshold_shortfalls"]
    assert prepared["monitor"]["stop_policy_trace"]["hard_stop_pct"] == 0.03
    assert prepared["monitor"]["stop_policy_trace"]["effective_stop_loss_pct"] == 0.0092
    assert prepared["monitor"]["policy_source"] == "strategist"
    assert prepared["monitor"]["applied_policy"]["pullback_min_pct"] == 0.008
    assert prepared["monitor"]["received_policy"]["volume_ratio_min"] == 0.68
    assert prepared["monitor"]["effective_policy"]["volume_ratio_min"] == 0.75
    assert prepared["monitor"]["policy_adjustment_summary"]
    assert compact["commander"]["selected_route"] == "cached_strategist"
    assert compact["commander"]["route_reason_text"] == "commander_skip_cached_strategist"
    assert compact["commander"]["policy_source"] == "strategist"
    assert compact["commander"]["applied_policy"]["volume_ratio_min"] == 0.68
    assert compact["commander"]["policy_partial_normalized"] is True
    assert compact["strategist"]["candidate_hints"] == ["122630", "233740", "005930"]
    assert compact["strategist"]["market_headlines"][0] == "KOSPI opens firmer on chip optimism."
    assert compact["scanner"]["playbook"] in {"pullback", "눌림목", "눌림"}
    assert compact["scanner"]["policy_source"] == "strategist"
    assert compact["scanner"]["scanner_bias_applied"] is True
    assert compact["scanner"]["candidate_bias_adjustments"][0]["symbol"] == "000660"
    assert compact["scanner"]["selection_trace"]["selection_reason"] in {
        "top_value + sector_theme",
        "거래대금 상위 + 섹터·테마 정렬",
        "거래대금 상위 + 섹터/테마 정렬",
    }
    assert compact["scanner"]["selection_trace"]["selected_symbol_score_drivers"]["trading_value"] == 0.22
    assert compact["scanner"]["selection_reason_with_bias"]
    assert "preference" in compact["scanner"]["selection_reason_with_bias"]
    assert compact["monitor"]["entry_check_summary"] == "mission=wait_for_confirmation | reason=reclaim_not_confirmed"
    assert compact["monitor"]["entry_blockers"] == ["volume_ok", "vwap_reclaim_ok"]
    assert compact["monitor"]["policy_source"] == "strategist"
    assert compact["monitor"]["applied_policy"]["pullback_min_pct"] == 0.008
    assert compact["monitor"]["received_policy"]["volume_ratio_min"] == 0.68
    assert compact["monitor"]["effective_policy"]["volume_ratio_min"] == 0.75
    assert compact["monitor"]["effective_policy_deltas"]
    assert any("volume_ratio" in row for row in compact["monitor"]["threshold_shortfalls"])
    assert compact["monitor"]["stop_policy_trace"]["adaptive_stop_loss_pct"] == 0.0092


def test_operator_brief_input_normalizes_stale_chart_coverage_from_canonical_trade(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)
    detail = data_access.load_run_detail(cfg, "run-1")
    detail["scanner"]["feature_coverage"] = {
        "present": 10,
        "total": 12,
        "coverage_ratio": 10 / 12,
        "quality": "strong",
        "present_keys": [
            "engine_ma20_gap",
            "engine_adx14",
            "engine_trend_strength",
            "engine_volume_spike20",
            "engine_volatility20",
            "engine_vwap_distance",
            "engine_sector_relative_strength",
            "engine_cross_section_rank",
            "engine_regime",
            "engine_signal_score",
        ],
        "missing_keys": ["engine_ma60", "engine_ma120"],
    }
    detail["trade_report"]["story_input_data"]["filters_human"] = {
        "summary": "Scanner and guard checks passed 4 of 8 visible gates. Chart completeness was partial with 6/12 captured features.",
        "bullets": ["chart completeness filter: PARTIAL - 6/12 captured chart features"],
    }
    detail["trade_report"]["report_data"]["scanner_filters"] = {
        "summary": "Scanner and guard checks passed 4 of 8 visible gates. Chart completeness was partial with 6/12 captured features.",
        "bullets": ["chart completeness filter: PARTIAL - 6/12 captured chart features"],
    }
    detail["trade_report"]["story_input_data"]["scanner_reason_human"] = {
        "summary": "Selected as top ranked symbol due to value/volume blend.",
        "bullets": [
            "Universe scanned: 5",
            "Selected rank: #1",
            "Chart / feature coverage: 6/12",
        ],
    }

    compact = data_access._build_operator_brief_input(detail)
    sections = data_access._build_operator_brief_sections(detail)

    assert "10/12 captured features" in compact["scanner"]["canonical_filters_summary"]
    assert any("10/12" in bullet for bullet in compact["scanner"]["canonical_filter_bullets"])
    assert any("10/12" in bullet for bullet in compact["scanner"]["canonical_bullets"])
    chart_rows = [row for row in sections["filters_and_gates"] if row["name"] == "Chart Completeness Filter"]
    assert chart_rows
    assert chart_rows[0]["note"] == "10/12 filled"


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
    assert "전략가는" in brief["strategist_summary"]
    assert "스캐너는" in brief["scanner_summary"]
    assert "실행 단계에서는" in brief["executor_summary"]
    assert "리포터 평가는 등급" in brief["reporter_summary"]


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
    assert sections["current_snapshot"]["current_focus"] == "005930"
    assert sections["strategist_evidence"]["market_regime"] == "neutral"
    assert sections["scanner_focus"]["selected_symbol"] == "005930"
    assert sections["scanner_focus"]["selected_rank"] == 1
    assert sections["monitor_guard_snapshot"]["guard_status"] == "blocked"
    assert sections["next_step"]["summary"]
    assert sections["filters_and_gates"][0]["status"] == "PASS"
    assert sections["position_monitor_reasoning"]["hold_reasons"][0] == "Posture: BUY"
    assert sections["reporter_evaluation"]["run_grade"] == "A-"
    assert sections["reporter_evaluation"]["key_finding"] == "Reporter linked and graded the run A-."


def test_operator_brief_sections_surface_monitor_exit_metrics(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)
    detail = data_access.load_run_detail(cfg, "run-1")
    detail["monitor"] = {
        "summary": {
            "monitor_reason": "hold",
            "exit_reason": "hold",
            "peak_price": 71500.0,
            "peak_drawdown": -0.01399,
            "vwap_distance": -0.004,
            "position_age_seconds": 1800,
        },
        "decision_trace": {
            "monitor_reason": "hold",
            "exit_reason": "hold",
            "price": 70500.0,
            "avg_price": 70000.0,
            "peak_price": 71500.0,
            "peak_drawdown": -0.01399,
            "vwap_distance": -0.004,
            "position_age_seconds": 1800,
            "thresholds": {
                "hard_stop_pct": 0.01,
                "effective_stop_loss_pct": 0.01,
                "effective_stop_reason": "hard_stop",
                "take_profit_pct": 0.015,
                "peak_drawdown_exit_pct": 0.012,
                "vwap_breakdown_pct": 0.008,
                "intraday_low_break_pct": 0.004,
                "trend_strength_floor": 0.2,
            },
        },
    }
    detail["trade_report"]["report_data"]["monitor_snapshot"] = {
        "holding_time": "2.5h",
        "effective_stop": "0.80%",
        "effective_stop_reason": "Peak drawdown",
        "take_profit": "1.20%",
        "current_price": "70300.00",
        "average_price": "70050.00",
        "peak_price": "71600.00",
        "current_drawdown": "-1.82%",
        "peak_drawdown": "-1.82%",
        "vwap_distance": "-0.60%",
        "price_source": "position.current_price",
        "feature_source": "selected.features",
        "price_source_policy": "market.quote > position.current_price > selected > market_snapshot > position.avg_plus_unrealized",
        "active_exit_axis": "Peak drawdown",
        "watch_axes": ["Peak drawdown", "VWAP breakdown"],
        "hold_reasons": ["latest hold snapshot reused"],
        "exit_triggers": ["stop-loss trigger (1.00%)"],
    }

    sections = data_access._build_operator_brief_sections(detail)
    monitor_sec = sections["position_monitor_reasoning"]

    assert monitor_sec["current_price"] == "70300.00"
    assert monitor_sec["average_price"] == "70050.00"
    assert monitor_sec["peak_price"] == "71600.00"
    assert monitor_sec["current_drawdown"] == "-1.82%"
    assert monitor_sec["peak_drawdown"] == "-1.82%"
    assert monitor_sec["effective_stop"] == "0.80%"
    assert monitor_sec["effective_stop_reason"] == "Peak drawdown"
    assert monitor_sec["vwap_distance"] == "-0.60%"
    assert monitor_sec["price_source"] == "position.current_price"
    assert monitor_sec["feature_source"] == "selected.features"
    assert monitor_sec["price_source_policy"] == "market.quote > position.current_price > selected > market_snapshot > position.avg_plus_unrealized"
    assert monitor_sec["active_exit_axis"] == "Peak drawdown"
    assert "Peak drawdown" in monitor_sec["watch_axes"]
    assert "VWAP breakdown" in monitor_sec["watch_axes"]
    snapshot_sec = sections["monitor_guard_snapshot"]
    assert any("Hard fail-safe stop" in line for line in snapshot_sec["stop_policy_summary"])
    assert any("Take profit" in line for line in snapshot_sec["stop_policy_summary"])


def test_operator_brief_sections_normalize_raw_trade_report_monitor_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)
    detail = data_access.load_run_detail(cfg, "run-1")
    detail["trade_report"]["report_data"]["monitor_snapshot"] = {
        "posture": "HOLD",
        "trigger_type": "hard_stop",
        "position_age_seconds": 0,
        "stop_loss_pct": 0.08,
        "effective_stop_loss_pct": 0.01,
        "effective_stop_reason": "hard_stop",
        "take_profit_pct": 0.0094,
        "exit_triggered": True,
        "price_source": "position.current_price",
        "feature_source": "selected.features",
        "price_source_policy": "market.quote > position.current_price > selected > market_snapshot > position.avg_plus_unrealized",
    }

    sections = data_access._build_operator_brief_sections(detail)
    monitor_sec = sections["position_monitor_reasoning"]

    assert monitor_sec["posture"] == "HOLD"
    assert monitor_sec["holding_time"] == "0s"
    assert monitor_sec["stop_loss"] == "8.00%"
    assert monitor_sec["effective_stop"] == "1.00%"
    assert monitor_sec["effective_stop_reason"] == "Hard stop"
    assert monitor_sec["take_profit"] == "0.94%"
    assert monitor_sec["price_source"] == "position.current_price"
    assert monitor_sec["feature_source"] == "selected.features"
    assert monitor_sec["price_source_policy"] == "market.quote > position.current_price > selected > market_snapshot > position.avg_plus_unrealized"
    assert monitor_sec["active_exit_axis"] == "Hard stop"


def test_operator_brief_artifacts_are_saved_under_trade_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)

    detail = data_access.load_run_detail(cfg, "run-1")
    trade_report = detail["trade_report"]
    brief_json = Path(str(trade_report.get("operator_brief_json_path") or ""))
    brief_md = Path(str(trade_report.get("operator_brief_md_path") or ""))
    trade_root = Path(str(trade_report.get("trade_root_path") or ""))

    assert brief_json.exists() is True
    assert brief_md.exists() is True
    saved = json.loads(brief_json.read_text(encoding="utf-8"))
    assert saved["run_id"] == "run-1"
    assert saved["trade_id"] == "20260316_005930_buy_run-1"
    assert saved["report_status"] == "available"
    assert saved["schema_version"] == "operator_brief.v1"
    assert saved["version"] == data_access.OPERATOR_BRIEF_ARTIFACT_VERSION
    assert saved["llm_brief_status"] == "ok"
    assert isinstance(saved.get("generation"), dict)
    assert saved["generation"]["status"] == "ok"
    assert saved["generation"]["mode"] == "llm"
    assert "model" in saved["generation"]
    assert "reason" in saved["generation"]
    assert saved["provenance"] == "llm"
    assert isinstance(saved.get("missing_fields"), list)
    assert isinstance(saved.get("completeness"), float)
    assert isinstance(saved.get("shared_facts"), dict)
    assert saved["shared_facts"]["action"] == "BUY"
    assert saved["shared_facts"]["holding_duration"] == "10m"
    assert str(saved.get("source_signature") or "").strip()
    assert saved["monitor_snapshot"]["price_source"] == "-"
    assert str(saved["monitor_snapshot"]["effective_stop_reason"] or "") in {"", "-", "Hard stop"}
    md_text = brief_md.read_text(encoding="utf-8")
    assert "# 운영자 브리프" in md_text
    assert "## 1. 현재 스냅샷" in md_text
    assert "## 2. 전략가 근거" in md_text
    assert "## 3. 스캐너 포커스" in md_text
    assert "## 4. 모니터 / 가드" in md_text
    assert "## 5. 다음 예상 단계" in md_text
    brief_compact = trade_root / "brief" / "brief_compact_input.json"
    brief_input = trade_root / "brief" / "brief_input.json"
    assert brief_input.exists() is True
    assert brief_compact.exists() is True
    brief_llm = brief_json.parent / "brief_llm_response.json"
    assert brief_llm.exists() is True
    assert json.loads(brief_llm.read_text(encoding="utf-8"))["component"] == "brief"


def test_operator_brief_save_syncs_trade_health_mirror(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)

    detail = data_access.load_run_detail(cfg, "run-1")
    trade_report = detail["trade_report"]
    trade_root = Path(str(trade_report.get("trade_root_path") or ""))
    reports_dir = trade_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "ai_trade_report.json").write_text(
        json.dumps(
            {
                "ai_trade_report_status": "ok",
                "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (reports_dir / "ai_trade_report.md").write_text("# report\n", encoding="utf-8")
    health_path = trade_root / "_health.json"
    health_path.write_text(
        json.dumps(
            {
                "ai_trade_report_status": None,
                "llm_trade_report_status": None,
                "report_generation_status": None,
                "operator_brief_status": None,
                "artifact_presence": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    data_access._save_operator_brief_artifact(detail, detail["operator_brief"])
    health = json.loads(health_path.read_text(encoding="utf-8"))

    assert health["operator_brief_status"] == "ok"
    assert health["llm_brief_status"] == "ok"
    assert health["llm_trade_report_status"] == "ok"
    assert health["report_generation_status"] == "available"
    assert health["artifact_presence"]["operator_brief_json"] is True
    assert health["artifact_presence"]["operator_brief_md"] is True
    assert health["artifact_presence"]["ai_trade_report_json"] is True


def test_operator_brief_saved_artifact_is_reused(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)
    first = data_access.load_run_detail(cfg, "run-1")
    brief_json = Path(str(first["trade_report"].get("operator_brief_json_path") or ""))
    payload = json.loads(brief_json.read_text(encoding="utf-8"))
    payload["headline"] = "saved artifact headline"
    brief_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    cache_path = cfg.operator_ui_cache_path / "run-1.json"
    if cache_path.exists():
        cache_path.unlink()

    second = data_access.load_run_detail(cfg, "run-1")

    assert second["operator_brief"]["headline"] == "saved artifact headline"


def test_operator_brief_saved_artifact_is_invalidated_when_trade_report_changes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)

    first = data_access.load_run_detail(cfg, "run-1")
    trade_report = first["trade_report"]
    brief_json = Path(str(trade_report.get("operator_brief_json_path") or ""))
    report_json = Path(str(trade_report.get("trade_report_json_path") or ""))

    payload = json.loads(brief_json.read_text(encoding="utf-8"))
    payload["headline"] = "stale saved headline"
    brief_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report_payload = json.loads(report_json.read_text(encoding="utf-8"))
    executive = report_payload.get("executive_summary") if isinstance(report_payload.get("executive_summary"), dict) else {}
    executive["summary"] = "trade report changed after the brief was saved"
    report_payload["executive_summary"] = executive
    report_json.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    cache_path = cfg.operator_ui_cache_path / "run-1.json"
    if cache_path.exists():
        cache_path.unlink()

    second = data_access.load_run_detail(cfg, "run-1")

    assert second["operator_brief"]["headline"] != "stale saved headline"


def test_operator_brief_detail_force_regenerates_saved_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)
    detail = data_access.load_run_detail(cfg, "run-1")
    trade_report = detail["trade_report"]
    story_id = str(trade_report.get("trade_id") or trade_report.get("story_id") or "")
    brief_json = Path(str(trade_report.get("operator_brief_json_path") or ""))
    trade_root = Path(str(trade_report.get("trade_root_path") or ""))
    brief_input = trade_root / "brief" / "brief_input.json"

    payload = json.loads(brief_json.read_text(encoding="utf-8"))
    payload["headline"] = "stale saved headline"
    brief_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if brief_input.exists():
        brief_input.unlink()

    monkeypatch.setenv("OPERATOR_UI_RUN_BRIEF_FORCE_REGENERATE", "1")
    refreshed = data_access.load_operator_brief_detail(cfg, story_id)

    assert refreshed["headline"] != "stale saved headline"
    assert brief_input.exists() is True


def test_operator_brief_uses_openrouter_default_max_tokens_when_role_value_missing(tmp_path: Path, monkeypatch) -> None:
    _CaptureBriefPolicyRouter.policies = []
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _CaptureBriefPolicyRouter()))
    monkeypatch.delenv("OPERATOR_UI_RUN_BRIEF_MAX_TOKENS", raising=False)
    monkeypatch.setenv("OPENROUTER_DEFAULT_MAX_TOKENS", "4096")
    cfg = _make_config(tmp_path)

    detail = data_access.load_run_detail(cfg, "run-1")

    assert detail["operator_brief"]["status"] == "ok"
    assert _CaptureBriefPolicyRouter.policies
    assert int(_CaptureBriefPolicyRouter.policies[0]["max_tokens"]) == 4096


def test_operator_brief_repairs_mixed_language_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _MixedLanguageRepairRouter()))
    cfg = _make_config(tmp_path)

    detail = data_access.load_run_detail(cfg, "run-1")
    brief = detail["operator_brief"]

    assert brief["status"] == "repaired"
    assert "中立" not in str(brief.get("executive_summary") or "")
    assert "候補" not in str(brief.get("scanner_reason") or "")
    assert "變動" not in str(brief.get("risk_summary") or "")


def test_operator_brief_sanitizes_internal_prompt_leakage_and_bad_monitor_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _LeakyBriefRouter()))
    cfg = _make_config(tmp_path)

    detail = data_access.load_run_detail(cfg, "run-1")
    brief = detail["operator_brief"]

    assert brief["status"] == "ok"
    assert all("canonical_trade.available" not in str(item) for item in brief["operator_takeaways"])
    assert all("reports/trades" not in str(item) for item in brief["operator_takeaways"])

    normalized = data_access._sanitize_operator_brief_result(
        {
            "trade_report": {"lifecycle_status": "open", "action": "BUY"},
            "executor": {"execution": {"action": "BUY"}},
        },
        {"monitor_summary": "포지션 없음(no_position) 상태를 확인했습니다.", "operator_takeaways": []},
        {"monitor_summary": "현재는 보유/모니터링 상태입니다.", "operator_takeaways": []},
    )
    assert normalized["monitor_summary"] == "현재는 보유/모니터링 상태입니다."


def test_operator_brief_prompt_uses_valid_korean_guidance() -> None:
    messages = data_access._build_operator_brief_messages({"symbol": "005930", "entry": {"decision": "WAIT"}})

    assert "??" not in messages[0]["content"]
    assert "??" not in messages[1]["content"]
    assert "이번 거래는 분봉 데이터가 확보되지 않아 진입 근거를 확인할 수 없었습니다." in messages[1]["content"]
    assert "자연스러운 한국어" in messages[0]["content"]
    assert "즉시 상황 파악용 snapshot" in messages[1]["content"]
    assert "긴 lifecycle 회고" in messages[1]["content"]


def test_operator_brief_fallback_markdown_keeps_all_sections_and_natural_korean() -> None:
    def _brief_for_reason(reason_code: str) -> dict:
        return {
            "status": "fallback",
            "headline": "AI Brief Failed WAIT 005930",
            "operator_takeaways": [],
            "sections": {
                "executive_decision": {"symbol": "005930", "final_action": "WAIT"},
                "why_symbol_chosen": {"universe_size": 5, "selected_rank": 1, "selection_reasons": [], "comparison_reasons": []},
                "entry_timing": {"reason_code": reason_code, "pattern": "", "metrics": {}},
                "position_monitor_reasoning": {"posture": "WAIT"},
                "exit_plan": {"watch_axes": []},
                "risk_alerts": {},
                "operator_conclusion": {"watch_next": ["다음 분봉 확인"]},
            },
        }

    minute_markdown = data_access._render_operator_brief_markdown(_brief_for_reason("minute_candle_missing"))
    incomplete_markdown = data_access._render_operator_brief_markdown(_brief_for_reason("data_incomplete"))
    no_entry_markdown = data_access._render_operator_brief_markdown(_brief_for_reason("no_position"))

    for heading in [
        "## 1. 최종 판단 요약",
        "## 2. 종목 선정 이유",
        "## 3. 진입 근거",
        "## 4. 현재 상태",
        "## 5. 청산 계획",
        "## 6. 리스크 요인",
        "## 7. 다음 체크포인트",
    ]:
        assert heading in minute_markdown
    assert "이번 거래는 분봉 데이터가 확보되지 않아 진입 근거를 확인할 수 없었습니다." in minute_markdown
    assert "체결 이전 분봉 기록이 충분하지 않아 진입 시점을 확정하기 어렵습니다." in incomplete_markdown
    assert "저장된 데이터 범위 안에서는 체결 직전 분봉 진입 근거가 충분히 남아 있지 않았습니다." in no_entry_markdown
    for forbidden in ["not captured", "not available", "unknown"]:
        assert forbidden not in minute_markdown.lower()
        assert forbidden not in incomplete_markdown.lower()
        assert forbidden not in no_entry_markdown.lower()


def test_operator_brief_markdown_prefers_snapshot_sections_when_present() -> None:
    brief = {
        "status": "fallback",
        "headline": "AI Brief Failed SELL 100790",
        "operator_takeaways": ["다음 분봉에서 거래량 회복 여부를 먼저 본다."],
        "sections": {
            "executive_decision": {"symbol": "100790", "final_action": "SELL"},
            "current_snapshot": {
                "summary": "100790은 피크 드로우다운 트리거로 청산된 상태입니다.",
                "current_focus": "100790",
                "guard_status": "approved",
                "execution_status": "filled",
            },
            "strategist_evidence": {
                "summary": "defensive playbook, global sentiment -0.05, VIX 25.33",
                "candidate_hints": ["100790", "005930"],
                "market_headlines": ["반도체 업종이 장중 강세를 유지했습니다."],
                "symbol_headlines": ["100790 관련 수급 유입이 확인됐습니다."],
            },
            "scanner_focus": {
                "summary": "Scanner selected 100790 as rank #1 out of 5 candidates.",
                "selected_symbol": "100790",
                "selected_rank": 1,
                "selection_reason": "top_value + top_volume",
                "top_candidates": [{"symbol": "100790"}, {"symbol": "005930"}],
                "score_drivers": {"trading_value": 0.831, "momentum": 0.622},
            },
            "monitor_guard_snapshot": {
                "summary": "peak_drawdown trigger confirmed.",
                "monitor_reason": "peak_drawdown",
                "stop_policy_summary": ["Hard fail-safe stop 8.00%", "Effective stop 3.00% (Hard stop)"],
                "guard_status": "approved",
            },
            "next_step": {
                "summary": "다음 거래에서는 분봉 확인과 거래량 회복을 우선 확인합니다.",
                "watch_next": ["거래량 회복 여부", "재진입 신호 여부"],
                "operator_takeaways": ["청산 후 재진입 전 cooldown을 확인합니다."],
            },
        },
    }

    markdown = data_access._render_operator_brief_markdown(brief)

    assert "## 1. 현재 스냅샷" in markdown
    assert "## 2. 전략가 근거" in markdown
    assert "## 3. 스캐너 포커스" in markdown
    assert "## 4. 모니터 / 가드" in markdown
    assert "## 5. 다음 예상 단계" in markdown
    assert "## 6. 운영자 포인트" in markdown
    assert "## 3. 진입 근거" not in markdown
    assert "전략가 후보 힌트: 100790, 005930" in markdown
    assert "최종 선택: 100790 (rank 1)" in markdown
    assert "활성 스톱 정책:" in markdown


def test_operator_brief_markdown_removes_internal_english_labels_and_fills_next_checkpoint() -> None:
    brief = {
        "status": "fallback",
        "headline": "AI Brief Failed HOLD 005930",
        "operator_takeaways": [],
        "sections": {
            "executive_decision": {"symbol": "005930", "final_action": "HOLD"},
            "why_symbol_chosen": {
                "universe_size": 5,
                "selected_rank": 1,
                "selection_reasons": ["Universe scanned: 5", "Selected rank: #1", "Runner-up symbols had weaker coverage"],
                "comparison_reasons": [],
            },
            "entry_timing": {
                "reason_code": "minute_candle_missing",
                "pattern": "",
                "metrics": {"recent_high": 70500, "volume_ratio": 1.8, "vwap_distance": 0.012},
            },
            "position_monitor_reasoning": {
                "posture": "HOLD",
                "hold_reasons": ["Posture: HOLD", "Exit trigger: no"],
                "average_price": "70,100원",
                "current_price": "70,500원",
                "peak_price": "70,900원",
                "current_drawdown": "+0.57%",
                "peak_drawdown": "-0.30%",
                "watch_axes": ["Hard stop", "Adaptive stop", "Take profit", "VWAP breakdown"],
                "effective_stop_reason": "Hard stop",
                "effective_stop": "-2.5%",
                "take_profit": "+3.5%",
            },
            "exit_plan": {
                "watch_axes": ["Hard stop", "Adaptive stop", "Take profit", "VWAP breakdown"],
                "effective_stop_reason": "Adaptive stop",
                "effective_stop": "-2.0%",
                "take_profit": "+3.5%",
            },
            "risk_alerts": {},
            "operator_conclusion": {"watch_next": []},
            "market_context": {"global_sentiment": "-0.20", "vix": "25.09"},
        },
    }

    markdown = data_access._render_operator_brief_markdown(brief)

    assert "Posture:" not in markdown
    assert "Hard stop" not in markdown
    assert "Adaptive stop" not in markdown
    assert "Take profit" not in markdown
    assert "Universe scanned:" not in markdown
    assert "Selected rank:" not in markdown
    assert "현재 포지션 판단은 보유 유지입니다." in markdown
    assert "고정 손절 기준" in markdown
    assert "상황 대응형 손절 기준" in markdown
    assert "목표 수익 실현 기준" in markdown
    assert "## 7. 다음 체크포인트" in markdown
    assert "다음 체크포인트" in markdown and "분봉 기준" in markdown


def test_operator_brief_scanner_reason_is_ranked_narrative_when_brief_text_is_generic() -> None:
    brief = {
        "status": "fallback",
        "headline": "AI Brief Failed WAIT 000660",
        "operator_takeaways": [],
        "sections": {
            "executive_decision": {"symbol": "000660", "final_action": "WAIT"},
            "why_symbol_chosen": {
                "universe_size": 5,
                "selected_rank": 1,
                "selection_reasons": ["volume expansion observed", "breakout attempt detected"],
                "comparison_reasons": [],
            },
            "entry_timing": {"reason_code": "no_breakout_signal", "pattern": "", "metrics": {}},
            "position_monitor_reasoning": {"posture": "WAIT"},
            "exit_plan": {"watch_axes": []},
            "risk_alerts": {},
            "operator_conclusion": {"watch_next": []},
        },
    }

    markdown = data_access._render_operator_brief_markdown(brief)

    assert "후보" in markdown or "선정" in markdown or "순위" in markdown
    assert "거래량과 거래대금 흐름이 함께 확인되었습니다." in markdown or "단기 돌파 시도 흐름이 포착되었습니다." in markdown


def test_operator_brief_fallback_rendered_stays_readable_and_not_error_stub() -> None:
    brief = {
        "status": "fallback",
        "fallback_rendered": True,
        "headline": "AI Brief Failed SELL 032820",
        "operator_takeaways": [],
        "sections": {
            "executive_decision": {"symbol": "032820", "final_action": "SELL"},
            "why_symbol_chosen": {"universe_size": 3, "selected_rank": 1, "selection_reasons": [], "comparison_reasons": []},
            "entry_timing": {"reason_code": "hard_stop", "pattern": "", "metrics": {}},
            "position_monitor_reasoning": {"posture": "SELL"},
            "exit_plan": {"watch_axes": ["VWAP breakdown"]},
            "risk_alerts": {},
            "operator_conclusion": {"watch_next": []},
        },
    }

    markdown = data_access._render_operator_brief_markdown(brief)

    assert "AI Brief Failed" not in markdown
    assert "브리프 생성에 실패했습니다" not in markdown
    assert "## 1. 최종 판단 요약" in markdown
    assert "## 7. 다음 체크포인트" in markdown


def test_operator_brief_closed_trade_fallback_uses_natural_korean_narrative() -> None:
    brief = {
        "status": "fallback",
        "fallback_rendered": True,
        "headline": "AI Brief Failed SELL 000660",
        "operator_takeaways": [],
        "sections": {
            "executive_decision": {"symbol": "000660", "final_action": "SELL"},
            "why_symbol_chosen": {"universe_size": 0, "selected_rank": 1, "selection_reasons": [], "comparison_reasons": []},
            "entry_timing": {"reason_code": "peak_drawdown", "pattern": "", "metrics": {}},
            "position_monitor_reasoning": {
                "posture": "SELL",
                "average_price": "1,011,000원",
                "current_price": "1,012,000원",
                "peak_drawdown": "-1.08%",
                "effective_stop_reason": "Hard stop",
                "effective_stop": "1.00%",
                "take_profit": "1.23%",
                "watch_axes": ["Hard stop", "Adaptive stop"],
            },
            "exit_plan": {
                "effective_stop_reason": "Hard stop",
                "effective_stop": "1.00%",
                "take_profit": "1.23%",
                "watch_axes": ["Hard stop", "Adaptive stop"],
            },
            "risk_alerts": {},
            "operator_conclusion": {"watch_next": []},
        },
    }

    markdown = data_access._render_operator_brief_markdown(brief)

    assert "이미 매도로 종료되었습니다" in markdown
    assert "후보 비교 데이터가 충분히 저장되지 않아" in markdown
    assert "## 7." in markdown
    assert "다음 거래에서는 분봉 진입 근거와 후보 비교 데이터가 충분히 남는지 먼저 확인합니다." in markdown


def test_operator_brief_closed_trade_fallback_replaces_placeholders_and_entry_wait_mismatch() -> None:
    brief = {
        "status": "fallback",
        "fallback_rendered": True,
        "headline": "AI Brief Failed SELL 000660",
        "operator_takeaways": [],
        "sections": {
            "executive_decision": {"symbol": "000660", "final_action": "SELL"},
            "why_symbol_chosen": {"universe_size": 5, "selected_rank": 1, "selection_reasons": [], "comparison_reasons": []},
            "entry_timing": {
                "reason_code": "pullback_structure_above_vwap_with_confirmation",
                "pattern": "pullback_vwap_hold",
                "metrics": {"vwap_distance": 0.1088, "volume_ratio": 0.74, "pullback_pct": 0.0575},
            },
            "position_monitor_reasoning": {
                "posture": "SELL",
                "effective_stop_reason": "not captured",
                "effective_stop": "6.38%",
                "take_profit": "3.22%",
                "watch_axes": ["Hard stop", "Adaptive stop", "Take profit", "Trailing stop"],
            },
            "exit_plan": {
                "effective_stop_reason": "not captured",
                "effective_stop": "6.38%",
                "take_profit": "3.22%",
                "watch_axes": ["Hard stop", "Adaptive stop", "Take profit", "Trailing stop"],
            },
            "risk_alerts": {},
            "operator_conclusion": {"watch_next": []},
        },
    }

    markdown = data_access._render_operator_brief_markdown(brief)

    assert "not captured" not in markdown.lower()
    assert "진입을 보류" not in markdown
    assert "눌림 이후 반등이 확인됐고" in markdown
    assert "현재 저장된 손절 기준은 6.38% 수준으로 보고 있습니다." in markdown


def test_operator_brief_ignores_list_literal_risk_summary() -> None:
    brief = {
        "status": "fallback",
        "headline": "AI Brief Failed SELL 000660",
        "risk_summary": "['스캐너 후보가 부족했습니다', '진입 이유가 비어 있습니다']",
        "operator_takeaways": [],
        "sections": {
            "executive_decision": {"symbol": "000660", "final_action": "SELL"},
            "why_symbol_chosen": {"universe_size": 0, "selected_rank": 1, "selection_reasons": [], "comparison_reasons": []},
            "entry_timing": {"reason_code": "peak_drawdown", "pattern": "", "metrics": {}},
            "position_monitor_reasoning": {"posture": "SELL"},
            "exit_plan": {"watch_axes": []},
            "risk_alerts": {"weak_factors": ["스캐너 후보가 부족했습니다.", "진입 이유 기록이 충분하지 않았습니다."]},
            "operator_conclusion": {"watch_next": []},
        },
    }

    markdown = data_access._render_operator_brief_markdown(brief)

    assert "['스캐너 후보가 부족했습니다'" not in markdown
    assert "스캐너 후보가 부족했습니다." in markdown


def test_operator_brief_prefers_richer_fallback_text_and_takeaways() -> None:
    normalized = data_access._sanitize_operator_brief_result(
        {"trade_report": {"lifecycle_status": "open", "action": "BUY"}, "executor": {"execution": {"action": "BUY"}}},
        {
            "monitor_summary": "HOLD posture, effective stop 1.00%",
            "operator_takeaways": [
                "Monitor enforces tight 1% stop",
                "Trade executed",
            ],
        },
        {
            "monitor_summary": "현재 포지션 보유 중이며 HOLD 결정. 평균 매수가 1,011,000원, 현재가 1,012,000원으로 약 +0.10% 평가.",
            "operator_takeaways": [
                "중립 시장에서 브레이크아웃 전략 실행, 글로벌 감성 -0.22 및 VIX 25.09 고려",
                "스캐너가 5개 후보 중 000660을 trading value와 sector_theme 근거로 선정",
                "모니터링 결과 HOLD, 유효 스톱 1.00% 및 테이크 프로핏 1.23% 적용",
                "BUY 주문 승인 및 시뮬레이션 체결 완료",
            ],
        },
    )

    assert "현재 포지션 보유 중이며 보유 유지 결정" in normalized["monitor_summary"]
    assert normalized["operator_takeaways"][0].startswith("중립 시장에서 브레이크아웃 전략 실행")


def test_operator_brief_writes_failure_artifact_after_retries(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _AlwaysEmptyRouter()))
    cfg = _make_config(tmp_path)

    detail = data_access.load_run_detail(cfg, "run-1")
    brief = detail["operator_brief"]
    brief_json = Path(str(detail["trade_report"].get("operator_brief_json_path") or ""))
    brief_llm = brief_json.parent / "brief_llm_response.json"
    artifact = json.loads(brief_llm.read_text(encoding="utf-8"))

    assert brief["status"] == "fallback"
    assert brief["failure"]["status"] == "empty_response"
    assert artifact["status"] == "fallback"
    assert artifact["retry_count"] >= 1
    assert str(artifact.get("response_ref") or "").endswith("response.json")
    assert str(artifact.get("prompt_ref") or "").endswith("prompt.json")
    assert artifact.get("raw_response_text", "") == ""
    assert artifact["parse_mode"] == "none"
    assert artifact["required_keys_missing"] == data_access.OPERATOR_BRIEF_REQUIRED_KEYS
    assert artifact["used_fallback_sections"] == data_access.OPERATOR_BRIEF_REQUIRED_KEYS
    assert brief["headline"].startswith("AI Brief Failed")


def test_operator_brief_timeout_retry_preserves_attempt_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _TimeoutThenEmptyRouter()))
    monkeypatch.setenv("OPERATOR_UI_RUN_BRIEF_RETRY_MAX", "1")
    cfg = _make_config(tmp_path)

    detail = data_access.load_run_detail(cfg, "run-1")
    brief = detail["operator_brief"]
    brief_json = Path(str(detail["trade_report"].get("operator_brief_json_path") or ""))
    artifact = json.loads((brief_json.parent / "brief_llm_response.json").read_text(encoding="utf-8"))

    assert brief["status"] == "fallback"
    assert brief["failure"]["status"] in {"timeout", "empty_response"}
    assert artifact["retry_count"] >= 1
    assert [row["step"] for row in artifact["attempts"][:2]] == ["first_attempt", "retry_1"]
    assert artifact["attempts"][0]["status"] == "timeout"
    assert artifact["parse_mode"] == "none"


def test_operator_brief_language_policy_failed_still_falls_back(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _AlwaysMixedLanguageRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "minimax/minimax-m2.5")
    cfg = _make_config(tmp_path)

    detail = data_access.load_run_detail(cfg, "run-1")
    brief = detail["operator_brief"]
    brief_json = Path(str(detail["trade_report"].get("operator_brief_json_path") or ""))
    artifact = json.loads((brief_json.parent / "brief_llm_response.json").read_text(encoding="utf-8"))

    assert brief["status"] == "fallback"
    assert brief["failure"]["reason"] == "language_policy_failed"
    assert artifact["attempts"][0]["error"] == "language_policy_failed"
    assert brief.get("fallback_rendered") is True


def test_operator_brief_fallback_payload_records_safe_meta_and_readable_text(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _AlwaysMixedLanguageRouter()))
    cfg = _make_config(tmp_path)

    detail = data_access.load_run_detail(cfg, "run-1")
    brief_json = Path(str(detail["trade_report"].get("operator_brief_json_path") or ""))
    saved = json.loads(brief_json.read_text(encoding="utf-8"))
    text_blob = " ".join(
        str(saved.get(key) or "")
        for key in (
            "headline",
            "monitor_summary",
            "scanner_reason",
            "risk_summary",
        )
    )

    assert saved["status"] == "fallback"
    assert saved["provenance"] == "fallback"
    assert saved["reason_code"] == "language_policy_failed"
    assert isinstance(saved.get("missing_fields"), list)
    assert isinstance(saved.get("completeness"), float)
    assert "中立" not in text_blob
    assert "候補" not in text_blob
    assert "變動" not in text_blob


def test_operator_ui_reads_new_trade_artifact_layout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)
    story_id = "TRD_20260316_005930_99"
    new_trade_root = cfg.reports_root / "trades" / "2026-03-16" / story_id
    _write_json(
        new_trade_root / "lifecycle_bundle.json",
        {
            "schema_version": "lifecycle_bundle.v1",
            "day": "2026-03-16",
            "run_id": "run-new",
            "trade_id": story_id,
            "story_id": story_id,
            "linked_run_ids": ["run-new"],
            "story_contract": {"story_type": "simulation", "execution_mode_label": "simulation"},
            "execution": {"action": "BUY", "symbol": "005930"},
            "artifacts": {},
        },
    )
    _write_json(
        new_trade_root / "entry.json",
        {"run_id": "run-new", "action": "BUY", "symbol": "005930"},
    )
    _write_json(
        new_trade_root / "hold.json",
        {"run_ids": ["run-new"], "posture": "HOLD"},
    )
    _write_json(
        new_trade_root / "exit.json",
        {},
    )
    _write_json(
        new_trade_root / "ai_trade_report_input.json",
        {"schema_version": "trade_story_input.v2", "trade_id": story_id, "story_id": story_id, "run_id": "run-new", "symbol": "005930", "day": "2026-03-16"},
    )
    _write_json(
        new_trade_root / "reports" / "ai_trade_report.json",
        {
            "schema_version": "trade_report.v2",
            "trade_id": story_id,
            "story_id": story_id,
            "run_id": "run-new",
            "symbol": "005930",
            "action": "BUY",
            "status": "open",
            "story_type": "simulation",
            "execution_mode_label": "simulation",
            "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free", "reason": ""},
            "executive_summary": {"headline": "BUY 005930", "summary": "new layout works"},
            "reporter_evaluation": {"summary": "linked", "status": "linked", "grade": "A"},
        },
    )

    report = data_access.load_trade_report_detail(cfg, story_id)

    assert report["found"] is True
    assert report["paths"]["ai_trade_report_json"].endswith("ai_trade_report.json")
    assert report["paths"]["ai_trade_report_input"].endswith("ai_trade_report_input.json")


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
    assert "Lifecycle Review" in page.text
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


def test_operator_ui_operator_brief_detail_page(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    app = create_app(_make_config(tmp_path))
    client = TestClient(app)

    page = client.get("/reports/trade/20260316_005930_buy_run-1/brief")
    assert page.status_code == 200
    assert "Operator brief" in page.text
    assert "Current Snapshot" in page.text
    assert "Strategist Evidence" in page.text
    assert "Scanner Focus" in page.text
    assert "Monitor / Guard" in page.text
    assert "Next Expected Step" in page.text
    assert "Operator Takeaways" in page.text
    assert "Open run detail" in page.text
    assert "Open full AI report" in page.text
    assert "Supporting Agent Summaries" in page.text
    assert "Saved brief JSON" in page.text


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


def test_operator_ui_run_detail_shows_portfolio_sync_mismatch_warning(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "stepfun/step-3.5-flash:free")
    cfg = _make_config(tmp_path)
    with cfg.event_log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": "run-sync-block", "ts": "2026-03-16T01:00:00+00:00", "stage": "commander_router", "event": "route", "payload": {"mode": "integrated_chain", "phase": "session", "agents": ["strategist", "scanner", "monitor"]}}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"run_id": "run-sync-block", "ts": "2026-03-16T01:00:01+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "no_position", "exit_reason": "no_position"}}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"run_id": "run-sync-block", "ts": "2026-03-16T01:00:02+00:00", "stage": "execute_from_packet", "event": "portfolio_guard_block", "payload": {"allowed": False, "reason": "portfolio_snapshot_positions_mismatch_unresolved", "reader_ok": True, "positions_source": "reader_positions", "reconciliation_status": "persisted_fallback", "reader_positions_authoritative": False, "positions_mismatch_detected": True, "reconciliation_applied": False, "reader_positions_count": 0, "persisted_positions_count": 1}}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"run_id": "run-sync-block", "ts": "2026-03-16T01:00:03+00:00", "stage": "commander_router", "event": "end", "payload": {"status": "ok", "path": "integrated_chain"}}, ensure_ascii=False) + "\n")

    app = create_app(cfg)
    client = TestClient(app)

    runs = client.get("/runs")
    assert runs.status_code == 200
    assert "run-sync-block" in runs.text
    assert "Portfolio Mismatch" in runs.text

    mismatch_runs = client.get("/runs?mismatch_only=true")
    assert mismatch_runs.status_code == 200
    assert "run-sync-block" in mismatch_runs.text
    assert "run-1" not in mismatch_runs.text

    detail = client.get("/runs/run-sync-block")
    assert detail.status_code == 200
    assert "계좌 동기화" in detail.text
    assert "Portfolio Mismatch" in detail.text
    assert "신규 BUY는 차단됩니다." in detail.text


def test_load_run_detail_prefers_canonical_run_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)
    canonical_dir = cfg.reports_root / "canonical" / "2026-03-16" / "run-1"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        canonical_dir / "commander.json",
        {
            "agent": "commander",
            "run_id": "run-1",
            "mode": "integrated_chain",
            "phase": "session",
            "path": "integrated_chain_monitor_only",
            "status": "ok",
        },
    )
    _write_json(
        canonical_dir / "strategist.json",
        {
            "agent": "strategist",
            "run_id": "run-1",
            "playbook": "canonical_defensive",
            "themes": ["chips"],
            "market_regime": "canonical_neutral",
            "market_sentiment": "canonical_mixed",
            "llm_metadata_summary": {"status": "ok", "model": "openrouter/free"},
        },
    )
    _write_json(
        canonical_dir / "scanner.json",
        {
            "agent": "scanner",
            "run_id": "run-1",
            "top_stock": "000660",
            "selected_symbol": "000660",
            "candidate_pool_after_filter": 7,
            "selected_candidate": {"symbol": "000660", "why": "canonical rank #1"},
        },
    )
    _write_json(
        canonical_dir / "monitor.json",
        {
            "agent": "monitor",
            "run_id": "run-1",
            "monitor_reason": "canonical_hold",
            "exit_reason": "canonical_hold",
            "selected_symbol": "000660",
        },
    )
    _write_json(
        canonical_dir / "supervisor.json",
        {
            "agent": "supervisor",
            "run_id": "run-1",
            "supervisor_allow": True,
            "supervisor_reason": "canonical_allowed",
        },
    )
    _write_json(
        canonical_dir / "executor.json",
        {
            "agent": "executor",
            "run_id": "run-1",
            "action": "BUY",
            "symbol": "000660",
            "qty": 1,
            "status": "CANONICAL_EXECUTED",
        },
    )

    detail = data_access.load_run_detail(cfg, "run-1")
    assert detail["strategist"]["provenance"] == "canonical"
    assert detail["scanner"]["provenance"] == "canonical"
    assert detail["monitor"]["provenance"] == "canonical"
    assert detail["strategist"]["summary"]["playbook"] == "canonical_defensive"
    assert detail["scanner"]["summary"]["top_stock"] == "000660"
    assert detail["monitor"]["summary"]["monitor_reason"] == "canonical_hold"
    compact = data_access._build_operator_brief_input(detail)
    assert compact["strategist"]["playbook"] == "canonical_defensive"
    assert compact["scanner"]["selected_symbol"] == "000660"
    assert compact["monitor"]["monitor_reason"] == "canonical_hold"



def test_operator_brief_sections_surface_canonical_scanner_reasoning_details(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(data_access.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))
    cfg = _make_config(tmp_path)
    detail = data_access.load_run_detail(cfg, "run-1")
    trade_report = detail["trade_report"]
    story_input = trade_report["story_input_data"]
    story_input["scanner_reason_human"] = {
        "summary": "Scanner selected 005930 as rank #1 out of 5 candidates with score 1.230.",
        "bullets": [
            "Universe scanned: 5",
            "Selected rank: #1",
            "Top candidates: #1 005930 score 1.230; #2 000660 score 1.205; #3 035420 score 1.180",
        ],
        "selected_symbol": "005930",
        "selected_rank": 1,
        "universe_size": 5,
        "selected_score": 1.23,
        "selection_basis": "Scanner selected the highest-ranked candidate after strategist-guided weighting, source scoring, and risk penalties.",
        "why_selected": [
            "highest total score (1.230)",
            "confidence 0.84 and lower risk 0.18",
            "source mix: top_value, top_volume",
        ],
        "top_candidates": [
            {"rank": 1, "symbol": "005930", "score_total": 1.23, "risk_score": 0.18, "confidence": 0.84},
            {"rank": 2, "symbol": "000660", "score_total": 1.205, "risk_score": 0.22, "confidence": 0.81},
            {"rank": 3, "symbol": "035420", "score_total": 1.18, "risk_score": 0.27, "confidence": 0.79},
        ],
        "runner_ups_lost": [
            {"symbol": "000660", "why_lost": ["lower total score (1.205 vs 1.230)", "higher risk (0.22 vs 0.18)"], "summary": "lower total score (1.205 vs 1.230); higher risk (0.22 vs 0.18)"},
            {"symbol": "035420", "why_lost": ["lower total score (1.180 vs 1.230)", "lower confidence (0.79 vs 0.84)"], "summary": "lower total score (1.180 vs 1.230); lower confidence (0.79 vs 0.84)"},
        ],
        "tie_break_rule": "score_total desc -> confidence desc -> risk_score asc",
    }
    story_input["scanner_evidence"] = {
        "candidate_selection_reasons": [
            {
                "payload": {
                    "selected_symbol": "005930",
                    "why_selected": [
                        "highest total score (1.230)",
                        "confidence 0.84 and lower risk 0.18",
                    ],
                    "runner_ups_lost": [
                        {"symbol": "000660", "why_lost": ["lower total score (1.205 vs 1.230)", "higher risk (0.22 vs 0.18)"]}
                    ],
                    "tie_break_rule": "score_total desc -> confidence desc -> risk_score asc",
                    "final_decision_basis": "Scanner selected the highest-ranked candidate after strategist-guided weighting, source scoring, and risk penalties.",
                }
            }
        ]
    }

    sections = data_access._build_operator_brief_sections(detail)

    assert any("highest-ranked candidate after strategist-guided weighting" in row for row in sections["why_symbol_chosen"]["selection_reasons"])
    assert any("confidence 0.84 and lower risk 0.18" in row for row in sections["why_symbol_chosen"]["selection_reasons"])
    assert sections["why_symbol_chosen"]["comparison_reasons"][0].startswith("000660 was weaker:")
    assert sections["scanner_ranking_explanation"]["tie_break_rule"] == "score_total desc -> confidence desc -> risk_score asc"
