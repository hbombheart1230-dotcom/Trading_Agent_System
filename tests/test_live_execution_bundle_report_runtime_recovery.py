from __future__ import annotations

import scripts.run_live_execution_bundle_report as mod


def test_derive_trade_recovery_metadata_marks_recovered_entry_without_execution_evidence() -> None:
    lifecycle = {
        "status": "closed",
        "entry": {
            "action": "BUY",
            "symbol": "000660",
            "reason_human": "Entry context was recovered from the preserved strategist frame.",
            "strategist_context": {"market_context_summary": "defensive frame"},
            "scanner_context": {},
        },
        "exit": {
            "run_id": "run-sell",
            "ts": "2026-04-16T00:08:48+00:00",
            "reason_human": "peak_drawdown",
        },
    }

    recovered = mod._derive_trade_recovery_metadata(  # type: ignore[attr-defined]
        lifecycle=lifecycle,
        evidence_completeness={"missing_sections": []},
        section_provenance={},
    )

    assert recovered["trade_origin"] == "recovered_partial"
    assert recovered["lifecycle_completeness"] == "partial"
    assert "entry_evidence" in recovered["recovery_missing_sections"]
    assert "entry_evidence_thin" in recovered["recovery_sources"]


def test_build_trade_lifecycles_keeps_partial_sell_linkage_honest() -> None:
    lifecycles = mod._build_trade_lifecycles(  # type: ignore[attr-defined]
        day="2026-04-16",
        run_snapshots=[
            {
                "run_id": "run-sell-only",
                "ts_start": "2026-04-16T00:08:48+00:00",
                "ts_epoch": 1713226128,
                "symbol": "000660",
                "execution_action": "SELL",
                "exit_reason": "peak_drawdown",
                "monitor_reason": "confirmed_exit_signal",
            }
        ],
            run_bundles={
                "run-sell-only": {
                    "execution": {"action": "SELL", "qty": 1, "price": 1162000.0},
                    "story_contract": {"story_type": "simulation", "execution_mode_label": "simulation (mock broker)"},
                    "monitor_reason_human": {"summary": "peak_drawdown", "trigger_type": "Peak Drawdown"},
                    "execution_outcome_human": {"summary": "Sell order submitted."},
                    "guard_reason_human": {},
                }
            },
    )

    assert len(lifecycles) == 1
    lifecycle = lifecycles[0]
    assert lifecycle["status"] == "partial"
    assert lifecycle["run_ids_all"] == ["run-sell-only"]
    assert lifecycle["summary"]["holding_duration"] == ""
    assert "entry was partially recovered" in " ".join(lifecycle["warnings"]).lower()


def test_build_trade_lifecycles_attaches_sell_to_existing_open_candidate_when_buy_snapshot_missing() -> None:
    lifecycles = mod._build_trade_lifecycles(  # type: ignore[attr-defined]
        day="2026-04-16",
        run_snapshots=[
            {
                "run_id": "run-sell-only",
                "ts_start": "2026-04-16T01:54:44+00:00",
                "ts_epoch": 1713232484,
                "symbol": "000660",
                "execution_action": "SELL",
                "exit_reason": "peak_drawdown",
                "monitor_reason": "confirmed_exit_signal",
                "execution_ord_no": "0095475",
                "execution_qty": 1,
                "execution_price": 1162000.0,
            }
        ],
        run_bundles={
            "run-sell-only": {
                "execution": {"action": "SELL", "qty": 1, "price": 1162000.0, "ord_no": "0095475"},
                "story_contract": {"story_type": "simulation", "execution_mode_label": "simulation (mock broker)"},
                "monitor_reason_human": {"summary": "peak_drawdown", "trigger_type": "Peak Drawdown"},
                "execution_outcome_human": {"summary": "Sell order submitted."},
                "guard_reason_human": {},
            }
        },
        existing_open_lifecycles_by_symbol={
            "000660": [
                {
                    "trade_id": "TRD_20260416_000660_04",
                    "symbol": "000660",
                    "status": "open",
                    "entry": {
                        "run_id": "run-buy-prev",
                        "ts": "2026-04-16T01:53:41+00:00",
                        "action": "BUY",
                        "price": 1161000.0,
                        "qty": 1,
                        "reason_human": "entry ok",
                        "scanner_context": {"selected_symbol": "000660"},
                    },
                    "holding": {"run_ids": [], "holding_events": [], "posture_history": [], "monitor_updates": []},
                    "run_ids_all": ["run-buy-prev"],
                    "story_type": "simulation",
                    "execution_mode_label": "simulation (mock broker)",
                    "timeline": [],
                    "warnings": [],
                    "entry_ts_epoch": 1713232421.0,
                }
            ]
        },
    )

    assert len(lifecycles) == 1
    lifecycle = lifecycles[0]
    assert lifecycle["trade_id"] == "TRD_20260416_000660_04"
    assert lifecycle["status"] == "open"
    assert lifecycle["entry"]["run_id"] == "run-buy-prev"
    assert lifecycle.get("exit", {}) == {}


def test_build_trade_lifecycles_creates_partial_only_when_no_attach_candidate_exists() -> None:
    lifecycles = mod._build_trade_lifecycles(  # type: ignore[attr-defined]
        day="2026-04-16",
        run_snapshots=[
            {
                "run_id": "run-sell-only",
                "ts_start": "2026-04-16T01:54:44+00:00",
                "ts_epoch": 1713232484,
                "symbol": "000660",
                "execution_action": "SELL",
                "exit_reason": "peak_drawdown",
            }
        ],
        run_bundles={
            "run-sell-only": {
                "execution": {"action": "SELL", "qty": 1, "price": 1162000.0},
                "story_contract": {"story_type": "simulation", "execution_mode_label": "simulation (mock broker)"},
                "monitor_reason_human": {"summary": "peak_drawdown"},
            }
        },
        existing_open_lifecycles_by_symbol={},
    )

    assert len(lifecycles) == 1
    lifecycle = lifecycles[0]
    assert lifecycle["status"] == "partial"
    attach_debug = list(lifecycle.get("lifecycle_attach_debug") or [])
    assert attach_debug and attach_debug[-1]["new_trade_created_reason"] == "no_active_or_existing_open_lifecycle"
    assert attach_debug[-1]["recovered_lifecycle_reason"] == "sell_without_attachable_open_entry"


def test_build_trade_lifecycles_prefers_current_active_open_over_existing_candidate() -> None:
    lifecycles = mod._build_trade_lifecycles(  # type: ignore[attr-defined]
        day="2026-04-16",
        run_snapshots=[
            {
                "run_id": "run-buy-current",
                "ts_start": "2026-04-16T01:53:41+00:00",
                "ts_epoch": 1713232421,
                "symbol": "000660",
                "execution_action": "BUY",
            },
            {
                "run_id": "run-sell-current",
                "ts_start": "2026-04-16T01:54:44+00:00",
                "ts_epoch": 1713232484,
                "symbol": "000660",
                "execution_action": "SELL",
            },
        ],
        run_bundles={
            "run-buy-current": {"execution": {"action": "BUY", "qty": 1, "price": 1160000.0}},
            "run-sell-current": {"execution": {"action": "SELL", "qty": 1, "price": 1162000.0}},
        },
        existing_open_lifecycles_by_symbol={
            "000660": [
                {
                    "trade_id": "TRD_20260416_000660_99",
                    "symbol": "000660",
                    "status": "open",
                    "entry": {"run_id": "stale-buy", "ts": "2026-04-16T00:00:00+00:00", "action": "BUY", "scanner_context": {"selected_symbol": "000660"}},
                    "holding": {},
                    "run_ids_all": ["stale-buy"],
                    "entry_ts_epoch": 1713225600.0,
                }
            ]
        },
    )

    assert len(lifecycles) == 1
    lifecycle = lifecycles[0]
    assert lifecycle["entry"]["run_id"] == "run-buy-current"
    assert lifecycle["exit"]["run_id"] == "run-sell-current"
    attach_debug = list(lifecycle.get("lifecycle_attach_debug") or [])
    assert attach_debug and attach_debug[-1]["attach_match_reason"] == "matched_active_open_lifecycle_in_current_pass"
