from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

_WRITE_LOCK = Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sanitize(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        out: Dict[str, Any] = {}
        for k, x in v.items():
            out[str(k)] = _sanitize(x)
        return out
    if isinstance(v, (list, tuple)):
        return [_sanitize(x) for x in v]
    return str(v)


def _resolve_log_path(path: Optional[str | Path] = None) -> Path:
    if path is not None:
        return Path(path)
    raw = str(os.getenv("EVIDENCE_LEDGER_PATH", "data/evidence_ledger/events.jsonl") or "").strip()
    return Path(raw or "data/evidence_ledger/events.jsonl")


def append_evidence_record(
    *,
    run_id: str,
    agent: str,
    stage: str,
    raw_input: Any = None,
    llm_prompt: Any = None,
    llm_response: Any = None,
    parsed_output: Any = None,
    decision_link: Any = None,
    timestamp: Optional[str] = None,
    log_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Append one evidence record as JSONL.

    This function is passive logging only and does not mutate runtime decisions.
    """
    record: Dict[str, Any] = {
        "run_id": str(run_id or "").strip() or "unknown-run",
        "timestamp": str(timestamp or _now_iso()),
        "agent": str(agent or "").strip().lower() or "unknown-agent",
        "stage": str(stage or "").strip() or "unspecified",
        "raw_input": _sanitize(raw_input) if raw_input is not None else {},
        "llm_prompt": str(llm_prompt or ""),
        "llm_response": str(llm_response or ""),
        "parsed_output": _sanitize(parsed_output) if parsed_output is not None else {},
        "decision_link": _sanitize(decision_link) if decision_link is not None else {},
    }

    path = _resolve_log_path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with _WRITE_LOCK:
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
    return record


def record_raw_input(
    *,
    run_id: str,
    agent: str,
    stage: str,
    raw_input: Dict[str, Any],
    decision_link: Optional[Dict[str, Any]] = None,
    log_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    return append_evidence_record(
        run_id=run_id,
        agent=agent,
        stage=stage,
        raw_input=raw_input,
        decision_link=decision_link or {},
        log_path=log_path,
    )


def record_llm_prompt(
    *,
    run_id: str,
    agent: str,
    stage: str,
    llm_prompt: str,
    raw_input: Optional[Dict[str, Any]] = None,
    decision_link: Optional[Dict[str, Any]] = None,
    log_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    return append_evidence_record(
        run_id=run_id,
        agent=agent,
        stage=stage,
        raw_input=raw_input or {},
        llm_prompt=llm_prompt,
        decision_link=decision_link or {},
        log_path=log_path,
    )


def record_llm_response(
    *,
    run_id: str,
    agent: str,
    stage: str,
    llm_response: str,
    parsed_output: Optional[Dict[str, Any]] = None,
    decision_link: Optional[Dict[str, Any]] = None,
    log_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    return append_evidence_record(
        run_id=run_id,
        agent=agent,
        stage=stage,
        llm_response=llm_response,
        parsed_output=parsed_output or {},
        decision_link=decision_link or {},
        log_path=log_path,
    )


def record_decision_bridge(
    *,
    run_id: str,
    agent: str,
    stage: str,
    parsed_output: Optional[Dict[str, Any]] = None,
    decision_link: Optional[Dict[str, Any]] = None,
    raw_input: Optional[Dict[str, Any]] = None,
    log_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    return append_evidence_record(
        run_id=run_id,
        agent=agent,
        stage=stage,
        raw_input=raw_input or {},
        parsed_output=parsed_output or {},
        decision_link=decision_link or {},
        log_path=log_path,
    )
