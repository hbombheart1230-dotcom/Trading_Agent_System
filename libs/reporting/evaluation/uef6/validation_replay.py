"""UEF-6C validation-only instrumentation harness.

NOT production runtime architecture. Intercepts the frozen UEF-5.2
historical-recompute pipeline's own aggregation call point
(``historical_recompute.aggregate_canonical_samples``, the exact module-
local name ``_aggregate()`` calls) for the DURATION of one validation
context only, routing it through the approved UEF-6B wrapper so a direct
lineage witness is captured for every real aggregation call -- while
returning ONLY the frozen, unmodified ``AggregateRecord`` back to
UEF-5.2, exactly as if no interception had happened at all.

Never modifies ``historical_recompute.py``, ``aggregate_canonical_samples()``,
or any other frozen file. The patch is installed and restored by
``unittest.mock.patch.object`` (a well-tested, exception-safe stdlib
mechanism), scoped to one ``with`` block, never leaked globally.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence
from unittest import mock

from libs.reporting.evaluation.uef5 import historical_recompute as hr

from .lineage_model import AggregateLineageWitness
from .lineage_witness import aggregate_canonical_samples_with_lineage, lineage_implementation_digest
from .population_dedup import population_semantic_digest as episode_population_semantic_digest
from .run_identity import detector_implementation_digest as uef6a_implementation_digest


class UEF6ValidationError(Exception):
    """Base class for UEF-6C-local validation errors."""


class UEF6SnapshotIntegrityError(UEF6ValidationError):
    """Raised when a file copied into an isolated validation snapshot does
    not match its recorded historical sha256 -- fail closed, never
    silently proceed on unverified bytes."""


class UEF6ReplayParityError(UEF6ValidationError):
    """Raised (by the caller, using ``compare_recompute_runs``'s result) when
    an instrumented replay's canonical output is not semantically identical
    to an uninstrumented baseline replay over the SAME isolated snapshot."""


# ---------------------------------------------------------------------------
# Interception
# ---------------------------------------------------------------------------


class _AggregationRecorder:
    """Callable replacement for ``historical_recompute.aggregate_canonical_samples``
    during validation. Calls the frozen aggregator EXACTLY ONCE per
    invocation (via ``aggregate_canonical_samples_with_lineage``), returns
    only the frozen ``AggregateRecord`` (matching the original function's
    return type and contract exactly), and captures the witness
    separately."""

    def __init__(self) -> None:
        self.witnesses: list = []
        self.call_count: int = 0

    def __call__(self, **kwargs):
        self.call_count += 1
        result = aggregate_canonical_samples_with_lineage(**kwargs)
        self.witnesses.append(result.witness)
        return result.aggregate_record


@contextmanager
def intercept_aggregation_for_validation():
    """Validation-only context manager. Patches
    ``historical_recompute.aggregate_canonical_samples`` -- the exact
    module-local name ``_aggregate()`` calls -- for the duration of the
    ``with`` block only. Restored on ANY exit, including an exception
    (``unittest.mock.patch.object``'s own guarantee). Yields the recorder
    (``.witnesses``, ``.call_count``)."""

    recorder = _AggregationRecorder()
    with mock.patch.object(hr, "aggregate_canonical_samples", recorder):
        yield recorder


def original_aggregator_is_restored() -> bool:
    """True iff ``historical_recompute.aggregate_canonical_samples`` is
    currently the frozen module-level function object (not a validation
    recorder) -- the regression this module's own tests assert after every
    ``intercept_aggregation_for_validation`` use, success or exception."""

    from libs.reporting.evaluation.canonical.metrics.aggregation import aggregate_canonical_samples as frozen_fn

    return hr.aggregate_canonical_samples is frozen_fn


# ---------------------------------------------------------------------------
# Isolated historical snapshot construction (Mode B input)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotFileEntry:
    path: str
    recorded_sha256: str
    copied_sha256: str


@dataclass(frozen=True)
class SnapshotManifest:
    target_uef52_run_id: str
    files: Sequence[SnapshotFileEntry]

    def to_dict(self) -> dict:
        return {
            "target_uef52_run_id": self.target_uef52_run_id,
            "file_count": len(self.files),
            "files": [{"path": f.path, "recorded_sha256": f.recorded_sha256} for f in self.files],
        }


def build_isolated_snapshot(repo_root: Path, uef52_run_id: str, snapshot_root: Path) -> SnapshotManifest:
    """Reconstructs, in ``snapshot_root``, an ISOLATED copy of exactly the
    files the target UEF-5.2 run's own ``input_manifest.json`` recorded as
    discovered (``primary_source_path`` + every ``companion_artifacts``
    path), each byte-verified against its recorded historical sha256.
    Fails closed (``UEF6SnapshotIntegrityError``) if the CURRENT repo's
    copy of any file no longer matches the historically recorded hash --
    this never silently assumes current bytes equal historical bytes."""

    repo_root = Path(repo_root)
    snapshot_root = Path(snapshot_root)
    run_root = repo_root / hr.OUTPUT_NAMESPACE / uef52_run_id
    input_manifest_path = run_root / "input_manifest.json"
    if not input_manifest_path.is_file():
        raise FileNotFoundError(f"no input_manifest.json for UEF-5.2 run_id={uef52_run_id!r} at {input_manifest_path}")

    input_manifest = json.loads(input_manifest_path.read_text(encoding="utf-8"))

    wanted: dict = {}  # rel_path -> recorded_sha256
    for art in input_manifest.get("artifacts", []):
        path = art.get("primary_source_path") or art.get("source_artifact")
        sha = art.get("primary_source_hash") or art.get("sha256")
        if path and sha:
            wanted[path] = sha
        for companion in art.get("companion_artifacts", []) or []:
            c_path, c_sha = companion.get("path"), companion.get("sha256")
            if c_path and c_sha:
                wanted[c_path] = c_sha

    # Also mirror the SAME fixed, bounded set of semantic-implementation
    # code files (historical_recompute.py's own `_SEMANTIC_IMPLEMENTATION_FILES`)
    # and the freeze-manifest doc that `semantic_implementation_identity`/
    # `frozen_core_manifest_identity` resolve relative to `repo_root` --
    # without these, a snapshot replay's own run_id would trivially never
    # match the real historical run's run_id (empty implementation-identity
    # dict vs a real one), making item 18's historical-parity linking check
    # impossible to ever pass honestly. These are CODE files (never
    # `reports/evaluation/` data), not part of the "1109 discovered
    # artifacts" input population -- copied with the same byte-verification
    # discipline.
    for rel_path in hr._SEMANTIC_IMPLEMENTATION_FILES:
        if rel_path not in wanted:
            source_path = repo_root / rel_path
            if source_path.is_file():
                wanted[rel_path] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    freeze_manifest_rel = hr._FREEZE_MANIFEST_PATH
    if freeze_manifest_rel not in wanted and (repo_root / freeze_manifest_rel).is_file():
        wanted[freeze_manifest_rel] = hashlib.sha256((repo_root / freeze_manifest_rel).read_bytes()).hexdigest()

    entries = []
    for rel_path in sorted(wanted.keys()):
        recorded_sha = wanted[rel_path]
        source_path = repo_root / rel_path
        if not source_path.is_file():
            raise UEF6SnapshotIntegrityError(
                f"snapshot build: {rel_path!r} no longer exists in the current repository at all -- "
                "cannot build an isolated snapshot without it"
            )
        actual_bytes = source_path.read_bytes()
        actual_sha = hashlib.sha256(actual_bytes).hexdigest()
        if actual_sha != recorded_sha:
            raise UEF6SnapshotIntegrityError(
                f"snapshot build: {rel_path!r} current bytes (sha256={actual_sha}) do not match the "
                f"historically recorded sha256={recorded_sha} -- refusing to assume current bytes equal "
                "historical bytes; this file has been modified since the target run was generated"
            )
        dest_path = snapshot_root / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(actual_bytes)
        entries.append(SnapshotFileEntry(path=rel_path, recorded_sha256=recorded_sha, copied_sha256=actual_sha))

    return SnapshotManifest(target_uef52_run_id=uef52_run_id, files=tuple(entries))


# ---------------------------------------------------------------------------
# Baseline vs instrumented replay + parity
# ---------------------------------------------------------------------------


@dataclass
class ReplayResult:
    run: object  # historical_recompute.RecomputeRun
    witnesses: Sequence[AggregateLineageWitness]
    aggregate_call_count: int


def run_baseline_replay(snapshot_root: Path) -> ReplayResult:
    """Uninstrumented: the frozen pipeline, untouched, no interception at all."""

    run = hr.run_historical_recompute(Path(snapshot_root), out_root=None)
    return ReplayResult(run=run, witnesses=(), aggregate_call_count=0)


def run_instrumented_replay(snapshot_root: Path) -> ReplayResult:
    """Instrumented: the SAME frozen pipeline entry point, with aggregation
    calls intercepted for the duration of this one call only."""

    with intercept_aggregation_for_validation() as recorder:
        run = hr.run_historical_recompute(Path(snapshot_root), out_root=None)
        witnesses = tuple(recorder.witnesses)
        call_count = recorder.call_count
    if not original_aggregator_is_restored():
        raise UEF6ValidationError("validation instrumentation failed to restore the original frozen aggregator -- refusing to report a result")
    return ReplayResult(run=run, witnesses=witnesses, aggregate_call_count=call_count)


@dataclass(frozen=True)
class ParityComparison:
    identical: bool
    differences: Sequence[str]


def compare_recompute_runs(baseline_run, instrumented_run) -> ParityComparison:
    """Compares canonical semantic output ONLY -- run_id, status, summary,
    serialized episodes, serialized aggregates, input_manifest,
    run_manifest. Byte-identical where the frozen pipeline's own output is
    already deterministic (it is: no datetime.now(), no randomness -- see
    historical_recompute.py's own module docstring)."""

    differences = []
    if baseline_run.run_id != instrumented_run.run_id:
        differences.append(f"run_id: {baseline_run.run_id!r} != {instrumented_run.run_id!r}")
    if baseline_run.status != instrumented_run.status:
        differences.append(f"status: {baseline_run.status!r} != {instrumented_run.status!r}")
    if json.dumps(baseline_run.summary, sort_keys=True) != json.dumps(instrumented_run.summary, sort_keys=True):
        differences.append("summary differs")
    baseline_episodes = hr._serialize_episodes(baseline_run.episodes)
    instrumented_episodes = hr._serialize_episodes(instrumented_run.episodes)
    if baseline_episodes != instrumented_episodes:
        differences.append("serialized episodes.jsonl content differs")
    baseline_aggregates = hr._serialize_aggregates(baseline_run.aggregates)
    instrumented_aggregates = hr._serialize_aggregates(instrumented_run.aggregates)
    if baseline_aggregates != instrumented_aggregates:
        differences.append("serialized aggregates.json content differs")
    if json.dumps(baseline_run.input_manifest, sort_keys=True) != json.dumps(instrumented_run.input_manifest, sort_keys=True):
        differences.append("input_manifest semantic content differs")
    if json.dumps(baseline_run.run_manifest, sort_keys=True) != json.dumps(instrumented_run.run_manifest, sort_keys=True):
        differences.append("run_manifest semantic content differs")
    return ParityComparison(identical=not differences, differences=tuple(differences))


# ---------------------------------------------------------------------------
# UEF-6C validation semantic digests (Final Audit items A/1-8) -- order-
# independent, multiplicity-sensitive, full-content multiset digests. Never
# sort/dedupe by evaluation_record_id alone: two rows can legitimately
# share it (evaluator_version variants for episodes; differing aggregation
# context for aggregates), and a stable sort keyed only on that field
# leaves ties in their ORIGINAL input order -- making the digest (and
# therefore UEF6C_RUN_ID) sensitive to source row order, which item 5/21
# forbids.
# ---------------------------------------------------------------------------


def aggregate_population_semantic_digest(aggregates: Sequence[tuple]) -> str:
    """Order-independent MULTISET digest over the full canonical
    ``(AggregateRecord, provenance_meta)`` collection -- same construction
    as UEF-6A's own ``population_semantic_digest`` (reused directly for
    episodes below): each row is canonicalized IN FULL (the complete
    ``AggregateRecord.to_dict()`` plus its own provenance meta -- family/
    unit/horizon_label/day, which IS semantically part of what
    distinguishes two aggregates sharing one ``evaluation_record_id``),
    the resulting canonical JSON strings are sorted (fixing a
    deterministic order regardless of input order), and the sorted list is
    hashed as one JSON array. Deliberately a MULTISET, not a set:
    ``[A, B]`` and ``[A, B, B]`` MUST digest differently."""

    rows = sorted(
        json.dumps(
            {"record": agg.to_dict(), "provenance": dict(meta)},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        )
        for agg, meta in aggregates
    )
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# UEF-6C validation run identity (item 21)
# ---------------------------------------------------------------------------

VALIDATION_SCHEMA_VERSION = "uef6c_historical_validation.v1"
# Final Audit item B/9: every UEF-6C module capable of changing validation
# SEMANTICS (witness<->aggregate accounting, population coverage,
# duplicate-member totals, cross-aggregate reuse -- all in
# lineage_coverage.py) must be covered by this digest, not just this file.
# Tests only, and CLI-only presentation code that does not affect the
# semantic result, are deliberately excluded (item 9).
_VALIDATION_IMPLEMENTATION_FILES = ("validation_replay.py", "lineage_coverage.py")


def validation_implementation_digest() -> str:
    package_dir = Path(__file__).resolve().parent
    parts = []
    for name in _VALIDATION_IMPLEMENTATION_FILES:
        p = package_dir / name
        content = p.read_bytes() if p.is_file() else b"ABSENT"
        parts.append(name.encode("utf-8") + b":" + hashlib.sha256(content).hexdigest().encode("ascii"))
    return hashlib.sha256(b"|".join(parts)).hexdigest()


def _content_digest(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


NOT_LINKED_TO_FROZEN_HISTORICAL_RESULT = "NOT_LINKED_TO_FROZEN_HISTORICAL_RESULT"
LINKED_TO_FROZEN_HISTORICAL_RESULT = "LINKED_TO_FROZEN_HISTORICAL_RESULT"


def link_witnesses_to_frozen_result(parity: ParityComparison) -> str:
    """Item 18: a replay witness may be associated with the frozen
    historical result ONLY if replay canonical output == target frozen
    canonical output. Never transfers a lineage claim across non-
    equivalent runs."""

    return LINKED_TO_FROZEN_HISTORICAL_RESULT if parity.identical else NOT_LINKED_TO_FROZEN_HISTORICAL_RESULT


def compute_uef6c_run_id(
    *,
    target_uef52_run_id: str,
    target_episodes_digest: str,
    target_aggregates_digest: str,
    uef6a_impl_digest: str,
    uef6b_impl_digest: str,
    uef6c_impl_digest: str,
    effective_replay_config_digest: str,
    validation_schema_version: str = VALIDATION_SCHEMA_VERSION,
) -> str:
    payload = {
        "target_uef52_run_id": target_uef52_run_id,
        "target_episodes_digest": target_episodes_digest,
        "target_aggregates_digest": target_aggregates_digest,
        "uef6a_impl_digest": uef6a_impl_digest,
        "uef6b_impl_digest": uef6b_impl_digest,
        "uef6c_impl_digest": uef6c_impl_digest,
        "effective_replay_config_digest": effective_replay_config_digest,
        "validation_schema_version": validation_schema_version,
    }
    return f"UEF6CRUN_{_content_digest(payload)[:16]}"
