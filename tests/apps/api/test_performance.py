from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from artifact_fixtures import trade_row, write_performance_day


def test_period_performance_uses_truth_surface_net_only(
    api_client: TestClient,
    api_settings,
) -> None:
    write_performance_day(
        api_settings.reports_root,
        "2026-08-10",
        [
            trade_row("T1", "2026-08-10", 0.02, 2000.0),
            trade_row("T2", "2026-08-10", -0.01, -1000.0),
            trade_row("T3", "2026-08-10", None),
        ],
    )
    write_performance_day(
        api_settings.reports_root,
        "2026-08-11",
        [trade_row("T4", "2026-08-11", 0.0)],
    )

    response = api_client.get(
        "/api/v1/performance/summary",
        params={"start": "2026-08-10", "end": "2026-08-11"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "PARTIAL"
    assert payload["counts"] == {
        "trade_count": 4,
        "resolved_count": 3,
        "unresolved_count": 1,
        "win_count": 1,
        "loss_count": 1,
        "flat_count": 1,
    }
    assert payload["win_rate"]["value"] == 0.5
    assert payload["average_trade_return"]["value"] == pytest.approx(1 / 3)
    assert payload["profit_factor"]["value"] == 2.0
    assert payload["max_drawdown"]["value"] == 1.0
    assert payload["realized_pnl"]["value"] == 1000.0
    assert payload["gross_pnl"]["status"] == "UNAVAILABLE"
    assert payload["cost_drag"]["value"] is None


def test_series_preserves_no_trade_day_without_fake_zero(
    api_client: TestClient,
    api_settings,
) -> None:
    write_performance_day(api_settings.reports_root, "2026-08-10", [])

    payload = api_client.get(
        "/api/v1/performance/series",
        params={"start": "2026-08-10", "end": "2026-08-10"},
    ).json()

    assert payload["status"] == "NO_DATA"
    assert payload["points"][0]["status"] == "NO_DATA"
    assert payload["points"][0]["average_trade_return_pct"] is None
    assert payload["points"][0]["realized_pnl_krw"] is None


def test_series_accumulates_only_trusted_realized_pnl(
    api_client: TestClient,
    api_settings,
) -> None:
    write_performance_day(
        api_settings.reports_root,
        "2026-08-10",
        [trade_row("T1", "2026-08-10", 0.01, 1000.0)],
    )
    write_performance_day(
        api_settings.reports_root,
        "2026-08-11",
        [trade_row("T2", "2026-08-11", -0.01, -400.0)],
    )

    payload = api_client.get(
        "/api/v1/performance/series",
        params={"start": "2026-08-10", "end": "2026-08-11"},
    ).json()

    assert [point["realized_pnl_krw"] for point in payload["points"]] == [
        1000.0,
        -400.0,
    ]
    assert [point["cumulative_realized_pnl_krw"] for point in payload["points"]] == [
        1000.0,
        600.0,
    ]


def test_unsupported_cost_basis_is_explicitly_unavailable(
    api_client: TestClient,
    api_settings,
) -> None:
    write_performance_day(
        api_settings.reports_root,
        "2026-08-10",
        [trade_row("T1", "2026-08-10", 0.02)],
    )

    payload = api_client.get(
        "/api/v1/performance/summary",
        params={
            "start": "2026-08-10",
            "end": "2026-08-10",
            "cost_basis": "GROSS",
        },
    ).json()

    assert payload["status"] == "UNAVAILABLE"
    assert payload["average_trade_return"]["value"] is None
    assert "not available" in payload["average_trade_return"]["reason"]


def test_invalid_performance_json_returns_error_not_500(
    api_client: TestClient,
    api_settings,
) -> None:
    target = api_settings.reports_root / "performance" / "2026-08-10" / "summary.json"
    target.parent.mkdir(parents=True)
    target.write_text("{invalid", encoding="utf-8")

    response = api_client.get(
        "/api/v1/performance/summary",
        params={"start": "2026-08-10", "end": "2026-08-10"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ERROR"
    assert response.json()["invalid_source_day_count"] == 1


def test_period_range_is_bounded(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/performance/summary",
        params={"start": "2020-01-01", "end": "2026-08-10"},
    )

    assert response.status_code == 400
