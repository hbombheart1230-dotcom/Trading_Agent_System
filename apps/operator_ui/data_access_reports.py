from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict


def _pick_first_existing(*paths: Path) -> Path:
    for path in paths:
        if isinstance(path, Path) and path.exists():
            return path
    return Path()


def load_trade_report_payloads(
    trade_report_meta: Dict[str, Any],
    *,
    read_json: Callable[[Path], Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    trade_root_path = Path(str(trade_report_meta.get("trade_root_path") or ""))
    normalized_story_input = trade_root_path / "ai_trade_report_input.json"
    normalized_lifecycle = trade_root_path / "lifecycle_bundle.json"
    normalized_report_json = trade_root_path / "reports" / "ai_trade_report.json"
    legacy_story_input = trade_root_path / "ai_trade_report" / "ai_trade_report_input.json"
    legacy_lifecycle = trade_root_path / "lifecycle" / "trade_lifecycle.json"
    legacy_report_json = trade_root_path / "ai_trade_report" / "ai_trade_report.json"

    story_input_meta_path = Path(str(trade_report_meta.get("trade_story_input_path") or ""))
    lifecycle_meta_path = Path(str(trade_report_meta.get("trade_lifecycle_json_path") or ""))
    report_meta_path = Path(str(trade_report_meta.get("trade_report_json_path") or ""))
    aggregated_bundle_path = Path(str(trade_report_meta.get("aggregated_bundle_path") or ""))

    story_input_path = _pick_first_existing(normalized_story_input, legacy_story_input, story_input_meta_path)
    lifecycle_path = _pick_first_existing(normalized_lifecycle, legacy_lifecycle, lifecycle_meta_path)
    report_json_path = _pick_first_existing(normalized_report_json, legacy_report_json, report_meta_path)

    story_input_data = read_json(story_input_path) if story_input_path.exists() else {}
    lifecycle_data = read_json(lifecycle_path) if lifecycle_path.exists() else {}
    report_data = read_json(report_json_path) if report_json_path.exists() else {}

    bundle_data = read_json(aggregated_bundle_path) if aggregated_bundle_path.exists() else {}
    if not bundle_data and normalized_lifecycle.exists():
        bundle_data = read_json(normalized_lifecycle)
    if not bundle_data and legacy_lifecycle.exists():
        bundle_data = read_json(legacy_lifecycle)
    canonical_fallback = (
        bundle_data.get("canonical_agent_artifacts")
        if isinstance(bundle_data.get("canonical_agent_artifacts"), dict)
        else {}
    )

    story_source = "normalized_trade_artifact" if story_input_path == normalized_story_input and story_input_path.exists() else ("direct_artifact" if story_input_path.exists() else "missing")
    lifecycle_source = "normalized_trade_artifact" if lifecycle_path == normalized_lifecycle and lifecycle_path.exists() else ("direct_artifact" if lifecycle_path.exists() else "missing")
    report_source = "normalized_trade_artifact" if report_json_path == normalized_report_json and report_json_path.exists() else ("direct_artifact" if report_json_path.exists() else "missing")

    return {
        "story_input_data": story_input_data if isinstance(story_input_data, dict) else {},
        "lifecycle_data": lifecycle_data if isinstance(lifecycle_data, dict) else {},
        "report_data": report_data if isinstance(report_data, dict) else {},
        "payload_sources": {
            "story_input": story_source,
            "lifecycle": lifecycle_source,
            "report": report_source,
            "canonical_fallback": "canonical_artifact" if canonical_fallback else "missing",
        },
        "paths": {
            "story_input_path": str(story_input_path) if story_input_path.exists() else "",
            "lifecycle_path": str(lifecycle_path) if lifecycle_path.exists() else "",
            "report_path": str(report_json_path) if report_json_path.exists() else "",
            "aggregated_bundle_path": str(aggregated_bundle_path) if aggregated_bundle_path.exists() else "",
        },
    }
