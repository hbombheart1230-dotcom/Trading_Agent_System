from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from ..infrastructure.bounded_reader import BoundedReadError, read_json_bounded


@dataclass(frozen=True, slots=True)
class RuntimeStatusArtifacts:
    lock: dict[str, Any]
    watchdog: dict[str, Any]
    market: dict[str, Any]
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WatchdogHistoryArtifacts:
    payloads: tuple[dict[str, Any], ...]
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScheduledIntelligenceArtifacts:
    preopen: dict[str, Any]
    closeout: dict[str, Any]
    briefing: dict[str, Any]
    issues: tuple[str, ...]


def load_runtime_status_artifacts(
    state_root: Path,
    reports_root: Path,
    *,
    max_bytes: int,
) -> RuntimeStatusArtifacts:
    issues: list[str] = []
    lock = _read_optional_object(
        state_root / "m13_live_loop.lock",
        max_bytes=max_bytes,
        invalid_issue="RUNTIME_LOCK_INVALID",
        issues=issues,
    )
    watchdog = _read_optional_object(
        reports_root / "runtime" / "trading_day_status" / "latest.json",
        max_bytes=max_bytes,
        invalid_issue="RUNTIME_WATCHDOG_STATUS_INVALID",
        issues=issues,
    )
    market = _read_optional_object(
        state_root / "kiwoom_market_status.json",
        max_bytes=max_bytes,
        invalid_issue="MARKET_STATUS_INVALID",
        issues=issues,
    )
    return RuntimeStatusArtifacts(lock, watchdog, market, tuple(issues))


def load_watchdog_history_artifacts(
    reports_root: Path,
    *,
    max_bytes: int,
    limit: int,
) -> WatchdogHistoryArtifacts:
    history_root = reports_root / "runtime" / "trading_day_status" / "history"
    if not history_root.is_dir():
        return WatchdogHistoryArtifacts((), ())

    issues: list[str] = []
    payloads: list[dict[str, Any]] = []
    paths = sorted(history_root.glob("*/*_watchdog.json"), reverse=True)
    for path in paths[:limit]:
        payload = _read_optional_object(
            path,
            max_bytes=max_bytes,
            invalid_issue="WATCHDOG_HISTORY_ITEM_INVALID",
            issues=issues,
        )
        if payload:
            payloads.append(payload)
    return WatchdogHistoryArtifacts(tuple(payloads), tuple(issues))


def load_scheduled_intelligence_artifacts(
    reports_root: Path,
    *,
    max_bytes: int,
    day: str | None = None,
) -> ScheduledIntelligenceArtifacts:
    issues: list[str] = []
    runtime = reports_root / "runtime" / "scheduled_jobs"
    if day:
        daily_root = runtime / day
        preopen_path = daily_root / "preopen.json"
        closeout_path = daily_root / "closeout.json"
    else:
        preopen_path = runtime / "latest_preopen.json"
        closeout_path = runtime / "latest_closeout.json"
    preopen = _read_optional_object(preopen_path, max_bytes=max_bytes, invalid_issue="PREOPEN_MANIFEST_INVALID", issues=issues)
    closeout = _read_optional_object(closeout_path, max_bytes=max_bytes, invalid_issue="CLOSEOUT_MANIFEST_INVALID", issues=issues)
    resolved_day = str(day or preopen.get("day") or closeout.get("day") or "")[:10]
    briefing = _read_optional_object(reports_root / "briefings" / resolved_day / "preopen_briefing.json", max_bytes=max_bytes, invalid_issue="PREOPEN_BRIEFING_INVALID", issues=issues) if resolved_day else {}
    return ScheduledIntelligenceArtifacts(preopen, closeout, briefing, tuple(issues))


def discover_scheduled_intelligence_days(reports_root: Path) -> list[str]:
    runtime = reports_root / "runtime" / "scheduled_jobs"
    if not runtime.is_dir():
        return []
    return sorted(
        (
            path.name
            for path in runtime.iterdir()
            if path.is_dir()
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.name)
            and ((path / "preopen.json").is_file() or (path / "closeout.json").is_file())
        ),
        reverse=True,
    )


def _read_optional_object(
    path: Path,
    *,
    max_bytes: int,
    invalid_issue: str,
    issues: list[str],
) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = read_json_bounded(path, max_bytes=max_bytes)
    except (OSError, BoundedReadError):
        issues.append(invalid_issue)
        return {}
    if not isinstance(payload, dict):
        issues.append(invalid_issue)
        return {}
    return payload
