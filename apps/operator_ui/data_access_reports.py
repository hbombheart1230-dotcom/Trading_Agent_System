from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict


def load_trade_report_payloads(
    trade_report_meta: Dict[str, Any],
    *,
    read_json: Callable[[Path], Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    story_input_path = Path(str(trade_report_meta.get("trade_story_input_path") or ""))
    lifecycle_path = Path(str(trade_report_meta.get("trade_lifecycle_json_path") or ""))
    report_json_path = Path(str(trade_report_meta.get("trade_report_json_path") or ""))
    story_input_data = read_json(story_input_path) if story_input_path.exists() else {}
    lifecycle_data = read_json(lifecycle_path) if lifecycle_path.exists() else {}
    report_data = read_json(report_json_path) if report_json_path.exists() else {}
    return {
        "story_input_data": story_input_data if isinstance(story_input_data, dict) else {},
        "lifecycle_data": lifecycle_data if isinstance(lifecycle_data, dict) else {},
        "report_data": report_data if isinstance(report_data, dict) else {},
    }
