from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from libs.core.settings import load_env_file
from libs.market.global_sentiment import compute_global_sentiment_signal


def _load_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def capture_preopen_macro_snapshot(
    *,
    env_path: Path = Path(".env"),
    state_path: Path = Path("data/state.json"),
    compute: Callable[..., Mapping[str, Any]] = compute_global_sentiment_signal,
) -> dict[str, Any]:
    load_env_file(env_path)
    state = _load_state(state_path)
    policy = dict(state.get("policy") or {}) if isinstance(state.get("policy"), Mapping) else {}
    policy.setdefault("macro_indicator_log_enabled", True)
    signal = dict(compute(state=state, policy=policy))
    return {
        "schema_version": "preopen_macro_snapshot_capture.v1",
        "phase": "preopen",
        "status": signal.get("status") or "unavailable",
        "source": signal.get("source") or "",
        "reason": signal.get("reason") or "",
        "signal_ts": signal.get("ts"),
    }
