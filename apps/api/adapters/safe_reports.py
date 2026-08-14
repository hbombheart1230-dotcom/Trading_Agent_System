from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..infrastructure.bounded_reader import (
    BoundedReadError,
    read_bytes_bounded,
    read_json_bounded,
)


@dataclass(frozen=True, slots=True)
class ReportSpec:
    report_id: str
    title: str
    relative_path: str
    format: str


REPORT_SPECS = (
    ReportSpec("ai-summary", "AI Trade Summary", "reports/ai_trade_summary.md", "markdown"),
    ReportSpec("quant-diagnosis", "Quant Trade Diagnosis", "reports/quant_trade_diagnosis.md", "markdown"),
    ReportSpec("post-exit", "Post-exit Price Review", "reports/post_exit_shadow_recap.md", "markdown"),
    ReportSpec("strategist-summary", "Strategist Summary", "reports/strategist_summary.md", "markdown"),
    ReportSpec("trade-report", "Detailed Trade Report", "reports/ai_trade_report.md", "markdown"),
    ReportSpec("post-exit-data", "Post-exit Data", "reports/post_exit_shadow_recap.json", "json"),
    ReportSpec("quant-diagnosis-data", "Quant Diagnosis Data", "reports/quant_trade_diagnosis.json", "json"),
)

_WINDOWS_PATH = re.compile(r"(?i)[A-Z]:[\\/][^\s)\]}]+")
_REDACTED_KEYS = ("path", "prompt", "response", "order_id", "account_number")


def report_spec(report_id: str) -> ReportSpec | None:
    return next((spec for spec in REPORT_SPECS if spec.report_id == report_id), None)


def report_path(root: Path, spec: ReportSpec) -> Path:
    candidate = (root / Path(spec.relative_path)).resolve()
    candidate.relative_to(root.resolve())
    return candidate


def read_safe_report(root: Path, spec: ReportSpec, *, max_bytes: int) -> Any:
    path = report_path(root, spec)
    if spec.format == "markdown":
        payload = read_bytes_bounded(path, max_bytes=max_bytes)
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BoundedReadError("invalid UTF-8 markdown") from exc
        return _WINDOWS_PATH.sub("[redacted-path]", text)
    payload = read_json_bounded(path, max_bytes=max_bytes)
    return _sanitize_json(payload, depth=0)


def _sanitize_json(value: Any, *, depth: int) -> Any:
    if depth > 20:
        return "[redacted-depth]"
    if isinstance(value, dict):
        return {
            str(key): _sanitize_json(item, depth=depth + 1)
            for key, item in value.items()
            if not _redacted_key(str(key))
        }
    if isinstance(value, list):
        return [_sanitize_json(item, depth=depth + 1) for item in value]
    if isinstance(value, str) and _WINDOWS_PATH.search(value):
        return "[redacted-path]"
    return value


def _redacted_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _REDACTED_KEYS)
