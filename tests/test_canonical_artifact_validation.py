import json
from pathlib import Path

from libs.contracts.agent_outputs import AGENT_VALIDATION_SCHEMA_VERSION, validate_artifact
from libs.runtime.canonical_artifacts import (
    llm_run_artifact_paths,
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
        response_payload={"response_text": "{\"ok\":true}"},
        meta_payload={"llm_status": "ok", "model": "minimax/minimax-m2.5"},
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
