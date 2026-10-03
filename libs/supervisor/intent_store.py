from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from libs.core.path_isolation import resolve_runtime_write_path

_DEFAULT_INTENT_STORE_PATH = "data/logs/intents.jsonl"


class IntentStore:
    """Very small persistence for supervisor intents.

    Stores JSONL records:
      {"ts": 1234567890, "intent_id": "...", "intent": {...}}
    """

    def __init__(self, path: str = _DEFAULT_INTENT_STORE_PATH):
        # Call-time isolation check -- see intent_state_store.py for why this
        # cannot be baked into the default parameter expression itself.
        # resolve_runtime_write_path (not isolate_canonical_path_for_pytest's
        # exact-literal match) so any repository-relative path is isolated
        # under pytest, not just the exact canonical default.
        self.path = resolve_runtime_write_path(path)

    @staticmethod
    def _ts_iso_utc(ts_epoch: int) -> str:
        dt = datetime.fromtimestamp(int(ts_epoch), tz=timezone.utc)
        return dt.replace(microsecond=0).isoformat()

    @staticmethod
    def _ts_iso_kst(ts_epoch: int) -> str:
        kst = timezone(timedelta(hours=9))
        dt = datetime.fromtimestamp(int(ts_epoch), tz=timezone.utc).astimezone(kst)
        return dt.replace(microsecond=0).isoformat()

    def _ensure_ts_fields(self, row: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row or {})
        try:
            ts_epoch = int(float(out.get("ts") or int(time.time())))
        except Exception:
            ts_epoch = int(time.time())
        out["ts"] = ts_epoch
        out.setdefault("ts_iso_utc", self._ts_iso_utc(ts_epoch))
        out.setdefault("ts_kst", self._ts_iso_kst(ts_epoch))
        return out

    def save(self, intent: Dict[str, Any]) -> None:
        intent_id = str(intent.get("intent_id") or "")
        if not intent_id:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rec = self._ensure_ts_fields({"ts": int(time.time()), "intent_id": intent_id, "intent": intent})
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
        row = self._ensure_ts_fields(row)
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
