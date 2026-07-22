from __future__ import annotations

import json

from libs.runtime.quant.shadow_candidates import (
    _market_snapshot_for_symbol,
    build_quant_shadow_candidate_payload,
    save_quant_shadow_candidate_payload,
    sync_q9_decision_candidates_for_state,
)


def test_build_quant_shadow_candidate_payload_captures_top_runner_and_skipped() -> None:
    state = {
        "run_id": "run-1",
        "q9_decision_id": "Q9_20260524_run-1",
        "q9_decision_snapshot": {
            "decision_id": "Q9_20260524_run-1",
            "scanner_control": {
                "top10": [{"symbol": "000660", "rank": 1}],
            },
            "strategist_selection": {
                "post_strategist_top10": [{"symbol": "005930", "rank": 1}],
            },
            "commander_final": {
                "selected_symbol": "005930",
                "decision": "approve",
            },
        },
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
            "entry_cost_filter": {
                "passed": False,
                "proxy_edge_available": True,
                "directional_edge_available": False,
                "allow_triggered_signal_proxy_edge": False,
            },
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
    assert payload["q9_decision_id"] == "Q9_20260524_run-1"
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
    assert top["q9_decision_id"] == "Q9_20260524_run-1"
    assert {
        row["q9_decision_role"]
        for row in payload["q9_decision_candidates"]
    } == {
        "A_SCANNER_CONTROL",
        "B_STRATEGIST_RANKED",
        "C_COMMANDER_FINAL",
    }
    assert top["symbol"] == "005930"
    assert top["name"] == "삼성전자"
    assert top["guard_blocked"] is True
    assert top["guard_reason"] == "quant_entry_block"
    assert top["buy_blocked_pending_buy"] is True
    assert top["entry_quant_cost_floor_state"] == "not_met"
    assert top["entry_cost_filter"]["proxy_edge_available"] is True
    assert top["entry_cost_filter"]["allow_triggered_signal_proxy_edge"] is False
    assert top["quant_tactic_id"] == "pullback_reclaim"
    runner = payload["candidates"][1]
    assert runner["symbol"] == "000660"
    assert runner["theme"] == "HBM"
    assert runner["would_enter"] is True
    assert "opening_momentum_probe_shadow" in runner
    skipped = payload["candidates"][2]
    assert skipped["symbol"] == "035420"
    assert skipped["evaluated"] is False


def test_build_quant_shadow_candidate_payload_preserves_q15_skipped_runner_up_evidence() -> None:
    state = {
        "run_id": "run-q15",
        "trade_day": "2026-07-10",
        "tick_ts": 1783641720,
        "selected": {"symbol": "005930", "rank": 1, "score_total": 1.2},
        "ranked_candidates": [
            {"symbol": "005930", "rank": 1, "score_total": 1.2},
            {"symbol": "000660", "rank": 2, "score_total": 0.8},
            {"symbol": "035420", "rank": 3, "score_total": 1.1},
        ],
        "monitor_entry": {
            "reason": "breakout_not_ready",
            "intent_submitted": False,
        },
        "monitor_entry_cascade": {
            "attempted": True,
            "eligible": True,
            "top_pick_symbol": "005930",
            "top_pick_triggered": False,
            "top_pick_reason": "breakout_not_ready",
            "top_pick_guard_blocked": False,
            "skipped": [
                {
                    "symbol": "000660",
                    "reason": "q15_score_gap_above_runner_up_limit",
                    "rank": 2,
                    "top_pick_score": 1.2,
                    "candidate_score": 0.8,
                    "score_gap": 0.4,
                    "max_score_gap": 0.2,
                },
                {
                    "symbol": "035420",
                    "reason": "q15_runner_up_expected_blocker",
                    "rank": 3,
                    "expected_blocker": "below_vwap_reclaim_not_ready",
                },
            ],
            "fallback_used": False,
            "final_selected_symbol": "005930",
        },
    }

    payload = build_quant_shadow_candidate_payload(state)
    skipped_rows = [
        row for row in payload["candidates"]
        if row.get("shadow_role") == "runner_up_skipped"
    ]

    assert len(skipped_rows) == 2
    score_gap_row = next(row for row in skipped_rows if row["symbol"] == "000660")
    blocker_row = next(row for row in skipped_rows if row["symbol"] == "035420")
    assert score_gap_row["reason"] == "q15_score_gap_above_runner_up_limit"
    assert score_gap_row["rank"] == 2
    assert score_gap_row["top_pick_score"] == 1.2
    assert score_gap_row["candidate_score"] == 0.8
    assert score_gap_row["score_gap"] == 0.4
    assert score_gap_row["max_score_gap"] == 0.2
    assert score_gap_row["would_enter"] is False
    assert blocker_row["reason"] == "q15_runner_up_expected_blocker"
    assert blocker_row["expected_blocker"] == "below_vwap_reclaim_not_ready"


def test_build_quant_shadow_candidate_payload_fills_quant_surface_and_market_snapshot() -> None:
    state = {
        "run_id": "run-market",
        "trade_day": "2026-06-01",
        "tick_ts": 1780268400,
        "selected": {"symbol": "005930", "score_total": 0.8},
        "recent_minute_ohlcv_by_symbol": {
            "005930": {
                "rows": [
                    {"ts": 1780268340, "open": 70000, "high": 70100, "low": 69900, "close": 70050, "volume": 10},
                    {"ts": 1780268400, "open": 70050, "high": 70200, "low": 70000, "close": 70100, "volume": 20},
                ]
            }
        },
        "monitor_entry": {
            "reason": "pullback_not_mature",
            "intent_submitted": False,
            "primary_failure_axis": "pullback_structure",
            "quant_factor_snapshot": {
                "source": "quant_monitor_entry_factor_snapshot.v1",
                "tactic_id": "vwap_reclaim_pullback",
                "factors": {"cost_floor_state": "met"},
            },
            "entry_quant_decision": {
                "tactic_id": "vwap_reclaim_pullback",
                "tactic_suitability": {"tier": "watch", "score": 0.62},
                "cost_edge": {"cost_floor_state": "met"},
            },
        },
        "monitor_entry_cascade": {
            "top_pick_symbol": "005930",
            "top_pick_triggered": False,
            "top_pick_reason": "pullback_not_mature",
            "top_pick_guard_blocked": False,
            "final_selected_symbol": "005930",
        },
    }

    payload = build_quant_shadow_candidate_payload(state)
    row = payload["candidates"][0]

    assert row["quant_tactic_id"] == "vwap_reclaim_pullback"
    assert row["tactic_suitability_tier"] == "watch"
    assert row["tactic_suitability_score"] == 0.62
    assert row["entry_quant_cost_floor_state"] == "met"
    assert row["shadow_forward_base"]["available"] is True
    assert row["shadow_forward_base"]["baseline_price"] == 70100.0


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


def test_opening_largecap_watchlist_row_reuses_same_symbol_runner_metrics() -> None:
    state = {
        "run_id": "run-5",
        "trade_day": "2026-05-28",
        "tick_ts": 1779840300,
        "selected": {"symbol": "402340", "score_total": 0.88},
        "ranked_candidates": [
            {"symbol": "402340", "rank": 1, "score_total": 0.88},
            {"symbol": "009150", "rank": 3, "score_total": 0.74},
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
            "fallback_trace": [
                {
                    "symbol": "009150",
                    "triggered": False,
                    "reason": "volume_confirmation_missing",
                    "volume_ratio": 0.86,
                    "vwap_distance": 0.021,
                    "breakout_ok": True,
                }
            ],
        },
    }

    payload = build_quant_shadow_candidate_payload(state)
    rows = [row for row in payload["candidates"] if row["symbol"] == "009150"]

    # The evaluated runner row is already present, so no duplicate watchlist row is needed.
    assert len(rows) == 1
    assert rows[0]["opening_largecap_surge_shadow"]["volume_ratio"] == 0.86
    assert rows[0]["opening_largecap_surge_shadow"]["vwap_distance_pct"] == 0.021
    assert rows[0]["opening_largecap_surge_shadow"]["reason"].startswith("cost_edge_not_met")


def test_opening_largecap_watchlist_marks_missing_metrics_when_no_same_symbol_metrics_exist() -> None:
    state = {
        "run_id": "run-6",
        "trade_day": "2026-05-28",
        "tick_ts": 1779840300,
        "selected": {"symbol": "402340", "score_total": 0.88},
        "ranked_candidates": [
            {"symbol": "402340", "rank": 1, "score_total": 0.88},
            {"symbol": "009150", "rank": 3, "score_total": 0.74},
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
    row = {row["symbol"]: row for row in payload["candidates"]}["009150"]

    assert row["shadow_role"] == "opening_largecap_watchlist"
    assert row["metric_source"] == "ranked_candidates"
    assert row["metric_missing_reason"] == "minute_metrics_not_available"


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


def test_sync_q9_decision_candidates_adds_commander_without_changing_q8_rows(tmp_path) -> None:
    payload = {
        "run_id": "run-1",
        "day": "2026-06-23",
        "latest_path": str(tmp_path / "latest.json"),
        "candidates": [{"symbol": "005930", "shadow_role": "top_pick"}],
        "q9_decision_candidates": [
            {"symbol": "000660", "q9_decision_role": "A_SCANNER_CONTROL"},
        ],
    }
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    state = {
        "run_id": "run-1",
        "trade_day": "2026-06-23",
        "tick_ts": 1782173100,
        "q9_decision_id": "Q9_20260623_run-1",
        "quant_shadow_candidates": {
            "path": str(path),
            "latest_path": str(tmp_path / "latest.json"),
        },
        "q9_decision_snapshot": {
            "decision_id": "Q9_20260623_run-1",
            "scanner_control": {"top10": [{"symbol": "000660", "rank": 1}]},
            "strategist_selection": {
                "post_strategist_top10": [{"symbol": "005930", "rank": 1}],
                "selected_symbol": "005930",
            },
            "commander_final": {
                "candidate_symbol": "005930",
                "selected_symbol": "005930",
                "decision": "approve",
            },
        },
    }

    result = sync_q9_decision_candidates_for_state(state)
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert result["status"] == "ok"
    assert result["q9_role_count"] == 3
    assert saved["candidates"] == payload["candidates"]
    assert saved["q9_sync_status"]["status"] == "complete"
    assert {row["q9_decision_role"] for row in saved["q9_decision_candidates"]} == {
        "A_SCANNER_CONTROL",
        "B_STRATEGIST_RANKED",
        "C_COMMANDER_FINAL",
    }


def test_market_snapshot_rejects_prior_day_minute_cache() -> None:
    result = _market_snapshot_for_symbol(
        {
            "recent_minute_ohlcv_by_symbol": {
                "005930": [{
                    "ts": 1782108120,
                    "close": 2640,
                    "raw_ts": "20260622150200",
                }]
            }
        },
        "005930",
        now_epoch=1782193411,
    )

    assert result["available"] is False
    assert result["reason"] == "same_day_minute_rows_unavailable"


def test_q9_candidate_uses_scanner_feature_price_when_minute_baseline_is_missing() -> None:
    payload = build_quant_shadow_candidate_payload(
        {
            "run_id": "run-q9",
            "trade_day": "2026-06-24",
            "tick_ts": 1782259500,
            "q9_decision_id": "Q9_20260624_run-q9",
            "q9_decision_snapshot": {
                "decision_id": "Q9_20260624_run-q9",
                "scanner_pre_strategist_universe": {
                    "intrinsic_ranked_top20": [
                        {
                            "symbol": "005930",
                            "rank": 1,
                            "compact_feature_snapshot": {
                                "engine_close_last": 85000,
                            },
                        }
                    ]
                },
                "scanner_control": {"top10": []},
                "strategist_selection": {"post_strategist_top10": []},
                "commander_final": {},
            },
            "selected": {"symbol": "005930"},
        }
    )

    row = payload["q9_decision_candidates"][0]
    assert row["q9_decision_role"] == "P_SCANNER_PRE_STRATEGIST_UNIVERSE"
    assert row["shadow_forward_base"]["available"] is True
    assert row["shadow_forward_base"]["baseline_price"] == 85000
    assert row["shadow_forward_base"]["source"] == "scanner_feature_snapshot"
