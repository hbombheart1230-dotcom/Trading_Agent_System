"""UEF-8 deterministic run identity.

Binds: the source UEF-7 run id, an order-independent semantic digest over
UEF-7's own normalized rows (never trusting the upstream run id alone as
a stand-in for content), UEF-8's own implementation digest, UEF-8's
schema version, and the fair-comparison policy version. Never a
wall-clock timestamp.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

# Every UEF-8 module capable of changing comparison-validity SEMANTIC
# output. Never the CLI (orchestration only) and never tests. Reporter is
# excluded -- presentation only, never treated as semantic authority.
_IMPLEMENTATION_FILES = ("model.py", "fair_comparison.py", "run_identity.py")


def uef7_normalized_rows_semantic_digest(normalized_rows: Sequence[Mapping[str, Any]]) -> str:
    """Order-independent, multiplicity-sensitive digest over UEF-7's own
    already-normalized candidate rows -- the same canonical-multiset-digest
    construction used throughout UEF-6/UEF-7 (sort full canonical row
    serializations, hash the sorted list as one JSON array). Input row
    order never changes this digest; row content does."""

    rows = sorted(
        json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
        for row in normalized_rows
    )
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def uef8_implementation_digest() -> str:
    package_dir = Path(__file__).resolve().parent
    parts = []
    for name in _IMPLEMENTATION_FILES:
        p = package_dir / name
        content = p.read_bytes() if p.is_file() else b"ABSENT"
        parts.append(name.encode("utf-8") + b":" + hashlib.sha256(content).hexdigest().encode("ascii"))
    return hashlib.sha256(b"|".join(parts)).hexdigest()


def compute_uef8_run_id(
    *,
    source_uef7_run_id: str,
    uef7_normalized_semantic_digest: str,
    uef8_implementation_digest_value: str,
    schema_version: str,
    fair_comparison_policy_version: str,
) -> str:
    payload = {
        "source_uef7_run_id": source_uef7_run_id,
        "uef7_normalized_semantic_digest": uef7_normalized_semantic_digest,
        "uef8_implementation_digest": uef8_implementation_digest_value,
        "schema_version": schema_version,
        "fair_comparison_policy_version": fair_comparison_policy_version,
    }
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"UEF8RUN_{digest}"


__all__ = [
    "uef7_normalized_rows_semantic_digest",
    "uef8_implementation_digest",
    "compute_uef8_run_id",
]
