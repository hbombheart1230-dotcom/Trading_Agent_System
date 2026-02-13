from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


class IntentStore:
    """Very small persistence for supervisor intents.

    Stores JSONL records:
      {"ts": 1234567890, "intent_id": "...", "intent": {...}}
    """

    def __init__(self, path: str = "data/logs/intents.jsonl"):
        self.path = Path(path)

    def save(self, intent: Dict[str, Any]) -> None:
        intent_id = str(intent.get("intent_id") or "")
        if not intent_id:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": int(time.time()), "intent_id": intent_id, "intent": intent}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def load(self, intent_id: str, *, scan_limit: int = 5000) -> Optional[Dict[str, Any]]:
        if not intent_id:
            return None
        if not self.path.exists():
            return None

        # scan from end for speed (approx) - read all lines then reverse
        lines = self.path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines[-scan_limit:]):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if str(rec.get("intent_id")) == str(intent_id):
                intent = rec.get("intent")
                return intent if isinstance(intent, dict) else None
        return None


    def append_row(self, row: Dict[str, Any]) -> None:
        """Append a raw journal row (intent or marker)."""
        if not isinstance(row, dict):
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def load_all_rows(self, *, scan_limit: int = 200000) -> list[Dict[str, Any]]:
        """Load all journal rows (best-effort)."""
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        rows: list[Dict[str, Any]] = []
        for line in lines[-scan_limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if isinstance(r, dict):
                rows.append(r)
        return rows
