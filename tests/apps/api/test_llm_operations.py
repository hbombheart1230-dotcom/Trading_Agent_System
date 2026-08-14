from __future__ import annotations

from fastapi.testclient import TestClient

from artifact_fixtures import (
    write_llm_call,
    write_llm_events,
    write_trade_bundle,
    write_trade_llm_response,
)


def test_llm_operations_aggregates_stages_models_and_latency(
    api_client: TestClient,
    api_settings,
) -> None:
    day = "2026-08-14"
    write_llm_call(
        api_settings.reports_root,
        day,
        "run-stage1",
        stage_index=1,
        stage_name="market_frame",
    )
    write_llm_call(
        api_settings.reports_root,
        day,
        "run-stage2",
        stage_index=2,
        stage_name="selected_symbol_tactical_refresh",
        status="failed",
    )
    write_llm_events(api_settings.logs_root, day)
    _, trade_root = write_trade_bundle(api_settings.reports_root, day=day)
    write_trade_llm_response(trade_root, "ai_trade_report_llm_response.json")
    write_trade_llm_response(trade_root, "ai_trade_summary_llm_response.json")

    response = api_client.get("/api/v1/llm/operations", params={"day": day})
    assert response.status_code == 200
    payload = response.json()

    assert payload["total_calls"] == 4
    assert payload["success_count"] == 3
    assert payload["failure_count"] == 1
    assert payload["latency"]["observed_count"] == 2
    assert payload["latency"]["average_ms"] == 2000
    assert payload["latency"]["p95_ms"] == 3000
    assert payload["token_usage"]["status"] == "UNAVAILABLE"
    assert payload["token_usage"]["total_tokens"] is None
    assert [stage["stage_index"] for stage in payload["stages"][:2]] == [1, 2]


def test_llm_operations_exposes_observed_and_configured_models(
    api_client: TestClient,
    api_settings,
) -> None:
    day = "2026-08-14"
    write_llm_call(
        api_settings.reports_root,
        day,
        "run-1",
        stage_index=1,
        stage_name="market_frame",
    )
    write_llm_events(api_settings.logs_root, day)

    payload = api_client.get(
        "/api/v1/llm/operations",
        params={"day": day},
    ).json()
    roles = {row["role"]: row for row in payload["roles"]}

    assert roles["strategist"]["observed_model"] == "deepseek/deepseek-v3.2"
    assert roles["strategist"]["fallback_model"] == "minimax/minimax-m2.5"
    assert roles["trade_report"]["configured_model"] == "minimax/minimax-m2.5"
    assert roles["trade_report"]["state"] == "ROUTING_WARNING"
    assert any("nvidia/nemotron" in issue for issue in payload["issues"])


def test_llm_operations_never_returns_prompt_or_response_text(
    api_client: TestClient,
    api_settings,
) -> None:
    day = "2026-08-14"
    write_llm_call(
        api_settings.reports_root,
        day,
        "run-1",
        stage_index=1,
        stage_name="market_frame",
    )
    write_llm_events(api_settings.logs_root, day)

    body = api_client.get(
        "/api/v1/llm/operations",
        params={"day": day},
    ).text

    assert "SENSITIVE_PROMPT" not in body
    assert "SENSITIVE_RESPONSE" not in body
    assert "response_text" not in body


def test_llm_operations_reports_no_data_without_artifacts(
    api_client: TestClient,
) -> None:
    payload = api_client.get(
        "/api/v1/llm/operations",
        params={"day": "2026-08-14"},
    ).json()

    assert payload["status"] == "NO_DATA"
    assert payload["total_calls"] == 0
    assert payload["success_rate"] is None


def test_llm_operations_uses_token_values_only_when_recorded(
    api_client: TestClient,
    api_settings,
) -> None:
    day = "2026-08-14"
    write_llm_call(
        api_settings.reports_root,
        day,
        "run-1",
        stage_index=1,
        stage_name="market_frame",
    )
    write_llm_events(api_settings.logs_root, day, include_usage=True)

    usage = api_client.get(
        "/api/v1/llm/operations",
        params={"day": day},
    ).json()["token_usage"]

    assert usage["status"] == "AVAILABLE"
    assert usage["prompt_tokens"] == 100
    assert usage["completion_tokens"] == 50
    assert usage["total_tokens"] == 150
    assert usage["estimated_cost_usd"] == 0.002
