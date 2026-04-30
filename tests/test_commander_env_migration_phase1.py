from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from graphs.commander_runtime import _run_integrated_chain
from libs.reporting.reporter_ai_review import build_ai_reporter_review
from libs.reporting.trade_report_ai import build_ai_trade_report
from scripts.run_live_execution_bundle_report import _resolve_trade_report_policy, _seed_diagnostics_for_policy


_REMOVED_ENV_KEYS = [
    "REPORTER_AI_REVIEW_ENABLED",
    "TRADE_REPORT_AI_ENABLED",
    "TRADE_REPORT_AI_GENERATE_ON_OPEN",
    "USE_EXIT_POLICY",
    "EXIT_POLICY_USE_EOD_FLAT",
    "MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION",
    "AI_STRATEGIST_STRICT",
    "ALLOW_LEGACY_RULE_RUNTIME",
    "ALLOW_LEGACY_STRATEGY_V1_RUNTIME",
    "COMMANDER_POST_SCANNER_REFRESH_ENABLED",
    "MEMORY_BIAS_OBSERVATION_ONLY",
    "USE_STRATEGY_MEMORY_FEEDBACK",
    "USE_STRATEGY_PERFORMANCE_MEMORY",
    "COMMANDER_MEMORY_USAGE_DISABLED",
    "STRATEGIST_MEMORY_USAGE_DISABLED",
    "STRATEGY_MEMORY_PERSIST_ENABLED",
    "COMMANDER_MONITOR_ONLY_WHEN_HOLDING_ENABLED",
    "COMMANDER_STRATEGIST_CACHE_WHEN_FLAT_ENABLED",
    "MONITOR_SCORING_ENABLED",
    "MONITOR_SCORING_SHADOW_MODE",
]


def _story_input() -> Dict[str, Any]:
    return {
        "trade_id": "TRD_20260408_000660_01",
        "story_id": "TRD_20260408_000660_01",
        "run_id": "run-1",
        "day": "2026-04-08",
        "symbol": "000660",
        "action": "HOLD",
        "status": "open",
        "story_type": "simulation",
        "execution_mode_label": "simulation",
        "monitor_reason_human": {"posture": "HOLD"},
    }


def test_commander_env_migration_phase1_removed_keys_absent_from_env_example() -> None:
    text = Path("config/.env.example").read_text(encoding="utf-8")
    for key in _REMOVED_ENV_KEYS:
        assert key not in text, key


def test_commander_env_migration_docs_are_utf8_and_have_keywords() -> None:
    for rel_path, keywords in {
        "docs/report_plan/commander_env_migration_plan.md": [
            "Commander-Centric Configuration Migration Plan",
            "applied_policy",
            "Commander owns configuration choice",
            "Runtime semantics",
        ],
        "docs/report_plan/commander_env_migration_phase1.md": [
            "Commander Env Migration Phase 1",
            "Removed env keys",
            "Canonical applied policy paths",
            "Runtime semantics unchanged",
        ],
    }.items():
        text = Path(rel_path).read_text(encoding="utf-8")
        lowered = text.lower()
        for keyword in keywords:
            assert keyword.lower() in lowered, (rel_path, keyword)


def test_reporter_ai_review_reads_applied_policy_without_env(monkeypatch) -> None:
    monkeypatch.setenv("DRY_RUN", "1")

    disabled = build_ai_reporter_review(
        day="2026-04-08",
        reporter_output={"applied_policy": {"reporter": {"ai_review": {"enabled": False}}}},
    )
    assert disabled["status"] == "disabled"
    assert disabled["reason"] == "reporter.ai_review.enabled is false"

    enabled = build_ai_reporter_review(
        day="2026-04-08",
        reporter_output={"applied_policy": {"reporter": {"ai_review": {"enabled": True}}}},
    )
    assert enabled["status"] == "dry_run"


def test_trade_report_policy_reads_applied_policy_without_env() -> None:
    policy = _resolve_trade_report_policy(
        runtime_state={"applied_policy": {"reporter": {"trade_report": {"enabled": False, "generate_on_open": False}}}}
    )
    assert policy["enabled"] is False
    assert policy["generate_on_open"] is False
    assert policy["policy_source"] == "runtime_state.applied_policy"

    diagnostics, should_attempt = _seed_diagnostics_for_policy(
        lifecycle_status="open",
        story_type="simulation",
        report_requested=True,
        story_input_available=True,
        model_hint="test/model",
        generate_on_open=False,
    )
    assert should_attempt is False
    assert diagnostics["report_status"] == "pending"
    assert diagnostics["report_reason_code"] == "awaiting_exit_for_full_report"

    disabled_report = build_ai_trade_report(
        {
            **_story_input(),
            "applied_policy": {"reporter": {"trade_report": {"enabled": False}}},
        }
    )
    assert (disabled_report.get("generation") or {}).get("status") == "disabled"
    assert (disabled_report.get("generation") or {}).get("reason") == "reporter.trade_report.enabled is false"


def test_commander_injects_behavior_policy_defaults_into_applied_policy(monkeypatch) -> None:
    temporary_keys = {
        "COMMANDER_POST_SCANNER_REFRESH_ENABLED",
        "MEMORY_BIAS_OBSERVATION_ONLY",
        "USE_STRATEGY_MEMORY_FEEDBACK",
        "USE_STRATEGY_PERFORMANCE_MEMORY",
        "COMMANDER_MEMORY_USAGE_DISABLED",
        "STRATEGIST_MEMORY_USAGE_DISABLED",
        "STRATEGY_MEMORY_PERSIST_ENABLED",
    }
    for key in temporary_keys:
        monkeypatch.delenv(key, raising=False)

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        state["portfolio_snapshot"] = {"cash": 1_000_000.0, "positions": [], "_health": {"reader_ok": True}}
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        state["strategist_output"] = {"playbook": "pullback"}
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["selected"] = {"symbol": "005930"}
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        state["decision"] = "hold"
        return state

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain({}, execute_fn=lambda state: state)
    applied = out.get("applied_policy") or {}

    assert (((applied.get("reporter") or {}).get("ai_review") or {}).get("enabled")) is False
    assert (((applied.get("reporter") or {}).get("trade_report") or {}).get("enabled")) is True
    assert (((applied.get("reporter") or {}).get("trade_report") or {}).get("generate_on_open")) is False
    assert (((applied.get("strategist") or {}).get("runtime") or {}).get("strict_mode")) is True
    assert (((applied.get("strategist") or {}).get("runtime") or {}).get("allow_legacy_rule")) is False
    assert (((applied.get("strategist") or {}).get("runtime") or {}).get("allow_legacy_strategy_v1")) is False
    assert (((applied.get("strategist") or {}).get("memory_feedback") or {}).get("enabled")) is False
    assert (((applied.get("strategist") or {}).get("performance_memory") or {}).get("enabled")) is False
    assert (((applied.get("strategist") or {}).get("performance_memory") or {}).get("persist_enabled")) is False
    assert (((applied.get("strategist") or {}).get("memory_usage") or {}).get("disabled")) is True
    assert (((applied.get("commander") or {}).get("memory_usage") or {}).get("disabled")) is True
    assert (((applied.get("scanner") or {}).get("memory_bias") or {}).get("observation_only")) is True
    assert (((applied.get("monitor") or {}).get("memory_bias") or {}).get("observation_only")) is True
    assert (((applied.get("commander") or {}).get("route") or {}).get("post_scanner_refresh_enabled")) is True
    assert (((applied.get("commander") or {}).get("route") or {}).get("monitor_only_when_holding")) is True
    assert (((applied.get("commander") or {}).get("route") or {}).get("cached_strategist_when_flat")) is False
    assert (((applied.get("monitor") or {}).get("exit") or {}).get("enabled")) is True
    assert ((((applied.get("monitor") or {}).get("exit") or {}).get("eod_flat") or {}).get("enabled")) is True
    assert (((applied.get("monitor") or {}).get("entry") or {}).get("block_buy_when_open_position")) is True
    assert ((((applied.get("monitor") or {}).get("entry") or {}).get("scoring") or {}).get("enabled")) is False
    assert ((((applied.get("monitor") or {}).get("entry") or {}).get("scoring") or {}).get("shadow_mode")) is True
    assert "reporter.ai_review.enabled" in list(((applied.get("policy_sources") or {}).get("commander_owned_fields") or []))
    for key in temporary_keys:
        assert os.getenv(key) is None
    commander_decision = out.get("commander_decision") or {}
    assert (commander_decision.get("commander_applied_policy_summary") or {}).get("strategist_strict_mode") is True
    assert (commander_decision.get("policy_sources") or {}).get("commander_owned_fields")
