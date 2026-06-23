from __future__ import annotations

from libs.reporting.evaluation.horizon_alignment import _combo_rows


def _row(day: str, symbol: str, gross: float) -> dict:
    return {
        "symbol": symbol,
        "quant_tactic_id": "volume_breakout",
        "shadow_role": "top_pick",
        "_payload_generated_at": f"{day}T00:00:00+00:00",
        "entry_lane_observation": {
            "time_bucket": "open_20_60m",
            "primary_lane": "volume_confirmation",
            "market_regime_rail": "mixed_neutral",
        },
        "shadow_forward_base": {
            "baseline_raw_ts": day.replace("-", "") + "093000",
        },
        "shadow_forward_outcome": {
            "checkpoints": {
                "+30m": {"status": "observed", "return_pct": gross},
            }
        },
    }


def test_combo_requires_cost_positive_robust_sample() -> None:
    rows = []
    for index in range(24):
        day = f"2026-06-{16 + (index % 4):02d}"
        rows.append(_row(day, f"{index % 8:06d}", 2.5))
    result = _combo_rows(
        rows,
        dimensions=("time_bucket", "tactic"),
        cost_pct=1.0,
    )
    thirty = next(row for row in result if row["horizon"] == "+30m")
    assert thirty["evidence_eligible"] is True
    assert thirty["cost_positive"] is True
    assert thirty["robust_across_days"] is True
    assert thirty["decision"] == "CONTROLLED_ADOPTION_CANDIDATE"


def test_combo_rejects_gross_positive_but_cost_negative() -> None:
    rows = []
    for index in range(24):
        day = f"2026-06-{16 + (index % 4):02d}"
        rows.append(_row(day, f"{index % 8:06d}", 0.5))
    result = _combo_rows(
        rows,
        dimensions=("time_bucket", "tactic"),
        cost_pct=1.0,
    )
    thirty = next(row for row in result if row["horizon"] == "+30m")
    assert thirty["evidence_eligible"] is True
    assert thirty["cost_positive"] is False
    assert thirty["decision"] == "REJECT_COST_NEGATIVE"


def test_combo_retains_day_concentrated_positive_result_for_observation() -> None:
    rows = []
    for index in range(24):
        day_number = 16 + (index % 4)
        gross = 4.0 if day_number == 16 else 0.8
        rows.append(_row(f"2026-06-{day_number:02d}", f"{index % 8:06d}", gross))
    result = _combo_rows(
        rows,
        dimensions=("time_bucket", "tactic"),
        cost_pct=1.0,
    )
    thirty = next(row for row in result if row["horizon"] == "+30m")
    assert thirty["evidence_eligible"] is True
    assert thirty["average_net_return_pct"] > 0
    assert thirty["robust_across_days"] is False
    assert thirty["cost_positive"] is False
    assert thirty["decision"] == "RETAIN_UNDER_OBSERVATION"
