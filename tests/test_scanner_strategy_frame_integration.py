from __future__ import annotations

from graphs.nodes.scanner_node import _apply_scanner_guidance_weights, _extract_scanner_guidance


def test_scanner_playbook_additively_changes_weights():
    base = {
        "trading_value": 0.20,
        "momentum": 0.22,
        "trend": 0.20,
        "volume_surge": 0.14,
        "intraday_strength": 0.12,
        "theme_boost": 0.06,
        "sentiment": 0.06,
        "volatility_penalty": 0.10,
        "gap_penalty": 0.07,
        "open_order_penalty": 0.04,
    }
    breakout = _apply_scanner_guidance_weights(
        dict(base),
        playbook="breakout",
        scanner_bias="momentum",
        scanner_priority=["momentum", "trend_strength"],
        trade_aggressiveness="high",
        risk_tone="aggressive",
    )
    defensive = _apply_scanner_guidance_weights(
        dict(base),
        playbook="defensive",
        scanner_bias="large_cap",
        scanner_priority=["liquidity", "risk_penalty"],
        trade_aggressiveness="low",
        risk_tone="conservative",
    )

    assert breakout["momentum"] > defensive["momentum"]
    assert defensive["volatility_penalty"] > breakout["volatility_penalty"]
    assert defensive["trading_value"] >= base["trading_value"]


def test_scanner_extract_guidance_reads_strategist_output_contract():
    state = {
        "strategist_output": {
            "themes": ["semiconductor", "ai"],
            "avoid_themes": ["biotech_smallcap"],
            "playbook": "breakout",
            "scanner_bias": "momentum",
            "scanner_priority": ["momentum", "trend_strength"],
            "scanner_source_policy": {
                "include_change_rate": True,
                "preferred_sources": ["top_change_rate", "condition_search"],
            },
            "trade_aggressiveness": "high",
            "risk_tone": "aggressive",
        }
    }
    out = _extract_scanner_guidance(state)

    assert out["themes"] == ["semiconductor", "ai"]
    assert out["avoid_themes"] == ["biotech_smallcap"]
    assert out["playbook"] == "breakout"
    assert out["scanner_bias"] == "momentum"
    assert out["scanner_priority"] == ["momentum", "trend_strength"]
    assert out["scanner_source_policy"]["include_change_rate"] is True
    assert out["scanner_source_policy"]["preferred_sources"] == ["top_change_rate", "condition_search"]
    assert out["trade_aggressiveness"] == "high"
    assert out["risk_tone"] == "aggressive"
