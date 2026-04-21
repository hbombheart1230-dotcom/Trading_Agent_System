from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.intraday_trade_reports import (
    _story_input_quality_score,
    finalize_ai_report_diagnostics,
    normalize_trade_id_filters,
    resolve_story_input_for_regeneration,
    sync_ai_report_diagnostics,
    sync_ai_trade_report_generation_state,
)
from libs.reporting.llm_artifacts import trade_artifact_paths
from scripts.run_ai_trade_report_batch import (
    _finalize_report_diagnostics,
    _normalize_trade_id_filters,
    _resolve_story_input_for_regeneration,
    _sync_report_diagnostics,
    _sync_report_generation_state,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_run_ai_trade_report_batch_reuses_intraday_helper_ownership() -> None:
    assert _normalize_trade_id_filters is normalize_trade_id_filters
    assert _resolve_story_input_for_regeneration is resolve_story_input_for_regeneration
    assert _sync_report_diagnostics is sync_ai_report_diagnostics
    assert _finalize_report_diagnostics is finalize_ai_report_diagnostics
    assert _sync_report_generation_state is sync_ai_trade_report_generation_state


def test_story_input_quality_score_penalizes_closed_symbol_mismatch_and_rewards_canonical_monitor() -> None:
    existing = {
        "symbol": "005380",
        "status": "closed",
        "selected_symbol": "034020",
        "run_id": "RUN_EXIT",
        "execution_details": {"filled_price": 537000, "broker_truth_source": "kiwoom.order_status"},
    }
    rebuilt = {
        "symbol": "005380",
        "status": "closed",
        "selected_symbol": "034020",
        "run_id": "RUN_EXIT",
        "execution_details": {"filled_price": 537000, "broker_truth_source": "kiwoom.order_status"},
        "canonical_monitor": {
            "current_price": 536000,
            "account_pnl_ratio": -0.0108,
        },
    }

    assert _story_input_quality_score(rebuilt) > _story_input_quality_score(existing)


def test_run_ai_trade_report_batch_syncs_salvaged_diagnostics_to_all_artifacts(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_paths = trade_artifact_paths(reports_root, "2026-03-19", "TRD_20260319_000660_01")

    for key in (
        "lifecycle_bundle_json",
        "ai_trade_report_input_json",
        "trade_health_json",
    ):
        _write_json(trade_paths[key], {"schema_version": "test.v1"})

    report = {
        "trade_id": "TRD_20260319_000660_01",
        "generation": {
            "status": "salvaged",
            "mode": "ai",
            "model": "stepfun/step-3.5-flash:free",
            "reason": "trade_report_ai returned truncated or partial JSON",
        },
    }
    llm_artifact = {
        "status": "salvaged",
        "model": "stepfun/step-3.5-flash:free",
        "error": "trade_report_ai returned truncated or partial JSON",
    }

    diagnostics = _sync_report_diagnostics(trade_paths, report, llm_artifact)
    _write_json(trade_paths["ai_trade_report_json"], report)
    _finalize_report_diagnostics(trade_paths, trade_paths["ai_trade_report_json"], diagnostics)

    assert diagnostics["report_status"] == "available"
    assert diagnostics["report_reason_code"] == "llm_generation_salvaged"

    for key in (
        "ai_trade_report_json",
        "lifecycle_bundle_json",
        "ai_trade_report_input_json",
        "trade_health_json",
    ):
        payload = _read_json(trade_paths[key])
        diag = payload.get("ai_report_diagnostics") or {}
        assert diag["report_status"] == "available"
        assert diag["report_output_available"] is True


def test_run_ai_trade_report_batch_normalizes_multiple_trade_id_filters() -> None:
    values = _normalize_trade_id_filters(
        ["TRD_1", "TRD_2,TRD_3", "TRD_2", "", "  TRD_4  "]
    )

    assert values == ["TRD_1", "TRD_2", "TRD_3", "TRD_4"]


def test_run_ai_trade_report_batch_syncs_generation_state_without_clobbering_other_components(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_paths = trade_artifact_paths(reports_root, "2026-03-19", "TRD_20260319_000660_01")

    _write_json(
        trade_paths["reports_dir"] / "report_generation_state.json",
        {
            "schema_version": "report_generation_state.v1",
            "components": {
                "ai_trade_report": {
                    "component": "ai_trade_report",
                    "status": "error",
                    "report_status": "missing",
                    "trade_id": "TRD_20260319_000660_01",
                    "run_id": "RUN_OLD",
                },
                "operator_brief": {
                    "component": "operator_brief",
                    "status": "skipped",
                    "skip_reason": "missing_brief_artifact",
                    "trade_id": "TRD_20260319_000660_01",
                },
            },
        },
    )
    _write_json(trade_paths["ai_trade_report_json"], {"schema_version": "test.v1"})
    _write_json(trade_paths["ai_trade_report_md"], {"schema_version": "test.v1"})

    story_input = {
        "trade_id": "TRD_20260319_000660_01",
        "run_id": "RUN_NEW",
        "story_id": "STORY_1",
    }
    compact_input = {"trade": {"symbol": "000660"}}
    report = {
        "ai_trade_report_status": "ok",
        "generation": {
            "status": "ok",
            "mode": "ai",
            "model": "openrouter/test-model",
        },
    }
    llm_artifact = {"status": "ok", "model": "openrouter/test-model"}

    payload = _sync_report_generation_state(
        trade_paths,
        story_input=story_input,
        compact_input=compact_input,
        report=report,
        llm_artifact=llm_artifact,
        llm_response_path=str(trade_paths["ai_trade_report_llm_response_json"]),
    )

    persisted = _read_json(trade_paths["reports_dir"] / "report_generation_state.json")
    ai_state = persisted["components"]["ai_trade_report"]

    assert payload == persisted
    assert ai_state["status"] == "ok"
    assert ai_state["report_status"] == "available"
    assert ai_state["trade_id"] == "TRD_20260319_000660_01"
    assert ai_state["run_id"] == "RUN_NEW"
    assert ai_state["model"] == "openrouter/test-model"
    assert ai_state["llm_response_path"] == str(trade_paths["ai_trade_report_llm_response_json"])
    assert "story_input_sha256" in ai_state["source_inputs"]
    assert "compact_input_sha256" in ai_state["source_inputs"]
    assert persisted["components"]["operator_brief"]["status"] == "skipped"


def test_run_ai_trade_report_batch_prefers_rebuilt_story_input_when_lifecycle_is_richer(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-03-19"
    trade_id = "TRD_20260319_000660_01"
    trade_paths = trade_artifact_paths(reports_root, day, trade_id)
    trade_dir = reports_root / "trades" / day / trade_id
    trade_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        trade_paths["ai_trade_report_input_json"],
        {
            "schema_version": "trade_story_input.v2",
            "trade_id": trade_id,
            "run_id": "RUN_EXIT",
            "symbol": "000660",
            "status": "closed",
            "action": "SELL",
            "selected_symbol": None,
            "candidate_count": None,
        },
    )
    _write_json(
        trade_paths["lifecycle_bundle_json"],
        {
            "day": day,
            "trade_id": trade_id,
            "run_id": "RUN_EXIT",
            "symbol": "000660",
            "trade_lifecycle_status": "closed",
            "lifecycle": {
                "entry": {
                    "run_id": "RUN_ENTRY",
                    "ts": "2026-03-19T00:10:00+00:00",
                    "action": "BUY",
                    "reason_human": "entry",
                    "scanner_context": {"selected_symbol": "000660"},
                },
                "hold": {"run_ids": ["RUN_MONITOR"]},
                "exit": {
                    "run_id": "RUN_EXIT",
                    "ts": "2026-03-19T00:11:00+00:00",
                    "action": "SELL",
                    "reason_human": "exit",
                },
            },
            "market_context_human": {"summary": "market"},
            "scanner_reason_human": {
                "summary": "scanner",
                "selected_symbol": "000660",
                "selected_rank": 1,
                "candidate_count": 5,
                "top_candidates": [{"symbol": "000660", "score": 1.2}],
            },
            "filters_human": {"summary": "filters"},
            "monitor_reason_human": {"summary": "monitor"},
            "guard_reason_human": {"summary": "guard"},
            "execution_outcome_human": {"summary": "execution"},
            "reporter_status_human": {"status": "linked_run", "summary": "reporter"},
            "operator_conclusion_human": {"summary": "conclusion"},
            "timeline": [],
            "warnings": [],
            "scanner_evidence": {
                "candidate_ranking_table": {"rows": [{"symbol": "000660", "score_total": 1.2}]}
            },
            "monitor_timeline": {},
        },
    )

    story_input, story_input_path, source, existing_score, rebuilt_score = _resolve_story_input_for_regeneration(
        trade_dir,
        trade_paths,
    )

    assert source == "rebuilt_from_lifecycle_bundle"
    assert story_input_path == str(trade_paths["ai_trade_report_input_json"])
    assert rebuilt_score >= existing_score
    assert story_input["scanner_reason_human"]["selected_symbol"] == "000660"
    assert story_input["scanner_selection_trace"]["selected_symbol"] == "000660"
    assert len(story_input["scanner_selection_trace"]["ranked_candidates"]) >= 1


def test_run_ai_trade_report_batch_rehydrates_broker_truth_from_lifecycle_bundle(tmp_path: Path, monkeypatch) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-04-20"
    trade_id = "TRD_20260420_010820_01"
    trade_paths = trade_artifact_paths(reports_root, day, trade_id)
    trade_dir = reports_root / "trades" / day / trade_id
    trade_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        trade_paths["ai_trade_report_input_json"],
        {
            "schema_version": "trade_story_input.v2",
            "trade_id": trade_id,
            "run_id": "RUN_EXIT",
            "symbol": "010820",
            "status": "closed",
            "action": "SELL",
            "exit_execution_details": {
                "order_id": "0174131",
                "filled_qty": 1,
                "filled_price": None,
                "broker_truth_source": None,
                "broker_day_truth_source": None,
            },
        },
    )
    _write_json(
        trade_paths["lifecycle_bundle_json"],
        {
            "day": day,
            "trade_id": trade_id,
            "run_id": "RUN_EXIT",
            "symbol": "010820",
            "trade_lifecycle_status": "closed",
            "lifecycle": {
                "entry": {
                    "run_id": "RUN_ENTRY",
                    "ts": "2026-04-20T06:04:17+00:00",
                    "action": "BUY",
                    "symbol": "010820",
                    "execution_details": {},
                },
                "exit": {
                    "run_id": "RUN_EXIT",
                    "ts": "2026-04-20T06:25:18+00:00",
                    "action": "SELL",
                    "symbol": "010820",
                    "execution_details": {
                        "order_id": "0174131",
                        "filled_qty": 1,
                    },
                },
                "summary": {
                    "lifecycle_summary_human": "closed",
                },
            },
            "entry": {
                "run_id": "RUN_ENTRY",
                "ts": "2026-04-20T06:04:17+00:00",
                "action": "BUY",
                "symbol": "010820",
                "execution_details": {},
            },
            "exit": {
                "run_id": "RUN_EXIT",
                "ts": "2026-04-20T06:25:18+00:00",
                "action": "SELL",
                "symbol": "010820",
                "execution_details": {
                    "order_id": "0174131",
                    "filled_qty": 1,
                },
            },
            "entry_execution_details": {},
            "exit_execution_details": {
                "order_id": "0174131",
                "filled_qty": 1,
            },
            "execution_details": {
                "order_id": "0174131",
                "filled_qty": 1,
            },
            "market_context_human": {"summary": "market"},
            "scanner_reason_human": {"summary": "scanner", "selected_symbol": "010820", "selected_rank": 1, "candidate_count": 2},
            "filters_human": {"summary": "filters"},
            "monitor_reason_human": {"summary": "monitor"},
            "guard_reason_human": {"summary": "guard"},
            "execution_outcome_human": {"summary": "execution"},
            "reporter_status_human": {"status": "linked_run", "summary": "reporter"},
            "operator_conclusion_human": {"summary": "conclusion"},
            "timeline": [],
            "warnings": [],
            "scanner_evidence": {},
            "monitor_timeline": {},
        },
    )

    def _fake_rehydrate(bundle: dict) -> dict:
        out = dict(bundle)
        truth = {
            "order_id": "0174131",
            "filled_qty": 1,
            "filled_price": 15610,
            "broker_truth_source": "kiwoom.order_status",
            "broker_day_truth_source": "kiwoom.ka10077",
            "broker_day_match_mode": "single_symbol_row",
            "broker_day_authoritative": True,
            "broker_realized_pnl": -240.0,
            "broker_fee": 12,
            "broker_tax": 8,
        }
        exit_ctx = dict(out.get("exit") or {})
        exit_ctx["execution_details"] = truth
        out["exit"] = exit_ctx
        lifecycle = dict(out.get("lifecycle") or {})
        lifecycle_exit = dict(lifecycle.get("exit") or {})
        lifecycle_exit["execution_details"] = truth
        lifecycle["exit"] = lifecycle_exit
        lifecycle["execution_details"] = truth
        out["lifecycle"] = lifecycle
        out["exit_execution_details"] = truth
        out["execution_details"] = truth
        return out

    monkeypatch.setattr(
        "libs.reporting.intraday_trade_reports.rehydrate_lifecycle_bundle_execution_truth",
        _fake_rehydrate,
    )

    story_input, story_input_path, source, _, _ = _resolve_story_input_for_regeneration(
        trade_dir,
        trade_paths,
    )

    assert source == "rebuilt_from_lifecycle_bundle"
    assert story_input_path == str(trade_paths["ai_trade_report_input_json"])
    assert story_input["exit_execution_details"]["filled_price"] == 15610
    assert story_input["exit_execution_details"]["broker_truth_source"] == "kiwoom.order_status"
    persisted = _read_json(trade_paths["ai_trade_report_input_json"])
    assert persisted["exit_execution_details"]["broker_day_truth_source"] == "kiwoom.ka10077"


def test_resolve_story_input_for_regeneration_prefers_rebuilt_when_truth_surface_differs_even_if_score_is_lower(tmp_path: Path, monkeypatch) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-04-21"
    trade_id = "TRD_20260421_005930_01"
    trade_paths = trade_artifact_paths(reports_root, day, trade_id)
    trade_dir = reports_root / "trades" / day / trade_id
    trade_dir.mkdir(parents=True, exist_ok=True)

    existing = {
        "trade_id": trade_id,
        "symbol": "005930",
        "status": "closed",
        "run_id": "RUN_EXIT",
        "selected_symbol": "005930",
        "execution_details": {
            "order_id": "0110847",
            "filled_price": 218000,
            "broker_truth_source": "kiwoom.order_status",
            "broker_day_truth_source": "kiwoom.ka10077",
            "broker_day_match_mode": "symbol_qty_price_exact",
            "broker_day_authoritative": True,
            "broker_realized_pnl": -1706.0,
            "broker_fee": 1520,
            "broker_tax": 436,
        },
        "canonical_monitor": {
            "current_price": 218250,
            "effective_pnl_ratio": -0.0078,
        },
    }
    _write_json(trade_paths["ai_trade_report_input_json"], existing)
    _write_json(
        trade_paths["lifecycle_bundle_json"],
        {
            "day": day,
            "trade_id": trade_id,
            "run_id": "RUN_EXIT",
            "symbol": "005930",
            "trade_lifecycle_status": "closed",
            "execution_details": {"order_id": "0110847", "filled_price": 218000},
        },
    )

    rebuilt = {
        "trade_id": trade_id,
        "symbol": "005930",
        "status": "closed",
        "run_id": "RUN_EXIT",
        "selected_symbol": "005930",
        "execution_details": {
            "order_id": "0110847",
            "filled_price": 218000,
            "broker_truth_source": "kiwoom.order_status",
            "broker_day_truth_source": "kiwoom.ka10077",
            "broker_day_match_mode": "ambiguous_symbol_rows",
            "broker_day_authoritative": False,
        },
    }

    monkeypatch.setattr(
        "libs.reporting.intraday_trade_reports.rehydrate_lifecycle_bundle_execution_truth",
        lambda bundle: dict(bundle),
    )
    monkeypatch.setattr(
        "libs.reporting.intraday_trade_reports.build_trade_story_input_from_bundle",
        lambda lifecycle_bundle, existing_story_input=None: dict(rebuilt),
    )

    story_input, story_input_path, source, _, _ = _resolve_story_input_for_regeneration(
        trade_dir,
        trade_paths,
    )

    assert source == "rebuilt_from_lifecycle_bundle"
    assert story_input_path == str(trade_paths["ai_trade_report_input_json"])
    assert story_input["execution_details"]["broker_day_match_mode"] == "ambiguous_symbol_rows"
    assert story_input["execution_details"]["broker_day_authoritative"] is False
