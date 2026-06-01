from __future__ import annotations

from libs.reporting.quant_tactic_evaluation import (
    build_quant_tactic_evaluation,
    render_quant_tactic_evaluation_lines,
)


def _row(**overrides):
    row = {
        "trade_id": "TRD_20260522_005930_01",
        "symbol": "005930",
        "status": "closed",
        "quant_tactic_id": "vwap_reclaim_pullback",
        "quant_tactic_id_source": "entry_quant_decision",
        "entry_quant_decision": "entry_ready",
        "exit_quant_decision": "exit_aligned",
        "tactic_suitability_tier": "fit",
        "entry_quant_cost_floor_state": "met",
        "quant_tactic_mismatch_count": 0,
    }
    row.update(overrides)
    return row


def test_quant_tactic_evaluation_holds_when_sample_is_small() -> None:
    payload = build_quant_tactic_evaluation([_row()])

    assert payload["status"] == "hold_sample_insufficient"
    assert payload["live_trade_readiness"] == "hold_sample_insufficient"
    assert payload["promotion_action"] == "hold"
    assert payload["closed_or_realized_sample_count"] == 1
    assert payload["missing_required_fields"] == []
    assert "hold_sample_insufficient" in "\n".join(render_quant_tactic_evaluation_lines(payload))
    assert "live-trade readiness" in "\n".join(render_quant_tactic_evaluation_lines(payload))


def test_quant_tactic_evaluation_holds_for_invalid_broker_alignment_samples() -> None:
    rows = [_row(trade_id=f"TRD_20260522_005930_{idx:02d}") for idx in range(1, 21)]
    rows[0]["broker_alignment_status"] = "mismatch"
    rows[0]["broker_alignment_missing_in_local_total"] = 1

    payload = build_quant_tactic_evaluation(rows)

    assert payload["status"] == "hold_invalid_truth_samples"
    assert payload["raw_closed_or_realized_sample_count"] == 20
    assert payload["closed_or_realized_sample_count"] == 19
    assert payload["invalid_sample_count"] == 1
    assert payload["invalid_sample_examples"][0]["reason"] == "broker_alignment_mismatch"
    lines = "\n".join(render_quant_tactic_evaluation_lines(payload))
    assert "invalid 1" in lines
    assert "Quant Q8 invalid samples" in lines
    assert "TRD_20260522_005930_01/005930:broker_alignment_mismatch" in lines


def test_quant_tactic_evaluation_holds_for_field_gaps_and_tactic_mismatch() -> None:
    rows = [_row(trade_id=f"TRD_20260522_005930_{idx:02d}") for idx in range(1, 9)]
    rows[0]["quant_tactic_mismatch_count"] = 1
    rows[1]["entry_quant_cost_floor_state"] = ""

    mismatch_payload = build_quant_tactic_evaluation(rows)

    assert mismatch_payload["status"] == "hold_tactic_id_mismatch"
    assert mismatch_payload["tactic_id_mismatch_trade_count"] == 1
    assert mismatch_payload["missing_required_fields"] == ["entry_quant_cost_floor_state"]
    assert "Quant Q8 tactic mismatch examples" in "\n".join(render_quant_tactic_evaluation_lines(mismatch_payload))
    rows[0]["quant_tactic_mismatch_count"] = 0

    field_gap_payload = build_quant_tactic_evaluation(rows)

    assert field_gap_payload["status"] == "hold_field_gaps"
    assert field_gap_payload["field_gaps"][-1]["coverage"] == 0.875


def test_quant_tactic_evaluation_requires_manual_review_after_data_is_ready() -> None:
    rows = [_row(trade_id=f"TRD_20260522_005930_{idx:02d}") for idx in range(1, 21)]

    payload = build_quant_tactic_evaluation(rows)

    assert payload["status"] == "promotion_review_ready"
    assert payload["promotion_action"] == "manual_review"


def test_quant_tactic_evaluation_reports_exit_tactic_drift_without_holding_readiness() -> None:
    rows = [
        _row(
            trade_id=f"TRD_20260522_005930_{idx:02d}",
            quant_exit_tactic_drift_count=1 if idx <= 3 else 0,
        )
        for idx in range(1, 21)
    ]

    payload = build_quant_tactic_evaluation(rows)
    lines = "\n".join(render_quant_tactic_evaluation_lines(payload))

    assert payload["status"] == "promotion_review_ready"
    assert payload["tactic_id_mismatch_trade_count"] == 0
    assert payload["exit_tactic_drift_trade_count"] == 3
    assert "exit drift trades 3" in lines
