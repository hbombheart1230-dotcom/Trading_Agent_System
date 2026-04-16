import json
import pytest
from pathlib import Path
from libs.reporting.trade_read_model import build_trade_read_model

def test_build_trade_read_model_normal(tmp_path):
    # 1. 정상 trade 데이터: 모든 필드가 lifecycle_bundle 중심으로 채워짐
    trade_dir = tmp_path / "TRD_123"
    trade_dir.mkdir()
    bundle = {
        "trade_id": "TRD_123",
        "symbol": "AAPL",
        "lifecycle": {
            "entry": {"timestamp": "2023-10-01T10:00:00Z", "reason": "breakout_vwap_hold"},
            "exit": {"timestamp": "2023-10-01T11:00:00Z", "reason": "take_profit", "pnl": 100.5, "pnl_pct": 0.05, "position_age_seconds": 3600},
            "status": "closed"
        },
        "canonical_agent_artifacts": {
            "strategist": {"playbook": "breakout", "policy_source": "strategist"},
            "commander": {"applied_policy_source": "commander_confirmed"},
        },
        "evidence_recovery_used": False
    }
    (trade_dir / "lifecycle_bundle.json").write_text(json.dumps(bundle))
    
    res = build_trade_read_model(str(trade_dir))
    assert res["trade_id"] == "TRD_123"
    assert res["symbol"] == "AAPL"
    assert res["pnl"] == 100.5
    assert res["pnl_pct"] == 0.05
    assert res["playbook"] == "breakout"
    assert res["hold_duration_sec"] == 3600
    assert res["entry_reason"] == "breakout_vwap_hold"
    assert res["exit_reason"] == "take_profit"
    assert res["applied_policy_source"] == "commander_confirmed"
    assert res["strategy_policy_source"] == "strategist"
    assert res["primary_blocker_if_no_buy"] == "unknown"
    assert res["data_source"] == "lifecycle_bundle"
    assert isinstance(res.get("facts"), dict)
    assert isinstance(res.get("provenance"), dict)
    assert isinstance(res.get("context"), dict)
    assert res["facts"]["trade_id"] == "TRD_123"
    assert res["facts"]["trade_id"] == res["trade_id"]
    assert res["provenance"]["data_source"] == "lifecycle_bundle"
    assert res["context"]["scanner_selection_summary"] == "unknown"
    assert res["provenance"]["field_sources"]["playbook"] == "canonical.strategist.playbook"
    assert res["provenance"]["field_sources"]["entry_reason"] == "lifecycle.entry.reason"
    assert res["provenance"]["field_sources"]["trade_id"] == "lifecycle_bundle.trade_id"
    assert res["provenance"]["field_sources"]["symbol"] == "lifecycle_bundle.symbol"
    assert res["provenance"]["field_sources"]["data_source"] == "derived.presence_check"
    assert res["context"]["same_day_reporter_status"] == "missing"
    assert res["context"]["data_source_quality"]["has_lifecycle_bundle"] is True
    assert isinstance(res["context"]["scanner"], dict)
    assert isinstance(res["context"]["monitor"], dict)
    assert isinstance(res["context"]["strategist"], dict)
    assert isinstance(res["context"]["executor"], dict)

def test_build_trade_read_model_fallback(tmp_path):
    # 2. 일부 missing 데이터: ai_trade_report.json 으로 fallback 처리
    trade_dir = tmp_path / "TRD_456"
    trade_dir.mkdir()
    report_dir = trade_dir / "reports"
    report_dir.mkdir()
    report = {
        "report_data": {
            "trade_id": "TRD_456",
            "symbol": "MSFT",
            "playbook": "pullback",
            "status": "open",
            "shared_facts": {
                "pnl": "unavailable",
                "entry_time": "2023-10-01T10:00:00Z"
            }
        }
    }
    (report_dir / "ai_trade_report.json").write_text(json.dumps(report))
    
    res = build_trade_read_model(str(trade_dir))
    assert res["trade_id"] == "TRD_456"
    assert res["symbol"] == "MSFT"
    assert res["pnl"] == 0.0  # safe float fallback should yield 0.0
    assert res["hold_duration_sec"] == 0
    assert res["playbook"] == "pullback"
    assert res["data_source"] == "ai_trade_report"
    assert res["execution_label"] == "open"
    assert res["facts"]["data_source"] == "ai_trade_report"
    assert res["provenance"]["paths"]["ai_trade_report_json"].endswith("ai_trade_report.json")
    assert res["provenance"]["same_day_reporter_linkage"]["status"] == "missing"
    assert res["provenance"]["same_day_reporter_linkage"]["file_found"] is False
    assert res["provenance"]["field_sources"]["playbook"] == "ai_trade_report.report_data.playbook"
    assert res["provenance"]["field_sources"]["trade_id"] == "ai_trade_report.report_data.trade_id"
    assert res["provenance"]["field_sources"]["symbol"] == "ai_trade_report.report_data.symbol"

def test_build_trade_read_model_no_trade(tmp_path):
    # 3. No-trade 케이스: primary_blocker_if_no_buy 값에 blocker 기록 확인
    trade_dir = tmp_path / "TRD_789"
    trade_dir.mkdir()
    bundle = {
        "trade_id": "TRD_789",
        "symbol": "TSLA",
        "canonical_agent_artifacts": {
            "monitor": {"primary_reason_code": "volume_insufficient"}
        }
    }
    (trade_dir / "lifecycle_bundle.json").write_text(json.dumps(bundle))
    
    res = build_trade_read_model(str(trade_dir))
    assert res["trade_id"] == "TRD_789"
    assert res["symbol"] == "TSLA"
    assert res["primary_blocker_if_no_buy"] == "volume_insufficient"
    assert res["entry_ts"] == "unknown"


def test_build_trade_read_model_provenance_and_context_surfaces(tmp_path):
    trade_dir = tmp_path / "TRD_999"
    trade_dir.mkdir()
    bundle = {
        "trade_id": "TRD_999",
        "symbol": "005930",
        "trade_story_input_meta": {
            "same_day_reporter_linkage_status": "missing",
            "same_day_reporter_linkage_reason": "not_found_same_day",
            "same_day_reporter_expected_path": "reports/reporter/2026-04-15.json",
        },
        "canonical_agent_artifacts": {
            "scanner": {
                "summary": "Scanner selected 005930",
                "selected_symbol_score_drivers": {"momentum": 0.2},
                "top_candidates": [{"rank": 1, "symbol": "005930", "score_total": 0.8}],
            },
            "monitor": {
                "primary_reason_code": "pullback_not_mature",
                "trigger_type": "breakout_confirmation",
                "effective_stop_loss_pct": -0.015,
                "take_profit_pct": 0.025,
                "watch_axes": ["reclaim", "drawdown"],
                "monitor_stop_policy_trace": {"active_exit_axis": "drawdown"},
                "monitor_blocker_trace": {"primary_blockers": ["pullback_not_mature"]},
            },
            "executor": {
                "execution_details": {"order_status": "filled", "filled_qty": 1}
            },
        },
        "artifacts": {
            "canonical_scanner_json": "reports/canonical/2026-04-15/run/scanner.json",
            "canonical_monitor_json": "reports/canonical/2026-04-15/run/monitor.json",
        },
        "canonical_executor_json": "reports/canonical/2026-04-15/run/executor.json",
        "evidence_provenance": {
            "scanner": {"source": "canonical"},
            "monitor": {"source": "canonical"},
        },
    }
    (trade_dir / "lifecycle_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")

    res = build_trade_read_model(str(trade_dir))
    assert res["provenance"]["canonical_artifact_paths"]["canonical_scanner_json"].endswith("scanner.json")
    assert res["provenance"]["canonical_artifact_paths"]["canonical_executor_json"].endswith("executor.json")
    assert res["provenance"]["evidence_provenance"]["scanner"]["source"] == "canonical"
    assert res["context"]["scanner_selection_summary"] == "Scanner selected 005930"
    assert res["context"]["scanner_score_drivers"]["momentum"] == 0.2
    assert res["context"]["monitor_stop_policy_trace"]["active_exit_axis"] == "drawdown"
    assert res["context"]["monitor_blocker_trace"]["primary_blockers"] == ["pullback_not_mature"]
    assert res["context"]["monitor_exit_trigger"] == "breakout_confirmation"
    assert res["context"]["watch_axes"] == ["reclaim", "drawdown"]
    assert res["context"]["thresholds_snapshot"]["take_profit_pct"] == 0.025
    assert res["context"]["thresholds_snapshot"]["effective_stop_loss_pct"] == -0.015
    assert res["context"]["executor_execution_details"]["order_status"] == "filled"
    assert res["context"]["same_day_reporter_status"] == "missing"
    assert res["context"]["data_source_quality"]["has_canonical_artifacts"] is True
    assert res["context"]["scanner"]["summary"] == "Scanner selected 005930"
    assert res["context"]["monitor"]["exit_trigger"] == "breakout_confirmation"
    assert res["context"]["strategist"]["playbook"] == "unknown"
    assert res["context"]["executor"]["execution_label"] == "unknown"
    assert res["provenance"]["field_sources"]["entry_reason"] == "default"
    assert res["provenance"]["field_sources"]["primary_blocker_if_no_buy"] == "canonical.monitor.primary_reason_code"
    assert res["provenance"]["field_sources"]["hold_duration_sec"] == "default"
    assert res["provenance"]["field_sources"]["pnl"] == "default"
    assert res["provenance"]["field_sources"]["pnl_pct"] == "default"
    assert res["provenance"]["same_day_reporter_linkage"]["status"] == "missing"
    assert res["provenance"]["same_day_reporter_linkage"]["reason"] == "not_found_same_day"
    assert res["provenance"]["same_day_reporter_linkage"]["expected_path"] == "reports/reporter/2026-04-15.json"
