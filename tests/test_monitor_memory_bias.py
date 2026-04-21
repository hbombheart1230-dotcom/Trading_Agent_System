from __future__ import annotations

from graphs.nodes.monitor_node import monitor_node
from libs.runtime.monitor_memory_bias import (
    apply_monitor_memory_bias_to_entry_policy,
    build_monitor_memory_bias,
    summarize_monitor_memory_bias,
)


def test_build_monitor_memory_bias_surfaces_daily_and_symbol_rules() -> None:
    bias = build_monitor_memory_bias(
        commander_memory_policy={
            "active_layers": ["daily", "symbol"],
            "monitor_bias_enabled": True,
            "symbol_memory_override_enabled": True,
        },
        memory_packets={
            "daily_strategy_memory": {
                "active": True,
                "best_playbooks": ["defensive"],
                "worst_playbooks": ["breakout"],
                "recent_failures": ["breakout_chase_failed", "volume_confirmation_failed"],
            },
            "symbol_memory_packet": {
                "active": True,
                "dominant_playbook": "pullback",
                "dominant_monitor_blocker": "below_vwap_reclaim_not_ready",
            },
        },
    )

    assert bias["enabled"] is True
    assert bias["risk_posture"] == "defensive"
    assert bias["entry_policy_delta"]["breakout_buffer_pct"] > 0.0
    assert bias["entry_policy_delta"]["volume_ratio_min"] > 0.0
    assert bias["entry_policy_delta"]["max_extended_from_vwap_pct"] < 0.0
    summary = summarize_monitor_memory_bias(bias)
    assert summary["entry_delta_keys"] == [
        "breakout_buffer_pct",
        "max_extended_from_vwap_pct",
        "volume_ratio_min",
    ]


def test_apply_monitor_memory_bias_to_entry_policy_clamps_and_marks_adjustments() -> None:
    result = apply_monitor_memory_bias_to_entry_policy(
        entry_policy={
            "volume_ratio_min": 1.48,
            "max_extended_from_vwap_pct": 0.035,
            "breakout_buffer_pct": 0.0295,
            "adjustments": ("frame_adjusted",),
            "policy_source": "monitor_entry_policy.v1",
        },
        monitor_memory_bias={
            "enabled": True,
            "entry_policy_delta": {
                "volume_ratio_min": 0.08,
                "max_extended_from_vwap_pct": -0.02,
                "breakout_buffer_pct": 0.005,
            },
        },
    )

    policy = result["policy"]
    assert result["applied"] is True
    assert float(policy["volume_ratio_min"]) == 1.5
    assert float(policy["max_extended_from_vwap_pct"]) == 0.03
    assert float(policy["breakout_buffer_pct"]) == 0.03
    assert "commander_memory_bias" in tuple(policy.get("adjustments") or ())
    assert len(result["deltas"]) == 3


def test_monitor_node_applies_commander_monitor_memory_bias(monkeypatch) -> None:
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    captured: dict[str, object] = {}

    def _fake_entry(rows, current_price, features, policy, scoring, frame, policy_contract):
        captured["policy"] = policy.to_dict()
        return {
            "enabled": True,
            "evaluated": True,
            "triggered": False,
            "reason": "too_extended_from_vwap",
            "thresholds": {"intent_cooldown_sec": 0},
            "metrics": {"current_price": current_price},
            "applied_policy": policy.to_dict(),
            "failed_checks": ["extension_ok"],
            "passed_checks": [],
        }

    monkeypatch.setattr("graphs.nodes.monitor_node.evaluate_intraday_entry_signal", _fake_entry)
    monkeypatch.setattr(
        "graphs.nodes.monitor_node._resolve_entry_closeout_window_guard",
        lambda state, policy: {"active": False, "minutes_to_close": 120, "cutoff_min": 10},
    )

    state = {
        "plan": {"thesis": "memory bias monitor"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "minute_ohlcv_by_symbol": {
            "BBB": [
                {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
                {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
                {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
                {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
                {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
                {"open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 900, "vwap": 101.2},
            ]
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": {"use_exit_policy": False, "monitor_policy": {"entry_intent_cooldown_sec": 0}},
        "strategist_output": {
            "playbook": "defensive",
            "monitor_guidance": "defensive_exit",
            "risk_tone": "conservative",
            "trade_aggressiveness": "low",
            "strategy_policy": {
                "market_policy": {},
                "scanner_policy": {},
                "monitor_policy": {
                    "applied_policy": {
                        "timeframe_minutes": 1,
                        "volume_ratio_min": 0.68,
                        "max_extended_from_vwap_pct": 0.13,
                        "breakout_buffer_pct": 0.0,
                        "pullback_min_pct": 0.008,
                        "pullback_max_pct": 0.07,
                        "reclaim_tolerance_pct": 0.0015,
                        "intent_cooldown_sec": 0,
                        "require_vwap_reclaim": True,
                        "require_rebound": True,
                        "policy_source": "strategist",
                    },
                    "policy_source": "strategist",
                    "monitor_memory_bias": {
                        "enabled": True,
                        "active_layers": ["daily", "symbol"],
                        "entry_policy_delta": {
                            "volume_ratio_min": 0.03,
                            "max_extended_from_vwap_pct": -0.01,
                            "breakout_buffer_pct": 0.0015,
                        },
                        "risk_posture": "defensive",
                        "bias_source": "commander_memory_bias.v1",
                        "reason": ["daily_breakout_quality_weak"],
                    },
                },
                "decision_policy": {},
                "commander_context": {},
            },
        },
    }

    out = monitor_node(state)
    monitor = out.get("monitor") or {}
    output = out.get("monitor_output") or {}
    effective_policy = monitor.get("entry_effective_policy") or {}
    memory_deltas = list(output.get("monitor_memory_bias_deltas") or [])

    assert monitor.get("monitor_memory_bias_applied") is True
    assert monitor.get("entry_received_policy", {}).get("volume_ratio_min") == 0.68
    assert any((row or {}).get("field") == "volume_ratio_min" and round(float((row or {}).get("to") or 0.0), 2) == 0.71 for row in memory_deltas)
    assert any((row or {}).get("field") == "max_extended_from_vwap_pct" and round(float((row or {}).get("to") or 0.0), 2) == 0.12 for row in memory_deltas)
    assert any((row or {}).get("field") == "breakout_buffer_pct" and round(float((row or {}).get("to") or 0.0), 4) == 0.0015 for row in memory_deltas)
    assert float(effective_policy.get("volume_ratio_min") or 0.0) >= 0.71
    assert float(effective_policy.get("max_extended_from_vwap_pct") or 0.0) <= 0.12
    assert monitor.get("entry_effective_policy_source") == "monitor_memory_bias_adjusted"
    assert "commander_memory_bias" in list(monitor.get("entry_effective_policy_source_chain") or [])
    assert output.get("effective_policy_source") == "monitor_memory_bias_adjusted"
    assert output.get("monitor_memory_bias_applied") is True
    assert any((row or {}).get("field") == "volume_ratio_min" for row in memory_deltas)
    assert float((captured.get("policy") or {}).get("volume_ratio_min") or 0.0) == float(effective_policy.get("volume_ratio_min") or 0.0)
