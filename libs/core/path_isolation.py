from __future__ import annotations

import os
import tempfile
from pathlib import Path


def running_under_pytest() -> bool:
    return bool(str(os.getenv("PYTEST_CURRENT_TEST", "") or "").strip())


def _same_path(left: Path, right: Path) -> bool:
    try:
        left_resolved = left if left.is_absolute() else Path.cwd() / left
        right_resolved = right if right.is_absolute() else Path.cwd() / right
        return left_resolved.resolve() == right_resolved.resolve()
    except Exception:
        return left == right


def isolate_canonical_path_for_pytest(
    path: str | os.PathLike[str],
    *,
    canonical_path: str | os.PathLike[str],
    isolated_name: str,
) -> Path:
    """Keep tests away from canonical runtime artifacts.

    Explicit non-canonical test paths, such as pytest ``tmp_path`` fixtures,
    remain untouched. Canonical paths from defaults or a loaded .env file are
    redirected outside the repository.
    """

    candidate = Path(path)
    if not running_under_pytest() or not _same_path(candidate, Path(canonical_path)):
        return candidate
    return (
        Path(tempfile.gettempdir())
        / "trading_agent_system_pytest"
        / str(os.getpid())
        / str(isolated_name)
    )


__all__ = [
    "isolate_canonical_path_for_pytest",
    "running_under_pytest",
]
