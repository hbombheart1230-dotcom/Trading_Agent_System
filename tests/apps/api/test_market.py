from __future__ import annotations

from fastapi.testclient import TestClient

from artifact_fixtures import write_market_day


def test_market_snapshot_normalizes_indicators(
    api_client: TestClient,
    api_settings,
) -> None:
    write_market_day(api_settings.logs_root, "2026-08-13", kospi_change=1.2)

    payload = api_client.get(
        "/api/v1/market/snapshot",
        params={"day": "2026-08-13"},
    ).json()

    assert payload["status"] == "AVAILABLE"
    assert payload["sentiment_score"] == 0.2
    assert payload["breadth"]["breadth_ratio"] == 0.2
    assert {metric["key"] for metric in payload["metrics"]} == {"kospi", "usdkrw"}
    assert payload["provenance"]["coverage"] == 1.0


def test_market_series_is_bounded_and_reports_missing_days(
    api_client: TestClient,
    api_settings,
) -> None:
    write_market_day(api_settings.logs_root, "2026-08-12", kospi_change=-0.5)
    write_market_day(api_settings.logs_root, "2026-08-13", kospi_change=1.2)

    payload = api_client.get(
        "/api/v1/market/series",
        params={
            "start": "2026-08-12",
            "end": "2026-08-14",
            "metric": "kospi",
        },
    ).json()

    assert payload["status"] == "PARTIAL"
    assert [point["change_pct"] for point in payload["points"]] == [-0.5, 1.2]
    assert payload["missing_day_count"] == 1
    assert payload["provenance"]["coverage"] == 2 / 3


def test_market_series_rejects_unsafe_metric_key(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/market/series",
        params={
            "start": "2026-08-12",
            "end": "2026-08-13",
            "metric": "../secret",
        },
    )

    assert response.status_code == 400
