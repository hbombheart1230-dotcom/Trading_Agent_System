from __future__ import annotations

from datetime import datetime, timedelta, timezone

from libs.runtime.same_symbol_loss_reentry import (
    evaluate_same_symbol_loss_reentry,
    record_same_symbol_exit,
)
from libs.runtime.monitor_entry_blockers import evaluate_entry_guard


KST = timezone(timedelta(hours=9))


def _epoch(day: str, hour: int = 10) -> int:
    return int(datetime.fromisoformat(f"{day}T{hour:02d}:00:00").replace(tzinfo=KST).timestamp())


def _sell(*, pnl_ratio: float, partial: bool = False) -> dict:
    return {
        "order": {
            "action": "SELL",
            "symbol": "005930",
            "qty": 10,
            "meta": {
                "pnl_ratio": pnl_ratio,
                "partial_exit": partial,
                "exit_qty": 10,
                "position_qty": 20 if partial else 10,
                "exit_reason": "confirmed_exit_signal",
            },
        }
    }


def test_full_loss_exit_blocks_only_same_symbol_on_same_day() -> None:
    persisted: dict = {}
    now = _epoch("2026-07-29")

    recorded = record_same_symbol_exit(persisted, _sell(pnl_ratio=-0.012), now_epoch=now)
    blocked = evaluate_same_symbol_loss_reentry(
        {"persisted_state": persisted},
        symbol="005930",
        now_epoch=now + 3600,
    )
    other = evaluate_same_symbol_loss_reentry(
        {"persisted_state": persisted},
        symbol="000660",
        now_epoch=now + 3600,
    )

    assert recorded["recorded"] is True
    assert recorded["outcome"] == "LOSS"
    assert blocked["blocked"] is True
    assert blocked["reason"] == "same_symbol_loss_reentry_blocked"
    assert other["blocked"] is False


def test_profit_exit_does_not_block_reentry() -> None:
    persisted: dict = {}
    now = _epoch("2026-07-29")
    record_same_symbol_exit(persisted, _sell(pnl_ratio=0.004), now_epoch=now)

    result = evaluate_same_symbol_loss_reentry(
        {"persisted_state": persisted},
        symbol="005930",
        now_epoch=now + 60,
    )

    assert result["blocked"] is False
    assert result["prior_exit"]["outcome"] == "NON_LOSS"


def test_partial_loss_exit_does_not_create_control() -> None:
    persisted: dict = {}
    result = record_same_symbol_exit(
        persisted,
        _sell(pnl_ratio=-0.02, partial=True),
        now_epoch=_epoch("2026-07-29"),
    )

    assert result == {"recorded": False, "reason": "partial_exit"}
    assert "same_symbol_loss_reentry_control_by_symbol" not in persisted


def test_prior_day_loss_does_not_block_new_trading_day() -> None:
    persisted: dict = {}
    record_same_symbol_exit(
        persisted,
        _sell(pnl_ratio=-0.02),
        now_epoch=_epoch("2026-07-29", 15),
    )

    result = evaluate_same_symbol_loss_reentry(
        {"persisted_state": persisted},
        symbol="005930",
        now_epoch=_epoch("2026-07-30", 9),
    )

    assert result["blocked"] is False
    assert result["prior_exit"] == {}


def test_unknown_pnl_is_recorded_but_does_not_block() -> None:
    persisted: dict = {}
    execution = {
        "order": {
            "action": "SELL",
            "symbol": "005930",
            "qty": 10,
            "meta": {"position_qty": 10, "exit_qty": 10},
        }
    }
    now = _epoch("2026-07-29")
    recorded = record_same_symbol_exit(persisted, execution, now_epoch=now)
    result = evaluate_same_symbol_loss_reentry(
        {"persisted_state": persisted},
        symbol="005930",
        now_epoch=now + 60,
    )

    assert recorded["outcome"] == "UNKNOWN"
    assert result["blocked"] is False


def test_entry_guard_marks_loss_reentry_as_symbol_specific() -> None:
    result = evaluate_entry_guard(
        entry_info={},
        entry_quality_gate={},
        entry_cost_filter={},
        selected_already_held=False,
        selected_pending_buy=False,
        max_positions_reached=False,
        closeout_window_active=False,
        buy_blocked_post_exit_cooldown=False,
        entry_intent_cooldown_sec=0,
        cooldown_until=0,
        now_epoch=1,
        forced_entry_block_reason="same_symbol_loss_reentry_blocked",
    )

    assert result["entry_guard_blocked"] is True
    assert result["buy_blocked_same_symbol"] is True
    assert result["buy_blocked_open_position"] is False
