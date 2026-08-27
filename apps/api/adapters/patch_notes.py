from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..infrastructure.bounded_reader import BoundedReadError, read_json_bounded


RELATIVE_PATH = Path(
    "docs/trading_agent_patch_notes_detailed_update/patch_notes.json"
)


def load_patch_notes(
    repository_root: Path,
    *,
    max_bytes: int,
) -> tuple[dict[str, Any], str | None]:
    path = (repository_root / RELATIVE_PATH).resolve()
    try:
        path.relative_to(repository_root.resolve())
    except ValueError:
        return {}, "patch_notes_path_outside_repository"
    if not path.exists():
        return {}, "patch_notes_missing"
    try:
        payload = read_json_bounded(path, max_bytes=max_bytes)
    except (OSError, BoundedReadError):
        return {}, "patch_notes_invalid"
    if not isinstance(payload, Mapping):
        return {}, "patch_notes_root_not_object"
    return dict(payload), None
