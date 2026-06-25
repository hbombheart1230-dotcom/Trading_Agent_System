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


def test_fixed_target_symbol() -> None:
    decision = build_decision_snapshot(
        day="2026-06-25",
        as_of_epoch=1782347400,
        woori_candles=_candles(),
        btc_signals=_btc(),
    )

    assert decision["target"]["symbol"] == TARGET_SYMBOL
    assert decision["target"]["ticker"] == "041190.KQ"


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
    )
    decisions = json.loads(Path(result["decisions"]).read_text(encoding="utf-8"))
    forward = json.loads(Path(result["forward_returns"]).read_text(encoding="utf-8"))

    assert decisions["schema_version"] == DECISIONS_SCHEMA
    assert forward["schema_version"] == FORWARD_SCHEMA
    assert decisions["fixed_target"] == "041190.KQ"
    for row in decisions["decisions"]:
        assert row["order_execution_allowed"] is False
        assert row["order_intent"] is None
        assert "execution" not in row
        assert row["entry_rule_count"] <= 3
        assert row["exit_rule_count"] <= 2

