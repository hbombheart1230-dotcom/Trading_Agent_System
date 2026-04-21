from datetime import datetime, timedelta, timezone
from pathlib import Path

from libs.runtime.live_loop_runner import run_live_loop


KST = timezone(timedelta(hours=9))


def test_run_live_loop_once_invokes_runner_and_returns_zero(tmp_path: Path) -> None:
    calls = {"count": 0}

    def run_once_fn(state, dt=None):
        calls["count"] += 1
        state["last_dt"] = dt.isoformat()
        return state

    rc = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=True,
        sleep_sec=1,
        session_hard_gate=False,
        lock_path=tmp_path / "m13.lock",
        lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 9, 5, tzinfo=KST),
        run_once_fn=run_once_fn,
        sleep_fn=lambda _: None,
    )

    assert rc == 0
    assert calls["count"] == 1


def test_run_live_loop_blocks_when_market_closed(tmp_path: Path, capsys) -> None:
    class ClosedMarketHours:
        def is_open(self, dt):
            return False

    rc = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=True,
        sleep_sec=1,
        session_hard_gate=True,
        lock_path=tmp_path / "m13.lock",
        lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 18, 0, tzinfo=KST),
        run_once_fn=lambda state, dt=None: state,
        sleep_fn=lambda _: None,
        market_hours=ClosedMarketHours(),
    )

    assert rc == 5
    assert "market_closed" in capsys.readouterr().out


def test_run_live_loop_requires_symbol_for_legacy_pipeline(tmp_path: Path) -> None:
    try:
        run_live_loop(
            {"m13_tick_pipeline": "legacy_m10"},
            once=True,
            sleep_sec=1,
            session_hard_gate=False,
            lock_path=tmp_path / "m13.lock",
            lock_stale_sec=30,
            now_fn=lambda: datetime(2026, 4, 20, 9, 5, tzinfo=KST),
            run_once_fn=lambda state, dt=None: state,
            sleep_fn=lambda _: None,
        )
    except SystemExit as exc:
        assert "symbol is required for legacy_m10" in str(exc)
    else:
        raise AssertionError("expected SystemExit for missing legacy symbol")
