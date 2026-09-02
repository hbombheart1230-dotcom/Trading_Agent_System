from __future__ import annotations

from libs.runtime.monitor_exit.observability import build_monitor_exit_payload
from libs.runtime.monitor_exit.preview import (
    _replace_stale_quote_with_position_price,
    preview_exit_decision_for_symbol,
)


def _hard_stop_decision(*, cached_quote: float, account_price: float, quote_age: int):
    now = 1_000
    return preview_exit_decision_for_symbol(
        state={
            "tick_ts": now,
            "skill_results": {
                "market.quote": {
                    "001210": {
                        "symbol": "001210",
                        "cur": cached_quote,
                        "_observed_epoch": now - quote_age,
                    }
                }
            },
        },
        symbol="001210",
        position={
            "symbol": "001210",
            "qty": 10,
            "avg_price": 13_830.0,
            "current_price": account_price,
            "hold_sec": 77,
        },
        selected={"symbol": "001210"},
        exit_policy_base={
            "hard_stop_pct": 0.02364,
            "stop_loss_pct": 0.08,
            "take_profit_pct": 0.20,
        },
    )


def test_77_second_cached_stop_is_cancelled_by_account_price() -> None:
    decision = _hard_stop_decision(
        cached_quote=13_130.0,
        account_price=13_530.0,
        quote_age=77,
    )

    assert decision["triggered"] is False
    assert decision["reason"] != "hard_stop"
    assert decision["effective_price"] == 13_530.0
    assert decision["_price"] == 13_530.0
    assert decision["_price_source"] == "position.current_price"
    assert decision["price_freshness"]["hard_stop_conflict_revalidation_applied"] is True
    assert decision["price_freshness"]["hard_stop_cached_quote_says_stop"] is True
    assert decision["price_freshness"]["hard_stop_account_price_says_stop"] is False


def test_77_second_cached_hold_is_replaced_by_account_hard_stop() -> None:
    decision = _hard_stop_decision(
        cached_quote=13_700.0,
        account_price=13_400.0,
        quote_age=77,
    )

    assert decision["triggered"] is True
    assert decision["reason"] == "hard_stop"
    assert decision["effective_price"] == 13_400.0
    assert decision["_price"] == 13_400.0
    assert decision["_price_source"] == "position.current_price"
    assert decision["price_freshness"]["hard_stop_conflict_revalidation_applied"] is True
    assert decision["price_freshness"]["hard_stop_cached_quote_says_stop"] is False
    assert decision["price_freshness"]["hard_stop_account_price_says_stop"] is True


def test_genuinely_fresh_aligned_quote_preserves_normal_stop_behavior() -> None:
    stop = _hard_stop_decision(
        cached_quote=13_400.0,
        account_price=13_400.0,
        quote_age=20,
    )
    hold = _hard_stop_decision(
        cached_quote=13_700.0,
        account_price=13_700.0,
        quote_age=20,
    )

    assert stop["reason"] == "hard_stop"
    assert stop["_price_source"].startswith("market.quote.")
    assert hold["triggered"] is False
    assert hold["_price_source"].startswith("market.quote.")


def test_stale_market_quote_is_replaced_by_live_position_price() -> None:
    price, source, evidence = _replace_stale_quote_with_position_price(
        state={"tick_ts": 1_000},
        symbol="001210",
        selected_for_exit={"_monitor_quote_observed_epoch": 800},
        position={"current_price": 13_530},
        price=13_130.0,
        price_source="market.quote.cur",
    )

    assert price == 13_530.0
    assert source == "position.current_price"
    assert evidence["quote_stale"] is True
    assert evidence["stale_quote_replaced"] is True


def test_fresh_market_quote_remains_authoritative() -> None:
    price, source, evidence = _replace_stale_quote_with_position_price(
        state={"tick_ts": 1_000},
        symbol="001210",
        selected_for_exit={"_monitor_quote_observed_epoch": 980},
        position={"current_price": 13_530},
        price=13_130.0,
        price_source="market.quote.cur",
    )

    assert price == 13_130.0
    assert source == "market.quote.cur"
    assert evidence["quote_stale"] is False
    assert evidence["stale_quote_replaced"] is False


def test_unstamped_divergent_market_quote_uses_position_price() -> None:
    price, source, evidence = _replace_stale_quote_with_position_price(
        state={"tick_ts": 1_000},
        symbol="001210",
        selected_for_exit={},
        position={"current_price": 13_530},
        price=13_130.0,
        price_source="market.quote.cur",
    )

    assert price == 13_530.0
    assert source == "position.current_price"
    assert evidence["quote_freshness_unverifiable"] is True
    assert evidence["stale_quote_replaced"] is True


def test_stale_market_quote_without_live_fallback_is_rejected() -> None:
    price, source, evidence = _replace_stale_quote_with_position_price(
        state={"tick_ts": 1_000},
        symbol="001210",
        selected_for_exit={"_monitor_quote_observed_epoch": 800},
        position={"avg_price": 13_830},
        price=13_130.0,
        price_source="market.quote.cur",
    )

    assert price is None
    assert source == "stale_market_quote_rejected"
    assert evidence["stale_quote_rejected"] is True


def test_exit_observability_preserves_price_freshness_evidence() -> None:
    decision = {
        "price_freshness": {
            "quote_stale": True,
            "stale_quote_replaced": True,
            "replacement_source": "position.current_price",
        }
    }

    artifact = build_monitor_exit_payload(
        decision=decision,
        features={},
        entry_info={},
        frame_applied={},
        eod_carry={},
        eod_carry_sweep={},
        effective_exit_policy_base={},
        decision_thresholds={},
        context={},
    )

    assert artifact["price_freshness"]["quote_stale"] is True
    assert artifact["price_freshness"]["replacement_source"] == "position.current_price"
