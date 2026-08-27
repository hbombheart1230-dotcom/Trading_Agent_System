from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import now_iso, relative_path, write_json, write_text


def materialize_closeout_intelligence(
    *,
    day: str,
    closeout_payload: dict[str, Any],
    closeout_paths: dict[str, str],
    reports_root: Path = Path("reports"),
) -> dict[str, Any]:
    normalized_day = str(day)[:10]
    root = Path(reports_root)
    steps = closeout_payload.get("steps") if isinstance(closeout_payload.get("steps"), dict) else {}
    normalized_steps = {
        name: {
            "status": "SUCCESS" if bool(row.get("ok")) else "SKIPPED" if bool(row.get("skipped")) else "FAILED",
            "artifacts": _artifact_refs(row, root),
        }
        for name, row in steps.items() if isinstance(row, dict)
    }
    failed = [name for name, row in normalized_steps.items() if row["status"] == "FAILED"]
    memory_step = steps.get("operator_daily_summary_artifact") if isinstance(steps.get("operator_daily_summary_artifact"), dict) else {}
    memory_sync = memory_step.get("performance_memory_sync") if isinstance(memory_step.get("performance_memory_sync"), dict) else {}
    memory_path = root / "performance" / normalized_day / "strategy_memory.json"
    status = "SUCCESS" if bool(closeout_payload.get("ok")) and memory_path.is_file() else "PARTIAL" if memory_path.is_file() else "FAILED"
    index = {
        "schema_version": "daily_intelligence_index.v1",
        "day": normalized_day,
        "generated_at": now_iso(),
        "status": status,
        "trigger": str(closeout_payload.get("trigger") or ""),
        "broker_truth": _step_summary(steps, "account_snapshot"),
        "trade_reconciliation": _step_summary(steps, "broker_closed_trade_reconciliation"),
        "operator_summary": _step_summary(steps, "operator_daily_summary_artifact"),
        "system_health": _step_summary(steps, "operator_visibility_summary"),
        "post_exit": _step_summary(steps, "post_exit_shadow_recap"),
        "evaluation": {
            "q8": _step_summary(steps, "q8_shadow_blocker_review"),
            "q9": _step_summary(steps, "q9_baseline_frozen_window"),
            "opening_rank1": _step_summary(steps, "opening_rank1_prospective_shadow"),
        },
        "memory": {
            "status": "GENERATED" if memory_path.is_file() else "MISSING",
            "artifact": relative_path(memory_path, root.parent) if memory_path.is_file() else "",
            "sync": memory_sync,
            "next_session_delivery": "PENDING_PREOPEN_RECEIPT" if memory_path.is_file() else "UNAVAILABLE",
        },
        "steps": normalized_steps,
        "failed_steps": failed,
        "source_closeout_reports": dict(closeout_paths),
    }
    out_dir = root / "briefings" / normalized_day
    json_path = write_json(out_dir / "daily_intelligence_index.json", index)
    md_path = write_text(out_dir / "daily_intelligence_index.md", _closeout_markdown(index))
    manifest = {
        "schema_version": "scheduled_job_manifest.v1",
        "day": normalized_day,
        "job": "closeout",
        "generated_at": now_iso(),
        "status": status,
        "steps": normalized_steps,
        "memory": index["memory"],
        "daily_index": {"json": relative_path(json_path, root.parent), "markdown": relative_path(md_path, root.parent)},
        "issues": failed,
    }
    manifest_path = write_json(root / "runtime" / "scheduled_jobs" / normalized_day / "closeout.json", manifest)
    write_json(root / "runtime" / "scheduled_jobs" / "latest_closeout.json", manifest)
    return {"status": status, "manifest_path": str(manifest_path), "index_json_path": str(json_path), "index_md_path": str(md_path)}


def _step_summary(steps: dict[str, Any], name: str) -> dict[str, Any]:
    row = steps.get(name) if isinstance(steps.get(name), dict) else {}
    return {"status": "SUCCESS" if bool(row.get("ok")) else "MISSING" if not row else "FAILED", **{key: value for key, value in row.items() if key not in {"ok", "payload"}}}


def _artifact_refs(row: dict[str, Any], reports_root: Path) -> list[str]:
    refs = []
    for key, value in row.items():
        if "path" not in key or not isinstance(value, str) or not value.strip(): continue
        path = Path(value)
        refs.append(relative_path(path, reports_root.parent) if path.exists() else value)
    return sorted(set(refs))


def _closeout_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# 최종 트레이딩 및 시스템 인덱스 - {payload['day']}", "", f"- 상태: **{payload['status']}**", f"- 트리거: `{payload['trigger'] or '-'}`", f"- 메모리: `{payload['memory']['status']}`", f"- 다음 장전 전달: `{payload['memory']['next_session_delivery']}`", "", "## 핵심 단계", ""]
    for name in ("broker_truth", "trade_reconciliation", "operator_summary", "system_health", "post_exit"):
        lines.append(f"- {name}: `{payload[name]['status']}`")
    lines += ["", "## 평가", ""]
    lines.extend(f"- {name}: `{row['status']}`" for name, row in payload["evaluation"].items())
    if payload["failed_steps"]:
        lines += ["", "## 실패 단계", ""] + [f"- `{name}`" for name in payload["failed_steps"]]
    return "\n".join(lines)
