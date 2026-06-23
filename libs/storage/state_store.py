from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


_BROKER_TRUTH_MARKER = "broker_truth_position_reconciliation"
_BROKER_TRUTH_PROTECTED_KEYS = (
    "mock_positions",
    "open_positions",
    "closeout_unresolved_flatten_by_symbol",
    "closeout_backup_liquidation",
    _BROKER_TRUTH_MARKER,
)


def _broker_truth_revision(state: Dict[str, Any]) -> float:
    marker = state.get(_BROKER_TRUTH_MARKER)
    if not isinstance(marker, dict) or not bool(marker.get("authoritative")):
        return 0.0
    text = str(marker.get("generated_at") or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _preserve_newer_broker_truth(state: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    if _broker_truth_revision(current) <= _broker_truth_revision(state):
        return state
    merged = dict(state)
    for key in _BROKER_TRUTH_PROTECTED_KEYS:
        if key in current:
            merged[key] = current[key]
        else:
            merged.pop(key, None)
    return merged


class StateStore:
    """Simple JSON state store.

    Default schema (extensible):
      {
        "last_order_epoch": 0,
        "open_positions": 0,
        "daily_pnl_ratio": 0.0,
        "mock_cash": 0.0,
        "mock_positions": [],
        "mock_realized_pnl": 0.0
      }
    """

    def __init__(self, path: str):
        self.path = Path(path)

    def load(self) -> Dict[str, Any]:
        default_state = {
            "last_order_epoch": 0,
            "open_positions": 0,
            "daily_pnl_ratio": 0.0,
            "mock_cash": 0.0,
            "mock_positions": [],
            "mock_realized_pnl": 0.0,
            "last_trade_side": "",
            "last_trade_epoch": 0,
        }
        if not self.path.exists():
            return dict(default_state)
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return dict(default_state)
            out = dict(default_state)
            out.update(data)
            return out
        except Exception:
            # corrupted -> reset
            return dict(default_state)

    def save(self, state: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        current: Dict[str, Any] = {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                current = loaded
        except Exception:
            current = {}
        state = _preserve_newer_broker_truth(dict(state), current)
        payload = json.dumps(state, ensure_ascii=False, indent=2)
        json.loads(payload)
        tmp_path = self.path.with_name(f"{self.path.name}.tmp.{os.getpid()}.{threading.get_ident()}")
        try:
            with tmp_path.open("w", encoding="utf-8", newline="\n") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
