from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ..infrastructure.jsonl_tail import read_jsonl_tail
from ..models.llm_operations import LlmRecentCall


@dataclass(frozen=True, slots=True)
class LlmEventTailLoad:
    calls: list[LlmRecentCall]
    issues: list[str]
    truncated: bool


def load_recent_transport_calls(
    logs_root: Path,
    day: date,
    *,
    max_bytes: int,
    max_rows: int,
) -> LlmEventTailLoad:
    path = logs_root / "events.jsonl"
    if not path.is_file():
        return LlmEventTailLoad([], ["EVENT_LOG_UNAVAILABLE"], False)
    try:
        tail = read_jsonl_tail(
            path,
            max_bytes=max_bytes,
            max_rows=max(max_rows * 20, max_rows),
        )
    except (OSError, ValueError):
        return LlmEventTailLoad([], ["EVENT_LOG_TAIL_UNREADABLE"], False)
    calls = [_event_call(row, day) for row in tail.rows]
    resolved = [call for call in calls if call is not None]
    issues = ["RECENT_EVENT_WINDOW_ONLY"] if tail.truncated else []
    return LlmEventTailLoad(resolved, issues, tail.truncated)


def _event_call(row: dict[str, Any], day: date) -> LlmRecentCall | None:
    if row.get("stage") != "strategist_llm" or row.get("event") != "result":
        return None
    occurred_at = _as_datetime(row.get("ts_kst") or row.get("ts"))
    if occurred_at is None or occurred_at.date() != day:
        return None
    payload = row.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    return LlmRecentCall(
        occurred_at=occurred_at,
        role="strategist",
        stage=str(payload.get("call_kind") or "strategic_frame"),
        model=str(payload.get("model") or "unknown"),
        status="ok" if payload.get("ok") is True else "failed",
        latency_ms=_non_negative_float(payload.get("latency_ms")),
        attempts=_non_negative_int(payload.get("attempts")),
        error_type=str(payload.get("error_type") or "") or None,
        prompt_tokens=_non_negative_int(payload.get("prompt_tokens")),
        completion_tokens=_non_negative_int(payload.get("completion_tokens")),
        total_tokens=_non_negative_int(payload.get("total_tokens")),
        estimated_cost_usd=_non_negative_float(payload.get("estimated_cost_usd")),
    )


def _as_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return datetime.fromisoformat(f"{text}+00:00") if parsed.tzinfo is None else parsed


def _non_negative_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _non_negative_int(value: Any) -> int | None:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
