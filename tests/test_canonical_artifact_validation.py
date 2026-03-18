import json
from pathlib import Path

from libs.contracts.agent_outputs import AGENT_VALIDATION_SCHEMA_VERSION, validate_artifact
from libs.runtime.canonical_artifacts import write_strategist_artifact


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
