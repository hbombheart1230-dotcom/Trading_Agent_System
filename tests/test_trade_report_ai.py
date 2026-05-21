from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

import libs.reporting.trade_report_ai as mod
from libs.reporting.report_truth_surface import build_trade_report_truth_surface


class _Route:
    def __init__(self, model: str) -> None:
        self.model = model


class _RetrySuccessRouter:
    def __init__(self) -> None:
        self.client = object()
        self.calls = 0

    @staticmethod
    def from_env() -> "_RetrySuccessRouter":
        return _RetrySuccessRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        self.calls += 1
        if self.calls == 1:
            return "not-json"
        return (
            '{"executive_summary":{"headline":"HOLD 000660","action":"HOLD","symbol":"000660","confidence":"high","summary":"ok"},'
            '"market_context_at_entry":{"summary":"context","bullets":["vix noted"]},'
            '"why_this_symbol_was_chosen":{"summary":"rank #1","bullets":["top value"]},'
            '"entry_decision":{"summary":"entry","bullets":[]},'
            '"holding_monitoring_story":{"summary":"hold","bullets":[]},'
            '"exit_decision":{"summary":"open trade","bullets":[]},'
            '"execution_quality":{"summary":"execution","bullets":[]},'
            '"scanner_filters":{"summary":"filters","bullets":[]},'
            '"guard_approval_result":{"summary":"guard","bullets":[]},'
            '"reporter_evaluation":{"summary":"reporter","status":"pending","grade":"N/A","bullets":[]},'
            '"errors_weaknesses_improvement_points":{"summary":"none","bullets":[]},'
            '"full_timeline":[{"event":"entry","ts":"2026-03-18T00:00:00+00:00","description":"entry"}],'
            '"final_operator_conclusion":{"summary":"hold","current_action":"HOLD","watch_next":["watch"],"thesis_invalidation":["stop"]}}'
        )


class _AlwaysEmptyRouter:
    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_AlwaysEmptyRouter":
        return _AlwaysEmptyRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return ""


def test_contains_hangul_does_not_use_fragile_regex() -> None:
    assert mod._contains_hangul("\ud55c\uae00")
    assert not mod._contains_hangul("abc 123")


class _TruncatedOuterJsonRouter:
    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_TruncatedOuterJsonRouter":
        return _TruncatedOuterJsonRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return (
            'prefix {"executive_summary":{"headline":"HOLD 000660","action":"HOLD","symbol":"000660","confidence":"high","summary":"ok"}}'
            ', "market_context_at_entry": {"summary":"cut off before outer object closes"'
        )


class _MissingKeysRouter:
    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_MissingKeysRouter":
        return _MissingKeysRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return json.dumps(
            {
                "executive_summary": {"headline": "HOLD 000660", "action": "HOLD", "symbol": "000660", "confidence": "high", "summary": "ok"},
                "market_context_at_entry": {"summary": "context", "bullets": ["vix noted"]},
            }
        )


class _ProseThenCompleteJsonRouter:
    def __init__(self) -> None:
        self.client = object()
        self.calls = 0

    @staticmethod
    def from_env() -> "_ProseThenCompleteJsonRouter":
        return _ProseThenCompleteJsonRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        self.calls += 1
        prefix = "I will now return the final JSON object only. " if self.calls == 1 else ""
        return (
            prefix
            +
            '{"executive_summary":{"headline":"HOLD 000660","action":"HOLD","symbol":"000660","confidence":"high","summary":"ok"},'
            '"market_context_at_entry":{"summary":"context","bullets":["vix noted"]},'
            '"why_this_symbol_was_chosen":{"summary":"rank #1","bullets":["top value"]},'
            '"entry_decision":{"summary":"entry","bullets":[]},'
            '"holding_monitoring_story":{"summary":"hold","bullets":[]},'
            '"exit_decision":{"summary":"open trade","bullets":[]},'
            '"execution_quality":{"summary":"execution","bullets":[]},'
            '"scanner_filters":{"summary":"filters","bullets":[]},'
            '"guard_approval_result":{"summary":"guard","bullets":[]},'
            '"reporter_evaluation":{"summary":"reporter","status":"pending","grade":"N/A","bullets":[]},'
            '"errors_weaknesses_improvement_points":{"summary":"none","bullets":[]},'
            '"full_timeline":[{"event":"entry","ts":"2026-03-18T00:00:00+00:00","description":"entry"}],'
            '"final_operator_conclusion":{"summary":"hold","current_action":"HOLD","watch_next":["watch"],"thesis_invalidation":["stop"]}}'
        )


class _CapturePolicyRouter:
    last_policies: List[Dict[str, Any]] = []

    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_CapturePolicyRouter":
        _CapturePolicyRouter.last_policies = []
        return _CapturePolicyRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        _CapturePolicyRouter.last_policies.append(dict(policy or {}))
        return (
            '{"executive_summary":{"headline":"HOLD 000660","action":"HOLD","symbol":"000660","confidence":"high","summary":"ok"},'
            '"market_context_at_entry":{"summary":"context","bullets":["vix noted"]},'
            '"why_this_symbol_was_chosen":{"summary":"rank #1","bullets":["top value"]},'
            '"entry_decision":{"summary":"entry","bullets":[]},'
            '"holding_monitoring_story":{"summary":"hold","bullets":[]},'
            '"exit_decision":{"summary":"open trade","bullets":[]},'
            '"execution_quality":{"summary":"execution","bullets":[]},'
            '"scanner_filters":{"summary":"filters","bullets":[]},'
            '"guard_approval_result":{"summary":"guard","bullets":[]},'
            '"reporter_evaluation":{"summary":"reporter","status":"pending","grade":"N/A","bullets":[]},'
            '"errors_weaknesses_improvement_points":{"summary":"none","bullets":[]},'
            '"full_timeline":[{"event":"entry","ts":"2026-03-18T00:00:00+00:00","description":"entry"}],'
            '"final_operator_conclusion":{"summary":"hold","current_action":"HOLD","watch_next":["watch"],"thesis_invalidation":["stop"]}}'
        )


class _SlowRouter:
    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_SlowRouter":
        return _SlowRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        time.sleep(0.2)
        return "{}"


def _story_input() -> Dict[str, Any]:
    return {
        "trade_id": "TRD_20260318_000660_01",
        "story_id": "TRD_20260318_000660_01",
        "run_id": "run-1",
        "day": "2026-03-18",
        "symbol": "000660",
        "action": "HOLD",
        "status": "open",
        "story_type": "simulation",
        "execution_mode_label": "simulation",
        "monitor_reason_human": {"posture": "HOLD"},
    }


def test_scanner_fallback_trade_summary_reanchors_to_actual_traded_symbol() -> None:
    scanner_reason = {
        "selected_symbol": "005380",
        "selected_rank": 3,
        "selected_score": 1.606,
        "confidence": 0.965,
        "selected_sources": [],
        "top_candidates": [
            {"rank": 1, "symbol": "034020", "score_total": 1.703, "risk_score": 0.085, "confidence": 0.99},
            {"rank": 2, "symbol": "036930", "score_total": 1.639, "risk_score": 0.454, "confidence": 0.96},
            {"rank": 3, "symbol": "005380", "score_total": 1.606, "risk_score": 0.146, "confidence": 0.965},
        ],
        "monitor_fallback_used": True,
        "scanner_top_pick_symbol": "034020",
        "monitor_fallback_reason": "breakout not ready",
        "monitor_trigger_reason": "breakout above recent high with vwap hold and volume confirmation",
        "scanner_selection_trace": {
            "selected_symbol": "005380",
            "selected_rank": 3,
            "monitor_fallback_used": True,
            "scanner_top_pick_symbol": "034020",
        },
    }
    market_context = {"playbook": "defensive"}
    entry_summary = {"reason_human": "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation"}
    monitor_reason = {
        "entry_condition_scores": {"confidence_score": 0.55, "confidence_threshold": 0.55},
        "entry_condition_path": "breakout_path",
    }

    scanner_summary = mod._build_scanner_choice_summary(scanner_reason, market_context)
    entry_summary_text = mod._build_entry_decision_summary(
        entry_summary,
        scanner_reason,
        market_context,
        monitor_reason,
        "BUY",
    )

    assert "005380" in scanner_summary
    assert "034020" in scanner_summary
    assert "실제 진입 종목" in scanner_summary
    assert "차순위 재평가 3위" in scanner_summary
    assert "스캐너 1순위" not in scanner_summary
    assert "005380" in entry_summary_text
    assert "034020" in entry_summary_text
    assert "전환" in entry_summary_text
    assert "차순위 재평가 3위" in entry_summary_text


def test_ai_trade_report_merge_replaces_scanner_execution_mismatch_with_fallback() -> None:
    story_input = _story_input()
    story_input["symbol"] = "005930"
    story_input["status"] = "closed"
    story_input["action"] = "SELL"
    story_input["scanner_reason_human"] = {
        "selected_symbol": "005930",
        "selected_rank": 2,
        "universe_size": 6,
        "selected_score": 1.105,
        "confidence": 0.693,
        "monitor_fallback_used": True,
        "scanner_top_pick_symbol": "000660",
        "monitor_fallback_reason": "breakout above recent high with vwap structure confirmation",
        "top_candidates": [
            {"rank": 1, "symbol": "000660", "score_total": 1.435, "risk_score": 0.476, "confidence": 0.805},
            {"rank": 2, "symbol": "005930", "score_total": 1.105, "risk_score": 0.642, "confidence": 0.693},
        ],
        "scanner_selection_trace": {
            "selected_symbol": "005930",
            "selected_rank": 2,
            "monitor_fallback_used": True,
            "scanner_top_pick_symbol": "000660",
            "monitor_selected_symbol": "005930",
            "monitor_fallback_reason": "breakout above recent high with vwap structure confirmation",
            "ranked_candidates": [
                {"rank": 1, "symbol": "000660", "score_total": 1.435, "risk_score": 0.476, "confidence": 0.805},
                {"rank": 2, "symbol": "005930", "score_total": 1.105, "risk_score": 0.642, "confidence": 0.693},
            ],
        },
    }

    report = mod._merge_trade_report_candidate(
        story_input,
        {
            "executive_summary": {"headline": "SELL 005930", "action": "SELL", "symbol": "005930", "confidence": "high", "summary": "ok"},
            "market_context_at_entry": {"summary": "context", "bullets": []},
            "strategist_summary": {"summary": "strategist", "bullets": []},
            "why_this_symbol_was_chosen": {
                "summary": "스캐너는 005930을 2위로 선정했습니다. 그러나 최종 선택에서 1위가 아닌 2위가 선택되는 불일치가 발생했습니다.",
                "bullets": [
                    "스캐너 선택 종목: 000660 (순위 1위, 점수 1.435)",
                    "실행 종목: 005930 (스캐너 선택과 불일치)",
                ],
            },
            "entry_decision": {"summary": "entry", "bullets": []},
            "holding_monitoring_story": {"summary": "holding", "bullets": []},
            "exit_decision": {"summary": "exit", "bullets": []},
            "execution_quality": {"summary": "execution", "bullets": []},
            "scanner_filters": {"summary": "filters", "bullets": []},
            "guard_approval_result": {"summary": "guard", "bullets": []},
            "reporter_evaluation": {"summary": "reporter", "status": "pending", "grade": "N/A", "bullets": []},
            "errors_weaknesses_improvement_points": {"summary": "none", "bullets": []},
            "full_timeline": [],
            "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        },
        status="ok",
        mode="ai",
        model="openrouter/free",
        reason="ok",
    )

    why = report["why_this_symbol_was_chosen"]
    assert "불일치" not in why["summary"]
    assert "스캐너 상위 후보 000660" in why["summary"]
    assert "차순위 재평가 2위" in why["summary"]
    assert "스캐너 1순위" not in why["summary"]
    assert not any("불일치" in row for row in why["bullets"])
    assert not any(str(row).startswith("스캐너 선택 종목:") for row in why["bullets"])


def test_trade_summary_monitor_fallback_labels_reassessment_rank_and_score() -> None:
    report = {
        "trade_id": "TRD_20260428_005010_01",
        "symbol": "005010",
        "status": "closed",
        "story_type": "simulation",
        "execution_mode_label": "simulation (mock broker)",
        "action": "SELL",
        "shared_facts": {"symbol": "005010", "status": "closed", "action": "SELL", "pnl": -273, "pnl_pct": -0.00038},
        "market_context_at_entry": {"summary": "시장 중립", "playbook": "defensive"},
        "why_this_symbol_was_chosen": {
            "symbol": "005010",
            "selected_rank": 1,
            "universe_size": 6,
            "basis": "거래대금, turnover and volume, 감성 지원",
            "bullets": [
                "스캐너 1순위 005380은 눌림목 rebound above vwap with volume confirmation 이유로 막혔고 실제 진입 종목은 005010입니다.",
            ],
            "scanner_selection_trace": {
                "ranked_candidates": [
                    {"rank": 1, "symbol": "005380", "score_total": 1.611},
                    {"rank": 2, "symbol": "001510", "score_total": 1.418},
                ],
                "selected_symbol": "005010",
                "selected_rank": 1,
                "monitor_fallback_used": True,
                "selection_path": "monitor_fallback_from_scanner_top_pick",
                "scanner_top_pick_symbol": "005380",
                "monitor_selected_symbol": "005010",
                "monitor_fallback_reason": "pullback rebound above vwap with volume confirmation",
                "news_scanner_contribution": {"selected_score_total": 0.6545414868109848},
            },
        },
        "entry_decision": {"summary": "진입은 눌림목 rebound above vwap with volume confirmation 조건에서 실행됐습니다.", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "reporter_evaluation": {"bullets": []},
        "memory_application_surface": {},
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL"},
        "full_timeline": [],
    }

    summary = mod.render_trade_summary_markdown(report)
    summary_input = mod.build_trade_summary_input(report)

    assert "* 선정 경로: 차순위 재평가" in summary
    assert "* 재평가 순위: 1위" in summary
    assert "* 재평가 점수: 0.655" in summary
    assert "스캐너 상위 후보 005380 보류 후 005010" in summary
    assert "VWAP 위 되돌림 반등과 거래량 확인" in summary
    assert "스캐너 순위: 1위" not in summary
    assert "스캐너 1순위 005380" not in summary
    assert "turnover and volume" not in summary
    assert "회전율/거래량" in summary
    assert summary_input["decision_flow"]["scanner_rank_basis"] == "monitor_fallback_reassessment"
    assert summary_input["decision_flow"]["scanner_score"] == 0.6545414868109848
    assert summary_input["decision_flow"]["selection_basis"] == "거래대금, 회전율/거래량, 감성 지원"


def test_trade_summary_ignores_later_unrelated_candidate_cascade_for_fallback_trade() -> None:
    report = {
        "trade_id": "TRD_20260511_078890_02",
        "symbol": "078890",
        "status": "closed",
        "story_type": "simulation",
        "execution_mode_label": "simulation (mock broker)",
        "action": "SELL",
        "shared_facts": {"symbol": "078890", "status": "closed", "action": "SELL", "pnl": 25718, "pnl_pct": 0.0086},
        "market_context_at_entry": {"summary": "시장 강세", "playbook": "pullback"},
        "why_this_symbol_was_chosen": {
            "symbol": "078890",
            "selected_rank": 2,
            "basis": "감성 지원",
            "scanner_selection_trace": {
                "selected_symbol": "078890",
                "selected_rank": 2,
                "monitor_fallback_used": True,
                "selection_path": "monitor_fallback_from_scanner_top_pick",
                "scanner_top_pick_symbol": "000660",
                "monitor_selected_symbol": "078890",
                "monitor_fallback_reason": "breakout above recent high with vwap hold and volume confirmation",
                "ranked_candidates": [
                    {"rank": 1, "symbol": "000660", "score_total": 1.12},
                    {"rank": 2, "symbol": "078890", "score_total": 0.97},
                ],
            },
        },
        "entry_decision": {"summary": "진입은 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파 조건에서 실행됐습니다.", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "reporter_evaluation": {"bullets": []},
        "memory_application_surface": {},
        "entry_execution_visibility": {
            "commander_entry_control": {
                "max_priority_rank": 10,
                "max_runner_ups": 9,
                "cascade_enabled": True,
            },
            "monitor_entry_candidate_cascade": {
                "attempted": False,
                "eligible": False,
                "cascade_enabled": True,
                "blocked_reason": "max_positions_reached",
                "top_pick_symbol": "005930",
                "final_selected_symbol": "005930",
                "max_priority_rank": 10,
                "max_runner_ups": 9,
            },
        },
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL"},
        "full_timeline": [],
    }

    summary = mod.render_trade_summary_markdown(report)

    assert "스캐너 상위 후보 000660 보류 후 078890" in summary
    assert "최종 후보: 005930" not in summary
    assert "1순위 005930" not in summary
    assert "max_positions_reached" not in summary


def test_attach_report_status_matrix_prefers_trade_read_model_for_separated_fallback(tmp_path, monkeypatch) -> None:
    trade_dir = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_20260318_000660_01"
    trade_dir.mkdir(parents=True)
    input_path = trade_dir / "ai_trade_report_input.json"
    input_path.write_text("{}", encoding="utf-8")

    sentinel_trade_model = {
        "trade_id": "TRD_20260318_000660_01",
        "from_trade_read_model": True,
        "applied_policy": {"llm": {"reporter": {"intraday": {"primary": "minimax/minimax-m2.5"}}}},
    }
    captured: dict[str, object] = {}

    def _fake_build_trade_read_model(path: str) -> dict[str, object]:
        captured["trade_read_model_path"] = path
        return dict(sentinel_trade_model)

    def _fake_build_separated_report(*, trade_model: dict[str, object], model: str | None = None, execution_profile=None):
        captured["trade_model"] = dict(trade_model)
        captured["model"] = model
        captured["execution_profile"] = execution_profile
        return {
            "fact_payload": {"trade": dict(trade_model)},
            "narrative": {"status": "ok", "summary": "used canonical trade read model"},
        }

    monkeypatch.setattr("libs.reporting.trade_read_model.build_trade_read_model", _fake_build_trade_read_model)
    monkeypatch.setattr("libs.reporting.fact_narrative_report.build_separated_report", _fake_build_separated_report)

    story_input = _story_input()
    story_input.update(
        {
            "status": "closed",
            "action": "SELL",
            "enable_separated_narrative": True,
            "skip_separated_report_llm": False,
            "artifacts": {"ai_trade_report_input_json": str(input_path)},
        }
    )

    out = mod._attach_report_status_matrix({}, story_input, ai_trade_report_status="ok")

    assert captured["trade_read_model_path"] == str(trade_dir)
    assert captured["trade_model"] == sentinel_trade_model
    assert ((out.get("fact_payload") or {}).get("trade") or {}).get("from_trade_read_model") is True
    assert (out.get("narrative") or {}).get("status") == "ok"


def test_deterministic_trade_report_does_not_invoke_hidden_fact_narrative_llm(monkeypatch) -> None:
    class ExplodingRouter:
        client = object()

        @staticmethod
        def from_env() -> "ExplodingRouter":
            return ExplodingRouter()

        def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
            raise AssertionError("deterministic report should not trigger hidden fact_narrative LLM calls")

    monkeypatch.setattr("libs.reporting.fact_narrative_report.LLMRouter", ExplodingRouter)

    report = mod.build_deterministic_trade_report(_story_input())
    narrative = report.get("narrative") if isinstance(report.get("narrative"), dict) else {}
    assert narrative.get("status") == "skipped"
    assert narrative.get("reason") == "runtime_separated_narrative_disabled"
    assert narrative.get("llm_call_skipped") is True


def test_ai_trade_report_can_skip_hidden_separated_report_llm_for_intraday_bundle(monkeypatch) -> None:
    class ExplodingRouter:
        client = object()

        @staticmethod
        def from_env() -> "ExplodingRouter":
            return ExplodingRouter()

        def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
            raise AssertionError("intraday bundle path should skip hidden separated-report LLM calls")

    monkeypatch.setattr(mod, "LLMRouter", _CapturePolicyRouter)
    monkeypatch.setattr("libs.reporting.fact_narrative_report.LLMRouter", ExplodingRouter)
    story_input = _story_input()
    story_input["status"] = "closed"
    story_input["action"] = "SELL"
    story_input["report_runtime_mode"] = "intraday_bundle"
    story_input["skip_separated_report_llm"] = True

    report = mod.build_ai_trade_report(story_input, enabled=True, model="free")

    assert report["generation"]["status"] == "ok"
    narrative = report.get("narrative") if isinstance(report.get("narrative"), dict) else {}
    assert narrative.get("status") == "skipped"
    assert narrative.get("reason") == "intraday_bundle_skip_separated_report_llm"
    assert narrative.get("llm_call_skipped") is True


def test_build_shared_summary_seed_prefers_trade_read_model_facts_when_artifacts_exist(tmp_path, monkeypatch) -> None:
    trade_dir = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_20260318_000660_01"
    trade_dir.mkdir(parents=True)
    input_path = trade_dir / "ai_trade_report_input.json"
    input_path.write_text("{}", encoding="utf-8")

    sentinel_trade_model = {
        "facts": {
            "hold_duration_sec": 900,
            "exit_reason": "trade_read_model_exit",
            "pnl": 12345.0,
            "pnl_pct": 0.0175,
        },
        "context": {
            "monitor": {
                "exit_trigger": "peak_drawdown",
                "thresholds_snapshot": {"effective_stop_loss_pct": 0.0092},
            }
        },
        "provenance": {"schema_version": "trade_read_model.v2"},
    }

    def _fake_build_trade_read_model(path: str) -> dict[str, object]:
        assert path == str(trade_dir)
        return dict(sentinel_trade_model)

    monkeypatch.setattr("libs.reporting.trade_read_model.build_trade_read_model", _fake_build_trade_read_model)

    story_input = _story_input()
    story_input.update(
        {
            "artifacts": {"ai_trade_report_input_json": str(input_path)},
            "status": "closed",
            "action": "SELL",
            "entry_summary": {},
            "exit_summary": {},
            "canonical_agent_artifacts": {"monitor": {}},
            "monitor_reason_human": {},
        }
    )

    seed = mod._build_shared_summary_seed(story_input)
    facts = seed.get("resolved_trade_facts") if isinstance(seed.get("resolved_trade_facts"), dict) else {}

    assert facts.get("holding_duration") == "900"
    assert facts.get("exit_reason") == "trade_read_model_exit"
    assert facts.get("pnl") == 12345.0
    assert facts.get("pnl_pct") == 0.0175
    assert (facts.get("data_source") or {}).get("holding_duration") == "trade_read_model"
    assert (seed.get("monitor_decision") or {}).get("reason_code") == "peak_drawdown"
    assert ((seed.get("monitor_decision") or {}).get("thresholds") or {}).get("effective_stop_loss_pct") == 0.0092


def test_build_shared_summary_seed_prefers_trade_read_model_context_when_runtime_sections_missing(tmp_path, monkeypatch) -> None:
    trade_dir = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_20260318_000660_01"
    trade_dir.mkdir(parents=True)
    input_path = trade_dir / "ai_trade_report_input.json"
    input_path.write_text("{}", encoding="utf-8")

    sentinel_trade_model = {
        "facts": {},
        "context": {
            "scanner": {
                "summary": "trade_read_model scanner summary",
                "score_drivers": {"trading_value": 0.22, "trend": 0.17},
                "top_candidates": [{"rank": 1, "symbol": "000660", "score_total": 1.286}],
            },
            "monitor": {
                "entry_reason": "trade_read_model monitor entry",
                "blocker_trace": {"threshold_shortfalls": ["volume ratio 0.10 below min 0.75"]},
                "stop_policy_trace": {"effective_stop_loss_pct": 0.0092, "take_profit_pct": 0.025},
            },
        },
        "provenance": {"schema_version": "trade_read_model.v2"},
    }

    monkeypatch.setattr(
        "libs.reporting.trade_read_model.build_trade_read_model",
        lambda path: dict(sentinel_trade_model),
    )

    story_input = _story_input()
    story_input.update(
        {
            "artifacts": {"ai_trade_report_input_json": str(input_path)},
            "scanner_reason_human": {},
            "scanner_selection_trace": {},
            "monitor_reason_human": {},
            "monitor_blocker_trace": {},
            "monitor_stop_policy_trace": {},
            "canonical_agent_artifacts": {},
        }
    )

    seed = mod._build_shared_summary_seed(story_input)
    scanner_reasoning = seed.get("scanner_reasoning") if isinstance(seed.get("scanner_reasoning"), dict) else {}
    monitor_reasoning = seed.get("monitor_reasoning") if isinstance(seed.get("monitor_reasoning"), dict) else {}

    assert scanner_reasoning.get("selection_reason_with_bias") == "trade_read_model scanner summary"
    assert ((scanner_reasoning.get("selection_trace") or {}).get("selected_symbol_score_drivers") or {}).get("trading_value") == 0.22
    assert (((scanner_reasoning.get("selection_trace") or {}).get("ranked_candidates") or [])[0] or {}).get("symbol") == "000660"
    assert monitor_reasoning.get("entry_check_summary") == "trade_read_model monitor entry"
    assert monitor_reasoning.get("threshold_shortfalls") == ["volume ratio 0.10 below min 0.75"]
    assert (monitor_reasoning.get("monitor_stop_policy_trace") or {}).get("effective_stop_loss_pct") == 0.0092


def test_build_shared_summary_seed_prefers_broker_truth_from_exit_execution_details() -> None:
    seed = mod._build_shared_summary_seed(
        {
            "trade_id": "TRD_20260420_005930_01",
            "story_id": "TRD_20260420_005930_01",
            "symbol": "005930",
            "action": "SELL",
            "status": "closed",
            "monitor_reason_human": {"pnl": -500, "pnl_pct": -0.01},
            "exit_execution_details": {
                "broker_realized_pnl": -320.0,
                "broker_realized_pnl_pct": -0.0064,
                "broker_fee": 14,
                "broker_tax": 9,
                "pnl_truth_source": "kiwoom.ka10077",
                "broker_day_truth_source": "kiwoom.ka10077",
                "broker_day_match_mode": "symbol_price_qty",
                "broker_day_authoritative": True,
                "broker_day_row_count": 1,
            },
        }
    )

    facts = seed.get("resolved_trade_facts") if isinstance(seed.get("resolved_trade_facts"), dict) else {}
    data_source = facts.get("data_source") if isinstance(facts.get("data_source"), dict) else {}

    assert facts.get("pnl") == -320.0
    assert facts.get("pnl_pct") == -0.0064
    assert facts.get("broker_fee") == 14
    assert facts.get("broker_tax") == 9
    assert facts.get("pnl_truth_source") == "kiwoom.ka10077"
    assert facts.get("broker_day_truth_source") == "kiwoom.ka10077"
    assert facts.get("broker_day_match_mode") == "symbol_price_qty"
    assert facts.get("broker_day_authoritative") is True
    assert facts.get("broker_day_row_count") == 1
    assert data_source.get("pnl") == "kiwoom.ka10077"
    assert data_source.get("pnl_pct") == "kiwoom.ka10077"


def test_build_shared_summary_seed_infers_pnl_pct_from_exit_fill_and_account_snapshot() -> None:
    seed = mod._build_shared_summary_seed(
        {
            "trade_id": "TRD_20260421_005380_01",
            "story_id": "TRD_20260421_005380_01",
            "symbol": "005380",
            "action": "SELL",
            "status": "closed",
            "exit_execution_details": {
                "filled_price": 537000.0,
                "filled_qty": 1,
                "broker_truth_source": "kiwoom.order_status",
            },
            "canonical_monitor": {
                "current_price": 536000.0,
                "account_pnl_ratio": -0.0108,
            },
            "monitor_reason_human": {
                "current_price": 536000.0,
                "current_drawdown": -0.0037,
            },
        }
    )

    facts = seed.get("resolved_trade_facts") if isinstance(seed.get("resolved_trade_facts"), dict) else {}
    assert round(float(facts.get("pnl_pct") or 0.0), 4) == -0.0090
    assert facts.get("pnl_truth_source") == "broker_fill_account_snapshot_estimate"


def test_build_shared_summary_seed_surfaces_price_truth_fields() -> None:
    seed = mod._build_shared_summary_seed(
        {
            "trade_id": "TRD_20260420_005930_02",
            "story_id": "TRD_20260420_005930_02",
            "symbol": "005930",
            "action": "SELL",
            "status": "closed",
            "entry_execution_details": {
                "filled_price": 69800,
                "broker_truth_source": "kiwoom.order_status",
            },
            "exit_execution_details": {
                "filled_price": 70100,
                "broker_truth_source": "kiwoom.order_status",
            },
            "monitor_reason_human": {
                "current_price": 70050,
                "price_source": "state.minute_ohlcv_by_symbol.close",
            },
        }
    )

    facts = seed.get("resolved_trade_facts") if isinstance(seed.get("resolved_trade_facts"), dict) else {}
    assert facts.get("broker_fill_price") == 70100.0
    assert facts.get("broker_buy_price") == 69800.0
    assert facts.get("monitor_mark_price") == 70050.0
    assert facts.get("account_mark_price") is None
    assert facts.get("price_truth_source") == "broker_fill"


def test_build_deterministic_trade_report_adds_truth_surface() -> None:
    report = mod.build_deterministic_trade_report(
        {
            "trade_id": "TRD_20260420_005930_03",
            "story_id": "TRD_20260420_005930_03",
            "symbol": "005930",
            "action": "SELL",
            "status": "closed",
            "execution_mode_label": "real broker",
            "exit_execution_details": {
                "filled_price": 70100.0,
                "broker_truth_source": "kiwoom.order_status",
                "broker_realized_pnl": -320.0,
                "broker_realized_pnl_pct": -0.0064,
                "broker_fee": 14,
                "broker_tax": 9,
                "pnl_truth_source": "kiwoom.ka10077",
                "broker_day_truth_source": "kiwoom.ka10077",
                "broker_day_match_mode": "symbol_price_qty",
                "broker_day_authoritative": True,
                "broker_day_row_count": 1,
            },
            "monitor_reason_human": {
                "current_price": 70050.0,
                "price_source": "state.minute_ohlcv_by_symbol.close",
            },
        }
    )

    truth_surface = report.get("truth_surface") if isinstance(report.get("truth_surface"), dict) else {}
    price = truth_surface.get("price") if isinstance(truth_surface.get("price"), dict) else {}
    pnl = truth_surface.get("pnl") if isinstance(truth_surface.get("pnl"), dict) else {}
    availability = truth_surface.get("availability") if isinstance(truth_surface.get("availability"), dict) else {}

    assert price.get("broker_fill_price") == 70100.0
    assert price.get("monitor_mark_price") == 70050.0
    assert price.get("price_truth_source") == "broker_fill"
    assert pnl.get("value") == -320.0
    assert pnl.get("pct") == -0.0064
    assert pnl.get("broker_fee") == 14
    assert pnl.get("broker_tax") == 9
    assert pnl.get("pnl_truth_source") == "kiwoom.ka10077"
    assert pnl.get("broker_day_truth_source") == "kiwoom.ka10077"
    assert pnl.get("broker_day_match_mode") == "symbol_price_qty"
    assert pnl.get("broker_day_authoritative") is True
    assert pnl.get("broker_day_row_count") == 1
    assert availability.get("broker_fill_present") is True
    assert availability.get("broker_pnl_present") is True
    assert availability.get("broker_day_authoritative") is True


def test_truth_surface_separates_broker_day_match_confidence_from_authority() -> None:
    exact = build_trade_report_truth_surface(
        {
            "pnl": -1000,
            "pnl_pct": -0.01,
            "pnl_truth_source": "kiwoom.ka10077",
            "broker_day_match_mode": "symbol_split_buy_sell_qty_exact",
            "broker_day_authoritative": True,
        }
    )
    ambiguous = build_trade_report_truth_surface(
        {
            "pnl": "unavailable",
            "pnl_pct": -0.01,
            "pnl_truth_source": "kiwoom.ka10077",
            "broker_day_match_mode": "ambiguous_symbol_rows",
            "broker_day_authoritative": False,
        }
    )

    assert exact["pnl"]["broker_day_match_status"] == "exact"
    assert exact["pnl"]["broker_day_match_confidence"] == "high"
    assert ambiguous["pnl"]["broker_day_match_status"] == "ambiguous"
    assert ambiguous["pnl"]["broker_day_match_confidence"] == "low"


def test_fallback_report_prefers_trade_read_model_strategist_and_scanner_context_when_runtime_sections_missing(tmp_path, monkeypatch) -> None:
    trade_dir = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_20260318_000660_01"
    trade_dir.mkdir(parents=True)
    input_path = trade_dir / "ai_trade_report_input.json"
    input_path.write_text("{}", encoding="utf-8")

    sentinel_trade_model = {
        "facts": {},
        "context": {
            "report_section_seeds": {
                "market_context_at_entry": {
                    "summary": "Canonical section seed for market context.",
                    "bullets": ["seed market bullet"],
                },
                "strategist_summary": {
                    "summary": "Canonical section seed for strategist summary.",
                    "bullets": ["seed strategist bullet"],
                },
                "why_this_symbol_was_chosen": {
                    "summary": "Canonical section seed for symbol choice.",
                    "bullets": ["seed why bullet"],
                },
                "entry_decision": {
                    "summary": "Canonical section seed for entry decision.",
                    "bullets": ["seed entry bullet"],
                },
                "holding_monitoring_story": {
                    "summary": "Canonical section seed for holding story.",
                    "bullets": ["seed holding bullet"],
                },
                "exit_decision": {
                    "summary": "Canonical section seed for exit decision.",
                    "bullets": ["seed exit bullet"],
                },
                "scanner_filters": {
                    "summary": "Canonical section seed for scanner filters.",
                    "bullets": ["seed filter bullet"],
                },
                "execution_quality": {
                    "summary": "Canonical section seed for execution quality.",
                    "bullets": ["seed execution bullet"],
                },
                "guard_approval_result": {
                    "summary": "Canonical section seed for guard approval.",
                    "bullets": ["seed guard bullet"],
                },
                "reporter_evaluation": {
                    "summary": "Canonical section seed for reporter evaluation.",
                    "bullets": ["seed reporter bullet"],
                    "status": "pending",
                    "grade": "B",
                },
                "final_operator_conclusion": {
                    "summary": "Canonical section seed for final conclusion.",
                    "current_action": "SELL",
                    "watch_next": ["seed watch"],
                    "thesis_invalidation": ["seed invalidate"],
                },
            },
            "scanner": {
                "summary": "Scanner selected 000660 from canonical ranking.",
                "score_drivers": {"momentum": 0.209, "trading_value": 0.2},
                "top_candidates": [{"rank": 1, "symbol": "000660", "score_total": 1.286}],
            },
            "strategist": {
                "playbook": "breakout",
                "policy_source": "canonical.strategist",
                "themes": ["semiconductor_leaders"],
                "market_context_summary": "Strategist framed the tape as neutral-to-risk-on for semiconductor leaders.",
            },
        },
        "provenance": {"schema_version": "trade_read_model.v2"},
    }

    monkeypatch.setattr(
        "libs.reporting.trade_read_model.build_trade_read_model",
        lambda path: dict(sentinel_trade_model),
    )

    story_input = _story_input()
    story_input.update(
        {
            "artifacts": {"ai_trade_report_input_json": str(input_path)},
            "market_context_human": {},
            "scanner_reason_human": {},
            "monitor_reason_human": {},
            "guard_reason_human": {},
            "execution_outcome_human": {},
            "reporter_status_human": {},
            "operator_conclusion_human": {},
            "entry_summary": {
                "run_id": "run-entry",
                "ts": "2026-03-18T00:00:00+00:00",
                "action": "BUY",
            },
        }
    )

    report = mod._fallback_report(
        story_input,
        status="salvaged",
        mode="ai",
        model="openrouter/free",
        reason="partial",
    )

    assert report["market_context_at_entry"]["playbook"] == "breakout"
    assert report["market_context_at_entry"]["policy_source"] == "canonical.strategist"
    assert "semiconductor_leaders" in list(report["market_context_at_entry"]["themes"] or [])
    assert report["market_context_at_entry"]["summary"] == "Canonical section seed for market context."
    assert report["why_this_symbol_was_chosen"]["selected_rank"] == 1
    assert report["why_this_symbol_was_chosen"]["scanner_selection_trace"]["selected_symbol"] == "000660"
    assert any("모멘텀 0.209" in row for row in report["why_this_symbol_was_chosen"]["bullets"])
    assert report["strategist_summary"]["summary"] == "Canonical section seed for strategist summary."
    assert report["entry_decision"]["summary"] == "Canonical section seed for entry decision."
    assert report["holding_monitoring_story"]["summary"] == "Canonical section seed for holding story."
    assert report["exit_decision"]["summary"] == "Canonical section seed for exit decision."
    assert report["scanner_filters"]["summary"] == "Canonical section seed for scanner filters."
    assert report["scanner_filters"]["bullets"] == ["seed filter bullet"]
    assert report["execution_quality"]["summary"] == "Canonical section seed for execution quality."
    assert report["guard_approval_result"]["summary"] == "Canonical section seed for guard approval."
    assert report["reporter_evaluation"]["summary"] == "Canonical section seed for reporter evaluation."
    assert report["reporter_evaluation"]["status"] == "pending"
    assert report["reporter_evaluation"]["grade"] == "B"
    assert report["final_operator_conclusion"]["summary"] == "Canonical section seed for final conclusion."
    assert report["final_operator_conclusion"]["current_action"] == "SELL"
    assert report["final_operator_conclusion"]["watch_next"] == ["seed watch"]
    assert report["final_operator_conclusion"]["thesis_invalidation"] == ["seed invalidate"]


def test_build_ai_trade_report_compact_input_prefers_section_seeds_for_aux_sections(tmp_path, monkeypatch) -> None:
    trade_dir = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_20260318_000660_01"
    trade_dir.mkdir(parents=True)
    input_path = trade_dir / "ai_trade_report_input.json"
    input_path.write_text("{}", encoding="utf-8")

    sentinel_trade_model = {
        "facts": {},
        "context": {
            "report_section_seeds": {
                "execution_quality": {
                    "summary": "Seed execution summary.",
                    "bullets": ["seed execution bullet"],
                },
                "guard_approval_result": {
                    "summary": "Seed guard summary.",
                    "bullets": ["seed guard bullet"],
                    "status": "approved",
                },
                "reporter_evaluation": {
                    "summary": "Seed reporter summary.",
                    "bullets": ["seed reporter bullet"],
                    "status": "pending",
                    "grade": "B",
                },
                "final_operator_conclusion": {
                    "summary": "Seed final conclusion.",
                    "current_action": "SELL",
                    "watch_next": ["seed watch"],
                    "thesis_invalidation": ["seed invalidate"],
                },
            },
        },
        "provenance": {"schema_version": "trade_read_model.v2"},
    }

    monkeypatch.setattr(
        "libs.reporting.trade_read_model.build_trade_read_model",
        lambda path: dict(sentinel_trade_model),
    )

    story_input = _story_input()
    story_input.update(
        {
            "artifacts": {"ai_trade_report_input_json": str(input_path)},
            "guard_reason_human": {},
            "execution_outcome_human": {},
            "reporter_status_human": {},
            "operator_conclusion_human": {},
        }
    )

    compact_input = mod.build_ai_trade_report_compact_input(story_input)

    assert compact_input["guard"]["summary"] == "Seed guard summary."
    assert compact_input["guard"]["status"] == "approved"
    assert compact_input["guard"]["bullets"] == ["seed guard bullet"]
    assert compact_input["execution"]["summary"] == "Seed execution summary."
    assert compact_input["execution"]["bullets"] == ["seed execution bullet"]
    assert compact_input["reporter"]["summary"] == "Seed reporter summary."
    assert compact_input["reporter"]["status"] == "pending"
    assert compact_input["reporter"]["grade"] == "B"
    assert compact_input["reporter"]["bullets"] == ["seed reporter bullet"]
    assert compact_input["operator_conclusion"]["summary"] == "Seed final conclusion."
    assert compact_input["operator_conclusion"]["current_action"] == "SELL"
    assert compact_input["operator_conclusion"]["watch_next"] == ["seed watch"]
    assert compact_input["operator_conclusion"]["thesis_invalidation"] == ["seed invalidate"]
    assert compact_input["report_section_seeds"]["execution_quality"]["summary"] == "Seed execution summary."
    assert compact_input["report_section_seeds"]["guard_approval_result"]["summary"] == "Seed guard summary."
    assert compact_input["report_section_seeds"]["reporter_evaluation"]["summary"] == "Seed reporter summary."
    assert compact_input["report_section_seeds"]["final_operator_conclusion"]["summary"] == "Seed final conclusion."


def test_build_ai_trade_report_compact_input_refreshes_placeholder_execution_seed(tmp_path, monkeypatch) -> None:
    trade_dir = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_20260318_000660_01"
    trade_dir.mkdir(parents=True)
    input_path = trade_dir / "ai_trade_report_input.json"
    input_path.write_text("{}", encoding="utf-8")

    sentinel_trade_model = {
        "facts": {},
        "context": {
            "report_section_seeds": {
                "execution_quality": {
                    "summary": "Execution outcome summary was 기록되지 않음. 체결 기준 가격은 17650.00였습니다.",
                    "bullets": ["Execution outcome: recorded"],
                }
            }
        },
        "provenance": {"schema_version": "trade_read_model.v2"},
    }

    monkeypatch.setattr(
        "libs.reporting.trade_read_model.build_trade_read_model",
        lambda path: dict(sentinel_trade_model),
    )

    story_input = _story_input()
    story_input.update(
        {
            "artifacts": {"ai_trade_report_input_json": str(input_path)},
            "execution_outcome_human": {
                "summary": "000660 1주 매도 주문은 실거래로 체결됐고 체결 기준 가격은 17650.00였습니다.",
                "status": "filled",
                "bullets": ["주문 번호는 0123456였습니다.", "체결 기준 가격은 17650.00였습니다."],
            },
        }
    )

    compact_input = mod.build_ai_trade_report_compact_input(story_input)

    assert compact_input["execution"]["summary"] == "000660 1주 매도 주문은 실거래로 체결됐고 체결 기준 가격은 17650.00였습니다."
    assert compact_input["report_section_seeds"]["execution_quality"]["summary"] == "000660 1주 매도 주문은 실거래로 체결됐고 체결 기준 가격은 17650.00였습니다."


def test_build_ai_trade_report_compact_input_refreshes_placeholder_reporter_summary(tmp_path, monkeypatch) -> None:
    trade_dir = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_20260318_000660_01"
    trade_dir.mkdir(parents=True)
    input_path = trade_dir / "ai_trade_report_input.json"
    input_path.write_text("{}", encoding="utf-8")

    sentinel_trade_model = {
        "facts": {},
        "context": {
            "report_section_seeds": {
                "reporter_evaluation": {
                    "summary": "이번 거래는 보유 이후 되밀림 관리가 더 크게 작동한 케이스로 보입니다.",
                    "bullets": ["seed reporter bullet"],
                    "status": "pending",
                    "grade": "B",
                }
            }
        },
        "provenance": {"schema_version": "trade_read_model.v2"},
    }

    monkeypatch.setattr(
        "libs.reporting.trade_read_model.build_trade_read_model",
        lambda path: dict(sentinel_trade_model),
    )

    story_input = _story_input()
    story_input.update(
        {
            "artifacts": {"ai_trade_report_input_json": str(input_path)},
            "reporter_status_human": {
                "summary": "Same-day reporter analysis was not generated yet.",
                "status": "missing",
                "grade": "N/A",
                "bullets": ["Link same-day reporter analysis to this lifecycle for a complete quality review."],
            },
        }
    )

    compact_input = mod.build_ai_trade_report_compact_input(story_input)

    assert compact_input["reporter"]["summary"] == "이번 거래는 보유 이후 되밀림 관리가 더 크게 작동한 케이스로 보입니다."
    assert compact_input["reporter"]["status"] == "pending"
    assert compact_input["reporter"]["grade"] == "B"
    assert compact_input["reporter"]["bullets"] == ["seed reporter bullet"]

    compact_story_input = mod._compact_story_input_for_llm(story_input)
    assert compact_story_input["reporter_status_human"]["summary"] == "이번 거래는 보유 이후 되밀림 관리가 더 크게 작동한 케이스로 보입니다."


def test_compact_story_input_prefers_section_seed_summaries_for_core_runtime_blocks(tmp_path, monkeypatch) -> None:
    trade_dir = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_20260318_000660_01"
    trade_dir.mkdir(parents=True)
    input_path = trade_dir / "ai_trade_report_input.json"
    input_path.write_text("{}", encoding="utf-8")

    sentinel_trade_model = {
        "facts": {},
        "context": {
            "report_section_seeds": {
                "market_context_at_entry": {"summary": "Seed market summary.", "bullets": ["seed market bullet"]},
                "strategist_summary": {"summary": "Seed strategist summary.", "bullets": ["seed strategist bullet"]},
                "why_this_symbol_was_chosen": {"summary": "Seed scanner summary.", "bullets": ["seed scanner bullet"]},
                "holding_monitoring_story": {"summary": "Seed monitor summary.", "bullets": ["seed monitor bullet"]},
                "scanner_filters": {"summary": "Seed filters summary.", "bullets": ["seed filters bullet"]},
                "execution_quality": {"summary": "Seed execution summary.", "bullets": ["seed execution bullet"]},
                "guard_approval_result": {"summary": "Seed guard summary.", "bullets": ["seed guard bullet"]},
                "reporter_evaluation": {"summary": "Seed reporter summary.", "bullets": ["seed reporter bullet"], "status": "pending", "grade": "B"},
                "final_operator_conclusion": {
                    "summary": "Seed conclusion summary.",
                    "bullets": ["seed conclusion bullet"],
                    "current_action": "SELL",
                    "watch_next": ["seed watch"],
                    "thesis_invalidation": ["seed invalidate"],
                },
            }
        },
        "provenance": {"schema_version": "trade_read_model.v2"},
    }

    monkeypatch.setattr(
        "libs.reporting.trade_read_model.build_trade_read_model",
        lambda path: dict(sentinel_trade_model),
    )

    story_input = _story_input()
    story_input.update(
        {
            "artifacts": {"ai_trade_report_input_json": str(input_path)},
            "market_context_human": {},
            "scanner_reason_human": {},
            "filters_human": {},
            "monitor_reason_human": {},
            "guard_reason_human": {},
            "execution_outcome_human": {},
            "reporter_status_human": {},
            "operator_conclusion_human": {},
        }
    )

    compact_input = mod._compact_story_input_for_llm(story_input)

    assert compact_input["market_context_human"]["summary"] == "Seed market summary."
    assert compact_input["market_context_human"]["bullets"] == ["seed market bullet"]
    assert compact_input["scanner_reason_human"]["summary"] == "Seed scanner summary."
    assert compact_input["scanner_reason_human"]["bullets"] == ["seed scanner bullet"]
    assert compact_input["filters_human"]["summary"] == "Seed filters summary."
    assert compact_input["filters_human"]["bullets"] == ["seed filters bullet"]
    assert compact_input["monitor_reason_human"]["summary"] == "Seed monitor summary."
    assert compact_input["monitor_reason_human"]["bullets"] == ["seed monitor bullet"]
    assert compact_input["guard_reason_human"]["summary"] == "Seed guard summary."
    assert compact_input["execution_outcome_human"]["summary"] == "Seed execution summary."
    assert compact_input["reporter_status_human"]["summary"] == "Seed reporter summary."
    assert compact_input["reporter_status_human"]["status"] == "pending"
    assert compact_input["reporter_status_human"]["grade"] == "B"
    assert compact_input["operator_conclusion_human"]["summary"] == "Seed conclusion summary."
    assert compact_input["operator_conclusion_human"]["current_action"] == "SELL"
    assert compact_input["operator_conclusion_human"]["watch_next"] == ["seed watch"]
    assert compact_input["operator_conclusion_human"]["thesis_invalidation"] == ["seed invalidate"]


def test_sparse_story_input_prefers_seed_for_placeholder_reporter_summary(tmp_path, monkeypatch) -> None:
    trade_dir = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_20260318_000660_01"
    trade_dir.mkdir(parents=True)
    input_path = trade_dir / "ai_trade_report_input.json"
    input_path.write_text("{}", encoding="utf-8")

    sentinel_trade_model = {
        "facts": {},
        "context": {
            "report_section_seeds": {
                "reporter_evaluation": {
                    "summary": "이번 거래는 보유 이후 되밀림 관리가 더 크게 작동한 케이스로 보입니다.",
                    "bullets": ["seed reporter bullet"],
                    "status": "pending",
                    "grade": "B",
                }
            }
        },
        "provenance": {"schema_version": "trade_read_model.v2"},
    }

    monkeypatch.setattr(
        "libs.reporting.trade_read_model.build_trade_read_model",
        lambda path: dict(sentinel_trade_model),
    )

    story_input = _story_input()
    story_input.update(
        {
            "artifacts": {"ai_trade_report_input_json": str(input_path)},
            "reporter_status_human": {
                "summary": "Same-day reporter analysis was not generated yet.",
                "status": "missing",
                "grade": "N/A",
                "bullets": ["Link same-day reporter analysis to this lifecycle for a complete quality review."],
            },
        }
    )

    sparse_input = mod._sparse_story_input_for_llm(story_input)

    assert sparse_input["reporter"]["summary"] == "이번 거래는 보유 이후 되밀림 관리가 더 크게 작동한 케이스로 보입니다."
    assert sparse_input["reporter"]["status"] == "pending"
    assert sparse_input["reporter"]["grade"] == "B"
    assert sparse_input["reporter"]["bullets"] == ["seed reporter bullet"]


def test_trade_report_shared_facts_align_between_deterministic_and_ai(monkeypatch) -> None:
    monkeypatch.setattr(mod, "LLMRouter", _RetrySuccessRouter)
    story_input = _story_input()
    story_input.update(
        {
            "action": "SELL",
            "status": "closed",
            "entry_summary": {"run_id": "run-entry-1", "action": "BUY"},
            "exit_summary": {"run_id": "run-exit-1", "action": "SELL", "reason_human": "vwap_breakdown"},
            "lifecycle_summary": {"holding_duration": "00:15:00", "exit_reason_human": "vwap_breakdown"},
            "scanner_evidence": {},
            "strategist_evidence": {},
            "canonical_agent_artifacts": {
                "monitor": {
                    "decision_phase": "exit",
                    "decision_action": "sell",
                    "decision_status": "ok",
                    "primary_reason_code": "vwap_breakdown",
                },
                "commander": {"selected_route": "full_cycle", "route_reason_text": "normal runtime route"},
            },
        }
    )

    deterministic = mod.build_deterministic_trade_report(story_input)
    ai_report = mod.build_ai_trade_report(story_input, enabled=True, model="free")

    assert deterministic["action"] == "SELL"
    assert ai_report["action"] == "SELL"
    assert deterministic["status"] == "closed"
    assert ai_report["status"] == "closed"
    det_facts = deterministic.get("shared_facts") if isinstance(deterministic.get("shared_facts"), dict) else {}
    ai_facts = ai_report.get("shared_facts") if isinstance(ai_report.get("shared_facts"), dict) else {}
    assert det_facts.get("holding_duration") == "00:15:00"
    assert ai_facts.get("holding_duration") == "00:15:00"
    assert det_facts.get("exit_reason") == "vwap_breakdown"
    assert ai_facts.get("exit_reason") == "vwap_breakdown"
    assert det_facts.get("action") == "SELL"
    assert ai_facts.get("action") == "SELL"
    assert (ai_facts.get("monitor_decision") or {}).get("reason_code") == "vwap_breakdown"


def test_trade_report_shared_fact_precedence_lifecycle_wins_over_monitor_and_entry() -> None:
    story_input = _story_input()
    story_input.update(
        {
            "status": "open",
            "entry_summary": {"action": "BUY"},
            "exit_summary": {"action": "BUY", "reason_human": "entry_side_reason"},
            "trade_lifecycle": {
                "action": "SELL",
                "status": "closed",
                "summary": {
                    "holding_duration": "00:25:00",
                    "exit_reason_human": "lifecycle_exit_reason",
                    "pnl": 12000,
                    "pnl_pct": 0.015,
                },
            },
            "canonical_agent_artifacts": {
                "monitor": {
                    "decision_action": "buy",
                    "decision_status": "ok",
                    "primary_reason_text": "monitor_conflict_reason",
                }
            },
        }
    )

    seed = mod._build_shared_summary_seed(story_input)
    facts = seed.get("resolved_trade_facts") if isinstance(seed.get("resolved_trade_facts"), dict) else {}
    data_source = facts.get("data_source") if isinstance(facts.get("data_source"), dict) else {}

    assert facts.get("action") == "SELL"
    assert facts.get("status") == "closed"
    assert facts.get("holding_duration") == "00:25:00"
    assert facts.get("exit_reason") == "lifecycle_exit_reason"
    assert facts.get("pnl") == 12000
    assert facts.get("pnl_pct") == 0.015
    assert data_source.get("action") == "lifecycle"
    assert data_source.get("holding_duration") == "lifecycle"
    assert data_source.get("exit_reason") == "lifecycle"


def test_trade_report_shared_fact_precedence_monitor_wins_over_entry_when_lifecycle_missing() -> None:
    story_input = _story_input()
    story_input.update(
        {
            "status": "closed",
            "entry_summary": {"action": "BUY"},
            "exit_summary": {"action": "BUY", "reason_human": "entry_conflict_reason"},
            "canonical_agent_artifacts": {
                "monitor": {
                    "decision_action": "sell",
                    "decision_status": "ok",
                    "primary_reason_text": "monitor_exit_confirmed",
                }
            },
        }
    )

    seed = mod._build_shared_summary_seed(story_input)
    facts = seed.get("resolved_trade_facts") if isinstance(seed.get("resolved_trade_facts"), dict) else {}
    data_source = facts.get("data_source") if isinstance(facts.get("data_source"), dict) else {}

    assert facts.get("action") == "SELL"
    assert facts.get("exit_reason") == "monitor_exit_confirmed"
    assert data_source.get("action") == "monitor"
    assert data_source.get("exit_reason") == "monitor"


def test_trade_report_shared_fact_closed_reconciles_buy_to_sell_from_exit_evidence() -> None:
    story_input = _story_input()
    story_input.update(
        {
            "status": "closed",
            "action": "BUY",
            "entry_summary": {"action": "BUY"},
            "exit_summary": {"reason_human": "SELL was triggered because peak_drawdown."},
            "canonical_agent_artifacts": {
                "monitor": {
                    "decision_action": "buy",
                    "decision_status": "ok",
                    "primary_reason_text": "entry_signal_confirmed",
                }
            },
        }
    )

    seed = mod._build_shared_summary_seed(story_input)
    facts = seed.get("resolved_trade_facts") if isinstance(seed.get("resolved_trade_facts"), dict) else {}
    data_source = facts.get("data_source") if isinstance(facts.get("data_source"), dict) else {}

    assert facts.get("status") == "closed"
    assert facts.get("action") == "SELL"
    assert data_source.get("action") == "closed_lifecycle_reconcile"


def test_normalize_trade_report_output_reconciles_closed_buy_when_exit_reason_is_sell() -> None:
    story_input = _story_input()
    story_input.update(
        {
            "status": "closed",
            "action": "BUY",
            "entry_summary": {"action": "BUY"},
            "exit_summary": {},
            "canonical_agent_artifacts": {"monitor": {"decision_action": "buy"}},
        }
    )
    report = {
        "action": "BUY",
        "status": "closed",
        "symbol": "000660",
        "executive_summary": {"summary": "x"},
        "market_context_at_entry": {"summary": "x", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "x", "bullets": []},
        "entry_decision": {"summary": "x", "bullets": []},
        "holding_monitoring_story": {"summary": "x", "bullets": []},
        "exit_decision": {"summary": "SELL was triggered because peak_drawdown.", "bullets": []},
        "scanner_filters": {"summary": "x", "bullets": []},
        "guard_approval_result": {"summary": "x", "bullets": []},
        "execution_quality": {"summary": "x", "bullets": []},
        "reporter_evaluation": {"summary": "x", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "x", "bullets": []},
        "shared_facts": {"exit_reason": "SELL was triggered because peak_drawdown."},
        "final_operator_conclusion": {"summary": "x", "current_action": "BUY", "watch_next": [], "thesis_invalidation": []},
    }

    normalized = mod._normalize_trade_report_output(story_input, report)

    assert normalized.get("status") == "closed"
    assert normalized.get("action") == "SELL"
    assert (normalized.get("executive_summary") or {}).get("action") == "SELL"
    assert (normalized.get("final_operator_conclusion") or {}).get("current_action") == "SELL"
    assert (normalized.get("shared_facts") or {}).get("exit_reason") == "SELL was triggered because peak_drawdown."


def test_trade_report_shared_fact_ignores_no_position_and_prefers_exit_monitor_axis() -> None:
    story_input = _story_input()
    story_input.update(
        {
            "status": "closed",
            "action": "SELL",
            "lifecycle_summary": {"exit_reason": "no_position"},
            "canonical_agent_artifacts": {
                "monitor": {
                    "decision_action": "buy",
                    "exit_reason": "no_position",
                    "primary_reason_code": "no_position",
                }
            },
            "monitor_reason_human": {
                "trigger_type": "intraday_low_break",
                "active_exit_axis": "Intraday Low Break",
                "summary": "SELL was triggered because intraday_low_break.",
            },
        }
    )

    seed = mod._build_shared_summary_seed(story_input)
    facts = seed.get("resolved_trade_facts") if isinstance(seed.get("resolved_trade_facts"), dict) else {}

    assert facts.get("exit_reason") == "intraday_low_break"
    assert (facts.get("data_source") or {}).get("exit_reason") == "monitor"


def test_deterministic_trade_report_preserves_post_exit_shadow_from_story_input() -> None:
    story_input = _story_input()
    story_input.update(
        {
            "status": "closed",
            "action": "SELL",
            "post_exit_shadow": {
                "schema_version": "post_exit_shadow.v1",
                "observability_only": True,
                "status": "pending",
                "symbol": "000660",
                "exit_price": 100000,
                "price_observation_status": "observed",
                "checkpoints": {
                    "+5m": {"status": "observed", "price": 101000, "return_pct": 0.01},
                    "+15m": {"status": "pending"},
                },
            },
        }
    )

    report = mod.build_deterministic_trade_report(story_input)
    summary_input = mod.build_trade_summary_input(report)
    markdown = mod.render_trade_report_markdown(report)

    assert report["post_exit_shadow"]["checkpoints"]["+5m"]["price"] == 101000
    assert summary_input["post_exit_shadow"]["checkpoints"]["+5m"]["price"] == 101000
    assert "## 매도 후 가격 추적 (관측-only)" in markdown


def test_trade_report_shared_fact_marks_unavailable_when_missing() -> None:
    story_input = _story_input()
    story_input.update(
        {
            "status": "",
            "entry_summary": {},
            "exit_summary": {},
            "lifecycle_summary": {},
            "trade_lifecycle": {},
            "canonical_agent_artifacts": {},
            "monitor_reason_human": {},
        }
    )

    seed = mod._build_shared_summary_seed(story_input)
    facts = seed.get("resolved_trade_facts") if isinstance(seed.get("resolved_trade_facts"), dict) else {}

    assert facts.get("holding_duration") == "unavailable"
    assert facts.get("exit_reason") == "unavailable"
    assert facts.get("pnl") == "unavailable"
    assert facts.get("pnl_pct") == "unavailable"


def test_trade_report_shared_seed_and_compact_input_include_runtime_route_and_monitor_blockers() -> None:
    story_input = _story_input()
    story_input.update(
        {
            "strategist_candidate_hints": ["122630", "233740", "005930"],
            "strategist_market_headlines": [
                "KOSPI opens higher as chip demand expectations improve.",
                "US futures steady ahead of inflation print.",
            ],
            "strategist_symbol_headlines": [
                "000660 rises on renewed AI memory optimism.",
                "Foreign flows return to semiconductor leaders.",
            ],
            "strategist_evidence_trace": {
                "candidate_hints": ["122630", "233740", "005930"],
                "news_query_targets": ["KOSPI", "US futures", "semiconductor"],
                "market_headlines": [
                    "KOSPI opens higher as chip demand expectations improve.",
                    "US futures steady ahead of inflation print.",
                ],
                "symbol_headlines": [
                    "000660 rises on renewed AI memory optimism.",
                    "Foreign flows return to semiconductor leaders.",
                ],
                "global_sentiment_signal": {"score": 0.12, "status": "ok"},
                "fear_index": {"vix_level": 18.4},
                "key_events": ["AI demand re-rating", "foreign inflow stabilization"],
            },
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
                "strategist_baseline_stop_loss_pct": 0.0081,
                "strategist_baseline_take_profit_pct": 0.0175,
                "strategist_baseline_trailing_stop_pct": 0.011,
            },
            "monitor_blocker_trace": {
                "entry_check_summary": "mission=wait_for_confirmation | reason=reclaim_not_confirmed",
                "entry_blockers": ["volume_ok", "vwap_reclaim_ok"],
                "threshold_shortfalls": ["volume ratio 0.10 below min 0.75"],
            },
            "scanner_reason_human": {
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
                        "bias_adjustments": [
                            {"rule": "prefer_shallow_pullback_candidates", "reason": "shallow pullback preference applied"}
                        ],
                    }
                ],
                "selection_reason_with_bias": "selected on near-tie after shallow pullback preference applied",
            },
            "monitor_reason_human": {
                "summary": "Monitor stayed on WAIT because reclaim confirmation is still pending.",
                "entry_check_summary": "mission=wait_for_confirmation | reason=reclaim_not_confirmed",
                "entry_blockers": ["volume_ok", "vwap_reclaim_ok"],
                    "policy_ref": {
                        "monitor_mission": "Wait for cleaner reclaim confirmation.",
                        "flow_instruction": "observe_only",
                        "policy_source": "strategist",
                        "risk_mode": "balanced",
                        "selected_playbook": "pullback",
                        "symbol_constraints": {
                            "preferred_themes": ["broad_market_leaders"],
                            "avoid_themes": ["counter_trend_low_liquidity"],
                        },
                        "policy_validation_status": "ok",
                        "policy_fallback_used": False,
                        "policy_partial_normalized": True,
                    "policy_default_filled_fields": ["enabled"],
                    "policy_validation_missing_fields": ["enabled"],
                    "policy_validation_invalid_fields": [],
                },
                "thresholds_guards_used": {
                    "thresholds": {
                        "volume_ratio_min": 0.75,
                        "max_extended_from_vwap_pct": 0.05,
                    }
                },
                "entry_metrics": {
                    "volume_ratio": 0.10,
                    "extended_from_vwap_pct": 0.19,
                },
                "entry_thresholds": {
                    "volume_ratio_min": 0.75,
                    "max_extended_from_vwap_pct": 0.05,
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
            },
            "canonical_agent_artifacts": {
                "commander": {
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
                    "commander_decision": {
                        "command_intent": "OBSERVE_ONLY",
                        "strategist_invocation": "SKIP",
                        "llm_policy": "SKIP",
                    },
                }
            },
        }
    )

    seed = mod._build_shared_summary_seed(story_input)
    commander_route = seed.get("commander_route") if isinstance(seed.get("commander_route"), dict) else {}
    strategist_evidence = seed.get("strategist_evidence") if isinstance(seed.get("strategist_evidence"), dict) else {}
    scanner_reasoning = seed.get("scanner_reasoning") if isinstance(seed.get("scanner_reasoning"), dict) else {}
    monitor_reasoning = seed.get("monitor_reasoning") if isinstance(seed.get("monitor_reasoning"), dict) else {}
    compact_input = mod.build_ai_trade_report_compact_input(story_input)
    deterministic = mod.build_deterministic_trade_report(story_input)

    assert commander_route.get("selected_route") == "cached_strategist"
    assert commander_route.get("command_intent") == "OBSERVE_ONLY"
    assert commander_route.get("strategist_invocation") == "SKIP"
    assert commander_route.get("llm_policy") == "SKIP"
    assert commander_route.get("strategist_cache_used") is True
    assert commander_route.get("strategist_called") is False
    assert commander_route.get("policy_source") == "strategist"
    assert commander_route.get("applied_policy", {}).get("volume_ratio_min") == 0.68
    assert commander_route.get("policy_partial_normalized") is True
    assert strategist_evidence.get("candidate_hints") == ["122630", "233740", "005930"]
    assert strategist_evidence.get("market_headlines")[0] == "KOSPI opens higher as chip demand expectations improve."
    assert strategist_evidence.get("symbol_headlines")[0] == "000660 rises on renewed AI memory optimism."
    assert scanner_reasoning.get("playbook") == "pullback"
    assert scanner_reasoning.get("policy_source") == "strategist"
    assert scanner_reasoning.get("scanner_bias_applied") is True
    assert scanner_reasoning.get("scanner_bias_summary", {}).get("summary")
    assert scanner_reasoning.get("selection_trace", {}).get("selected_symbol") == "000660"
    assert scanner_reasoning.get("selection_trace", {}).get("selected_symbol_score_drivers", {}).get("trading_value") == 0.22
    assert monitor_reasoning.get("entry_blockers") == ["volume_ok", "vwap_reclaim_ok"]
    assert monitor_reasoning.get("policy_source") == "strategist"
    assert monitor_reasoning.get("applied_policy", {}).get("pullback_min_pct") == 0.008
    assert monitor_reasoning.get("received_policy", {}).get("volume_ratio_min") == 0.68
    assert monitor_reasoning.get("effective_policy", {}).get("volume_ratio_min") == 0.75
    assert monitor_reasoning.get("policy_adjustment_summary")
    assert monitor_reasoning.get("monitor_stop_policy_trace", {}).get("hard_stop_pct") == 0.03
    assert monitor_reasoning.get("monitor_stop_policy_trace", {}).get("adaptive_stop_loss_pct") == 0.0092
    assert monitor_reasoning.get("monitor_stop_policy_trace", {}).get("strategist_baseline_stop_loss_pct") == 0.0081
    assert monitor_reasoning.get("threshold_shortfalls") == ["volume ratio 0.10 below min 0.75"]
    assert compact_input["commander"]["selected_route"] == "cached_strategist"
    assert compact_input["commander"]["route_reason_text"] == "commander_skip_cached_strategist"
    assert compact_input["commander"]["policy_source"] == "strategist"
    assert compact_input["commander"]["applied_policy"]["volume_ratio_min"] == 0.68
    assert compact_input["commander"]["policy_partial_normalized"] is True
    assert compact_input["market_context"]["candidate_hints"] == ["122630", "233740", "005930"]
    assert compact_input["market_context"]["market_headlines"][0] == "KOSPI opens higher as chip demand expectations improve."
    assert compact_input["market_context"]["symbol_headlines"][0] == "000660 rises on renewed AI memory optimism."
    assert compact_input["market_context"]["risk_mode"] == "balanced"
    assert compact_input["market_context"]["selected_playbook"] == "pullback"
    assert compact_input["market_context"]["preferred_themes"] == ["broad_market_leaders"]
    assert "counter_trend_low_liquidity" in compact_input["market_context"]["avoid_themes"]
    assert compact_input["market_context"]["scanner_bias_summary"]["summary"]
    assert compact_input["scanner"]["playbook"] == "pullback"
    assert compact_input["scanner"]["policy_source"] == "strategist"
    assert compact_input["scanner"]["scanner_bias_applied"] is True
    assert compact_input["scanner"]["scanner_bias_summary"]["summary"]
    assert compact_input["scanner"]["candidate_bias_adjustments"][0]["symbol"] == "000660"
    assert "shallow pullback" in compact_input["scanner"]["selection_reason_with_bias"]
    assert compact_input["scanner"]["selection_trace"]["selected_symbol"] == "000660"
    assert compact_input["scanner"]["selection_trace"]["selection_reason"] == "top_value + sector_theme"
    assert compact_input["monitor"]["entry_check_summary"] == "mission=wait_for_confirmation | reason=reclaim_not_confirmed"
    assert compact_input["monitor"]["entry_blockers"] == ["volume_ok", "vwap_reclaim_ok"]
    assert compact_input["monitor"]["policy_source"] == "strategist"
    assert compact_input["monitor"]["applied_policy"]["pullback_min_pct"] == 0.008
    assert compact_input["monitor"]["received_policy"]["volume_ratio_min"] == 0.68
    assert compact_input["monitor"]["effective_policy"]["volume_ratio_min"] == 0.75
    assert compact_input["monitor"]["effective_policy_deltas"]
    assert compact_input["monitor"]["entry_metrics"]["volume_ratio"] == 0.1
    assert compact_input["monitor"]["monitor_stop_policy_trace"]["hard_stop_pct"] == 0.03
    assert compact_input["monitor"]["monitor_stop_policy_trace"]["adaptive_stop_loss_pct"] == 0.0092
    assert compact_input["monitor"]["monitor_stop_policy_trace"]["strategist_baseline_stop_loss_pct"] == 0.0081
    assert deterministic["market_context_at_entry"]["strategist_candidate_hints"] == ["122630", "233740", "005930"]
    assert deterministic["why_this_symbol_was_chosen"]["scanner_selection_trace"]["selected_symbol"] == "000660"
    assert deterministic["holding_monitoring_story"]["monitor_stop_policy_trace"]["effective_stop_loss_pct"] == 0.0092
    assert deterministic["holding_monitoring_story"]["monitor_stop_policy_trace"]["strategist_baseline_stop_loss_pct"] == 0.0081


def test_trade_report_marks_scanner_evidence_unavailable_when_missing() -> None:
    story_input = _story_input()
    story_input["scanner_evidence"] = {}
    story_input["scanner_reason_human"] = {}

    report = mod.build_deterministic_trade_report(story_input)

    scanner_section = report.get("why_this_symbol_was_chosen") if isinstance(report.get("why_this_symbol_was_chosen"), dict) else {}
    summary = str(scanner_section.get("summary") or "").lower()
    facts = report.get("shared_facts") if isinstance(report.get("shared_facts"), dict) else {}
    assert "scanner evidence unavailable" in summary
    assert facts.get("scanner_evidence_status") == "unavailable"


def test_ai_trade_report_retries_before_success(monkeypatch):
    monkeypatch.setattr(mod, "LLMRouter", _RetrySuccessRouter)

    report = mod.build_ai_trade_report(_story_input(), enabled=True, model="free")

    assert report["generation"]["status"] == "ok"
    artifact = report["llm_response_artifact"]
    assert artifact["status"] == "ok"
    assert artifact["retry_count"] == 1
    assert len(artifact["attempts"]) == 2
    assert artifact["model"] == "openrouter/free"
    assert report["deterministic_report_status"] == "ok"
    assert report["ai_trade_report_status"] == "ok"


def test_ai_trade_report_writes_failure_state_after_retries(monkeypatch):
    monkeypatch.setattr(mod, "LLMRouter", _AlwaysEmptyRouter)
    monkeypatch.setenv("TRADE_REPORT_AI_RETRY_MAX", "2")

    report = mod.build_ai_trade_report(_story_input(), enabled=True, model="free")

    assert report["generation"]["status"] == "empty_response"
    assert report["failure"]["status"] == "empty_response"
    artifact = report["llm_response_artifact"]
    assert artifact["status"] == "empty_response"
    assert artifact["retry_count"] == 2
    assert report["executive_summary"]["headline"].startswith("AI trade report failed")
    assert report["deterministic_report_status"] == "ok"
    assert report["ai_trade_report_status"] == "error"


def test_build_deterministic_trade_report_is_always_available() -> None:
    report = mod.build_deterministic_trade_report(_story_input())
    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    assert generation.get("mode") == "deterministic"
    assert report["deterministic_report_status"] == "ok"
    assert report["ai_trade_report_status"] == "skipped"


def test_ai_trade_report_truncated_outer_json_is_not_treated_as_ok(monkeypatch):
    monkeypatch.setattr(mod, "LLMRouter", _TruncatedOuterJsonRouter)

    report = mod.build_ai_trade_report(_story_input(), enabled=True, model="free")

    assert report["generation"]["status"] == "salvaged"
    artifact = report["llm_response_artifact"]
    assert artifact["status"] == "salvaged"
    assert artifact["parse_mode"] == "partial"
    assert "executive_summary" in artifact["required_keys_present"]
    assert "market_context_at_entry" in artifact["required_keys_missing"]
    assert artifact["completeness_score"] < 1.0
    assert artifact["used_fallback_sections"]


def test_ai_trade_report_missing_required_keys_is_downgraded(monkeypatch):
    monkeypatch.setattr(mod, "LLMRouter", _MissingKeysRouter)

    report = mod.build_ai_trade_report(_story_input(), enabled=True, model="free")

    assert report["generation"]["status"] == "salvaged"
    artifact = report["llm_response_artifact"]
    assert artifact["status"] == "salvaged"
    assert artifact["parse_mode"] == "full"
    assert "executive_summary" in artifact["required_keys_present"]
    assert "entry_decision" in artifact["required_keys_missing"]
    assert artifact["completeness_score"] < 1.0


def test_ai_trade_report_complete_json_with_leading_prose_is_repaired(monkeypatch):
    monkeypatch.setattr(mod, "LLMRouter", _ProseThenCompleteJsonRouter)

    report = mod.build_ai_trade_report(_story_input(), enabled=True, model="free")

    assert report["generation"]["status"] == "ok"
    artifact = report["llm_response_artifact"]
    assert artifact["status"] == "ok"
    assert artifact["parse_mode"] == "full"
    assert artifact["required_keys_missing"] == []
    assert artifact["completeness_score"] == 1.0
    assert artifact["retry_count"] == 1
    assert len(artifact["attempts"]) == 2
    assert artifact["attempts"][0]["status"] == "partial"
    assert artifact["attempts"][1]["status"] == "ok"


def test_ai_trade_report_complete_json_with_leading_prose_is_ok_when_extracted_cleanly(monkeypatch):
    monkeypatch.setattr(mod, "LLMRouter", _ProseThenCompleteJsonRouter)
    monkeypatch.setenv("TRADE_REPORT_AI_RETRY_MAX", "0")

    report = mod.build_ai_trade_report(_story_input(), enabled=True, model="free")

    assert report["generation"]["status"] == "ok"
    artifact = report["llm_response_artifact"]
    assert artifact["status"] == "ok"
    assert artifact["parse_mode"] == "partial"
    assert artifact["required_keys_missing"] == []
    assert artifact["completeness_score"] == 1.0
    assert artifact["retry_count"] == 0
    assert artifact["finish_reason"] == "complete_json_extracted_after_protocol_deviation"


def test_ai_trade_report_messages_use_compact_projection() -> None:
    story_input = _story_input()
    story_input["entry_summary"] = {"run_id": "run-entry", "reason_human": "entry reason"}
    story_input["holding_summary"] = {
        "run_ids": [f"run-{i}" for i in range(40)],
        "holding_events": [{"event": "hold", "description": "x" * 200} for _ in range(20)],
        "posture_history": [{"ts": f"2026-03-18T00:00:{i:02d}+00:00", "posture": "HOLD", "reason": "monitor"} for i in range(12)],
        "monitor_updates": [f"update-{i}-" + ("y" * 200) for i in range(30)],
    }
    story_input["timeline"] = [
        {"ts": f"2026-03-18T00:00:{i:02d}+00:00", "event": "monitor", "description": "z" * 200}
        for i in range(20)
    ]
    story_input["market_context_human"] = {"summary": "market context", "bullets": ["vix", "news", "macro"]}
    story_input["scanner_reason_human"] = {"summary": "scanner context", "runner_ups": ["A", "B", "C"]}

    messages = mod._build_messages(story_input)
    user_prompt = str(messages[1]["content"])

    assert "holding_event_count" in user_prompt
    assert "recent_monitor_updates" in user_prompt
    assert "holding_events" not in user_prompt
    assert "\"posture_history\"" not in user_prompt
    assert len(user_prompt) < 12000


def test_ai_trade_report_compact_input_surfaces_structured_strategist_output_boundary() -> None:
    story_input = _story_input()
    story_input["canonical_agent_artifacts"] = {
        "strategist": {
            "strategy_thesis": {
                "market_view": "AI memory leadership remains constructive but entry needs confirmation.",
                "trade_style": "pullback continuation",
                "risk_tone": "balanced",
                "selected_playbook": "pullback",
                "one_line": "Use pullback entries only after liquidity and VWAP confirmation.",
            },
            "pre_llm_playbook": "defensive",
            "llm_requested_playbook": "pullback",
            "final_playbook": "pullback",
            "tactical_strategy": "vwap_reclaim_pullback",
            "strategy_scores": {"vwap_reclaim_pullback": 0.77, "defensive_observe": 0.22},
            "candidate_watch_policy": {
                "behavior_effect": "visibility_only",
                "max_priority_rank": 5,
                "max_runner_ups": 4,
                "cascade_enabled": True,
                "reason": "pullback frame should watch liquid reclaim candidates",
            },
            "memory_usage_trace": {
                "schema_version": "strategist_memory_usage_trace.v1",
                "active_layers": ["daily", "symbol"],
                "priority_order": ["symbol", "daily", "weekly"],
                "layer_decisions": {
                    "daily": {
                        "used": True,
                        "visible": True,
                        "gate_reason": "recent same-day win-rate was weak",
                        "effect": "tighten entry confirmation",
                    }
                },
                "scanner_application": {
                    "applied": True,
                    "selected_symbol": "000660",
                    "active_layers": ["daily"],
                    "reason": ["daily memory adjusted scanner bias"],
                },
            },
            "news_usage_trace": {
                "schema_version": "strategist_news_usage_trace.v1",
                "query_targets": ["000660", "semiconductor"],
                "market_headlines_used": ["KOSPI higher on chip demand expectations."],
                "market_effect": "market tone supports semiconductor leadership",
                "scanner_guidance_effect": "prefer AI memory liquidity leaders",
            },
            "scanner_handoff": {
                "prefer_candidate_traits": ["liquidity leader", "VWAP reclaim"],
                "ranking_guidance": "rank candidates by liquidity and confirmation quality",
                "not_responsible_for": ["final_symbol_selection"],
            },
            "monitor_handoff": {
                "entry_confirmation": ["volume ratio >= 0.75", "VWAP reclaim"],
                "policy_effect_summary": "monitor owns entry gate confirmation",
            },
            "responsibility_boundary": {
                "strategist_owns": ["market frame", "policy bias"],
                "scanner_owns": ["final_symbol_selection", "ranking"],
                "monitor_owns": ["entry_gate", "exit_gate"],
                "not_responsible_for": ["final_symbol_selection"],
            },
        }
    }

    compact_input = mod.build_ai_trade_report_compact_input(story_input)
    strategist = compact_input["strategist_output"]

    assert strategist["strategy_thesis"]["selected_playbook"] == "pullback"
    assert strategist["strategy_detail"]["pre_llm_playbook"] == "defensive"
    assert strategist["strategy_detail"]["llm_requested_playbook"] == "pullback"
    assert strategist["strategy_detail"]["candidate_watch_policy"]["max_priority_rank"] == 5
    assert strategist["memory_usage_trace"]["layer_decisions"]["daily"]["used"] is True
    assert strategist["memory_usage_trace"]["scanner_application"]["selected_symbol"] == "000660"
    assert strategist["news_usage_trace"]["market_effect"] == "market tone supports semiconductor leadership"
    assert strategist["scanner_handoff"]["not_responsible_for"] == ["final_symbol_selection"]
    assert strategist["responsibility_boundary"]["scanner_owns"] == ["final_symbol_selection", "ranking"]
    assert "Do not infer final symbol selection" in strategist["direct_consumption_rule"]


def test_ai_trade_report_preserves_and_renders_structured_strategist_output() -> None:
    story_input = _story_input()
    story_input["canonical_agent_artifacts"] = {
        "strategist": {
            "strategy_thesis": {
                "selected_playbook": "pullback",
                "risk_tone": "normal",
                "market_view": "neutral tape",
                "one_line": "pullback frame with normal risk tone",
            },
            "pre_llm_playbook": "defensive",
            "llm_requested_playbook": "pullback",
            "final_playbook": "pullback",
            "tactical_strategy": "vwap_reclaim_pullback",
            "strategy_scores": {"vwap_reclaim_pullback": 0.73, "defensive_observe": 0.31},
            "candidate_watch_policy": {
                "behavior_effect": "visibility_only",
                "max_priority_rank": 5,
                "max_runner_ups": 4,
                "cascade_enabled": True,
                "reason": "pullback watch expansion is visibility-only",
            },
            "memory_usage_trace": {
                "active_layers": ["daily"],
                "priority_order": ["daily", "weekly", "monthly", "symbol"],
                "layer_decisions": {
                    "daily": {"used": True, "gate_reason": "fresh_packet"},
                    "weekly": {"used": False, "gate_reason": "layer inactive"},
                },
                "human_summary": "Daily memory was used; weekly memory stayed inactive.",
            },
            "news_usage_trace": {
                "query_targets": ["KOSPI", "000660"],
                "human_summary": "News was used for market and scanner guidance.",
                "confidence": "medium",
            },
            "scanner_handoff": {
                "ranking_guidance": "prefer liquid leaders",
                "prefer_candidate_traits": ["liquidity", "relative_strength"],
                "penalize_traits": ["thin_volume"],
                "not_responsible_for": ["final_symbol_selection"],
            },
            "monitor_handoff": {
                "policy_effect_summary": "wait for VWAP reclaim",
                "entry_aggressiveness": "normal",
                "entry_confirmation": ["vwap_reclaim"],
                "hold_off_conditions": ["volume_missing"],
            },
            "trade_permission_frame": {
                "permission_level": "conditional",
                "reason": "monitor confirmation required",
                "entry_allowed_if": ["vwap_reclaim"],
                "entry_blocked_if": ["volume_missing"],
            },
        }
    }

    report = mod.build_deterministic_trade_report(story_input)
    strategist_output = report.get("strategist_output") or {}
    assert strategist_output["strategy_thesis"]["selected_playbook"] == "pullback"
    assert strategist_output["strategy_detail"]["tactical_strategy"] == "vwap_reclaim_pullback"
    assert strategist_output["strategy_detail"]["candidate_watch_policy"]["max_priority_rank"] == 5
    assert strategist_output["memory_usage_trace"]["active_layers"] == ["daily"]
    assert strategist_output["news_usage_trace"]["query_targets"] == ["KOSPI", "000660"]

    markdown = mod.render_trade_report_markdown(report)
    assert "## 전략가 출력 근거" in markdown
    assert "- [전략가 출력]" in markdown
    assert "- [전략 디테일]" in markdown
    assert "vwap_reclaim_pullback" in markdown
    assert "- [메모리]" in markdown
    assert "daily=used/fresh_packet" in markdown
    assert "- [뉴스]" in markdown
    assert "- [스캐너 인계]" in markdown
    assert "- [모니터 인계]" in markdown
    assert "- [권한 프레임]" in markdown
    assert "- [역할 경계]" in markdown


def test_ai_trade_report_surfaces_candidate_watch_execution_visibility() -> None:
    story_input = _story_input()
    story_input["symbol"] = "000660"
    story_input["canonical_agent_artifacts"] = {
        "strategist": {
            "strategy_thesis": {
                "selected_playbook": "pullback",
                "risk_tone": "balanced",
                "market_view": "leader pullback needs confirmation",
            },
            "tactical_strategy": "vwap_reclaim_pullback",
            "candidate_watch_policy": {
                "source": "strategist_output.candidate_watch_policy",
                "behavior_effect": "execution_proposal",
                "max_priority_rank": 10,
                "max_runner_ups": 9,
                "cascade_enabled": True,
                "tactical_strategy": "vwap_reclaim_pullback",
                "reason": "watch leaders beyond the first rank",
            },
        },
        "commander": {
            "selected_route": "full_cycle",
            "policy_source": "strategist",
            "commander_decision": {
                "command_intent": "ALLOW_ENTRY_SCAN",
                "entry_control": {
                    "mode": "strategy_watch_policy",
                    "decision": "apply_strategy_candidate_watch_policy",
                    "reason": "strategy_candidate_watch_policy",
                    "max_priority_rank": 7,
                    "max_runner_ups": 6,
                    "cascade_enabled": True,
                    "candidate_watch_policy_detected": True,
                    "candidate_watch_policy_applied": True,
                    "candidate_watch_policy_clamp_reason": "balanced_rank_cap",
                    "candidate_watch_policy_proposal": {
                        "source": "strategist_output.candidate_watch_policy",
                        "max_priority_rank": 10,
                        "max_runner_ups": 9,
                        "cascade_enabled": True,
                        "reason": "watch leaders beyond the first rank",
                    },
                },
            },
        },
        "monitor": {
            "entry_candidate_cascade": {
                "attempted": True,
                "eligible": True,
                "cascade_enabled": True,
                "top_pick_symbol": "005930",
                "top_pick_triggered": False,
                "top_pick_reason": "breakout_not_ready",
                "max_priority_rank": 7,
                "max_runner_ups": 6,
                "runner_up_symbols": ["000660", "035420"],
                "fallback_used": True,
                "fallback_from_symbol": "005930",
                "fallback_to_symbol": "000660",
                "fallback_to_rank": 2,
                "final_selected_symbol": "000660",
                "final_selected_rank": 2,
                "fallback_trace": [
                    {
                        "symbol": "000660",
                        "rank": 2,
                        "score_total": 0.72,
                        "triggered": True,
                        "reason": "vwap_reclaim_confirmed",
                        "confidence_score": 0.61,
                        "confidence_threshold": 0.55,
                    }
                ],
            }
        },
    }

    compact_input = mod.build_ai_trade_report_compact_input(story_input)
    visibility = compact_input["entry_execution_visibility"]

    assert visibility["strategy_candidate_watch_proposal"]["max_priority_rank"] == 10
    assert visibility["commander_entry_control"]["max_priority_rank"] == 7
    assert visibility["monitor_entry_candidate_cascade"]["fallback_to_symbol"] == "000660"
    assert compact_input["commander"]["entry_control"]["candidate_watch_policy_clamp_reason"] == "balanced_rank_cap"
    assert compact_input["monitor"]["entry_candidate_cascade"]["final_selected_rank"] == 2

    report = mod.build_deterministic_trade_report(story_input)
    assert report["entry_execution_visibility"]["commander_entry_control"]["max_runner_ups"] == 6

    summary = mod.render_trade_summary_markdown(report)
    full = mod.render_trade_report_markdown(report)
    assert "후보 감시:" in summary
    assert "후보 감시: 7위까지 / 차순위 6개 / cascade 활성" in summary
    assert "후보 선택: 최종 후보: 000660(2위)" in summary
    assert "전략가 후보 감시 제안" not in summary
    assert "watch leaders beyond the first rank" not in summary
    assert "balanced_rank_cap" not in summary
    assert "지휘관 최종 적용 범위" not in summary
    assert "지휘관 최종 적용 범위" not in full
    assert "최종 후보: 000660(2위)" in full
    assert "- [후보 감시 실행]" in full


def test_trade_summary_omits_empty_candidate_watch_proposal_explanation() -> None:
    story_input = _story_input()
    story_input["canonical_agent_artifacts"] = {
        "strategist": {
            "tactical_strategy": "vwap_reclaim_pullback",
            "candidate_watch_policy": {
                "tactical_strategy": "vwap_reclaim_pullback",
                "reason": "recent pullback pattern explanation",
            },
        }
    }

    report = mod.build_deterministic_trade_report(story_input)
    summary = mod.render_trade_summary_markdown(report)
    full = mod.render_trade_report_markdown(report)

    assert "전략가 후보 감시 제안은 -" not in summary
    assert "후보 감시:" not in summary
    assert "recent pullback pattern explanation" not in summary
    assert "전략가 후보 감시 제안은 -" not in full


def test_entry_execution_visibility_reads_handoff_nested_cascade() -> None:
    story_input = _story_input()
    story_input["canonical_agent_artifacts"] = {
        "commander": {
            "commander_decision": {
                "entry_control": {
                    "mode": "strategy_watch_policy",
                    "max_priority_rank": 3,
                    "max_runner_ups": 2,
                    "cascade_enabled": False,
                    "candidate_watch_policy_clamp_reason": "risk_off_rank_cap",
                }
            }
        },
        "monitor": {
            "scanner_monitor_handoff": {
                "entry_candidate_cascade": {
                    "attempted": False,
                    "eligible": False,
                    "cascade_enabled": False,
                    "top_pick_symbol": "005930",
                    "top_pick_reason": "breakout_not_ready",
                    "blocked_reason": "cascade_disabled_by_entry_control",
                    "max_priority_rank": 3,
                    "max_runner_ups": 2,
                }
            }
        },
    }

    seed = mod._build_shared_summary_seed(story_input)
    visibility = seed["entry_execution_visibility"]

    assert visibility["commander_entry_control"]["max_priority_rank"] == 3
    assert visibility["commander_entry_control"]["candidate_watch_policy_clamp_reason"] == "risk_off_rank_cap"
    assert visibility["monitor_entry_candidate_cascade"]["blocked_reason"] == "cascade_disabled_by_entry_control"

    report = mod.build_deterministic_trade_report(story_input)
    summary = mod.render_trade_summary_markdown(report)
    assert "실제 확인: 차순위 미실행 (1순위 005930, 사유: 지휘관 설정으로 차순위 확인 비활성)" in summary
    assert "cascade_disabled_by_entry_control" not in summary


def test_trade_summary_candidate_watch_open_position_is_operator_readable() -> None:
    story_input = _story_input()
    story_input["symbol"] = "034020"
    story_input["canonical_agent_artifacts"] = {
        "commander": {
            "commander_decision": {
                "entry_control": {
                    "max_priority_rank": 10,
                    "max_runner_ups": 4,
                    "cascade_enabled": True,
                    "candidate_watch_policy_clamp_reason": "market_supportive_repeated_blocker:below_vwap_reclaim_not_ready:streak=14",
                }
            }
        },
        "monitor": {
            "entry_candidate_cascade": {
                "attempted": False,
                "top_pick_symbol": "034020",
                "blocked_reason": "open_position_present",
                "max_priority_rank": 10,
                "max_runner_ups": 4,
            }
        },
    }

    report = mod.build_deterministic_trade_report(story_input)
    summary = mod.render_trade_summary_markdown(report)

    assert "* 후보 감시: 10위까지 / 차순위 4개 / cascade 활성" in summary
    assert "* 실제 확인: 차순위 미실행 (1순위 034020, 사유: 보유 포지션 존재)" in summary
    assert "market_supportive_repeated_blocker" not in summary
    assert "지휘관 최종 적용 범위" not in summary
    assert "모니터 차순위 확인은 실행되지 않았습니다" not in summary


def test_entry_execution_visibility_enriches_strategy_proposal_from_commander_proposed_scope() -> None:
    story_input = _story_input()
    story_input["canonical_agent_artifacts"] = {
        "strategist": {
            "candidate_watch_policy": {
                "source": "strategist_visibility_proposal",
                "tactical_strategy": "vwap_reclaim_pullback",
                "reason": "watch clean pullbacks",
            }
        },
        "commander": {
            "commander_decision": {
                "entry_control": {
                    "max_priority_rank": 10,
                    "max_runner_ups": 4,
                    "cascade_enabled": True,
                    "candidate_watch_policy_detected": True,
                    "candidate_watch_policy_applied": True,
                    "candidate_watch_policy_effect": "commander_clamped_execution",
                    "candidate_watch_policy_clamp_reason": "market_supportive_repeated_blocker",
                    "proposed_max_priority_rank": 5,
                    "proposed_max_runner_ups": 4,
                }
            }
        },
    }

    compact = mod.build_ai_trade_report_compact_input(story_input)
    proposal = compact["entry_execution_visibility"]["strategy_candidate_watch_proposal"]

    assert proposal["max_priority_rank"] == 5
    assert proposal["max_runner_ups"] == 4
    assert proposal["tactical_strategy"] == "vwap_reclaim_pullback"


def test_trade_report_reconstructs_strategy_output_surface_from_entry_visibility() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "010170",
        "action": "SELL",
        "status": "closed",
        "strategist_summary": {
            "summary": "cached strategist가 사용됐습니다.",
            "selected_playbook": "pullback",
        },
        "market_context": {"risk_mode": "balanced"},
        "entry_execution_visibility": {
            "strategy_candidate_watch_proposal": {
                "source": "strategist_visibility_proposal",
                "tactical_strategy": "vwap_reclaim_pullback",
                "reason": "watch clean pullbacks",
            },
            "commander_entry_control": {
                "max_priority_rank": 10,
                "max_runner_ups": 4,
                "cascade_enabled": True,
                "proposed_max_priority_rank": 5,
                "proposed_max_runner_ups": 4,
            },
            "monitor_entry_candidate_cascade": {
                "attempted": False,
                "top_pick_symbol": "010170",
                "blocked_reason": "open_position_present",
                "final_selected_symbol": "010170",
            },
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "## 전략가 출력 근거" in markdown
    assert "- [전략 디테일]" in markdown
    assert "전술=vwap_reclaim_pullback" in markdown
    assert "후보 감시 제안=rank<=5 / runner_ups=4" in markdown
    assert "- [후보 감시 실행]" in markdown
    assert "전략가 제안: 5위까지 / 차순위 4개" in markdown
    assert "실제 확인: 차순위 미실행 (1순위 010170, 사유: 보유 포지션 존재)" in markdown


def test_trade_report_candidate_watch_display_filters_non_krx_runner_up_symbols() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "010170",
        "action": "BUY",
        "status": "closed",
        "entry_execution_visibility": {
            "commander_entry_control": {
                "max_priority_rank": 10,
                "max_runner_ups": 4,
                "cascade_enabled": True,
            },
            "monitor_entry_candidate_cascade": {
                "attempted": True,
                "top_pick_symbol": "005930",
                "top_pick_reason": "below_vwap_reclaim_not_ready",
                "runner_up_symbols": ["000660", "SK", "010170", "DB"],
                "fallback_used": True,
                "fallback_to_symbol": "010170",
                "fallback_to_rank": 4,
                "final_selected_symbol": "010170",
            },
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "차순위 000660, 010170 확인" in markdown
    assert "차순위 000660, SK" not in markdown
    assert ", DB" not in markdown


def test_ai_trade_report_messages_use_clean_json_only_instructions() -> None:
    messages = mod._build_messages(_story_input())
    system_prompt = str(messages[0]["content"])
    user_prompt = str(messages[1]["content"])

    assert "반드시 JSON 객체 하나만 반환하십시오." in system_prompt
    assert "trade lifecycle retrospective" in system_prompt
    assert "숫자, 이벤트, 이유, evidence를 지어내지 마십시오." in system_prompt
    assert "사람이 읽는 모든 값은 반드시 한국어로 작성해야 합니다." in system_prompt
    assert "strategist -> scanner -> monitor -> supervisor -> executor -> reporter" in user_prompt
    assert "왜 진입했는가, 왜 보유했는가, 왜 청산했는가" in user_prompt
    assert "영어 source 문장을 그대로 복사하지 마십시오." in user_prompt
    assert "selection_basis" in user_prompt
    assert "runner_ups_lost" in user_prompt
    assert "decision_reason_chain" in user_prompt
    assert "strategist_output" in user_prompt
    assert "strategy_thesis" in user_prompt
    assert "memory_usage_trace" in user_prompt
    assert "news_usage_trace" in user_prompt
    assert "scanner_handoff" in user_prompt
    assert "The strategist is not the final symbol selector" in user_prompt
    assert "scanner/why_this_symbol_was_chosen" in user_prompt


def test_ai_trade_report_repair_messages_do_not_reinject_non_json_reasoning() -> None:
    messages = mod._build_repair_messages(_story_input(), "First, the user says I should output JSON.")
    system_prompt = str(messages[0]["content"])
    user_prompt = str(messages[1]["content"])

    assert "설명문, 사고 과정" in system_prompt
    assert "[previous response was non-JSON reasoning or invalid text; ignore it]" in user_prompt
    assert "First, the user says" not in user_prompt
    assert "계획 문장은 절대 쓰지 마십시오" in system_prompt


def test_ai_trade_report_repair_messages_strip_reasoning_from_partial_json_response() -> None:
    raw = (
        "First, I will think step by step. "
        '{"executive_summary":{"headline":"HOLD 000660","action":"HOLD","symbol":"000660","confidence":"high","summary":"ok"}}'
    )
    messages = mod._build_repair_messages(_story_input(), raw)
    user_prompt = str(messages[1]["content"])

    assert "First, I will think step by step." not in user_prompt
    assert '"executive_summary"' in user_prompt


def test_ai_trade_report_sparse_repair_messages_use_shorter_contract() -> None:
    story_input = _story_input()
    story_input["timeline"] = [
        {"ts": f"2026-03-18T00:00:{i:02d}+00:00", "event": "holding", "description": "monitor hold"}
        for i in range(12)
    ]

    regular = mod._build_repair_messages(story_input, "not-json", sparse=False)
    sparse = mod._build_repair_messages(story_input, "not-json", sparse=True)
    regular_prompt = str(regular[1]["content"])
    sparse_prompt = str(sparse[1]["content"])

    assert "복구" in sparse_prompt
    assert "full_timeline" not in sparse_prompt
    assert len(sparse_prompt) <= len(regular_prompt) + 200


def test_ai_trade_report_language_meta_flags_mostly_english_sections() -> None:
    candidate = {
        "executive_summary": {
            "headline": "Trade closed after quick exit",
            "summary": "Current lifecycle status is closed.",
        },
        "market_context_at_entry": {
            "summary": "Market regime was neutral with a defensive playbook.",
            "bullets": ["Global sentiment score: -0.22", "VIX level: 25.09"],
        },
        "final_operator_conclusion": {
            "summary": "Review the monitor trigger and reporter linkage.",
            "watch_next": ["Monitor trigger changes", "Macro/news shifts"],
            "thesis_invalidation": ["negative macro regime shift"],
        },
    }

    meta = mod._trade_report_language_meta(candidate)

    assert meta["requires_korean_repair"] is True
    assert meta["language_english_like_count"] >= 6


def test_ai_trade_report_repair_messages_can_enforce_korean() -> None:
    messages = mod._build_repair_messages(_story_input(), "not-json", sparse=True, enforce_korean=True)
    system_prompt = str(messages[0]["content"])
    user_prompt = str(messages[1]["content"])

    assert "사람이 읽는 모든 값은 반드시 한국어로 작성해야 합니다." in system_prompt
    assert "최종 JSON을 반환하기 전에 남아 있는 영어 설명 문장을 모두 한국어로 번역하십시오." in user_prompt
    assert "watch_next" in user_prompt


def test_ai_trade_report_compact_input_is_smaller_than_full_story() -> None:
    story_input = _story_input()
    story_input["holding_summary"] = {
        "run_ids": [f"run-{i}" for i in range(40)],
        "holding_events": [{"event": "hold", "description": "x" * 200} for _ in range(30)],
        "monitor_updates": [f"update-{i}-" + ("y" * 200) for i in range(20)],
    }
    story_input["timeline"] = [
        {"ts": f"2026-03-18T00:00:{i:02d}+00:00", "event": "monitor", "description": "z" * 200}
        for i in range(20)
    ]

    compact_input = mod.build_ai_trade_report_compact_input(story_input)
    full_len = len(json.dumps(story_input, ensure_ascii=False))
    compact_len = len(json.dumps(compact_input, ensure_ascii=False))

    assert compact_len < full_len
    assert "holding_events" not in json.dumps(compact_input, ensure_ascii=False)


def test_ai_trade_report_uses_policy_execution_profile_max_tokens_when_role_value_missing(monkeypatch) -> None:
    monkeypatch.setattr(mod, "LLMRouter", _CapturePolicyRouter)
    story_input = _story_input()
    story_input["applied_policy"] = {
        "llm": {
            "reporter": {
                "intraday": {
                    "execution_profile": {
                        "name": "concise_review",
                        "max_tokens": 4096,
                    }
                }
            }
        }
    }

    report = mod.build_ai_trade_report(story_input, enabled=True, model="free")

    assert report["generation"]["status"] == "ok"
    assert _CapturePolicyRouter.last_policies
    assert int(_CapturePolicyRouter.last_policies[0]["max_tokens"]) == 4096
    assert _CapturePolicyRouter.last_policies[0]["plugins"] == [{"id": "response-healing"}]


def test_ai_trade_report_prefers_top_level_execution_profile(monkeypatch) -> None:
    monkeypatch.setattr(mod, "LLMRouter", _CapturePolicyRouter)
    story_input = _story_input()
    story_input["applied_policy"] = {
        "llm": {
            "execution_profile": {
                "profile_name": "default_intraday",
                "temperature": 0.33,
                "max_tokens": 1337,
                "timeout_sec": 11,
                "retry": {"max_attempts": 3, "backoff_sec": 0.0},
            },
            "reporter": {
                "intraday": {
                    "execution_profile": {
                        "name": "concise_review",
                        "max_tokens": 4096,
                    }
                }
            },
        }
    }

    report = mod.build_ai_trade_report(story_input, enabled=True, model="free")

    assert report["generation"]["status"] == "ok"
    assert _CapturePolicyRouter.last_policies
    assert float(_CapturePolicyRouter.last_policies[0]["temperature"]) == 0.33
    assert int(_CapturePolicyRouter.last_policies[0]["max_tokens"]) == 1337
    assert float(_CapturePolicyRouter.last_policies[0]["timeout_sec"]) == 11.0


def test_ai_trade_report_local_debug_skips_llm(monkeypatch) -> None:
    class ExplodingRouter:
        client = object()

        @staticmethod
        def from_env() -> "ExplodingRouter":
            return ExplodingRouter()

        def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
            return _Route(str((policy or {}).get("model") or "openrouter/free"))

        def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
            raise AssertionError("local_debug_no_llm should skip trade_report LLM calls")

    monkeypatch.setattr(mod, "LLMRouter", ExplodingRouter)

    report = mod.build_ai_trade_report(
        _story_input(),
        enabled=True,
        model="free",
        local_debug_no_llm=True,
        retry_max_override=0,
        hard_timeout_sec_override=1.0,
    )

    assert report["generation"]["status"] == "ok"
    assert report["generation"]["mode"] == "local_debug"
    assert report["ai_trade_report_status"] == "skipped"
    assert report["deterministic_report_status"] == "ok"
    assert report["llm_response_artifact"]["status"] == "fallback"
    assert report["llm_response_artifact"]["meta"]["reason"] == "local_debug_no_llm"


def test_ai_trade_report_retry_override_can_disable_retry(monkeypatch) -> None:
    monkeypatch.setattr(mod, "LLMRouter", _RetrySuccessRouter)

    report = mod.build_ai_trade_report(
        _story_input(),
        enabled=True,
        model="free",
        retry_max_override=0,
    )

    assert report["generation"]["status"] != "ok"
    assert int(report["llm_response_artifact"]["retry_count"]) == 0


def test_ai_trade_report_hard_timeout_override_stops_slow_call(monkeypatch) -> None:
    monkeypatch.setattr(mod, "LLMRouter", _SlowRouter)

    started = time.perf_counter()
    report = mod.build_ai_trade_report(
        _story_input(),
        enabled=True,
        model="free",
        retry_max_override=0,
        timeout_sec_override=30.0,
        hard_timeout_sec_override=0.05,
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 0.25
    assert report["generation"]["status"] == "timeout"
    assert report["llm_response_artifact"]["status"] == "timeout"
    assert "hard timeout" in str(report["llm_response_artifact"]["error"] or report["llm_response_artifact"]["meta"].get("reason") or "").lower()


def test_ai_trade_report_fallback_preserves_structured_market_context_fields() -> None:
    story_input = _story_input()
    story_input["market_context_human"] = {
        "regime": "risk_off",
        "market_sentiment": "bearish",
        "playbook": "defensive",
        "themes": ["defensive_assets"],
        "global_sentiment_score": -0.22,
        "vix_level": 25.09,
        "stress_flags": ["elevated_vix"],
        "news_input_summary": "75 headlines were considered across 10 targets.",
        "news_query_targets": ["KOSPI", "US market"],
        "key_events_hint": ["fear_index vix=25.09 change=12.16% pressure=0.255"],
        "summary": "risk-off market context. 75 headlines were considered across 10 targets.",
        "bullets": ["Market regime: risk_off", "News input: 75 headlines were considered across 10 targets."],
    }
    story_input["scanner_reason_human"] = {
        "selected_symbol": "000660",
        "selected_rank": 1,
        "universe_size": 5,
        "ranking_basis": ["trading value", "theme alignment"],
        "summary": "scanner selected rank #1",
        "bullets": ["Universe scanned: 5", "Selected rank: #1"],
    }

    report = mod._merge_trade_report_candidate(
        story_input,
        {},
        status="salvaged",
        mode="ai",
        model="openrouter/free",
        reason="partial",
    )

    assert report["generation"]["status"] == "salvaged"
    assert report["report_generation"]["status"] == "salvaged"
    assert report["market_context_at_entry"]["regime"] == "risk_off"
    assert report["market_context_at_entry"]["global_sentiment_score"] == -0.22
    assert report["market_context_at_entry"]["vix_level"] == 25.09
    bullets = [str(row) for row in report["market_context_at_entry"]["bullets"]]
    assert not any("headlines were considered across" in row.lower() for row in bullets)
    assert not any("news input:" in row.lower() for row in bullets)
    assert not any("news query targets:" in row.lower() for row in bullets)
    assert any("vix" in row.lower() for row in bullets)
    assert "headlines were considered across" not in str(report["market_context_at_entry"]["summary"]).lower()
    assert "scanner_linkage_summary" in report["market_context_at_entry"]
    assert "000660" in str(report["market_context_at_entry"]["scanner_linkage_summary"])
    assert report["why_this_symbol_was_chosen"]["selected_rank"] == 1
    assert report["why_this_symbol_was_chosen"]["universe_size"] == 5


def test_ai_trade_report_fallback_enriches_scanner_summary_and_basis() -> None:
    story_input = _story_input()
    story_input["market_context_human"] = {
        "playbook": "breakout",
    }
    story_input["scanner_reason_human"] = {
        "selected_symbol": "000660",
        "selected_rank": 1,
        "universe_size": 4,
        "selected_score": 1.286,
        "ranking_basis": ["trading value", "theme and sector alignment", "sentiment support"],
        "selected_sources": ["top_value", "sector_theme"],
        "confidence": 0.728,
        "top_candidates": [
            {"rank": 1, "symbol": "000660", "score_total": 1.286, "risk_score": 0.563, "confidence": 0.728},
            {"rank": 2, "symbol": "005930", "score_total": 1.223, "risk_score": 0.559, "confidence": 0.746},
            {"rank": 3, "symbol": "047040", "score_total": 1.201, "risk_score": 0.853, "confidence": 0.785},
        ],
        "runner_ups": [
            {"symbol": "005930", "rank": 2, "score_total": 1.223, "risk_score": 0.559, "confidence": 0.746, "why": "score gap 0.063"},
            {"symbol": "047040", "rank": 3, "score_total": 1.201, "risk_score": 0.853, "confidence": 0.785, "why": "score gap 0.085; higher risk (0.853 vs 0.563)"},
        ],
        "selected_symbol_score_drivers": {
            "momentum": 0.209,
            "trading_value": 0.2,
            "trend": 0.184,
            "repeat_symbol_penalty": -0.4,
        },
        "scanner_selection_trace": {
            "chart_feature_coverage": {
                "present": 12,
                "total": 13,
                "missing_keys": ["engine_ma60", "engine_ma120"],
            }
        },
        "summary": "scanner selected rank #1",
    }
    story_input["entry_summary"] = {
        "run_id": "run-entry",
        "ts": "2026-03-18T00:00:00+00:00",
        "action": "BUY",
    }

    report = mod._fallback_report(
        story_input,
        status="salvaged",
        mode="ai",
        model="openrouter/free",
        reason="partial",
    )

    why_summary = report["why_this_symbol_was_chosen"]["summary"]
    why_bullets = report["why_this_symbol_was_chosen"]["bullets"]
    entry_summary = report["entry_decision"]["summary"]
    assert "000660은 총 4개 후보 중 1위로 선정됐습니다." in why_summary
    assert "종합 점수는 1.286로 가장 높았습니다" in why_summary
    assert "강했던 축은 거래대금, 섹터·테마 정렬, 감성 지원 축이었습니다" in why_summary
    assert "005930은 종합 점수 1.223" in why_summary
    assert "047040은 종합 점수 1.201" in why_summary
    assert report["why_this_symbol_was_chosen"]["basis"] == "거래대금, 섹터·테마 정렬, 감성 지원"
    assert any("총 4개 후보를 비교했고 000660이 1위로 선정됐습니다." in row for row in why_bullets)
    assert any("주요 점수 기여는 모멘텀 0.209, 거래대금 0.200, 추세 0.184였습니다." in row for row in why_bullets)
    assert any("상위 후보는 #1 000660(1.286) / #2 005930(1.223) / #3 047040(1.201) 순이었습니다." in row for row in why_bullets)
    assert any("차트 피처 커버리지는 12/13였습니다." in row for row in why_bullets)
    assert not any("누락된 항목은 60일선, 120일선" in row for row in why_bullets)
    assert "000660이 스캐너 1위 후보로 올라온 뒤 매수로 이어졌습니다." in entry_summary


def test_prefer_fallback_summary_for_why_this_symbol_when_ai_summary_stays_english() -> None:
    preferred = mod._prefer_fallback_summary(
        "why_this_symbol_was_chosen",
        "000660 ranked #1 because it led on trading value, theme and sector alignment.",
        "000660은 스캐너 후보 중 최종 1순위였습니다. 거래대금과 섹터·테마 정렬이 강했습니다.",
    )

    assert preferred == "000660은 스캐너 후보 중 최종 1순위였습니다. 거래대금과 섹터·테마 정렬이 강했습니다."


def test_build_entry_decision_summary_and_bullets_surface_monitor_path_and_policy() -> None:
    summary = mod._build_entry_decision_summary(
        {
            "action": "BUY",
            "reason_human": "breakout_above_recent_high_with_vwap_structure_confirmation",
        },
        {
            "selected_symbol": "000660",
            "selected_rank": 1,
        },
        {
            "playbook": "pullback",
        },
        {
            "entry_condition_path": "breakout_path",
            "entry_grouped_logic_trace": {
                "triggered_path": "breakout_path",
                "reclaim_gate_ok": True,
                "extension_ok": True,
                "confidence_gate_ok": True,
            },
            "entry_condition_scores": {
                "confidence_score": 0.55,
                "confidence_threshold": 0.55,
                "entry_quality_score": 0.8123,
                "entry_quality_tier": "strong",
                "entry_quality_path": "breakout_path",
            },
        },
        "BUY",
    )
    bullets = mod._build_entry_decision_bullets(
        {
            "run_id": "run-entry",
            "ts": "2026-04-15T04:38:19+00:00",
            "action": "BUY",
            "reason_human": "breakout_above_recent_high_with_vwap_structure_confirmation",
        },
        {
            "selected_symbol": "000660",
            "selected_rank": 1,
            "selected_score": 1.286,
        },
        {
            "playbook": "pullback",
        },
        {
            "entry_condition_path": "breakout_path",
            "entry_condition_paths_passed": ["breakout_path"],
            "entry_grouped_logic_trace": {
                "triggered_path": "breakout_path",
                "paths_passed": ["breakout_path"],
                "reclaim_gate_ok": True,
                "extension_ok": True,
                "confidence_gate_ok": True,
            },
            "entry_condition_scores": {
                "confidence_score": 0.55,
                "confidence_threshold": 0.55,
                "entry_quality_score": 0.8123,
                "entry_quality_tier": "strong",
                "entry_quality_path": "breakout_path",
            },
            "entry_thresholds": {
                "timeframe_minutes": 1,
                "breakout_lookback": 4,
                "volume_ratio_min": 0.73,
                "require_vwap_reclaim": True,
                "require_rebound": True,
            },
        },
        "BUY",
    )

    assert "진입은 직전 고점 돌파와 VWAP 구조 확인 조건에서 실행됐습니다." in summary
    assert "000660이 스캐너 1위 후보로 올라온 뒤 매수로 이어졌습니다." in summary
    assert "전략가 플레이북은 눌림목이었지만 실제 엔트리는 돌파 경로에서 확정됐습니다." in summary
    assert "진입 게이트 점수는 0.5500이며 기준 0.5500과 동일했습니다." in summary
    assert "확률형 신뢰도가 아니라 모니터 진입 조건의 경로 점수입니다." in summary
    assert "진입 품질 점수는 0.8123 / 등급 strong / 우세 경로 돌파 경로였습니다." in summary
    assert "관측용이며 매수 허용 기준으로 쓰지 않습니다." in summary
    assert any("진입 사유는 직전 고점 돌파와 VWAP 구조 확인이었습니다." in row for row in bullets)
    assert any("진입 시점 스캐너에서는 000660이 1위, 종합 점수 1.286였습니다." in row for row in bullets)
    assert any("실제 진입 경로는 돌파 경로였습니다. 통과 경로는 돌파 경로였습니다." in row for row in bullets)
    assert any("진입 게이트 상태는 VWAP 재회복 통과, 과확장 점검 통과, 신뢰도 게이트 통과였습니다." in row for row in bullets)
    assert any("진입 품질 점수는 0.8123, 등급은 strong, 우세 경로는 돌파 경로였습니다." in row for row in bullets)
    assert any("적용 정책은 1분봉, 돌파 확인 기준 봉 수 4, 최소 거래량 비율 0.73, VWAP 재회복 필수, 반등 확인 필수였습니다." in row for row in bullets)


def test_fallback_entry_decision_uses_buy_detail_before_later_monitor_gate() -> None:
    story_input = _story_input()
    story_input.update(
        {
            "symbol": "050890",
            "action": "SELL",
            "status": "closed",
            "entry_summary": {
                "run_id": "run-entry",
                "ts": "2026-04-30T00:57:31+00:00",
                "action": "BUY",
                "reason_human": "breakout_above_recent_high_with_vwap_structure_confirmation",
            },
            "scanner_reason_human": {
                "selected_symbol": "050890",
                "selected_rank": 4,
                "selected_score": 0.799,
            },
            "market_context_human": {"playbook": "defensive"},
            "monitor_reason_human": {
                "posture": "SELL",
                "trigger_type": "hard_stop",
                "entry_condition_path": "",
                "entry_condition_scores": {
                    "confidence_score": 0.5488,
                    "confidence_threshold": 0.55,
                    "confidence_gate_ok": False,
                    "entry_quality_score": 0.7423,
                    "entry_quality_tier": "watch",
                    "entry_quality_path": "breakout_path",
                },
                "entry_grouped_logic_trace": {
                    "reclaim_gate_ok": False,
                    "extension_ok": True,
                    "confidence_gate_ok": False,
                    "triggered_path": "",
                    "paths_passed": [],
                },
            },
            "monitor_timeline": {
                "entry_decision_details": [
                    {
                        "run_id": "run-entry",
                        "ts": "2026-04-30T00:59:21+00:00",
                        "payload": {
                            "decision": "BUY",
                            "entry_triggered": True,
                            "buy_submitted": True,
                            "entry_reason": "breakout_above_recent_high_with_vwap_structure_confirmation",
                            "entry_condition_path": "breakout_path",
                            "entry_condition_paths_passed": ["breakout_path"],
                            "condition_scores": {
                                "confidence_score": 0.55,
                                "confidence_threshold": 0.55,
                                "confidence_gate_ok": True,
                                "entry_quality_score": 0.8647,
                                "entry_quality_tier": "strong",
                                "entry_quality_path": "breakout_path",
                            },
                            "grouped_logic_trace": {
                                "triggered_path": "breakout_path",
                                "paths_passed": ["breakout_path"],
                                "reclaim_gate_ok": True,
                                "extension_ok": True,
                                "confidence_gate_ok": True,
                            },
                            "applied_policy": {
                                "timeframe_minutes": 1,
                                "breakout_lookback": 5,
                                "volume_ratio_min": 0.79,
                                "require_vwap_reclaim": True,
                                "require_rebound": True,
                            },
                        },
                    }
                ]
            },
        }
    )

    report = mod._fallback_report(
        story_input,
        status="salvaged",
        mode="ai",
        model="openrouter/free",
        reason="partial",
    )

    summary = report["entry_decision"]["summary"]
    bullets = report["entry_decision"]["bullets"]
    assert "진입 게이트 점수는 0.5500이며 기준 0.5500과 동일했습니다." in summary
    assert "0.5488" not in summary
    assert any("진입 게이트 상태는 VWAP 재회복 통과, 과확장 점검 통과, 신뢰도 게이트 통과였습니다." in row for row in bullets)
    assert not any("진입 게이트 상태는 VWAP 재회복 미통과" in row for row in bullets)
    assert any("사후 모니터 재평가 게이트는 VWAP 재회복 미통과, 과확장 점검 통과, 신뢰도 게이트 미통과였습니다." in row for row in bullets)
    assert any("점수는 0.5488 / 기준 0.5500" in row for row in bullets)


def test_fallback_entry_decision_does_not_use_later_monitor_gate_as_entry_gate_without_buy_detail() -> None:
    story_input = _story_input()
    story_input.update(
        {
            "symbol": "050890",
            "action": "SELL",
            "status": "closed",
            "entry_summary": {
                "run_id": "run-entry",
                "ts": "2026-04-30T00:57:31+00:00",
                "action": "BUY",
                "reason_human": "breakout_above_recent_high_with_vwap_structure_confirmation",
            },
            "scanner_reason_human": {
                "selected_symbol": "050890",
                "selected_rank": 4,
                "selected_score": 0.799,
            },
            "monitor_reason_human": {
                "posture": "SELL",
                "trigger_type": "hard_stop",
                "active_exit_axis": "hard_stop",
                "position_age_seconds": 240,
                "entry_condition_path": "",
                "entry_condition_scores": {
                    "confidence_score": 0.5488,
                    "confidence_threshold": 0.55,
                    "confidence_gate_ok": False,
                },
                "entry_grouped_logic_trace": {
                    "reclaim_gate_ok": False,
                    "extension_ok": True,
                    "confidence_gate_ok": False,
                    "triggered_path": "",
                    "paths_passed": [],
                },
            },
            "monitor_timeline": {"entry_decision_details": []},
        }
    )

    report = mod._fallback_report(
        story_input,
        status="salvaged",
        mode="ai",
        model="openrouter/free",
        reason="partial",
    )

    summary = report["entry_decision"]["summary"]
    bullets = report["entry_decision"]["bullets"]
    summary_markdown = mod.render_trade_summary_markdown(report)
    entry_section = summary_markdown.split("## 🚪 진입 판단", 1)[1].split("---", 1)[0]

    assert "진입 게이트 점수는 0.5488" not in summary
    assert not any(row.startswith("진입 게이트 상태는") for row in bullets)
    assert any(row.startswith("사후 모니터 재평가 게이트는") for row in bullets)
    assert "신뢰도 게이트 미통과" not in entry_section


def test_entry_decision_detail_can_be_read_from_monitor_evidence_artifact(tmp_path) -> None:
    evidence_path = tmp_path / "monitor_evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "entry_decision_details": [
                    {
                        "run_id": "run-entry",
                        "payload": {
                            "decision": "BUY",
                            "entry_triggered": True,
                            "entry_condition_path": "breakout_path",
                            "condition_scores": {"confidence_score": 0.55},
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    detail = mod._select_entry_decision_detail(
        {
            "monitor_timeline": {},
            "artifacts": {"monitor_evidence_json": str(evidence_path)},
        },
        {"run_id": "run-entry"},
    )

    assert detail["run_id"] == "run-entry"
    assert detail["payload"]["condition_scores"]["confidence_score"] == 0.55


def test_prefer_fallback_summary_for_entry_decision_when_ai_summary_stays_english() -> None:
    preferred = mod._prefer_fallback_summary(
        "entry_decision",
        "breakout_above_recent_high_with_vwap_structure_confirmation with strategist-guided weighting.",
        "진입은 직전 고점 돌파와 VWAP 구조 확인 조건에서 실행됐습니다.",
    )

    assert preferred == "진입은 직전 고점 돌파와 VWAP 구조 확인 조건에서 실행됐습니다."


def test_build_reporter_evaluation_section_surfaces_responsibility_split() -> None:
    section = mod._build_reporter_evaluation_section(
        {
            "symbol": "000660",
            "holding_duration": "1.1m",
            "exit_reason": "SELL was triggered because peak_drawdown.",
        },
        {
            "selected_symbol": "000660",
            "selected_rank": 1,
            "selected_score": 1.286,
            "confidence": 0.728,
            "top_candidates": [
                {"rank": 1, "symbol": "000660", "score_total": 1.286, "risk_score": 0.563, "confidence": 0.728},
            ],
        },
        {
            "position_age_seconds": 60,
            "trigger_type": "peak_drawdown",
        },
        {
            "summary": "SELL order for 000660 x1 was approved and recorded successfully in simulation mode.",
        },
        {
            "status": "linked",
            "grade": "N/A",
            "same_day_linkage_status": "linked_run",
            "same_day_linkage_reason": "A same-day reporter analysis linked directly to this lifecycle run.",
            "summary": "Monitor behavior showed overtrading or rapid exit pressure in this run window.",
        },
    )

    assert "이번 거래는 종목 선정 자체보다 진입 타이밍 부담이 더 크게 드러났습니다." in section["summary"]
    assert "스캐너는 000660을 1위" in section["summary"]
    assert "추가 상승 지속성이 약했습니다." in section["summary"]
    assert "실행 기록상 주문 자체 문제는 보이지 않았습니다." in section["summary"]
    assert any("종목 선정 평가는 000660 1위" in row for row in section["bullets"])
    assert any("진입 평가는 진입 후 약 1분 6초 만에 고점 대비 하락폭 청산이 나와" in row for row in section["bullets"])
    assert any("청산 평가는 청산 축이 고점 대비 하락폭으로 명확해" in row for row in section["bullets"])
    assert any("보유 평가는 보유 시간이 1분 6초에 그쳐 중간 악화 흐름을 두껍게 읽기에는 정보가 부족합니다." in row for row in section["bullets"])
    assert any("당일 리포터 연계 상태는 동일 실행 기록 직접 연계였습니다." in row for row in section["bullets"])
    assert any("동일 일자 리포터도 과매매 또는 빠른 청산 압력을 시사했습니다." in row for row in section["bullets"])


def test_build_reporter_evaluation_section_uses_same_day_feedback_packet_when_linkage_is_missing() -> None:
    section = mod._build_reporter_evaluation_section(
        {
            "symbol": "047040",
            "holding_duration": "48s",
            "exit_reason": "SELL was triggered because peak_drawdown.",
        },
        {
            "selected_symbol": "047040",
            "selected_rank": 2,
            "selected_score": 1.112,
            "confidence": 0.64,
            "top_candidates": [],
        },
        {
            "position_age_seconds": 48,
            "trigger_type": "peak_drawdown",
        },
        {
            "summary": "SELL order for 047040 x1 was approved and recorded successfully in live mode.",
        },
        {
            "status": "missing",
            "grade": "N/A",
            "same_day_linkage_status": "missing",
            "summary": "당일 리포터 분석은 아직 생성되지 않았습니다.",
        },
        {
            "available": True,
            "consumed": True,
            "confidence": "high",
            "source_reports": {
                "trade_reports": True,
                "metrics": False,
                "reporter_analysis": False,
            },
            "insight_summary": "Same-day closed trade reports show 3 trades with 1 wins, 2 losses, avg pnl pct -0.003.",
            "dominant_patterns": [
                {"name": "same_price_cost_loss_ratio", "detail": "same-price cost-loss trades 2/3", "value": 0.66},
            ],
            "recommendation": [
                "Same-price round trips produced fee/tax drag; tighten follow-through evidence before repeating quick reversals.",
            ],
            "trade_report_analysis": {
                "closed_trade_count": 3,
                "win_count": 1,
                "loss_count": 2,
                "avg_pnl_pct": -0.003,
            },
        },
    )

    assert section["status"] == "ok"
    assert section["grade"] == "A"
    assert "당일 reporter feedback은 당일 닫힌 거래 리포트 기준으로 생성됐습니다." in section["summary"]
    assert "당일 closed trade 3건, 승/패 1/2, 평균 손익률 -0.30%였습니다." in section["summary"]
    assert any("피드백 생성 소스는 당일 닫힌 거래 리포트입니다." in row for row in section["bullets"])
    assert any("권고: 동일가 왕복 거래에서 수수료와 세금 손실이 반복돼" in row for row in section["bullets"])


def test_holding_duration_label_humanizes_fractional_minutes() -> None:
    assert mod._holding_duration_label("1.1m") == "보유 시간은 1분 6초였습니다."


def test_operatorize_report_text_normalizes_strategy_policy_line() -> None:
    rendered = mod._operatorize_report_text("적용 정책: timeframe 1분, breakout lookback 5, volume ratio min 0.75")

    assert rendered == "적용 정책은 1분봉, 돌파 확인 기준 봉 수 5, 최소 거래량 비율 0.75였습니다."


def test_operatorize_report_text_normalizes_final_conclusion_and_timeline_phrases() -> None:
    assert (
        mod._operatorize_report_text("Current lifecycle status is closed. Entry and exit are connected in one lifecycle story.")
        == "이번 라이프사이클은 종결 상태이며, 진입과 청산이 하나의 거래 흐름으로 연결됐습니다."
    )
    assert (
        mod._operatorize_report_text("Supervisor approved the order because Allowed.")
        == "슈퍼바이저는 주문을 승인했고 가드 판단은 허용이었습니다."
    )
    assert (
        mod._operatorize_report_text("Entry BUY was executed by run abc123.")
        == "run abc123에서 매수 진입이 실행됐습니다."
    )
    assert (
        mod._operatorize_report_text("Exit SELL was executed by run def456.")
        == "run def456에서 매도 청산이 실행됐습니다."
    )
    assert mod._operatorize_report_text("Monitor trigger changes") == "모니터 트리거 변화"
    assert mod._operatorize_report_text("Macro/news shifts") == "거시 환경 및 뉴스 변화"
    assert mod._operatorize_report_text("stop-loss breach") == "손절 기준 이탈"


def test_prefer_fallback_summary_for_reporter_evaluation_when_ai_summary_stays_english() -> None:
    preferred = mod._prefer_fallback_summary(
        "reporter_evaluation",
        "Monitor behavior showed overtrading or rapid exit pressure in this run window.",
        "이번 거래는 종목 선정 자체보다 진입 타이밍 부담이 더 크게 드러났습니다.",
    )

    assert preferred == "이번 거래는 종목 선정 자체보다 진입 타이밍 부담이 더 크게 드러났습니다."


def test_ai_trade_report_merge_keeps_priority_fallback_scanner_bullets() -> None:
    story_input = _story_input()
    story_input["scanner_reason_human"] = {
        "selected_symbol": "000660",
        "selected_rank": 1,
        "universe_size": 5,
        "summary": "scanner selected rank #1",
        "bullets": [
            "Universe scanned: 5",
            "Top candidates: #1 000660 score 1.178; #2 005930 score 1.152; #3 047040 score 1.141",
            "Selection decision: highest total score (1.178); confidence 0.81 and risk 0.63",
            "Final decision basis: Scanner selected the highest-ranked candidate after strategist-guided weighting.",
            "Tie-break rule: score_total desc -> confidence desc -> risk_score asc",
            "Runner-ups lost because: 005930: lower total score (1.152 vs 1.178)",
        ],
        "why_selected": ["highest total score (1.178)"],
        "selection_basis": "Scanner selected the highest-ranked candidate after strategist-guided weighting.",
        "tie_break_rule": "score_total desc -> confidence desc -> risk_score asc",
        "runner_ups_lost": [{"symbol": "005930", "summary": "lower total score (1.152 vs 1.178)"}],
    }

    report = mod._merge_trade_report_candidate(
        story_input,
        {
            "executive_summary": {"headline": "HOLD 000660", "action": "HOLD", "symbol": "000660", "confidence": "high", "summary": "ok"},
            "market_context_at_entry": {"summary": "context", "bullets": ["vix noted"]},
            "why_this_symbol_was_chosen": {"summary": "rank #1", "bullets": ["selected for strength"]},
            "entry_decision": {"summary": "entry", "bullets": []},
            "holding_monitoring_story": {"summary": "hold", "bullets": []},
            "exit_decision": {"summary": "open trade", "bullets": []},
            "execution_quality": {"summary": "execution", "bullets": []},
            "scanner_filters": {"summary": "filters", "bullets": []},
            "guard_approval_result": {"summary": "guard", "bullets": []},
            "reporter_evaluation": {"summary": "reporter", "status": "pending", "grade": "N/A", "bullets": []},
            "errors_weaknesses_improvement_points": {"summary": "none", "bullets": []},
            "full_timeline": [{"event": "entry", "ts": "2026-03-18T00:00:00+00:00", "description": "entry"}],
            "final_operator_conclusion": {"summary": "hold", "current_action": "HOLD", "watch_next": ["watch"], "thesis_invalidation": ["stop"]},
        },
        status="ok",
        mode="ai",
        model="openrouter/free",
        reason="ok",
    )

    bullets = report["why_this_symbol_was_chosen"]["bullets"]
    assert "selected for strength" in bullets
    assert any("Top candidates:" in str(row) for row in bullets)
    assert any("Selection decision:" in str(row) for row in bullets)
    assert any("Tie-break rule:" in str(row) for row in bullets)


def test_ai_trade_report_merge_prefers_detailed_monitor_fallback_when_ai_bullets_are_generic() -> None:
    story_input = _story_input()
    story_input["holding_summary"] = {
        "run_ids": [f"run-{idx}" for idx in range(6)],
        "monitor_updates": ["hold", "hold", "hold"],
    }
    story_input["monitor_reason_human"] = {
        "posture": "HOLD",
        "trigger_type": "hold",
        "position_age_seconds": 1974,
        "effective_stop_loss_pct": 0.01,
        "effective_stop_reason": "hard_stop",
        "take_profit_pct": 0.0123,
        "active_exit_axis": "Hold",
        "watch_axes": ["Hard stop", "Take profit", "VWAP breakdown"],
        "confirm_required": 1,
        "confirm_count": 0,
        "decision_reason_chain": ["hold", "hold", "hold"],
        "current_price": 1012000.0,
        "average_price": 1011000.0,
        "peak_price": 1013000.0,
        "current_drawdown": -0.001,
        "peak_drawdown": -0.001,
        "price_source": "position.current_price",
        "feature_source": "selected.features",
    }

    report = mod._merge_trade_report_candidate(
        story_input,
        {
            "executive_summary": {"headline": "HOLD 000660", "action": "HOLD", "symbol": "000660", "confidence": "high", "summary": "ok"},
            "market_context_at_entry": {"summary": "context", "bullets": ["vix noted"]},
            "why_this_symbol_was_chosen": {"summary": "rank #1", "bullets": ["selected for strength"]},
            "entry_decision": {"summary": "entry", "bullets": []},
            "holding_monitoring_story": {"summary": "hold", "bullets": ["hold", "hold", "hold", "hold"]},
            "exit_decision": {"summary": "open trade", "bullets": ["hold"]},
            "execution_quality": {"summary": "execution", "bullets": []},
            "scanner_filters": {"summary": "filters", "bullets": []},
            "guard_approval_result": {"summary": "guard", "bullets": []},
            "reporter_evaluation": {"summary": "reporter", "status": "pending", "grade": "N/A", "bullets": []},
            "errors_weaknesses_improvement_points": {"summary": "none", "bullets": []},
            "full_timeline": [{"event": "entry", "ts": "2026-03-18T00:00:00+00:00", "description": "entry"}],
            "final_operator_conclusion": {"summary": "hold", "current_action": "HOLD", "watch_next": ["watch"], "thesis_invalidation": ["stop"]},
        },
        status="ok",
        mode="ai",
        model="openrouter/free",
        reason="ok",
    )

    bullets = report["holding_monitoring_story"]["bullets"]
    assert any("Monitor runs:" in str(row) for row in bullets)
    assert any(str(row).startswith("현재 포지션 판단은") for row in bullets)
    assert any(str(row).startswith("유효 손절 기준은") for row in bullets)
    assert any(str(row).startswith("판단 흐름은") for row in bullets)


def test_ai_trade_report_fallback_exit_decision_uses_exit_monitor_context_details() -> None:
    story_input = _story_input()
    story_input["status"] = "closed"
    story_input["exit_summary"] = {
        "run_id": "run-exit",
        "ts": "2026-03-18T00:10:00+00:00",
        "action": "SELL",
        "reason_human": "SELL was triggered because hard_stop.",
        "monitor_context": {
            "trigger_type": "hard_stop",
            "active_exit_axis": "Hard Stop",
            "confirm_required": 3,
            "confirm_count": 0,
            "effective_stop_loss_pct": 0.01,
            "effective_stop_reason": "hard_stop",
            "take_profit_pct": 0.0084,
            "current_price": 29300.0,
            "average_price": 29650.0,
            "peak_price": 29650.0,
            "current_drawdown": -0.0118,
            "decision_reason_chain": ["confirmed_exit_signal", "hard_stop", "hard_stop"],
            "price_source": "position.current_price",
            "feature_source": "selected.features",
        },
        "guard_context": {"summary": "Supervisor approved the order because Allowed."},
        "execution_context": {"summary": "SELL order for 032820 x1 was approved and recorded successfully in simulation mode."},
    }

    report = mod._fallback_report(
        story_input,
        status="salvaged",
        mode="ai",
        model="openrouter/free",
        reason="partial",
    )

    summary = report["exit_decision"]["summary"]
    bullets = report["exit_decision"]["bullets"]
    assert "청산 당시 상황은" in summary
    assert "확인 조건은 0/3" in summary
    assert "현재가는 29300.00, 평균가는 29650.00" in summary
    assert any("Trigger type:" in str(row) for row in bullets)
    assert any(str(row).startswith("청산 시점의 유효 손절 기준은 1.00%") for row in bullets)
    assert any(str(row).startswith("현재가, 평균가, 고점 기준 값은 29300.00 / 29650.00 / 29650.00") for row in bullets)
    assert any("청산 확인 신호 -> 고정 손절 -> 고정 손절 기준" in str(row) or "confirmed_exit_signal -> hard_stop -> hard_stop" in str(row) for row in bullets)


def test_ai_trade_report_prefers_hangul_execution_bullets_without_english_duplicates() -> None:
    story_input = _story_input()
    report = mod._merge_trade_report_candidate(
        story_input,
        {
            "executive_summary": {"headline": "HOLD 000660", "action": "HOLD", "symbol": "000660", "confidence": "high", "summary": "ok"},
            "market_context_at_entry": {"summary": "context", "bullets": ["vix noted"]},
            "why_this_symbol_was_chosen": {"summary": "rank #1", "bullets": ["selected for strength"]},
            "entry_decision": {"summary": "entry", "bullets": []},
            "holding_monitoring_story": {"summary": "hold", "bullets": []},
            "exit_decision": {"summary": "open trade", "bullets": []},
            "execution_quality": {
                "summary": "?ㅽ뻾???뺤긽 ?꾨즺?섏뿀?듬땲??",
                "bullets": ["Execution outcome: recorded", "Filled qty: 1", "Execution mode: simulation (mock broker)"],
            },
            "scanner_filters": {"summary": "filters", "bullets": []},
            "guard_approval_result": {"summary": "guard", "bullets": []},
            "reporter_evaluation": {"summary": "reporter", "status": "pending", "grade": "N/A", "bullets": []},
            "errors_weaknesses_improvement_points": {"summary": "none", "bullets": []},
            "full_timeline": [{"event": "entry", "ts": "2026-03-18T00:00:00+00:00", "description": "entry"}],
            "final_operator_conclusion": {"summary": "hold", "current_action": "HOLD", "watch_next": ["watch"], "thesis_invalidation": ["stop"]},
        },
        status="ok",
        mode="ai",
        model="openrouter/free",
        reason="ok",
    )

    bullets = report["execution_quality"]["bullets"]
    assert any("실행 모드는 시뮬레이션" in row for row in bullets)
    assert any("브로커 환경 정보는 별도로 기록되지 않았습니다." == row for row in bullets)
    assert any("주문 상태는 별도로 기록되지 않았습니다." == row for row in bullets)


def test_ai_trade_report_normalizes_internal_english_labels_in_json_sections() -> None:
    story_input = _story_input()
    report = mod._merge_trade_report_candidate(
        story_input,
        {
            "executive_summary": {"headline": "SELL 005930", "action": "SELL", "symbol": "005930", "confidence": "high", "summary": "ok"},
            "market_context_at_entry": {
                "summary": "context",
                "bullets": ["Market regime: neutral", "Global sentiment score: -0.07", "News input: 60 headlines were considered."],
            },
            "why_this_symbol_was_chosen": {
                "summary": "rank #1",
                "bullets": ["Top candidates: #1 005930", "Selection decision: highest total score"],
            },
            "entry_decision": {"summary": "entry", "bullets": ["Entry action: BUY", "Entry reason: breakout confirmed"]},
            "holding_monitoring_story": {
                "summary": "hold",
                "bullets": ["Monitor runs: 6", "Posture: HOLD", "Effective stop: 1.00% (hard_stop)"],
            },
            "exit_decision": {"summary": "open trade", "bullets": ["Exit action: SELL", "Exit reason: hard_stop"]},
            "execution_quality": {"summary": "execution", "bullets": ["Execution outcome: recorded", "Execution mode: simulation (mock broker)"]},
            "scanner_filters": {"summary": "filters", "bullets": ["liquidity filter: PASS - top value input supported the selection"]},
            "guard_approval_result": {"summary": "guard", "bullets": ["Supervisor verdict: approve", "Guard reason: Allowed"]},
            "reporter_evaluation": {"summary": "reporter", "status": "pending", "grade": "N/A", "bullets": []},
            "errors_weaknesses_improvement_points": {"summary": "none", "bullets": []},
            "full_timeline": [],
            "final_operator_conclusion": {"summary": "hold", "current_action": "HOLD", "watch_next": ["watch"], "thesis_invalidation": []},
        },
        status="ok",
        mode="ai",
        model="openrouter/free",
        reason="ok",
    )

    all_bullets = []
    for key in (
        "market_context_at_entry",
        "why_this_symbol_was_chosen",
        "entry_decision",
        "holding_monitoring_story",
        "exit_decision",
        "execution_quality",
        "scanner_filters",
        "guard_approval_result",
    ):
        all_bullets.extend(list((report.get(key) or {}).get("bullets") or []))

    joined = "\n".join(str(row) for row in all_bullets)
    assert "Market regime:" not in joined
    assert "Monitor runs:" not in joined
    assert "Execution outcome:" not in joined
    assert "시장 상태는" in joined
    assert "현재 포지션 판단은 보유 유지입니다." in joined
    assert "실행 모드는 시뮬레이션" in joined


def test_render_trade_report_markdown_uses_korean_titles_and_narrative_labels() -> None:
    report = {
        "trade_id": "TRD_20260320_005930_01",
        "action": "BUY",
        "symbol": "005930",
        "status": "open",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "?쇱꽦?꾩옄 ?④린 紐⑤찘? 吏꾩엯 ?댄썑 ?꾩옱??蹂댁쑀 ?좎? 愿?먯쑝濡?愿由?以묒엯?덈떎."},
        "market_context_at_entry": {"summary": "?쒖옣 ?섍꼍? 以묐┰?댁?留?諛섎룄泥???뺤＜濡??섍툒??吏묒쨷?먯뒿?덈떎.", "bullets": ["global sentiment -0.20", "vix 25.09"]},
        "why_this_symbol_was_chosen": {"summary": "?꾩껜 ?꾨낫 以?1?쒖쐞濡??좎젙?먯뒿?덈떎.", "bullets": ["Top candidates: 005930, 000660, 047040"]},
        "entry_decision": {"summary": "遺꾨큺 湲곗? ?뚰뙆? 嫄곕옒??利앷?媛 ?④퍡 ?뺤씤?먯뒿?덈떎.", "bullets": ["VWAP hold", "volume ratio 1.8x"]},
        "holding_monitoring_story": {
            "summary": "hold",
            "bullets": [
                "Monitor runs: 6",
                "Posture: HOLD",
                "Effective stop: 1.00% (hard_stop)",
                "Take profit: 1.80%",
                "Watch axes: Hard stop, Adaptive stop, Take profit, VWAP breakdown",
            ],
        },
        "exit_decision": {"summary": "open trade", "bullets": ["Exit trigger: no"]},
        "scanner_filters": {"summary": "filters", "bullets": ["liquidity filter: pass"]},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "none", "bullets": []},
        "full_timeline": [{"event": "entry", "description": "breakout confirmed"}],
        "final_operator_conclusion": {"summary": "hold", "current_action": "HOLD", "watch_next": ["VWAP retest"], "thesis_invalidation": ["prior low break"]},
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "# AI 거래 리포트" in markdown
    assert "## 시장 환경 요약" in markdown
    assert "## 보유 경과" in markdown
    assert "## 청산 판단 근거" in markdown
    assert "## 최종 운영 판단" in markdown
    assert "Executive Summary" not in markdown
    assert "Holding / Monitoring Story" not in markdown
    assert "Posture:" not in markdown
    assert "Take profit" not in markdown
    assert "Hard stop" not in markdown
    assert "현재 포지션 판단은 보유 유지입니다." in markdown
    assert "모니터는 총 6회 실행되었습니다." in markdown
    assert "vix 25.09" in markdown


def test_render_trade_summary_markdown_creates_operator_summary_without_replacing_full_report() -> None:
    report = {
        "trade_id": "TRD_SUMMARY",
        "symbol": "000660",
        "status": "closed",
        "story_type": "simulation",
        "execution_mode_label": "simulation (mock broker)",
        "action": "SELL",
        "shared_facts": {
            "symbol": "000660",
            "status": "closed",
            "action": "SELL",
            "pnl": -1000,
            "pnl_pct": -0.01,
            "broker_buy_price": 100000,
            "broker_fill_price": 99000,
            "broker_fee": 10,
            "broker_tax": 5,
            "pnl_truth_source": "kiwoom.ka10077",
            "holding_duration": "12m",
            "exit_reason": "SELL was triggered because peak_drawdown.",
        },
        "market_context_at_entry": {
            "summary": "코스피는 혼조였습니다.",
            "playbook": "defensive",
            "risk_mode": "balanced",
            "market_sentiment": "neutral",
            "market_news_titles": ["코스피: 시장 뉴스"],
            "candidate_news_titles": ["000660: 종목 뉴스"],
        },
        "monitor_snapshot": {
            "current_price": 99500.0,
            "average_price": 100000.0,
            "peak_price": 100500.0,
            "gross_pnl_ratio": 0.0,
            "effective_pnl_ratio": -0.009,
            "stop_pnl_ratio": 0.0,
            "stop_pnl_ratio_source": "raw_price",
            "hard_stop_pnl_ratio": -0.009,
            "hard_stop_pnl_ratio_source": "account_pnl_ratio_mark",
            "cost_drag_pressure": True,
            "cost_drag_pressure_pct": 0.009,
            "cost_drag_pressure_reason": "account_pnl_ratio_more_conservative",
            "stop_loss_cost_drag_blocked": True,
            "stop_loss_cost_drag_blocked_reason": "net_pnl_stop_loss_without_technical_stop",
        },
        "why_this_symbol_was_chosen": {
            "symbol": "000660",
            "selected_rank": 2,
            "score_total": 1.108,
            "basis": "거래대금",
            "bullets": ["스캐너 1순위 047040은 막혔고 실제 진입 종목은 000660입니다."],
        },
        "entry_decision": {
            "bullets": [
                "진입 사유는 직전 고점 돌파와 VWAP 구조 확인이었습니다.",
                "진입 게이트 점수는 0.5500이며 기준 0.5500과 동일했습니다. 표시 목적은 확률형 신뢰도보다 진입 조건 통과 여부 확인입니다.",
            ]
        },
        "exit_decision": {
            "summary": "고점 대비 하락폭 기준으로 청산. 청산 당시 상황은 핵심 청산 축은 고점 대비 하락폭, 확인 조건은 0/1, 현재가는 99500.00, 평균가는 100000.00, 현재 손익 변동은 -0.50%입니다.",
            "bullets": [
                "청산을 직접 촉발한 신호는 고점 대비 하락폭이었습니다.",
                "현재가, 평균가, 고점 기준 값은 99500.00 / 100000.00 / 100500.00입니다.",
            ],
        },
        "post_exit_shadow": {
            "observability_only": True,
            "status": "pending",
            "symbol": "000660",
            "exit_price": 99000,
            "price_observation_status": "observed",
            "best_exit_offset": "+15m",
            "best_exit_price": 101500,
            "checkpoints": {
                "+5m": {
                    "status": "observed",
                    "price": 100000,
                    "high_since_exit": 100500,
                    "low_since_exit": 98500,
                    "return_pct": 0.0101010101,
                },
                "+15m": {
                    "status": "observed",
                    "price": 101000,
                    "high_since_exit": 101500,
                    "low_since_exit": 98500,
                    "return_pct": 0.0202020202,
                },
                "+30m": {"status": "pending"},
                "+60m": {"status": "pending"},
            },
        },
        "reporter_evaluation": {
            "bullets": [
                "당일 closed trade 집계는 9건, 승패 2/6, 평균 손익률 -0.40%입니다.",
                "주요 패턴: monitor_only 25/25 runs",
            ]
        },
        "memory_application_surface": {
            "scanner_memory_bias": {"applied": False},
            "monitor_memory_bias": {
                "applied": True,
                "active_layers": ["symbol"],
                "applied_deltas": [{"field": "breakout_buffer_pct", "from": 0.0, "to": 0.001, "delta": 0.001}],
                "exit_deltas": [{"field": "peak_drawdown_exit_pct", "from": 0.005, "to": 0.003, "delta": -0.002}],
            },
        },
        "final_operator_conclusion": {"summary": "최종 판단입니다.", "current_action": "SELL"},
        "full_timeline": [
            {"event": "entry", "description": "Entry BUY was executed by run 102ca680681e444ca5849816df5316a5."},
            {"event": "exit", "description": "Exit SELL was executed by run 8a8ed5ff82ed4f07bf696750d8e2c16b."},
        ],
    }

    summary = mod.render_trade_summary_markdown(report)
    summary_input = mod.build_trade_summary_input(report)
    summary_report = mod.build_trade_summary_report(summary_input, enabled=False)
    evaluated_summary = {
        **summary_report,
        "generation": {"status": "ok", "mode": "ai", "model": "test"},
        "llm_evaluation": {
            "conclusion": "청산 조건과 차순위 진입 구조를 우선 점검해야 합니다.",
            "root_cause": "root_cause_candidates가 비어 있어 단정은 어렵지만 peak_drawdown 기준과 scanner 재평가가 손익비를 압박했습니다.",
            "priority_actions": ["peak_drawdown confirm 조건 재검증"],
            "risk_notes": ["중립 inúmer により 阈值 미달성况"],
            "validation_questions": ["monitor_only 경로가 25/25로 고정된 이유는何か?"],
        },
    }
    full = mod.render_trade_report_markdown(report)
    summary_with_eval = mod.render_trade_summary_markdown_with_evaluation(report, evaluated_summary)

    assert "## 🔴 운영 요약 (Operator Decision Summary)" in summary
    assert "## 📊 실행 결과 (Truth Surface)" in summary
    assert "당일 성과(리포트 생성 시점 기준)" in summary
    assert "9건 중 2승 / 6패 / 평균 -0.40%" in summary
    assert "peak_drawdown activation/confirm 조건 점검" in summary
    assert summary_input["schema_version"] == "ai_trade_summary_input.v1"
    assert summary_input["same_day_context"]["basis"] == "report_generation_time"
    assert summary_input["same_day_context"]["label"] == "당일 성과(리포트 생성 시점 기준)"
    assert summary_input["truth_surface"]["pnl"] == -1000
    assert summary_input["decision_flow"]["scanner_rank"] == 2
    assert summary_input["decision_flow"]["exit_reason"] == "고점 대비 하락폭 기준"
    assert summary_input["decision_flow"]["exit_observation"]["basis"] == "monitor_signal_snapshot"
    assert summary_input["decision_flow"]["exit_observation"]["monitor_current_price"] == 99500.0
    assert summary_input["decision_flow"]["exit_observation"]["position_avg_price"] == 100000.0
    assert summary_input["decision_flow"]["exit_observation"]["gross_pnl_ratio"] == 0.0
    assert summary_input["decision_flow"]["exit_observation"]["effective_pnl_ratio"] == -0.009
    assert summary_input["decision_flow"]["exit_observation"]["stop_pnl_ratio"] == 0.0
    assert summary_input["decision_flow"]["exit_observation"]["stop_loss_cost_drag_blocked"] is True
    assert summary_input["post_exit_shadow"]["price_observation_status"] == "observed"
    assert summary_input["post_exit_shadow"]["checkpoints"]["+5m"]["price"] == 100000
    assert "price" in summary_input["llm_task"]["hard_constraints"][0]
    assert "monitor_signal_snapshot" in summary_input["llm_task"]["hard_constraints"][2]
    assert "observation-only" in summary_input["llm_task"]["hard_constraints"][3]
    assert summary_report["schema_version"] == "ai_trade_summary.v1"
    assert "포지션 평균단가(모니터 신호 계산용) 100,000" in summary
    assert "고점 대비 하락폭 -0.50%" in summary
    assert "손익 기준 분리: 가격 기준 손익 0.00% / 비용/계좌 반영 손익 -0.90% / 일반 손절 판단 기준 0.00%, raw_price" in summary
    assert "일반 손절 차단: 가격 기준 손절선은 미통과했고 비용 반영 손익만 손절선을 건드렸습니다" in summary
    assert "신호 기준 손익" not in summary
    assert "체결/실현손익 기준: Truth Surface의 매수가 100,000 / 매도가 99,000" in summary
    assert "### 매도 후 가격 추적 (관측-only)" in summary
    assert "* +5분: 100,000 (1.01%) / 구간 고가 100,500 / 구간 저가 98,500" in summary
    assert "현재까지 최선 가상 청산 지점: +15분, 101,500" in summary
    assert "## 매도 후 가격 추적 (관측-only)" in full
    assert "* +15분: 101,000 (2.02%) / 구간 고가 101,500 / 구간 저가 98,500" in full
    assert "평균가는" not in summary
    assert "## 🧾 확정 진단" in summary_with_eval
    assert "## 🤖 LLM 복기 초안" in summary_with_eval
    assert summary_with_eval.index("## 🧾 확정 진단") < summary_with_eval.index("## 🤖 LLM 복기 초안")
    assert summary_with_eval.index("## 🤖 LLM 복기 초안") < summary_with_eval.index("## 🧭 거래 개요")
    assert "root_cause_candidates" not in summary_with_eval
    assert "何か" not in summary_with_eval
    assert "により" not in summary_with_eval
    assert "阈值" not in summary_with_eval
    assert "inúmer" not in summary_with_eval
    assert "?입니다" not in summary_with_eval
    assert "## 🔴 운영 요약 (Operator Decision Summary)" not in full

    messages = mod._build_trade_summary_evaluation_messages(summary_input)
    prompt = "\n".join(message["content"] for message in messages)
    assert "exit_observation은 모니터 신호 판단용 스냅샷" in prompt
    assert "Truth Surface 기준과 모니터 관측값 기준을 반드시 구분" in prompt


def test_trade_summary_marks_recovered_partial_sell_as_exit_only() -> None:
    report = {
        "trade_id": "TRD_20260506_036540_01",
        "symbol": "036540",
        "status": "partial",
        "story_type": "simulation",
        "execution_mode_label": "simulation (mock broker)",
        "action": "SELL",
        "trade_origin": "recovered_partial",
        "lifecycle_completeness": "partial",
        "evidence_recovery_used": True,
        "shared_facts": {
            "symbol": "036540",
            "status": "partial",
            "action": "SELL",
            "broker_buy_price": 8620,
            "broker_fill_price": 8970,
            "broker_fee": 610,
            "broker_tax": 179,
            "pnl": 2711,
            "pnl_pct": 0.0315,
            "pnl_truth_source": "kiwoom.ka10077",
            "exit_reason": "SELL was triggered because stop_loss.",
        },
        "truth_surface": {
            "price": {"broker_buy_price": 8620, "broker_fill_price": 8970},
            "pnl": {
                "value": 2711,
                "pnl_pct": 0.0315,
                "broker_fee": 610,
                "broker_tax": 179,
                "pnl_truth_source": "kiwoom.ka10077",
            },
        },
        "market_context_at_entry": {"summary": "시장 컨텍스트가 캡처되지 않았습니다.", "risk_mode": "balanced"},
        "why_this_symbol_was_chosen": {
            "symbol": "036540",
            "selected_rank": 0,
            "universe_size": 0,
            "basis": "combined scanner ranking score",
        },
        "entry_decision": {
            "summary": "Entry evidence was not captured for this day. Position context was inferred from downstream monitor/exit artifacts.",
            "bullets": [
                "진입 사유는 Entry evidence was not captured for this day. Position context was inferred from downstream monitor/exit artifacts.",
            ],
        },
        "holding_monitoring_story": {
            "summary": "SELL was triggered because stop_loss.",
            "bullets": ["Trigger type: stop_loss"],
        },
        "exit_decision": {
            "summary": "stop_loss 기준으로 청산됐습니다.",
            "bullets": [
                "청산을 직접 촉발한 신호는 stop_loss입니다.",
                "청산 확인 조건은 0/1 단계로 기록되었습니다.",
                "현재가, 평균가, 고점 기준 값은 8620.00 / 8620.00 / 8620.00입니다.",
                "현재 손익 변동은 0.00%입니다.",
            ],
        },
        "reporter_evaluation": {"summary": "", "bullets": []},
        "final_operator_conclusion": {
            "summary": "현재 판단은 청산 완료입니다.",
            "current_action": "SELL",
        },
    }

    summary = mod.render_trade_summary_markdown(report)
    summary_input = mod.build_trade_summary_input(report)

    assert "회수/partial 청산: 당일 진입 증거가 부족해 신규 진입 평가는 제외" in summary
    assert "* 스캐너 순위: 기록 없음" in summary
    assert "* 스캐너 순위: 0위" not in summary
    assert "신규 진입 판단이 아니라 회수 포지션 청산 리포트입니다" in summary
    assert "threshold 근접 진입 여부 확인 필요" not in summary
    assert "Entry evidence was 기록되지 않음" not in summary
    assert "모니터 신호명은 고정 손절 기준이었지만 Truth Surface 기준 실현 결과는 이익입니다" in summary
    assert summary_input["trade"]["recovered_partial_exit"] is True
    assert summary_input["trade"]["entry_assessment_scope"] == "excluded_recovered_partial"
    assert summary_input["decision_flow"]["scanner_rank"] is None
    assert summary_input["decision_flow"]["scanner_rank_basis"] == "recovered_partial_no_entry_evidence"
    assert summary_input["decision_flow"]["selection_basis"] == "보유/회수 포지션 청산"
    assert summary_input["decision_flow"]["entry_reason"].startswith("당일 진입 증거가 부족해")
    assert summary_input["decision_flow"]["exit_reason"] == "고정 손절 기준"
    assert "실현 결과는 이익" in summary_input["decision_flow"]["exit_result_note"]


def test_trade_summary_marks_weekend_carryover_exit_with_date_basis() -> None:
    report = {
        "trade_id": "TRD_20260511_005930_01",
        "symbol": "005930",
        "status": "partial",
        "story_type": "simulation",
        "execution_mode_label": "simulation (mock broker)",
        "action": "SELL",
        "shared_facts": {
            "symbol": "005930",
            "status": "partial",
            "action": "SELL",
            "broker_buy_price": 264500,
            "broker_fill_price": 287750,
            "broker_fee": 3860,
            "broker_tax": 1150,
            "pnl": 41490,
            "pnl_pct": 0.0784,
            "pnl_truth_source": "kiwoom.ka10077",
            "exit_reason": "partial_take_profit",
            "commander_route": {
                "applied_policy": {
                    "horizon": {
                        "runtime_context": {
                            "carry_state": "multi_session_stale",
                            "carry_risk_bias": "urgent_exit_review",
                        }
                    }
                }
            },
        },
        "truth_surface": {
            "price": {"broker_buy_price": 264500, "broker_fill_price": 287750},
            "pnl": {
                "value": 41490,
                "pnl_pct": 0.0784,
                "broker_fee": 3860,
                "broker_tax": 1150,
                "pnl_truth_source": "kiwoom.ka10077",
            },
        },
        "fact_payload": {
            "trade": {
                "exit_summary": {"ts": "2026-05-11T00:49:27+00:00"},
                "exit_vs_strategy_intent": {"actual_hold_sec": 249265},
            }
        },
        "market_context_at_entry": {
            "summary": "중립 regime에서 강세 sentiment 우세",
            "playbook": "pullback",
            "risk_mode": "balanced",
            "market_sentiment": "bullish",
            "korea_indices": {
                "indices": {
                    "KOSPI": {"current": 7876.6, "previous_close": 7498.0, "change_pct": 0.0505}
                }
            },
        },
        "why_this_symbol_was_chosen": {
            "symbol": "005930",
            "selected_rank": 1,
            "score_total": 1.354,
            "basis": "sector theme alignment",
        },
        "entry_execution_visibility": {
            "monitor_entry_candidate_cascade": {
                "top_pick_symbol": "078890",
                "final_selected_symbol": "078890",
                "ranked_candidates": [
                    {"rank": 1, "symbol": "078890"},
                    {"rank": 2, "symbol": "000660"},
                ],
            }
        },
        "entry_decision": {
            "summary": "Entry evidence was not captured for this day. Position context was inferred from downstream monitor/exit artifacts.",
            "bullets": [
                "진입 사유는 Entry evidence was not captured for this day. Position context was inferred from downstream monitor/exit artifacts.",
            ],
        },
        "holding_monitoring_story": {
            "summary": "SELL was triggered because partial_take_profit.",
            "bullets": ["Trigger type: partial_take_profit"],
        },
        "exit_decision": {
            "summary": "partial_take_profit 기준으로 청산됐습니다.",
            "bullets": ["청산을 직접 촉발한 신호는 partial_take_profit입니다."],
        },
        "reporter_evaluation": {"summary": "", "bullets": []},
        "final_operator_conclusion": {
            "summary": "005930 2주 매도 주문이 시뮬레이션으로 승인 및 기록됐습니다.",
            "current_action": "SELL",
        },
    }

    summary = mod.render_trade_summary_markdown(report)
    summary_input = mod.build_trade_summary_input(report)

    assert "포지션 성격: 전일/주말 이월 보유" in summary
    assert "보유 시작 2026-05-08 12:35 KST / 청산 2026-05-11 09:49 KST" in summary
    assert "선정 경로: 오버나이트/주말 이월 포지션 청산" in summary
    assert "주말 이월: 금요일 보유분이 월요일 청산까지 이어진 거래입니다" in summary
    assert "신규 진입 판단이 아니라 이월 포지션 청산 리포트입니다" in summary
    assert "최종 후보: 078890" not in summary
    assert "스캐너 순위: 1위" not in summary
    assert summary_input["trade"]["carryover_exit"] is True
    assert summary_input["trade"]["entry_assessment_scope"] == "excluded_carryover_exit"
    assert summary_input["decision_flow"]["scanner_rank"] is None
    assert summary_input["decision_flow"]["scanner_rank_basis"] == "carryover_exit_no_same_day_entry"
    assert summary_input["decision_flow"]["carryover_context"]["weekend_carry"] is True
    assert summary_input["decision_flow"]["selection_basis"] == "오버나이트/주말 이월 포지션 청산"


def test_render_trade_summary_markdown_filters_symbol_news_to_trade_symbol() -> None:
    report = {
        "trade_id": "TRD_20260429_098460_01",
        "symbol": "098460",
        "status": "closed",
        "story_type": "live trade report",
        "execution_mode_label": "real broker",
        "action": "SELL",
        "shared_facts": {
            "symbol": "098460",
            "status": "closed",
            "action": "SELL",
            "broker_buy_price": 10000,
            "broker_fill_price": 10100,
            "pnl": 1000,
            "pnl_pct": 0.01,
        },
        "market_context_at_entry": {
            "summary": "시장 요약",
            "playbook": "defensive",
            "risk_mode": "balanced",
            "themes": ["반도체_시스템반도체", "휴대폰_RF부품"],
            "preferred_themes": ["반도체_시스템반도체", "휴대폰_RF부품"],
            "theme_source": "kiwoom_live",
            "theme_source_status": "ok",
            "market_news_titles": ["코스피: 시장 뉴스"],
            "candidate_news_titles": [
                "006340: 대우건설 투자경고 공시",
                "098460: 고영 어닝서프라이즈 전망",
            ],
        },
        "why_this_symbol_was_chosen": {
            "symbol": "098460",
            "selected_rank": 1,
            "score_total": 1.234,
            "basis": "거래대금, 감성 지원",
        },
        "entry_decision": {"summary": "진입", "bullets": []},
        "exit_decision": {"summary": "청산", "bullets": []},
        "final_operator_conclusion": {"summary": "최종", "current_action": "SELL"},
    }

    summary = mod.render_trade_summary_markdown(report)
    symbol_news_section = summary.split("### 종목 뉴스 (098460)", 1)[1].split("## ", 1)[0]
    summary_input = mod.build_trade_summary_input(report)

    assert "098460: 고영 어닝서프라이즈 전망" in symbol_news_section
    assert "006340:" not in symbol_news_section
    assert summary_input["market_and_strategy"]["symbol_news_titles"] == ["098460: 고영 어닝서프라이즈 전망"]
    assert "* 핵심 테마: 반도체_시스템반도체, 휴대폰_RF부품" in summary
    assert "* 테마 출처: kiwoom_live / ok" in summary
    assert summary_input["market_and_strategy"]["themes"] == ["반도체_시스템반도체", "휴대폰_RF부품"]
    assert summary_input["market_and_strategy"]["theme_source"] == "kiwoom_live"


def test_render_trade_summary_markdown_explains_missing_news_sample_location() -> None:
    report = {
        "trade_id": "TRD_20260430_005930_01",
        "symbol": "005930",
        "status": "closed",
        "story_type": "live trade report",
        "execution_mode_label": "real broker",
        "action": "SELL",
        "market_context_at_entry": {
            "summary": "시장 요약",
            "playbook": "defensive",
            "risk_mode": "balanced",
            "market_news_titles": [],
            "candidate_news_titles": [],
        },
        "why_this_symbol_was_chosen": {
            "symbol": "005930",
            "selected_rank": 1,
            "score_total": 1.0,
        },
        "entry_decision": {"summary": "진입", "bullets": []},
        "exit_decision": {"summary": "청산", "bullets": []},
        "final_operator_conclusion": {"summary": "최종", "current_action": "SELL"},
    }

    summary = mod.render_trade_summary_markdown(report)
    news_section = summary.split("## 📰 뉴스 및 컨텍스트", 1)[1].split("---", 1)[0]

    assert "상세 리포트에서 확인 필요" not in news_section
    assert "ai_trade_report_input.json" in news_section
    assert "market_context_at_entry.market_news_titles" in news_section
    assert "market_context_at_entry.candidate_news_titles" in news_section
    assert "005930 항목" in news_section


def test_trade_summary_corrects_closed_sell_final_operator_summary_prefix() -> None:
    report = {
        "trade_id": "TRD_20260504_018880_01",
        "symbol": "018880",
        "status": "closed",
        "story_type": "live trade report",
        "execution_mode_label": "real broker",
        "action": "SELL",
        "shared_facts": {
            "symbol": "018880",
            "status": "closed",
            "action": "SELL",
            "broker_buy_price": 4810,
            "broker_fill_price": 4870,
            "pnl": 173,
            "pnl_pct": 0.0036,
        },
        "entry_decision": {"summary": "진입", "bullets": []},
        "exit_decision": {"summary": "청산", "bullets": []},
        "final_operator_conclusion": {
            "summary": "현재 판단은 진입 유지입니다. 018880 10주 매도 주문은 실거래로 체결됐습니다.",
            "current_action": "SELL",
        },
    }

    summary = mod.render_trade_summary_markdown(report)
    summary_input = mod.build_trade_summary_input(report)

    assert "현재 판단은 청산 완료입니다." in summary
    assert "현재 판단은 진입 유지입니다." not in summary
    assert summary_input["decision_flow"]["final_operator_summary"].startswith("현재 판단은 청산 완료입니다.")


def test_trade_summary_does_not_surface_stale_post_entry_gate_as_confirmed_entry_gate() -> None:
    report = {
        "trade_id": "TRD_20260504_018880_01",
        "symbol": "018880",
        "status": "closed",
        "story_type": "live trade report",
        "execution_mode_label": "real broker",
        "action": "SELL",
        "shared_facts": {
            "symbol": "018880",
            "status": "closed",
            "action": "SELL",
            "broker_buy_price": 4810,
            "broker_fill_price": 4870,
            "pnl": 173,
            "pnl_pct": 0.0036,
        },
        "entry_decision": {
            "summary": "진입",
            "bullets": [
                "진입 게이트 상태는 VWAP 재회복 통과, 과확장 점검 통과, 신뢰도 게이트 미통과였습니다.",
            ],
        },
        "exit_decision": {"summary": "청산", "bullets": []},
        "final_operator_conclusion": {"summary": "현재 판단은 진입 유지이다. 매도 주문 완료.", "current_action": "SELL"},
    }

    summary = mod.render_trade_summary_markdown(report)
    summary_input = mod.build_trade_summary_input(report)
    entry_section = summary.split("## 🚪 진입 판단", 1)[1].split("---", 1)[0]

    assert "신뢰도 게이트 미통과" not in entry_section
    assert "사후 모니터 재평가와 혼재" in entry_section
    assert "청산 완료입니다." in summary_input["decision_flow"]["final_operator_summary"]


def test_trade_summary_prefers_entry_run_monitor_visibility_over_exit_snapshot(tmp_path: Path) -> None:
    run_id = "entry-run-1"
    report_dir = tmp_path / "trades" / "2026-05-20" / "0900" / "TRD_20260520_000660_01" / "reports"
    canonical_dir = tmp_path / "canonical" / "2026-05-20" / run_id
    report_dir.mkdir(parents=True)
    canonical_dir.mkdir(parents=True)
    (canonical_dir / "monitor.json").write_text(
        json.dumps(
            {
                "entry_reason": "breakout_above_recent_high_with_vwap_structure_confirmation",
                "entry_triggered": True,
                "entry_candidate_cascade": {
                    "attempted": False,
                    "top_pick_triggered": True,
                    "blocked_reason": "",
                },
                "monitor_focus_context": {
                    "entry_decision": "BUY",
                    "entry_triggered": True,
                    "entry_guard_blocked": False,
                    "entry_guard_reason": "",
                    "entry_cost_adjusted_edge_ok": True,
                },
                "entry_grouped_logic_trace": {
                    "human_chart_entry_score": 0.73,
                    "human_chart_setup_quality": "B",
                },
                "policy_ref": {
                    "entry_control": {
                        "max_priority_rank": 3,
                        "max_runner_ups": 2,
                        "cascade_enabled": True,
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report_path = report_dir / "ai_trade_report.json"
    report = {
        "trade_id": "TRD_20260520_000660_01",
        "run_id": run_id,
        "symbol": "000660",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation",
        "action": "SELL",
        "paths": {"ai_trade_report_json": str(report_path)},
        "shared_facts": {
            "symbol": "000660",
            "status": "closed",
            "action": "SELL",
            "broker_buy_price": 1731000,
            "broker_fill_price": 1716000,
            "pnl": -30482,
            "pnl_pct": -0.0176,
        },
        "fact_payload": {"trade": {"entry_summary": {"run_id": run_id}}},
        "entry_execution_visibility": {
            "monitor_focus_context": {
                "entry_decision": "WAIT",
                "entry_triggered": False,
                "entry_guard_blocked": True,
                "entry_guard_reason": "same_symbol_position_open",
                "entry_cost_adjusted_edge_ok": False,
            },
            "entry_grouped_logic_trace": {
                "human_chart_entry_score": 0.05,
                "human_chart_setup_quality": "C",
            },
        },
        "monitor_snapshot": {
            "entry_candidate_cascade": {
                "blocked_reason": "hard_entry_blocker_no_cascade",
                "top_pick_guard_blocked": True,
            },
            "monitor_focus_context": {
                "entry_guard_blocked": True,
                "entry_guard_reason": "same_symbol_position_open",
            },
        },
        "entry_decision": {"summary": "entry", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "truth_surface": {
            "status": {"status": "closed"},
            "price": {"broker_buy_price": 1731000, "broker_fill_price": 1716000},
            "pnl": {"value": -30482, "pct": -0.0176},
            "availability": {},
        },
    }

    summary_input = mod.build_trade_summary_input(report)
    visibility = summary_input["decision_flow"]["entry_execution_visibility"]

    assert visibility["monitor_focus_context"]["entry_guard_blocked"] is False
    assert visibility["monitor_focus_context"]["entry_cost_adjusted_edge_ok"] is True
    assert visibility["entry_grouped_logic_trace"]["human_chart_entry_score"] == 0.73
    assert visibility["monitor_entry_candidate_cascade"]["top_pick_triggered"] is True


def test_render_trade_report_markdown_translates_fixed_english_report_phrases() -> None:
    report = {
        "trade_id": "TRD_20260323_000660_01",
        "action": "BUY",
        "symbol": "000660",
        "status": "open",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "以묐┰ Regime, bearish Market Sentiment, pullback playbook ?곸슜."},
        "market_context_at_entry": {
            "summary": "以묐┰ Regime, bearish Market Sentiment, pullback playbook ?곸슜.",
            "bullets": [
                "Stress Flags: elevated_vix, yield_rise",
                "News input: 75 headlines were considered across 10 targets (10 market / 5 candidate signals).",
            ],
        },
        "why_this_symbol_was_chosen": {
            "summary": "selection",
            "bullets": [
                "Scanner Rank: 1??/ Total Score: 0.661",
                "Final decision basis: Scanner selected the highest-ranked candidate after strategist-guided weighting, source scoring, and risk penalties.",
                "Tie Break Rule: score_total desc -> confidence desc -> risk_score asc",
                "Entry reason: Scanner selected 000660 as rank #1 out of 5 candidates with score 0.661 because it led on trading value, theme and sector alignment.",
            ],
        },
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "hold", "bullets": ["Watch axes: Trailing stop, VWAP breakdown"]},
        "exit_decision": {"summary": "open trade", "bullets": []},
        "scanner_filters": {"summary": "filters", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "none", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "hold", "current_action": "HOLD", "watch_next": [], "thesis_invalidation": []},
    }

    markdown = mod.render_trade_report_markdown(report)

    for forbidden in [
        "Trailing stop",
        "Scanner selected",
        "headlines were considered",
        "Market Sentiment",
        "Stress Flags",
        "Scanner Rank",
        "Tie Break Rule",
    ]:
        assert forbidden not in markdown
    assert "시장 심리" in markdown
    assert "스트레스 신호" in markdown
    assert "스캐너 순위" in markdown
    assert "동률 해소 기준" in markdown


def test_render_trade_report_markdown_renders_provenance_metadata_with_korean_labels() -> None:
    report = {
        "trade_id": "TRD_20260323_005930_01",
        "action": "SELL",
        "symbol": "005930",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generated_at": "2026-03-23T09:12:30+09:00",
        "generation": {
            "status": "ok",
            "mode": "ai",
            "model": "openrouter/free",
            "reason": "not available",
        },
        "executive_summary": {"summary": "留ㅻℓ 寃곌낵瑜??뺣━?덉뒿?덈떎."},
        "market_context_at_entry": {
            "summary": "?쒖옣 ?곹솴???뺣━?덉뒿?덈떎.",
            "bullets": ["global_sentiment score=-0.258 status=ok source=yfinance"],
        },
        "why_this_symbol_was_chosen": {"summary": "?좎젙 ?댁쑀瑜??뺣━?덉뒿?덈떎.", "bullets": []},
        "entry_decision": {"summary": "吏꾩엯 洹쇨굅瑜??뺣━?덉뒿?덈떎.", "bullets": []},
        "holding_monitoring_story": {"summary": "蹂댁쑀 寃쎄낵瑜??뺣━?덉뒿?덈떎.", "bullets": []},
        "exit_decision": {"summary": "泥?궛 洹쇨굅瑜??뺣━?덉뒿?덈떎.", "bullets": []},
        "scanner_filters": {"summary": "?꾪꽣 ?먭? 寃곌낵瑜??뺣━?덉뒿?덈떎.", "bullets": []},
        "guard_approval_result": {"summary": "?뱀씤 寃곌낵瑜??뺣━?덉뒿?덈떎.", "bullets": []},
        "execution_quality": {"summary": "?ㅽ뻾 寃곌낵瑜??뺣━?덉뒿?덈떎.", "bullets": []},
        "reporter_evaluation": {"summary": "?됯? 寃곌낵瑜??뺣━?덉뒿?덈떎.", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "蹂댁셿 ?ъ씤?몃? ?뺣━?덉뒿?덈떎.", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "理쒖쥌 ?먮떒???뺣━?덉뒿?덈떎.", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        "section_provenance": {
            "market_context_at_entry": {
                "source": "canonical",
                "confidence": "high",
                "artifact_path": "reports/canonical/2026-03-23/run-1/strategist.json",
            },
            "why_this_symbol_was_chosen": {
                "source": "direct_artifact",
                "confidence": "medium",
                "artifact_path": "reports/trades/2026-03-23/TRD_20260323_005930_01/evidence/scanner_evidence.json",
            },
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "데이터 출처:" in markdown
    assert "참조 경로:" in markdown
    assert "생성 상태:" in markdown
    assert "생성 시각:" in markdown
    assert "source=" not in markdown
    assert "path=" not in markdown
    assert "generated_at=" not in markdown
    assert "status=" not in markdown
    assert "reports/canonical/2026-03-23/run-1/strategist.json" in markdown
    assert "데이터 출처: yfinance" in markdown
    assert "상태: ok" in markdown
    assert "확인되지 않음" in markdown
    assert report["section_provenance"]["market_context_at_entry"]["artifact_path"] == "reports/canonical/2026-03-23/run-1/strategist.json"


def test_report_section_provenance_prefers_section_seed_entries_over_legacy_human_keys() -> None:
    result = mod._report_section_provenance(
        {
            "section_provenance": {
                "market_context_human": {
                    "source": "direct_artifact",
                    "confidence": "medium",
                    "artifact_path": "reports/trades/day/trade/evidence/strategist_evidence.json",
                },
                "report_section_provenance_seeds": {
                    "market_context_at_entry": {
                        "source": "canonical",
                        "confidence": "high",
                        "artifact_path": "reports/canonical/day/run/strategist.json",
                    },
                    "scanner_filters": {
                        "source": "canonical",
                        "confidence": "high",
                        "artifact_path": "reports/canonical/day/run/scanner.json",
                    },
                },
            }
        }
    )

    assert result["market_context_at_entry"]["source"] == "canonical"
    assert result["market_context_at_entry"]["artifact_path"] == "reports/canonical/day/run/strategist.json"
    assert result["scanner_filters"]["source"] == "canonical"
    assert result["scanner_filters"]["artifact_path"] == "reports/canonical/day/run/scanner.json"


def test_render_trade_report_markdown_monitor_snapshot_uses_active_thresholds_and_trigger() -> None:
    report = {
        "trade_id": "TRD_20260320_005930_99",
        "action": "SELL",
        "symbol": "005930",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {
            "summary": "holding",
            "bullets": [
                "Watch axes: hard_stop, take_profit",
                "placeholder-holding-text",
            ],
        },
        "exit_decision": {
            "summary": "exit",
            "bullets": [
                "Effective stop: 3.00%",
                "Take profit: 3.42%",
                "placeholder-exit-text",
            ],
        },
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        "shared_facts": {"pnl": "unavailable", "pnl_pct": 0.0},
        "monitor_snapshot": {
            "posture": "SELL",
            "trigger_type": "peak_drawdown",
            "hard_stop_pct": 0.03,
            "strategist_baseline_stop_loss_pct": 0.0191,
            "adaptive_stop_loss_pct": None,
            "effective_stop_loss_pct": 0.03,
            "effective_stop_reason": "hard_stop",
            "take_profit_pct": 0.0342,
            "strategist_baseline_take_profit_pct": 0.0359,
            "trailing_stop_pct": 0.04,
            "strategist_baseline_trailing_stop_pct": 0.0173,
            "current_price": 1162000.0,
            "average_price": 1160000.0,
            "peak_price": 1162000.0,
            "current_drawdown": 0.0,
            "peak_drawdown": -0.0116,
            "active_exit_axis": "Peak Drawdown",
            "watch_axes": ["Hard stop", "Adaptive stop", "Take profit", "Trailing stop", "Peak drawdown"],
            "price_source": "market.quote.price",
            "feature_source": "selected.features",
            "exit_triggered": True,
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "## 모니터 스냅샷" in markdown
    assert "3.00%" in markdown
    assert "3.42%" in markdown
    assert "실제 청산 트리거는" in markdown
    assert "별도 조건 축" in markdown
    assert "baseline" not in markdown
    assert "Watch axes:" not in markdown
    assert "Effective stop:" not in markdown
    assert "Take profit:" not in markdown


def test_render_trade_report_markdown_surfaces_price_truth_fields() -> None:
    report = {
        "trade_id": "TRD_20260320_005930_100",
        "action": "SELL",
        "symbol": "005930",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        "shared_facts": {
            "pnl": -320.0,
            "pnl_pct": -0.0064,
            "broker_buy_price": 69900.0,
            "broker_fill_price": 70100.0,
            "account_mark_price": 70080.0,
            "monitor_mark_price": 70050.0,
            "price_truth_source": "broker_fill",
            "pnl_truth_source": "kiwoom.ka10077",
            "broker_day_truth_source": "kiwoom.ka10077",
            "broker_day_match_mode": "symbol_price_qty",
            "broker_day_authoritative": True,
        },
        "monitor_snapshot": {
            "posture": "SELL",
            "trigger_type": "eod_flat",
            "current_price": 70050.0,
            "average_price": 69900.0,
            "exit_triggered": True,
            "price_source": "state.minute_ohlcv_by_symbol.close",
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "## Truth Surface" in markdown
    assert "브로커 매수가/매도가는 69900.00 / 70100.00입니다." in markdown
    assert "계좌 기준 마크 가격은 70080.00입니다." in markdown
    assert "모니터 관측 가격은 70050.00입니다." not in markdown
    assert "가격 기준은 브로커 체결가 기준입니다." in markdown
    assert "손익 기준은 키움 당일 실현손익 기준(ka10077)입니다." in markdown
    assert "브로커 당일 손익은 확정 기준으로 연결됐고, 소스는 키움 당일 실현손익 기준(ka10077)입니다." in markdown
    assert "브로커 당일 손익 매칭 방식은 symbol_price_qty입니다." in markdown
    assert "모니터 가격 소스는 분봉 종가입니다." in markdown
    assert "가용성 요약: 브로커 체결가는 확보됐습니다, 계좌 마크는 확인됐습니다, 모니터 가격은 남아 있습니다, 브로커 손익도 확인됐습니다." in markdown


def test_build_execution_quality_section_surfaces_broker_truth_fields() -> None:
    section = mod._build_execution_quality_section(
        {
            "symbol": "005930",
            "action": "SELL",
            "execution_mode_label": "real broker",
            "execution_details": {
                "filled_qty": 2,
                "filled_price": 70100.0,
                "avg_price": 70100.0,
                "order_status": "recorded",
                "order_id": "OID-1",
                "execution_mode": "real",
                "broker_env": "real",
                "broker_truth_source": "kiwoom.order_status",
                "broker_realized_pnl": -320.0,
                "broker_realized_pnl_pct": -0.0064,
                "broker_fee": 14,
                "broker_tax": 9,
                "pnl_truth_source": "kiwoom.ka10077",
            },
        },
        {"outcome": "recorded", "quantity": 2},
        {},
    )

    bullets = section.get("bullets") or []
    assert "브로커 체결 기준 가격은 70100.00였습니다." in bullets
    assert "브로커 실현 손익은 -320.0 / -0.64% 기준으로 정리했습니다." in bullets
    assert "브로커 수수료/세금은 14 / 9였습니다." in bullets
    assert "체결 truth 소스는 kiwoom.order_status였습니다." in bullets
    assert "손익 truth 소스는 키움 당일 실현손익 기준(ka10077)으로 확인했습니다." in bullets


def test_execution_quality_does_not_treat_position_avg_as_exit_fill() -> None:
    section = mod._build_execution_quality_section(
        {
            "symbol": "178320",
            "action": "SELL",
            "execution_mode_label": "simulation (mock broker)",
            "execution_details": {
                "filled_qty": 1,
                "filled_price": None,
                "avg_price": 56800.0,
                "order_status": "recorded",
                "order_id": "OID-EXIT",
                "execution_mode": "real",
                "broker_env": "mock",
                "broker_truth_source": None,
            },
        },
        {"outcome": "recorded", "quantity": 1},
        {},
    )

    text = " ".join([section.get("summary") or "", *list(section.get("bullets") or [])])
    assert "체결 기준 가격은 56800.00였습니다." not in text
    assert "브로커 체결가는 직접 확보되지 않았습니다." in text


def test_truth_surface_hides_fallback_pct_from_realized_pnl_when_truth_unavailable() -> None:
    truth = build_trade_report_truth_surface(
        {
            "pnl": "unavailable",
            "pnl_pct": -0.0035,
            "pnl_truth_source": "unavailable",
            "broker_fill_price": None,
            "broker_buy_price": 56800.0,
            "monitor_mark_price": 56700.0,
            "price_truth_source": "monitor_mark",
            "data_source": {"pnl_pct": "fallback"},
        }
    )

    assert truth["pnl"]["pct"] is None
    assert truth["pnl"]["pct_display"] == (56700.0 - 56800.0) / 56800.0
    assert truth["pnl"]["pct_display_role"] == "fallback_mark_only"
    assert truth["availability"]["broker_pnl_present"] is False


def test_truth_surface_treats_ambiguous_broker_day_pct_as_observation_only() -> None:
    truth = build_trade_report_truth_surface(
        {
            "pnl": "unavailable",
            "pnl_pct": -0.027707808564231717,
            "pnl_truth_source": "kiwoom.ka10077",
            "broker_day_truth_source": "kiwoom.ka10077",
            "broker_day_match_mode": "ambiguous_symbol_rows",
            "broker_day_authoritative": False,
            "broker_day_row_count": 2,
            "broker_fill_price": None,
            "broker_buy_price": 17800.0,
            "monitor_mark_price": 17370.0,
            "price_truth_source": "monitor_mark",
            "data_source": {"pnl_pct": "fallback"},
        }
    )

    assert truth["pnl"]["pct"] is None
    assert truth["pnl"]["pct_display"] == (17370.0 - 17800.0) / 17800.0
    assert truth["pnl"]["pct_display_role"] == "fallback_mark_only"
    assert truth["pnl"]["broker_day_authoritative"] is False
    assert truth["availability"]["broker_pnl_present"] is False


def test_trade_summary_labels_observed_negative_pct_as_loss_not_breakeven() -> None:
    shared_facts = {
        "symbol": "199820",
        "trade_id": "TRD_20260430_199820_02",
        "action": "SELL",
        "status": "closed",
        "exit_reason": "hard_stop",
        "pnl": "unavailable",
        "pnl_pct": -0.027707808564231717,
        "pnl_truth_source": "kiwoom.ka10077",
        "broker_day_truth_source": "kiwoom.ka10077",
        "broker_day_match_mode": "ambiguous_symbol_rows",
        "broker_day_authoritative": False,
        "broker_day_row_count": 2,
        "broker_fill_price": None,
        "broker_buy_price": 17800.0,
        "monitor_mark_price": 17370.0,
        "price_truth_source": "monitor_mark",
        "qty": 1,
        "data_source": {"pnl": "unavailable", "pnl_pct": "fallback"},
    }
    report = {
        "trade_id": "TRD_20260430_199820_02",
        "symbol": "199820",
        "status": "closed",
        "story_type": "simulation",
        "execution_mode_label": "simulation (mock broker)",
        "action": "SELL",
        "shared_facts": shared_facts,
        "truth_surface": build_trade_report_truth_surface(shared_facts),
        "entry_decision": {"summary": "entry"},
        "exit_decision": {"summary": "hard stop"},
        "holding_monitoring_story": {"bullets": ["목표 수익 실현 기준은 1.42%였습니다."]},
        "final_operator_conclusion": {"current_action": "SELL"},
    }

    summary_input = mod.build_trade_summary_input(report)
    markdown = mod.render_trade_summary_markdown(report)

    assert summary_input["truth_surface"]["result_label"] == "loss"
    assert summary_input["truth_surface"]["pnl"] == "unavailable"
    assert summary_input["truth_surface"]["pnl_pct"] == (17370.0 - 17800.0) / 17800.0
    assert summary_input["truth_surface"]["truth_source"] == "모니터 관측값 기준"
    cost = summary_input["truth_surface"]["cost_analysis"]
    assert cost["observed_pnl_pct"] == (17370.0 - 17800.0) / 17800.0
    assert "broker_reported_pnl_pct" not in cost
    assert "total_cost" not in cost
    assert "* 결과: **손실 관측 (-2.42%)**" in markdown
    assert "* 실현 손익: **확인 불가**" in markdown
    assert "* 매수가 / 매도가: 17,800 / - (체결가 미확정, 모니터 기준 17,370)" in markdown
    assert "* 청산가: - (체결가 미확정, 모니터 기준 17,370)" in markdown
    assert "매도 체결가 미확정" in markdown
    assert "실현 손익: **- (-2.77%)**" not in markdown
    assert "* 청산은 고정 손절 기준으로 실행됨" in markdown
    assert "청산은 목표 수익 실현 기준으로 실행됨" not in markdown
    assert "키움 제공 손익률" not in markdown
    assert "비용 드래그: 0" not in markdown


def test_resolve_trade_facts_uses_mark_return_not_peak_drawdown_for_fallback() -> None:
    facts = mod._resolve_trade_facts_with_precedence(
        {
            "status": "closed",
            "exit_summary": {
                "action": "SELL",
                "reason_human": "SELL was triggered because peak_drawdown.",
            },
            "monitor_reason_human": {
                "current_price": 52900.0,
                "average_price": 53000.0,
                "current_drawdown": -0.01855287569573283,
                "peak_drawdown": -0.01855287569573283,
            },
            "canonical_agent_artifacts": {
                "monitor": {
                    "position_snapshot": {
                        "current_price": 52900.0,
                        "avg_price": 53000.0,
                        "peak_price": 53900.0,
                    }
                }
            },
        }
    )

    assert facts["pnl_pct"] == (52900.0 - 53000.0) / 53000.0
    assert facts["data_source"]["pnl_pct"] == "fallback"


def test_truth_surface_ignores_zero_mark_price_for_fallback_pct() -> None:
    truth = build_trade_report_truth_surface(
        {
            "symbol": "115160",
            "status": "closed",
            "pnl": "unavailable",
            "pnl_pct": -1.0,
            "pnl_truth_source": "unavailable",
            "broker_buy_price": 6906.0,
            "broker_fill_price": 0.0,
            "account_mark_price": 0.0,
            "monitor_mark_price": 0.0,
            "data_source": {"pnl_pct": "fallback"},
        }
    )

    assert truth["pnl"]["pct"] is None
    assert truth["pnl"]["pct_display"] is None
    assert truth["pnl"]["pct_display_role"] == "fallback_mark_only"


def test_truth_surface_ignores_zero_fill_snapshot_estimate_for_fallback_pct() -> None:
    truth = build_trade_report_truth_surface(
        {
            "symbol": "115160",
            "status": "closed",
            "pnl": "unavailable",
            "pnl_pct": -1.0,
            "pnl_truth_source": "broker_fill_account_snapshot_estimate",
            "broker_buy_price": 6906.0,
            "broker_fill_price": 0.0,
            "account_mark_price": None,
            "monitor_mark_price": 6900.0,
            "data_source": {"pnl_pct": "broker_fill_account_snapshot_estimate"},
        }
    )

    assert truth["price"]["broker_fill_price"] is None
    assert truth["availability"]["broker_fill_present"] is False
    assert truth["pnl"]["pct"] is None
    assert abs(float(truth["pnl"]["pct_display"]) - ((6900.0 - 6906.0) / 6906.0)) < 1e-9
    assert truth["pnl"]["pct_display_role"] == "fallback_mark_only"


def test_shared_summary_seed_ignores_read_model_default_zero_pnl(tmp_path) -> None:
    trade_dir = tmp_path / "TRD_20260430_199820_02"
    report_dir = trade_dir / "reports"
    report_dir.mkdir(parents=True)
    input_path = trade_dir / "ai_trade_report_input.json"
    input_path.write_text("{}", encoding="utf-8")
    (trade_dir / "lifecycle_bundle.json").write_text(
        json.dumps(
            {
                "trade_id": "TRD_20260430_199820_02",
                "symbol": "199820",
                "lifecycle": {
                    "exit": {"reason_human": "SELL was triggered because hard_stop."},
                    "status": "closed",
                },
            }
        ),
        encoding="utf-8",
    )
    (report_dir / "ai_trade_report.json").write_text(
        json.dumps(
            {
                "trade_id": "TRD_20260430_199820_02",
                "symbol": "199820",
                "status": "closed",
                "shared_facts": {
                    "pnl": "unavailable",
                    "pnl_pct": -0.027707808564231717,
                },
            }
        ),
        encoding="utf-8",
    )
    story_input = {
        "trade_id": "TRD_20260430_199820_02",
        "symbol": "199820",
        "status": "closed",
        "artifacts": {"ai_trade_report_input_json": str(input_path)},
        "monitor_reason_human": {"current_drawdown": -0.027707808564231717},
    }

    seed = mod._build_shared_summary_seed(story_input)
    facts = seed["resolved_trade_facts"]

    assert seed["pnl"] == "unavailable"
    assert seed["pnl_pct"] == -0.027707808564231717
    assert facts["data_source"]["pnl"] == "unavailable"
    assert facts["data_source"]["pnl_pct"] == "trade_read_model"


def test_render_trade_report_markdown_surfaces_execution_truth_fields() -> None:
    report = {
        "trade_id": "TRD_20260320_005930_101",
        "action": "SELL",
        "symbol": "005930",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        "shared_facts": {
            "pnl": -320.0,
            "pnl_pct": -0.0064,
            "broker_fee": 14,
            "broker_tax": 9,
            "broker_fill_price": 70100.0,
            "price_truth_source": "broker_fill",
            "pnl_truth_source": "kiwoom.ka10077",
        },
        "monitor_snapshot": {
            "posture": "SELL",
            "trigger_type": "eod_flat",
            "current_price": 70050.0,
            "average_price": 69900.0,
            "exit_triggered": True,
            "price_source": "state.minute_ohlcv_by_symbol.close",
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "## 실행 결과" in markdown
    assert "- 브로커 체결 기준 가격은 70100.00였습니다." in markdown
    assert "- 브로커 실현 손익은 -320.0 / -0.64% 기준으로 정리했습니다." in markdown
    assert "- 브로커 수수료/세금은 14 / 9였습니다." in markdown
    assert "- 가격 truth 소스는 브로커 체결가 기준으로 확인했습니다." in markdown
    assert "- 손익 truth 소스는 키움 당일 실현손익 기준(ka10077)으로 확인했습니다." in markdown


def test_render_trade_report_markdown_clarifies_closed_trade_monitor_sections_against_truth_surface() -> None:
    report = {
        "trade_id": "TRD_20260423_003280_01",
        "action": "SELL",
        "symbol": "003280",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {
            "summary": "보유 구간은 제한적이어서 저장된 모니터 근거를 기준으로 정리했습니다.",
            "bullets": [
                "보유 시간은 0였습니다.",
                "현재 포지션 판단은 매도입니다.",
                "포지션 보유 시간은 약 540초입니다.",
                "현재가, 평균가, 고점 기준 값은 3230.00 / 3320.00 / 3435.00입니다.",
                "현재 손익 변동과 고점 대비 하락폭은 -5.97% / -입니다.",
                "가격 기준 소스는 position.current_price입니다.",
            ],
        },
        "exit_decision": {
            "summary": "고정 손절 기준으로 청산. 청산 당시 상황은 핵심 청산 축은 고정 손절 기준, 확인 조건은 0/1, 현재가는 3230.00, 평균가는 3320.00, 현재 손익 변동은 -5.97%입니다.",
            "bullets": [
                "청산 액션은 매도입니다.",
                "현재가, 평균가, 고점 기준 값은 3230.00 / 3320.00 / 3435.00입니다.",
                "현재 손익 변동과 고점 대비 하락폭은 -5.97% / -입니다.",
            ],
        },
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        "truth_surface": {
            "price": {
                "broker_buy_price": 3320.0,
                "broker_fill_price": 3235.0,
                "monitor_mark_price": 3230.0,
                "price_truth_source": "broker_fill",
                "monitor_price_source": "position.current_price",
            },
            "pnl": {
                "value": -110.0,
                "pct": -0.00033,
                "broker_fee": 20,
                "broker_tax": 5,
                "pnl_truth_source": "kiwoom.ka10077",
            },
            "availability": {
                "broker_fill_present": True,
                "broker_buy_present": True,
                "monitor_mark_present": True,
                "broker_pnl_present": True,
            },
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "청산 직전 모니터 관측 기준입니다." in markdown
    assert "청산 직전 모니터 관측가는 3230.00였고 실제 매도 체결가는 3235.00였습니다." in markdown
    assert "실제 실현손익은 -110.0 / -0.03%였습니다." in markdown
    assert "보유 시간은 0였습니다." not in markdown
    assert "청산 직전 모니터 판단은 매도입니다." in markdown
    assert "청산 직전 모니터 관측값(현재/평균/고점)은 3230.00 / 3320.00 / 3435.00입니다." in markdown
    assert "청산 직전 모니터 기준 손익 변동/고점 대비 하락폭은 -5.97% / -입니다." in markdown


def test_trade_summary_separates_broker_pct_from_notional_return_and_mock_cost_drag() -> None:
    report = {
        "trade_id": "TRD_20260429_098460_01",
        "symbol": "098460",
        "action": "SELL",
        "status": "closed",
        "story_type": "simulation",
        "execution_mode_label": "mock broker",
        "shared_facts": {
            "symbol": "098460",
            "trade_id": "TRD_20260429_098460_01",
            "action": "SELL",
            "status": "closed",
            "pnl": 562.0,
            "pnl_pct": 0.000131,
            "broker_fee": 300,
            "broker_tax": 88,
            "broker_buy_price": 43050.0,
            "broker_fill_price": 44000.0,
            "pnl_truth_source": "kiwoom.ka10077",
            "price_truth_source": "broker_fill",
        },
        "fact_payload": {
            "trade": {
                "execution_details": {
                    "filled_qty": 1,
                },
            },
        },
    }

    summary = mod.render_trade_summary_markdown(report)
    full = mod.render_trade_report_markdown(report)
    summary_input = mod.build_trade_summary_input(report)
    cost = summary_input["truth_surface"]["cost_analysis"]

    assert "* 키움 제공 손익률: 0.01%" in summary
    assert "* 거래금액 기준 순수익률: **1.31%**" in summary
    assert "* 비용 드래그: 388 (0.90%)" in summary
    assert "* 손익분기 필요 상승률: 약 0.90%" in summary
    assert "* 모의투자 비용 주의:" in summary
    assert "- 거래금액 기준 순수익률: 1.31%" in full
    assert cost["quantity"] == 1
    assert round(cost["net_return_pct_on_buy_notional"], 4) == 0.0131
    assert round(cost["cost_drag_pct"], 4) == 0.0090
    assert cost["broker_pct_display_warning"] is True
    assert cost["mock_cost_warning"] is True


def test_build_deterministic_trade_report_prefers_holding_summary_duration_over_zero_read_model(monkeypatch) -> None:
    monkeypatch.setattr(
        mod,
        "_load_trade_read_model_hint",
        lambda story_input: {"facts": {"hold_duration_sec": 0}},
    )
    story_input = {
        "trade_id": "TRD_20260429_098460_01",
        "symbol": "098460",
        "status": "closed",
        "action": "SELL",
        "holding_summary": {
            "hold_duration": "16.0m",
            "hold_duration_sec": 958,
        },
        "entry_summary": {"action": "BUY"},
        "exit_summary": {"action": "SELL", "reason_human": "take_profit"},
        "monitor_reason_human": {"posture": "SELL", "exit_reason": "take_profit"},
    }

    report = mod.build_deterministic_trade_report(story_input)

    assert report["shared_facts"]["holding_duration"] == "16.0m"
    assert report["shared_facts"]["data_source"]["holding_duration"] == "trade_artifact"
    assert "보유 시간은 16분였습니다." in report["holding_monitoring_story"]["bullets"][0]


def test_render_trade_report_markdown_partial_sell_uses_structured_fallbacks_and_suppresses_zero_candidate_claims() -> None:
    report = {
        "trade_id": "TRD_20260424_006340_01",
        "action": "SELL",
        "symbol": "006340",
        "status": "partial",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "local_debug", "model": "minimax/minimax-m2.5"},
        "market_context_at_entry": {
            "summary": "깨진요약??",
            "bullets": [],
            "regime": "not_captured",
            "market_sentiment": "not_captured",
            "playbook": "not_captured",
            "selected_playbook": "not_captured",
            "global_sentiment_score": 0.0,
            "risk_mode": "balanced",
            "preferred_themes": ["broad_market_leaders"],
            "avoid_themes": ["illiquid_microcap", "headline_only_momentum"],
            "strategist_market_context_summary": "Market regime was not_captured with a not_captured playbook. Global sentiment scored 0.00 and VIX was not_captured.",
        },
        "strategist_summary": {"summary": "깨진전략요약??", "bullets": []},
        "why_this_symbol_was_chosen": {
            "summary": "깨진선정요약??",
            "selected_rank": 0,
            "universe_size": 0,
            "basis": "combined scanner ranking score",
            "scanner_selection_trace": {
                "ranked_candidates": [],
                "selected_symbol": "",
                "selected_rank": 0,
                "selection_reason": "Scanner selected - as rank #1 out of 0 candidates with score 0.000 because it led on combined scanner ranking score.",
            },
        },
        "scanner_filters": {"summary": "", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "깨진청산요약??", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        "shared_facts": {
            "action": "SELL",
            "commander_route": {
                "applied_policy": {
                    "interpretation_policy": {
                        "entry_style": "defensive",
                        "required_checks": ["reclaim_gate_ok"],
                        "blockers": ["failed_breakout=confirmed"],
                        "notes": ["monitor_guidance:defensive_exit", "vwap_reclaim_required"],
                    }
                }
            },
        },
        "monitor_snapshot": {
            "trigger_type": "take_profit",
            "effective_stop_loss_pct": 0.03,
            "effective_stop_reason": "hard_stop",
            "current_price": 8340.0,
            "average_price": 8140.0,
            "peak_price": 8340.0,
        },
        "truth_surface": {
            "price": {"broker_fill_price": 8340.0, "price_truth_source": "broker_fill"},
            "pnl": {"value": 0.0, "pct": 0.0157, "pnl_truth_source": "broker_fill_account_snapshot_estimate"},
            "availability": {
                "broker_fill_present": True,
                "broker_buy_present": False,
                "account_mark_present": False,
                "monitor_mark_present": True,
                "broker_pnl_present": True,
            },
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "## 시장 환경 요약" in markdown
    assert "## 전략가 요약" in markdown
    assert "글로벌 감성 입력은 0.000이었고" in markdown
    assert "선호 테마는 시장 대표주 기준으로 정리됐습니다." in markdown
    assert "회피 테마는 유동성 낮은 초소형주, 헤드라인 추격형 모멘텀 기준으로 정리됐습니다." in markdown
    assert "전략가는 최종적으로 방어형 전략 프레임을 유지했습니다." in markdown
    assert "핵심 확인 조건은 VWAP 재회복 확인이었습니다." in markdown
    assert "경계 신호는 실패 돌파가 확인된 상태였습니다." in markdown
    assert "스캐너 0위" not in markdown
    assert "out of 0 candidates" not in markdown
    assert "저장된 스캐너 후보 표가 없어" in markdown
    assert "실제 청산 트리거는 목표 수익 실현 기준이었습니다." in markdown


def test_render_trade_report_markdown_uses_estimated_pnl_phrase_when_broker_fill_only() -> None:
    report = {
        "trade_id": "TRD_20260421_005380_01",
        "action": "SELL",
        "symbol": "005380",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        "shared_facts": {
            "pnl": "unavailable",
            "pnl_pct": -0.0090,
            "broker_fill_price": 537000.0,
            "monitor_mark_price": 536000.0,
            "price_truth_source": "broker_fill",
            "monitor_price_source": "position.current_price",
            "pnl_truth_source": "broker_fill_account_snapshot_estimate",
        },
        "truth_surface": {
            "price": {
                "broker_fill_price": 537000.0,
                "monitor_mark_price": 536000.0,
                "price_truth_source": "broker_fill",
                "monitor_price_source": "position.current_price",
            },
            "pnl": {
                "value": "unavailable",
                "pct": -0.0090,
                "pnl_truth_source": "broker_fill_account_snapshot_estimate",
            },
            "availability": {
                "broker_fill_present": True,
                "account_mark_present": False,
                "monitor_mark_present": True,
                "broker_pnl_present": True,
            },
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "종료 직전 모니터 관측 가격은 536000.00입니다." not in markdown
    assert "브로커 체결가와 계좌 평가손익 기준 추정 손익률은 -0.90%입니다." in markdown
    assert "손익 기준은 브로커 체결가와 계좌 평가손익 역산 기준입니다." in markdown


def test_render_trade_report_markdown_rewrites_memory_sections_with_active_layers_and_applied_deltas() -> None:
    report = {
        "trade_id": "TRD_20260423_003280_01",
        "action": "SELL",
        "symbol": "003280",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        "memory_surface": {
            "status": {
                "strategy_memory_used": True,
                "selected_symbol_memory_used": True,
                "reporter_feedback_used": True,
                "read_model_facts_used": False,
            },
            "strategy_memory": {
                "scope": "aggregated_strategy_memory",
                "status": "ok",
                "best_playbooks": ["defensive"],
                "worst_playbooks": ["defensive"],
                "recent_failures": ["playbook:defensive"],
            },
            "commander_memory_policy": {
                "active_layers": ["daily"],
                "priority_order": ["daily", "weekly", "monthly", "symbol"],
                "symbol_memory_override_enabled": False,
            },
            "memory_packets": {
                "daily": {"status": "ok", "active": True},
                "weekly": {"status": "ok", "active": False, "sample_day_count": 1},
                "monthly": {"status": "ok", "active": False, "sample_day_count": 1},
                "symbol": {"status": "ok", "active": True},
            },
            "selected_symbol_memory": {
                "present": True,
                "symbol": "003280",
                "trade_count": 4,
                "win_rate": 0.0,
                "dominant_playbook": "defensive",
                "dominant_monitor_blocker": "unknown",
            },
            "reporter_feedback_packet": {
                "present": True,
                "available": True,
                "confidence": "high",
                "source_reports": {"trade_reports": True},
                "trade_report_analysis": {"closed_trade_count": 11, "win_count": 0, "loss_count": 11, "avg_pnl_pct": -0.0014},
                "recommendation": ["Same-day closed trades are loss-heavy; keep defensive entry posture until follow-through quality improves."],
            },
            "read_model_facts": {"present": False},
            "usage_trace": {
                "playbook": "defensive",
                "monitor_guidance": "defensive_exit",
                "scanner_bias": "leader",
            },
        },
        "memory_application_surface": {
            "scanner_memory_bias": {
                "captured": True,
                "applied": False,
                "active_layers": ["daily"],
                "selected_symbol": "003280",
                "selected_bias_adjustment": 0.0,
                "reason": [
                    "daily_strategy_memory_available",
                    "daily_best:defensive",
                    "commander_risk_posture:defensive",
                ],
            },
            "monitor_memory_bias": {
                "captured": True,
                "applied": True,
                "active_layers": ["daily"],
                "applied_deltas": [
                    {"field": "breakout_buffer_pct", "from": 0.0015, "to": 0.003, "delta": 0.0015},
                    {"field": "max_extended_from_vwap_pct", "from": 0.05, "to": 0.045, "delta": -0.005},
                ],
                "hold_applied": True,
                "hold_deltas": [
                    {"field": "confirm_ticks", "from": 2, "to": 1, "delta": -1.0},
                ],
                "exit_applied": True,
                "exit_deltas": [
                    {"field": "stop_loss_pct", "from": 0.020, "to": 0.015, "delta": -0.005},
                    {"field": "peak_drawdown_exit_pct", "from": 0.015, "to": 0.010, "delta": -0.005},
                ],
                "risk_posture": "defensive",
                "effective_policy_source": "monitor_memory_bias_adjusted",
                "reason": ["commander_risk_posture:defensive", "commander_focus:exit_quality"],
            },
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "## 전략가 프롬프트에서 직접 확인된 메모리" in markdown
    assert "## 거래 설명용 사후 복원 메모리" in markdown
    assert "[포함 여부] 전략 메모리=확인, 메모리 패킷=확인, 지휘관 정책=확인, 종목 메모리=확인, 리포터 피드백=확인, 읽기 모델=미확인." in markdown
    assert "[전략 메모리] 상태=정상 기록, 우세=방어형, 취약=방어형, 최근 실패=방어형 전략 프레임 실패." in markdown
    assert "raw 값 부록: best_playbooks=defensive, worst_playbooks=defensive, recent_failures=playbook:defensive" not in markdown
    assert "[종목 메모리] 종목=003280, 과거 거래=4건, 승률=0.00%, 우세 전략=방어형." in markdown
    assert "[리포터 피드백] 사용 가능=예, 소비=아니오, 상태=정상 기록, 신뢰도=높음, 소스=당일 닫힌 거래 리포트, 요약=닫힌 거래 11건 / 승패 0/11 / 평균 손익률 -0.14%." in markdown
    assert "이 거래는 전략가 프롬프트만으로 대부분 설명돼, 사후 메모리 복원은 크지 않았습니다." in markdown
    assert "이번 거래 후보 003280에는 메모리 기반 추가 가감점이 없었습니다." in markdown
    assert "스캐너 쪽은 소스 가중치 변화 상세가 남지 않아, 후보별 가감점만 확인됩니다." in markdown
    assert "이번 거래에서는 모니터가 당일 메모리를 진입 판단에 직접 반영했습니다." in markdown
    assert "진입 정책 변화는 breakout_buffer_pct 0.002 -> 0.003 (+0.002), max_extended_from_vwap_pct 0.050 -> 0.045 (-0.005)입니다." in markdown
    assert "진입 적용 해석: 돌파 확인 버퍼를 키워 추격 진입을 더 보수적으로 막았습니다." in markdown
    assert "VWAP 기준 과확장 추격 허용 범위를 줄여 현재 가격 부담이 큰 진입을 줄였습니다." in markdown
    assert "보유 관리 변화는 confirm_ticks 2.000 -> 1.000 (-1.000)입니다." in markdown
    assert "보유 관리 해석: 경고 후 재확인 조건을 줄여, 보유 포지션을 더 빨리 정리할 수 있게 했습니다." in markdown
    assert "청산 정책 변화는 stop_loss_pct 0.020 -> 0.015 (-0.005), peak_drawdown_exit_pct 0.015 -> 0.010 (-0.005)입니다." in markdown
    assert "청산 정책 해석: 손실과 drawdown 기준을 더 타이트하게 잡아, 손상이 확인되면 더 빨리 청산하도록 조정했습니다." in markdown
    assert "모니터 조정은 지휘관 위험 자세는 방어형이었습니다, 지휘관은 청산 품질 점검을 우선했습니다." in markdown
    assert "raw tag 부록" not in markdown


def test_render_trade_report_markdown_normalizes_raw_english_exit_reason() -> None:
    report = {
        "trade_id": "TRD_20260423_047040_01",
        "action": "SELL",
        "symbol": "047040",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "strategist_summary": {"summary": "strategist", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {
            "summary": "SELL was triggered because intraday low break.",
            "bullets": ["정규화된 청산 사유는 SELL was triggered because intraday low break.입니다."],
        },
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "SELL was triggered because intraday low break" not in markdown
    assert "장중 저점 이탈 기준으로 청산" in markdown


def test_render_trade_report_markdown_explains_same_price_round_trip_as_cost_loss() -> None:
    report = {
        "trade_id": "TRD_20260421_005380_01",
        "action": "SELL",
        "symbol": "005380",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        "shared_facts": {
            "pnl": -4813.0,
            "pnl_pct": -0.0090,
            "broker_fee": 3740,
            "broker_tax": 1073,
            "broker_buy_price": 537000.0,
            "broker_fill_price": 537000.0,
            "price_truth_source": "broker_fill",
            "pnl_truth_source": "kiwoom.ka10077",
        },
        "truth_surface": {
            "price": {
                "broker_buy_price": 537000.0,
                "broker_fill_price": 537000.0,
                "monitor_mark_price": 536000.0,
                "price_truth_source": "broker_fill",
                "monitor_price_source": "position.current_price",
            },
            "pnl": {
                "value": -4813.0,
                "pct": -0.0090,
                "broker_fee": 3740,
                "broker_tax": 1073,
                "pnl_truth_source": "kiwoom.ka10077",
            },
            "availability": {
                "broker_fill_present": True,
                "broker_buy_present": True,
                "account_mark_present": False,
                "monitor_mark_present": True,
                "broker_pnl_present": True,
            },
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "<span style=" not in markdown
    assert "**[확정값]**" in markdown
    assert "브로커 매수가/매도가는 537000.00 / 537000.00입니다." in markdown
    assert "매수가와 매도가가 같았고, 손익은 가격 변동이 아니라 수수료와 세금에서 발생했습니다." in markdown
    assert "모니터 가격 소스는" not in markdown


def test_trade_summary_cost_analysis_keeps_zero_price_move_when_qty_missing() -> None:
    report = {
        "trade_id": "TRD_20260507_010170_01",
        "action": "SELL",
        "symbol": "010170",
        "status": "closed",
        "shared_facts": {
            "pnl": -13481.0,
            "pnl_pct": -0.008978354978354978,
            "broker_fee": 10480,
            "broker_tax": 3001,
            "broker_buy_price": 21450.0,
            "broker_fill_price": 21450.0,
            "price_truth_source": "broker_fill",
            "pnl_truth_source": "kiwoom.ka10077",
        },
        "truth_surface": {
            "price": {
                "broker_buy_price": 21450.0,
                "broker_fill_price": 21450.0,
                "price_truth_source": "broker_fill",
            },
            "pnl": {
                "value": -13481.0,
                "pct": -0.008978354978354978,
                "broker_fee": 10480,
                "broker_tax": 3001,
                "pnl_truth_source": "kiwoom.ka10077",
            },
        },
    }

    summary_input = mod.build_trade_summary_input(report)
    cost = summary_input["truth_surface"]["cost_analysis"]

    assert cost["price_move_pct"] == 0.0
    assert round(cost["cost_drag_pct"], 6) == round(0.008978354978354978, 6)


def test_render_trade_report_markdown_discloses_missing_buy_price_when_only_sell_fill_is_recovered() -> None:
    report = {
        "trade_id": "TRD_20260421_005930_01",
        "action": "SELL",
        "symbol": "005930",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        "truth_surface": {
            "price": {
                "broker_fill_price": 218000.0,
                "broker_buy_price": None,
                "monitor_mark_price": 218250.0,
                "price_truth_source": "broker_fill",
                "monitor_price_source": "position.current_price",
            },
            "pnl": {
                "value": -1706.0,
                "pct": -0.0078,
                "broker_fee": 1520,
                "broker_tax": 436,
                "pnl_truth_source": "kiwoom.ka10077",
                "broker_day_truth_source": "kiwoom.ka10077",
                "broker_day_match_mode": "symbol_qty_price_exact",
                "broker_day_authoritative": True,
            },
            "availability": {
                "broker_fill_present": True,
                "broker_buy_present": False,
                "account_mark_present": False,
                "monitor_mark_present": True,
                "broker_pnl_present": True,
            },
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "브로커 체결 가격은 218000.00입니다." in markdown
    assert "브로커 매수 체결가는 직접 복구되지 않았고, 확정 손익은 키움 당일 실현손익 기준으로만 확인했습니다." in markdown
    assert "모니터 가격 소스는" not in markdown


def test_render_trade_report_markdown_places_monitor_snapshot_and_scanner_comparison_in_requested_order() -> None:
    report = {
        "trade_id": "TRD_20260415_000660_01",
        "action": "SELL",
        "symbol": "000660",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        "monitor_snapshot": {
            "posture": "SELL",
            "trigger_type": "hard_stop",
            "effective_stop_loss_pct": 0.03,
            "take_profit_pct": 0.0342,
            "trailing_stop_pct": 0.02,
            "exit_triggered": True,
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    idx_why = markdown.find("## 선택된 종목 상세 분석")
    idx_scanner = markdown.find("## 스캐너 후보 비교")
    idx_entry = markdown.find("## 진입 상세 근거")
    idx_exit = markdown.find("## 청산 판단 근거")
    idx_snapshot = markdown.find("## 모니터 스냅샷")

    assert idx_why >= 0 and idx_scanner >= 0 and idx_entry >= 0
    assert idx_why < idx_scanner < idx_entry
    assert idx_exit >= 0 and idx_snapshot >= 0
    assert idx_exit < idx_snapshot


def test_render_trade_report_markdown_splits_strategist_summary_from_market_context() -> None:
    report = {
        "trade_id": "TRD_20260415_000660_01",
        "action": "SELL",
        "symbol": "000660",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {
            "summary": "context",
            "bullets": [
                "시장 상태는 중립입니다.",
                "스캐너 연결 근거는 selected 000660 under 눌림목 플레이북 because scanner reasoning입니다.",
                "전략가 핵심 입력은 global_sentiment score=0.081입니다.",
                "주요 시장 뉴스는 코스피: headline A; 코스닥: headline B입니다.",
            ],
        },
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
    }

    markdown = mod.render_trade_report_markdown(report)

    idx_market = markdown.find("## 시장 환경 요약")
    idx_strategist = markdown.find("## 전략가 요약")
    idx_why = markdown.find("## 선택된 종목 상세 분석")

    assert idx_market >= 0 and idx_strategist >= 0 and idx_why >= 0
    assert idx_market < idx_strategist < idx_why
    assert "- 스캐너 연결 근거는 selected 000660 under 눌림목 플레이북 because scanner reasoning입니다." in markdown
    assert "- 전략가 핵심 입력은 global_sentiment score=0.081입니다." in markdown
    assert "- 주요 시장 뉴스는 코스피: headline A; 코스닥: headline B입니다." in markdown
    idx_scanner_link = markdown.find("- 스캐너 연결 근거는 selected 000660 under 눌림목 플레이북 because scanner reasoning입니다.")
    idx_key_input = markdown.find("- 전략가 핵심 입력은 global_sentiment score=0.081입니다.")
    idx_market_news = markdown.find("- 주요 시장 뉴스는 코스피: headline A; 코스닥: headline B입니다.")
    assert idx_key_input >= 0 and idx_market_news >= 0 and idx_scanner_link >= 0
    assert idx_key_input < idx_scanner_link
    assert idx_market_news < idx_scanner_link


def test_render_trade_report_markdown_drops_stale_scanner_execution_mismatch_summary() -> None:
    report = {
        "trade_id": "TRD_20260427_005930_01",
        "action": "SELL",
        "symbol": "005930",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "minimax/minimax-m2.5"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "strategist_summary": {"summary": "strategist", "bullets": []},
        "why_this_symbol_was_chosen": {
            "summary": "스캐너는 042700을 최고 순위로 선택했으나, 실제 실행은 005930에서 발생함. 이는 스캐너와 실행 간의 불일치를 나타내며, 선택 근거는 042700에 대한 것임.",
            "symbol": "042700",
            "selected_rank": 1,
            "universe_size": 7,
            "basis": "거래대금, 감성 지원",
            "bullets": [
                "스캐너 선택 종목: 042700 (순위 1위, 점수 1.378)",
                "실행 종목: 005930 (스캐너 선택과 불일치)",
                "상위 후보는 #1 042700(1.378) / #2 000660(1.250) / #3 006340(0.708) 순이었습니다.",
            ],
            "scanner_selection_trace": {
                "selected_symbol": "042700",
                "selected_rank": 1,
                "ranked_candidates": [
                    {"rank": 1, "symbol": "042700", "score_total": 1.378, "risk_score": 0.479, "confidence": 0.853},
                    {"rank": 2, "symbol": "000660", "score_total": 1.250, "risk_score": 0.500, "confidence": 0.770},
                ],
            },
        },
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
    }

    markdown = mod.render_trade_report_markdown(report)

    why_section = markdown[markdown.find("## 선택된 종목 상세 분석") : markdown.find("## 스캐너 후보 비교")]
    assert "불일치" not in why_section
    assert "스캐너 선택 종목: 042700" not in why_section
    assert "실행 종목: 005930" not in why_section
    assert "실제 체결 종목 005930은 스캐너 1위/7개 후보" not in why_section
    assert "highest combined scanner score" not in why_section
    assert "점수에 직접 반영된 핵심 축" not in why_section
    assert "저장된 스캐너 비교 표는 042700 기준" in why_section


def test_render_trade_report_markdown_describes_monitor_fallback_without_mismatch() -> None:
    report = {
        "trade_id": "TRD_20260427_005930_02",
        "action": "SELL",
        "symbol": "005930",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "minimax/minimax-m2.5"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "strategist_summary": {"summary": "strategist", "bullets": []},
        "why_this_symbol_was_chosen": {
            "summary": "스캐너는 005930을 2위로 선정했습니다. 그러나 최종 선택에서 1위가 아닌 2위가 선택되는 불일치가 발생했습니다.",
            "symbol": "005930",
            "selected_rank": 2,
            "universe_size": 6,
            "bullets": [
                "스캐너 선정 순위: 2위 (종합 점수 1.105)",
                "1위였던 000660(종합 점수 1.435)이 최종 선택되지 않음",
            ],
            "scanner_selection_trace": {
                "selected_symbol": "005930",
                "selected_rank": 2,
                "monitor_fallback_used": True,
                "scanner_top_pick_symbol": "000660",
                "monitor_selected_symbol": "005930",
                "monitor_fallback_reason": "breakout above recent high with vwap structure confirmation",
                "selection_path": "monitor_fallback_from_scanner_top_pick",
                "ranked_candidates": [
                    {"rank": 1, "symbol": "000660", "score_total": 1.435, "risk_score": 0.476, "confidence": 0.805},
                    {"rank": 2, "symbol": "005930", "score_total": 1.105, "risk_score": 0.642, "confidence": 0.693},
                ],
                "selected_symbol_score_drivers": {
                    "trading_value": 0.238,
                    "momentum": 0.220,
                    "trend": 0.149,
                },
            },
        },
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
    }

    markdown = mod.render_trade_report_markdown(report)

    why_section = markdown[markdown.find("## 선택된 종목 상세 분석") : markdown.find("## 스캐너 후보 비교")]
    assert "불일치" not in why_section
    assert "실제 체결 종목 005930은 차순위 재평가 2위/6개 후보" in why_section
    assert "차순위 재평가" in why_section
    assert "스캐너 상위 후보 000660" in why_section


def test_render_trade_report_markdown_restores_news_from_market_context_human() -> None:
    report = {
        "trade_id": "TRD_20260424_098460_02",
        "action": "SELL",
        "symbol": "098460",
        "status": "closed",
        "story_type": "live trade report",
        "execution_mode_label": "real broker",
        "generation": {"status": "ok", "mode": "local_debug", "model": "minimax/minimax-m2.5"},
        "executive_summary": {"summary": "summary"},
        "market_context_human": {
            "summary": "Market regime was neutral with a defensive playbook. Global sentiment scored -0.04 and VIX was 19.31. 60 headlines were considered across 7 targets.",
            "regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "defensive",
            "global_sentiment_score": -0.04,
            "vix_level": 19.31,
            "headline_count": 60,
            "news_query_count": 7,
            "market_news_titles": [
                "코스피: <b>코스피</b> 6000 탈환 기대감",
                "코스피: 외인·기관 동반 매수세",
            ],
            "candidate_news_titles": [
                "005930: 삼성전자 실적 개선 기대",
                "000660: SK하이닉스 수요 회복 기대",
            ],
            "news_symbol_linkage": {
                "linkage_strength": "weak",
                "selected_symbol": "098460",
                "runner_up_symbol": "000660",
                "selected_vs_runner_up": {
                    "selected_symbol": "098460",
                    "runner_up_symbol": "000660",
                    "selected_headline_count": 0,
                    "runner_up_headline_count": 0,
                },
            },
        },
        "strategist_market_headlines": [
            "코스피: <b>코스피</b> 6000 탈환 기대감",
            "코스피: 외인·기관 동반 매수세",
        ],
        "strategist_symbol_headlines": [
            "005930: 삼성전자 실적 개선 기대",
            "000660: SK하이닉스 수요 회복 기대",
        ],
        "shared_facts": {
            "commander_route": {
                "applied_policy": {
                    "interpretation_policy": {
                        "entry_style": "defensive",
                        "notes": ["monitor_guidance:defensive_exit", "vwap_reclaim_required"],
                        "required_checks": ["reclaim_gate_ok"],
                        "blockers": ["failed_breakout=confirmed"],
                    }
                }
            }
        },
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "## 시장 환경 요약" in markdown
    assert "- 뉴스 입력은 7개 관찰 대상에서 60개 headline을 검토했습니다." in markdown
    assert "- 참고한 시장 뉴스는 코스피: 코스피 6000 탈환 기대감 / 코스피: 외인·기관 동반 매수세였습니다." in markdown
    assert "## 전략가 요약" in markdown
    assert "005930: 삼성전자 실적 개선 기대" not in markdown
    assert "전략가가 후보군 판단에 참고한 뉴스는" not in markdown
    assert "선택 종목 098460과 차순위 000660에 직접 연결된 뉴스는 모두 없어 시장 톤 확인용으로만 활용했습니다." in markdown


def test_render_trade_report_markdown_restores_news_from_nested_market_context_fields() -> None:
    report = {
        "trade_id": "TRD_20260424_098460_03",
        "action": "SELL",
        "symbol": "098460",
        "status": "closed",
        "story_type": "live trade report",
        "execution_mode_label": "real broker",
        "generation": {"status": "ok", "mode": "local_debug", "model": "minimax/minimax-m2.5"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {
            "summary": "",
            "bullets": [],
            "regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "defensive",
            "global_sentiment_score": -0.04,
            "strategist_market_headlines": [
                "코스피: <b>코스피</b> 6000 탈환 기대감",
                "코스피: 외인·기관 동반 매수세",
            ],
            "strategist_symbol_headlines": [
                "005930: 삼성전자 실적 개선 기대",
                "000660: SK하이닉스 수요 회복 기대",
            ],
        },
        "shared_facts": {
            "commander_route": {
                "applied_policy": {
                    "interpretation_policy": {
                        "entry_style": "defensive",
                        "notes": [],
                        "required_checks": [],
                        "blockers": [],
                    }
                }
            }
        },
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "- 참고한 시장 뉴스는 코스피: 코스피 6000 탈환 기대감 / 코스피: 외인·기관 동반 매수세였습니다." in markdown
    assert "후보 뉴스 2건" not in markdown
    assert "005930: 삼성전자 실적 개선 기대" not in markdown
    assert "000660: SK하이닉스 수요 회복 기대" not in markdown


def test_build_market_scanner_linkage_bullet_surfaces_numeric_trace() -> None:
    bullet = mod._build_market_scanner_linkage_bullet(
        {
            "playbook": "눌림목",
            "global_sentiment_score": 0.0797090927,
            "vix_level": 18.36,
        },
        {
            "selected_symbol": "000660",
            "selected_score": 1.2859626409,
            "selected_sources": ["top_value", "sector_theme"],
            "news_scanner_contribution": {
                "core_score_contributions": {
                    "theme_boost": {"value": 0.067392},
                    "sentiment": {"value": 0.0176772773},
                },
                "sentiment_inputs": {
                    "global_sentiment_score": 0.0797090927,
                    "weighted_sentiment_score_contribution": 0.0176772773,
                },
            },
        },
    )
    rendered = mod._operatorize_report_text(bullet)

    assert rendered.startswith("스캐너 연결 근거는 종목 000660을 눌림목 플레이북 기준으로 선정했고")
    assert "종합 점수 1.286" in rendered
    assert "감성 기여 +0.018" in rendered
    assert "테마 가점 +0.067" in rendered
    assert "글로벌 감성 0.080" in rendered
    assert "VIX 18.36" in rendered
    assert "selected 000660 under" not in rendered
    assert "because" not in rendered


def test_build_market_context_bullets_surfaces_market_axes_and_news() -> None:
    bullets = mod._build_market_context_bullets(
        {
            "regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "pullback",
            "themes": ["broad_market_leaders"],
            "theme_source": "unavailable",
            "theme_source_status": "unavailable",
            "theme_source_reason": "kiwoom_theme_live_fetch_disabled",
            "theme_strength_top_themes": [],
            "global_sentiment_score": 0.0808,
            "vix_level": 18.36,
            "fear_index": {"change_pct": -3.97},
            "headline_count": 60,
            "news_query_count": 7,
            "news_query_targets": ["코스피", "코스닥", "미국 증시"],
            "key_events": ["us_indices sp500=1.18% nasdaq=1.96% dow=0.66%"],
            "market_news_titles": [
                "코스피: <b>코스피</b> 6000 탈환 기대감",
                "코스피: 외인·기관 동반 매수세",
            ],
            "candidate_news_titles": [
                "000660: SK하이닉스, 1분기 영업익 38조 사상 최대",
            ],
        },
        scanner_reason={"selected_symbol": "000660"},
    )

    assert len(bullets) >= 5
    assert any("시장 상태는 중립" in bullet for bullet in bullets)
    assert any("글로벌 감성 0.081" in bullet and "VIX 18.36" in bullet for bullet in bullets)
    assert any("미국 지수는 S&P500 +1.18%" in bullet for bullet in bullets)
    assert any("뉴스 입력은 60건 헤드라인" in bullet for bullet in bullets)
    assert any("대표 종목/섹터 뉴스는 000660: SK하이닉스" in bullet for bullet in bullets)
    assert any("키움 테마 packet" in bullet and "status=unavailable" in bullet for bullet in bullets)


def test_build_strategist_summary_section_connects_inputs_and_scanner() -> None:
    section = mod._build_strategist_summary_section(
        {
            "regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "pullback",
            "themes": ["broad_market_leaders"],
            "risk_mode": "balanced",
            "selected_playbook": "pullback",
            "preferred_themes": ["broad_market_leaders"],
            "avoid_themes": ["defensive_assets", "counter_trend_low_liquidity"],
            "theme_source": "unavailable",
            "theme_source_status": "unavailable",
            "theme_source_reason": "kiwoom_theme_live_fetch_disabled",
            "theme_strength_top_themes": [],
            "scanner_bias_summary": {
                "active_biases": [
                    "prefer_shallow_pullback_candidates",
                    "penalize_overextended",
                    "prefer_reclaim_candidates",
                    "prefer_volume_confirmation",
                ],
                "bias_strength": "low",
            },
            "global_sentiment_score": 0.0808,
            "vix_level": 18.36,
            "headline_count": 60,
            "news_query_count": 7,
            "news_query_targets": ["코스피", "코스닥", "미국 증시"],
            "key_events": ["us_indices sp500=1.18% nasdaq=1.96% dow=0.66%"],
            "market_news_titles": ["코스피: 코스피 6000 탈환 기대감"],
            "candidate_news_titles": ["000660: SK하이닉스, 1분기 영업익 38조 사상 최대"],
        },
        {
            "selected_symbol": "000660",
            "selected_rank": 1,
            "selected_score": 1.2859626409,
            "selected_sources": ["top_value", "sector_theme"],
            "news_scanner_contribution": {
                "core_score_contributions": {
                    "theme_boost": {"value": 0.067392},
                    "sentiment": {"value": 0.0176772773},
                }
            },
        },
    )

    assert "전략가는 시장을 중립, 시장 심리를 중립으로 해석했고 눌림목 플레이북과 브로드마켓 리더 프레임을 유지했습니다." in section["summary"]
    assert any("핵심 입력은 글로벌 감성 0.081" in bullet for bullet in section["bullets"])
    assert any("전략 해석은 시장 상태 중립, 시장 심리 중립, 플레이북 눌림목, 핵심 테마 브로드마켓 리더, 스트레스 신호 없음 기준이었습니다." in bullet for bullet in section["bullets"])
    assert any("전략가가 관찰한 대상은 다음과 같았습니다: 코스피, 코스닥, 미국 증시." in bullet for bullet in section["bullets"])
    assert any("전략가 운용 기준은 리스크 모드 균형형이었고, 선택 플레이북은 눌림목이었습니다." in bullet for bullet in section["bullets"])
    assert any("전략가 선호/회피 기준은 선호 테마 브로드마켓 리더, 회피 테마 방어 자산, 역추세 저유동성이었습니다." in bullet for bullet in section["bullets"])
    assert any("전략가 테마 강도 입력은" in bullet and "status=unavailable" in bullet for bullet in section["bullets"])
    assert any("스캐너 바이어스는 얕은 눌림목 후보 선호, 과확장 후보 패널티, 재회복 후보 선호, 거래량 확인 후보 선호 (강도 낮음) 기준이었습니다." in bullet for bullet in section["bullets"])
    assert any("뉴스 연결 해석은 시장 뉴스로 시장 주도 대형주 우위 맥락을 확인했고" in bullet for bullet in section["bullets"])
    assert any("이 해석은 거래대금 상위와 섹터·테마 정렬 축으로 연결했습니다." in bullet for bullet in section["bullets"])
    assert any("스캐너 반영은 감성 기여 +0.018, 테마 가점 +0.067, 선정 소스 거래대금 상위와 섹터·테마 정렬" in bullet for bullet in section["bullets"])
    assert any("종목 연결은 000660, 1위, 점수 1.286" in bullet for bullet in section["bullets"])


def test_scanner_bias_text_parses_stringified_active_biases() -> None:
    rendered = mod._scanner_bias_text(
        {
            "active_biases": "['prefer_shallow_pullback_candidates', 'penalize_overextended', 'prefer_reclaim_candidates']",
            "bias_strength": "low",
            "summary": "prefer_shallow_pullback_candidates, penalize_overextended, prefer_reclaim_candidates (low)",
        }
    )

    assert rendered == "얕은 눌림목 후보 선호, 과확장 후보 패널티, 재회복 후보 선호 (강도 낮음)"


def test_build_scanner_filters_summary_and_bullets_from_checks() -> None:
    summary = mod._build_scanner_filters_summary(
        {
            "checks": [
                {"name": "liquidity filter", "status": "PASS", "detail": "top value input supported the selection"},
                {"name": "turnover filter", "status": "FAIL", "detail": "turnover evidence was weaker"},
                {"name": "price anomaly filter", "status": "NOT_AVAILABLE", "detail": "not captured in this run"},
            ],
            "feature_coverage": {"present": 12, "total": 13, "quality": "strong"},
        }
    )
    bullets = mod._build_scanner_filters_bullets(
        {
            "checks": [
                {"name": "liquidity filter", "status": "PASS", "detail": "top value input supported the selection"},
                {"name": "turnover filter", "status": "FAIL", "detail": "turnover evidence was weaker"},
            ]
        }
    )

    assert "통과 1개, 미통과 1개, 확인 불가 1개" in summary
    assert "12/13" in summary
    assert any("유동성 점검은 통과였습니다." in bullet for bullet in bullets)
    assert any("회전율 점검은 미통과였습니다." in bullet for bullet in bullets)


def test_render_trade_report_markdown_uses_explicit_strategist_summary_section() -> None:
    report = {
        "trade_id": "TRD_20260415_000660_01",
        "action": "SELL",
        "symbol": "000660",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": ["시장 상태는 중립입니다."]},
        "strategist_summary": {"summary": "전략가 해석입니다.", "bullets": ["핵심 입력은 global_sentiment 0.081이었습니다."]},
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "## 전략가 요약" in markdown
    assert "전략가 해석입니다." in markdown
    assert "핵심 입력은 global_sentiment 0.081이었습니다." in markdown


def test_render_trade_report_markdown_splits_strategist_refresh_trace() -> None:
    report = {
        "trade_id": "TRD_20260428_058430_01",
        "action": "BUY",
        "symbol": "058430",
        "status": "open",
        "story_type": "live trade report",
        "execution_mode_label": "mock broker",
        "generation": {"status": "ok", "mode": "fallback", "model": "none"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "strategist_summary": {"summary": "전략가 해석입니다.", "bullets": []},
        "strategist_output": {
            "strategy_thesis": {
                "one_line": "방어형 전략 프레임을 유지했습니다.",
                "selected_playbook": "defensive",
                "risk_tone": "normal",
            }
        },
        "strategist_refresh_trace": {
            "summary": "refresh trace",
            "stages": [
                {
                    "stage": "initial_frame",
                    "label": "1차 전략 프레임",
                    "summary": "1차 프레임은 full_cycle/RUN_REFRESH로 평가됐습니다.",
                },
                {
                    "stage": "post_scanner_refresh",
                    "label": "2차 후보 확정 후 refresh",
                    "summary": "선택 종목이 캐시 프레임 밖이라 refresh가 요청됐습니다.",
                    "requested": True,
                    "reason": "selected_symbol_outside_cached_frame",
                    "selected_symbol": "058430",
                },
                {
                    "stage": "final_application",
                    "label": "최종 적용 결과",
                    "summary": "정책 delta가 없어 기존 프레임을 유지했습니다.",
                    "evaluated": True,
                    "effective": False,
                    "policy_delta_count": 0,
                },
            ],
            "policy_delta_count": 0,
        },
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "HOLD", "watch_next": [], "thesis_invalidation": []},
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "## 전략가 Refresh Trace" in markdown
    assert "[1차 전략 프레임]" in markdown
    assert "[2차 후보 확정 후 refresh]" in markdown
    assert "selected_symbol_outside_cached_frame" in markdown
    assert "[최종 적용 결과]" in markdown
    assert markdown.find("## 전략가 요약") < markdown.find("## 전략가 Refresh Trace") < markdown.find("## 전략가 출력 근거")


def test_build_report_strategist_refresh_trace_uses_commander_refresh_facts() -> None:
    story_input = {
        "canonical_agent_artifacts": {
            "commander": {
                "commander_decision": {
                    "strategist_invocation": "RUN_REFRESH",
                    "route_selected": "full_cycle",
                    "observations": {
                        "post_scanner_refresh_requested": True,
                        "post_scanner_refresh_reason": "selected_symbol_outside_cached_frame",
                        "post_scanner_refresh_selected_symbol": "058430",
                    },
                    "strategist_refresh_requested": True,
                    "strategist_refresh_reason": "selected_symbol_outside_cached_frame",
                    "strategist_refresh_context": {
                        "selected_symbol": "058430",
                        "selected_symbol_in_cached_frame": False,
                        "cached_candidate_hints": ["005930", "000660"],
                    },
                    "strategist_refresh_evaluated": True,
                    "strategist_refresh_effective": False,
                    "strategist_refresh_policy_delta_count": 0,
                }
            },
            "strategist": {
                "playbook": "defensive",
                "commander_invocation_hint": "RUN_REFRESH",
            },
        }
    }

    trace = mod._build_report_strategist_refresh_trace(story_input)

    assert trace["refresh_requested"] is True
    assert trace["policy_delta_count"] == 0
    assert [row["stage"] for row in trace["stages"]] == [
        "initial_frame",
        "post_scanner_refresh",
        "final_application",
    ]
    assert "selected_symbol_outside_cached_frame" in trace["stages"][1]["summary"]
    assert "정책 delta가 없어" in trace["stages"][2]["summary"]


def test_render_trade_report_markdown_normalizes_guard_timeline_and_final_conclusion() -> None:
    report = {
        "trade_id": "TRD_20260415_000660_01",
        "action": "SELL",
        "symbol": "000660",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "local_debug", "model": "minimax/minimax-m2.5"},
        "executive_summary": {
            "summary": "Current lifecycle status is closed. Entry and exit are connected in one lifecycle story.",
        },
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "strategist_summary": {"summary": "strategy", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "guard_approval_result": {
            "summary": "Supervisor approved the order because Allowed.",
            "bullets": ["Approval mode: not captured in the execution trace"],
        },
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {
            "summary": "warnings",
            "bullets": ["Holding-phase evidence is thin; preserve more monitor context between entry and exit."],
        },
        "full_timeline": [
            {"event": "entry", "description": "Entry BUY was executed by run abc123."},
            {"event": "exit", "description": "Exit SELL was executed by run def456."},
        ],
        "final_operator_conclusion": {
            "summary": "Current lifecycle status is closed. Entry and exit are connected in one lifecycle story.",
            "current_action": "SELL",
            "watch_next": ["Lifecycle status: closed", "Monitor trigger changes", "Macro/news shifts"],
            "thesis_invalidation": ["stop-loss breach", "monitor and scanner divergence", "negative macro regime shift"],
        },
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "Current lifecycle status is closed" not in markdown
    assert "Supervisor approved the order because Allowed." not in markdown
    assert "Entry BUY was executed by run" not in markdown
    assert "Exit SELL was executed by run" not in markdown
    assert "현재 판단은 청산 완료입니다. 000660 거래는 매수 진입 후 매도 청산까지 기록됐습니다." in markdown
    assert "슈퍼바이저는 주문을 승인했고 가드 판단은 허용이었습니다." in markdown
    assert "승인 모드는 실행 추적에는 별도로 남아 있지 않습니다." in markdown
    assert "- 진입: run abc123에서 매수 진입이 실행됐습니다." in markdown
    assert "- 청산: run def456에서 매도 청산이 실행됐습니다." in markdown
    assert "- 다음 확인 항목은 라이프사이클 상태는 종결입니다.입니다." not in markdown
    assert "- 다음 확인 항목은 라이프사이클 상태 종결입니다." in markdown
    assert "- 다음 확인 항목은 모니터 트리거 변화입니다." in markdown
    assert "- 다음 확인 항목은 거시 환경 및 뉴스 변화입니다." in markdown
    assert "- 기존 판단이 무효화되는 조건은 손절 기준 이탈입니다." in markdown
    assert "- 기존 판단이 무효화되는 조건은 모니터와 스캐너 판단 발산입니다." in markdown
    assert "- 기존 판단이 무효화되는 조건은 거시 환경의 부정적 전환입니다." in markdown
    assert "- 보유 구간 근거는 제한적이며 진입과 청산 사이 모니터 맥락이 충분하지 않습니다." in markdown


def test_render_trade_report_markdown_translates_timeline_and_final_conclusion() -> None:
    report = {
        "trade_id": "TRD_20260320_000660_01",
        "action": "SELL",
        "symbol": "000660",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "salvaged", "mode": "ai", "model": "openrouter/free", "reason": "partial"},
        "executive_summary": {"summary": "嫄곕옒??泥?궛源뚯? ?꾨즺?먯뒿?덈떎."},
        "market_context_at_entry": {"summary": "?쒖옣 ?щ━???ㅼ냼 ?쏀뻽吏留??좏깮 醫낅ぉ 媛뺣룄???좎??먯뒿?덈떎.", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "?곷? 媛뺣룄? 嫄곕옒?湲덉씠 ?곗닔?덉뒿?덈떎.", "bullets": []},
        "entry_decision": {"summary": "遺꾨큺 ?щ룎???뺤씤 ??吏꾩엯?덉뒿?덈떎.", "bullets": []},
        "holding_monitoring_story": {"summary": "hold", "bullets": ["Decision chain: hold -> hold -> hold"]},
        "exit_decision": {"summary": "SELL was triggered because hard_stop.", "bullets": ["Exit action: SELL", "Exit reason: hard_stop"]},
        "scanner_filters": {"summary": "filters", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "none", "bullets": []},
        "full_timeline": [{"event": "entry", "description": "breakout confirmed"}, {"event": "exit", "description": "hard stop triggered"}],
        "final_operator_conclusion": {"summary": "open trade", "current_action": "SELL", "watch_next": ["VWAP retest"], "thesis_invalidation": ["prior low break"]},
    }

    markdown = mod.render_trade_report_markdown(report)

    assert "## 생성 정보" in markdown
    assert "## 전체 타임라인" in markdown
    assert "- 진입:" in markdown
    assert "- 청산:" in markdown
    assert "## 최종 운영 판단" in markdown
    assert "- 현재 판단 액션은 매도입니다." in markdown
    assert "- 다음 확인 항목은" in markdown
    assert "- 기존 판단이 무효화되는 조건은" in markdown


