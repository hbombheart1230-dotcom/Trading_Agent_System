from __future__ import annotations

from fastapi.testclient import TestClient

from artifact_fixtures import trade_row, write_operator_day, write_performance_day


def test_portfolio_maps_reconciled_positions(
    api_client: TestClient,
    api_settings,
) -> None:
    write_operator_day(
        api_settings.reports_root,
        "2026-08-10",
        [
            {
                "symbol": "005930",
                "qty": 2,
                "avg_price": 100.0,
                "current_price": 110.0,
                "unrealized_pnl": 20.0,
                "account_pnl_ratio": 0.1,
                "status": "open",
            }
        ],
    )

    payload = api_client.get(
        "/api/v1/portfolio",
        params={"day": "2026-08-10"},
    ).json()

    assert payload["status"] == "AVAILABLE"
    assert payload["authority"] == "RECONCILED_CLOSEOUT_READ_MODEL"
    assert payload["position_count"] == 1
    assert payload["positions"][0]["market_value"] == 220.0
    assert payload["total_market_value"]["value"] == 220.0
    assert payload["total_unrealized_pnl"]["value"] == 20.0
    assert payload["open_order_count"]["status"] == "UNAVAILABLE"


def test_portfolio_defaults_to_latest_daily_artifact(
    api_client: TestClient,
    api_settings,
) -> None:
    write_operator_day(api_settings.reports_root, "2026-08-09", [])
    write_operator_day(api_settings.reports_root, "2026-08-11", [])

    payload = api_client.get("/api/v1/portfolio").json()

    assert payload["day"] == "2026-08-11"
    assert payload["position_count"] == 0
    assert payload["total_market_value"]["value"] == 0


def test_overview_composes_same_day_sources(
    api_client: TestClient,
    api_settings,
) -> None:
    day = "2026-08-10"
    write_operator_day(api_settings.reports_root, day, [])
    write_performance_day(
        api_settings.reports_root,
        day,
        [trade_row("T1", day, 0.01)],
    )

    payload = api_client.get("/api/v1/overview", params={"day": day}).json()

    assert payload["status"] == "AVAILABLE"
    assert payload["read_only"] is True
    assert payload["mode"] == "SIMULATION_MOCK_BROKER"
    assert payload["performance"]["counts"]["trade_count"] == 1
    assert payload["portfolio"]["day"] == day


def test_missing_portfolio_day_is_not_fake_flat(
    api_client: TestClient,
) -> None:
    payload = api_client.get(
        "/api/v1/portfolio",
        params={"day": "2026-08-10"},
    ).json()

    assert payload["status"] == "UNAVAILABLE"
    assert payload["position_count"] == 0
    assert payload["total_market_value"]["value"] is None
    assert payload["issues"] == ["PORTFOLIO_SOURCE_MISSING"]


def test_product_responses_do_not_expose_host_paths(
    api_client: TestClient,
    api_settings,
) -> None:
    day = "2026-08-10"
    write_operator_day(api_settings.reports_root, day, [])
    write_performance_day(api_settings.reports_root, day, [])

    responses = [
        api_client.get("/api/v1/overview", params={"day": day}),
        api_client.get("/api/v1/portfolio", params={"day": day}),
        api_client.get(
            "/api/v1/performance/summary",
            params={"start": day, "end": day},
        ),
    ]

    assert all(str(api_settings.repository_root) not in response.text for response in responses)
