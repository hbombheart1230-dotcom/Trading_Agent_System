from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.config import ApiSettings
from apps.api.main import create_app


def test_liveness_is_read_only(api_client: TestClient) -> None:
    response = api_client.get("/health/live")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "AVAILABLE"
    assert payload["read_only"] is True
    assert payload["execution_callable"] is False


def test_readiness_reports_source_names_without_paths(api_client: TestClient) -> None:
    response = api_client.get("/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "AVAILABLE"
    assert {row["source"] for row in payload["sources"]} == {
        "logs",
        "reports",
        "state",
    }
    assert all("path" not in row for row in payload["sources"])


def test_readiness_is_partial_when_one_source_is_missing(
    api_settings: ApiSettings,
) -> None:
    missing_settings = ApiSettings(
        repository_root=api_settings.repository_root,
        reports_root=api_settings.reports_root,
        logs_root=api_settings.logs_root,
        state_root=api_settings.state_root / "missing",
    )

    with TestClient(create_app(missing_settings)) as client:
        payload = client.get("/health/ready").json()

    assert payload["status"] == "PARTIAL"
    state = next(row for row in payload["sources"] if row["source"] == "state")
    assert state == {
        "source": "state",
        "status": "UNAVAILABLE",
        "readable": False,
    }
