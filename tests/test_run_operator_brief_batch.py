from __future__ import annotations

from scripts.run_operator_brief_batch import _normalize_trade_id_filters


def test_run_operator_brief_batch_normalizes_multiple_trade_id_filters() -> None:
    values = _normalize_trade_id_filters(
        ["TRD_A", "TRD_B,TRD_C", "TRD_B", "", "  TRD_D  "]
    )

    assert values == ["TRD_A", "TRD_B", "TRD_C", "TRD_D"]
