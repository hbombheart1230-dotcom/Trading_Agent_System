from __future__ import annotations

from libs.runtime.monitor_exit.position_tracking import update_position_peak_price
from libs.runtime.monitor_exit.price_resolution import resolve_price_with_source


def test_cross_symbol_price_cannot_update_position_peak() -> None:
    state = {"run_id": "incident", "tick_ts": 1000, "persisted_state": {}}
    peak = update_position_peak_price(
        state,
        "251340",
        avg_price=2525.0,
        observed_price=8830.0,
        observed_price_symbol="004310",
        observed_price_source="monitor_output.current_price",
    )
    assert peak == 2525.0
    assert state["persisted_state"]["position_peak_price"]["251340"] == 2525.0
    assert state["peak_update_events"][-1]["accepted"] is False
    assert state["peak_update_events"][-1]["candidate_price_symbol"] == "004310"


def test_same_symbol_valid_price_updates_position_peak() -> None:
    state = {"run_id": "valid", "tick_ts": 1001, "persisted_state": {}}
    peak = update_position_peak_price(
        state,
        "251340",
        avg_price=2525.0,
        observed_price=2600.0,
        observed_price_symbol="251340",
        observed_price_source="market.quote.price",
    )
    assert peak == 2600.0
    assert state["peak_update_events"][-1]["accepted"] is True


def test_position_price_row_with_different_symbol_is_rejected() -> None:
    price, source = resolve_price_with_source(
        {},
        "251340",
        None,
        position={"symbol": "004310", "current_price": 8830.0},
    )
    assert price is None
    assert source == "unavailable"
