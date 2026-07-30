from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.scanner_alignment_root_cause import (
    build_scanner_alignment_root_cause_range,
    build_scanner_alignment_root_cause_report,
)


def _row(
    trade_id: str,
    *,
    raw: str = "A",
    post: str = "A",
    selected: str = "A",
    executed: str = "A",
    final_changed: bool = False,
) -> dict:
    return {
        "trade_id": trade_id,
        "raw_scanner_top1": raw,
        "post_strategy_top1": post,
        "selected_symbol": selected,
        "executed_symbol": executed,
        "selected_to_monitor_changed": False,
        "monitor_to_commander_changed": False,
        "final_to_executed_changed": final_changed,
    }


def _model(trade_id: str, *, selected: str = "A", rank: int = 1, top: str = "A", ret: float = -0.5) -> dict:
    return {
        "trade_id": trade_id,
        "symbol": selected,
        "outcome": {"net_return_pct": ret},
        "selection": {
            "scanner_top1": {"symbol": top, "score_total": 1.0},
            "selected_symbol": selected,
            "selected_rank": rank,
            "selected_candidate": {"symbol": selected, "rank": rank, "score_total": 0.8},
        },
    }


def _evaluation(trade_id: str, ret: float) -> dict:
    return {"trade_id": trade_id, "realized_outcome": {"net_return_pct": ret}}


def test_scanner_alignment_root_cause_classifies_candidate_filtering() -> None:
    result = build_scanner_alignment_root_cause_report(
        day="2026-07-06",
        models=[_model("T1", selected="B", rank=2, top="A", ret=-1.0)],
        evaluations=[_evaluation("T1", -1.0)],
        selection_authority={"rows": [_row("T1", raw="A", post="A", selected="B", executed="B")]},
    )

    assert result["rows"][0]["root_cause"] == "Candidate Filtering"
    assert result["largest_root_cause"]["root_cause"] == "Candidate Filtering"
    assert "runner-up" in result["q15_behavior_patch_candidate"]


def test_scanner_alignment_root_cause_classifies_scanner_ranking_failure() -> None:
    result = build_scanner_alignment_root_cause_report(
        day="2026-07-06",
        models=[_model("T1", selected="A", rank=1, top="A", ret=-0.3)],
        evaluations=[_evaluation("T1", -0.3)],
        selection_authority={"rows": [_row("T1", raw="A", post="A", selected="A", executed="A")]},
    )

    assert result["rows"][0]["root_cause"] == "Scanner Ranking Failure"
    summary = {row["root_cause"]: row for row in result["cause_summary"]}
    assert summary["Scanner Ranking Failure"]["trade_count"] == 1
    assert summary["Scanner Ranking Failure"]["avg_return_pct"] == -0.3
    assert summary["Scanner Ranking Failure"]["diagnostic_kind"] == "outcome_conditioned"
    assert summary["Scanner Ranking Failure"]["causal_eligible"] is False
    assert result["rows"][0]["diagnostic_kind"] == "outcome_conditioned"
    assert result["largest_structural_root_cause"] == {}


def test_scanner_alignment_root_cause_identifies_structural_cause_separately() -> None:
    result = build_scanner_alignment_root_cause_report(
        day="2026-07-06",
        models=[
            _model("T1", selected="A", rank=1, top="A", ret=-0.3),
            _model("T2", selected="B", rank=2, top="A", ret=-0.2),
        ],
        evaluations=[
            _evaluation("T1", -0.3),
            _evaluation("T2", -0.2),
        ],
        selection_authority={
            "rows": [
                _row("T1", raw="A", post="A", selected="A", executed="A"),
                _row("T2", raw="A", post="A", selected="B", executed="B"),
            ]
        },
    )

    assert result["largest_behavior_root_cause"]["root_cause"] == "Scanner Ranking Failure"
    assert result["largest_structural_root_cause"]["root_cause"] == "Candidate Filtering"


def test_scanner_alignment_excludes_trade_absent_from_authority_audit() -> None:
    result = build_scanner_alignment_root_cause_report(
        day="2026-07-21",
        models=[_model("T1", selected="A", rank=1, top="A", ret=-0.92)],
        evaluations=[_evaluation("T1", -0.92)],
        selection_authority={
            "rows": [],
            "summary": {"excluded:confirmed_runtime_defect": 1},
        },
    )

    assert result["trade_count"] == 0
    assert result["largest_behavior_root_cause"] == {}


def test_scanner_alignment_root_cause_range_reads_daily_artifacts(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    daily = reports / "evaluation" / "daily" / "2026-07-06"
    trade = reports / "evaluation" / "trades" / "2026-07-06" / "T1"
    daily.mkdir(parents=True)
    trade.mkdir(parents=True)
    (daily / "selection_authority_audit.json").write_text(
        json.dumps({"rows": [_row("T1", raw="A", post="A", selected="B", executed="B")]}),
        encoding="utf-8",
    )
    (trade / "trade_read_model.json").write_text(
        json.dumps(_model("T1", selected="B", rank=2, top="A", ret=-1.0)),
        encoding="utf-8",
    )
    (trade / "trade_evaluation.json").write_text(json.dumps(_evaluation("T1", -1.0)), encoding="utf-8")

    result = build_scanner_alignment_root_cause_range(
        reports_root=reports,
        start="2026-07-06",
        end="2026-07-06",
    )

    assert result["trade_count"] == 1
    assert result["largest_root_cause"]["root_cause"] == "Candidate Filtering"
