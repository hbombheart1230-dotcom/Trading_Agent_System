import json
from pathlib import Path

from libs.contracts.agent_outputs import AGENT_VALIDATION_SCHEMA_VERSION, validate_artifact
from libs.runtime.canonical_artifacts import (
    llm_stage_manifest_path,
    llm_run_artifact_paths,
    strategist_llm_stage_descriptor,
    write_llm_stage_manifest_entry,
    write_llm_stage_skip_entry,
    write_scanner_artifact,
    write_executor_artifact,
    write_llm_artifact_bundle,
    write_strategist_artifact,
)


def test_validate_artifact_reports_partial_when_required_fields_missing() -> None:
    artifact = {
        "schema_version": "agent_output.v1",
        "agent": "strategist",
        "run_id": "run-1",
        "ts": "2026-03-18T00:00:00+00:00",
        "phase": "session",
        "status": "ok",
    }
    validation = validate_artifact(artifact)
    assert validation["schema_version"] == AGENT_VALIDATION_SCHEMA_VERSION
    assert validation["status"] == "partial"
    assert "playbook" in validation["required_keys_missing"]
    assert 0.0 < float(validation["completeness_score"]) < 1.0


def test_write_strategist_artifact_always_includes_validation(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    state = {
        "run_id": "run-1",
        "started_at": "2026-03-18T01:02:03+00:00",
        "runtime_phase": "session",
        "reports_root": str(reports_root),
        "strategist_output": {
            "market_regime": "neutral",
            "playbook": "defensive",
            "themes": ["semiconductor"],
        },
    }

    path = Path(write_strategist_artifact(state))
    assert path.exists()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload.get("validation"), dict)
    assert payload["validation"]["schema_version"] == AGENT_VALIDATION_SCHEMA_VERSION
    assert payload["validation"]["status"] in {"ok", "partial", "invalid"}


def test_write_strategist_artifact_is_write_once_per_agent_path(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    state = {
        "run_id": "run-write-once",
        "started_at": "2026-03-18T01:02:03+00:00",
        "runtime_phase": "session",
        "reports_root": str(reports_root),
        "strategist_output": {
            "market_regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "breakout",
            "themes": ["semiconductor"],
            "strategy_policy": {},
        },
    }
    path = Path(write_strategist_artifact(state))
    first_payload = json.loads(path.read_text(encoding="utf-8"))
    state["strategist_output"]["playbook"] = "defensive"
    second_path = Path(write_strategist_artifact(state))
    second_payload = json.loads(second_path.read_text(encoding="utf-8"))

    assert path == second_path
    assert first_payload["playbook"] == "breakout"
    assert second_payload["playbook"] == "breakout"


def test_write_scanner_artifact_overwrites_after_post_scanner_refresh(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    state = {
        "run_id": "run-scanner-refresh",
        "started_at": "2026-03-18T01:02:03+00:00",
        "runtime_phase": "session",
        "reports_root": str(reports_root),
        "selected": {"symbol": "AAA", "score_total": 1.0, "score_breakdown": {"momentum": 0.2}},
        "ranked_candidates": [
            {"symbol": "AAA", "score_total": 1.0, "score_breakdown": {"momentum": 0.2}},
            {"symbol": "BBB", "score_total": 0.9, "score_breakdown": {"momentum": 0.1}},
        ],
        "scanner_output": {"top_stock": "AAA", "selection_summary": "first_scan"},
    }

    path = Path(write_scanner_artifact(state))
    first_payload = json.loads(path.read_text(encoding="utf-8"))

    state["selected"] = {"symbol": "CCC", "score_total": 1.2, "score_breakdown": {"volume": 0.3}}
    state["ranked_candidates"] = [
        {"symbol": "CCC", "score_total": 1.2, "score_breakdown": {"volume": 0.3}},
        {"symbol": "DDD", "score_total": 1.1, "score_breakdown": {"volume": 0.2}},
    ]
    state["scanner_output"] = {"top_stock": "CCC", "selection_summary": "post_scanner_refresh"}

    second_path = Path(write_scanner_artifact(state))
    second_payload = json.loads(second_path.read_text(encoding="utf-8"))

    assert path == second_path
    assert first_payload["selected_symbol"] == "AAA"
    assert second_payload["selected_symbol"] == "CCC"
    assert second_payload["top_ranked_symbols"][:2] == ["CCC", "DDD"]


def test_write_scanner_artifact_keeps_commander_visible_candidate_scope(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    ranked = [
        {"symbol": symbol, "score_total": 1.0 - (idx * 0.01), "score_breakdown": {"rank": idx}}
        for idx, symbol in enumerate(symbols)
    ]
    state = {
        "run_id": "run-scanner-visible-scope",
        "started_at": "2026-03-18T01:02:03+00:00",
        "runtime_phase": "session",
        "reports_root": str(reports_root),
        "selected": dict(ranked[0]),
        "ranked_candidates": ranked,
        "scanner_output": {
            "top_stock": "AAA",
            "selection_summary": "visible_scope",
            "applied_scanner_policy": {
                "entry_control": {"max_priority_rank": 10, "max_runner_ups": 9}
            },
        },
    }

    path = Path(write_scanner_artifact(state))
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["top_ranked_symbols"] == symbols
    assert [row["symbol"] for row in payload["ranked_candidates"]] == symbols
    assert [row["symbol"] for row in payload["candidate_ranking_table"]["rows"]] == symbols


def test_llm_bundle_writes_to_normalized_reports_llm_path(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    state = {
        "run_id": "run-llm-1",
        "started_at": "2026-03-18T09:00:00+00:00",
        "reports_root": str(reports_root),
    }
    refs = write_llm_artifact_bundle(
        state,
        artifact_name="strategist",
        prompt_payload={"prompt_text": "hello"},
        response_payload={"response_text": "{\"playbook\":\"defensive\",\"selected_themes\":[\"semiconductor\"]}"},
        meta_payload={"component": "strategist", "llm_status": "ok", "model": "minimax/minimax-m2.5"},
    )

    paths = llm_run_artifact_paths("run-llm-1", day="2026-03-18", reports_root=reports_root, artifact_name="strategist")
    assert Path(refs["prompt_ref"]) == paths["prompt"]
    assert Path(refs["response_ref"]) == paths["response"]
    assert Path(refs["meta_ref"]) == paths["meta"]
    assert paths["prompt"].exists()
    assert paths["response"].exists()
    assert paths["meta"].exists()
    meta_payload = json.loads(paths["meta"].read_text(encoding="utf-8"))
    assert str(meta_payload.get("prompt_hash") or "").strip()
    assert str(meta_payload.get("response_hash") or "").strip()
    assert Path(refs["strategist_summary_md_ref"]) == paths["base_dir"] / "strategist_summary.md"
    assert Path(refs["strategist_summary_json_ref"]) == paths["base_dir"] / "strategist_summary.json"
    assert (paths["base_dir"] / "strategist_summary.md").exists()
    assert (paths["base_dir"] / "strategist_summary.json").exists()
    assert meta_payload["strategist_summary_md_ref"].endswith("strategist_summary.md")


def test_llm_paths_prefer_classified_run_folder(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    classified = reports_root / "llm" / "2026-05-11" / "no_trade" / ("a" * 32)
    classified.mkdir(parents=True)

    paths = llm_run_artifact_paths("a" * 32, day="2026-05-11", reports_root=reports_root, artifact_name="strategist")
    manifest = llm_stage_manifest_path("a" * 32, day="2026-05-11", reports_root=reports_root)

    assert paths["base_dir"] == classified / "strategist"
    assert manifest == classified / "llm_stage_manifest.json"


def test_write_executor_artifact_classifies_llm_run_by_execution_result(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    run_id = "b" * 32
    state = {
        "run_id": run_id,
        "started_at": "2026-05-11T05:00:00+00:00",
        "reports_root": str(reports_root),
    }

    refs = write_llm_artifact_bundle(
        state,
        artifact_name="strategist_stage2_selected_symbol",
        prompt_payload={"prompt_text": "stage2"},
        response_payload={"response_text": "{}"},
        meta_payload={"component": "strategist_stage2_selected_symbol", "llm_status": "ok"},
    )
    write_llm_stage_manifest_entry(
        state,
        {
            **strategist_llm_stage_descriptor("selected_symbol_tactical_refresh"),
            "status": "ok",
            "prompt_ref": refs["prompt_ref"],
            "response_ref": refs["response_ref"],
            "meta_ref": refs["meta_ref"],
        },
    )

    write_executor_artifact(
        state,
        execution={"allowed": True, "execution_ok": True, "status": "filled", "action": "BUY", "symbol": "005930"},
        order={"action": "BUY", "symbol": "005930", "qty": 1},
    )

    classified_dir = reports_root / "llm" / "2026-05-11" / "trade_executed" / run_id
    assert classified_dir.exists()
    assert not (reports_root / "llm" / "2026-05-11" / run_id).exists()
    assert state["llm_report_classification"]["category"] == "trade_executed"
    assert "trade_executed" in state["llm_artifacts"]["strategist_stage2_selected_symbol"]
    meta_payload = json.loads((classified_dir / "strategist_stage2_selected_symbol" / "meta.json").read_text(encoding="utf-8"))
    manifest_payload = json.loads((classified_dir / "llm_stage_manifest.json").read_text(encoding="utf-8"))
    assert "trade_executed" in meta_payload["prompt_ref"]
    assert "trade_executed" in manifest_payload["stages"][0]["prompt_ref"]


def test_llm_stage_manifest_upserts_stage_entry(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    state = {
        "run_id": "run-stage-manifest",
        "started_at": "2026-05-08T09:00:00+00:00",
        "reports_root": str(reports_root),
    }

    descriptor = strategist_llm_stage_descriptor("selected_symbol_tactical_refresh")
    refs = write_llm_stage_manifest_entry(
        state,
        {
            **descriptor,
            "status": "ok",
            "reason": "selected_symbol_tactical_refresh",
            "prompt_ref": "stage2/prompt.json",
            "response_ref": "stage2/response.json",
            "meta_ref": "stage2/meta.json",
        },
    )

    path = llm_stage_manifest_path("run-stage-manifest", day="2026-05-08", reports_root=reports_root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert refs["llm_stage_manifest_ref"] == str(path)
    assert payload["schema_version"] == "llm_stage_manifest.v1"
    assert payload["stages"][0]["stage_index"] == 2
    assert payload["stages"][0]["component"] == "strategist_stage2_selected_symbol"
    assert state["llm_artifacts"]["llm_stage_manifest"] == str(path)


def test_llm_stage_skip_entry_does_not_overwrite_existing_stage(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    state = {
        "run_id": "run-stage-skip",
        "started_at": "2026-05-08T09:00:00+00:00",
        "reports_root": str(reports_root),
    }

    write_llm_stage_manifest_entry(
        state,
        {
            **strategist_llm_stage_descriptor("stale_intraday_hold_review"),
            "status": "ok",
            "reason": "reviewed",
            "meta_ref": "stage3/meta.json",
        },
    )
    refs = write_llm_stage_skip_entry(
        state,
        call_kind="stale_intraday_hold_review",
        reason="not_due_this_cycle",
    )

    payload = json.loads(Path(refs["llm_stage_manifest_ref"]).read_text(encoding="utf-8"))
    assert refs["already_present"] is True
    assert payload["stages"][0]["status"] == "ok"
    assert payload["stages"][0]["reason"] == "reviewed"


def test_write_strategist_artifact_refreshes_llm_summary_after_canonical_detail(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    state = {
        "run_id": "run-strategy-detail-refresh",
        "started_at": "2026-05-07T01:02:03+00:00",
        "runtime_phase": "session",
        "reports_root": str(reports_root),
        "strategist_output": {
            "market_regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "pullback",
            "pre_llm_playbook": "defensive",
            "llm_requested_playbook": "pullback",
            "requested_playbook": "pullback",
            "requested_playbook_source": "llm",
            "final_playbook": "pullback",
            "tactical_strategy": "leader_vwap_reclaim_pullback",
            "strategy_scores": {
                "leader_vwap_reclaim_pullback": 0.85,
                "defensive_observe": 0.15,
            },
            "rejected_strategy_reasons": {
                "defensive_observe": "active pullback is preferred",
            },
            "candidate_watch_policy": {
                "max_priority_rank": 5,
                "max_runner_ups": 4,
                "cascade_enabled": True,
            },
            "themes": ["통신장비"],
        },
    }
    refs = write_llm_artifact_bundle(
        state,
        artifact_name="strategist",
        prompt_payload={"prompt_text": "hello"},
        response_payload={"response_text": "{\"playbook\":\"pullback\",\"selected_themes\":[\"통신장비\"]}"},
        meta_payload={"component": "strategist", "llm_status": "ok", "model": "test-model"},
    )

    summary_json_path = Path(refs["strategist_summary_json_ref"])
    before = json.loads(summary_json_path.read_text(encoding="utf-8"))
    assert before["strategy_detail"]["llm_requested_playbook"] == ""

    write_strategist_artifact(state)

    after = json.loads(summary_json_path.read_text(encoding="utf-8"))
    detail = after["strategy_detail"]
    assert detail["pre_llm_playbook"] == "defensive"
    assert detail["llm_requested_playbook"] == "pullback"
    assert detail["requested_playbook_source"] == "llm"
    md = Path(refs["strategist_summary_md_ref"]).read_text(encoding="utf-8")
    assert "전략 강화 필드: 적용됨" in md
    assert "플레이북 흐름: defensive -> pullback -> pullback (source=llm)" in md
