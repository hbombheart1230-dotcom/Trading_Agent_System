from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class JsonlTail:
    rows: list[dict[str, Any]]
    scanned_bytes: int
    file_size: int
    truncated: bool


def read_jsonl_tail(
    path: Path,
    *,
    max_bytes: int,
    max_rows: int,
) -> JsonlTail:
    if max_bytes <= 0 or max_rows <= 0:
        raise ValueError("tail limits must be positive")
    size = path.stat().st_size
    offset = max(0, size - max_bytes)
    with path.open("rb") as handle:
        handle.seek(offset)
        payload = handle.read(max_bytes)
    if offset:
        separator = payload.find(b"\n")
        payload = payload[separator + 1 :] if separator >= 0 else b""
    rows: list[dict[str, Any]] = []
    for raw_line in payload.splitlines():
        try:
            value = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            rows.append(value)
    return JsonlTail(
        rows=rows[-max_rows:],
        scanned_bytes=len(payload),
        file_size=size,
        truncated=offset > 0 or len(rows) > max_rows,
    )
