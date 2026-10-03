"""UEF-7 deterministic run identity.

Binds: the source Alpha Board's own semantic content digest, UEF-7's own
implementation digest, and the normalization schema version. Never a
wall-clock timestamp -- ``alpha_board_semantic_digest`` hashes an explicit
Alpha Board v2 CONTRACT-SURFACE projection, never the raw input mapping.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

# Every UEF-7 module capable of changing normalized SEMANTIC output.
# Never the CLI (orchestration only) and never tests.
_IMPLEMENTATION_FILES = ("model.py", "alpha_board_normalization.py", "run_identity.py")

# Defect B fix: the explicit, authoritative Alpha Board v2 top-level
# semantic contract surface, as `canonicalize_board()` actually builds it
# (libs/reporting/alpha_research_board/canonical.py) -- never the raw
# input mapping's own keys. A contract-EXTERNAL top-level field (e.g. a
# caller-added `generated_at`, or any other field this list does not name)
# is structurally excluded from the digest, so it can never silently
# influence UEF-7's semantic identity while also being invisible to it.
# This list is NOT Alpha Board's own contract module -- it is UEF-7's own
# read-only projection of that module's already-frozen output shape;
# Alpha Board's contract module itself is never touched to support this.
_BOARD_CONTRACT_SURFACE_FIELDS = (
    "schema_version",
    "contract_version",
    "behavior_effect",
    "through_day",
    "authority",
    "cost_authority",
    "questions",
    "candidate_count",
    "candidate_ids",
    "row_columns",
    "feature_columns",
    "candidates",
    "closeout_summary",
    "settled_findings",
    "integrity",
    "sources",
    "behavior_change_authorized",
)


def board_contract_surface_projection(board: Mapping[str, Any]) -> dict:
    """The UEF-7-local semantic projection of an Alpha Board v2 payload --
    exactly the fields ``_BOARD_CONTRACT_SURFACE_FIELDS`` names, in that
    fixed order, each defaulting to ``None`` when absent (never silently
    skipped, so a genuinely missing contract field is still visible in the
    projection and therefore still semantic). Any OTHER top-level key the
    input mapping carries is never read here."""

    return {name: board.get(name) for name in _BOARD_CONTRACT_SURFACE_FIELDS}


def alpha_board_semantic_digest(board: Mapping[str, Any]) -> str:
    """Canonical, deterministic digest over the Alpha Board v2 CONTRACT-
    SURFACE projection only (Defect B fix) -- sorted keys, fixed
    separators, no wall-clock timestamp introduced by this function
    itself, and no contract-external top-level field (this function never
    reads one)."""

    projection = board_contract_surface_projection(board)
    payload = json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalizer_implementation_digest() -> str:
    package_dir = Path(__file__).resolve().parent
    parts = []
    for name in _IMPLEMENTATION_FILES:
        p = package_dir / name
        content = p.read_bytes() if p.is_file() else b"ABSENT"
        parts.append(name.encode("utf-8") + b":" + hashlib.sha256(content).hexdigest().encode("ascii"))
    return hashlib.sha256(b"|".join(parts)).hexdigest()


def compute_uef7_run_id(
    *,
    source_board_semantic_digest: str,
    normalizer_implementation_digest_value: str,
    normalization_schema_version: str,
) -> str:
    payload = {
        "source_board_semantic_digest": source_board_semantic_digest,
        "normalizer_implementation_digest": normalizer_implementation_digest_value,
        "normalization_schema_version": normalization_schema_version,
    }
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"UEF7RUN_{digest}"


__all__ = [
    "board_contract_surface_projection",
    "alpha_board_semantic_digest",
    "normalizer_implementation_digest",
    "compute_uef7_run_id",
]
