from __future__ import annotations

import json
from pathlib import Path

from libs.research.integrated_trade_diagnosis.lineage import build_lineage
from libs.research.integrated_trade_diagnosis.pipeline import (
    run_integrated_trade_diagnosis,
)
from libs.research.integrated_trade_diagnosis.policies import (
    opening_policy_rows,
    opening_policy_summary,
    reentry_policy_summary,
)
from libs.research.integrated_trade_diagnosis.read_model import (
    build_symbol_day_sequences,
)
from libs.research.integrated_trade_diagnosis.validation import (
    prospective_validation,
)


def test_lineage_preserves_stage_changes() -> None:
    result = build_lineage(
        {
            "symbol": "C",
            "selection": {
                "q9_decision_id": "Q9-1",
                "raw_scanner_top1": {"symbol": "A"},
                "post_strategist_top10": [{"symbol": "B"}],
                "selected_symbol": "B",
            },
        }
    )

    assert result["confidence"] == "EXACT"
    assert result["consistent"] is False
    assert [row["reason"] for row in result["transitions"]] == [
        "STRATEGY_CONTEXT_CHANGED",
        "EXECUTION_OR_MAPPING_DIFFERENCE",
    ]


def test_opening_policy_is_deterministic_and_point_in_time() -> None:
    row = {
        "decision_id": "D1",
        "day": "2026-07-01",
        "symbol": "A",
        "decision_from_open_sec": 120,
        "playbook": "breakout",
        "above_vwap": True,
        "completed_bar_count_before_decision": 1,
        "precompleted_return_1m_pct": 1.0,
        "opening_relative_volume": 1.2,
        "entry_vs_prior_close_pct": 2.0,
        "intrinsic_30m_net_pct": 3.0,
        "monitor_candidate_30m_net_pct": -1.0,
        "monitor_intent": "BUY",
        "commander_decision": "approve",
    }

    first = opening_policy_rows([row])
    second = opening_policy_rows([dict(row)])
    assert first == second
    assert {item["policy"] for item in first if item["would_enter"]} == {
        "CURRENT_PIPELINE",
        "OPENING_PROBE",
        "WAIT_CONFIRM",
        "NO_CHASE",
    }
    summary = opening_policy_summary(first)
    assert summary["OPENING_PROBE"]["performance"]["average_return_pct"] == 3.0
    assert summary["CURRENT_PIPELINE"]["performance"]["average_return_pct"] == -1.0


def test_opening_policy_does_not_require_unused_vwap_evidence() -> None:
    rows = opening_policy_rows(
        [
            {
                "decision_id": "D1",
                "day": "2026-08-04",
                "symbol": "A",
                "decision_from_open_sec": 60,
                "playbook": "breakout",
                "above_vwap": None,
                "entry_vs_prior_close_pct": 2.0,
                "intrinsic_30m_net_pct": 1.0,
            }
        ]
    )

    assert all(row["rule_evidence_status"] == "COMPLETE" for row in rows)
    assert next(row for row in rows if row["policy"] == "OPENING_PROBE")[
        "would_enter"
    ] is True


def test_sequence_counterfactual_does_not_infer_fresh_episode() -> None:
    sequences = build_symbol_day_sequences(
        [
            {"day": "2026-07-01", "symbol": "A", "trade_id": "T1", "entry_timestamp": "09:00", "net_return_pct": 2.0},
            {"day": "2026-07-01", "symbol": "A", "trade_id": "T2", "entry_timestamp": "10:00", "net_return_pct": -1.5},
        ]
    )
    result = reentry_policy_summary(sequences)

    assert sequences[0]["profit_giveback_pct"] == 1.5
    assert result["CURRENT"]["performance"]["average_return_pct"] == 0.5
    assert result["STOP_AFTER_FIRST_EXIT"]["performance"]["average_return_pct"] == 2.0
    assert result["FRESH_EPISODE_ONLY"]["evidence_status"] == "INSUFFICIENT_EVIDENCE"


def test_pipeline_writes_strict_reconstructable_artifacts(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    trade_dir = reports / "evaluation" / "trades" / "2026-07-01" / "T1"
    trade_dir.mkdir(parents=True)
    (trade_dir / "trade_read_model.json").write_text(
        json.dumps(
            {
                "schema_version": "q9_trade_read_model.v1",
                "trade_id": "T1",
                "day": "2026-07-01",
                "symbol": "A",
                "status": "closed",
                "entry": {"timestamp": "2026-07-01T00:01:00+00:00", "price": 100},
                "exit": {"timestamp": "2026-07-01T00:31:00+00:00", "price": 101},
                "outcome": {"net_return_pct": 0.72, "holding_seconds": 1800},
                "selection": {"q9_decision_id": "D1", "raw_scanner_top1": {"symbol": "A"}},
            }
        ),
        encoding="utf-8",
    )
    (trade_dir / "trade_evaluation.json").write_text("{}", encoding="utf-8")
    longitudinal = tmp_path / "longitudinal.json"
    longitudinal.write_text(
        json.dumps(
            {
                "stage_rows": [
                    {
                        "decision_id": "D1",
                        "day": "2026-07-01",
                        "symbol": "A",
                        "decision_from_open_sec": 60,
                        "playbook": "breakout",
                        "above_vwap": True,
                        "intrinsic_30m_net_pct": 1.0,
                    }
                ],
                "events": [],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    paths = run_integrated_trade_diagnosis(
        reports_root=reports,
        longitudinal_path=longitudinal,
        output_root=output,
        start_day="2026-06-01",
        end_day="2026-07-31",
    )

    summary = json.loads(Path(paths["summary"]).read_text(encoding="utf-8"))
    assert summary["evidence_coverage"]["trade_row_count"] == 1
    assert summary["runtime_validation_contract"]["required_full_trading_days"] == 3
    assert Path(paths["report"]).exists()


def test_prospective_validation_accepts_no_trade_observation_day() -> None:
    stage = {"day": "2026-08-03", "decision_id": "D1"}
    stage["forward_30m_status"] = "observed"
    policies = [
        {"day": "2026-08-03", "policy": policy}
        for policy in ("CURRENT_PIPELINE", "OPENING_PROBE", "WAIT_CONFIRM", "NO_CHASE")
    ]
    result = prospective_validation(
        stage_rows=[stage],
        opening_rows=policies,
        trade_rows=[],
        start_day="2026-08-03",
    )

    assert result["valid_day_count"] == 1
    assert result["days"][0]["status"] == "VALID"


def test_prospective_validation_inherits_opening_artifact_failure() -> None:
    stage = {
        "day": "2026-08-05",
        "decision_id": "D1",
        "forward_30m_status": "observed",
    }
    policies = [
        {"day": "2026-08-05", "policy": policy}
        for policy in ("CURRENT_PIPELINE", "OPENING_PROBE", "WAIT_CONFIRM", "NO_CHASE")
    ]

    result = prospective_validation(
        stage_rows=[stage],
        opening_rows=policies,
        trade_rows=[],
        start_day="2026-08-03",
        opening_day_statuses={"2026-08-05": "ARTIFACT_INCOMPLETE"},
    )

    assert result["valid_day_count"] == 0
    assert result["days"][0]["status"] == "INVALID"
    assert result["days"][0]["defects"] == [
        "opening_shadow_status:ARTIFACT_INCOMPLETE"
    ]
