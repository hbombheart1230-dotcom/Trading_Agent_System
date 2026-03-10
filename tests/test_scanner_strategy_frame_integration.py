from __future__ import annotations

from graphs.nodes.scanner_node import _apply_scanner_guidance_weights


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
