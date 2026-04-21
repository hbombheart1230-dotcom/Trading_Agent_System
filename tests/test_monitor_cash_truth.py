from graphs.nodes.monitor_node import _resolve_cash


def test_resolve_cash_prefers_capital_available_for_sizing():
    state = {
        "risk_context": {"capital_available_for_sizing": 321000.0},
        "portfolio_snapshot": {"cash": 999999.0},
    }

    assert _resolve_cash(state) == 321000.0
