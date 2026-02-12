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
        "daily_pnl_ratio": 0.0
      }
    """

    def __init__(self, path: str):
        self.path = Path(path)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {
                "last_order_epoch": 0,
                "open_positions": 0,
                "daily_pnl_ratio": 0.0,
            }
        try:
            with self.path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # corrupted -> reset
            return {
                "last_order_epoch": 0,
                "open_positions": 0,
                "daily_pnl_ratio": 0.0,
            }

    def save(self, state: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
