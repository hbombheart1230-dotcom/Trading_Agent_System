from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.baseline_btc_woori_tech.contracts import (
    DECISIONS_SCHEMA,
    FORWARD_SCHEMA,
    TARGET_SYMBOL,
)
from libs.reporting.baseline_btc_woori_tech.forward_returns import (
    attach_forward_returns,
    summarize,
)
from libs.reporting.baseline_btc_woori_tech.pipeline import (
    build_baseline_btc_woori_artifacts,
)
from libs.reporting.baseline_btc_woori_tech.strategy import (
    build_decision_snapshot,
)
from libs.reporting.baseline_btc_woori_tech.data_provider import signal_at


def _candles(*, start: int = 1782345600, count: int = 61) -> list[dict]:
    rows = []
    for index in range(count):
        price = 1000.0 + (index * 2.0)
        rows.append(
            {
                "ts": start + (index * 60),
                "raw_ts": f"2026062509{index:02d}00",
                "open": price,
                "high": price + 2.0,
                "low": price - 1.0,
                "close": price,
                "volume": 500.0 if index == 30 else 100.0,
            }
        )
    return rows


def _btc(*, start: int = 1782345600, positive: bool = True) -> dict:
    step = 0.1 if positive else -0.1
    rows = [
        {
            "ts": start + (index * 60),
            "raw_ts": f"2026062509{index:02d}00",
            "price": 100.0 + (index * step),
            "momentum_5m_pct": 0.5 if positive else -0.5,
            "source": "fixture",
        }
        for index in range(6, 61)
    ]
    return {
        "available": True,
        "available_sources": ["btc_usd"],
        "sources": {"btc_usd": rows},
        "fallback_reason": "",
    }


def _fear_greed() -> dict:
    return {
        "schema_version": "q12_crypto_fear_greed.v1",
        "available": True,
        "source": "fixture",
        "day": "2026-06-25",
        "observed_day": "2026-06-25",
        "observed_at": "2026-06-25T09:00:00+09:00",
        "value": 72,
        "classification": "Greed",
        "regime": "greed",
        "fallback_reason": "",
        "behavior_effect": "observation_only",
    }


def test_fixed_target_symbol() -> None:
    decision = build_decision_snapshot(
        day="2026-06-25",
        as_of_epoch=1782347400,
        woori_candles=_candles(),
        btc_signals=_btc(),
        crypto_fear_greed=_fear_greed(),
    )

    assert decision["target"]["symbol"] == TARGET_SYMBOL
    assert decision["target"]["ticker"] == "041190.KQ"
    assert decision["crypto_fear_greed"]["value"] == 72
    assert decision["crypto_fear_greed_behavior_effect"] == "observation_only"


def test_btc_signal_unavailable_fallback() -> None:
    decision = build_decision_snapshot(
        day="2026-06-25",
        as_of_epoch=1782347400,
        woori_candles=_candles(),
        btc_signals={
            "available": False,
            "available_sources": [],
            "sources": {},
            "fallback_reason": "btc_and_crypto_proxy_unavailable",
        },
    )

    assert decision["eligible"] is False
    assert decision["action"] == "NO_ENTRY"
    assert decision["reason"] == "btc_signal_unavailable"


def test_deterministic_decision() -> None:
    kwargs = {
        "day": "2026-06-25",
        "as_of_epoch": 1782347400,
        "woori_candles": _candles(),
        "btc_signals": _btc(),
    }

    assert build_decision_snapshot(**kwargs) == build_decision_snapshot(**kwargs)


def test_btc_signal_records_stale_proxy_without_changing_direct_signal() -> None:
    payload = _btc()
    payload["sources"]["coinbase_proxy"] = [
        {
            "ts": 1782345600,
            "raw_ts": "20260625090000",
            "price": 100.0,
            "momentum_5m_pct": -5.0,
            "source": "fixture:stale_proxy",
        }
    ]
    decision = build_decision_snapshot(
        day="2026-06-25",
        as_of_epoch=1782347400,
        woori_candles=_candles(),
        btc_signals=payload,
    )

    assert decision["btc_signal"]["positive"] is True
    assert decision["btc_signal"]["stale_sources"] == ["coinbase_proxy"]
    assert decision["btc_signal"]["freshness_warning"] == "stale_sources_present"


def test_btc_regime_timeframes_are_observation_only() -> None:
    payload = _btc()
    for row in payload["sources"]["btc_usd"]:
        row.update(
            {
                "momentum_15m_pct": 0.8,
                "momentum_60m_pct": 1.5,
                "momentum_24h_pct": 6.0,
                "momentum_since_krx_open_pct": 3.0,
            }
        )

    signal = signal_at(payload, epoch=1782347400)

    assert signal["momentum_60m_pct"] == 1.5
    assert signal["momentum_24h_pct"] == 6.0
    assert signal["momentum_since_krx_open_pct"] == 3.0
    assert signal["market_regime"] == "strong_bull"
    assert signal["market_regime_behavior_effect"] == "observation_only"
    assert signal["leading_positive"] is True


def test_strong_btc_regime_allows_a_shallow_five_minute_pullback() -> None:
    payload = _btc()
    for row in payload["sources"]["btc_usd"]:
        row.update(
            {
                "momentum_5m_pct": -0.1,
                "momentum_15m_pct": 0.6,
                "momentum_60m_pct": 1.2,
                "momentum_24h_pct": 5.0,
                "momentum_since_krx_open_pct": 2.0,
            }
        )
    decision = build_decision_snapshot(
        day="2026-06-25",
        as_of_epoch=1782347400,
        woori_candles=_candles(),
        btc_signals=payload,
    )

    assert decision["btc_signal"]["positive"] is False
    assert decision["btc_signal"]["leading_positive"] is True
    assert decision["btc_signal"]["leading_signal_reason"] == "bull_regime_short_pullback"
    assert decision["entry_conditions"]["btc_multihorizon_leading_signal_positive"] is True
    assert decision["behavior_effect"] == "shadow_only"


def test_strong_btc_regime_does_not_mask_a_sharp_five_minute_drop() -> None:
    payload = _btc()
    for row in payload["sources"]["btc_usd"]:
        row.update(
            {
                "momentum_5m_pct": -0.5,
                "momentum_15m_pct": 0.6,
                "momentum_60m_pct": 1.2,
                "momentum_24h_pct": 5.0,
            }
        )

    signal = signal_at(payload, epoch=1782347400)

    assert signal["market_regime"] == "strong_bull"
    assert signal["leading_positive"] is False


def test_cost_and_slippage_application() -> None:
    summary = summarize(
        [
            {
                "baseline_decision_id": "D1",
                "rank": 1,
                "eligible": True,
                "returns": {"+5m": {"status": "observed", "return_pct": 1.0}},
            }
        ],
        cost_pct=0.2,
        slippage_pct=0.1,
    )
    row = next(item for item in summary["horizons"] if item["horizon"] == "+5m")

    assert row["eligible_entries_gross"]["average_return_pct"] == 1.0
    assert row["eligible_entries_net"]["average_return_pct"] == 0.7


def test_forward_return_calculation() -> None:
    decision = build_decision_snapshot(
        day="2026-06-25",
        as_of_epoch=1782347400,
        woori_candles=_candles(),
        btc_signals=_btc(),
    )
    decision["generated_at"] = "2026-06-25T00:30:00+00:00"
    rows = attach_forward_returns([decision], candles=_candles())

    assert len(rows) == 1
    assert rows[0]["symbol"] == TARGET_SYMBOL
    assert rows[0]["returns"]["+5m"]["status"] == "observed"


def test_artifacts_have_no_order_intent_or_execution(tmp_path: Path) -> None:
    cost_path = tmp_path / "cost.json"
    cost_path.write_text(
        json.dumps({"conservative_round_trip_cost_pct": 0.002}),
        encoding="utf-8",
    )
    result = build_baseline_btc_woori_artifacts(
        day="2026-06-25",
        reports_root=tmp_path / "reports",
        state_path=tmp_path / "state.json",
        cost_profile_path=cost_path,
        q9_root=tmp_path / "q9",
        candles=_candles(),
        btc_signals=_btc(),
        crypto_fear_greed=_fear_greed(),
    )
    decisions = json.loads(Path(result["decisions"]).read_text(encoding="utf-8"))
    forward = json.loads(Path(result["forward_returns"]).read_text(encoding="utf-8"))

    assert decisions["schema_version"] == DECISIONS_SCHEMA
    assert forward["schema_version"] == FORWARD_SCHEMA
    assert decisions["fixed_target"] == "041190.KQ"
    assert decisions["crypto_fear_greed"]["regime"] == "greed"
    assert decisions["crypto_fear_greed_behavior_effect"] == "observation_only"
    for row in decisions["decisions"]:
        assert row["order_execution_allowed"] is False
        assert row["order_intent"] is None
        assert "execution" not in row
        assert row["entry_rule_count"] <= 3
        assert row["exit_rule_count"] <= 2
        assert row["crypto_fear_greed"]["classification"] == "Greed"
        assert row["crypto_fear_greed_behavior_effect"] == "observation_only"


def test_crypto_fear_greed_does_not_change_virtual_entry_rule() -> None:
    base_kwargs = {
        "day": "2026-06-25",
        "as_of_epoch": 1782347400,
        "woori_candles": _candles(),
        "btc_signals": _btc(),
    }
    greedy = build_decision_snapshot(
        **base_kwargs,
        crypto_fear_greed={**_fear_greed(), "value": 84, "classification": "Extreme Greed", "regime": "extreme_greed"},
    )
    fearful = build_decision_snapshot(
        **base_kwargs,
        crypto_fear_greed={**_fear_greed(), "value": 12, "classification": "Extreme Fear", "regime": "extreme_fear"},
    )

    assert greedy["entry_conditions"] == fearful["entry_conditions"]
    assert greedy["eligible"] == fearful["eligible"]
    assert greedy["action"] == fearful["action"]


def test_no_fresh_fetch_preserves_existing_market_observations(tmp_path: Path, monkeypatch) -> None:
    kwargs = {
        "day": "2026-06-25",
        "reports_root": tmp_path / "reports",
        "state_path": tmp_path / "state.json",
        "q9_root": tmp_path / "q9",
        "candles": _candles(),
        "btc_signals": _btc(),
    }
    build_baseline_btc_woori_artifacts(**kwargs, crypto_fear_greed=_fear_greed())
    monkeypatch.setattr(
        "libs.reporting.baseline_btc_woori_tech.pipeline.load_btc_signal_rows",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("fresh BTC fetch must not run")),
    )
    offline_kwargs = dict(kwargs)
    offline_kwargs.pop("btc_signals")
    result = build_baseline_btc_woori_artifacts(**offline_kwargs, allow_fresh_fetch=False)
    payload = json.loads(Path(result["decisions"]).read_text(encoding="utf-8"))

    assert payload["crypto_fear_greed"]["available"] is True
    assert payload["crypto_fear_greed"]["value"] == 72
    assert payload["btc_signal_availability"]["available"] is True
    assert any(row["btc_signal"]["available"] for row in payload["decisions"])
