from __future__ import annotations

import json
from pathlib import Path

from libs.market.preopen_macro_snapshot import capture_preopen_macro_snapshot


def test_preopen_capture_uses_runtime_state_and_enables_log(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({"policy": {"sentiment_ticker_nasdaq": "^IXIC"}}),
        encoding="utf-8",
    )
    observed = {}

    def fake_compute(*, state, policy):
        observed["state"] = state
        observed["policy"] = policy
        return {"status": "ok", "source": "fixture", "reason": "", "ts": 123}

    result = capture_preopen_macro_snapshot(
        env_path=tmp_path / ".env",
        state_path=state_path,
        compute=fake_compute,
    )

    assert result["phase"] == "preopen"
    assert result["status"] == "ok"
    assert observed["policy"]["macro_indicator_log_enabled"] is True
    assert observed["policy"]["sentiment_ticker_nasdaq"] == "^IXIC"


def test_preopen_capture_tolerates_missing_state(tmp_path: Path) -> None:
    result = capture_preopen_macro_snapshot(
        env_path=tmp_path / ".env",
        state_path=tmp_path / "missing.json",
        compute=lambda **_kwargs: {
            "status": "fallback",
            "source": "fixture",
            "reason": "partial_data",
            "ts": 456,
        },
    )

    assert result["status"] == "fallback"
    assert result["signal_ts"] == 456
