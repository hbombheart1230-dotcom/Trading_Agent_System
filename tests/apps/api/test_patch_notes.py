from __future__ import annotations

import json

from fastapi.testclient import TestClient

from apps.api.config import ApiSettings


def _write_patch_notes(settings: ApiSettings) -> None:
    target = settings.repository_root / "docs" / "trading_agent_patch_notes_detailed_update" / "patch_notes.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "generated_for": "Trading_Agent_System",
                "entry_count": 2,
                "entries": [
                    {"date": "2026-08-21", "version": "v1", "title": "Old", "stage": "Research", "types": ["ALPHA"], "summary": "old summary", "details": ["old detail"], "impact": "old impact", "sources": ["docs/old.md"], "status": "historical"},
                    {"date": "2026-08-28", "version": "v2", "title": "Current", "stage": "Operations", "types": ["WEB_UI", "ALPHA"], "summary": "current summary", "details": ["current detail"], "impact": "current impact", "sources": ["docs/current.md"], "status": "current", "provenance": {"owner": "codex", "reviewer": "claude-code", "final_approval": "human", "verification": "14 passed"}},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_patch_notes_are_exposed_newest_first(api_client: TestClient, api_settings: ApiSettings) -> None:
    _write_patch_notes(api_settings)

    response = api_client.get("/api/v1/patch-notes")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "AVAILABLE"
    assert payload["entry_count"] == 2
    assert payload["entries"][0]["title"] == "Current"
    assert payload["entries"][0]["provenance"] == {
        "development_era": None,
        "owner": "codex",
        "reviewer": "claude-code",
        "final_approval": "human",
        "verification": "14 passed",
        "source_baseline": None,
        "provenance_baseline": None,
    }
    assert payload["entries"][1]["provenance"] is None
    assert payload["stages"] == ["Operations", "Research"]
    assert payload["types"] == ["ALPHA", "WEB_UI"]
    assert payload["read_only"] is True
    assert payload["execution_callable"] is False


def test_repository_patch_notes_preserve_baseline_and_count() -> None:
    repository_root = __import__("pathlib").Path(__file__).resolve().parents[3]
    target = repository_root / "docs" / "trading_agent_patch_notes_detailed_update" / "patch_notes.json"
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["entry_count"] == 58
    assert len(payload["entries"]) == 58
    baseline = payload["entries"][-1]
    assert baseline["version"] == "Pre-Claude Refactoring Baseline"
    assert baseline["provenance"]["source_baseline"].startswith("6aa4e398")
    assert baseline["provenance"]["provenance_baseline"].startswith("c94746b")


def test_patch_notes_missing_is_non_fatal(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/patch-notes")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "UNAVAILABLE"
    assert payload["reason"] == "patch_notes_missing"
    assert payload["entries"] == []
