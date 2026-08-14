from __future__ import annotations

from fastapi.testclient import TestClient

from artifact_fixtures import write_trade_bundle


def test_report_catalog_is_fixed_allowlist(
    api_client: TestClient,
    api_settings,
) -> None:
    trade_id, _ = write_trade_bundle(api_settings.reports_root)

    payload = api_client.get(f"/api/v1/trades/{trade_id}/reports").json()

    assert payload["status"] == "AVAILABLE"
    ids = {row["report_id"] for row in payload["reports"]}
    assert "ai-summary" in ids
    assert "quant-diagnosis-data" in ids
    assert "llm-response" not in ids


def test_markdown_report_redacts_absolute_host_path(
    api_client: TestClient,
    api_settings,
) -> None:
    trade_id, _ = write_trade_bundle(api_settings.reports_root)

    payload = api_client.get(
        f"/api/v1/trades/{trade_id}/reports/ai-summary"
    ).json()

    assert payload["status"] == "AVAILABLE"
    assert "[redacted-path]" in payload["markdown"]
    assert "C:\\secret" not in payload["markdown"]


def test_json_report_removes_path_fields(
    api_client: TestClient,
    api_settings,
) -> None:
    trade_id, _ = write_trade_bundle(api_settings.reports_root)

    payload = api_client.get(
        f"/api/v1/trades/{trade_id}/reports/quant-diagnosis-data"
    ).json()

    assert payload["status"] == "AVAILABLE"
    assert payload["json_content"]["evidence"] == {}
    assert str(api_settings.repository_root) not in str(payload)


def test_unknown_report_is_not_arbitrary_file_access(
    api_client: TestClient,
    api_settings,
) -> None:
    trade_id, _ = write_trade_bundle(api_settings.reports_root)

    response = api_client.get(
        f"/api/v1/trades/{trade_id}/reports/../../entry.json"
    )

    assert response.status_code == 404
