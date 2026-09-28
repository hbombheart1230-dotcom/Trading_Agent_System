"""UEF-5.3 dual-run orchestrator.

Core Correction 1 rewrite: builds the LEGACY UNIVERSE and CANONICAL
UNIVERSE independently for each family, performs an explicit join, and
accounts for every cell as exactly one of: matched pair, legacy-only,
canonical-only, blocked, non-comparable (HIGH-3). Nothing disappears
because another cell from the same file/path was already processed.

Also builds a deterministic legacy input manifest (content hash of every
legacy artifact actually consumed, verified against UEF-5.2's own recorded
``primary_source_hash`` where available) and binds it into ``dual_run_id``,
so a changed legacy byte always changes the run id (HIGH-2).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import canonical_run as canonical_run_mod
from .comparison_unit import ComparisonRecord
from .divergence_classifier import classify_q10_semiconductor_cell, classify_q11_exit_day, classify_q12_calc1_day
from .legacy_forward_returns import FAMILY_GLOBS, extract_horizon_views, iter_legacy_forward_returns_artifacts
from .legacy_opportunity_engine import extract_q11_exit_day, iter_legacy_q11_artifacts
from .taxonomy import ComparisonResult

NUMERIC_COMPARABLE_FAMILIES = ("q10_semiconductor", "q12_calc1", "q11_virtual_probe")
FAMILIES_WITH_VIEW_DIMENSION = ("q10_semiconductor",)
FAMILIES_WITHOUT_VIEW_DIMENSION = ("q12_calc1",)
FAMILIES_SINGLE_POPULATION = ("q11_virtual_probe",)

DUAL_RUN_OUTPUT_NAMESPACE = "reports/evaluation/uef5_dual_run"
COMPARISON_IMPLEMENTATION_ID = "uef5_3_dual_run.v3"  # bumped for Core Correction 2
TAXONOMY_ID = "uef5_3_taxonomy.v1"

# The actual reader/classifier module source files that determine dual-run
# semantics. Hashed together into `_reader_implementation_digest()` so that
# "reader/profile implementation changes -> dual-run identity changes"
# (Core Correction 2 item 2) is automatic and content-derived, never a
# manually-bumped version string a change could forget to update.
_IMPLEMENTATION_FILES = (
    "canonical_run.py",
    "comparison_unit.py",
    "divergence_classifier.py",
    "legacy_forward_returns.py",
    "legacy_opportunity_engine.py",
    "dual_run.py",
)


def _reader_implementation_digest() -> str:
    package_dir = Path(__file__).resolve().parent
    parts = []
    for name in _IMPLEMENTATION_FILES:
        p = package_dir / name
        content = p.read_bytes() if p.is_file() else b"ABSENT"
        parts.append(name.encode("utf-8") + b":" + hashlib.sha256(content).hexdigest().encode("ascii"))
    return hashlib.sha256(b"|".join(parts)).hexdigest()


@dataclass
class LegacyInputManifestEntry:
    path: str
    sha256: str
    reader_profile_id: str
    recorded_source_hash: Optional[str]
    hash_match: str  # HASH_MATCH | HASH_MISMATCH | NO_RECORDED_HASH

    def to_json(self) -> dict:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "reader_profile_id": self.reader_profile_id,
            "recorded_source_hash": self.recorded_source_hash,
            "hash_match": self.hash_match,
        }


@dataclass
class DualRunResult:
    dual_run_id: str
    uef52_run_id: str
    legacy_input_manifest: list = field(default_factory=list)  # list[LegacyInputManifestEntry]
    legacy_input_manifest_digest: str = ""
    canonical_content_digest: str = ""
    reader_implementation_digest: str = ""
    records: list = field(default_factory=list)  # list[ComparisonRecord]
    parse_errors: list = field(default_factory=list)
    families_compared: list = field(default_factory=list)
    families_non_comparable: list = field(default_factory=list)
    accounting: dict = field(default_factory=dict)

    def counts(self) -> dict:
        total = len(self.records)
        by_result = {r.value: 0 for r in ComparisonResult}
        exact_empty = 0
        exact_nonempty = 0
        cost_policy_nonempty = 0
        for rec in self.records:
            by_result[rec.result.value] += 1
            if rec.result == ComparisonResult.EXACT_MATCH:
                if "EXACT_EMPTY" in rec.detail:
                    exact_empty += 1
                elif "EXACT_NONEMPTY" in rec.detail:
                    exact_nonempty += 1
            if rec.reason is not None and rec.reason.value == "COST_POLICY_DIFFERENCE":
                legacy_count = (rec.legacy or {}).get("count") or 0
                if legacy_count > 0:
                    cost_policy_nonempty += 1
        return {
            "total_comparison_units": total,
            "exact_match": by_result[ComparisonResult.EXACT_MATCH.value],
            "exact_empty": exact_empty,
            "exact_nonempty": exact_nonempty,
            "explained_divergence": by_result[ComparisonResult.EXPLAINED_DIVERGENCE.value],
            "non_comparable": by_result[ComparisonResult.NON_COMPARABLE.value],
            "blocked": by_result[ComparisonResult.BLOCKED.value],
            "unexplained_divergence": by_result[ComparisonResult.UNEXPLAINED_DIVERGENCE.value],
            "cost_policy_difference_nonempty_units": cost_policy_nonempty,
        }

    def top_divergence_reasons(self, limit: int = 10) -> list:
        tally: dict = {}
        for rec in self.records:
            if rec.reason is None:
                continue
            tally[rec.reason.value] = tally.get(rec.reason.value, 0) + 1
        ordered = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
        return [{"reason": k, "count": v} for k, v in ordered[:limit]]


def _compute_dual_run_id(
    uef52_run_id: str,
    family_keys: list,
    legacy_input_manifest_digest: str,
    canonical_content_digest: str,
    reader_implementation_digest: str,
) -> str:
    """Core Correction 2 item 2: binds ALL FOUR identity components a
    dual-run's output actually depends on -- legacy bytes (via the input
    manifest digest), canonical bytes (via the run's own real content
    digest, not just its run_id string), and the reader/classifier
    implementation's own bytes -- so any one of them changing changes this
    id. Never relies on a human-maintained version string alone."""

    payload = json.dumps(
        {
            "uef52_run_id": uef52_run_id,
            "families": sorted(family_keys),
            "legacy_input_manifest_digest": legacy_input_manifest_digest,
            "canonical_content_digest": canonical_content_digest,
            "reader_implementation_digest": reader_implementation_digest,
            "comparison_implementation_id": COMPARISON_IMPLEMENTATION_ID,
            "taxonomy_id": TAXONOMY_ID,
        },
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"UEF53DUAL_{digest}"


def _canonical_only_record(family_key, aggregate, canonical_run_id, canonical_content_digest, reader_implementation_digest) -> ComparisonRecord:
    from .comparison_unit import ComparisonUnitIdentity
    from .taxonomy import DivergenceReason, SourceAlignment

    unit = ComparisonUnitIdentity(
        family=family_key,
        trading_date=aggregate.day,
        source_path=aggregate.unit_path,
        legacy_content_hash="",
        canonical_run_id=canonical_run_id,
        canonical_aggregate_id=aggregate.canonical_aggregate_id,
        canonical_content_digest=canonical_content_digest,
        reader_profile_identity=reader_implementation_digest,
        view=aggregate.view,
        horizon_label=aggregate.horizon_label,
        cost_treatment=None,
    )
    return ComparisonRecord(
        unit=unit,
        source_alignment=SourceAlignment.MISSING_LEGACY_SOURCE,
        result=ComparisonResult.NON_COMPARABLE,
        reason=DivergenceReason.MISSING_INPUT,
        detail=(
            f"canonical produced an aggregate (view={aggregate.view!r} horizon={aggregate.horizon_label!r}) for "
            f"this source path with no corresponding legacy comparison cell -- e.g. a horizon canonical evaluates "
            f"that legacy's own summary.horizons[] never included"
        ),
        legacy=None,
        canonical={
            "canonical_aggregate_id": aggregate.canonical_aggregate_id,
            "evaluated_count": aggregate.pf_sample.evaluated_count if aggregate.pf_sample else None,
            "profit_factor_status": aggregate.profit_factor.status,
            "profit_factor_value": aggregate.profit_factor.value,
        },
        hash_match="NO_RECORDED_HASH",
    )


def run_dual_run(
    repo_root: Path,
    uef52_run_id: Optional[str] = None,
    family_keys: Optional[list] = None,
) -> DualRunResult:
    repo_root = Path(repo_root)

    if uef52_run_id is None:
        uef52_run_id = canonical_run_mod.discover_latest_run(repo_root)
        if uef52_run_id is None:
            raise FileNotFoundError(
                f"no UEF-5.2 historical_recompute run found under {repo_root / canonical_run_mod.UEF52_RUN_NAMESPACE}"
            )

    canonical = canonical_run_mod.load_canonical_run(repo_root, uef52_run_id)
    reader_implementation_digest = _reader_implementation_digest()

    if family_keys is None:
        family_keys = list(NUMERIC_COMPARABLE_FAMILIES)

    records: list = []
    parse_errors: list = []
    families_compared: list = []
    families_non_comparable: list = []
    legacy_input_manifest: list = []
    consumed_ids: dict = defaultdict(set)  # family_key -> set(id(aggregate))
    expected_records = 0

    for family_key in family_keys:
        if family_key not in FAMILY_GLOBS and family_key not in FAMILIES_SINGLE_POPULATION:
            families_non_comparable.append(
                {"family": family_key, "reason": "no legacy reader registered for this family in UEF-5.3 yet"}
            )
            continue
        families_compared.append(family_key)

        if family_key in FAMILIES_SINGLE_POPULATION:
            reader_profile_identity = f"legacy_opportunity_engine.v1:{reader_implementation_digest}"
            for path, doc, error, identity in iter_legacy_q11_artifacts(repo_root):
                if error is not None:
                    parse_errors.append({"family": family_key, "path": str(path), "error": str(error)})
                    continue
                _record_manifest_entry(legacy_input_manifest, canonical, identity)
                legacy_day = extract_q11_exit_day(path, doc, identity.sha256, repo_root=repo_root)
                record, consumed = classify_q11_exit_day(
                    legacy_day, canonical, family_key, uef52_run_id, canonical.content_digest, reader_profile_identity
                )
                records.append(record)
                expected_records += 1
                if consumed is not None:
                    consumed_ids[family_key].add(id(consumed))

        elif family_key in FAMILIES_WITH_VIEW_DIMENSION:
            reader_profile_identity = f"legacy_forward_returns.v1:{reader_implementation_digest}"
            for path, doc, error, identity in iter_legacy_forward_returns_artifacts(repo_root, family_key):
                if error is not None:
                    parse_errors.append({"family": family_key, "path": str(path), "error": str(error)})
                    continue
                _record_manifest_entry(legacy_input_manifest, canonical, identity)
                for legacy_row in extract_horizon_views(path, doc, identity.sha256, repo_root=repo_root):
                    record, consumed = classify_q10_semiconductor_cell(
                        legacy_row, canonical, family_key, uef52_run_id, canonical.content_digest, reader_profile_identity
                    )
                    records.append(record)
                    expected_records += 1
                    if consumed is not None:
                        consumed_ids[family_key].add(id(consumed))

        elif family_key in FAMILIES_WITHOUT_VIEW_DIMENSION:
            reader_profile_identity = f"legacy_forward_returns.v1:{reader_implementation_digest}"
            for path, doc, error, identity in iter_legacy_forward_returns_artifacts(repo_root, family_key):
                if error is not None:
                    parse_errors.append({"family": family_key, "path": str(path), "error": str(error)})
                    continue
                _record_manifest_entry(legacy_input_manifest, canonical, identity)
                rows = extract_horizon_views(path, doc, identity.sha256, repo_root=repo_root)
                by_horizon: dict = defaultdict(list)
                for row in rows:
                    by_horizon[row.horizon].append(row)
                for horizon_rows in by_horizon.values():
                    day_records, consumed = classify_q12_calc1_day(
                        horizon_rows, canonical, family_key, uef52_run_id, canonical.content_digest, reader_profile_identity
                    )
                    records.extend(day_records)
                    expected_records += len(horizon_rows)
                    if consumed is not None:
                        consumed_ids[family_key].add(id(consumed))

        # HIGH-3: independent canonical-universe accounting -- every
        # canonical aggregate for this family that was never consumed by a
        # legacy join becomes an explicit canonical-only record.
        for aggregate in canonical.aggregates_for_family(family_key):
            if id(aggregate) not in consumed_ids[family_key]:
                records.append(
                    _canonical_only_record(family_key, aggregate, uef52_run_id, canonical.content_digest, reader_implementation_digest)
                )

    legacy_input_manifest_digest = _digest_manifest(legacy_input_manifest, reader_implementation_digest)
    dual_run_id = _compute_dual_run_id(
        uef52_run_id, family_keys, legacy_input_manifest_digest, canonical.content_digest, reader_implementation_digest
    )

    result = DualRunResult(
        dual_run_id=dual_run_id,
        uef52_run_id=uef52_run_id,
        legacy_input_manifest=legacy_input_manifest,
        legacy_input_manifest_digest=legacy_input_manifest_digest,
        canonical_content_digest=canonical.content_digest,
        reader_implementation_digest=reader_implementation_digest,
        records=records,
        parse_errors=parse_errors,
        families_compared=families_compared,
        families_non_comparable=families_non_comparable,
    )
    result.accounting = _compute_accounting(result, expected_records)
    return result


def _record_manifest_entry(legacy_input_manifest: list, canonical, identity) -> str:
    from .divergence_classifier import compute_hash_match

    if any(e.path == identity.path for e in legacy_input_manifest):
        # already recorded (e.g. re-visited) -- manifest entries are per
        # distinct path, not per row
        return next(e.hash_match for e in legacy_input_manifest if e.path == identity.path)
    hash_match = compute_hash_match(canonical, identity.path, identity.sha256)
    recorded = canonical.recorded_source_hash_for_path(identity.path)
    legacy_input_manifest.append(
        LegacyInputManifestEntry(
            path=identity.path,
            sha256=identity.sha256,
            reader_profile_id=identity.reader_profile_id,
            recorded_source_hash=recorded,
            hash_match=hash_match,
        )
    )
    return hash_match


def _digest_manifest(entries: list, reader_implementation_digest: str) -> str:
    """Binds path + content sha256 + reader/profile id for every consumed
    legacy artifact, AND the reader/classifier implementation's own digest
    (Core Correction 2 item 2D) -- changing reader semantics changes this
    digest even if no legacy byte changed."""

    payload = json.dumps(
        {
            "artifacts": sorted(
                [{"path": e.path, "sha256": e.sha256, "reader_profile_id": e.reader_profile_id} for e in entries],
                key=lambda d: (d["path"], d["sha256"]),
            ),
            "reader_implementation_digest": reader_implementation_digest,
        },
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _compute_accounting(result: DualRunResult, expected_legacy_records: int) -> dict:
    """Required invariant (item 12): every legacy cell and every canonical
    aggregate ends in exactly one terminal state. unaccounted=0,
    collisions=0 are the required pass condition."""

    unit_ids = [r.unit.unit_id() for r in result.records]
    id_counts = Counter(unit_ids)
    collisions = sum(1 for _uid, n in id_counts.items() if n > 1)

    # unaccounted: legacy rows that did not produce a record (structurally
    # should be 0 -- every code path in the classifier returns exactly one
    # record per legacy row it is handed).
    non_canonical_only_records = sum(1 for r in result.records if r.legacy is not None)
    unaccounted = expected_legacy_records - non_canonical_only_records

    return {
        "expected_legacy_cells": expected_legacy_records,
        "legacy_cells_accounted": non_canonical_only_records,
        "canonical_only_records": sum(1 for r in result.records if r.legacy is None),
        "unaccounted": unaccounted,
        "collisions": collisions,
    }


def write_dual_run_outputs(repo_root: Path, result: DualRunResult) -> Path:
    """Writes the required output artifacts under
    ``reports/evaluation/uef5_dual_run/<dual_run_id>/``:
    ``dual_run_summary.json``, ``dual_run_summary.md``,
    ``dual_run_records.jsonl``, ``divergence_summary.json``, and (Core
    Correction 1 item 22) ``dual_run_input_manifest.json``."""

    out_dir = Path(repo_root) / DUAL_RUN_OUTPUT_NAMESPACE / result.dual_run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    records_path = out_dir / "dual_run_records.jsonl"
    with records_path.open("w", encoding="utf-8") as fh:
        for rec in result.records:
            fh.write(json.dumps(rec.to_json(), sort_keys=True) + "\n")

    counts = result.counts()
    summary_doc = {
        "document": "dual_run_summary",
        "dual_run_id": result.dual_run_id,
        "uef52_run_id": result.uef52_run_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "families_compared": result.families_compared,
        "families_non_comparable": result.families_non_comparable,
        "parse_errors": result.parse_errors,
        "counts": counts,
        "accounting": result.accounting,
        "success_criterion": "UNEXPLAINED_DIVERGENCES = 0",
        "unexplained_divergences": counts["unexplained_divergence"],
    }
    (out_dir / "dual_run_summary.json").write_text(json.dumps(summary_doc, indent=2, sort_keys=True), encoding="utf-8")

    divergence_doc = {
        "document": "divergence_summary",
        "dual_run_id": result.dual_run_id,
        "top_divergence_reasons": result.top_divergence_reasons(),
        "unexplained_units": [
            rec.to_json() for rec in result.records if rec.result == ComparisonResult.UNEXPLAINED_DIVERGENCE
        ],
    }
    (out_dir / "divergence_summary.json").write_text(json.dumps(divergence_doc, indent=2, sort_keys=True), encoding="utf-8")

    input_manifest_doc = {
        "document": "dual_run_input_manifest",
        "dual_run_id": result.dual_run_id,
        "canonical_run_id": result.uef52_run_id,
        "canonical_artifact_identity": {
            "run_root": str((Path(repo_root) / canonical_run_mod.UEF52_RUN_NAMESPACE / result.uef52_run_id)).replace("\\", "/"),
            "canonical_content_digest": result.canonical_content_digest,
        },
        "reader_implementation_digest": result.reader_implementation_digest,
        "comparison_implementation_id": COMPARISON_IMPLEMENTATION_ID,
        "taxonomy_id": TAXONOMY_ID,
        "legacy_artifacts": [e.to_json() for e in result.legacy_input_manifest],
        "legacy_input_manifest_digest": result.legacy_input_manifest_digest,
    }
    (out_dir / "dual_run_input_manifest.json").write_text(json.dumps(input_manifest_doc, indent=2, sort_keys=True), encoding="utf-8")

    md_lines = [
        f"# UEF-5.3 Dual Run `{result.dual_run_id}`",
        "",
        f"- UEF-5.2 run compared against: `{result.uef52_run_id}`",
        f"- Families compared (numeric): {', '.join(result.families_compared) or '(none)'}",
        f"- Legacy input manifest digest: `{result.legacy_input_manifest_digest}`",
        "",
        "## Counts",
        "",
        "| Metric | Count |",
        "|---|---:|",
    ]
    for label, key in (
        ("Total comparison units", "total_comparison_units"),
        ("Exact match (total)", "exact_match"),
        ("  of which EXACT_EMPTY", "exact_empty"),
        ("  of which EXACT_NONEMPTY", "exact_nonempty"),
        ("Explained divergence", "explained_divergence"),
        ("Non-comparable", "non_comparable"),
        ("Blocked", "blocked"),
        ("Unexplained divergence", "unexplained_divergence"),
        ("COST_POLICY_DIFFERENCE units with nonempty legacy population", "cost_policy_difference_nonempty_units"),
    ):
        md_lines.append(f"| {label} | {counts[key]} |")
    md_lines += [
        "",
        f"**Success criterion (UNEXPLAINED_DIVERGENCES = 0): "
        f"{'MET' if counts['unexplained_divergence'] == 0 else 'NOT MET'}**",
        "",
        "## Accounting",
        "",
        f"- unaccounted: {result.accounting.get('unaccounted')}",
        f"- collisions: {result.accounting.get('collisions')}",
        f"- canonical-only records: {result.accounting.get('canonical_only_records')}",
        "",
        "## Top divergence reasons",
        "",
        "| Reason | Count |",
        "|---|---:|",
    ]
    for row in result.top_divergence_reasons():
        md_lines.append(f"| {row['reason']} | {row['count']} |")
    if result.families_non_comparable:
        md_lines += ["", "## Non-comparable families"]
        for entry in result.families_non_comparable:
            md_lines.append(f"- `{entry['family']}`: {entry['reason']}")
    (out_dir / "dual_run_summary.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return out_dir
