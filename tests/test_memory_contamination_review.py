from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.memory_review import build_memory_contamination_review
from libs.reporting.evaluation.memory_review.classifier import classify_stage2_row
from libs.reporting.evaluation.memory_review.contracts import (
    INSUFFICIENT_MEMORY_EVIDENCE,
    MEMORY_CLEAN,
    STALE_OR_CONTRADICTORY_MEMORY,
    SYMBOL_MEMORY_MISMATCH,
)
from libs.reporting.evaluation.memory_review.forward import build_forward_comparison


def _stage2(run_id: str, target: str) -> dict:
    return {
        "run_id": run_id,
        "day": "2026-08-12",
        "timestamp": "2026-08-12T00:03:00+00:00",
        "target_symbol": target,
        "selected_symbol_decision": "watch_rank1_with_tighter_gates",
        "entry_policy_delta": {"tighten_confidence_threshold": True},
        "memory_usage": {"status": "used", "effect": "cautionary"},
    }


def _strategist(memory_symbol: str = "", *, stale: bool = False) -> dict:
    selected = {
        "present": bool(memory_symbol),
        "symbol": memory_symbol,
        "trade_count": 5 if memory_symbol else 0,
    }
    return {
        "memory_packet_visibility": {
            "selected_symbol_memory": selected,
            "strategy_memory": {
                "status": "ok",
                "requested_day": "2026-08-12",
                "resolved_day": "2026-08-01" if stale else "2026-08-11",
            },
        },
        "strategy_memory_snapshot": {
            "status": "ok",
            "requested_day": "2026-08-12",
            "resolved_day": "2026-08-01" if stale else "2026-08-11",
            "best_playbooks": ["opening_momentum"] if stale else [],
            "worst_playbooks": [],
        },
    }


def test_memory_review_classifier_separates_integrity_cohorts() -> None:
    clean = classify_stage2_row(
        _stage2("clean", "005930"),
        strategist=_strategist("005930"),
        q9_window={},
        trade_outcomes=[],
    )
    mismatch = classify_stage2_row(
        _stage2("mismatch", "001210"),
        strategist=_strategist("233740"),
        q9_window={},
        trade_outcomes=[],
    )
    stale = classify_stage2_row(
        _stage2("stale", "005930"),
        strategist=_strategist(stale=True),
        q9_window={},
        trade_outcomes=[],
    )
    insufficient = classify_stage2_row(
        _stage2("missing", "005930"),
        strategist={},
        q9_window={},
        trade_outcomes=[],
    )

    assert clean["cohort"] == MEMORY_CLEAN
    assert mismatch["cohort"] == SYMBOL_MEMORY_MISMATCH
    assert mismatch["symbol_consistent"] is False
    assert stale["cohort"] == STALE_OR_CONTRADICTORY_MEMORY
    assert stale["strategy_memory"]["age_days"] == 11
    assert insufficient["cohort"] == INSUFFICIENT_MEMORY_EVIDENCE


def test_memory_review_pipeline_writes_json_and_markdown(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    evidence_path = tmp_path / "events.jsonl"
    run_id = "run-memory-mismatch"
    event = {
        "run_id": run_id,
        "timestamp": "2026-08-12T00:03:00+00:00",
        "agent": "strategist",
        "stage": "theme_selection",
        "parsed_output": {
            "target_symbol": "001210",
            "selected_symbol_tactical_review": {
                "target_symbol": "001210",
                "target_rank": 1,
                "selected_symbol_decision": "watch_rank1_with_tighter_gates",
                "entry_policy_delta": {"tighten_confidence_threshold": True},
                "memory_usage": {"status": "used", "effect": "cautionary"},
            },
        },
    }
    evidence_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    strategist_path = reports_root / "canonical" / "2026-08-12" / run_id / "strategist.json"
    strategist_path.parent.mkdir(parents=True, exist_ok=True)
    strategist_path.write_text(json.dumps(_strategist("233740")), encoding="utf-8")
    q9_path = reports_root / "operator_summary" / "daily" / "2026-08-12" / "q9_decision_windows.json"
    q9_path.parent.mkdir(parents=True, exist_ok=True)
    q9_path.write_text(
        json.dumps(
            {
                "windows": [
                    {
                        "run_id": run_id,
                        "decision_id": "Q9_TEST",
                        "window_type": "scanner_selection",
                        "commander_final": {
                            "decision": "reject",
                            "veto": True,
                            "no_trade": True,
                            "reason": "risk_too_high",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output_root = tmp_path / "out"

    result = build_memory_contamination_review(
        reports_root=reports_root,
        evidence_path=evidence_path,
        start_day="2026-08-12",
        end_day="2026-08-12",
        output_root=output_root,
    )

    cohort = result["cohorts"][SYMBOL_MEMORY_MISMATCH]
    assert result["stage2_call_count"] == 1
    assert cohort["stage2_call_count"] == 1
    assert cohort["commander_veto_count"] == 1
    assert cohort["entry_policy_tightened_count"] == 1
    assert output_root.joinpath("memory_contamination_review.json").exists()
    markdown = output_root.joinpath("memory_contamination_review.md").read_text(encoding="utf-8")
    assert "SYMBOL_MEMORY_MISMATCH" in markdown
    assert "001210" in markdown
    assert "233740" in markdown


def test_memory_review_does_not_attribute_reused_run_trade_to_another_target() -> None:
    row = classify_stage2_row(
        _stage2("shared-run", "001210"),
        strategist=_strategist("233740"),
        q9_window={},
        trade_outcomes=[
            {
                "trade_id": "TRD_OTHER",
                "symbol": "005930",
                "net_return_pct": -1.0,
                "trusted_for_behavior": True,
            }
        ],
    )

    assert row["trusted_trade_count"] == 0
    assert row["trade_outcomes"][0]["memory_review_target_match"] is False
    assert row["trade_outcomes"][0]["trusted_for_memory_review"] is False


def _forward_candidate(decision_id: str, role: str, value: float, **extra: object) -> dict:
    return {
        "q9_decision_id": decision_id,
        "q9_decision_role": role,
        "rank": 1,
        "q9_selected": role == "B_STRATEGIST_RANKED",
        "shadow_forward_outcome": {
            "checkpoints": {
                "+5m": {"status": "observed", "return_pct": value},
            }
        },
        **extra,
    }


def test_memory_forward_comparison_keeps_clean_and_mismatch_separate() -> None:
    classified = [
        {
            "q9_decision_id": "Q9_CLEAN",
            "cohort": MEMORY_CLEAN,
            "commander_no_trade": False,
        },
        {
            "q9_decision_id": "Q9_BAD",
            "cohort": SYMBOL_MEMORY_MISMATCH,
            "commander_no_trade": True,
        },
    ]
    candidates = [
        _forward_candidate("Q9_CLEAN", "A_SCANNER_CONTROL", 1.0),
        _forward_candidate("Q9_CLEAN", "B_STRATEGIST_RANKED", 1.5),
        _forward_candidate("Q9_CLEAN", "C_COMMANDER_FINAL", 1.5),
        _forward_candidate("Q9_BAD", "A_SCANNER_CONTROL", 2.0),
        _forward_candidate("Q9_BAD", "B_STRATEGIST_RANKED", 1.0),
    ]

    result = build_forward_comparison(classified, candidates, cost_pct=0.28)
    clean = result["by_cohort"][MEMORY_CLEAN]["horizons"][0]
    mismatch = result["by_cohort"][SYMBOL_MEMORY_MISMATCH]["horizons"][0]

    assert clean["strategist_minus_scanner_avg_pct"] == 0.5
    assert clean["commander_minus_strategist_avg_pct"] == 0.0
    assert mismatch["strategist_minus_scanner_avg_pct"] == -1.0
    assert mismatch["commander_policy_avg_net_return_pct"] == 0.0
    assert mismatch["commander_minus_strategist_avg_pct"] == -0.72
