"""UEF-8 output writer. Presentation only -- never treated as semantic
authority, deliberately excluded from ``run_identity.uef8_implementation_digest``.
"""

from __future__ import annotations

import json
from pathlib import Path

from .model import FairComparisonRun

OUTPUT_NAMESPACE = "reports/evaluation/uef8_fair_comparison"


def _summary_markdown(run: FairComparisonRun) -> str:
    s = run.summary
    lines = [
        f"# UEF-8 Fair Comparison Validation -- {run.uef8_run_id}",
        "",
        f"- source_uef7_run_id: {run.source_uef7_run_id}",
        f"- candidate_count: {s.candidate_count}",
        f"- pair_count: {s.pair_count}",
        f"- COMPARABLE: {s.comparable_count}",
        f"- CONDITIONAL: {s.conditional_count}",
        f"- NOT_COMPARABLE: {s.not_comparable_count}",
        "",
        "## Reason counts",
        "",
    ]
    for reason, count in s.reason_counts.items():
        lines.append(f"- {reason}: {count}")
    return "\n".join(lines) + "\n"


def write_uef8_fair_comparison_outputs(run: FairComparisonRun, *, repo_root: Path) -> Path:
    out_dir = Path(repo_root) / OUTPUT_NAMESPACE / run.uef8_run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    with (out_dir / "fair_comparison_pairs.jsonl").open("w", encoding="utf-8") as fh:
        for pair in run.pairs:
            fh.write(json.dumps(pair.to_dict(), sort_keys=True) + "\n")

    (out_dir / "fair_comparison_summary.json").write_text(
        json.dumps(run.to_dict(), indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "fair_comparison_summary.md").write_text(_summary_markdown(run), encoding="utf-8")

    manifest = {
        "document": "uef8_fair_comparison_manifest",
        "uef8_run_id": run.uef8_run_id,
        "schema_version": run.schema_version,
        "source_uef7_run_id": run.source_uef7_run_id,
        "uef7_normalized_semantic_digest": run.uef7_normalized_semantic_digest,
        "uef8_implementation_digest": run.uef8_implementation_digest,
        "candidate_count": run.candidate_count,
        "pair_count": run.summary.pair_count,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return out_dir


__all__ = ["OUTPUT_NAMESPACE", "write_uef8_fair_comparison_outputs"]
