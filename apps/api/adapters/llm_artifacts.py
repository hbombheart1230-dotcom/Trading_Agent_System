from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..infrastructure.bounded_reader import BoundedReadError, read_json_bounded
from ..infrastructure.trade_index import discover_trade_bundles


@dataclass(frozen=True, slots=True)
class LlmArtifactLoad:
    rows: list[dict[str, Any]]
    issues: list[str]
    truncated: bool


def load_strategist_calls(
    reports_root: Path,
    day: date,
    *,
    max_bytes: int,
    max_rows: int,
) -> LlmArtifactLoad:
    day_root = reports_root / "llm" / day.isoformat()
    if not day_root.is_dir():
        return LlmArtifactLoad([], [], False)
    paths = sorted(day_root.glob("*/*/strategist_stage*/response.json"))
    truncated = len(paths) > max_rows
    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    for path in paths[:max_rows]:
        try:
            payload = read_json_bounded(path, max_bytes=max_bytes)
        except (OSError, BoundedReadError):
            issues.append("UNREADABLE_STRATEGIST_LLM_ARTIFACT")
            continue
        if not isinstance(payload, dict):
            issues.append("INVALID_STRATEGIST_LLM_ARTIFACT")
            continue
        rows.append(_safe_strategist_row(payload))
    if truncated:
        issues.append("STRATEGIST_LLM_ARTIFACT_LIMIT_REACHED")
    return LlmArtifactLoad(rows, issues, truncated)


def load_trade_report_calls(
    reports_root: Path,
    day: date,
    *,
    max_bytes: int,
    max_rows: int,
    max_bundles: int,
) -> LlmArtifactLoad:
    refs, discovery_issues = discover_trade_bundles(
        reports_root,
        day,
        day,
        max_days=1,
        max_bundles=max_bundles,
    )
    rows: list[dict[str, Any]] = []
    issues = list(discovery_issues)
    names = (
        ("trade_report", "ai_trade_report_llm_response.json"),
        ("trade_report", "ai_trade_summary_llm_response.json"),
        ("operator_ui", "brief_llm_response.json"),
    )
    for ref in refs:
        for role, name in names:
            path = ref.root / "reports" / name
            if not path.is_file():
                continue
            if len(rows) >= max_rows:
                issues.append("TRADE_LLM_ARTIFACT_LIMIT_REACHED")
                return LlmArtifactLoad(rows, issues, True)
            try:
                payload = read_json_bounded(path, max_bytes=max_bytes)
            except (OSError, BoundedReadError):
                issues.append(f"UNREADABLE_TRADE_LLM_ARTIFACT:{ref.trade_id}")
                continue
            if isinstance(payload, dict):
                rows.append(_safe_trade_row(payload, role, ref.trade_id, day))
    return LlmArtifactLoad(rows, issues, False)


def _safe_strategist_row(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "strategist",
        "provider": payload.get("provider"),
        "model": payload.get("model"),
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "run_id": payload.get("run_id"),
        "saved_at": payload.get("saved_at"),
        "stage_index": payload.get("stage_index"),
        "stage_name": payload.get("stage_name"),
        "stage_component": payload.get("stage_component"),
        "call_kind": payload.get("call_kind"),
        "attempts": payload.get("attempts"),
        "profile_name": payload.get("llm_execution_profile_name"),
    }


def _safe_trade_row(
    payload: dict[str, Any],
    role: str,
    trade_id: str,
    day: date,
) -> dict[str, Any]:
    model_info = payload.get("model_info")
    model_info = model_info if isinstance(model_info, dict) else {}
    return {
        "role": role,
        "provider": payload.get("provider") or model_info.get("provider"),
        "model": payload.get("model") or model_info.get("model"),
        "status": payload.get("status") or payload.get("llm_status"),
        "reason": payload.get("reason") or payload.get("error"),
        "run_id": trade_id,
        "saved_at": payload.get("saved_at") or f"{day.isoformat()}T00:00:00+00:00",
        "stage_index": None,
        "stage_name": "trade_report_generation",
        "stage_component": role,
        "call_kind": role,
        "attempts": payload.get("attempts"),
        "profile_name": None,
    }
