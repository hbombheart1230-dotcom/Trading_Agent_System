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
from libs.reporting.llm_artifacts import resolve_trade_day_root, trade_artifact_paths
from libs.reporting.trade_report_ai import build_deterministic_trade_report
from scripts.run_ai_trade_report_batch import (
    _build_parser,
    _classify_missing_story_input,
    _finalize_report_diagnostics,
    _resolve_generation_mode,
    _mark_partial_trade_artifact,
    _resolve_output_paths,
    _normalize_trade_id_filters,
    _resolve_story_input_for_regeneration,
    _sync_report_diagnostics,
    _sync_report_generation_state,
    main as _run_batch_main,
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


def test_run_ai_trade_report_batch_uses_separate_local_debug_output_paths(tmp_path: Path) -> None:
    trade_paths = trade_artifact_paths(tmp_path / "reports", "2026-03-19", "TRD_20260319_000660_01")

    resolved = _resolve_output_paths(trade_paths, True)

    assert resolved["compact_input_path"].name == "ai_trade_report_compact_input.local_debug.json"
    assert resolved["report_json_path"].name == "ai_trade_report.local_debug.json"
    assert resolved["report_md_path"].name == "ai_trade_report.local_debug.md"
    assert resolved["llm_path"].name == "ai_trade_report_llm_response.local_debug.json"


def test_run_ai_trade_report_batch_defaults_to_deterministic_no_llm() -> None:
    args = _build_parser().parse_args(["--day", "2026-03-19"])

    assert args.with_llm is False
    assert _resolve_generation_mode(args) == "deterministic"


def test_run_ai_trade_report_batch_can_opt_into_llm() -> None:
    args = _build_parser().parse_args(["--day", "2026-03-19", "--with-llm"])

    assert args.with_llm is True
    assert _resolve_generation_mode(args) == "llm"


def test_run_ai_trade_report_batch_resolves_misplaced_trade_day_root(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    misplaced_day_root = tmp_path / "2026-03-19"
    misplaced_trade_dir = misplaced_day_root / "TRD_20260319_000660_01"
    misplaced_trade_dir.mkdir(parents=True, exist_ok=True)

    resolved_day_root = resolve_trade_day_root(reports_root, "2026-03-19")
    trade_paths = trade_artifact_paths(
        reports_root,
        "2026-03-19",
        "TRD_20260319_000660_01",
        prefer_existing_day_root=True,
    )

    assert resolved_day_root == misplaced_day_root
    assert trade_paths["trade_root"] == misplaced_trade_dir


def test_run_ai_trade_report_batch_classifies_partial_trade_artifact_when_only_early_evidence_exists(
    tmp_path: Path,
) -> None:
    reports_root = tmp_path / "reports"
    trade_paths = trade_artifact_paths(reports_root, "2026-03-19", "TRD_20260319_000660_01")
    trade_dir = trade_paths["trade_root"]
    trade_dir.mkdir(parents=True, exist_ok=True)
    _write_json(trade_paths["strategist_input_json"], {"schema_version": "strategist_input.v1"})
    trade_paths["evidence_dir"].mkdir(parents=True, exist_ok=True)

    out = _classify_missing_story_input(trade_dir, trade_paths)

    assert out["partial_trade_artifact"] is True
    assert out["skip_reason"] == "partial_trade_artifact"


def test_run_ai_trade_report_batch_does_not_classify_partial_trade_artifact_when_lifecycle_exists(
    tmp_path: Path,
) -> None:
    reports_root = tmp_path / "reports"
    trade_paths = trade_artifact_paths(reports_root, "2026-03-19", "TRD_20260319_000660_01")
    trade_dir = trade_paths["trade_root"]
    trade_dir.mkdir(parents=True, exist_ok=True)
    _write_json(trade_paths["lifecycle_bundle_json"], {"schema_version": "trade_lifecycle.v1"})

    out = _classify_missing_story_input(trade_dir, trade_paths)

    assert out["partial_trade_artifact"] is False
    assert out["skip_reason"] == ""


def test_run_ai_trade_report_batch_marks_partial_trade_artifact_in_health_json(
    tmp_path: Path,
) -> None:
    reports_root = tmp_path / "reports"
    trade_paths = trade_artifact_paths(reports_root, "2026-03-19", "TRD_20260319_000660_01")
    trade_paths["trade_root"].mkdir(parents=True, exist_ok=True)
    _write_json(trade_paths["strategist_input_json"], {"schema_version": "strategist_input.v1"})
    trade_paths["evidence_dir"].mkdir(parents=True, exist_ok=True)

    _mark_partial_trade_artifact(
        trade_paths,
        day="2026-03-19",
        trade_id="TRD_20260319_000660_01",
        skip_reason="partial_trade_artifact",
    )

    health = _read_json(trade_paths["trade_health_json"])
    assert health["schema_version"] == "trade_health.v1"
    assert health["lifecycle_status"] == "partial"
    assert health["report_generation_status"] == "skipped"
    assert health["partial_trade_artifact"] is True
    assert health["skip_reason"] == "partial_trade_artifact"
    assert health["artifact_presence"]["strategist_input_json"] is True
    assert health["artifact_presence"]["lifecycle_bundle_json"] is False


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


def test_run_ai_trade_report_batch_syncs_deterministic_regen_as_skipped_ai_status(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_id = "TRD_20260319_000660_01"
    trade_paths = trade_artifact_paths(reports_root, "2026-03-19", trade_id)

    for key in (
        "lifecycle_bundle_json",
        "ai_trade_report_input_json",
        "trade_health_json",
    ):
        _write_json(trade_paths[key], {"schema_version": "test.v1"})

    story_input = {"trade_id": trade_id, "run_id": "RUN_DETERMINISTIC", "symbol": "000660"}
    report = build_deterministic_trade_report(story_input)

    diagnostics = _sync_report_diagnostics(trade_paths, report, {})
    _write_json(trade_paths["ai_trade_report_json"], report)
    _finalize_report_diagnostics(trade_paths, trade_paths["ai_trade_report_json"], diagnostics)

    assert diagnostics["report_status"] == "available"
    assert diagnostics["report_reason_code"] == "deterministic_only"
    assert diagnostics["generation_attempted"] is False
    assert diagnostics["ai_trade_report_status"] == "skipped"

    payload = _read_json(trade_paths["trade_health_json"])
    assert payload["report_generation_status"] == "available"
    assert payload["ai_trade_report_status"] == "skipped"
    assert payload["llm_trade_report_status"] == "skipped"


def test_run_ai_trade_report_batch_updates_top_level_health_status_after_success(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_paths = trade_artifact_paths(reports_root, "2026-03-19", "TRD_20260319_000660_01")

    for key in (
        "lifecycle_bundle_json",
        "ai_trade_report_input_json",
        "trade_health_json",
    ):
        _write_json(
            trade_paths[key],
            {
                "schema_version": "test.v1",
                "ai_trade_report_status": "error",
                "llm_trade_report_status": "error",
                "llm_response_status": "error",
            },
        )

    report = {
        "trade_id": "TRD_20260319_000660_01",
        "ai_trade_report_status": "ok",
        "deterministic_report_status": "ok",
        "llm_brief_status": "skipped",
        "generation": {
            "status": "ok",
            "mode": "ai",
            "model": "openrouter/test-model",
            "ai_trade_report_status": "ok",
        },
    }
    llm_artifact = {
        "status": "ok",
        "model": "openrouter/test-model",
        "parse_mode": "full",
        "completeness_score": 1.0,
    }

    diagnostics = _sync_report_diagnostics(trade_paths, report, llm_artifact)
    _write_json(trade_paths["ai_trade_report_json"], report)
    _finalize_report_diagnostics(trade_paths, trade_paths["ai_trade_report_json"], diagnostics)

    for key in (
        "ai_trade_report_json",
        "lifecycle_bundle_json",
        "ai_trade_report_input_json",
        "trade_health_json",
    ):
        payload = _read_json(trade_paths[key])
        assert payload["ai_trade_report_status"] == "ok"
        assert payload["llm_trade_report_status"] == "ok"
        assert payload["llm_response_status"] == "ok"
        assert payload["llm_parse_mode"] == "full"
        assert payload["llm_completeness_score"] == 1.0
        assert payload["report_generation_status"] == "available"
        assert payload["ai_report_diagnostics"]["report_status"] == "available"


def test_run_ai_trade_report_batch_normalizes_multiple_trade_id_filters() -> None:
    values = _normalize_trade_id_filters(
        ["TRD_1", "TRD_2,TRD_3", "TRD_2", "", "  TRD_4  "]
    )

    assert values == ["TRD_1", "TRD_2", "TRD_3", "TRD_4"]


def test_run_ai_trade_report_batch_default_regeneration_does_not_call_llm(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    import scripts.run_ai_trade_report_batch as batch_mod

    reports_root = tmp_path / "reports"
    day = "2026-03-19"
    trade_id = "TRD_20260319_000660_01"
    trade_paths = trade_artifact_paths(reports_root, day, trade_id)
    trade_paths["trade_root"].mkdir(parents=True, exist_ok=True)
    _write_json(
        trade_paths["ai_trade_report_input_json"],
        {
            "schema_version": "trade_story_input.v2",
            "trade_id": trade_id,
            "run_id": "RUN_DEFAULT_NO_LLM",
            "day": day,
            "symbol": "000660",
            "status": "closed",
        },
    )

    def exploding_builder(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("default batch regeneration must not call report LLM")

    monkeypatch.setattr(batch_mod, "build_ai_trade_report", exploding_builder)

    rc = _run_batch_main(
        [
            "--reports-root",
            str(reports_root),
            "--day",
            day,
            "--trade-id",
            trade_id,
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    report = _read_json(trade_paths["ai_trade_report_json"])

    assert rc == 0
    assert out["ok"] is True
    assert out["operator_summary_refresh"]["status"] == "ok"
    assert out["rows"][0]["generation_mode_requested"] == "deterministic"
    assert out["rows"][0]["llm_enabled"] is False
    assert out["rows"][0]["llm_status"] == "fallback"
    assert report["generation"]["mode"] == "deterministic"
    assert report["ai_trade_report_status"] == "skipped"
    assert trade_paths["ai_trade_report_md"].exists() is True
    assert trade_paths["ai_trade_report_llm_response_json"].exists() is True
    llm_marker = _read_json(trade_paths["ai_trade_report_llm_response_json"])
    assert llm_marker["status"] == "fallback"
    assert llm_marker["meta"]["reason"] == "deterministic_no_llm"


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
