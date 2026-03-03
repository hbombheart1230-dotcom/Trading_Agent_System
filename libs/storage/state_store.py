from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


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
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
