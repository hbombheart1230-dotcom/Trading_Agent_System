"""Observation evidence and cross-process manifest serialization (no trading policy)."""
from __future__ import annotations

import math
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


@contextmanager
def manifest_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix('.lock'), 'a+b') as handle:
        # Windows permits byte-range locks beyond EOF. Do not initialize
        # the byte: that write itself races an existing process's lock.
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def valid_price(row: Mapping[str, Any]) -> bool:
    try:
        price = float(row.get('current'))
        return math.isfinite(price) and price > 0
    except (TypeError, ValueError):
        return False


def market_epoch(row: Mapping[str, Any]) -> float | None:
    value = row.get('market_observed_at') or row.get('quote_timestamp')
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def verified_components(indices, *, scheduled_epoch: int, observed_epoch: int, is_close: bool) -> bool:
    if not indices:
        return False
    for row in indices.values():
        timestamp = market_epoch(row)
        # A local request timestamp is not market-side evidence. Permit only
        # the existing checkpoint's 90-second observation tolerance.
        if not valid_price(row) or timestamp is None or not scheduled_epoch <= timestamp <= scheduled_epoch + 90:
            return False
        if timestamp > observed_epoch + 5:
            return False
        if is_close and not any(row.get(key) is True for key in ('session_finalized', 'close_finalized')):
            return False
    return True
