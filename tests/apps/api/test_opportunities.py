from __future__ import annotations

from fastapi.testclient import TestClient

from artifact_fixtures import write_opportunity_day


def test_opportunity_funnel_uses_latest_signal_per_symbol(
    api_client: TestClient,
    api_settings,
) -> None:
    write_opportunity_day(api_settings.reports_root, "2026-08-13")

    payload = api_client.get(
        "/api/v1/opportunities/funnel",
        params={"day": "2026-08-13"},
    ).json()

    assert payload["status"] == "AVAILABLE"
    assert payload["behavior_effect"] == "SHADOW_ONLY"
    assert payload["signal_count"] == 2
    assert payload["current_signal_count"] == 1
    assert payload["probe_candidate_count"] == 1
    assert payload["current_signals"][0]["price"] == 101.0
    assert payload["blockers"][0]["coverage"] == 0.75


def test_opportunity_outcomes_keep_cost_surfaces_separate(
    api_client: TestClient,
    api_settings,
) -> None:
    write_opportunity_day(api_settings.reports_root, "2026-08-13")

    payload = api_client.get(
        "/api/v1/opportunities/outcomes",
        params={"day": "2026-08-13"},
    ).json()

    assert payload["status"] == "PARTIAL"
    assert payload["behavior_effect"] == "OBSERVATION_ONLY"
    assert payload["coverage"] == 0.5
    checkpoint = payload["outcomes"][0]["checkpoints"][0]
    assert checkpoint["gross_return_pct"] == 1.0
    assert checkpoint["live_equivalent_net_return_pct"] == 0.72
    assert checkpoint["mock_broker_net_return_pct"] == 0.2


def test_missing_opportunity_day_is_truthful_no_data(
    api_client: TestClient,
) -> None:
    payload = api_client.get(
        "/api/v1/opportunities/funnel",
        params={"day": "2026-08-01"},
    ).json()

    assert payload["status"] == "ERROR"
    assert payload["signal_count"] == 0
    assert payload["issues"] == ["MISSING_SOURCE:signals", "MISSING_SOURCE:blockers"]
