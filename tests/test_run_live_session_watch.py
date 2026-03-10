from __future__ import annotations

from scripts.run_live_session_watch import evaluate_watch_health


def _summary(
    *,
    window_total: int = 10,
    llm_total: int = 10,
    llm_error_rate: float = 0.0,
    verdict_total: int = 10,
    blocked_total: int = 2,
    executed_broker_fail_total: int = 0,
) -> dict:
    return {
        "events": {"window_total": int(window_total)},
        "strategist_llm": {"total": int(llm_total), "error_rate": float(llm_error_rate)},
        "execution": {
            "verdict_total": int(verdict_total),
            "blocked_total": int(blocked_total),
            "executed_broker_fail_total": int(executed_broker_fail_total),
        },
    }


def test_live_watch_health_green_when_loop_alive_and_recent_events() -> None:
    out = evaluate_watch_health(
        _summary(),
        loop_alive=True,
        event_lag_sec=40,
        max_event_lag_sec=420,
    )
    assert out["status"] == "GREEN"


def test_live_watch_health_yellow_when_llm_error_rate_high() -> None:
    out = evaluate_watch_health(
        _summary(llm_total=8, llm_error_rate=0.5),
        loop_alive=True,
        event_lag_sec=45,
        max_event_lag_sec=420,
    )
    assert out["status"] == "YELLOW"
    assert any("llm_error_rate_high" in str(x) for x in out["reasons"])


def test_live_watch_health_red_when_loop_not_alive() -> None:
    out = evaluate_watch_health(
        _summary(),
        loop_alive=False,
        event_lag_sec=30,
        max_event_lag_sec=420,
    )
    assert out["status"] == "RED"
    assert "loop_not_alive" in out["reasons"]


def test_live_watch_health_red_when_event_lag_exceeds_threshold() -> None:
    out = evaluate_watch_health(
        _summary(),
        loop_alive=True,
        event_lag_sec=900,
        max_event_lag_sec=420,
    )
    assert out["status"] == "RED"
    assert any("event_lag_exceeded" in str(x) for x in out["reasons"])
