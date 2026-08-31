from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

# Computed once at module import (i.e. once per process, since Python
# caches module imports) -- see _pytest_isolated_write_root() for why this
# exists alongside os.getpid().
_PROCESS_NONCE = uuid.uuid4().hex[:10]


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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _pytest_isolated_write_root() -> Path:
    # PID alone is not a safe uniqueness key here: Windows recycles PIDs
    # quickly, and this repo's full test suite is invoked repeatedly in
    # quick succession during development. A confirmed real incident: a
    # short-lived-cooldown state file (Kiwoom token refresh failure,
    # 60s TTL) written by one pytest invocation was inherited by a *later*,
    # unrelated invocation that happened to reuse the same PID within that
    # window, causing spurious cross-run failures though the two runs were
    # never using this directory at the same time. A random per-process
    # nonce (computed once at import) makes each process's write root
    # unique regardless of PID reuse.
    return (
        Path(tempfile.gettempdir())
        / "trading_agent_system_pytest"
        / f"{os.getpid()}-{_PROCESS_NONCE}"
        / "runtime_write_root"
    )


# This repository's pytest.ini sets --basetemp=.pytest-work (a path
# relative to the repo root), so every pytest tmp_path/tmp_path_factory
# fixture in this project resolves *inside* the repository rather than
# under the OS temp dir -- unlike a default pytest setup. A path already
# under one of these pytest-owned subdirectories is exactly the kind of
# "explicit non-canonical test path" that must pass through unchanged;
# without this exception, resolve_runtime_write_path would redirect every
# test's own tmp_path-based path a second time and break it.
_PYTEST_OWNED_REPO_SUBDIRS = (".pytest-work", ".pytest_cache", "__pycache__")


def resolve_runtime_write_path(path: str | os.PathLike[str]) -> Path:
    """General-purpose writable-path policy (Phase 1 P0 Fix 2).

    isolate_canonical_path_for_pytest only redirects a path that matches one
    specific, named canonical literal -- exactly right for call sites that
    know their canonical default up front, but it does nothing for a writer
    whose default is *some* repository-relative path the caller doesn't
    enumerate ahead of time (e.g. a root-level literal like "b.jsonl", or an
    explicit-but-still-production-relative argument passed straight through
    without any isolation check at all -- both confirmed leak patterns).

    Under pytest: any relative path, or any absolute path that resolves
    *inside this repository*, is redirected under one isolated root shared
    for the lifetime of this pytest process, preserving the path's relative
    structure so different callers still land in distinct files instead of
    colliding into one.

    An absolute path that resolves *outside* the repository -- which is
    exactly what every pytest ``tmp_path`` value is -- passes through
    unchanged. This is what keeps this function from redirecting a test's
    own explicit tmp_path arguments; without it, every existing test that
    builds its own tmp_path-based path would break.

    Outside pytest this is a no-op (returns the path unchanged) -- it never
    alters production behavior.
    """
    candidate = Path(path)
    if not running_under_pytest():
        return candidate
    repo_root = _repo_root()
    if candidate.is_absolute():
        try:
            rel = candidate.resolve().relative_to(repo_root)
        except (ValueError, OSError):
            return candidate
        if rel.parts and rel.parts[0] in _PYTEST_OWNED_REPO_SUBDIRS:
            return candidate
    else:
        rel = candidate
    return _pytest_isolated_write_root() / rel


__all__ = [
    "isolate_canonical_path_for_pytest",
    "resolve_runtime_write_path",
    "running_under_pytest",
]
