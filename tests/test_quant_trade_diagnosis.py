from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.quant_trade_diagnosis import (
    build_quant_trade_diagnosis,
    render_quant_trade_diagnosis,
    write_quant_trade_diagnoses_for_day,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _model() -> dict:
    return {
        "schema_version": "q9_trade_read_model.v1",
        "trade_id": "TRD_1",
        "day": "2026-07-30",
        "symbol": "005930",
        "status": "closed",
        "entry": {
            "timestamp": "2026-07-30T00:10:00+00:00",
            "price": 100.0,
            "quantity": 10,
            "reason": "breakout_confirmed",
        },
        "exit": {
            "timestamp": "2026-07-30T00:25:00+00:00",
            "price": 102.0,
            "quantity": 10,
            "reason": "take_profit",
            "broker_authoritative": True,
            "broker_truth_source": "kiwoom.ka10170",
        },
        "outcome": {
            "net_return_pct": 1.25,
            "realized_pnl": 1250,
            "pnl_source": "kiwoom.ka10170",
            "holding_seconds": 900,
        },
        "selection": {
            "raw_scanner_top1": {"symbol": "005930"},
            "scanner_top1": {"symbol": "005930"},
            "post_strategist_top10": [{"symbol": "005930"}],
            "selected_symbol": "005930",
            "selected_rank": 1,
            "selected_candidate": {
                "symbol": "005930",
                "score_total": 0.81,
                "confidence": 0.72,
                "risk_score": 0.42,
            },
            "commander_final": {"symbol": "005930"},
            "score_decomposition": {"momentum": 0.2, "risk_penalty": -0.05},
        },
        "integrity": {"status": "PASS", "defects": [], "watch_items": []},
    }


def _evaluation() -> dict:
    return {
        "schema_version": "trade_evaluation.v1",
        "trade_id": "TRD_1",
        "exit_quality": {
            "status": "observed",
            "best_exit_offset": "+15m",
            "max_post_exit_upside_pct": 0.2,
            "max_post_exit_drawdown_pct": -0.1,
            "observed_checkpoints": {},
        },
        "horizon_alignment": {
            "status": "ALIGNED",
            "strategy_horizon": "scalp",
            "horizon_violation_candidate": False,
            "target_hold_would_improve_exit": False,
        },
    }


def _trade_dir(root: Path) -> Path:
    trade = root / "reports" / "trades" / "2026-07-30" / "0900" / "TRD_1"
    _write(
        trade / "lifecycle_bundle.json",
        {
            "trade_id": "TRD_1",
            "symbol": "005930",
            "strategist_summary": {
                "market_regime": "risk_on",
                "market_sentiment": "bullish",
                "playbook": "breakout",
                "risk_tone": "normal",
                "trade_aggressiveness": "medium",
                "llm_parsed_output": {
                    "strategy_candidates": [
                        {
                            "strategy": "opening_range_breakout",
                            "score": 0.82,
                            "result": "selected",
                        }
                    ]
                },
            },
            "scanner_reason_human": {
                "selected_score": 0.81,
                "confidence": 0.72,
                "selection_reason": "rank1 momentum and trend",
                "score_breakdown": {"momentum": 0.2},
            },
            "commander_summary": {
                "mode": "integrated_chain",
                "risk_mode": "normal",
                "scanner_policy": {
                    "max_priority_rank": 1,
                    "max_runner_ups": 0,
                    "entry_control": {
                        "cascade_enabled": False,
                        "reason": "rank1_only",
                    },
                },
            },
            "monitor_reason_human": {
                "entry_pattern": "breakout",
                "entry_condition_path": "breakout_path",
                "entry_condition_scores": {
                    "entry_quality_score": 0.9,
                    "entry_hard_gate_passed": True,
                },
                "position_age_seconds": 900,
                "exit_triggered": True,
                "trigger_type": "take_profit",
            },
        },
    )
    _write(
        trade / "reports" / "ai_trade_summary_input.json",
        {
            "quant_tactic": {
                "entry_quant_decision": {
                    "decision": "allow",
                    "blockers": [],
                    "cost_edge": {
                        "cost_floor_state": "met",
                        "cost_adjusted_edge_pct": 0.004,
                        "cost_drag_pct": 0.0028,
                    },
                }
            }
        },
    )
    return trade


def test_quant_trade_diagnosis_is_deterministic_and_broker_authoritative(
    tmp_path: Path,
) -> None:
    trade = _trade_dir(tmp_path)
    kwargs = {
        "trade_dir": trade,
        "model": _model(),
        "evaluation": _evaluation(),
        "root_cause_report": {
            "rows": [{"trade_id": "TRD_1", "root_cause": "Aligned / No Alignment Issue"}]
        },
        "entry_timing_report": {
            "rows": [{"trade_id": "TRD_1", "label": "ENTRY_APPROPRIATE"}]
        },
        "all_models": [_model()],
        "conditional_alpha_context": {
            "match_status": "EXACT_DECISION_ID",
            "authority": "AUTHORITATIVE_POINT_IN_TIME_LINK",
            "cohort_ids": ["CONFIRMED_RANK_POSITIVE_1M"],
        },
    }

    first = build_quant_trade_diagnosis(**kwargs)
    second = build_quant_trade_diagnosis(**kwargs)

    assert first == second
    assert first["schema_version"] == "quant_trade_diagnosis.v1"
    assert first["behavior_effect"] == "diagnostic_only"
    assert first["authority"]["pnl"] == "broker_truth"
    assert first["trade_outcome"]["net_return_pct"] == 1.25
    assert first["trade_outcome"]["broker_truth_source"] == "kiwoom.ka10170"
    assert first["selection_authority_chain"]["consistent"] is True
    assert first["strategy_candidate_scores"]["rows"][0]["score"] == 0.82
    assert first["quant_interpretation"]["entry_cost_edge_positive"] is True
    assert (
        first["quant_interpretation"]["statistical_plausibility_status"]
        == "INSUFFICIENT_EVIDENCE"
    )
    assert first["quant_interpretation"]["thesis_statistically_plausible"] is None
    assert first["quant_interpretation"]["primary_failure_axis"] is None
    assert first["conditional_alpha_context"]["match_status"] == "EXACT_DECISION_ID"
    assert (
        first["quant_interpretation"]["primary_attribution_axis"]
        == "Aligned / No Alignment Issue"
    )
    assert "OrderIntent" not in json.dumps(first)


def test_quant_trade_diagnosis_missing_strategy_scores_are_not_inferred(
    tmp_path: Path,
) -> None:
    trade = _trade_dir(tmp_path)
    _write(trade / "lifecycle_bundle.json", {"trade_id": "TRD_1", "symbol": "005930"})

    payload = build_quant_trade_diagnosis(
        trade_dir=trade,
        model=_model(),
        evaluation=_evaluation(),
        all_models=[_model()],
    )
    markdown = render_quant_trade_diagnosis(payload)

    assert payload["strategy_candidate_scores"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert payload["strategy_candidate_scores"]["rows"] == []
    assert "no score was inferred" in markdown


def test_quant_trade_diagnosis_day_writer_creates_json_and_markdown(
    tmp_path: Path,
) -> None:
    trade = _trade_dir(tmp_path)
    reports = tmp_path / "reports"

    result = write_quant_trade_diagnoses_for_day(
        reports_root=reports,
        day="2026-07-30",
        trade_dirs=[trade],
        models=[_model()],
        evaluations=[_evaluation()],
        attributions=[{"schema_version": "q9_selection_attribution.v1"}],
        root_cause_report={"rows": []},
        entry_timing_report={"rows": []},
    )

    assert result["written_count"] == 1
    json_path = trade / "reports" / "quant_trade_diagnosis.json"
    markdown_path = trade / "reports" / "quant_trade_diagnosis.md"
    assert json_path.exists()
    assert markdown_path.exists()
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["behavior_effect"] == "diagnostic_only"
    assert "# Quant Trade Diagnosis" in markdown_path.read_text(encoding="utf-8")
