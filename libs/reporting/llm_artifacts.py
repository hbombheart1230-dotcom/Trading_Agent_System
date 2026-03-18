from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def split_prompt_messages(messages: Any) -> Tuple[str, str]:
    system_parts: List[str] = []
    user_parts: List[str] = []
    if not isinstance(messages, list):
        return "", ""
    for row in messages:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "").strip().lower()
        content = str(row.get("content") or "")
        if not content:
            continue
        if role == "system":
            system_parts.append(content)
        elif role == "user":
            user_parts.append(content)
    return "\n\n".join(system_parts).strip(), "\n\n".join(user_parts).strip()


def split_prompt_text(prompt_text: Any) -> Tuple[str, str]:
    text = str(prompt_text or "").strip()
    if not text:
        return "", ""
    system_prompt = ""
    user_prompt = ""
    system_match = []
    user_match = []
    current_role = ""
    current_lines: List[str] = []
    for raw_line in text.splitlines():
        line = str(raw_line or "")
        stripped = line.strip().lower()
        if stripped in {"[system]", "[user]"}:
            if current_role == "system" and current_lines:
                system_match.append("\n".join(current_lines).strip())
            elif current_role == "user" and current_lines:
                user_match.append("\n".join(current_lines).strip())
            current_role = stripped.strip("[]")
            current_lines = []
            continue
        current_lines.append(line)
    if current_role == "system" and current_lines:
        system_match.append("\n".join(current_lines).strip())
    elif current_role == "user" and current_lines:
        user_match.append("\n".join(current_lines).strip())
    system_prompt = "\n\n".join(x for x in system_match if x).strip()
    user_prompt = "\n\n".join(x for x in user_match if x).strip()
    if system_prompt or user_prompt:
        return system_prompt, user_prompt
    return "", text


def normalize_llm_status(value: Any, *, default: str = "fallback") -> str:
    raw = str(value or "").strip().lower()
    if raw in {"ok", "error", "fallback", "salvaged", "parse_error", "timeout", "network_error", "empty_response"}:
        return raw
    if raw in {"repaired", "line_repaired"}:
        return "salvaged"
    if raw in {"disabled", "unavailable", "dry_run"}:
        return "fallback"
    return default


def classify_llm_exception(exc: Exception) -> str:
    text = str(exc or "").strip().lower()
    if isinstance(exc, TimeoutError) or "timeout" in text or "timed out" in text:
        return "timeout"
    if any(marker in text for marker in ("connection", "network", "dns", "ssl", "reset by peer", "temporarily unavailable")):
        return "network_error"
    return "error"


def make_attempt(
    *,
    step: str,
    messages: Any,
    raw_response_text: Any,
    parsed_output: Any,
    model: Any,
    provider: Any = "OpenRouter",
    latency_ms: Any = 0,
    status: Any = "ok",
    meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    system_prompt, user_prompt = split_prompt_messages(messages)
    payload = {
        "step": str(step or "").strip() or "primary",
        "role": str(meta.get("role") if isinstance(meta, dict) and meta.get("role") is not None else "").strip() if isinstance(meta, dict) else "",
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "raw_response_text": str(raw_response_text or ""),
        "parsed_output": parsed_output if isinstance(parsed_output, (dict, list)) else {},
        "model_info": {
            "provider": str(provider or "OpenRouter"),
            "model": str(model or ""),
        },
        "latency_ms": int(float(latency_ms or 0)),
        "status": normalize_llm_status(status),
    }
    if isinstance(meta, dict):
        for key, value in meta.items():
            if key in payload:
                continue
            payload[key] = value
    return payload


def build_llm_response_artifact(
    *,
    component: str,
    run_id: Any,
    trade_id: Any = "",
    story_id: Any = "",
    day: Any = "",
    status: Any = "ok",
    attempts: List[Dict[str, Any]] | None = None,
    parsed_output: Any = None,
    model_info: Dict[str, Any] | None = None,
    latency_ms: Any = 0,
    meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    out = {
        "schema_version": "llm_response_artifact.v1",
        "component": str(component or "").strip(),
        "role": str(component or "").strip(),
        "run_id": str(run_id or ""),
        "trade_id": str(trade_id or ""),
        "story_id": str(story_id or trade_id or ""),
        "day": str(day or ""),
        "saved_at": utc_now_iso(),
        "status": normalize_llm_status(status),
        "latency_ms": int(float(latency_ms or 0)),
        "parsed_output": parsed_output if isinstance(parsed_output, (dict, list)) else {},
        "model_info": dict(model_info or {}),
        "model": str((model_info or {}).get("model") or ""),
        "attempts": [dict(row) for row in list(attempts or []) if isinstance(row, dict)],
    }
    final_attempt = out["attempts"][-1] if out["attempts"] else {}
    out["system_prompt"] = str(final_attempt.get("system_prompt") or "")
    out["user_prompt"] = str(final_attempt.get("user_prompt") or "")
    out["raw_response_text"] = str(final_attempt.get("raw_response_text") or "")
    if not out["parsed_output"] and isinstance(final_attempt.get("parsed_output"), (dict, list)):
        out["parsed_output"] = final_attempt.get("parsed_output")
    out["error"] = str(final_attempt.get("error") or "")
    out["retry_count"] = max(0, len(out["attempts"]) - 1)
    if isinstance(meta, dict):
        out["meta"] = dict(meta)
        if not out["error"] and meta.get("error") is not None:
            out["error"] = str(meta.get("error") or "")
    return out


def write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text or ""), encoding="utf-8")
    return path


def trade_artifact_paths(reports_root: Path, day: str, trade_id: str) -> Dict[str, Path]:
    normalized_day = str(day or "").strip()
    trade_root = reports_root / "trades" / normalized_day / str(trade_id or "").strip()
    legacy_root = reports_root / "trades" / normalized_day[:4] / normalized_day[5:7] / str(trade_id or "").strip()
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
        "ai_trade_report_json": trade_root / "ai_trade_report" / "ai_trade_report.json",
        "ai_trade_report_md": trade_root / "ai_trade_report" / "ai_trade_report.md",
        "ai_trade_report_llm_response_json": trade_root / "ai_trade_report" / "ai_trade_report_llm_response.json",
        "brief_input_json": trade_root / "brief" / "brief_input.json",
        "brief_json": trade_root / "brief" / "operator_brief.json",
        "brief_md": trade_root / "brief" / "operator_brief.md",
        "brief_llm_response_json": trade_root / "brief" / "brief_llm_response.json",
        "trade_lifecycle_json": trade_root / "lifecycle" / "trade_lifecycle.json",
        "aggregated_execution_bundle_json": trade_root / "lifecycle" / "aggregated_execution_bundle.json",
        "strategist_evidence_json": trade_root / "evidence" / "strategist_evidence.json",
        "scanner_evidence_json": trade_root / "evidence" / "scanner_evidence.json",
        "monitor_timeline_json": trade_root / "evidence" / "monitor_timeline.json",
        "legacy_trade_story_input_json": legacy_root / "trade_story_input.json",
        "legacy_trade_report_json": legacy_root / "trade_report.json",
        "legacy_trade_report_md": legacy_root / "trade_report.md",
        "legacy_trade_lifecycle_json": legacy_root / "trade_lifecycle.json",
        "legacy_aggregated_execution_bundle_json": legacy_root / "aggregated_execution_bundle.json",
        "legacy_operator_brief_json": legacy_root / "operator_brief.json",
        "legacy_operator_brief_md": legacy_root / "operator_brief.md",
    }


def daily_artifact_paths(reports_root: Path, day: str) -> Dict[str, Path]:
    normalized_day = str(day or "").strip()
    daily_root = reports_root / "daily" / normalized_day
    return {
        "daily_root": daily_root,
        "daily_report_json": daily_root / "daily_report.json",
        "daily_report_md": daily_root / "daily_report.md",
        "daily_report_llm_response_json": daily_root / "daily_report_llm_response.json",
        "legacy_daily_json": reports_root / "daily" / f"daily_{normalized_day}.json",
        "legacy_daily_md": reports_root / "daily" / f"daily_{normalized_day}.md",
        "root_daily_json": reports_root / f"daily_{normalized_day}.json",
        "root_daily_md": reports_root / f"daily_{normalized_day}.md",
    }
