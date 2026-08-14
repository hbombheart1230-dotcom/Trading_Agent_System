from __future__ import annotations

import os
from pathlib import Path

from ..models.common import AvailabilityStatus
from ..models.health import SourceRootStatus


def inspect_source_roots(roots: dict[str, Path]) -> list[SourceRootStatus]:
    statuses: list[SourceRootStatus] = []
    for name, path in sorted(roots.items()):
        readable = path.is_dir() and os.access(path, os.R_OK)
        statuses.append(
            SourceRootStatus(
                source=name,
                status=(
                    AvailabilityStatus.AVAILABLE
                    if readable
                    else AvailabilityStatus.UNAVAILABLE
                ),
                readable=readable,
            )
        )
    return statuses
