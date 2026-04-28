from __future__ import annotations

import json
from pathlib import Path

from graphs.nodes.strategist_node import _build_compact_strategist_llm_payload
from libs.runtime.commander_memory_policy import build_commander_memory_policy
from libs.runtime.memory_packet_loader import load_commander_memory_packets


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _summary_payload(layer: str, trade_count: int) -> dict:
    return {
        "schema_version": f"operator_summary.{layer}.v1",
        "metrics": {
            "trade_count": trade_count,
            "closed_trade_count": trade_count,
            "win_rate": 0.5,
            "avg_return_pct": 0.12,
        },
        "operator_view": {
            "conclusion": f"{layer} operator summary is visible.",
            "review_points": ["entry quality", "exit quality"],
        },
    }


def test_commander_memory_packets_attach_operator_summaries_without_activating_memory(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(reports / "operator_summary" / "daily" / "2026-04-28" / "daily_summary.json", _summary_payload("daily", 2))
    _write_json(reports / "operator_summary" / "weekly" / "2026-W18" / "weekly_summary.json", _summary_payload("weekly", 5))
    _write_json(reports / "operator_summary" / "monthly" / "2026-04" / "monthly_summary.json", _summary_payload("monthly", 9))
    _write_json(reports / "operator_summary" / "symbols" / "005930" / "symbol_summary.json", _summary_payload("symbol", 3))

    packets = load_commander_memory_packets(
        state={
            "reports_root": str(reports),
            "day": "2026-04-28",
            "runtime_day": "2026-04-28",
            "selected": {"symbol": "005930"},
            "selected_symbol_memory": {
                "symbol": "005930",
                "trade_count": 1,
                "closed_trade_count": 1,
                "win_rate": 0.0,
                "avg_pnl_pct": -0.1,
            },
        }
    )

    assert packets["daily_strategy_memory"]["active"] is False
    assert packets["weekly_strategy_memory"]["active"] is False
    assert packets["monthly_strategy_memory"]["active"] is False
    assert packets["daily_strategy_memory"]["operator_summary"]["available"] is True
    assert packets["weekly_strategy_memory"]["operator_summary"]["metrics"]["trade_count"] == 5
    assert packets["monthly_strategy_memory"]["operator_summary"]["key"] == "2026-04"
    assert packets["symbol_memory_packet"]["operator_summary"]["metrics"]["trade_count"] == 3


def test_commander_policy_surfaces_operator_summary_metrics_as_quality_only(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(reports / "operator_summary" / "daily" / "2026-04-28" / "daily_summary.json", _summary_payload("daily", 2))

    packets = load_commander_memory_packets(
        state={
            "reports_root": str(reports),
            "day": "2026-04-28",
            "runtime_day": "2026-04-28",
        }
    )
    policy = build_commander_memory_policy(session_bias="active_selection", memory_packets=packets)

    assert policy["active_layers"] == []
    assert policy["scanner_bias_enabled"] is False
    assert policy["monitor_bias_enabled"] is False
    assert policy["layer_quality"]["daily"]["operator_summary_available"] is True
    assert policy["layer_quality"]["daily"]["operator_trade_count"] == 2
    assert "daily_operator_summary_available" in policy["rationale"]


def test_strategist_compact_payload_preserves_operator_summary_surface() -> None:
    daily_summary = _summary_payload("daily", 2)
    daily_summary["available"] = True
    daily_summary["status"] = "ok"
    daily_summary["artifact_path"] = "reports/operator_summary/daily/2026-04-28/daily_summary.json"
    payload = {
        "memory_packets": {
            "daily_strategy_memory": {
                "status": "empty",
                "best_playbooks": [],
                "worst_playbooks": [],
                "operator_summary": daily_summary,
            },
            "weekly_strategy_memory": {"status": "unavailable"},
            "monthly_strategy_memory": {"status": "unavailable"},
            "symbol_memory_packet": {"status": "unavailable"},
        }
    }

    compact = _build_compact_strategist_llm_payload(payload)

    compact_summary = compact["memory_packets"]["daily_strategy_memory"]["operator_summary"]
    assert compact_summary["available"] is True
    assert compact_summary["metrics"]["trade_count"] == 2
    assert compact_summary["operator_view"]["conclusion"] == "daily operator summary is visible."
