from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)
    text = str(ts).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except Exception:
        pass
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def tail_text(value: str, *, max_chars: int = 2000) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def parse_stdout_json(stdout_text: str) -> Dict[str, Any]:
    body = str(stdout_text or "").strip()
    if not body:
        return {}
    try:
        obj = json.loads(body)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {}


def latest_event_epoch(event_log_path: Path, *, max_tail_lines: int = 2000) -> Optional[int]:
    if not event_log_path.exists():
        return None
    tail: deque[str] = deque(maxlen=max(100, int(max_tail_lines)))
    with event_log_path.open("r", encoding="utf-8") as file:
        for line in file:
            tail.append(line)
    for raw in reversed(tail):
        line = str(raw or "").strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        epoch = to_epoch(obj.get("ts"))
        if epoch is not None:
            return int(epoch)
    return None
