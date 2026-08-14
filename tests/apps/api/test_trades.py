from __future__ import annotations

from fastapi.testclient import TestClient

from artifact_fixtures import write_trade_bundle


def test_trade_list_maps_normalized_truth(
    api_client: TestClient,
    api_settings,
) -> None:
    trade_id, _ = write_trade_bundle(api_settings.reports_root)

    payload = api_client.get(
        "/api/v1/trades",
        params={"start": "2026-08-10", "end": "2026-08-10"},
    ).json()

    assert payload["status"] == "AVAILABLE"
    assert payload["total_count"] == 1
    trade = payload["items"][0]
    assert trade["trade_id"] == trade_id
    assert trade["symbol_name"] == "Samsung Electronics"
    assert trade["realized_return_pct"] == 1.8
    assert trade["realized_pnl_krw"] == 1800.0
    assert trade["scanner_rank"] == 1


def test_trade_list_filters_and_defaults_to_latest_day(
    api_client: TestClient,
    api_settings,
) -> None:
    write_trade_bundle(api_settings.reports_root, "2026-08-09", "000660")
    latest_id, _ = write_trade_bundle(api_settings.reports_root, "2026-08-11")

    latest = api_client.get("/api/v1/trades").json()
    filtered = api_client.get(
        "/api/v1/trades",
        params={
            "start": "2026-08-09",
            "end": "2026-08-11",
            "symbol": "000660",
        },
    ).json()

    assert [row["trade_id"] for row in latest["items"]] == [latest_id]
    assert filtered["total_count"] == 1
    assert filtered["items"][0]["symbol"] == "000660"


def test_trade_detail_builds_bounded_timeline_and_lineage(
    api_client: TestClient,
    api_settings,
) -> None:
    trade_id, _ = write_trade_bundle(api_settings.reports_root, excluded=True)

    payload = api_client.get(f"/api/v1/trades/{trade_id}").json()

    assert payload["status"] == "PARTIAL"
    assert [row["stage"] for row in payload["timeline"]] == [
        "ENTRY",
        "HOLD",
        "EXIT",
    ]
    assert payload["decisions"]["scanner_score"] == 0.63
    assert payload["decisions"]["tactic_id"] == "confirmed_breakout"
    assert payload["post_exit"][0]["return_pct"] == 0.98
    integrity = payload["integrity"]
    assert integrity["evaluation_eligible"] is False
    assert integrity["exclusion_reason"] == "confirmed_runtime_defect"
    assert "HOLD_EVENT_OUTSIDE_LIFECYCLE" in integrity["issues"]


def test_large_lifecycle_bundle_is_not_read(
    api_client: TestClient,
    api_settings,
) -> None:
    trade_id, root = write_trade_bundle(api_settings.reports_root)
    (root / "lifecycle_bundle.json").write_bytes(b"x" * (api_settings.max_report_bytes + 1))

    response = api_client.get(f"/api/v1/trades/{trade_id}")

    assert response.status_code == 200
    assert response.json()["trade"]["trade_id"] == trade_id


def test_invalid_trade_identifier_cannot_escape_trade_root(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/trades/..%2F..%2F.env")

    assert response.status_code == 404


def test_missing_display_identity_marks_trade_partial(
    api_client: TestClient,
    api_settings,
) -> None:
    trade_id, root = write_trade_bundle(api_settings.reports_root)
    summary_path = root / "reports" / "ai_trade_summary_input.json"
    import json

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["trade"]["symbol_name"] = ""
    summary_path.write_text(json.dumps(payload), encoding="utf-8")

    response = api_client.get(
        "/api/v1/trades",
        params={"start": "2026-08-10", "end": "2026-08-10"},
    ).json()

    assert response["status"] == "PARTIAL"
    assert response["items"][0]["artifact_status"] == "PARTIAL"
    assert f"PARTIAL_TRADE_ARTIFACT:{trade_id}" in response["issues"]


def test_performance_row_without_bundle_remains_visible(
    api_client: TestClient,
    api_settings,
) -> None:
    from artifact_fixtures import trade_row, write_performance_day

    trade_id = "TRD_20260810_000660_09"
    write_performance_day(
        api_settings.reports_root,
        "2026-08-10",
        [trade_row(trade_id, "2026-08-10", -0.01, -1000.0)],
    )

    listing = api_client.get(
        "/api/v1/trades",
        params={"start": "2026-08-10", "end": "2026-08-10"},
    ).json()
    detail = api_client.get(f"/api/v1/trades/{trade_id}").json()

    assert listing["total_count"] == 1
    assert listing["items"][0]["artifact_scope"] == "PERFORMANCE_FALLBACK"
    assert f"TRADE_BUNDLE_MISSING:{trade_id}" in listing["issues"]
    assert detail["status"] == "PARTIAL"
    assert detail["timeline"] == []
    assert detail["integrity"]["issues"] == ["TRADE_BUNDLE_MISSING"]
