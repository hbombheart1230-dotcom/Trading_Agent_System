from __future__ import annotations

from typing import Any, Mapping

from ..adapters.patch_notes import load_patch_notes
from ..config import ApiSettings
from ..models.common import AvailabilityStatus
from ..models.patch_notes import PatchNoteEntry, PatchNotesResponse


def _entry(value: Any) -> PatchNoteEntry | None:
    if not isinstance(value, Mapping):
        return None
    try:
        return PatchNoteEntry.model_validate(value)
    except ValueError:
        return None


def _declared_count(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def build_patch_notes(settings: ApiSettings) -> PatchNotesResponse:
    payload, error = load_patch_notes(
        settings.repository_root,
        max_bytes=settings.max_report_bytes,
    )
    raw_entries = payload.get("entries")
    values = raw_entries if isinstance(raw_entries, list) else []
    entries = [
        entry
        for value in values
        if (entry := _entry(value)) is not None
    ]
    entries.reverse()
    stages = sorted({entry.stage for entry in entries})
    types = sorted({tag for entry in entries for tag in entry.types})
    status = (
        AvailabilityStatus.UNAVAILABLE
        if error
        else AvailabilityStatus.PARTIAL
        if len(entries) != _declared_count(payload.get("entry_count"), len(entries))
        or len(entries) != len(values)
        else AvailabilityStatus.AVAILABLE
    )
    return PatchNotesResponse(
        status=status,
        schema_version=str(payload.get("schema_version") or ""),
        generated_for=str(payload.get("generated_for") or "Trading_Agent_System"),
        entry_count=len(entries),
        stages=stages,
        types=types,
        entries=entries,
        reason=error,
    )
