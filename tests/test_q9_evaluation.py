from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.contracts import EvidenceClass, validate_contract_payload
from libs.reporting.evaluation.metrics import performance_metrics
from libs.reporting.evaluation.pipeline import build_q9_evaluation
from libs.reporting.evaluation.trade_read_model import build_q9_trade_read_model


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_contract_rejects_invalid_evidence_class() -> None:
    try:
        validate_contract_payload({
            "contract_version": "q9_evaluation_contract.v1",
            "evidence_class": "BAD",
        })
    except ValueError:
        pass
    else:
        raise AssertionError("invalid evidence class must fail")
    assert EvidenceClass.REALIZED.value == "REALIZED"


def test_performance_metrics() -> None:
    result = performance_metrics([1.0, -0.5, 0.25])
    assert result["count"] == 3
    assert result["win_count"] == 2
    assert result["profit_factor"] == 2.5
    assert result["maximum_drawdown_pct"] == -0.5


def test_rolling_scorecard_preserves_trade_distribution() -> None:
    from libs.reporting.evaluation.rolling_scorecard import build_rolling_scorecard

    rows = []
    for day, samples in (("2026-06-18", [2.0, -1.0]), ("2026-06-19", [1.0] * 18)):
        rows.append({
            "day": day,
            "realized_performance": {
                "count": len(samples),
                "average_return_pct": sum(samples) / len(samples),
                "return_samples_pct": samples,
            },
            "artifact_integrity": {"status_counts": {"PASS": len(samples)}},
            "evaluation_phase": {
                "full_chain_start_gate": {"status": "READY"},
            },
        })
    result = build_rolling_scorecard(rows, window_days=5)
    assert result["realized_performance"]["count"] == 20
    assert result["realized_performance"]["win_count"] == 19
    assert result["realized_performance"]["loss_count"] == 1
    assert result["decision_class"] == "RETAIN"


def test_q9_pipeline_writes_read_only_outputs(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    trade = reports / "trades" / "2026-06-19" / "1400" / "TRD_1"
    _write(trade / "lifecycle_bundle.json", {
        "schema_version": "lifecycle_bundle.v1",
        "day": "2026-06-19",
        "trade_id": "TRD_1",
        "symbol": "005930",
        "lifecycle": {
            "status": "closed",
            "entry": {"timestamp": "2026-06-19T00:01:00+00:00", "price": 100, "qty": 1},
            "exit": {
                "timestamp": "2026-06-19T00:10:00+00:00",
                "price": 101,
                "qty": 1,
                "pnl": 1,
                "pnl_pct": 0.01,
            },
        },
    })
    for name in ("scanner", "strategist", "commander", "monitor"):
        _write(trade / "evidence" / f"{name}_evidence.json", {"schema_version": f"{name}.v1"})
    _write(trade / "entry.json", {"symbol": "005930"})
    daily = reports / "operator_summary" / "daily" / "2026-06-19"
    _write(daily / "daily_summary.json", {"schema_version": "operator_daily_summary.v1"})
    _write(daily / "q8_shadow_blocker_review.json", {
        "candidate_count": 10,
        "evaluation_trust_gate": {
            "trusted_forward_count": 9,
            "trusted_forward_coverage": 0.9,
            "promotion_allowed": False,
        },
    })

    result = build_q9_evaluation(reports, "2026-06-19")
    scorecard = json.loads(Path(result["daily_scorecard"]).read_text(encoding="utf-8"))
    assert scorecard["schema_version"] == "daily_scorecard.v1"
    assert scorecard["realized_performance"]["count"] == 1
    assert scorecard["realized_performance"]["average_return_pct"] == 1.0
    assert scorecard["selection_attribution"]["comparison_count"] == 0
    assert scorecard["decision_class"] == "INSUFFICIENT_EVIDENCE"
    assert scorecard["evaluation_phase"]["q8_status"] == "CLOSED"
    assert scorecard["evaluation_phase"]["full_chain_start_gate"]["status"] == "NOT_READY"
    assert Path(result["full_chain_start_gate"]).exists()
    assert (reports / "evaluation" / "trades" / "2026-06-19" / "TRD_1" / "trade_evaluation.json").exists()


def test_open_trade_exit_placeholder_is_not_realized(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    trade = reports / "trades" / "2026-06-19" / "1400" / "TRD_OPEN"
    _write(trade / "lifecycle_bundle.json", {
        "day": "2026-06-19",
        "trade_id": "TRD_OPEN",
        "symbol": "005930",
        "entry": {"ts": "2026-06-19T00:01:00+00:00", "price": 100, "qty": 1},
        "exit": {"available": True, "summary": "position remains open"},
        "shared_facts": {"status": "open", "pnl_pct": 0.5},
    })
    for name in ("scanner", "strategist", "commander", "monitor"):
        _write(trade / "evidence" / f"{name}_evidence.json", {})
    _write(trade / "entry.json", {})
    daily = reports / "operator_summary" / "daily" / "2026-06-19"
    _write(daily / "daily_summary.json", {})
    _write(daily / "q8_shadow_blocker_review.json", {})

    result = build_q9_evaluation(reports, "2026-06-19")
    evaluation = json.loads(
        (reports / "evaluation" / "trades" / "2026-06-19" / "TRD_OPEN" / "trade_evaluation.json").read_text(encoding="utf-8")
    )
    assert evaluation["evidence_class"] == "UNAVAILABLE"
    assert evaluation["integrity"]["status"] == "WATCH"
    assert evaluation["realized_outcome"]["net_return_pct"] is None


def test_q9_read_model_derives_hold_rank_and_playbook_from_evidence(tmp_path: Path) -> None:
    trade = tmp_path / "TRD_20260622_009150_01"
    _write(trade / "lifecycle_bundle.json", {
        "day": "2026-06-22",
        "trade_id": trade.name,
        "symbol": "009150",
        "lifecycle": {
            "status": "closed",
            "entry": {
                "ts": "2026-06-22T02:53:29+00:00",
                "price": 2273000,
                "qty": 1,
                "scanner_context": {
                    "selected_symbol": "009150",
                    "top_candidates": [{"rank": 1, "symbol": "005935"}],
                },
                "strategist_context": {"playbook": ""},
            },
            "exit": {
                "ts": "2026-06-22T03:12:58+00:00",
                "action": "SELL",
                "price": 2258000,
                "qty": 1,
                "execution_details": {
                    "filled_qty": 1,
                    "broker_realized_pnl": -35366,
                    "broker_realized_pnl_pct": -0.0156,
                },
            },
        },
    })
    _write(trade / "entry.json", {})
    _write(trade / "exit.json", {})
    for name in ("strategist", "commander", "monitor"):
        _write(trade / "evidence" / f"{name}_evidence.json", {})
    _write(trade / "evidence" / "scanner_evidence.json", {
        "candidate_ranking_tables": [{
            "payload": {
                "rows": [
                    {"rank": 1, "symbol": "005935"},
                    {"rank": 6, "symbol": "009150"},
                ]
            }
        }],
        "candidate_selection_reasons": [{
            "payload": {"playbook": "defensive"}
        }],
    })

    model = build_q9_trade_read_model(trade)

    assert model["outcome"]["holding_seconds"] == 1169
    assert model["selection"]["selected_rank"] == 6
    assert model["selection"]["strategist_playbook"] == "defensive"
    assert [row["symbol"] for row in model["selection"]["post_strategist_top10"]] == ["005935", "009150"]
    assert model["selection"]["raw_scanner_snapshot_source"] == ""


def test_trade_read_model_recovers_q9_snapshot_from_daily_window(tmp_path) -> None:
    reports = tmp_path / "reports"
    trade = reports / "trades" / "2026-06-23" / "0900" / "TRD_20260623_005930_01"
    _write(trade / "lifecycle_bundle.json", {
        "day": "2026-06-23",
        "trade_id": trade.name,
        "symbol": "005930",
        "lifecycle": {
            "status": "closed",
            "entry": {
                "ts": "2026-06-23T00:05:00+00:00",
                "run_id": "run-entry",
                "scanner_context": {"selected_symbol": "005930"},
            },
            "exit": {
                "ts": "2026-06-23T00:20:00+00:00",
                "action": "SELL",
                "execution_details": {
                    "filled_qty": 1,
                    "broker_realized_pnl_pct": 0.001,
                },
            },
        },
    })
    _write(trade / "entry.json", {"run_id": "run-entry"})
    _write(trade / "exit.json", {})
    _write(
        reports / "operator_summary" / "daily" / "2026-06-23" / "q9_decision_windows.json",
        {
            "windows": [{
                "decision_id": "Q9_20260623_run-entry",
                "run_id": "run-entry",
                "scanner_control": {
                    "source": "scanner_intrinsic_control_snapshot",
                    "scope": "same_candidate_universe_ranking_only",
                    "top10": [{"symbol": "000660"}],
                },
                "strategist_selection": {
                    "selected_symbol": "005930",
                    "post_strategist_top10": [{"symbol": "005930"}],
                },
                "commander_final": {
                    "decision_id": "Q9_20260623_run-entry",
                    "selected_symbol": "005930",
                    "decision": "approve",
                },
            }],
        },
    )

    model = build_q9_trade_read_model(trade)

    assert model["selection"]["q9_snapshot_source"] == "daily_q9_window.run_id"
    assert model["selection"]["q9_decision_id"] == "Q9_20260623_run-entry"
    assert model["selection"]["raw_scanner_top1"]["symbol"] == "000660"
    assert model["selection"]["commander_final_explicit"] is True
