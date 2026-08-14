from __future__ import annotations

import json
from dataclasses import replace

from fastapi.testclient import TestClient

from apps.api.config import ExposureProfile
from apps.api.infrastructure.public_sanitization import sanitize_public_payload
from apps.api.main import create_app
from artifact_fixtures import write_trade_bundle
from artifact_fixtures import trade_row, write_performance_day


def test_public_profile_is_server_side_and_keeps_truthful_mode(api_settings) -> None:
    settings = replace(api_settings, exposure_profile=ExposureProfile.PUBLIC)
    with TestClient(create_app(settings)) as client:
        profile = client.get("/api/v1/profile").json()
        health = client.get("/health/ready").json()

    assert profile["profile"] == "public"
    assert profile["public_mode"] is True
    assert profile["execution_mode"] == "SIMULATION_MOCK"
    assert profile["metric_contract"] == "SAME_AS_PRIVATE_PROFILE"
    assert profile["report_content_access"] is False
    assert health["public_mode"] is True
    assert health["execution_callable"] is False


def test_public_profile_disables_raw_report_content(api_settings) -> None:
    trade_id, _ = write_trade_bundle(api_settings.reports_root)
    settings = replace(api_settings, exposure_profile=ExposureProfile.PUBLIC)
    with TestClient(create_app(settings)) as client:
        catalog = client.get(f"/api/v1/trades/{trade_id}/reports").json()
        content = client.get(
            f"/api/v1/trades/{trade_id}/reports/ai-summary"
        ).json()

    assert catalog["status"] == "UNAVAILABLE"
    assert catalog["reports"] == []
    assert content["status"] == "UNAVAILABLE"
    assert content["markdown"] is None
    assert content["json_content"] is None


def test_public_profile_redacts_sensitive_values_from_domain_responses(api_settings) -> None:
    trade_id, root = write_trade_bundle(api_settings.reports_root)
    entry_path = root / "entry.json"
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["reason_human"] = (
        r"source C:\secret\orders.json account 1234 Bearer abcdefghijklmnop"
    )
    entry_path.write_text(json.dumps(entry), encoding="utf-8")
    settings = replace(api_settings, exposure_profile=ExposureProfile.PUBLIC)

    with TestClient(create_app(settings)) as client:
        body = client.get(f"/api/v1/trades/{trade_id}").text

    assert r"C:\secret" not in body
    assert "abcdefghijklmnop" not in body
    assert "1234" not in body
    assert "[redacted-path]" in body
    assert "[redacted-credential]" in body


def test_public_sanitizer_removes_forbidden_keys_recursively() -> None:
    payload = sanitize_public_payload(
        {
            "safe": 1,
            "nested": {
                "order_id": "123",
                "prompt": "secret",
                "response_text": "secret",
                "source_path": r"C:\private\file.json",
            },
        }
    )

    assert payload == {"safe": 1, "nested": {}}


def test_public_profile_keeps_private_performance_formula(api_settings) -> None:
    write_performance_day(
        api_settings.reports_root,
        "2026-08-10",
        [trade_row("TRD_20260810_005930_01", "2026-08-10", 0.01, 1000.0)],
    )
    params = {"start": "2026-08-10", "end": "2026-08-10"}
    with TestClient(create_app(api_settings)) as client:
        private = client.get("/api/v1/performance/summary", params=params).json()
    settings = replace(api_settings, exposure_profile=ExposureProfile.PUBLIC)
    with TestClient(create_app(settings)) as client:
        public = client.get("/api/v1/performance/summary", params=params).json()

    for field in ("counts", "cost_basis", "win_rate", "average_trade_return", "realized_pnl"):
        assert public[field] == private[field]
