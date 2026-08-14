from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from artifact_fixtures import write_trade_bundle


def _set_trade_result(root, *, playbook: str, pnl_pct: float) -> None:
    path = root / "reports" / "ai_trade_summary_input.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["market_and_strategy"]["playbook"] = playbook
    payload["truth_surface"]["pnl_pct"] = pnl_pct
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_strategy_breakdown_is_deterministic_and_net_based(
    api_client: TestClient,
    api_settings,
) -> None:
    _, first = write_trade_bundle(api_settings.reports_root, sequence="01")
    _, second = write_trade_bundle(api_settings.reports_root, sequence="02")
    _set_trade_result(first, playbook="breakout", pnl_pct=0.02)
    _set_trade_result(second, playbook="breakout", pnl_pct=-0.01)

    payload = api_client.get(
        "/api/v1/strategies/performance",
        params={
            "start": "2026-08-10",
            "end": "2026-08-10",
            "dimension": "playbook",
        },
    ).json()

    item = payload["items"][0]
    assert payload["cost_basis"] == "MOCK_BROKER_NET"
    assert item["trade_count"] == 2
    assert item["win_rate"] == 0.5
    assert item["average_return_pct"] == pytest.approx(0.5)
    assert item["profit_factor"] == 2.0
    assert item["max_drawdown_pct"] == 1.0


def test_strategy_range_is_bounded(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/strategies/performance",
        params={"start": "2020-01-01", "end": "2026-08-10"},
    )

    assert response.status_code == 400
