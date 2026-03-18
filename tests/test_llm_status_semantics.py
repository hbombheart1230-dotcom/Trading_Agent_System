from libs.reporting.llm_artifacts import build_llm_response_artifact, canonical_llm_status


def test_canonical_llm_status_maps_legacy_statuses() -> None:
    assert canonical_llm_status("ok") == "ok"
    assert canonical_llm_status("partial") == "partial"
    assert canonical_llm_status("salvaged") == "salvaged"
    assert canonical_llm_status("repaired") == "repaired"
    assert canonical_llm_status("fallback") == "fallback"
    assert canonical_llm_status("error") == "error"
    assert canonical_llm_status("parse_error") == "error"
    assert canonical_llm_status("timeout") == "error"
    assert canonical_llm_status("network_error") == "error"
    assert canonical_llm_status("empty_response") == "error"


def test_llm_artifact_exposes_canonical_status_field() -> None:
    artifact = build_llm_response_artifact(
        component="brief",
        run_id="run-1",
        trade_id="TRD_1",
        status="timeout",
        attempts=[{"status": "timeout"}],
    )
    assert artifact["status"] == "timeout"
    assert artifact["llm_status"] == "error"


def test_llm_artifact_backfills_model_from_final_attempt() -> None:
    artifact = build_llm_response_artifact(
        component="brief",
        run_id="run-1",
        trade_id="TRD_1",
        status="ok",
        model_info={},
        attempts=[
            {
                "status": "ok",
                "model_info": {"provider": "OpenRouter", "model": "openrouter/free"},
            }
        ],
    )
    assert artifact["model"] == "openrouter/free"
    assert artifact["model_info"]["model"] == "openrouter/free"
