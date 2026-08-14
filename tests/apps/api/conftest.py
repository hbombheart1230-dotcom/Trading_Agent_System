from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.config import ApiSettings
from apps.api.main import create_app


@pytest.fixture
def api_settings(tmp_path: Path) -> ApiSettings:
    reports = tmp_path / "reports"
    logs = tmp_path / "logs"
    state = tmp_path / "state"
    for path in (reports, logs, state):
        path.mkdir()
    return ApiSettings(
        repository_root=tmp_path,
        reports_root=reports,
        logs_root=logs,
        state_root=state,
    )


@pytest.fixture
def api_client(api_settings: ApiSettings) -> TestClient:
    with TestClient(create_app(api_settings)) as client:
        yield client
