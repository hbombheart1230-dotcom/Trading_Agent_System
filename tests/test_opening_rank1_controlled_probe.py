from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import graphs.nodes.monitor_node as monitor_module
from graphs.nodes.monitor_node import monitor_node
from libs.runtime.opening_rank1_controlled_probe import (
    classify_candidate_setup,
    evaluate_opening_rank1_controlled_probe,
    load_probe_submissions,
    record_probe_submission,
)


KST = ZoneInfo("Asia/Seoul")


def _epoch(hour: int = 9, minute: int = 10) -> int:
    return int(datetime(2026, 8, 17, hour, minute, tzinfo=KST).timestamp())


def _candidate(*, fresh: bool = True) -> dict:
    return {
        "symbol": "005930",
        "rank": 1,
        "sources": ["top_change_rate", "top_value"] if fresh else ["top_value", "top_volume"],
        "score_breakdown": {
            "momentum": 0.1,
            "trend": 0.1,
            "ma_alignment": 0.1,
            "adx_trend": 0.1,
        },
    }


def _evaluate(**overrides) -> dict:
    params = {
        "selected": _candidate(),
        "entry_info": {"triggered": False},
        "original_wait_reason": "pullback_below_vwap_reclaim_not_ready",
        "base_entry_guard_blocked": False,
        "base_entry_guard_reason": "",
        "entry_quality_gate": {"reasons": []},
        "entry_cost_filter": {"enabled": True, "passed": True},
        "quant_entry_enforcement": {"blocked": False, "matched_blockers": []},
        "risk_off_policy": {"blocked": False},
        "now_epoch": _epoch(),
        "normal_qty": 8,
        "prior_probe_count": 0,
        "is_top_pick": True,
        "same_symbol_reentry_detected": False,
        "broker_mode": "mock",
        "enabled": True,
    }
    params.update(overrides)
    return evaluate_opening_rank1_controlled_probe(**params)


def test_fresh_change_rank1_probe_is_applied_with_quarter_size() -> None:
    result = _evaluate()

    assert result["applied"] is True
    assert result["candidate_setup"] == "FRESH_CHANGE_ACTIVATION"
    assert result["probe_qty"] == 2
    assert result["qty_fraction_effective"] == 0.25


def test_directional_breadth_can_override_only_listed_quant_volume_block() -> None:
    candidate = _candidate(fresh=False)
    result = _evaluate(
        selected=candidate,
        entry_info={"triggered": True},
        original_wait_reason="entry_signal_confirmed",
        quant_entry_enforcement={
            "blocked": True,
            "matched_blockers": ["volume_confirmation_missing"],
        },
    )

    assert classify_candidate_setup(candidate) == "DIRECTIONAL_BREADTH"
    assert result["applied"] is True
    assert result["overridden_quant_blockers"] == ["volume_confirmation_missing"]


def test_liquidity_only_candidate_is_not_eligible() -> None:
    candidate = _candidate(fresh=False)
    candidate["score_breakdown"] = {"momentum": 0.1}

    result = _evaluate(selected=candidate)

    assert classify_candidate_setup(candidate) == "LIQUIDITY_ONLY"
    assert result["applied"] is False
    assert result["reason"] == "candidate_setup_not_allowed"


def test_probe_preserves_hard_safety_guards() -> None:
    cases = [
        ({"broker_mode": "real"}, "mock_broker_required"),
        ({"is_top_pick": False}, "top_pick_only"),
        ({"prior_probe_count": 1}, "daily_probe_limit_reached"),
        ({"same_symbol_reentry_detected": True}, "same_symbol_reentry_not_allowed"),
        ({"entry_cost_filter": {"enabled": True, "passed": False}}, "cost_adjusted_edge_not_ready"),
        ({"entry_quality_gate": {"reasons": ["chart_fit_below_hard_floor"]}}, "entry_quality_hard_floor_not_met"),
        ({"risk_off_policy": {"blocked": True}}, "risk_off_policy_blocked"),
        (
            {
                "base_entry_guard_blocked": True,
                "base_entry_guard_reason": "same_symbol_position_open",
            },
            "same_symbol_position_open",
        ),
        ({"now_epoch": _epoch(9, 21)}, "outside_opening_window"),
    ]

    for override, expected_reason in cases:
        result = _evaluate(**override)
        assert result["applied"] is False
        assert result["reason"] == expected_reason


def test_non_overrideable_quant_blocker_remains_blocked() -> None:
    result = _evaluate(
        entry_info={"triggered": True},
        original_wait_reason="entry_signal_confirmed",
        quant_entry_enforcement={
            "blocked": True,
            "matched_blockers": ["directional_edge_evidence_missing"],
        },
    )

    assert result["applied"] is False
    assert result["reason"] == "non_overrideable_quant_blocker"


def test_probe_ledger_allows_only_one_submission_per_day(tmp_path: Path) -> None:
    decision = _evaluate()
    first = record_probe_submission(
        decision,
        run_id="run-1",
        recorded_at="2026-08-17T00:10:00+00:00",
        root=tmp_path,
    )
    second = record_probe_submission(
        decision,
        run_id="run-2",
        recorded_at="2026-08-17T00:11:00+00:00",
        root=tmp_path,
    )

    rows = load_probe_submissions("2026-08-17", root=tmp_path)
    assert first["recorded"] is True
    assert second["recorded"] is False
    assert second["reason"] == "daily_probe_limit_reached"
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-1"


def test_monitor_attaches_probe_provenance_and_caps_order_qty(monkeypatch) -> None:
    rows = [
        {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
        {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
        {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
        {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
        {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 2500, "vwap": 101.2},
    ]

    def _forced_probe(**kwargs) -> dict:
        assert kwargs["is_top_pick"] is True
        return {
            "schema_version": "opening_rank1_controlled_probe.v1",
            "applied": True,
            "eligible": True,
            "reason": "opening_rank1_controlled_probe_applied",
            "day": "2026-08-17",
            "symbol": "005930",
            "scanner_rank": 1,
            "candidate_setup": "FRESH_CHANGE_ACTIVATION",
            "probe_qty": 2,
            "normal_qty": kwargs["normal_qty"],
            "original_wait_reason": kwargs["original_wait_reason"],
            "overridden_quant_blockers": [],
        }

    monkeypatch.setattr(monitor_module, "evaluate_opening_rank1_controlled_probe", _forced_probe)
    monkeypatch.setattr(monitor_module, "load_probe_submissions", lambda _day: [])
    monkeypatch.setattr(
        monitor_module,
        "record_probe_submission",
        lambda *_args, **_kwargs: {"recorded": True, "reason": "recorded", "count": 1},
    )
    state = {
        "plan": {"thesis": "controlled probe integration"},
        "selected": {
            "symbol": "005930",
            "rank": 1,
            "price": 101.8,
            "score": 0.9,
            "risk_score": 0.2,
            "confidence": 0.8,
            "expected_move_pct": 0.03,
            "scanner_chart_fit_score": 0.86,
            "sources": ["top_change_rate", "top_value"],
        },
        "minute_ohlcv_by_symbol": {"005930": rows},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "market_snapshot": {"symbol": "005930", "price": 101.8},
        "policy": {
            "use_position_sizing": True,
            "risk_per_trade_ratio": 0.01,
            "stop_loss_pct": 0.03,
            "position_notional_ratio": 0.50,
            "max_position_qty": 10,
        },
    }

    out = monitor_node(state)

    assert len(out["intents"]) == 1
    assert out["intents"][0]["qty"] == 2
    probe = out["intents"][0]["meta"]["opening_rank1_controlled_probe"]
    assert probe["applied"] is True
    assert probe["reservation"]["recorded"] is True
    assert out["intents"][0]["meta"]["entry_lane"] == "opening_rank1_controlled_probe"
