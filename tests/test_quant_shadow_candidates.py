from __future__ import annotations

import json

from libs.runtime.quant.shadow_candidates import (
    build_quant_shadow_candidate_payload,
    save_quant_shadow_candidate_payload,
)


def test_build_quant_shadow_candidate_payload_captures_top_runner_and_skipped() -> None:
    state = {
        "run_id": "run-1",
        "trade_day": "2026-05-24",
        "tick_ts": 1779581400,
        "selected": {
            "symbol": "005930",
            "name": "삼성전자",
            "rank": 1,
            "score_total": 88.2,
            "theme": "반도체",
            "quant_tactic_id": "pullback_reclaim",
            "tactic_suitability_tier": "A",
        },
        "ranked_candidates": [
            {"symbol": "005930", "rank": 1, "score_total": 88.2},
            {
                "symbol": "000660",
                "name": "SK하이닉스",
                "rank": 2,
                "score_total": 82.1,
                "theme": "HBM",
                "quant_tactic_id": "breakout_continuation",
            },
            {"symbol": "035420", "name": "NAVER", "rank": 3, "score_total": 76.0},
        ],
        "monitor_entry": {
            "reason": "volume_confirmation_missing",
            "intent_submitted": False,
            "guard_reason": "quant_entry_block",
            "buy_blocked_pending_buy": True,
            "primary_failure_axis": "volume",
            "cost_adjusted_edge_ok": False,
            "cost_adjusted_edge_pct": -0.05,
            "cost_drag_pct": 0.31,
            "quant_factor_snapshot": {"vwap_distance_pct": 0.2},
            "entry_quant_decision": {
                "decision": "observe",
                "cost_edge": {"cost_floor_state": "not_met"},
            },
        },
        "monitor_entry_cascade": {
            "attempted": True,
            "eligible": True,
            "top_pick_symbol": "005930",
            "top_pick_triggered": False,
            "top_pick_reason": "volume_confirmation_missing",
            "top_pick_guard_blocked": True,
            "fallback_trace": [
                {
                    "symbol": "000660",
                    "rank": 2,
                    "score_total": 82.1,
                    "triggered": True,
                    "guard_blocked": False,
                    "reason": "ready",
                    "transition_readiness_score": 0.91,
                    "vwap_distance": 0.12,
                    "volume_ratio": 1.8,
                }
            ],
            "skipped": [{"symbol": "035420", "reason": "capacity_limit"}],
            "fallback_used": True,
            "fallback_from_symbol": "005930",
            "fallback_to_symbol": "000660",
            "final_selected_symbol": "000660",
        },
    }

    payload = build_quant_shadow_candidate_payload(state)

    assert payload["schema_version"] == "quant_shadow_candidates.v1"
    assert payload["behavior_effect"] == "observation_only"
    assert payload["summary"]["candidate_count"] == 3
    assert payload["summary"]["evaluated_count"] == 2
    assert payload["summary"]["would_enter_count"] == 1
    assert payload["opening_momentum_probe_shadow"]["behavior_effect"] == "observation_only"
    assert [row["shadow_role"] for row in payload["candidates"]] == [
        "top_pick",
        "runner_up_evaluated",
        "runner_up_skipped",
    ]
    top = payload["candidates"][0]
    assert top["symbol"] == "005930"
    assert top["name"] == "삼성전자"
    assert top["guard_blocked"] is True
    assert top["guard_reason"] == "quant_entry_block"
    assert top["buy_blocked_pending_buy"] is True
    assert top["entry_quant_cost_floor_state"] == "not_met"
    runner = payload["candidates"][1]
    assert runner["symbol"] == "000660"
    assert runner["theme"] == "HBM"
    assert runner["would_enter"] is True
    assert "opening_momentum_probe_shadow" in runner
    skipped = payload["candidates"][2]
    assert skipped["symbol"] == "035420"
    assert skipped["evaluated"] is False


def test_build_quant_shadow_candidate_payload_marks_opening_momentum_probe_shadow() -> None:
    state = {
        "run_id": "run-2",
        "trade_day": "2026-05-26",
        "tick_ts": 1779754200,
        "selected": {"symbol": "122630", "score_total": 1.2},
        "monitor_entry": {
            "reason": "too_extended_from_vwap",
            "intent_submitted": False,
            "primary_failure_axis": "overextension",
            "cost_adjusted_edge_ok": True,
            "cost_adjusted_edge_pct": 0.012,
            "cost_drag_pct": 0.0021,
            "quant_factor_snapshot": {
                "factors": {
                    "vwap_distance_pct": 0.011,
                    "volume_ratio": 1.6,
                    "breakout_ok": True,
                    "weighted_score_passed": True,
                    "human_chart_entry_score": 0.72,
                    "cost_floor_state": "met",
                }
            },
            "entry_quant_decision": {
                "decision": "entry_ready",
                "blockers": [],
                "cost_edge": {"ok": True, "cost_floor_state": "met"},
            },
        },
        "monitor_entry_cascade": {
            "top_pick_symbol": "122630",
            "top_pick_triggered": False,
            "top_pick_reason": "too_extended_from_vwap",
            "top_pick_guard_blocked": False,
            "final_selected_symbol": "122630",
        },
    }

    payload = build_quant_shadow_candidate_payload(state)
    row = payload["candidates"][0]

    assert payload["summary"]["would_enter_count"] == 0
    assert payload["summary"]["opening_momentum_probe_would_enter_count"] == 1
    assert row["opening_momentum_probe_would_enter"] is True
    assert row["opening_momentum_probe_shadow"]["reason"] == "opening_momentum_probe_ready"
    assert row["opening_momentum_probe_shadow"]["behavior_effect"] == "observation_only"


def test_build_quant_shadow_candidate_payload_marks_largecap_surge_below_standard_volume_floor() -> None:
    state = {
        "run_id": "run-3",
        "trade_day": "2026-05-27",
        "tick_ts": 1779840774,
        "selected": {"symbol": "005930", "score_total": 0.54},
        "monitor_entry": {
            "reason": "below_vwap_reclaim_not_ready",
            "intent_submitted": False,
            "primary_failure_axis": "confirmed_entry",
            "cost_adjusted_edge_ok": True,
            "quant_factor_snapshot": {
                "factors": {
                    "vwap_distance_pct": 0.0035,
                    "volume_ratio": 0.759,
                    "breakout_ok": True,
                    "human_chart_entry_score": 0.41,
                    "cost_floor_state": "met",
                }
            },
            "entry_quant_decision": {
                "decision": "entry_ready",
                "blockers": [],
                "cost_edge": {"ok": True, "cost_floor_state": "met"},
            },
        },
        "monitor_entry_cascade": {
            "top_pick_symbol": "005930",
            "top_pick_triggered": False,
            "top_pick_reason": "below_vwap_reclaim_not_ready",
            "top_pick_guard_blocked": False,
            "final_selected_symbol": "005930",
        },
    }

    payload = build_quant_shadow_candidate_payload(state)
    row = payload["candidates"][0]

    assert row["opening_momentum_probe_would_enter"] is False
    assert row["opening_largecap_surge_would_enter"] is True
    assert row["opening_largecap_surge_shadow"]["reason"] == "opening_largecap_surge_ready"
    assert payload["summary"]["opening_largecap_surge_would_enter_count"] == 1


def test_build_quant_shadow_candidate_payload_adds_opening_largecap_watchlist_ranked_rows() -> None:
    state = {
        "run_id": "run-4",
        "trade_day": "2026-05-27",
        "tick_ts": 1779840300,
        "selected": {"symbol": "402340", "score_total": 0.88},
        "ranked_candidates": [
            {"symbol": "402340", "rank": 1, "score_total": 0.88},
            {
                "symbol": "000660",
                "rank": 2,
                "score_total": 0.81,
                "volume_ratio": 0.91,
                "vwap_distance_pct": 0.004,
                "breakout_ok": True,
                "cost_adjusted_edge_ok": True,
            },
            {
                "symbol": "009150",
                "rank": 3,
                "score_total": 0.74,
                "volume_ratio": 0.45,
                "vwap_distance_pct": 0.002,
                "breakout_ok": True,
                "cost_adjusted_edge_ok": True,
            },
        ],
        "monitor_entry": {
            "reason": "volume_confirmation_missing",
            "intent_submitted": False,
            "cost_adjusted_edge_ok": False,
        },
        "monitor_entry_cascade": {
            "top_pick_symbol": "402340",
            "top_pick_triggered": False,
            "top_pick_reason": "volume_confirmation_missing",
            "top_pick_guard_blocked": True,
            "final_selected_symbol": "402340",
        },
    }

    payload = build_quant_shadow_candidate_payload(state)
    rows = {row["symbol"]: row for row in payload["candidates"]}

    assert rows["000660"]["shadow_role"] == "opening_largecap_watchlist"
    assert rows["000660"]["opening_largecap_surge_would_enter"] is True
    assert rows["009150"]["shadow_role"] == "opening_largecap_watchlist"
    assert rows["009150"]["opening_largecap_surge_would_enter"] is False
    assert rows["009150"]["opening_largecap_surge_shadow"]["reason"] == "volume_ratio_below_largecap_floor"


def test_save_quant_shadow_candidate_payload_writes_day_file_and_latest(tmp_path) -> None:
    payload = {
        "schema_version": "quant_shadow_candidates.v1",
        "run_id": "run/1",
        "day": "2026-05-24",
        "candidates": [{"symbol": "005930", "shadow_role": "top_pick"}],
    }

    result = save_quant_shadow_candidate_payload(payload, root=tmp_path)

    assert result["status"] == "ok"
    path = tmp_path / "2026-05-24" / "latest.json"
    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["candidates"][0]["symbol"] == "005930"
    assert saved["latest_path"] == str(path)


def test_save_quant_shadow_candidate_payload_skips_empty_payload(tmp_path) -> None:
    result = save_quant_shadow_candidate_payload({"day": "2026-05-24", "candidates": []}, root=tmp_path)

    assert result == {"status": "skipped", "reason": "no_shadow_candidates", "candidate_count": 0}
    assert not (tmp_path / "2026-05-24").exists()
