from __future__ import annotations

import json
import time
from typing import Any, Dict, List

import libs.reporting.trade_report_ai as mod


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
    assert "full_timeline" in sparse_prompt
    assert len(sparse_prompt) < len(regular_prompt)


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
    assert any("차트 피처 커버리지는 12/13였습니다. 누락된 항목은 60일선, 120일선이었습니다." in row for row in why_bullets)
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
    assert "진입 신뢰도 점수는 0.55로 기준 0.55와 동일했습니다." in summary
    assert any("진입 사유는 직전 고점 돌파와 VWAP 구조 확인이었습니다." in row for row in bullets)
    assert any("진입 시점 스캐너에서는 000660이 1위, 종합 점수 1.286였습니다." in row for row in bullets)
    assert any("실제 진입 경로는 돌파 경로였습니다. 통과 경로는 돌파 경로였습니다." in row for row in bullets)
    assert any("진입 게이트 상태는 VWAP 재회복 통과, 과확장 점검 통과, 신뢰도 게이트 통과였습니다." in row for row in bullets)
    assert any("적용 정책은 1분봉, 돌파 확인 기준 봉 수 4, 최소 거래량 비율 0.73, VWAP 재회복 필수, 반등 확인 필수였습니다." in row for row in bullets)


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
    assert any("당일 reporter 연계 상태는 동일 실행 기록 직접 연계였습니다." in row for row in section["bullets"])
    assert any("동일 일자 reporter도 과매매 또는 빠른 청산 압력을 시사했습니다." in row for row in section["bullets"])


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
    assert "이번 라이프사이클은 종결 상태이며, 진입과 청산이 하나의 거래 흐름으로 연결됐습니다." in markdown
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
    assert "- 보유 단계 근거가 얇아 진입과 청산 사이의 모니터 맥락을 더 보존해야 합니다." in markdown


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


