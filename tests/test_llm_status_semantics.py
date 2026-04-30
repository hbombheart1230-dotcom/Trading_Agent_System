from pathlib import Path

from libs.reporting.llm_artifacts import (
    build_llm_response_artifact,
    canonical_llm_status,
    persist_llm_artifact_refs,
)


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


def test_persist_llm_artifact_refs_moves_raw_payload_out_of_trade_surface(tmp_path: Path) -> None:
    compact = persist_llm_artifact_refs(
        artifact=build_llm_response_artifact(
            component="brief",
            run_id="run-1",
            trade_id="TRD_1",
            day="2026-03-18",
            status="partial",
            attempts=[
                {
                    "step": "first_attempt",
                    "system_prompt": "sys",
                    "user_prompt": "user",
                    "raw_response_text": "{\"k\":1}",
                    "status": "partial",
                    "latency_ms": 11,
                }
            ],
            parsed_output={"k": 1},
            model_info={"provider": "OpenRouter", "model": "openrouter/free"},
            meta={"response_truncated": True, "repair_used": True, "llm_error_type": "JSONDecodeError"},
        ),
        reports_root=tmp_path / "reports",
        day="2026-03-18",
        run_id="run-1",
        component="brief",
    )
    assert compact["prompt_ref"].endswith("prompt.json")
    assert compact["response_ref"].endswith("response.json")
    assert compact["prompt_hash"]
    assert compact["response_hash"]
    assert "raw_response_text" not in compact
    assert "system_prompt" not in compact
    assert "user_prompt" not in compact


def test_persist_llm_artifact_refs_generates_strategist_summary(tmp_path: Path) -> None:
    compact = persist_llm_artifact_refs(
        artifact=build_llm_response_artifact(
            component="strategist",
            run_id="run-s1",
            day="2026-04-29",
            status="ok",
            attempts=[
                {
                    "step": "first_attempt",
                    "system_prompt": "sys",
                    "user_prompt": "user",
                    "raw_response_text": '{"playbook":"defensive","selected_themes":["semiconductor"]}',
                    "status": "ok",
                    "latency_ms": 11,
                }
            ],
            parsed_output={"playbook": "defensive", "selected_themes": ["semiconductor"]},
            model_info={"provider": "OpenRouter", "model": "test-model"},
        ),
        reports_root=tmp_path / "reports",
        day="2026-04-29",
        run_id="run-s1",
        component="strategist",
    )

    md_path = tmp_path / "reports" / "llm" / "2026-04-29" / "run-s1" / "strategist" / "strategist_summary.md"
    json_path = tmp_path / "reports" / "llm" / "2026-04-29" / "run-s1" / "strategist" / "strategist_summary.json"
    assert md_path.exists()
    assert json_path.exists()
    assert compact["strategist_summary_md_ref"].endswith("strategist_summary.md")
    assert compact["strategist_summary_json_ref"].endswith("strategist_summary.json")
