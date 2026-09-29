"""UEF-7 output writer. Presentation only -- never treated as semantic
authority, deliberately excluded from ``run_identity.normalizer_implementation_digest``.
"""

from __future__ import annotations

import json
from pathlib import Path

from .model import NormalizedAlphaBoard

OUTPUT_NAMESPACE = "reports/evaluation/uef7_alpha_board"


def _summary_markdown(normalized: NormalizedAlphaBoard) -> str:
    lines = [
        f"# UEF-7 Alpha Board Normalization -- {normalized.uef7_run_id}",
        "",
        f"- through_day: {normalized.through_day}",
        f"- candidate_row_count: {normalized.candidate_row_count}",
        f"- shared_source_group_count: {normalized.normalization_summary.shared_source_group_count}",
        f"- rows_with_shared_source_count: {normalized.normalization_summary.rows_with_shared_source_count}",
        f"- unresolved_population_candidate_count: {normalized.normalization_summary.unresolved_population_candidate_count}",
        "",
        "## Source overlap groups",
        "",
    ]
    if not normalized.source_groups:
        lines.append("(none)")
    for group in normalized.source_groups:
        lines.append(f"- {group.source_group_id} ({group.source_key}): {', '.join(group.candidate_ids)}")
    return "\n".join(lines) + "\n"


def write_uef7_normalization_outputs(normalized: NormalizedAlphaBoard, *, repo_root: Path) -> Path:
    out_dir = Path(repo_root) / OUTPUT_NAMESPACE / normalized.uef7_run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = normalized.to_dict()
    (out_dir / "normalized_alpha_board.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "source_overlap_groups.json").write_text(
        json.dumps([g.to_dict() for g in normalized.source_groups], indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "normalization_summary.md").write_text(_summary_markdown(normalized), encoding="utf-8")
    manifest = {
        "document": "uef7_alpha_board_normalization_manifest",
        "uef7_run_id": normalized.uef7_run_id,
        "schema_version": normalized.schema_version,
        "source_board_schema_version": normalized.source_board_schema_version,
        "source_board_semantic_digest": normalized.source_board_semantic_digest,
        "normalizer_implementation_digest": normalized.normalizer_implementation_digest,
        "candidate_row_count": normalized.candidate_row_count,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return out_dir


__all__ = ["OUTPUT_NAMESPACE", "write_uef7_normalization_outputs"]
