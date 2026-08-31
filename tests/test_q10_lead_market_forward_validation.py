from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from libs.reporting.baseline_samsung_hynix.forward_validation.contracts import EXPERIMENT_GUARDS
from libs.reporting.baseline_samsung_hynix.forward_validation.expected_actual import classify_reaction
from libs.reporting.baseline_samsung_hynix.forward_validation.market_inputs import flatten_signal_inputs
from libs.reporting.baseline_samsung_hynix.forward_validation.pipeline import (
    build_q10_forward_validation,
    capture_q10_preopen_snapshot,
)
from libs.reporting.baseline_samsung_hynix.forward_validation.reaction_reader import build_actual_reactions
from libs.reporting.baseline_samsung_hynix.forward_validation.scoring import (
    classify_hynix_extension,
    score_korea_market_state,
    score_semiconductor_signal,
)
from libs.reporting.baseline_samsung_hynix.forward_validation.shadow_comparison import build_shadow_comparison


KST = timezone(timedelta(hours=9))


class FixtureProvider:
    def __init__(self) -> None:
        self.calls = 0

    def capture(self, *, as_of: datetime):
        self.calls += 1
        def row(value: float, previous: float = 100.0):
            return {"status": "AVAILABLE", "current": previous * (1 + value / 100), "previous": previous, "return_pct": value}
        return {
            "sox": row(5.5), "nvidia": row(3.0), "micron": row(2.0),
            "hynix_adr": row(1.0), "nasdaq": row(1.0), "sp500": row(0.8),
            "nasdaq100_futures_0850": {**row(0.5), "previous_close": 100.0},
            "sp500_futures_0850": {**row(0.4), "previous_close": 100.0},
            "usdkrw_0850": {**row(-0.3), "previous_close": 100.0},
            "us10y": row(-0.1, 4.0), "vix": row(-6.0),
            "sk_hynix": {**row(2.0, 200000.0), "three_day_return_pct": 9.0},
            "samsung": row(1.0, 80000.0),
        }


def _epoch(day: str, hhmm: str) -> int:
    return int(datetime.combine(date.fromisoformat(day), time.fromisoformat(hhmm), tzinfo=KST).timestamp())


def _candles(day: str, start: float) -> list[dict]:
    values = {"09:00": start, "09:03": start * 1.01, "09:05": start * 1.005, "09:10": start * 1.02,
              "09:15": start * 1.025, "09:30": start * 1.03, "10:00": start * 1.04, "15:20": start * 1.05}
    return [
        {"ts": _epoch(day, label), "open": price, "high": price * 1.001, "low": price * .999,
         "close": price, "volume": 1000 + index}
        for index, (label, price) in enumerate(values.items())
    ]


def test_frozen_semiconductor_and_market_scoring() -> None:
    inputs = {
        "sox_return_pct": 5.1, "nvidia_return_pct": 2.0, "micron_return_pct": 1.0,
        "hynix_adr_return_pct": 0.5, "nasdaq100_futures_0850_return_pct": -0.5,
        "usdkrw_0850_change_pct": 0.4,
    }
    hynix = score_semiconductor_signal(inputs)
    samsung = score_semiconductor_signal(inputs, samsung=True)
    assert hynix["state"] == "STRONG_POSITIVE"
    assert samsung["score"] < hynix["score"]
    assert hynix["confidence"] == "LOW"
    assert classify_hynix_extension({"hynix_3d_cumulative_return_pct": 8.1})["state"] == "EXTENDED"
    market = score_korea_market_state({
        "nasdaq_return_pct": 1.0, "sp500_return_pct": 1.0, "sox_return_pct": 4.0,
        "nasdaq100_futures_0850_return_pct": 0.5, "sp500_futures_0850_return_pct": 0.5,
        "usdkrw_0850_change_pct": -0.5, "us10y_yield_change": -0.1, "vix_change_pct": -6.0,
    })
    assert market["state"] == "STRONG_RISK_ON"


def test_us10y_change_is_normalized_to_percentage_points() -> None:
    ordinary = flatten_signal_inputs({"us10y": {"current": 4.66, "previous": 4.63}})
    scaled = flatten_signal_inputs({"us10y": {"current": 46.6, "previous": 46.3}})
    assert ordinary["us10y_yield_change"] == 0.03
    assert scaled["us10y_yield_change"] == 0.03
    assert ordinary["us10y_yield_change_unit"] == "percentage_point"


def test_reaction_classification_is_deterministic() -> None:
    assert classify_reaction(expected_state="POSITIVE", opening_gap_pct=0.2) == "UNDERREACTION"
    assert classify_reaction(expected_state="POSITIVE", opening_gap_pct=2.0) == "OVERREACTION"
    assert classify_reaction(expected_state="POSITIVE", opening_gap_pct=-0.5) == "DIVERGENCE"


def test_pipeline_is_prospective_and_preopen_snapshot_is_immutable(tmp_path: Path) -> None:
    provider = FixtureProvider()
    not_active = build_q10_forward_validation(
        day="2026-08-28", output_dir=tmp_path / "old", state_path=tmp_path / "state.json",
        macro_root=tmp_path / "macro", candle_map={}, cost_pct=.28, slippage_pct=.05,
        now=datetime(2026, 8, 28, 8, 50, tzinfo=KST), lead_market_provider=provider,
    )
    assert not_active["q10_forward_validation_status"] == "NOT_ACTIVE_PROSPECTIVE_ONLY"
    assert provider.calls == 0

    output = tmp_path / "reports" / "2026-08-31"
    first = build_q10_forward_validation(
        day="2026-08-31", output_dir=output, state_path=tmp_path / "state.json",
        macro_root=tmp_path / "macro", candle_map={}, cost_pct=.28, slippage_pct=.05,
        now=datetime(2026, 8, 31, 8, 50, 10, tzinfo=KST), lead_market_provider=provider,
    )
    second = build_q10_forward_validation(
        day="2026-08-31", output_dir=output, state_path=tmp_path / "state.json",
        macro_root=tmp_path / "macro", candle_map={}, cost_pct=.28, slippage_pct=.05,
        now=datetime(2026, 8, 31, 8, 55, tzinfo=KST), lead_market_provider=provider,
    )
    assert first["q10_forward_validation_status"] == "CAPTURED"
    assert second["q10_forward_validation_status"] == "CAPTURED"
    assert provider.calls == 1
    snapshot = json.loads(Path(first["q10_preopen_snapshot"]).read_text(encoding="utf-8"))
    assert snapshot["signals"]["hynix_extension"]["state"] == "EXTENDED"
    assert snapshot["guards"] == EXPERIMENT_GUARDS


def test_dedicated_q10_preopen_capture_writes_canonical_snapshot(tmp_path: Path) -> None:
    provider = FixtureProvider()
    result = capture_q10_preopen_snapshot(
        day="2026-08-31",
        reports_root=tmp_path / "reports",
        state_path=tmp_path / "state.json",
        now=datetime(2026, 8, 31, 8, 50, 5, tzinfo=KST),
        lead_market_provider=provider,
    )

    assert result["q10_preopen_capture_status"] == "CAPTURED"
    assert provider.calls == 1
    path = Path(result["path"])
    assert path.name == "q10_preopen_signal_snapshot.json"
    assert json.loads(path.read_text(encoding="utf-8"))["capture_status"] == "CAPTURED"


def test_missed_capture_is_not_backfilled(tmp_path: Path) -> None:
    provider = FixtureProvider()
    result = build_q10_forward_validation(
        day="2026-08-31", output_dir=tmp_path / "2026-08-31", state_path=tmp_path / "state.json",
        macro_root=tmp_path / "macro", candle_map={}, cost_pct=.28, slippage_pct=.05,
        now=datetime(2026, 8, 31, 9, 1, tzinfo=KST), lead_market_provider=provider,
    )
    assert result["q10_forward_validation_status"] == "MISSED"
    assert provider.calls == 0


def test_actual_reaction_and_shadow_metrics(tmp_path: Path) -> None:
    day = "2026-08-31"
    reactions = build_actual_reactions(
        day=day,
        candle_map={"005930": _candles(day, 81000), "000660": _candles(day, 202000)},
        macro_root=tmp_path,
        signal_inputs={"samsung_previous_close": 80000, "hynix_previous_close": 200000},
    )
    assert reactions["targets"]["samsung"]["opening_gap_pct"] == 1.25
    assert reactions["targets"]["sk_hynix"]["points"]["CLOSE"]["status"] == "OBSERVED"
    expected = {"rows": [
        {"target": "samsung", "expected_state": "POSITIVE", "reaction_state": "FAIR_REACTION"},
        {"target": "sk_hynix", "expected_state": "POSITIVE", "reaction_state": "FAIR_REACTION"},
    ]}
    shadow = build_shadow_comparison(expected_actual=expected, reactions=reactions, cost_pct=.28, slippage_pct=.05)
    row = next(item for item in shadow["outcomes"] if item["target"] == "samsung" and item["policy"] == "ENTRY_0900")
    assert row["status"] == "OBSERVED"
    assert row["net_eod_return_pct"] == 4.67
    serialized = json.dumps(shadow)
    assert "OrderIntent" not in serialized
    assert "executor" not in serialized.lower()
