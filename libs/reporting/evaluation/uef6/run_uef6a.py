"""UEF-6A filesystem-run orchestrator.

Ties together: loader (episodes.jsonl -> EpisodeRecord list, fail-closed) ->
pure classifier (``analyze_episode_population``) -> run identity -> writer.
Read-only against the UEF-5.2 run it reads; never regenerates or modifies it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .loader import load_episodes_jsonl
from .population_dedup import analyze_episode_population, population_semantic_digest as _population_semantic_digest
from .report_model import PopulationDedupReport, REPORT_SCHEMA_VERSION
from .run_identity import compute_uef6a_run_id, detector_implementation_digest

UEF52_RUN_NAMESPACE = "reports/evaluation/uef5/historical_recompute"


@dataclass
class UEF6ARunResult:
    uef6a_run_id: str
    source_uef52_run_id: str
    raw_episodes_content_sha256: str
    """Pure source-artifact provenance: the exact bytes of episodes.jsonl as
    read from disk. NOT the semantic population identity -- two files with
    the same EpisodeRecord multiset in a different row order have
    DIFFERENT raw hashes but the SAME population_semantic_digest/run id."""
    population_semantic_digest: str
    """Order-independent MULTISET digest of the loaded EpisodeRecord
    population. THIS is what UEF6A_RUN_ID binds to."""
    detector_implementation_digest: str
    report_schema_version: str
    report: PopulationDedupReport

    def input_manifest(self) -> dict:
        return {
            "source_uef52_run_id": self.source_uef52_run_id,
            "raw_episodes_content_sha256": self.raw_episodes_content_sha256,
            "population_semantic_digest": self.population_semantic_digest,
            "detector_implementation_digest": self.detector_implementation_digest,
            "report_schema_version": self.report_schema_version,
        }


def run_uef6a_dedup_detection(repo_root: Path, uef52_run_id: str) -> UEF6ARunResult:
    """Read-only against ``reports/evaluation/uef5/historical_recompute/<uef52_run_id>/episodes.jsonl``.
    Never regenerates or modifies the UEF-5.2 run.

    UEF6A_RUN_ID is derived from the order-independent
    ``population_semantic_digest``, never from ``raw_episodes_content_sha256``
    (row-order-only permutation of the same source file must reproduce the
    identical run id and semantic report)."""

    repo_root = Path(repo_root)
    episodes_path = repo_root / UEF52_RUN_NAMESPACE / uef52_run_id / "episodes.jsonl"
    if not episodes_path.is_file():
        raise FileNotFoundError(f"no episodes.jsonl for UEF-5.2 run_id={uef52_run_id!r} at {episodes_path}")

    episodes, raw_episodes_content_sha256 = load_episodes_jsonl(episodes_path)
    report = analyze_episode_population(episodes)
    semantic_digest = _population_semantic_digest(episodes)
    impl_digest = detector_implementation_digest()
    uef6a_run_id = compute_uef6a_run_id(uef52_run_id, semantic_digest, impl_digest, REPORT_SCHEMA_VERSION)

    return UEF6ARunResult(
        uef6a_run_id=uef6a_run_id,
        source_uef52_run_id=uef52_run_id,
        raw_episodes_content_sha256=raw_episodes_content_sha256,
        population_semantic_digest=semantic_digest,
        detector_implementation_digest=impl_digest,
        report_schema_version=REPORT_SCHEMA_VERSION,
        report=report,
    )
