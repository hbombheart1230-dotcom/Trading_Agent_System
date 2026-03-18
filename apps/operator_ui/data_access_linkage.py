from __future__ import annotations

from pathlib import Path
from typing import Dict

from libs.reporting.llm_artifacts import trade_artifact_paths


def trade_root_from_bundle_path(bundle_path: Path) -> Path:
    parent = bundle_path.parent
    if parent.name == "lifecycle":
        return parent.parent
    return parent


def trade_paths_from_bundle(bundle_path: Path, *, day_hint: str = "", trade_id_hint: str = "") -> Dict[str, Path]:
    trade_root = trade_root_from_bundle_path(bundle_path)
    if day_hint and trade_id_hint:
        try:
            paths = trade_artifact_paths(bundle_path.parents[2], day_hint, trade_id_hint)
            # Only trust helper paths when root already matches trade root pattern.
            if str(paths["trade_root"]) == str(trade_root):
                return paths
        except Exception:
            pass
    legacy_root = trade_root
    if trade_root.name in {"brief", "ai_trade_report", "lifecycle", "strategist", "evidence"}:
        trade_root = trade_root.parent
    return {
        "trade_root": trade_root,
        "legacy_trade_root": legacy_root,
        "strategist_dir": trade_root / "strategist",
        "ai_trade_report_dir": trade_root / "ai_trade_report",
        "brief_dir": trade_root / "brief",
        "lifecycle_dir": trade_root / "lifecycle",
        "evidence_dir": trade_root / "evidence",
        "strategist_llm_response_json": trade_root / "strategist" / "strategist_llm_response.json",
        "ai_trade_report_input_json": trade_root / "ai_trade_report" / "ai_trade_report_input.json",
        "ai_trade_report_compact_input_json": trade_root / "ai_trade_report" / "ai_trade_report_compact_input.json",
        "ai_trade_report_json": trade_root / "ai_trade_report" / "ai_trade_report.json",
        "ai_trade_report_md": trade_root / "ai_trade_report" / "ai_trade_report.md",
        "ai_trade_report_llm_response_json": trade_root / "ai_trade_report" / "ai_trade_report_llm_response.json",
        "brief_input_json": trade_root / "brief" / "brief_input.json",
        "brief_compact_input_json": trade_root / "brief" / "brief_compact_input.json",
        "brief_json": trade_root / "brief" / "operator_brief.json",
        "brief_md": trade_root / "brief" / "operator_brief.md",
        "brief_llm_response_json": trade_root / "brief" / "brief_llm_response.json",
        "trade_lifecycle_json": trade_root / "lifecycle" / "trade_lifecycle.json",
        "aggregated_execution_bundle_json": trade_root / "lifecycle" / "aggregated_execution_bundle.json",
        "strategist_evidence_json": trade_root / "evidence" / "strategist_evidence.json",
        "scanner_evidence_json": trade_root / "evidence" / "scanner_evidence.json",
        "monitor_timeline_json": trade_root / "evidence" / "monitor_timeline.json",
        "trade_provenance_json": trade_root / "_provenance.json",
        "trade_health_json": trade_root / "_health.json",
        "trade_artifact_links_json": trade_root / "_artifact_links.json",
        "legacy_trade_story_input_json": trade_root / "trade_story_input.json",
        "legacy_trade_report_json": trade_root / "trade_report.json",
        "legacy_trade_report_md": trade_root / "trade_report.md",
        "legacy_trade_lifecycle_json": trade_root / "trade_lifecycle.json",
        "legacy_aggregated_execution_bundle_json": trade_root / "aggregated_execution_bundle.json",
        "legacy_operator_brief_json": trade_root / "operator_brief.json",
        "legacy_operator_brief_md": trade_root / "operator_brief.md",
    }


def existing_trade_path(paths: Dict[str, Path], *keys: str) -> Path:
    for key in keys:
        path = paths.get(key)
        if isinstance(path, Path) and path.exists():
            return path
    return Path()
