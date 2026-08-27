from __future__ import annotations

from libs.reporting.evaluation.stage2_authority.builder import (
    build_stage2_authority_records,
    build_stage2_authority_review,
)
from libs.reporting.evaluation.stage2_authority.deep_dive import (
    build_stage2_effectiveness_deep_dive,
)


def _row(decision_id: str, role: str, symbol: str, value: float) -> dict:
    return {
        "q9_decision_id": decision_id,
        "q9_decision_role": role,
        "rank": 1,
        "symbol": symbol,
        "day": "2026-08-27",
        "shadow_forward_outcome": {
            "checkpoints": {"+30m": {"status": "observed", "return_pct": value}}
        },
    }


def test_stage2_authority_decomposes_candidate_change_and_tightening() -> None:
    decision_id = "Q9_20260827_RUN1"
    records = build_stage2_authority_records(
        candidate_rows=[
            _row(decision_id, "R1_PRE_REFRESH_SCANNER", "005930", 1.0),
            _row(decision_id, "R2_POST_REFRESH_SCANNER", "000660", -0.5),
        ],
        windows={
            decision_id: {
                "run_id": "RUN1",
                "commander_final": {"no_trade": True, "reason": "risk_too_high"},
            }
        },
        responses={
            ("2026-08-27", "RUN1"): {
                "artifact_path": "response.json",
                "parsed": {
                    "selected_symbol_decision": "watch_rank1_with_tighter_gates",
                    "entry_policy_delta": {"tighten_confidence_threshold": True},
                    "commander_actionability": "policy_delta_allowed",
                },
            }
        },
    )

    assert len(records) == 1
    assert records[0]["candidate_changed"] is True
    assert records[0]["entry_tightening"] is True
    assert records[0]["delta_pct"] == -1.5


def test_stage2_authority_does_not_promote_concentrated_degrading_signal() -> None:
    records = []
    for index in range(20):
        records.append(
            {
                "day": f"2026-08-{25 + (index % 2):02d}",
                "candidate_changed": True,
                "delta_pct": -0.5,
                "after_return_pct": -0.4,
                "entry_tightening": True,
                "no_trade_recommended": True,
                "downstream_no_trade": True,
                "stage2_response_available": True,
            }
        )
    review = build_stage2_authority_review(start="2026-08-25", end="2026-08-26", records=records)

    assert review["authorities"]["rerank"]["state"] == "DEGRADING"
    assert review["authorities"]["candidate_change"]["advisory_candidate_eligible"] is False
    assert review["authorities"]["candidate_change"]["promotion_eligibility"]["state"] == "INSUFFICIENT_STABILITY"
    assert review["authorities"]["entry_tightening"]["state"] == "NOT_MEASURABLE"
    assert review["authorities"]["no_trade"]["advisory_candidate_eligible"] is False


def test_stage2_authority_promotes_distributed_consistent_degrading_signal() -> None:
    records = []
    for index in range(50):
        records.append(
            {
                "day": f"2026-08-{18 + (index % 5):02d}",
                "candidate_changed": True,
                "delta_pct": -0.5,
                "after_return_pct": -0.4,
                "stage2_response_available": True,
            }
        )
    review = build_stage2_authority_review(start="2026-08-18", end="2026-08-22", records=records)

    candidate = review["authorities"]["candidate_change"]
    assert candidate["state"] == "DEGRADING"
    assert candidate["promotion_eligibility"]["state"] == "ELIGIBLE"
    assert candidate["advisory_candidate_eligible"] is True


def test_stage2_authority_excludes_unlinked_refresh_from_authority_decision() -> None:
    records = [
        {
            "day": "2026-08-25" if index < 10 else "2026-08-26",
            "candidate_changed": True,
            "delta_pct": -1.0,
            "after_return_pct": -0.5,
            "stage2_response_available": False,
        }
        for index in range(20)
    ]
    review = build_stage2_authority_review(start="2026-08-25", end="2026-08-26", records=records)

    assert review["authorities"]["refresh_pipeline_all"]["comparison_count"] == 20
    assert review["authorities"]["refresh_pipeline_all"]["state"] == "OBSERVATIONAL_ONLY"
    assert review["authorities"]["rerank"]["comparison_count"] == 0
    assert review["authorities"]["rerank"]["state"] == "NOT_MEASURABLE"


def test_stage2_deep_dive_separates_consensus_and_candidate_change() -> None:
    records = [
        {
            "day": "2026-08-26",
            "stage2_response_available": True,
            "candidate_changed": False,
            "before_symbol": "005930",
            "after_symbol": "005930",
            "horizon_returns": {
                "+30m": {"before_return_pct": 1.0, "after_return_pct": 1.0, "delta_pct": 0.0}
            },
            "before_candidate": {
                "sources": ["top_value"],
                "entry_lane": {"time_bucket": "open_0_20m", "market_regime_rail": "risk_on"},
                "market_metrics": {"kospi_pct": 1.2, "kosdaq_pct": 0.8},
            },
            "stage2": {
                "selected_symbol_decision": "watch_rank1",
                "target_symbol": "005930",
                "watch_intensity": "normal",
                "memory_effect": "supportive",
            },
        },
        {
            "day": "2026-08-27",
            "stage2_response_available": True,
            "candidate_changed": True,
            "before_symbol": "005930",
            "after_symbol": "000660",
            "horizon_returns": {
                "+30m": {"before_return_pct": 0.8, "after_return_pct": -0.2, "delta_pct": -1.0}
            },
            "before_candidate": {
                "sources": ["top_value", "top_volume"],
                "entry_lane": {"time_bucket": "open_0_20m", "market_regime_rail": "mixed_neutral"},
                "market_metrics": {"kospi_pct": 0.1, "kosdaq_pct": -0.1},
            },
            "stage2": {
                "selected_symbol_decision": "watch_rank1_with_tighter_gates",
                "target_symbol": "005930",
                "watch_intensity": "strict",
                "memory_effect": "cautionary",
            },
        },
    ]

    result = build_stage2_effectiveness_deep_dive(
        start="2026-08-26", end="2026-08-27", records=records
    )

    assert result["coverage"]["same_symbol_records"] == 1
    assert result["coverage"]["changed_symbol_records"] == 1
    changed = result["changed_symbol_by_horizon"]["+30m"]
    assert changed["before_average_return_pct"] == 0.8
    assert changed["after_average_return_pct"] == -0.2
    assert changed["average_delta_pct"] == -1.0
    target_rows = result["dimensions"]["target_alignment"]["candidate_changed_only"]
    assert target_rows[0]["value"] == "target_matches_r1"
