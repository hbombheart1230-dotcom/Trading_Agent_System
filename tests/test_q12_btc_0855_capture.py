from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from libs.reporting.baseline_btc_woori_tech.point_in_time_capture import (
    capture_paths,
    capture_q12_btc_0855_snapshot,
    load_captured_sources,
)


KST = timezone(timedelta(hours=9))
DAY = "2026-08-31"


def _epoch(hour: int, minute: int) -> int:
    return int(datetime(2026, 8, 31, hour, minute, tzinfo=KST).timestamp())


def _loader(*, day: str) -> dict:
    assert day == DAY
    return {
        "sources": {
            "btc_usd": [
                {
                    "ts": _epoch(8, 54),
                    "raw_ts": "20260831085400",
                    "price": 100.0,
                    "momentum_24h_pct": 5.2,
                }
            ],
            "btc_krw": [
                {
                    "ts": _epoch(8, 53),
                    "raw_ts": "20260831085300",
                    "price": 140000000.0,
                    "momentum_24h_pct": 5.0,
                }
            ],
        }
    }


def test_q12_0855_capture_is_immutable_and_writes_daily_ledger(tmp_path) -> None:
    result = capture_q12_btc_0855_snapshot(
        day=DAY,
        root=tmp_path,
        now=datetime(2026, 8, 31, 8, 55, 10, tzinfo=KST),
        signal_loader=_loader,
    )
    second = capture_q12_btc_0855_snapshot(
        day=DAY,
        root=tmp_path,
        now=datetime(2026, 8, 31, 8, 57, tzinfo=KST),
        signal_loader=lambda **_: {},
    )

    assert result["capture_status"] == "CAPTURED"
    assert result["snapshot_submitted"] is True
    assert second == result
    assert load_captured_sources(DAY, root=tmp_path)["btc_usd"][0]["momentum_24h_pct"] == 5.2
    ledger = json.loads(capture_paths(DAY, root=tmp_path)["ledger"].read_text(encoding="utf-8"))
    assert ledger["latest_status"] == "CAPTURED"
    assert ledger["snapshot_submitted"] is True
    assert ledger["attempt_count"] == 1
    assert ledger["attempts"][0]["source_count"] == 2


def test_q12_0855_late_attempt_is_recorded_as_missed_without_backfill(tmp_path) -> None:
    result = capture_q12_btc_0855_snapshot(
        day=DAY,
        root=tmp_path,
        now=datetime(2026, 8, 31, 9, 0, tzinfo=KST),
        signal_loader=_loader,
    )

    assert result["capture_status"] == "MISSED"
    assert result["snapshot_submitted"] is False
    assert load_captured_sources(DAY, root=tmp_path) == {}


def test_q12_data_provider_reuses_frozen_0855_source(monkeypatch) -> None:
    from libs.reporting.baseline_btc_woori_tech import data_provider
    from libs.reporting.baseline_btc_woori_tech import point_in_time_capture

    monkeypatch.setattr(data_provider, "_yf_rows", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        point_in_time_capture,
        "load_captured_sources",
        lambda day: {
            "btc_usd": [
                {
                    "ts": _epoch(8, 54),
                    "raw_ts": "20260831085400",
                    "price": 100.0,
                    "momentum_24h_pct": 5.2,
                }
            ]
        },
    )

    payload = data_provider.load_btc_signal_rows(day=DAY)

    assert payload["btc_0855_capture_reused"] is True
    assert payload["sources"]["btc_usd"][0]["momentum_24h_pct"] == 5.2
