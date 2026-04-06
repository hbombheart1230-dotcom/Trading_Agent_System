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