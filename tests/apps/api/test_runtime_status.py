from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from apps.api.adapters.runtime_status_artifacts import RuntimeStatusArtifacts
from apps.api.config import ExposureProfile
from apps.api.domain.runtime_status_projection import build_runtime_status_projection
from apps.api.main import create_app


NOW = datetime(2026, 8, 26, 1, 5, tzinfo=UTC)


def _artifacts(
    *,
    lock: dict | None = None,
    process_tree: dict | None = None,
    market_label: str = "regular_session_open",
) -> RuntimeStatusArtifacts:
    watchdog = {
        "generated_at": "2026-08-26T10:04:00+09:00",
        "ok": True,
        "blockers": [],
        "live_after": {
            "lock_pid": 101,
            "process_count": 2,
            "process_tree": process_tree or {},
        },
    }
    market = {
        "updated_at": "2026-08-26T01:00:00+00:00",
        "current": {
            "received_at": "2026-08-26T01:00:00+00:00",
            "code": "R",
            "label": market_label,
        },
    }
    return RuntimeStatusArtifacts(lock or {}, watchdog, market, ())


def test_fresh_heartbeat_and_parent_child_tree_is_running() -> None:
    result = build_runtime_status_projection(
        _artifacts(
            lock={
                "pid": 101,
                "started_ts": "2026-08-26T00:00:00+00:00",
                "heartbeat_ts": "2026-08-26T01:04:00+00:00",
            },
            process_tree={
                "raw_process_count": 2,
                "logical_session_count": 1,
                "tree_state": "NORMAL_PROCESS_TREE",
                "processes": [
                    {"pid": 100, "parent_pid": 1, "is_owner": False},
                    {"pid": 101, "parent_pid": 100, "is_owner": True},
                ],
            },
        ),
        now=NOW,
    )

    assert result.runtime_state == "RUNNING"
    assert result.process.raw_process_count == 2
    assert result.process.logical_session_count == 1
    assert result.lock.heartbeat_age_seconds == 60


def test_two_logical_process_trees_are_duplicate() -> None:
    result = build_runtime_status_projection(
        _artifacts(
            lock={"pid": 101, "heartbeat_ts": "2026-08-26T01:04:00+00:00"},
            process_tree={
                "raw_process_count": 4,
                "logical_session_count": 2,
                "tree_state": "DUPLICATE_SESSION",
                "processes": [],
            },
        ),
        now=NOW,
    )

    assert result.runtime_state == "DUPLICATE"
    assert "DUPLICATE_RUNTIME_SESSION" in result.issues


def test_missing_runtime_during_market_session_is_unexpected() -> None:
    result = build_runtime_status_projection(_artifacts(), now=NOW)

    assert result.runtime_state == "STOPPED_UNEXPECTED"
    assert result.market.expected_running is True


def test_missing_runtime_after_close_is_expected() -> None:
    result = build_runtime_status_projection(
        _artifacts(market_label="regular_session_close"),
        now=datetime(2026, 8, 26, 6, 31, tzinfo=UTC),
    )

    assert result.runtime_state == "STOPPED_EXPECTED"
    assert result.status == "AVAILABLE"


def test_runtime_endpoint_reads_artifacts_without_execution(api_settings) -> None:
    (api_settings.state_root / "m13_live_loop.lock").write_text(
        json.dumps({"pid": 101, "heartbeat_ts": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )
    watchdog_path = api_settings.reports_root / "runtime" / "trading_day_status" / "latest.json"
    watchdog_path.parent.mkdir(parents=True)
    watchdog_path.write_text(
        json.dumps({"generated_at": datetime.now(UTC).isoformat(), "ok": True, "live_after": {}}),
        encoding="utf-8",
    )

    with TestClient(create_app(api_settings)) as client:
        response = client.get("/api/v1/runtime/status")
        post = client.post("/api/v1/runtime/status")

    assert response.status_code == 200
    assert response.json()["runtime_state"] == "RUNNING"
    assert response.json()["read_only"] is True
    assert response.json()["execution_callable"] is False
    assert post.status_code == 405


def test_public_runtime_endpoint_hides_process_identifiers(api_settings) -> None:
    (api_settings.state_root / "m13_live_loop.lock").write_text(
        json.dumps({"pid": 101, "heartbeat_ts": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )
    settings = replace(api_settings, exposure_profile=ExposureProfile.PUBLIC)

    with TestClient(create_app(settings)) as client:
        payload = client.get("/api/v1/runtime/status").json()

    assert payload["lock"]["owner_pid"] is None
    assert payload["process"]["processes"] == []


def test_runtime_endpoint_exposes_supervisor_policy(api_settings) -> None:
    watchdog_path = api_settings.reports_root / "runtime" / "trading_day_status" / "latest.json"
    watchdog_path.parent.mkdir(parents=True)
    watchdog_path.write_text(
        json.dumps({
            "generated_at": datetime.now(UTC).isoformat(),
            "ok": True,
            "supervisor": {
                "policy_version": "host_supervisor.v1",
                "decision": "HEALTHY",
                "decision_reason": "RUNTIME_HEALTHY",
                "restart_count": 1,
                "max_daily_restarts": 3,
                "last_action": "RECOVERED",
                "last_reason": "HEARTBEAT_STALE",
            },
        }),
        encoding="utf-8",
    )

    with TestClient(create_app(api_settings)) as client:
        payload = client.get("/api/v1/runtime/status").json()

    assert payload["supervisor"]["policy_version"] == "host_supervisor.v1"
    assert payload["supervisor"]["restart_count"] == 1
    assert payload["supervisor"]["last_action"] == "RECOVERED"


def test_watchdog_history_endpoint_is_read_only_and_ordered(api_settings) -> None:
    history = api_settings.reports_root / "runtime" / "trading_day_status" / "history" / "2026-08-27"
    history.mkdir(parents=True)
    for stamp, action, before, after in (
        ("090500", "RECOVERED", "STALE", "RUNNING"),
        ("091000", "HEALTHY", "RUNNING", "RUNNING"),
    ):
        tree_before = {"logical_session_count": 1, "tree_state": "NORMAL_PROCESS_TREE"}
        (history / f"20260827{stamp}_watchdog.json").write_text(
            json.dumps({
                "day": "2026-08-27",
                "generated_at": f"2026-08-27T{stamp[:2]}:{stamp[2:4]}:00+09:00",
                "ok": True,
                "live_before": {
                    "running": before != "STOPPED",
                    "heartbeat_age_seconds": 400 if before == "STALE" else 10,
                    "process_tree": tree_before,
                },
                "live_after": {
                    "running": after != "STOPPED",
                    "heartbeat_age_seconds": 4,
                    "process_tree": tree_before,
                },
                "supervisor": {
                    "last_action": action,
                    "last_reason": "HEARTBEAT_STALE" if action == "RECOVERED" else "RUNTIME_HEALTHY",
                    "restart_count": 1,
                    "max_daily_restarts": 3,
                },
                "blockers": [],
            }),
            encoding="utf-8",
        )

    with TestClient(create_app(api_settings)) as client:
        response = client.get("/api/v1/runtime/watchdog-history?limit=10")
        post = client.post("/api/v1/runtime/watchdog-history")

    assert response.status_code == 200
    payload = response.json()
    assert [item["action"] for item in payload["items"]] == ["HEALTHY", "RECOVERED"]
    assert payload["items"][1]["runtime_before"] == "STALE"
    assert payload["items"][1]["runtime_after"] == "RUNNING"
    assert payload["read_only"] is True
    assert payload["execution_callable"] is False
    assert post.status_code == 405


def test_scheduled_intelligence_endpoint_projects_existing_manifests(api_settings) -> None:
    runtime = api_settings.reports_root / "runtime" / "scheduled_jobs"
    runtime.mkdir(parents=True)
    (runtime / "latest_preopen.json").write_text(json.dumps({
        "day": "2026-08-27", "job": "preopen", "generated_at": "2026-08-27T08:51:00+09:00",
        "status": "SUCCESS", "issues": [],
    }), encoding="utf-8")
    briefing = api_settings.reports_root / "briefings" / "2026-08-27" / "preopen_briefing.json"
    briefing.parent.mkdir(parents=True)
    briefing.write_text(json.dumps({
        "memory_delivery": {"status": "DELIVERED_ADVISORY", "source_day": "2026-08-26"},
        "market_frame": {"one_line": "risk-on opening frame"},
    }), encoding="utf-8")

    with TestClient(create_app(api_settings)) as client:
        response = client.get("/api/v1/runtime/scheduled-intelligence")
        post = client.post("/api/v1/runtime/scheduled-intelligence")

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobs"][0]["status"] == "SUCCESS"
    assert payload["jobs"][0]["memory_status"] == "DELIVERED_ADVISORY"
    assert payload["jobs"][1]["status"] == "NOT_RUN"
    assert payload["read_only"] is True
    assert payload["execution_callable"] is False
    assert post.status_code == 405
