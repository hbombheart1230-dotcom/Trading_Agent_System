from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class BoundedReadError(ValueError):
    pass


def read_bytes_bounded(path: Path, *, max_bytes: int) -> bytes:
    if max_bytes <= 0:
        raise BoundedReadError("max_bytes must be positive")
    size = path.stat().st_size
    if size > max_bytes:
        raise BoundedReadError(f"file exceeds read limit: {size} > {max_bytes}")

    with path.open("rb") as handle:
        payload = handle.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise BoundedReadError("file grew beyond read limit while reading")
    return payload


def read_json_bounded(path: Path, *, max_bytes: int) -> Any:
    payload = read_bytes_bounded(path, max_bytes=max_bytes)
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BoundedReadError(f"invalid UTF-8 JSON: {path.name}") from exc
