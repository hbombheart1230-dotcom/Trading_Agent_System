from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.operator_summary_mining import (
    build_operator_summary_mining,
    render_operator_summary_mining_markdown,
    write_operator_summary_mining,
)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_operator_summary_mining_separates_q9_overlap(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    daily = reports / "operator_summary" / "daily" / "2026-06-26"
    _write(daily / "daily_summary.json", {
        "schema_version": "operator_daily_summary.v1",
        "metrics": {"trade_count": 2, "closed_trade_count": 2, "win_rate": 0.5, "avg_return_pct": 0.1},
        "quant_shadow_candidate_evaluation": {
            "candidate_count": 20,
            "deduped_candidate_count": 10,
            "forward_outcome_coverage": 0.8,
        },
    })
    _write(daily / "operator_summary.json", {"schema_version": "operator_summary.v1"})
    _write(daily / "q8_shadow_blocker_review.json", {
        "candidate_count": 10,
        "evaluation_trust_gate": {"trusted_forward_count": 8, "promotion_allowed": False},
    })
    _write(daily / "q9_decision_windows.json", {
        "schema_version": "q9_decision_windows.v1",
        "window_count": 12,
        "windows": [{"decision_id": "a"}],
    })
    _write(daily / "trade_index.json", [{"trade_id": "t1"}, {"trade_id": "t2"}])

    weekly = reports / "operator_summary" / "weekly" / "2026-W26"
    _write(weekly / "weekly_summary.json", {
        "metrics": {"trade_count": 7},
        "pattern_performance": {"schema_version": "pattern_performance.v1"},
        "quant_tactic_evaluation": {"schema_version": "quant_tactic_evaluation.v1"},
        "quant_shadow_candidate_evaluation": {"schema_version": "quant_shadow_candidate_evaluation.v1"},
        "strategist_llm_evaluation": {"schema_version": "strategist_llm_evaluation.v1"},
    })

    symbol = reports / "operator_summary" / "symbols" / "005930"
    _write(symbol / "symbol_summary.json", {
        "metrics": {"trade_count": 6, "closed_trade_count": 5, "win_rate": 0.2, "avg_return_pct": -0.1},
        "pattern_performance": {},
        "quant_shadow_candidate_evaluation": {},
        "strategist_llm_evaluation": {},
    })

    result = build_operator_summary_mining(reports)

    assert result["schema_version"] == "operator_summary_mining.v1"
    assert result["daily_presence"]["presence_counts"]["q9_decision_windows"] == 1
    assert result["q9_overlap"]["q9_window_count_total"] == 12
    assert "weekly strategist_llm_evaluation" in result["q9_overlap"]["not_fully_consumed_by_q9"]
    assert result["weekly_quality"]["usable_week_count"] == 1
    assert result["symbol_quality"]["symbols_with_trade_count_ge_5"] == 1
    assert result["readiness"]["status"] in {"USABLE_WITH_GAPS", "USABLE", "WEAK", "NEEDS_REPAIR"}


def test_operator_summary_mining_writes_json_and_markdown(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    daily = reports / "operator_summary" / "daily" / "2026-06-26"
    _write(daily / "daily_summary.json", {"metrics": {"trade_count": 0}})
    _write(daily / "operator_summary.json", {})

    paths = write_operator_summary_mining(reports)
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    markdown = Path(paths["markdown"]).read_text(encoding="utf-8")

    assert payload["behavior_effect"] == "observation_only"
    assert "# Operator Summary Mining Report" in markdown
    assert "Not fully consumed by Q9" in render_operator_summary_mining_markdown(payload)
