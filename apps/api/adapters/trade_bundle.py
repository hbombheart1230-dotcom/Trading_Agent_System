from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..infrastructure.bounded_reader import BoundedReadError, read_json_bounded
from ..infrastructure.trade_index import TradeBundleRef


@dataclass(frozen=True, slots=True)
class TradeBundleSource:
    ref: TradeBundleRef
    summary_input: dict[str, Any] | None
    entry: dict[str, Any] | None
    hold: dict[str, Any] | None
    exit: dict[str, Any] | None
    health: dict[str, Any] | None
    provenance: dict[str, Any] | None
    diagnosis: dict[str, Any] | None
    exclusion: dict[str, Any] | None
    source_status: str
    issues: tuple[str, ...]


def load_trade_bundle(
    ref: TradeBundleRef,
    *,
    max_bytes: int,
    detail: bool,
) -> TradeBundleSource:
    issues: list[str] = []
    summary = _read_object(
        ref.root / "reports" / "ai_trade_summary_input.json",
        max_bytes,
        "SUMMARY_INPUT",
        issues,
        required=True,
    )
    entry = _read_object(ref.root / "entry.json", max_bytes, "ENTRY", issues)
    hold = _read_object(ref.root / "hold.json", max_bytes, "HOLD", issues) if detail else None
    exit_row = _read_object(ref.root / "exit.json", max_bytes, "EXIT", issues)
    health = _read_object(ref.root / "_health.json", max_bytes, "HEALTH", issues)
    provenance = _read_object(ref.root / "_provenance.json", max_bytes, "PROVENANCE", issues) if detail else None
    diagnosis = _read_object(ref.root / "reports" / "quant_trade_diagnosis.json", max_bytes, "DIAGNOSIS", issues) if detail else None
    exclusion = _read_object(ref.root / "evaluation_exclusion.json", max_bytes, "EXCLUSION", issues) if detail else None
    if summary is None:
        status = "INVALID" if any("INVALID" in issue for issue in issues) else "MISSING"
    elif issues:
        status = "PARTIAL"
    else:
        status = "VALID"
    return TradeBundleSource(ref, summary, entry, hold, exit_row, health, provenance, diagnosis, exclusion, status, tuple(issues))


def _read_object(path, max_bytes, label, issues, required=False):
    if not path.is_file():
        if required:
            issues.append(f"MISSING_{label}")
        return None
    try:
        payload = read_json_bounded(path, max_bytes=max_bytes)
        if not isinstance(payload, dict):
            raise BoundedReadError("root must be an object")
        return payload
    except (BoundedReadError, OSError):
        issues.append(f"INVALID_{label}")
        return None
