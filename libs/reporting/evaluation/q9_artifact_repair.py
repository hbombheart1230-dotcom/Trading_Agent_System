from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.quant_shadow_candidate_evaluation import (
    _augment_missing_q9_commander_candidate,
    shadow_candidate_root_for_reports,
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _normalized_generated_at(value: Any) -> tuple[str, int | None]:
    text = str(value or "").strip()
    try:
        dt = datetime.fromtimestamp(float(text), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text, None
    return dt.isoformat(timespec="seconds"), int(dt.timestamp())


def repair_q9_day_artifacts(*, reports_root: Path, day: str) -> dict[str, Any]:
    normalized_day = str(day or "")[:10]
    decision_path = (
        Path(reports_root)
        / "operator_summary"
        / "daily"
        / normalized_day
        / "q9_decision_windows.json"
    )
    decision_payload = _read_json(decision_path)
    windows = [
        dict(row)
        for row in decision_payload.get("windows") or []
        if isinstance(row, Mapping)
    ]
    normalized_windows = 0
    windows_by_id: dict[str, dict[str, Any]] = {}
    for row in windows:
        before = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        row["window_type"] = (
            "scanner_selection"
            if isinstance(row.get("scanner_control"), Mapping)
            else "commander_monitor_only"
        )
        generated_at, epoch = _normalized_generated_at(row.get("generated_at"))
        if generated_at:
            row["generated_at"] = generated_at
        if row.get("decision_epoch") is None and epoch is not None:
            row["decision_epoch"] = epoch
        if json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) != before:
            normalized_windows += 1
        decision_id = str(row.get("decision_id") or "")
        if decision_id:
            windows_by_id[decision_id] = row
    if windows and decision_path.exists():
        decision_payload["windows"] = windows
        decision_payload["window_count"] = len(windows)
        _write_json_atomic(decision_path, decision_payload)

    shadow_root = shadow_candidate_root_for_reports(Path(reports_root)) / normalized_day
    repaired_payloads = 0
    complete_payloads = 0
    for path in sorted(shadow_root.glob("*.json")) if shadow_root.exists() else []:
        if path.name == "latest.json":
            continue
        payload = _read_json(path)
        if not payload:
            continue
        before = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        payload = _augment_missing_q9_commander_candidate(
            payload,
            windows_by_id=windows_by_id,
        )
        roles = {
            str(row.get("q9_decision_role") or "")
            for row in payload.get("q9_decision_candidates") or []
            if isinstance(row, Mapping)
        }
        if "C_COMMANDER_FINAL" in roles:
            complete_payloads += 1
            payload["q9_sync_status"] = {
                "status": "complete",
                "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "role_count": len(roles),
                "source": "q9_artifact_repair",
            }
        after = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        if after != before:
            _write_json_atomic(path, payload)
            repaired_payloads += 1
    return {
        "ok": True,
        "day": normalized_day,
        "decision_path": str(decision_path),
        "window_count": len(windows),
        "normalized_window_count": normalized_windows,
        "shadow_payload_repaired_count": repaired_payloads,
        "shadow_payload_complete_count": complete_payloads,
    }


__all__ = ["repair_q9_day_artifacts"]
