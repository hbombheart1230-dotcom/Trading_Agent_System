from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.trade_symbol_integrity import repair_trade_symbol_artifacts


def test_repair_trade_symbol_artifacts_reanchors_authoritative_contexts(
    tmp_path: Path,
) -> None:
    trade_dir = tmp_path / "TRD_20260625_005930_01"
    trade_dir.mkdir()
    scanner = {
        "selected_symbol": "000660",
        "selected_rank": 1,
        "selected_score": 1.01,
        "confidence": 0.80,
        "ranked_candidates": [
            {"symbol": "000660", "rank": 1, "score_total": 1.01, "confidence": 0.80},
            {"symbol": "005930", "rank": 2, "score_total": 0.79, "confidence": 0.62},
        ],
    }
    (trade_dir / "entry.json").write_text(
        json.dumps({"symbol": "005930", "scanner_context": scanner}),
        encoding="utf-8",
    )
    (trade_dir / "lifecycle_bundle.json").write_text(
        json.dumps(
            {
                "symbol": "005930",
                "entry": {"scanner_context": scanner},
                "lifecycle": {"entry": {"scanner_context": scanner}},
                "scanner_reason_human": scanner,
            }
        ),
        encoding="utf-8",
    )

    result = repair_trade_symbol_artifacts(trade_dir)
    lifecycle = json.loads(
        (trade_dir / "lifecycle_bundle.json").read_text(encoding="utf-8")
    )

    assert result["changed"] is True
    for context in (
        lifecycle["entry"]["scanner_context"],
        lifecycle["lifecycle"]["entry"]["scanner_context"],
        lifecycle["scanner_reason_human"],
    ):
        assert context["selected_symbol"] == "005930"
        assert context["scanner_selected_symbol"] == "000660"
        assert context["selected_rank"] == 2
        assert context["selected_score"] == 0.79
        assert context["confidence"] == 0.62
