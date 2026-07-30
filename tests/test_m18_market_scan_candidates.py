from __future__ import annotations

from graphs.nodes.strategist_node import strategist_node


def test_m18_strategist_generates_3_to_5_candidates_without_manual_input(monkeypatch):
    # ensure DRY_RUN forces fallback (no network)
    monkeypatch.setenv("DRY_RUN", "1")
    out = strategist_node({})
    cands = out.get("candidates")
    assert isinstance(cands, list)
    assert 3 <= len(cands) <= 5
    assert all(isinstance(x, dict) and x.get("symbol") for x in cands)


def test_m18_strategist_respects_state_candidate_symbols_injection():
    out = strategist_node({"candidate_symbols": ["111111", "222222", "333333", "444444", "555555", "666666"]})
    cands = out.get("candidates")
    assert [x["symbol"] for x in cands] == ["111111", "222222", "333333", "444444", "555555"]


def test_m18_strategist_embeds_commander_context_and_plan_without_breaking_strategy_policy(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    out = strategist_node(
        {
            "runtime_phase": "session",
            "candidate_symbols": ["111111", "222222", "333333"],
            "commander_decision": {
                "command_intent": "OBSERVE_ONLY",
                "strategist_invocation": "SKIP",
                "llm_policy": "SKIP",
                "market_regime": "neutral",
                "session_bias": "active_selection",
                "risk_mode": "balanced",
                "allowed_playbooks": ["pullback", "defensive"],
                "banned_playbooks": ["reversal"],
                "scanner_mission": "Prioritize liquid leaders.",
                "monitor_mission": "Wait for confirmation and protect downside.",
                "no_trade_reason_code": "WAIT_FOR_CONFIRMATION",
                "observations": {"market_changed": False},
                "source_priority": ["shadow_commander", "runtime_observation", "strategist_fallback"],
                "shadow_used": True,
                "strategist_fallback_used": False,
                "decision_summary": "Commander prefers balanced pullback scouting.",
            },
        }
    )

    strategy_policy = out.get("strategy_policy") or {}
    assert "market_policy" in strategy_policy
    assert "scanner_policy" in strategy_policy
    assert "monitor_policy" in strategy_policy
    assert "decision_policy" in strategy_policy
    assert strategy_policy["commander_context"]["market_regime"] == "neutral"
    assert strategy_policy["commander_context"]["command_intent"] == "OBSERVE_ONLY"
    assert strategy_policy["commander_context"]["strategist_invocation"] == "SKIP"
    assert strategy_policy["commander_context"]["llm_policy"] == "SKIP"
    assert strategy_policy["commander_context"]["no_trade_reason_code"] == "WAIT_FOR_CONFIRMATION"
    assert strategy_policy["commander_context"]["source_priority"][0] == "shadow_commander"
    assert strategy_policy["provenance"]["market_policy_owner"] == "commander"
    assert strategy_policy["provenance"]["scanner_policy_owner"] == "strategist"
    assert strategy_policy["provenance"]["shadow_used"] is True
    assert strategy_policy["provenance"]["strategist_fallback_used"] is False
    assert strategy_policy["strategist_plan"]["selected_playbook"] == (out.get("strategist_output") or {}).get("playbook")


def test_m18_strategist_generates_monitor_entry_policy_baseline(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    out = strategist_node(
        {
            "runtime_phase": "session",
            "candidate_symbols": ["111111", "222222", "333333"],
        }
    )

    strategist_output = out.get("strategist_output") or {}
    strategy_policy = strategist_output.get("strategy_policy") or {}
    monitor_policy = strategy_policy.get("monitor_policy") or {}

    assert strategist_output.get("policy_source") == "strategist"
    assert strategist_output.get("policy_validation_status") == "ok"
    assert strategist_output.get("policy_fallback_used") is False
    assert isinstance(strategist_output.get("monitor_entry_policy"), dict)
    assert strategist_output["monitor_entry_policy"]["volume_ratio_min"] == 0.68
    assert strategist_output["monitor_entry_policy"]["pullback_min_pct"] == 0.008
    assert strategist_output["monitor_entry_policy"]["threshold_policy"]["volume_ratio_min"] == 0.68
    assert strategist_output["monitor_entry_policy"]["interpretation_policy"]["entry_style"] == strategist_output.get("playbook")
    assert "required_checks" in strategist_output["monitor_entry_policy"]["interpretation_policy"]
    assert isinstance(strategist_output.get("policy_rationale"), str)
    assert isinstance(strategist_output.get("market_regime_summary"), str)
    assert strategist_output["strategy_horizon_feedback"]["observability_only"] is True
    assert strategist_output["strategist_horizon_proposal"]["observability_only"] is True
    assert strategist_output["commander_horizon_policy"]["owner"] == "commander"
    assert strategist_output["commander_horizon_policy"]["observability_only"] is False
    assert strategist_output["commander_horizon_policy"]["allow_behavior_change"] is True
    assert strategist_output["commander_horizon_policy"]["do_not_force_hold"] is True
    assert strategist_output["strategy_horizon"] in {"scalp", "intraday"}
    assert strategist_output["strategy_horizon_feedback"]["monitor_handoff"]["do_not_force_hold"] is True
    assert isinstance(monitor_policy.get("entry_policy"), dict)
    assert monitor_policy["strategy_horizon_feedback"]["observability_only"] is True
    assert monitor_policy["commander_horizon_policy"]["owner"] == "commander"
    assert monitor_policy["entry_policy"]["volume_ratio_min"] == 0.68
    assert monitor_policy["entry_policy"]["threshold_policy"]["volume_ratio_min"] == 0.68
    assert monitor_policy["entry_policy"]["interpretation_policy"]["entry_style"] == strategist_output.get("playbook")
    assert isinstance(strategist_output.get("scanner_bias_context"), dict)
    assert isinstance((strategy_policy.get("scanner_policy") or {}).get("scanner_bias"), dict)
    assert strategist_output.get("scanner_bias_summary", {}).get("summary")


def test_m18_strategist_generates_structure_aware_interpretation_policy(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    out = strategist_node(
        {
            "runtime_phase": "session",
            "candidate_symbols": ["111111", "222222", "333333"],
            "ai_strategist_output": {
                "playbook": "breakout",
                "monitor_guidance": "hold_through_noise",
                "risk_tone": "normal",
                "trade_aggressiveness": "high",
                "policy_source": "strategist",
            },
        }
    )

    interpretation = ((out.get("strategist_output") or {}).get("monitor_entry_policy") or {}).get("interpretation_policy") or {}

    assert interpretation.get("entry_style") == "breakout"
    assert "structure_hh_hl=intact" in list(interpretation.get("preferred_checks") or [])
    assert "momentum_follow_through=strong" in list(interpretation.get("preferred_checks") or [])
    assert "failed_breakout=confirmed" in list(interpretation.get("blockers") or [])
    assert "momentum_decay=strong" in list(interpretation.get("blockers") or [])
    assert "structure_hh_hl" in list((interpretation.get("evidence_focus") or {}).get("primary") or [])


def test_m18_strategist_invalid_monitor_entry_policy_falls_back_with_trace(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    out = strategist_node(
        {
            "runtime_phase": "session",
            "candidate_symbols": ["111111", "222222", "333333"],
            "ai_strategist_output": {
                "playbook": "pullback",
                "monitor_entry_policy": {
                    "timeframe_minutes": 30,
                    "volume_ratio_min": 9.0,
                    "pullback_min_pct": -1.0,
                    "pullback_max_pct": 0.001,
                },
                "policy_rationale": "Try an invalid draft to verify fallback behavior.",
                "policy_source": "strategist",
            },
        }
    )

    strategist_output = out.get("strategist_output") or {}
    policy = strategist_output.get("monitor_entry_policy") or {}

    assert strategist_output.get("policy_validation_status") == "fallback_invalid"
    assert strategist_output.get("policy_fallback_used") is True
    assert "invalid_fields=" in str(strategist_output.get("policy_fallback_reason") or "")
    assert isinstance(strategist_output.get("policy_validation_issues"), list)
    assert policy["timeframe_minutes"] == 1
    assert policy["volume_ratio_min"] == 0.68
    assert policy["pullback_min_pct"] == 0.008
    assert policy["pullback_max_pct"] == 0.07


def test_m18_strategist_partial_monitor_entry_policy_marks_partial_normalized(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    out = strategist_node(
        {
            "runtime_phase": "session",
            "candidate_symbols": ["111111", "222222", "333333"],
            "ai_strategist_output": {
                "playbook": "pullback",
                "monitor_entry_policy": {
                    "volume_ratio_min": 0.72,
                    "pullback_min_pct": 0.01,
                },
                "policy_rationale": "Keep the draft sparse and let defaults fill safe gaps.",
                "policy_source": "strategist",
            },
        }
    )

    strategist_output = out.get("strategist_output") or {}
    policy = strategist_output.get("monitor_entry_policy") or {}

    assert strategist_output.get("policy_validation_status") == "partial_normalized"
    assert strategist_output.get("policy_fallback_used") is False
    assert strategist_output.get("policy_partial_normalized") is True
    assert "enabled" in list(strategist_output.get("policy_default_filled_fields") or [])
    assert "enabled" in list(strategist_output.get("policy_validation_missing_fields") or [])
    assert list(strategist_output.get("policy_validation_invalid_fields") or []) == []
    assert policy["volume_ratio_min"] == 0.72
    assert policy["pullback_min_pct"] == 0.01
    assert policy["timeframe_minutes"] == 1


def test_m18_strategist_clamps_positive_min_extended_without_invalid_fallback(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    out = strategist_node(
        {
            "runtime_phase": "session",
            "candidate_symbols": ["111111", "222222", "333333"],
            "ai_strategist_output": {
                "playbook": "pullback",
                "monitor_entry_policy": {
                    "volume_ratio_min": 0.72,
                    "min_extended_from_vwap_pct": 0.0015,
                },
                "policy_rationale": "Clamp an over-strict positive lower VWAP extension bound.",
                "policy_source": "strategist",
            },
        }
    )

    strategist_output = out.get("strategist_output") or {}
    policy = strategist_output.get("monitor_entry_policy") or {}

    assert strategist_output.get("policy_validation_status") == "partial_normalized"
    assert strategist_output.get("policy_fallback_used") is False
    assert list(strategist_output.get("policy_validation_invalid_fields") or []) == []
    assert policy["min_extended_from_vwap_pct"] == 0.0
    assert any(
        "min_extended_from_vwap_pct:clamped_to_upper_bound" in str(issue)
        for issue in list(strategist_output.get("policy_validation_issues") or [])
    )


def test_m18_strategist_accepts_percent_unit_monitor_entry_policy(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    out = strategist_node(
        {
            "runtime_phase": "session",
            "candidate_symbols": ["111111", "222222", "333333"],
            "ai_strategist_output": {
                "playbook": "pullback",
                "monitor_entry_policy": {
                    "volume_ratio_min": 0.72,
                    "min_extended_from_vwap_pct": -1.5,
                    "max_extended_from_vwap_pct": 3.0,
                    "pullback_min_pct": 0.5,
                    "pullback_max_pct": 3.0,
                    "reclaim_tolerance_pct": 0.2,
                },
                "policy_rationale": "LLM expressed pct thresholds in percent units.",
                "policy_source": "strategist",
            },
        }
    )

    strategist_output = out.get("strategist_output") or {}
    policy = strategist_output.get("monitor_entry_policy") or {}
    issues = [str(issue) for issue in list(strategist_output.get("policy_validation_issues") or [])]

    assert strategist_output.get("policy_fallback_used") is False
    assert strategist_output.get("policy_validation_status") == "partial_normalized"
    assert list(strategist_output.get("policy_validation_invalid_fields") or []) == []
    assert policy["min_extended_from_vwap_pct"] == -0.015
    assert policy["max_extended_from_vwap_pct"] == 0.03
    assert policy["pullback_min_pct"] == 0.005
    assert policy["pullback_max_pct"] == 0.03
    assert policy["reclaim_tolerance_pct"] == 0.002
    assert any("max_extended_from_vwap_pct:percent_unit_normalized" in issue for issue in issues)
