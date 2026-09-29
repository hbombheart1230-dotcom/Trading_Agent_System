"""Presentation-only writer for a verified UEF-9 authority manifest."""

from __future__ import annotations

import json
from pathlib import Path

from .model import FormalEvaluationAuthority


OUTPUT_NAMESPACE = "reports/evaluation/uef9_formal_authority"


def _markdown(authority: FormalEvaluationAuthority) -> str:
    data = authority.to_dict()
    lines = [
        f"# UEF-9 Formal Evaluation Authority -- {authority.uef9_run_id}",
        "",
        f"- authority_status: {authority.authority_status}",
        f"- source_uef7_run_id: {authority.source_uef7_run_id}",
        f"- source_uef8_run_id: {authority.source_uef8_run_id}",
        f"- candidate_count: {authority.candidate_count}",
        f"- pair_count: {authority.pair_count}",
        f"- comparable_reachable_with_current_uef7_schema: {authority.comparable_reachable_with_current_uef7_schema}",
        "",
        "## Comparison status counts",
    ]
    for status, count in data["comparison_status_counts"].items():
        lines.append(f"- {status}: {count}")
    return "\n".join(lines) + "\n"


def write_formal_evaluation_authority(authority: FormalEvaluationAuthority, *, repo_root: Path) -> Path:
    out_dir = Path(repo_root) / OUTPUT_NAMESPACE / authority.uef9_run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = authority.to_dict()
    (out_dir / "formal_evaluation_authority.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "formal_evaluation_authority.md").write_text(_markdown(authority), encoding="utf-8")
    (out_dir / "manifest.json").write_text(
        json.dumps(
            {
                "document": "uef9_formal_evaluation_authority_manifest",
                "uef9_run_id": authority.uef9_run_id,
                "schema_version": authority.schema_version,
                "authority_status": authority.authority_status,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return out_dir


__all__ = ["OUTPUT_NAMESPACE", "write_formal_evaluation_authority"]
