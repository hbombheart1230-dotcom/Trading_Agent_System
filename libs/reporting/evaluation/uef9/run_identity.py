"""Deterministic identity helpers for the UEF-9 authority contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


_IMPLEMENTATION_FILES = ("__init__.py", "model.py", "authority.py", "run_identity.py")


def canonical_string_sequence_digest(values: Sequence[str]) -> str:
    """Hash a sorted, multiplicity-sensitive sequence of authority IDs."""

    payload = json.dumps(sorted(str(value) for value in values), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_mapping_digest(value: Mapping[str, Any]) -> str:
    """Digest an already-frozen authority object without interpreting it."""

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_uef8_authority_digest(value: Mapping[str, Any]) -> str:
    """Digest UEF-8 authority with non-semantic collection order removed."""

    projection = dict(value)
    projection["candidate_ids"] = sorted(str(item) for item in list(value.get("candidate_ids") or []))
    projection["pairs"] = sorted(
        (dict(item) for item in list(value.get("pairs") or [])),
        key=lambda item: str(item.get("comparison_pair_id") or ""),
    )
    return canonical_mapping_digest(projection)


def uef9_implementation_digest() -> str:
    package_dir = Path(__file__).resolve().parent
    parts = []
    for name in _IMPLEMENTATION_FILES:
        path = package_dir / name
        content = path.read_bytes() if path.is_file() else b"ABSENT"
        parts.append(name.encode("utf-8") + b":" + hashlib.sha256(content).hexdigest().encode("ascii"))
    return hashlib.sha256(b"|".join(parts)).hexdigest()


def compute_uef9_run_id(
    *,
    source_uef7_run_id: str,
    verified_uef7_normalized_rows_digest: str,
    source_uef8_run_id: str,
    uef9_derived_uef8_authority_digest: str,
    candidate_ids_digest: str,
    comparison_pair_ids_digest: str,
    uef9_implementation_digest_value: str,
    schema_version: str,
    authority_contract_version: str,
) -> str:
    payload = {
        "source_uef7_run_id": source_uef7_run_id,
        "verified_uef7_normalized_rows_digest": verified_uef7_normalized_rows_digest,
        "source_uef8_run_id": source_uef8_run_id,
        "uef9_derived_uef8_authority_digest": uef9_derived_uef8_authority_digest,
        "candidate_ids_digest": candidate_ids_digest,
        "comparison_pair_ids_digest": comparison_pair_ids_digest,
        "uef9_implementation_digest": uef9_implementation_digest_value,
        "schema_version": schema_version,
        "authority_contract_version": authority_contract_version,
    }
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "UEF9RUN_" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "canonical_string_sequence_digest",
    "canonical_mapping_digest",
    "canonical_uef8_authority_digest",
    "uef9_implementation_digest",
    "compute_uef9_run_id",
]
