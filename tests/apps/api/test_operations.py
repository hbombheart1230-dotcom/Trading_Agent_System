from __future__ import annotations

import json


def _write_day(api_settings, day: str, *, regime: str, playbook: str, trade_count: int, issue: str | None = None) -> None:
    runtime = api_settings.reports_root / "runtime" / "scheduled_jobs" / day
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "preopen.json").write_text(json.dumps({
        "day": day,
        "job": "preopen",
        "generated_at": f"{day}T08:51:00+09:00",
        "status": "SUCCESS",
        "issues": [],
        "steps": {"market_snapshot": {"status": "SUCCESS"}},
    }), encoding="utf-8")
    (runtime / "closeout.json").write_text(json.dumps({
        "day": day,
        "job": "closeout",
        "generated_at": f"{day}T16:02:00+09:00",
        "status": "SUCCESS",
        "issues": [],
        "steps": {"daily_summary": {"status": "SUCCESS"}},
        "memory": {"status": "GENERATED", "sync": {"total_trades": trade_count}},
    }), encoding="utf-8")
    briefing = api_settings.reports_root / "briefings" / day / "preopen_briefing.json"
    briefing.parent.mkdir(parents=True, exist_ok=True)
    briefing.write_text(json.dumps({
        "market_frame": {
            "one_line": f"{regime} fixture",
            "regime": regime,
            "playbook": playbook,
            "risk_tone": "normal",
        },
        "entry_frame": {"permission_level": "conditional"},
        "memory_delivery": {"status": "DELIVERED_ADVISORY"},
        "issues": [issue] if issue else [],
    }), encoding="utf-8")


def test_operations_dashboard_combines_timeline_alerts_and_day_comparison(api_client, api_settings) -> None:
    _write_day(api_settings, "2026-08-27", regime="neutral", playbook="pullback", trade_count=2)
    _write_day(
        api_settings,
        "2026-08-28",
        regime="risk_on",
        playbook="breakout",
        trade_count=0,
        issue="GLOBAL_SENTIMENT_MISSING",
    )

    response = api_client.get("/api/v1/operations")
    post = api_client.post("/api/v1/operations")

    assert response.status_code == 200
    payload = response.json()
    assert payload["day"] == "2026-08-28"
    assert payload["previous_day"] == "2026-08-27"
    assert payload["read_only"] is True
    assert payload["execution_callable"] is False
    assert [row["phase"] for row in payload["timeline"]] == ["preopen", "closeout"]
    comparison = {row["metric"]: row for row in payload["comparison"]}
    assert comparison["시장 국면"]["current_value"] == "risk_on"
    assert comparison["시장 국면"]["previous_value"] == "neutral"
    assert comparison["시장 국면"]["change"] == "변경"
    assert comparison["거래 수"]["current_value"] == "0"
    assert any(row["detail"] == "GLOBAL_SENTIMENT_MISSING" for row in payload["alerts"])
    assert post.status_code == 405


def test_operations_dashboard_returns_no_data_without_scheduled_artifacts(api_client) -> None:
    response = api_client.get("/api/v1/operations")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "NO_DATA"
    assert payload["timeline"] == []
    assert payload["issues"] == ["SCHEDULED_INTELLIGENCE_NOT_FOUND"]
