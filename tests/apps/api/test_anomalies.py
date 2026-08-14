from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from apps.api.adapters.source_freshness import FreshnessObservation
from apps.api.domain.anomaly_rules import AnomalyPolicy, evaluate_freshness
from artifact_fixtures import write_opportunity_day, write_trade_bundle


def _make_loss(root, *, hold_seconds: float = 30.0) -> None:
    path = root / "reports" / "ai_trade_summary_input.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["truth_surface"].update({"pnl": -1000.0, "pnl_pct": -0.01, "result_label": "loss"})
    payload["strategy_horizon"]["actual_hold_sec"] = hold_seconds
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_anomaly_endpoint_classifies_explainable_operating_signals(
    api_client: TestClient,
    api_settings,
) -> None:
    _, first = write_trade_bundle(api_settings.reports_root, "2026-08-13", "005930", "01")
    _, second = write_trade_bundle(api_settings.reports_root, "2026-08-13", "005930", "02")
    _make_loss(first)
    _make_loss(second)
    write_opportunity_day(api_settings.reports_root, "2026-08-13")
    outcome_path = (
        api_settings.reports_root
        / "evaluation"
        / "opening_rank1_shadow"
        / "2026-08-13"
        / "opening_rank1_shadow_daily.json"
    )
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    episode = outcome["episodes"][0]
    episode["symbol"] = "000660"
    episode["episode_id"] = "OPEN:2026-08-13:000660:1"
    episode["checkpoints"]["+30m"] = {
        "status": "observed",
        "mock_net_return_pct": 1.25,
        "live_net_return_pct": 1.5,
        "gross_return_pct": 1.8,
    }
    outcome_path.write_text(json.dumps(outcome), encoding="utf-8")

    payload = api_client.get(
        "/api/v1/anomalies",
        params={"day": "2026-08-13"},
    ).json()

    categories = [row["category"] for row in payload["items"]]
    assert payload["status"] == "AVAILABLE"
    assert payload["behavior_effect"] == "OBSERVATION_ONLY"
    assert payload["evaluated_trade_count"] == 2
    assert categories.count("REPEATED_LOSS") == 1
    assert categories.count("EARLY_LOSS_EXIT") == 2
    assert categories.count("COST_SPIKE") == 2
    assert categories.count("MISSED_OPPORTUNITY") == 1
    assert len({row["anomaly_id"] for row in payload["items"]}) == len(payload["items"])


def test_anomaly_ids_and_order_are_deterministic(api_client, api_settings) -> None:
    _, root = write_trade_bundle(api_settings.reports_root, "2026-08-12", "005930", "01")
    _make_loss(root)

    first = api_client.get("/api/v1/anomalies", params={"day": "2026-08-12"}).json()
    second = api_client.get("/api/v1/anomalies", params={"day": "2026-08-12"}).json()

    assert [row["anomaly_id"] for row in first["items"]] == [
        row["anomaly_id"] for row in second["items"]
    ]


def test_freshness_rule_only_alarms_during_market_session() -> None:
    policy = AnomalyPolicy()
    observation = FreshnessObservation(
        source="runtime_events",
        available=True,
        modified_at=datetime(2026, 8, 14, 0, 0, tzinfo=UTC),
        age_seconds=1000,
    )

    market = evaluate_freshness(
        observation,
        now=datetime(2026, 8, 14, 0, 20, tzinfo=UTC),
        policy=policy,
    )
    after_hours = evaluate_freshness(
        observation,
        now=datetime(2026, 8, 14, 10, 0, tzinfo=UTC),
        policy=policy,
    )

    assert market[0].severity == "CRITICAL"
    assert after_hours == []
