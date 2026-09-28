"""CLI entrypoint for UEF-6C Historical Dedup & Direct-Lineage Validation.

Read-only against the target UEF-5.2 run and the current repository.
Writes ONLY under reports/evaluation/uef6_validation/<UEF6C_RUN_ID>/.
Never modifies UEF-1..UEF-5.3, never mutates the target UEF5RUN artifacts.

  python scripts/run_uef6_historical_validation.py --uef52-run-id UEF5RUN_... [--repo-root DIR] [--keep-snapshot]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.uef5 import historical_recompute as hr  # noqa: E402
from libs.reporting.evaluation.uef6.lineage_coverage import (  # noqa: E402
    account_witnesses_against_aggregates,
    aggregate_coverage_totals,
    compute_witness_coverage,
    find_cross_aggregate_physical_event_reuse,
    find_cross_aggregate_record_reuse,
    scan_duplicate_members,
)
from libs.reporting.evaluation.uef6.run_identity import detector_implementation_digest as uef6a_impl_digest  # noqa: E402
from libs.reporting.evaluation.uef6.run_uef6a import run_uef6a_dedup_detection  # noqa: E402
from libs.reporting.evaluation.uef6.lineage_witness import lineage_implementation_digest as uef6b_impl_digest  # noqa: E402
from libs.reporting.evaluation.uef6.validation_replay import (  # noqa: E402
    UEF6SnapshotIntegrityError,
    aggregate_population_semantic_digest,
    build_isolated_snapshot,
    compare_recompute_runs,
    compute_uef6c_run_id,
    episode_population_semantic_digest,
    link_witnesses_to_frozen_result,
    run_baseline_replay,
    run_instrumented_replay,
    validation_implementation_digest,
)

OUTPUT_NAMESPACE = "reports/evaluation/uef6_validation"


def _content_digest(payload) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=str(ROOT))
    ap.add_argument("--uef52-run-id", required=True)
    ap.add_argument("--keep-snapshot", action="store_true")
    args = ap.parse_args()
    repo_root = Path(args.repo_root)

    result = {"document": "uef6c_validation_summary", "target_uef52_run_id": args.uef52_run_id}

    # --- Mode A: frozen-output observation (UEF-6A over the real episodes.jsonl) ---
    uef6a_result = run_uef6a_dedup_detection(repo_root, args.uef52_run_id)
    result["mode_a_uef6a_historical_dedup"] = uef6a_result.report.summary_dict()
    result["mode_a_uef6a_run_id"] = uef6a_result.uef6a_run_id

    # --- Mode B: instrumented historical replay over an isolated snapshot ---
    tmp_dir = Path(tempfile.mkdtemp(prefix="uef6c_snapshot_"))
    try:
        try:
            snapshot_manifest = build_isolated_snapshot(repo_root, args.uef52_run_id, tmp_dir)
        except UEF6SnapshotIntegrityError as exc:
            result["mode_b_status"] = "NOT_REPRODUCIBLE"
            result["mode_b_reason"] = str(exc)
            print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
            return 0

        result["snapshot_file_count"] = len(snapshot_manifest.files)

        baseline = run_baseline_replay(tmp_dir)
        instrumented = run_instrumented_replay(tmp_dir)
        parity = compare_recompute_runs(baseline.run, instrumented.run)
        result["baseline_vs_instrumented_parity"] = {"identical": parity.identical, "differences": list(parity.differences)}

        if not parity.identical:
            result["mode_b_status"] = "FAIL_CLOSED_PARITY_VIOLATION"
            print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
            return 1

        result["replay_run_id"] = instrumented.run.run_id
        result["replay_status"] = str(instrumented.run.status)
        result["replay_aggregate_count"] = len(instrumented.run.aggregates)
        result["replay_call_count"] = instrumented.aggregate_call_count
        result["captured_witness_count"] = len(instrumented.witnesses)

        # --- historical parity: does the snapshot replay's run_id match the TARGET frozen run_id? ---
        historically_linked = instrumented.run.run_id == args.uef52_run_id
        result["historical_run_id_match"] = historically_linked
        result["lineage_link_status"] = link_witnesses_to_frozen_result(parity) if historically_linked else "NOT_LINKED_TO_FROZEN_HISTORICAL_RESULT"
        if not historically_linked:
            result["historical_link_reason"] = (
                f"replay run_id={instrumented.run.run_id!r} != target run_id={args.uef52_run_id!r} -- the "
                "isolated snapshot's own recomputation does not reproduce the exact historical run identity "
                "(see effective_run_config/registry/day-validity/candle-config differences, if any)"
            )

        # --- witness/aggregate accounting ---
        accounting = account_witnesses_against_aggregates(instrumented.witnesses, instrumented.run.aggregates)
        result["witness_aggregate_accounting"] = accounting.to_dict()

        # --- population lineage coverage ---
        episode_by_record_id = {e.identity.evaluation_record_id: e for e in instrumented.run.episodes}
        family_by_record_id = {agg.identity.evaluation_record_id: meta.get("family", "") for agg, meta in instrumented.run.aggregates}
        coverage_details = compute_witness_coverage(instrumented.witnesses, instrumented.run.episodes, family_by_record_id)
        result["population_lineage_coverage"] = aggregate_coverage_totals(coverage_details)
        result["not_provable_witness_count"] = sum(1 for d in coverage_details if not d.exact_evaluated_episode_membership_proven)

        # --- duplicate member scan ---
        result["duplicate_member_scan"] = scan_duplicate_members(instrumented.witnesses)

        # --- cross-aggregate reuse ---
        record_reuse = find_cross_aggregate_record_reuse(instrumented.witnesses)
        event_reuse = find_cross_aggregate_physical_event_reuse(instrumented.witnesses, episode_by_record_id)
        result["cross_aggregate_record_reuse_count"] = len(record_reuse)
        result["cross_aggregate_physical_event_reuse_count"] = len(event_reuse)

        # --- UEF-6C run identity ---
        # Order-independent multiset digests (Final Audit item A) -- never a
        # stable sort keyed only on evaluation_record_id, which leaves rows
        # sharing that key (evaluator_version variants; context-different
        # aggregates) in their original input order and makes the digest
        # (and therefore UEF6C_RUN_ID) row-order sensitive.
        episodes_digest = episode_population_semantic_digest(instrumented.run.episodes)
        aggregates_digest = aggregate_population_semantic_digest(instrumented.run.aggregates)
        effective_config_digest = _content_digest({"repo_root_relative": True, "families": "DEFAULT_FAMILIES"})
        uef6c_run_id = compute_uef6c_run_id(
            target_uef52_run_id=args.uef52_run_id, target_episodes_digest=episodes_digest, target_aggregates_digest=aggregates_digest,
            uef6a_impl_digest=uef6a_impl_digest(), uef6b_impl_digest=uef6b_impl_digest(),
            uef6c_impl_digest=validation_implementation_digest(), effective_replay_config_digest=effective_config_digest,
        )
        result["uef6c_run_id"] = uef6c_run_id
        result["mode_b_status"] = "COMPLETE"

        out_dir = repo_root / OUTPUT_NAMESPACE / uef6c_run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "validation_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True), encoding="utf-8")
        with (out_dir / "lineage_witnesses.jsonl").open("w", encoding="utf-8") as fh:
            for w in instrumented.witnesses:
                fh.write(json.dumps(w.to_dict(), sort_keys=True) + "\n")
        (out_dir / "cross_aggregate_reuse.json").write_text(
            json.dumps({"record_reuse": record_reuse, "physical_event_reuse": event_reuse}, indent=2, sort_keys=True), encoding="utf-8"
        )
        print(f"wrote: {out_dir}", file=sys.stderr)
    finally:
        if not args.keep_snapshot:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
