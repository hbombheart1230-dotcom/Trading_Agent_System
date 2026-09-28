"""Read-only loader for a FROZEN UEF-5.2 ``historical_recompute`` run.

This module never re-derives a canonical number. It only parses the JSON
documents a UEF-5.2 run already wrote to disk (``run_manifest.json``,
``aggregates.json``, ``recompute_summary.json``, ``input_manifest.json``)
and exposes them using the REAL frozen canonical metric contract, read
directly from ``libs/reporting/evaluation/canonical/metrics/contracts.py``
and ``policy.py`` (UEF-3A, frozen):

- ``MetricComputationStatus``: ``VALID | EMPTY_POPULATION | UNDEFINED_METRIC |
  INSUFFICIENT_EVIDENCE | MISSING_EVIDENCE`` -- NOT ``COMPUTED``.
- ``SamplePopulation``: ``sample_count = evaluated_count + missing_count +
  excluded_count``. ``evaluated_count`` is the ONE population both legacy's
  own shared aggregator (``performance_metrics``) and canonical share the
  same definition for (the missing-filtered population a win/loss/flat
  breakdown and profit_factor are actually computed over) -- see that
  contract module's own evidence docstring, which cites
  ``performance_metrics``'s ``len(rows)`` as the source of this exact
  definition. This is the correct population to compare a legacy
  ``summary.horizons[].{view}_{net}.count`` figure against -- NEVER
  ``AggregateRecord.episode_count`` (a lineage/provenance bookkeeping
  field, orthogonal to metric population size; see ``record.py``'s own
  invariant that ``episode_count == 0`` is compatible with
  ``lineage_status == UNKNOWN`` regardless of how large the metric
  population actually is -- UEF-5.2's own aggregate construction never
  wires episode lineage, so ``episode_count`` is 0 for essentially every
  UEF-5.2 aggregate today, VALID non-empty ones included).
- ``WinLossFlatPopulation``: ``win_count + loss_count + flat_count ==
  evaluated_count`` -- persisted directly on ``profit_factor.population``,
  so legacy's own win/loss/flat counts ARE comparable against canonical,
  contrary to this package's first delivery (which wrongly assumed
  canonical persists no win/loss/flat breakdown at all).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


UEF52_RUN_NAMESPACE = "reports/evaluation/uef5/historical_recompute"

# Real MetricComputationStatus members (uef3a_cost_metric.v1), read directly
# from libs/reporting/evaluation/canonical/metrics/contracts.py. Never
# invented; this package must fail loudly (KeyError) rather than silently
# accept an unrecognized status string.
VALID_METRIC_STATUSES = frozenset(
    {"VALID", "EMPTY_POPULATION", "UNDEFINED_METRIC", "INSUFFICIENT_EVIDENCE", "MISSING_EVIDENCE"}
)

# family_key -> the exact provenance["family"] text label UEF-5.2 itself
# writes into aggregates.json / recompute_summary.json (read directly from
# a real run's output, not invented).
FAMILY_LABELS = {
    "q10_semiconductor": "Q10 Semiconductor",
    "q12_calc1": "Q12 Calc1",
    "q12_calc2": "Q12 Calc2",
    "q10_index": "Q10 Index",
    "q11_virtual_probe": "Q11 v2",
}

# Families whose canonical aggregation scope has NO per-view dimension
# (confirmed by reading _pipeline_q12_calc1: it aggregates once per
# horizon_label over a single undifferentiated "decisions" scope, unlike
# _pipeline_q10_semiconductor's per-view aggregation).
FAMILIES_WITHOUT_CANONICAL_VIEW_DIMENSION = frozenset({"q12_calc1"})


@dataclass(frozen=True)
class ArtifactOutcome:
    """One row of UEF-5.2's ``run_manifest.json['artifact_outcomes']``."""

    path: str
    bucket: str
    bucket_detail: str
    bucket_reason: str


@dataclass(frozen=True)
class SamplePopulation:
    sample_count: int
    evaluated_count: int
    missing_count: int
    excluded_count: int


@dataclass(frozen=True)
class WinLossFlatPopulation:
    win_count: Optional[int]
    loss_count: Optional[int]
    flat_count: Optional[int]


@dataclass(frozen=True)
class MetricValue:
    status: str  # one of VALID_METRIC_STATUSES
    unit: Optional[str]
    value: Optional[float]

    def is_valid(self) -> bool:
        return self.status == "VALID"


@dataclass(frozen=True)
class CanonicalAggregate:
    """One aggregate record from UEF-5.2's ``aggregates.json``, read using
    the REAL frozen UEF-3A metric contract (not the first-delivery's
    incorrect assumptions)."""

    family: str
    day: str
    unit_path: str
    view: Optional[str]
    horizon_label: Optional[str]
    canonical_aggregate_id: str
    evaluation_record_id: str
    lineage_status: str
    episode_count: int  # lineage bookkeeping ONLY -- never a population signal
    source_episode_ids: tuple  # the frozen canonical contract's own membership enumeration (may be empty/unwired)
    profit_factor: MetricValue
    pf_population: WinLossFlatPopulation
    pf_sample: Optional[SamplePopulation]
    max_drawdown: MetricValue
    mdd_sample_count_in_curve: Optional[int]

    def derived_win_rate(self) -> Optional[float]:
        """win_count / evaluated_count, using the exact same arithmetic
        legacy's own shared aggregator uses -- never a new metric formula,
        just applying legacy's own definition to canonical's real counts."""

        if self.pf_sample is None or not self.pf_sample.evaluated_count:
            return None
        if self.pf_population.win_count is None:
            return None
        return self.pf_population.win_count / self.pf_sample.evaluated_count


@dataclass(frozen=True)
class CanonicalRun:
    """A fully-loaded, read-only view of one UEF-5.2 recompute run."""

    run_id: str
    run_root: Path
    status: str
    families_summary: list
    outcomes_by_path: dict  # str -> ArtifactOutcome
    aggregates_by_path: dict  # str -> list[CanonicalAggregate]
    recorded_source_hash_by_path: dict  # str -> str (UEF-5.2's own input_manifest.json primary_source_hash)
    content_digest: str = ""  # sha256 over the ACTUAL bytes of this run's own output files (Core Correction 2 item 2B)
    run_manifest_digest_fields: dict = field(default_factory=dict)

    def outcome_for_path(self, path: str) -> Optional[ArtifactOutcome]:
        return self.outcomes_by_path.get(_normalize_path(path))

    def aggregates_for_path(self, path: str) -> list:
        return self.aggregates_by_path.get(_normalize_path(path), [])

    def aggregates_for_family(self, family_key: str) -> list:
        """The full CANONICAL UNIVERSE for one family: every aggregate UEF-5.2
        actually produced, regardless of whether any legacy reader ever
        visits its unit_path. This is what HIGH-3's independent-universe
        enumeration requires -- never built by walking legacy paths."""

        label = FAMILY_LABELS.get(family_key)
        out = []
        for aggs in self.aggregates_by_path.values():
            for a in aggs:
                if a.family == label:
                    out.append(a)
        return out

    def recorded_source_hash_for_path(self, path: str) -> Optional[str]:
        return self.recorded_source_hash_by_path.get(_normalize_path(path))


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def discover_latest_run(repo_root: Path) -> Optional[str]:
    root = repo_root / UEF52_RUN_NAMESPACE
    if not root.is_dir():
        return None
    candidates = [p for p in root.iterdir() if p.is_dir() and (p / "run_manifest.json").is_file()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: (p / "run_manifest.json").stat().st_mtime)
    return candidates[-1].name


def _parse_metric_value(block: Optional[dict]) -> MetricValue:
    envelope = (block or {}).get("metric") or {}
    status = envelope.get("status")
    if status is not None and status not in VALID_METRIC_STATUSES:
        raise ValueError(f"unrecognized MetricComputationStatus {status!r} -- UEF-3A contract has no such member")
    return MetricValue(status=status, unit=envelope.get("unit"), value=envelope.get("value"))


def _parse_sample_population(sample: Optional[dict]) -> Optional[SamplePopulation]:
    if not sample:
        return None
    if "evaluated_count" not in sample or "sample_count" not in sample:
        return None
    return SamplePopulation(
        sample_count=int(sample.get("sample_count", 0) or 0),
        evaluated_count=int(sample.get("evaluated_count", 0) or 0),
        missing_count=int(sample.get("missing_count", 0) or 0),
        excluded_count=int(sample.get("excluded_count", 0) or 0),
    )


def _parse_win_loss_flat(population: Optional[dict]) -> WinLossFlatPopulation:
    population = population or {}
    return WinLossFlatPopulation(
        win_count=population.get("win_count"),
        loss_count=population.get("loss_count"),
        flat_count=population.get("flat_count"),
    )


def compute_canonical_content_digest(run_root: Path) -> str:
    """sha256 over the ACTUAL bytes of this UEF-5.2 run's own output files
    (Core Correction 2 item 2B). Binding only the run_id STRING into
    dual_run_id was insufficient -- if a run's own files are edited in
    place without renaming the run_id folder, comparison output changes
    but dual_run_id previously did not. Every file that actually
    influences comparison output (run_manifest.json's artifact_outcomes,
    aggregates.json, input_manifest.json's recorded hashes) is included,
    hashed in a fixed, deterministic order; a missing file contributes a
    fixed sentinel rather than being silently skipped."""

    parts = []
    for name in ("run_manifest.json", "aggregates.json", "input_manifest.json"):
        p = run_root / name
        if p.is_file():
            parts.append(name.encode("utf-8") + b":" + hashlib.sha256(p.read_bytes()).hexdigest().encode("ascii"))
        else:
            parts.append(name.encode("utf-8") + b":ABSENT")
    return hashlib.sha256(b"|".join(parts)).hexdigest()


def load_canonical_run(repo_root: Path, run_id: str) -> CanonicalRun:
    run_root = repo_root / UEF52_RUN_NAMESPACE / run_id
    run_manifest_path = run_root / "run_manifest.json"
    aggregates_path = run_root / "aggregates.json"
    summary_path = run_root / "recompute_summary.json"
    input_manifest_path = run_root / "input_manifest.json"

    if not run_manifest_path.is_file():
        raise FileNotFoundError(f"no UEF-5.2 run_manifest.json for run_id={run_id!r} at {run_manifest_path}")

    content_digest = compute_canonical_content_digest(run_root)
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    aggregates_doc = json.loads(aggregates_path.read_text(encoding="utf-8")) if aggregates_path.is_file() else {}
    summary_doc = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}

    outcomes_by_path: dict = {}
    for row in run_manifest.get("artifact_outcomes", []) or []:
        p = _normalize_path(row.get("path", ""))
        if not p:
            continue
        outcomes_by_path[p] = ArtifactOutcome(
            path=p,
            bucket=row.get("bucket", ""),
            bucket_detail=row.get("bucket_detail", ""),
            bucket_reason=row.get("bucket_reason", ""),
        )

    recorded_source_hash_by_path: dict = {}
    if input_manifest_path.is_file():
        input_manifest = json.loads(input_manifest_path.read_text(encoding="utf-8"))
        for entry in input_manifest.get("artifacts", []) or []:
            p = _normalize_path(entry.get("primary_source_path") or entry.get("source_artifact") or "")
            h = entry.get("primary_source_hash") or entry.get("sha256")
            if p and h:
                recorded_source_hash_by_path[p] = h

    aggregates_by_path: dict = {}
    for a in aggregates_doc.get("aggregates", []) or []:
        prov = a.get("provenance", {}) or {}
        rec = a.get("record", {}) or {}
        unit_path = _normalize_path(prov.get("unit", ""))
        if not unit_path:
            continue
        metrics = rec.get("metrics", {}) or {}
        identity = rec.get("identity", {}) or {}
        pf_block = metrics.get("profit_factor") or {}
        mdd_block = metrics.get("max_drawdown") or {}
        entry = CanonicalAggregate(
            family=prov.get("family", ""),
            day=prov.get("day", ""),
            unit_path=unit_path,
            view=prov.get("view"),
            horizon_label=prov.get("horizon_label"),
            canonical_aggregate_id=(identity.get("aggregate_ref") or {}).get("canonical_event_id", ""),
            evaluation_record_id=identity.get("evaluation_record_id", ""),
            lineage_status=rec.get("lineage_status", ""),
            source_episode_ids=tuple(rec.get("source_episode_ids") or ()),
            episode_count=int(rec.get("episode_count", 0) or 0),
            profit_factor=_parse_metric_value(pf_block),
            pf_population=_parse_win_loss_flat(pf_block.get("population")),
            pf_sample=_parse_sample_population(pf_block.get("sample") or metrics.get("sample_population")),
            max_drawdown=_parse_metric_value(mdd_block),
            mdd_sample_count_in_curve=mdd_block.get("sample_count_in_curve"),
        )
        aggregates_by_path.setdefault(unit_path, []).append(entry)

    return CanonicalRun(
        run_id=run_manifest.get("run_id", run_id),
        run_root=run_root,
        status=run_manifest.get("status", ""),
        families_summary=summary_doc.get("families", []) or [],
        outcomes_by_path=outcomes_by_path,
        aggregates_by_path=aggregates_by_path,
        recorded_source_hash_by_path=recorded_source_hash_by_path,
        content_digest=content_digest,
        run_manifest_digest_fields={
            "frozen_core_manifest_identity": run_manifest.get("frozen_core_manifest_identity"),
            "semantic_implementation_identity": run_manifest.get("semantic_implementation_identity"),
            "registry_digest": run_manifest.get("registry_digest"),
        },
    )
