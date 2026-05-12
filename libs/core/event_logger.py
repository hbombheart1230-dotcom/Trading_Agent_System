# libs/event_logger.py
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def new_run_id() -> str:
    """Create a unique run id for a single cycle/run."""
    return uuid.uuid4().hex


def _utc_iso() -> str:
    """UTC ISO timestamp (no microseconds)"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _to_kst_iso(iso_ts: str) -> str:
    """
    Convert an ISO timestamp to KST (+09:00) ISO format.

    If timezone info is missing, treat it as UTC.
    """
    dt = datetime.fromisoformat(iso_ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    kst = timezone(timedelta(hours=9))
    return dt.astimezone(kst).replace(microsecond=0).isoformat()


def resolve_event_log_path(default: str = "./data/logs/events.jsonl") -> Path:
    """Resolve the effective event-log path.

    Runtime defaults to the canonical operator log. During pytest, when no
    explicit EVENT_LOG_PATH is provided, route writes to a separate test log so
    local test runs do not pollute live operator artifacts.
    """
    raw = str(os.getenv("EVENT_LOG_PATH", "") or "").strip()
    if raw:
        return Path(raw)
    if os.getenv("PYTEST_CURRENT_TEST"):
        return Path("./data/logs/dev/testing/pytest_events.jsonl")
    return Path(default)


def _is_canonical_operator_event_log_path(path: Path) -> bool:
    try:
        candidate = Path(path)
        canonical_relative = Path("data") / "logs" / "events.jsonl"
        if not candidate.is_absolute():
            return candidate == canonical_relative or candidate == Path(".") / canonical_relative
        return candidate.resolve() == (Path.cwd() / canonical_relative).resolve()
    except Exception:
        return False


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            out[str(key)] = _sanitize_payload(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_sanitize_payload(item) for item in value]
    return str(value)


def build_event_envelope(
    *,
    run_id: str,
    stage: str,
    event: str,
    payload: Optional[Dict[str, Any]] = None,
    ts: Optional[str] = None,
    event_name: str = "",
    level: str = "info",
    trade_id: str = "",
    session_id: str = "",
    cycle_id: str = "",
    agent: str = "",
    phase: str = "",
    symbol: str = "",
) -> Dict[str, Any]:
    ts_utc = ts or _utc_iso()
    safe_payload = _sanitize_payload(payload or {})
    stage_text = str(stage or "").strip()
    event_text = str(event or "").strip()
    event_name_text = str(event_name or "").strip() or ".".join(part for part in (stage_text, event_text) if part)
    agent_text = str(agent or "").strip() or stage_text
    phase_text = str(phase or "").strip()
    symbol_text = str(symbol or "").strip()
    trade_id_text = str(trade_id or "").strip()
    session_id_text = str(session_id or "").strip()
    cycle_id_text = str(cycle_id or "").strip()
    return {
        "run_id": run_id,
        "ts": ts_utc,
        "ts_kst": _to_kst_iso(ts_utc),
        "stage": stage_text,
        "event": event_text,
        "event_name": event_name_text,
        "level": str(level or "info").strip().lower() or "info",
        "trade_id": trade_id_text,
        "session_id": session_id_text,
        "cycle_id": cycle_id_text,
        "agent": agent_text,
        "phase": phase_text,
        "symbol": symbol_text,
        "payload": safe_payload,
    }


def log_state_event(
    logger: "EventLogger",
    state: Dict[str, Any],
    *,
    stage: str,
    event: str,
    event_name: str,
    payload: Optional[Dict[str, Any]] = None,
    level: str = "info",
    agent: str = "",
    phase: str = "",
    symbol: str = "",
    trade_id: str = "",
    session_id: str = "",
    cycle_id: str = "",
    ts: Optional[str] = None,
) -> Dict[str, Any]:
    runtime_plan = state.get("runtime_plan") if isinstance(state.get("runtime_plan"), dict) else {}
    return logger.log(
        run_id=str(state.get("run_id") or "").strip() or "unknown-run",
        stage=stage,
        event=event,
        event_name=event_name,
        level=level,
        trade_id=str(trade_id or state.get("trade_id") or "").strip(),
        session_id=str(session_id or state.get("session_id") or runtime_plan.get("session_id") or "").strip(),
        cycle_id=str(cycle_id or state.get("cycle_id") or "").strip(),
        agent=str(agent or stage or "").strip(),
        phase=str(phase or state.get("phase") or runtime_plan.get("phase") or "").strip(),
        symbol=str(symbol or state.get("symbol") or "").strip(),
        payload=payload or {},
        ts=ts,
    )


@dataclass
class EventLogger:
    """
    Append-only JSONL event logger.

    - One event per line (JSONL)
    - Minimal schema enforced
    - Creates parent dirs automatically
    """
    log_path: Path

    def __post_init__(self) -> None:
        self.log_path = Path(self.log_path)
        if (
            os.getenv("PYTEST_CURRENT_TEST")
            and not str(os.getenv("EVENT_LOG_PATH", "") or "").strip()
            and _is_canonical_operator_event_log_path(self.log_path)
        ):
            self.log_path = resolve_event_log_path()

    def log(
        self,
        *,
        run_id: str,
        stage: str,
        event: str,
        payload: Optional[Dict[str, Any]] = None,
        ts: Optional[str] = None,
        event_name: str = "",
        level: str = "info",
        trade_id: str = "",
        session_id: str = "",
        cycle_id: str = "",
        agent: str = "",
        phase: str = "",
        symbol: str = "",
    ) -> Dict[str, Any]:
        """
        Append one event to JSONL.

        Schema:
        {
          "run_id": "...",
          "ts": "2026-02-07T01:23:45+00:00",
          "ts_kst": "2026-02-07T10:23:45+09:00",
          "stage": "strategist_plan",
          "event": "decision",
          "payload": {...}
        }
        """
        if not run_id or not isinstance(run_id, str):
            raise ValueError("run_id must be a non-empty string")
        if not stage or not isinstance(stage, str):
            raise ValueError("stage must be a non-empty string")
        if not event or not isinstance(event, str):
            raise ValueError("event must be a non-empty string")

        rec = build_event_envelope(
            run_id=run_id,
            stage=stage,
            event=event,
            payload=payload,
            ts=ts,
            event_name=event_name,
            level=level,
            trade_id=trade_id,
            session_id=session_id,
            cycle_id=cycle_id,
            agent=agent,
            phase=phase,
            symbol=symbol,
        )

        # Ensure directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Append atomically-ish (single write) for most OSes
        line = json.dumps(rec, ensure_ascii=False)
        with open(self.log_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

        return rec

    def read_all(self) -> list[Dict[str, Any]]:
        """Convenience reader for local debugging/tests."""
        if not self.log_path.exists():
            return []
        out: list[Dict[str, Any]] = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                out.append(json.loads(line))
        return out
