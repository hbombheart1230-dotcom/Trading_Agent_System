from __future__ import annotations

from libs.reporting.opening_rank1_shadow.latent_forward import (
    _fresh_triggers,
    _observe,
)


def test_fresh_trigger_uses_first_signal_only() -> None:
    payload = {
        "rows": [{
            "watch_id": "W1", "initial_episode_id": "E1", "initial_day": "2026-08-03", "symbol": "005930",
            "redetections": [
                {"first_signal_evidence": {"day": "2026-08-05", "decision_id": "D2", "decision_epoch": 200, "rank": 2, "signal_evidence": {"evidence_count": 1}}},
                {"first_signal_evidence": {"day": "2026-08-04", "decision_id": "D1", "decision_epoch": 100, "rank": 1, "signal_evidence": {"evidence_count": 1}}},
            ],
        }]
    }
    rows = _fresh_triggers(payload)
    assert len(rows) == 1
    assert rows[0]["trigger_decision_id"] == "D1"


def test_forward_reference_is_next_minute_open() -> None:
    row = {"trigger_epoch": 100, "symbol": "005930", "trigger_day": "2026-08-03"}
    candles = [
        {"ts": 100, "open": 99, "high": 101, "low": 98, "close": 100},
        {"ts": 160, "open": 101, "high": 103, "low": 100, "close": 102},
        {"ts": 460, "open": 104, "high": 105, "low": 103, "close": 104},
    ]
    result = _observe(row, candles)
    assert result["reference_entry"] == {
        "epoch": 160, "price": 101.0, "source": "next_available_minute_open"
    }
    assert result["checkpoints"]["+5m"]["gross_return_pct"] == 2.9703
