from datetime import datetime, timezone, timedelta

from graphs.pipelines.m13_tick import run_m13_tick
from libs.runtime.market_hours import MarketHours

KST = timezone(timedelta(hours=9))

def test_tick_skips_when_market_closed():
    state = {"decision_packet": {"intent": {"action": "NOOP"}, "risk": {}, "exec_context": {}}}
    dt = datetime(2026, 2, 14, 12, 0, tzinfo=KST)  # Sat
    out = run_m13_tick(state, dt=dt, market_hours=MarketHours(), run_m10=lambda s: {**s, "ran_m10": True})
    assert out["tick_skipped"] is True
    assert "ran_m10" not in out

def test_tick_runs_when_market_open():
    state = {"m13_tick_pipeline": "legacy_m10", "ran_m10": False}
    dt = datetime(2026, 2, 13, 10, 0, tzinfo=KST)  # Fri 10:00
    def fake_m10(s):
        s["ran_m10"] = True
        return s
    out = run_m13_tick(state, dt=dt, market_hours=MarketHours(), run_m10=fake_m10)
    assert out["tick_skipped"] is False
    assert out["ran_m10"] is True


def test_tick_defaults_to_integrated_chain_when_market_open():
    state = {"ran_chain": False}
    dt = datetime(2026, 2, 13, 10, 0, tzinfo=KST)  # Fri 10:00

    def fake_integrated(s):
        s["ran_chain"] = True
        return s

    out = run_m13_tick(state, dt=dt, market_hours=MarketHours(), run_integrated=fake_integrated)
    assert out["tick_skipped"] is False
    assert out["tick_pipeline"] == "integrated_chain"
    assert out["ran_chain"] is True


def test_tick_runs_integrated_chain_when_selected():
    state = {"m13_tick_pipeline": "integrated_chain", "ran_chain": False}
    dt = datetime(2026, 2, 13, 10, 0, tzinfo=KST)  # Fri 10:00

    def fake_m10(s):
        s["ran_m10"] = True
        return s

    def fake_integrated(s):
        s["ran_chain"] = True
        return s

    out = run_m13_tick(
        state,
        dt=dt,
        market_hours=MarketHours(),
        run_m10=fake_m10,
        run_integrated=fake_integrated,
    )
    assert out["tick_skipped"] is False
    assert out["tick_pipeline"] == "integrated_chain"
    assert out["ran_chain"] is True
    assert "ran_m10" not in out
