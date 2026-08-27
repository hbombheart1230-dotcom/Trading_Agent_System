from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


_VOLATILE_KEYS = {
    "generated_at",
    "updated_at",
    "captured_at",
    "created_at",
    "timestamp",
}


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(raw)
            for key, raw in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key) not in _VOLATILE_KEYS
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def stable_evidence_id(prefix: str, payload: Any) -> str:
    """Return a stable content ID without volatile artifact timestamps."""
    encoded = json.dumps(
        _canonical(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:20]
    clean_prefix = "".join(ch for ch in str(prefix).lower() if ch.isalnum() or ch in "_-")
    return f"{clean_prefix or 'evidence'}_{digest}"


__all__ = ["stable_evidence_id"]
