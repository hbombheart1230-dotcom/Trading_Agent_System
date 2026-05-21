from __future__ import annotations

from libs.reporting.live_execution_report_context import trade_time_bucket_from_lifecycle_bundle


def test_trade_time_bucket_prefers_trade_lifecycle_entry_ts(monkeypatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    bucket = trade_time_bucket_from_lifecycle_bundle(
        {
            "ts": "2026-05-19T01:40:10+00:00",
            "trade_lifecycle": {
                "entry": {"ts": "2026-05-19T00:38:42+00:00"},
                "exit": {"ts": "2026-05-19T00:42:53+00:00"},
            },
        }
    )

    assert bucket == "0900"
