"""UEF-6A run identity: binds output identity to the exact SEMANTIC input
and implementation -- never to source-file row ordering.

UEF-6A Order-Independent Run Identity Fix: the run id is derived from
``population_semantic_digest`` (an order-independent MULTISET digest of
the loaded ``EpisodeRecord`` population -- see
``population_dedup.population_semantic_digest``), NOT from the raw
``episodes.jsonl`` byte hash. The raw byte hash remains available
separately as pure source-artifact provenance (``raw_episodes_content_sha256``
in the input manifest) -- it answers "are these the exact source bytes",
while the semantic digest answers "is this the exact same population,
regardless of row order". A changed episode's semantic content or a
changed detector implementation both change ``UEF6A_RUN_ID``; permuting
row order, or a repeated identical execution, both reproduce the same one.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .report_model import REPORT_SCHEMA_VERSION

# The uef6 package's own source files that determine detector semantics --
# hashed together so "detector implementation changes -> run id changes"
# is automatic and content-derived (same pattern as UEF-5.3's
# reader_implementation_digest), never a manually-bumped version string.
_IMPLEMENTATION_FILES = (
    "report_model.py",
    "population_dedup.py",
    "loader.py",
    "run_identity.py",
    "reporter.py",
    "run_uef6a.py",
)


def detector_implementation_digest() -> str:
    package_dir = Path(__file__).resolve().parent
    parts = []
    for name in _IMPLEMENTATION_FILES:
        p = package_dir / name
        content = p.read_bytes() if p.is_file() else b"ABSENT"
        parts.append(name.encode("utf-8") + b":" + hashlib.sha256(content).hexdigest().encode("ascii"))
    return hashlib.sha256(b"|".join(parts)).hexdigest()


def compute_uef6a_run_id(
    source_uef52_run_id: str,
    population_semantic_digest: str,
    detector_implementation_digest_value: str,
    report_schema_version: str = REPORT_SCHEMA_VERSION,
) -> str:
    """Binds ``source_uef52_run_id`` + the order-independent
    ``population_semantic_digest`` + the detector's own implementation
    digest + the report schema version. Deliberately does NOT take the raw
    ``episodes.jsonl`` byte hash -- row ordering must never affect this id."""

    payload = json.dumps(
        {
            "source_uef52_run_id": source_uef52_run_id,
            "population_semantic_digest": population_semantic_digest,
            "detector_implementation_digest": detector_implementation_digest_value,
            "report_schema_version": report_schema_version,
        },
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"UEF6ARUN_{digest}"
