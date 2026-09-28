"""UEF-6A output writer.

Writes the required output artifacts under
``reports/evaluation/uef6_dedup/<UEF6A_RUN_ID>/``. Outputs are derived
evidence only -- never new runtime authority, never fed into live trading.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .report_model import PopulationDedupReport

OUTPUT_NAMESPACE = "reports/evaluation/uef6_dedup"


def write_dedup_report_outputs(repo_root: Path, uef6a_run_id: str, report: PopulationDedupReport, input_manifest: dict) -> Path:
    out_dir = Path(repo_root) / OUTPUT_NAMESPACE / uef6a_run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # `generated_at` is NON-SEMANTIC wall-clock metadata -- it is expected
    # to differ across otherwise-identical executions and is deliberately
    # NOT part of the determinism contract (which covers the dedup
    # semantic result, population_semantic_digest, UEF6A_RUN_ID, and every
    # other field in report.summary_dict()). Kept inline here rather than
    # split into a separate file -- nothing about this field's presence
    # makes the semantic fields non-deterministic, it only means a raw
    # byte-for-byte diff of this JSON file across two runs is expected to
    # differ in this one field.
    summary_doc = {
        "document": "dedup_summary",
        "uef6a_run_id": uef6a_run_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **report.summary_dict(),
    }
    (out_dir / "dedup_summary.json").write_text(json.dumps(summary_doc, indent=2, sort_keys=True), encoding="utf-8")

    with (out_dir / "event_clusters.jsonl").open("w", encoding="utf-8") as fh:
        for cluster in report.event_clusters:
            fh.write(json.dumps(cluster.to_dict(), sort_keys=True) + "\n")

    with (out_dir / "duplicate_groups.jsonl").open("w", encoding="utf-8") as fh:
        for group in report.duplicate_groups:
            fh.write(json.dumps(group.to_dict(), sort_keys=True) + "\n")

    manifest_doc = {"document": "input_manifest", "uef6a_run_id": uef6a_run_id, **input_manifest}
    (out_dir / "input_manifest.json").write_text(json.dumps(manifest_doc, indent=2, sort_keys=True), encoding="utf-8")

    md_lines = [
        f"# UEF-6A Population Dedup Detection `{uef6a_run_id}`",
        "",
        f"- Source UEF-5.2 run: `{input_manifest.get('source_uef52_run_id', '')}`",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|---|---:|",
    ]
    summary = report.summary_dict()
    for label, key in (
        ("Raw row count", "raw_row_count"),
        ("Unique physical events (canonical_event_id)", "unique_canonical_event_count"),
        ("Unique evaluation subjects", "unique_evaluation_subject_count"),
        ("Unique evaluation records", "unique_evaluation_record_count"),
        ("Duplicate groups", "duplicate_group_count"),
        ("Duplicate excess rows", "duplicate_excess_row_count"),
        ("Event clusters", "event_cluster_count"),
        ("Events with multiple subjects", "events_with_multiple_subjects"),
        ("Events with multiple records", "events_with_multiple_records"),
    ):
        md_lines.append(f"| {label} | {summary[key]} |")
    md_lines += ["", "## Relation counts", "", "| Relation | Count |", "|---|---:|"]
    for relation, count in sorted(summary["relation_counts"].items()):
        md_lines.append(f"| {relation} | {count} |")
    (out_dir / "dedup_summary.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return out_dir
