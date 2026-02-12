# libs/event_logger.py
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def new_run_id() -> str:
    """Create a unique run id for a single cycle/run."""
    return uuid.uuid4().hex


def _utc_iso() -> str:
    """UTC ISO timestamp (no microseconds)"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class EventLogger:
    """
    Append-only JSONL event logger.

    - One event per line (JSONL)
    - Minimal schema enforced
    - Creates parent dirs automatically
    """
    log_path: Path

    def __post_init__(self) -> None:
        self.log_path = Path(self.log_path)

    def log(
        self,
        *,
        run_id: str,
        stage: str,
        event: str,
        payload: Optional[Dict[str, Any]] = None,
        ts: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Append one event to JSONL.

        Schema:
        {
          "run_id": "...",
          "ts": "2026-02-07T01:23:45+00:00",
          "stage": "strategist_plan",
          "event": "decision",
          "payload": {...}
        }
        """
        if not run_id or not isinstance(run_id, str):
            raise ValueError("run_id must be a non-empty string")
        if not stage or not isinstance(stage, str):
            raise ValueError("stage must be a non-empty string")
        if not event or not isinstance(event, str):
            raise ValueError("event must be a non-empty string")

        rec: Dict[str, Any] = {
            "run_id": run_id,
            "ts": ts or _utc_iso(),
            "stage": stage,
            "event": event,
            "payload": payload or {},
        }

        # Ensure directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Append atomically-ish (single write) for most OSes
        line = json.dumps(rec, ensure_ascii=False)
        with open(self.log_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

        return rec

    def read_all(self) -> list[Dict[str, Any]]:
        """Convenience reader for local debugging/tests."""
        if not self.log_path.exists():
            return []
        out: list[Dict[str, Any]] = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                out.append(json.loads(line))
        return out
