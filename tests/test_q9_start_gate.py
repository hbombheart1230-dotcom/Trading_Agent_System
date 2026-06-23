from __future__ import annotations

from libs.reporting.evaluation.start_gate import build_full_chain_start_gate
from libs.runtime.scanner.output_payloads import build_candidate_ranking_table_payload


def test_start_gate_rejects_reconstructed_scanner_baseline() -> None:
    model = {
        "trade_id": "TRD_1",
        "symbol": "005930",
        "entry": {"timestamp": "2026-06-22T00:01:00+00:00"},
        "exit": {"timestamp": "2026-06-22T00:10:00+00:00"},
        "selection": {
            "post_strategist_top10": [{"symbol": "005930"}],
            "reconstructed_pre_adjust_top10": [{"symbol": "000660"}],
            "raw_scanner_top10": [],
            "raw_scanner_snapshot_source": "",
            "strategist_run_id": "S1",
            "commander_final_explicit": False,
        },
        "monitor": {
            "entry_decision_count": 1,
            "exit_decision_count": 1,
            "post_exit": {
                "checkpoints": {
                    "+5m": {"status": "observed", "return_pct": 0.01},
                }
            },
        },
        "integrity": {"status": "PASS"},
        "baseline_versions": {
            "q8_contract": "q8.v1",
            "q9_contract": "q9.v1",
            "tactic_contract": "tactic.v1",
            "strategist_prompt": "prompt.v1",
            "cost_model": "cost.v1",
            "strategy_policy": "policy.v1",
        },
    }
    inventory = {
        "daily_artifacts": {
            "q9_decision_windows": {"exists": False},
        }
    }

    gate = build_full_chain_start_gate(
        models=[model],
        inventory=inventory,
        baseline_hash="abc123",
    )

    assert gate["status"] == "NOT_READY"
    assert gate["checks"]["raw_scanner_control_snapshot"] is False
    assert gate["trade_checks"][0]["reconstructed_scanner_snapshot_available"] is True
    assert "decision_window_inventory" in gate["missing"]


def test_scanner_payload_labels_pre_adjust_ranking_as_reconstructed() -> None:
    payload = build_candidate_ranking_table_payload([
        {
            "rank": 1,
            "symbol": "005930",
            "pre_adjust_score_total": 0.4,
            "post_adjust_score_total": 0.8,
            "confidence": 0.7,
            "risk_score": 0.3,
            "scanner_intrinsic_control_score_total": 0.2,
        },
        {
            "rank": 2,
            "symbol": "000660",
            "pre_adjust_score_total": 0.7,
            "post_adjust_score_total": 0.6,
            "confidence": 0.6,
            "risk_score": 0.4,
            "scanner_intrinsic_control_score_total": 0.9,
        },
    ])

    assert payload["post_strategist_top10"][0]["symbol"] == "005930"
    assert payload["reconstructed_pre_adjust_top10"][0]["symbol"] == "000660"
    assert payload["reconstructed_pre_adjust_evidence_class"] == "RECONSTRUCTED"
    assert "not a raw Scanner control" in payload["reconstructed_pre_adjust_limitation"]
    assert payload["scanner_intrinsic_control_top10"][0]["symbol"] == "000660"
    assert payload["scanner_intrinsic_control_source"] == "same_candidate_universe_ranking_only"
