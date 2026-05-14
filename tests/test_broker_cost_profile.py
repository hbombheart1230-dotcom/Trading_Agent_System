from __future__ import annotations

import json
from pathlib import Path

import pytest

from libs.read.kiwoom_day_pnl_reader import _normalize_percent
from libs.runtime.broker_cost_profile import (
    apply_broker_cost_profile_to_exit_policy,
    update_broker_cost_profile_from_execution_details,
)


def test_kiwoom_percent_profit_rate_is_normalized_as_api_percent() -> None:
    assert _normalize_percent("-0.49") == pytest.approx(-0.0049)


def test_update_broker_cost_profile_persists_observed_kiwoom_costs(tmp_path: Path) -> None:
    path = tmp_path / "broker_cost_profile.json"

    profile = update_broker_cost_profile_from_execution_details(
        {
            "symbol": "005930",
            "filled_qty": 10,
            "filled_price": 295500,
            "broker_buy_price": 291975,
            "broker_fee": 20550,
            "broker_tax": 5909,
            "pnl_truth_source": "kiwoom.ka10077",
        },
        path=path,
        now_epoch=123.0,
    )

    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == profile
    assert profile["source"] == "kiwoom.ka10077"
    assert profile["fee_rate_on_gross_notional"] == pytest.approx(20550 / (2919750 + 2955000))
    assert profile["tax_rate_on_sell_notional"] == pytest.approx(5909 / 2955000)
    assert profile["last_round_trip_cost_pct"] == pytest.approx((20550 + 5909) / 2919750)


def test_apply_broker_cost_profile_raises_profit_floor_without_lowering_existing_policy() -> None:
    profile = {
        "source": "kiwoom.ka10077",
        "updated_epoch": 123.0,
        "sample_count": 1,
        "conservative_round_trip_cost_pct": 0.00906,
    }

    out = apply_broker_cost_profile_to_exit_policy(
        {
            "round_trip_cost_floor_pct": 0.004,
            "min_net_profit_buffer_pct": 0.003,
            "cost_aware_profit_floor_pct": 0.006,
        },
        profile=profile,
    )

    assert out["cost_aware_profit_floor_enabled"] is True
    assert out["round_trip_cost_floor_pct"] == pytest.approx(0.00906)
    assert out["cost_aware_profit_floor_pct"] == pytest.approx(0.01206)
    assert out["broker_cost_profile_source"] == "kiwoom.ka10077"


def test_apply_broker_cost_profile_keeps_more_conservative_policy() -> None:
    out = apply_broker_cost_profile_to_exit_policy(
        {
            "round_trip_cost_floor_pct": 0.012,
            "min_net_profit_buffer_pct": 0.003,
            "cost_aware_profit_floor_pct": 0.016,
        },
        profile={"conservative_round_trip_cost_pct": 0.009},
    )

    assert out["round_trip_cost_floor_pct"] == pytest.approx(0.012)
    assert out["cost_aware_profit_floor_pct"] == pytest.approx(0.016)
