from __future__ import annotations

import json
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
    assert monitor_reasoning.get("threshold_shortfalls") == ["volume ratio 0.10 below min 0.75"]
    assert compact_input["commander"]["selected_route"] == "cached_strategist"
    assert compact_input["commander"]["route_reason_text"] == "commander_skip_cached_strategist"
    assert compact_input["commander"]["policy_source"] == "strategist"
    assert compact_input["commander"]["applied_policy"]["volume_ratio_min"] == 0.68
    assert compact_input["commander"]["policy_partial_normalized"] is True
    assert compact_input["market_context"]["candidate_hints"] == ["122630", "233740", "005930"]
    assert compact_input["market_context"]["market_headlines"][0] == "KOSPI opens higher as chip demand expectations improve."
    assert compact_input["market_context"]["symbol_headlines"][0] == "000660 rises on renewed AI memory optimism."
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
    assert deterministic["market_context_at_entry"]["strategist_candidate_hints"] == ["122630", "233740", "005930"]
    assert deterministic["why_this_symbol_was_chosen"]["scanner_selection_trace"]["selected_symbol"] == "000660"
    assert deterministic["holding_monitoring_story"]["monitor_stop_policy_trace"]["effective_stop_loss_pct"] == 0.0092


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
    assert "아래 JSON 템플릿에 값만 채워 반환하십시오" in user_prompt
    assert "영어 source 문장을 그대로 복사하지 마십시오." in user_prompt
    assert "selection_basis" in user_prompt
    assert "runner_ups_lost" in user_prompt
    assert "decision_reason_chain" in user_prompt


def test_ai_trade_report_repair_messages_do_not_reinject_non_json_reasoning() -> None:
    messages = mod._build_repair_messages(_story_input(), "First, the user says I should output JSON.")
    system_prompt = str(messages[0]["content"])
    user_prompt = str(messages[1]["content"])

    assert "사고 과정" in system_prompt
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

    assert "마지막 복구 패스" in sparse_prompt
    assert "full_timeline은 최대 8개 행" in sparse_prompt
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
    assert "남아 있는 영어 설명 문장을 모두 한국어로 번역하십시오." in user_prompt
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


def test_ai_trade_report_uses_openrouter_default_max_tokens_when_role_value_missing(monkeypatch) -> None:
    monkeypatch.setattr(mod, "LLMRouter", _CapturePolicyRouter)
    monkeypatch.delenv("TRADE_REPORT_AI_MAX_TOKENS", raising=False)
    monkeypatch.setenv("OPENROUTER_DEFAULT_MAX_TOKENS", "4096")

    report = mod.build_ai_trade_report(_story_input(), enabled=True, model="free")

    assert report["generation"]["status"] == "ok"
    assert _CapturePolicyRouter.last_policies
    assert int(_CapturePolicyRouter.last_policies[0]["max_tokens"]) == 4096
    assert _CapturePolicyRouter.last_policies[0]["plugins"] == [{"id": "response-healing"}]


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
        "news_query_targets": ["코스피", "미국 증시"],
        "key_events_hint": ["fear_index vix=25.09 change=12.16% pressure=0.255"],
        "summary": "risk-off market context",
        "bullets": ["Market regime: risk_off"],
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
    assert any(str(row).startswith("뉴스 입력 요약은") for row in report["market_context_at_entry"]["bullets"])
    assert sum(1 for row in report["market_context_at_entry"]["bullets"] if str(row).startswith("뉴스 조회 대상은")) == 1
    assert any(str(row).startswith("전략가 핵심 입력은") for row in report["market_context_at_entry"]["bullets"])
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
        "universe_size": 5,
        "selected_score": 1.178,
        "ranking_basis": ["trading value", "theme and sector alignment"],
        "selected_sources": ["top_value", "sector_theme"],
        "confidence": 0.81,
        "runner_ups_lost": [
            {"symbol": "005930", "summary": "lower total score and higher risk"},
            {"symbol": "047040", "summary": "lower confidence and higher risk"},
        ],
        "summary": "scanner selected rank #1",
        "bullets": ["Universe scanned: 5", "Selected rank: #1"],
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
    entry_summary = report["entry_decision"]["summary"]
    assert "총 5개 후보 중 1순위" in why_summary
    assert "선정에 반영된 소스는 top_value, sector_theme" in why_summary
    assert "005930은 lower total score and higher risk 때문에 밀렸습니다" in why_summary
    assert report["why_this_symbol_was_chosen"]["basis"] == "trading value, theme and sector alignment"
    assert "진입 판단은 매수로 이어졌습니다." in entry_summary


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
    assert any(str(row).startswith("상위 후보는") for row in bullets)
    assert any(str(row).startswith("최종 선정 판단은") for row in bullets)
    assert any(str(row).startswith("동률 해소 기준은") for row in bullets)


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
    assert any(str(row).startswith("모니터는 총") for row in bullets)
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
    assert any(str(row).startswith("감지된 핵심 신호는") for row in bullets)
    assert any(str(row).startswith("청산 시점의 유효 손절 기준은 1.00%") for row in bullets)
    assert any(str(row).startswith("현재가, 평균가, 고점 기준 값은 29300.00 / 29650.00 / 29650.00") for row in bullets)
    assert any(str(row).startswith("판단 흐름은 confirmed_exit_signal -> hard_stop -> hard_stop") for row in bullets)


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
                "summary": "실행이 정상 완료되었습니다.",
                "bullets": ["실행 결과: 기록됨", "수량: 1", "실행 모드: 시뮬레이션 (모의 브로커)"],
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
    assert bullets == ["실행 결과: 기록됨", "수량: 1", "실행 모드: 시뮬레이션 (모의 브로커)"]


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
    assert "주문 실행 결과는 recorded입니다." in joined


def test_render_trade_report_markdown_uses_korean_titles_and_narrative_labels() -> None:
    report = {
        "trade_id": "TRD_20260320_005930_01",
        "action": "BUY",
        "symbol": "005930",
        "status": "open",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "삼성전자 단기 모멘텀 진입 이후 현재는 보유 유지 관점으로 관리 중입니다."},
        "market_context_at_entry": {"summary": "시장 환경은 중립이지만 반도체 대형주로 수급이 집중됐습니다.", "bullets": ["global sentiment -0.20", "vix 25.09"]},
        "why_this_symbol_was_chosen": {"summary": "전체 후보 중 1순위로 선정됐습니다.", "bullets": ["Top candidates: 005930, 000660, 047040"]},
        "entry_decision": {"summary": "분봉 기준 돌파와 거래량 증가가 함께 확인됐습니다.", "bullets": ["VWAP hold", "volume ratio 1.8x"]},
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
    assert "목표 수익 실현 기준은 1.80% 수준입니다." in markdown
    assert "고정 손절 기준" in markdown


def test_render_trade_report_markdown_translates_fixed_english_report_phrases() -> None:
    report = {
        "trade_id": "TRD_20260323_000660_01",
        "action": "BUY",
        "symbol": "000660",
        "status": "open",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free"},
        "executive_summary": {"summary": "중립 Regime, bearish Market Sentiment, pullback playbook 적용."},
        "market_context_at_entry": {
            "summary": "중립 Regime, bearish Market Sentiment, pullback playbook 적용.",
            "bullets": [
                "Stress Flags: elevated_vix, yield_rise",
                "News input: 75 headlines were considered across 10 targets (10 market / 5 candidate signals).",
            ],
        },
        "why_this_symbol_was_chosen": {
            "summary": "selection",
            "bullets": [
                "Scanner Rank: 1위 / Total Score: 0.661",
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
    assert "추적 손절" in markdown
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
        "executive_summary": {"summary": "매매 결과를 정리했습니다."},
        "market_context_at_entry": {
            "summary": "시장 상황을 정리했습니다.",
            "bullets": ["global_sentiment score=-0.258 status=ok source=yfinance"],
        },
        "why_this_symbol_was_chosen": {"summary": "선정 이유를 정리했습니다.", "bullets": []},
        "entry_decision": {"summary": "진입 근거를 정리했습니다.", "bullets": []},
        "holding_monitoring_story": {"summary": "보유 경과를 정리했습니다.", "bullets": []},
        "exit_decision": {"summary": "청산 근거를 정리했습니다.", "bullets": []},
        "scanner_filters": {"summary": "필터 점검 결과를 정리했습니다.", "bullets": []},
        "guard_approval_result": {"summary": "승인 결과를 정리했습니다.", "bullets": []},
        "execution_quality": {"summary": "실행 결과를 정리했습니다.", "bullets": []},
        "reporter_evaluation": {"summary": "평가 결과를 정리했습니다.", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "보완 포인트를 정리했습니다.", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "최종 판단을 정리했습니다.", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
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


def test_render_trade_report_markdown_translates_timeline_and_final_conclusion() -> None:
    report = {
        "trade_id": "TRD_20260320_000660_01",
        "action": "SELL",
        "symbol": "000660",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "salvaged", "mode": "ai", "model": "openrouter/free", "reason": "partial"},
        "executive_summary": {"summary": "거래는 청산까지 완료됐습니다."},
        "market_context_at_entry": {"summary": "시장 심리는 다소 약했지만 선택 종목 강도는 유지됐습니다.", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "상대 강도와 거래대금이 우수했습니다.", "bullets": []},
        "entry_decision": {"summary": "분봉 재돌파 확인 후 진입했습니다.", "bullets": []},
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

    assert "## 생성 참고" in markdown
    assert "## 전체 타임라인" in markdown
    assert "- 진입:" in markdown
    assert "- 청산:" in markdown
    assert "## 최종 운영 판단" in markdown
    assert "- 현재 판단 액션은 매도입니다." in markdown
    assert "- 다음 확인 항목은" in markdown
    assert "- 기존 판단이 무효화되는 조건은" in markdown
