import json
import pytest
from pathlib import Path
from libs.reporting.symbol_read_model import build_symbol_read_model

def _create_mock_trade(root: Path, trade_id: str, symbol: str, bundle_data: dict):
    trade_dir = root / trade_id
    trade_dir.mkdir(parents=True)
    bundle = {
        "trade_id": trade_id,
        "symbol": symbol,
        **bundle_data
    }
    (trade_dir / "lifecycle_bundle.json").write_text(json.dumps(bundle))

def test_symbol_read_model_aggregation_and_patterns(tmp_path):
    trades_root = tmp_path / "reports" / "trades"
    
    # Trade 1: Win (AAPL)
    _create_mock_trade(trades_root, "TRD_1", "AAPL", {
        "lifecycle": {
            "entry": {"reason": "reclaim_ready"},
            "exit": {"reason": "take_profit", "pnl": 500.0, "pnl_pct": 0.05, "position_age_seconds": 1000}
        },
        "canonical_agent_artifacts": {
            "strategist": {"playbook": "breakout"}
        }
    })
    
    # Trade 2: Win (AAPL) -> Same pattern
    _create_mock_trade(trades_root, "TRD_2", "AAPL", {
        "lifecycle": {
            "entry": {"reason": "reclaim_ready"},
            "exit": {"reason": "take_profit", "pnl": 300.0, "pnl_pct": 0.03, "position_age_seconds": 800}
        },
        "canonical_agent_artifacts": {
            "strategist": {"playbook": "breakout"}
        }
    })
    
    # Trade 3: Loss (AAPL)
    _create_mock_trade(trades_root, "TRD_3", "AAPL", {
        "lifecycle": {
            "entry": {"reason": "volume_surge"},
            "exit": {"reason": "stop_loss", "pnl": -200.0, "pnl_pct": -0.02, "position_age_seconds": 600}
        },
        "canonical_agent_artifacts": {
            "strategist": {"playbook": "pullback"}
        }
    })

    # Trade 4: No Buy Blocker (AAPL)
    _create_mock_trade(trades_root, "TRD_4", "AAPL", {
        "canonical_agent_artifacts": {
            "monitor": {"primary_reason_code": "volume_insufficient"},
            "strategist": {"playbook": "breakout"}
        }
    })

    # Trade 5: Different Symbol (MSFT) - should be ignored
    _create_mock_trade(trades_root, "TRD_5", "MSFT", {
        "lifecycle": {"entry": {"reason": "test"}, "exit": {"reason": "test", "pnl": 100}}
    })

    res = build_symbol_read_model(str(trades_root), "AAPL")

    assert res["symbol"] == "AAPL"
    assert res["trade_count"] == 4
    assert res["closed_trade_count"] == 3
    assert res["win_count"] == 2
    assert res["loss_count"] == 1
    assert res["win_rate"] == pytest.approx(2/3)
    
    assert res["total_pnl"] == 600.0
    assert res["avg_pnl"] == 200.0
    assert res["avg_hold_duration_sec"] == 800.0  # (1000+800+600)/3

    assert res["dominant_playbook"] == "breakout"
    assert res["dominant_entry_reason"] == "reclaim_ready"
    assert res["dominant_exit_reason"] == "take_profit"
    assert res["dominant_monitor_blocker"] == "volume_insufficient"

    # Test Success Pattern (Top 1 should be breakout|reclaim_ready|take_profit, count=2)
    success = res["recent_success_pattern"]
    assert len(success) == 1
    assert success[0] == {"playbook": "breakout", "entry_reason": "reclaim_ready", "exit_reason": "take_profit", "count": 2}

    # Test Failure Pattern
    failure = res["repeated_failure_pattern"]
    assert len(failure) == 2
    types = [f["type"] for f in failure]
    assert "exit_reason" in types  # The stop loss
    assert "blocker" in types      # The volume_insufficient

def test_symbol_read_model_dominant_ignores_unknown(tmp_path):
    trades_root = tmp_path / "reports" / "trades"
    _create_mock_trade(trades_root, "T1", "TSLA", {"canonical_agent_artifacts": {"strategist": {"playbook": "pullback"}}})
    _create_mock_trade(trades_root, "T2", "TSLA", {"canonical_agent_artifacts": {"strategist": {"playbook": "unknown"}}})
    _create_mock_trade(trades_root, "T3", "TSLA", {"canonical_agent_artifacts": {}}) # Will be unknown by default
    
    res = build_symbol_read_model(str(trades_root), "TSLA")
    assert res["dominant_playbook"] == "pullback" # Pullback wins over multiple unknowns
    assert res["dominant_entry_reason"] == "unknown" # No valid entry reason at all

def test_symbol_read_model_empty_and_safe_math(tmp_path):
    # Empty directory
    trades_root = tmp_path / "empty_dir"
    trades_root.mkdir()
    res = build_symbol_read_model(str(trades_root), "NVDA")
    assert res["symbol"] == "NVDA"
    assert res["trade_count"] == 0
    assert res["win_rate"] == 0.0
    assert res["data_quality"]["unknown_fields_ratio"] == 0.0

def test_symbol_read_model_data_quality(tmp_path):
    trades_root = tmp_path / "reports" / "trades"
    _create_mock_trade(trades_root, "T1", "AMD", {
        "canonical_agent_artifacts": {"strategist": {"playbook": "pullback"}}
    }) # T1 has playbook="pullback", all other 5 fields will fallback to "unknown". So 5/6 unknown.
    
    res = build_symbol_read_model(str(trades_root), "AMD")
    assert res["data_quality"]["unknown_fields_ratio"] == pytest.approx(5/6)


def test_symbol_read_model_prefers_persisted_symbol_memory(tmp_path):
    reports_root = tmp_path / "reports"
    trades_root = reports_root / "trades"
    trades_root.mkdir(parents=True)
    symbol_root = reports_root / "symbols" / "AAPL"
    symbol_root.mkdir(parents=True)
    (symbol_root / "symbol_memory.json").write_text(
        json.dumps(
            {
                "schema_version": "symbol_memory.v1",
                "symbol": "AAPL",
                "trade_stats": {
                    "trade_count": 7,
                    "completed_trade_count": 5,
                    "win_rate": 0.4,
                    "avg_return_pct": -0.25,
                    "avg_hold_seconds": 420.0,
                },
                "playbook_stats": {
                    "pullback": {"count": 4, "win_rate": 0.5, "avg_return_pct": 0.2},
                    "breakout": {"count": 3, "win_rate": 0.0, "avg_return_pct": -0.8},
                },
                "pattern_stats": {
                    "successful_entry_patterns": ["pullback"],
                    "failed_entry_patterns": ["breakout"],
                    "common_monitor_failures": ["confirmed_entry"],
                },
                "monitor_patterns": {
                    "repeated_blockers": ["confirmed_entry"],
                    "dominant_exit_failure_axis": "hard_stop",
                },
            }
        ),
        encoding="utf-8",
    )

    res = build_symbol_read_model(str(trades_root), "AAPL")

    assert res["trade_count"] == 7
    assert res["closed_trade_count"] == 5
    assert res["win_count"] == 2
    assert res["loss_count"] == 3
    assert res["avg_pnl_pct"] == -0.25
    assert res["avg_hold_duration_sec"] == 420.0
    assert res["dominant_playbook"] == "pullback"
    assert res["dominant_exit_reason"] == "hard_stop"
    assert res["dominant_monitor_blocker"] == "confirmed_entry"
    assert res["data_quality"]["data_source"] == "symbol_memory"
