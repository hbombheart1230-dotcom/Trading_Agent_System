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
