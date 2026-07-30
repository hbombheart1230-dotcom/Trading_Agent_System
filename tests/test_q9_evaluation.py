from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.contracts import EvidenceClass, validate_contract_payload
from libs.reporting.evaluation.metrics import performance_metrics
from libs.reporting.evaluation.pipeline import build_q9_evaluation
from libs.reporting.evaluation.trade_read_model import build_q9_trade_read_model
from libs.reporting.evaluation.trade_evaluator import evaluate_trade
from libs.reporting.evaluation.pipeline import _baseline_hash
from libs.reporting.evaluation.start_gate import build_full_chain_start_gate
from libs.reporting.evaluation.frozen_window_closeout import _cleanup_q9_daily_artifact_debris


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
    assert Path(result["no_trade_attribution_report"]).exists()
    assert Path(result["q16_proxy_rejection_review"]).exists()
    assert (reports / "evaluation" / "trades" / "2026-06-19" / "TRD_1" / "trade_evaluation.json").exists()
    assert result["quant_trade_diagnosis"]["written_count"] == 1
    assert (trade / "reports" / "quant_trade_diagnosis.json").exists()
    assert (trade / "reports" / "quant_trade_diagnosis.md").exists()


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


def test_closeout_broker_skip_excludes_unresolved_trade_from_metrics(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    trade = reports / "trades" / "2026-07-03" / "1500" / "TRD_20260703_025440_06"
    _write(trade / "lifecycle_bundle.json", {
        "day": "2026-07-03",
        "trade_id": "TRD_20260703_025440_06",
        "symbol": "025440",
        "lifecycle": {
            "status": "partial",
            "entry": {"timestamp": "2026-07-03T06:01:00+00:00", "price": 3280, "qty": 49},
            "exit": {
                "timestamp": "2026-07-03T06:02:00+00:00",
                "action": "SELL",
                "price": 3279,
                "qty": 49,
                "execution_details": {"filled_qty": 49},
            },
        },
        "shared_facts": {"status": "partial", "pnl_pct": -0.0001, "pnl": -159},
    })
    for name in ("scanner", "strategist", "commander", "monitor"):
        _write(trade / "evidence" / f"{name}_evidence.json", {})
    _write(trade / "entry.json", {})
    daily = reports / "operator_summary" / "daily" / "2026-07-03"
    _write(daily / "daily_summary.json", {})
    _write(daily / "q8_shadow_blocker_review.json", {})
    _write(daily / "closeout_maintenance.json", {
        "steps": {
            "broker_closed_trade_reconciliation": {
                "snapshot_path": "data/logs/kiwoom_account_snapshots/2026-07-03/latest.json",
                "skipped": [{
                    "trade_id": "TRD_20260703_025440_06",
                    "symbol": "025440",
                    "reason": "order_pair_or_day_diary_row_not_found",
                }],
            }
        }
    })

    result = build_q9_evaluation(reports, "2026-07-03")
    scorecard = json.loads(Path(result["daily_scorecard"]).read_text(encoding="utf-8"))
    evaluation = json.loads(
        (reports / "evaluation" / "trades" / "2026-07-03" / "TRD_20260703_025440_06" / "trade_evaluation.json").read_text(encoding="utf-8")
    )

    assert "broker_closed_trade_unresolved" in evaluation["integrity"]["defects"]
    assert evaluation["integrity"]["promotion_metric_eligible"] is False
    assert scorecard["realized_performance"]["count"] == 0


def test_closeout_broker_skip_does_not_override_existing_broker_truth(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    trade = reports / "trades" / "2026-07-03" / "1500" / "TRD_20260703_025440_06"
    _write(trade / "lifecycle_bundle.json", {
        "day": "2026-07-03",
        "trade_id": "TRD_20260703_025440_06",
        "symbol": "025440",
        "lifecycle": {
            "status": "partial",
            "entry": {"timestamp": "2026-07-03T06:01:00+00:00", "price": 3280, "qty": 49},
            "exit": {
                "timestamp": "2026-07-03T06:02:00+00:00",
                "action": "SELL",
                "price": 3365,
                "qty": 49,
                "execution_details": {
                    "filled_qty": 49,
                    "broker_realized_pnl": -159,
                    "broker_realized_pnl_pct": -0.0001,
                },
            },
        },
        "shared_facts": {
            "status": "partial",
            "pnl_pct": -0.0001,
            "pnl": -159,
            "pnl_truth_source": "kiwoom.ka10170",
            "price_truth_source": "broker_fill",
        },
    })
    for name in ("scanner", "strategist", "commander", "monitor"):
        _write(trade / "evidence" / f"{name}_evidence.json", {})
    _write(trade / "entry.json", {})
    daily = reports / "operator_summary" / "daily" / "2026-07-03"
    _write(daily / "daily_summary.json", {})
    _write(daily / "q8_shadow_blocker_review.json", {})
    _write(daily / "closeout_maintenance.json", {
        "steps": {
            "broker_closed_trade_reconciliation": {
                "snapshot_path": "data/logs/kiwoom_account_snapshots/2026-07-03/latest.json",
                "skipped": [{
                    "trade_id": "TRD_20260703_025440_06",
                    "symbol": "025440",
                    "reason": "order_pair_or_day_diary_row_not_found",
                }],
            }
        }
    })

    result = build_q9_evaluation(reports, "2026-07-03")
    scorecard = json.loads(Path(result["daily_scorecard"]).read_text(encoding="utf-8"))
    evaluation = json.loads(
        (reports / "evaluation" / "trades" / "2026-07-03" / "TRD_20260703_025440_06" / "trade_evaluation.json").read_text(encoding="utf-8")
    )

    assert "broker_closed_trade_unresolved" not in evaluation["integrity"]["defects"]
    assert evaluation["integrity"]["promotion_metric_eligible"] is True
    assert scorecard["realized_performance"]["count"] == 1
    assert scorecard["realized_performance"]["average_return_pct"] == -0.01


def test_broker_day_split_sell_child_is_not_counted_as_independent_trade(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    parent = reports / "trades" / "2026-07-15" / "0900" / "TRD_20260715_005360_01"
    child = reports / "trades" / "2026-07-15" / "0900" / "TRD_20260715_005360_02"
    _write(parent / "lifecycle_bundle.json", {
        "day": "2026-07-15",
        "trade_id": parent.name,
        "symbol": "005360",
        "lifecycle": {
            "status": "closed",
            "entry": {
                "timestamp": "2026-07-15T00:01:00+00:00",
                "price": 3186,
                "qty": 952,
            },
            "exit": {
                "timestamp": "2026-07-15T00:09:00+00:00",
                "action": "SELL",
                "price": 3445,
                "qty": 476,
                "execution_details": {"filled_qty": 476},
            },
        },
        "shared_facts": {"status": "closed", "pnl_pct": 0.0806616},
    })
    _write(parent / "entry.json", {"symbol": "005360", "filled_qty": 952})
    _write(parent / "exit.json", {
        "symbol": "005360",
        "ts": "2026-07-15T00:09:00+00:00",
        "action": "SELL",
        "filled_qty": 476,
    })
    (parent / "reports").mkdir(parents=True)
    (parent / "reports" / "ai_trade_summary.md").write_text("# summary", encoding="utf-8")

    _write(child / "lifecycle_bundle.json", {
        "day": "2026-07-15",
        "trade_id": child.name,
        "symbol": "005360",
        "lifecycle": {
            "status": "closed",
            "entry": {
                "timestamp": "2026-07-15T00:01:00+00:00",
                "price": 3186,
                "qty": 476,
            },
            "exit": {
                "timestamp": "2026-07-15T00:09:01+00:00",
                "action": "SELL",
                "price": 3445,
                "qty": 476,
                "execution_details": {"filled_qty": 476},
            },
        },
        "shared_facts": {"status": "closed", "pnl_pct": 0.0806616},
    })
    _write(child / "entry.json", {"trade_id": child.name, "symbol": "005360", "filled_qty": 476})
    _write(child / "exit.json", {
        "trade_id": child.name,
        "symbol": "005360",
        "filled_qty": 476,
    })
    _write(child / "_health.json", {
        "trade_id": child.name,
        "symbol": "005360",
        "status": "closed_by_broker_day_trade_diary",
    })
    for trade in (parent, child):
        for name in ("scanner", "strategist", "commander", "monitor"):
            _write(trade / "evidence" / f"{name}_evidence.json", {})
    daily = reports / "operator_summary" / "daily" / "2026-07-15"
    _write(daily / "daily_summary.json", {})
    _write(daily / "q8_shadow_blocker_review.json", {})

    result = build_q9_evaluation(reports, "2026-07-15")
    scorecard = json.loads(Path(result["daily_scorecard"]).read_text(encoding="utf-8"))
    child_eval = json.loads(
        (reports / "evaluation" / "trades" / "2026-07-15" / child.name / "trade_evaluation.json").read_text(encoding="utf-8")
    )
    selection = json.loads(Path(result["selection_authority_audit"]).read_text(encoding="utf-8"))

    assert scorecard["artifact_integrity"]["trade_count"] == 2
    assert scorecard["artifact_integrity"]["eligible_trade_count"] == 1
    assert scorecard["realized_performance"]["count"] == 1
    assert "broker_day_partial_exit_duplicate" in child_eval["integrity"]["defects"]
    assert child_eval["integrity"]["promotion_metric_eligible"] is False
    assert selection["trade_count"] == 1
    assert selection["summary"]["excluded:broker_day_partial_exit_duplicate"] == 1


def test_q9_daily_artifact_cleanup_removes_stale_temp_and_lock(tmp_path: Path) -> None:
    daily = tmp_path / "reports" / "operator_summary" / "daily" / "2026-07-03"
    daily.mkdir(parents=True)
    (daily / "q9_decision_windows.json").write_text("{}", encoding="utf-8")
    (daily / "q9_decision_windows.json.1234.deadbeef.tmp").write_text("{}", encoding="utf-8")
    (daily / "q9_decision_windows.json.lock").write_bytes(b"\0")

    result = _cleanup_q9_daily_artifact_debris(
        reports_root=tmp_path / "reports",
        day="2026-07-03",
    )

    assert result["ok"] is True
    assert result["removed_count"] == 2
    assert not (daily / "q9_decision_windows.json.1234.deadbeef.tmp").exists()
    assert not (daily / "q9_decision_windows.json.lock").exists()


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


def test_broker_authoritative_close_without_timestamp_is_watch(tmp_path: Path) -> None:
    trade = tmp_path / "TRD_BROKER_CLOSE"
    _write(trade / "lifecycle_bundle.json", {
        "day": "2026-06-24",
        "trade_id": trade.name,
        "symbol": "097780",
        "lifecycle": {
            "status": "closed",
            "entry": {"ts": "2026-06-24T01:42:09+00:00", "price": 1414, "qty": 1000},
        },
    })
    _write(trade / "entry.json", {})
    _write(trade / "exit.json", {
        "broker_day_authoritative": True,
        "action": "SELL",
        "price": 1399,
        "qty": 1000,
        "timestamp": "",
        "execution_details": {
            "broker_day_authoritative": True,
            "broker_day_truth_source": "kiwoom.ka10170",
            "broker_realized_pnl": -27433,
            "broker_realized_pnl_pct": -0.0194,
        },
    })
    for name in ("scanner", "strategist", "commander", "monitor"):
        _write(trade / "evidence" / f"{name}_evidence.json", {})

    model = build_q9_trade_read_model(trade)

    assert model["evidence_class"] == "REALIZED"
    assert model["integrity"]["status"] == "WATCH"
    assert model["integrity"]["defects"] == []
    assert "broker_exit_timestamp_unavailable" in model["integrity"]["watch_items"]
    assert model["exit"]["broker_authoritative"] is True
    assert model["outcome"]["net_return_pct"] == -1.94


def test_q9_horizon_contract_flags_early_exit_vs_strategy_intent(tmp_path: Path) -> None:
    trade = tmp_path / "TRD_HORIZON_EARLY_EXIT"
    _write(trade / "lifecycle_bundle.json", {
        "day": "2026-06-26",
        "trade_id": trade.name,
        "symbol": "097780",
        "lifecycle": {
            "status": "closed",
            "entry": {"ts": "2026-06-26T00:10:00+00:00", "price": 1000, "qty": 1},
            "exit": {
                "ts": "2026-06-26T00:12:00+00:00",
                "action": "SELL",
                "price": 990,
                "qty": 1,
                "execution_details": {
                    "filled_qty": 1,
                    "broker_realized_pnl_pct": -0.01,
                },
            },
        },
    })
    _write(trade / "entry.json", {
        "monitor_context": {
            "commander_horizon_policy": {
                "schema_version": "commander_horizon_policy.v1",
                "strategy_horizon": "intraday",
                "source_strategy_horizon": "intraday",
                "expected_hold_window": {
                    "min_sec": 300,
                    "target_sec": 1800,
                    "max_sec": 14400,
                },
                "exit_guidance": {
                    "early_exit_allowed_reasons": ["hard_stop", "liquidity_collapse"],
                    "avoid_early_exit_reasons": ["small_noise_pullback"],
                },
                "observability_only": True,
                "allow_behavior_change": False,
                "do_not_force_hold": True,
            }
        }
    })
    _write(trade / "exit.json", {
        "post_exit_shadow": {
            "checkpoints": {
                "+30m": {
                    "status": "observed",
                    "return_pct": 1.25,
                }
            },
            "max_post_exit_upside_pct": 1.5,
        }
    })
    for name in ("scanner", "strategist", "commander", "monitor"):
        _write(trade / "evidence" / f"{name}_evidence.json", {})

    model = build_q9_trade_read_model(trade)
    evaluation = evaluate_trade(model)

    assert model["horizon_contract"]["available"] is True
    assert model["horizon_contract"]["strategy_horizon"] == "intraday"
    assert evaluation["horizon_alignment"]["status"] == "observed"
    assert evaluation["horizon_alignment"]["bucket"] == "before_min_hold"
    assert evaluation["horizon_alignment"]["horizon_violation_candidate"] is True
    assert evaluation["horizon_alignment"]["target_hold_would_improve_exit"] is True
    assert "horizon_violation_candidate" in evaluation["integrity"]["watch_items"]


def test_freeze_baseline_hash_is_stable_and_trade_independent() -> None:
    assert _baseline_hash() == _baseline_hash()


def test_confirmed_runtime_defect_is_preserved_but_excluded_from_promotion_metrics(tmp_path: Path) -> None:
    trade = tmp_path / "reports" / "trades" / "2026-07-21" / "0900" / "TRD_20260721_006800_01"
    _write(trade / "lifecycle_bundle.json", {
        "day": "2026-07-21",
        "trade_id": trade.name,
        "symbol": "006800",
        "lifecycle": {
            "status": "closed",
            "entry": {"ts": "2026-07-21T00:54:02+00:00", "price": 36351},
            "exit": {
                "ts": "2026-07-21T00:54:36+00:00",
                "price": 36343,
                "action": "SELL",
                "execution_details": {
                    "broker_realized_pnl_pct": -0.0092,
                    "broker_realized_pnl": -27411,
                    "broker_day_authoritative": True,
                },
            },
        },
        "shared_facts": {"status": "closed"},
    })
    _write(trade / "entry.json", {"timestamp": "2026-07-21T00:54:02+00:00", "price": 36351})
    _write(trade / "exit.json", {"timestamp": "2026-07-21T00:54:36+00:00", "price": 36343})
    _write(trade / "evaluation_exclusion.json", {
        "schema_version": "evaluation_exclusion.v1",
        "trade_id": trade.name,
        "active": True,
        "reason_code": "invalid_vwap_fallback_false_trend_breakdown",
        "scopes": ["promotion_metrics", "behavior_attribution"],
    })
    for name in ("scanner", "strategist", "commander", "monitor"):
        _write(trade / "evidence" / f"{name}_evidence.json", {})

    model = build_q9_trade_read_model(trade)
    evaluation = evaluate_trade(model)

    assert model["outcome"]["net_return_pct"] == -0.92
    assert model["integrity"]["status"] == "WATCH"
    assert "confirmed_runtime_defect" in model["integrity"]["defects"]
    assert model["integrity"]["evaluation_exclusion"]["behavior_metric_excluded"] is True
    assert evaluation["integrity"]["promotion_metric_eligible"] is False


def test_start_gate_accepts_legitimate_pending_forward_rows() -> None:
    gate = build_full_chain_start_gate(
        models=[],
        baseline_hash=_baseline_hash(),
        inventory={
            "daily_artifacts": {
                "q9_decision_windows": {
                    "exists": True,
                    "schema_match": True,
                    "complete_abc_window_count": 20,
                    "pre_strategist_forward_candidate_count": 100,
                    "forward_observed_candidate_count": 80,
                    "forward_pending_candidate_count": 20,
                    "forward_invalid_candidate_count": 0,
                    "missing_selected_candidate_count": 0,
                }
            }
        },
    )

    assert "missing_forward_price" not in gate["reason_categories"]
