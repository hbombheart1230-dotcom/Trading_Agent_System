from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from pathlib import Path

# Computed once at module import (i.e. once per process, since Python
# caches module imports) -- used only as a fallback when no explicit
# session marker/root is present (see _pytest_isolated_write_root()).
_PROCESS_NONCE = uuid.uuid4().hex[:10]

# Env var names for the explicit pytest session marker (Phase 1 P0
# corrective commit, item 2). Set once, project-wide, by
# conftest.py::pytest_sessionstart -- covers collection and session-scoped
# fixture setup, neither of which run inside a specific test's
# setup/call/teardown phase, so PYTEST_CURRENT_TEST alone would be unset
# during them. Also inherited by any subprocess a test spawns without
# overriding env=, so a child process's own writers see the *same*
# isolated root as the parent rather than computing a different one from
# its own PID.
SESSION_MARKER_ENV = "TRADING_AGENT_PYTEST"
SESSION_ROOT_ENV = "TRADING_AGENT_PYTEST_ROOT"


def _is_trueish(value: str | None) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def running_under_pytest() -> bool:
    if _is_trueish(os.getenv(SESSION_MARKER_ENV)):
        return True
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
    return _pytest_isolated_write_root() / str(isolated_name)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _pytest_isolated_write_root() -> Path:
    # Prefer the explicit session-wide root set once by
    # conftest.py::pytest_sessionstart. This is what makes a child
    # subprocess (which inherits the parent's env unless it overrides
    # env=) land in the *same* isolated directory as its parent, instead of
    # computing a fresh one from its own (different) PID.
    #
    # The os.getpid()+nonce fallback only matters when this module is used
    # outside of a real pytest session run through this repo's conftest.py
    # (e.g. a standalone script importing it directly) -- PID alone is not
    # a safe uniqueness key on its own: Windows recycles PIDs quickly, and
    # this repo's test suite is invoked repeatedly in quick succession
    # during development. A confirmed real incident: a short-lived-cooldown
    # state file (Kiwoom token refresh failure, 60s TTL) written by one
    # pytest invocation was inherited by a *later*, unrelated invocation
    # that happened to reuse the same PID within that window.
    explicit_root = os.getenv(SESSION_ROOT_ENV)
    if explicit_root:
        return Path(explicit_root)
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


def _escaped_fallback_path(original: str | os.PathLike[str]) -> Path:
    """Deterministic, always-contained fallback for an input whose join
    result could not be verified to stay inside the isolated root (see
    resolve_runtime_write_path). Keyed off the *original* untrusted string
    so repeated calls with the same input land on the same fallback file."""
    text = str(original)
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:24]
    suffix = Path(text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]).suffix
    return _pytest_isolated_write_root() / "_escaped_paths" / f"{digest}{suffix}"


def resolve_runtime_write_path(path: str | os.PathLike[str]) -> Path:
    """General-purpose writable-path policy (Phase 1 P0).

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

    Containment is re-verified after the join (Phase 1 P0 corrective commit,
    item 1): naive string/Path concatenation of an untrusted, possibly
    hostile input (``..`` traversal, a Windows drive-relative path like
    ``"C:data\\x.json"``, or a rooted-but-driveless path like
    ``"\\data\\x.json"``) can escape the isolated root entirely -- pathlib's
    join operator has special, easy-to-get-wrong semantics for exactly
    these forms, and ``Path.is_absolute()`` returns False for the latter
    two even though they behave like absolute paths once joined. Rather
    than trying to enumerate and special-case every such form up front,
    the joined result is resolved and checked to actually be a descendant
    of the isolated root; anything that fails that check is redirected to
    a deterministic, always-contained fallback location instead of ever
    being handed back to the caller.

    Outside pytest this is a no-op (returns the path unchanged) -- it never
    alters production behavior.
    """
    candidate = Path(path)
    if not running_under_pytest():
        return candidate

    repo_root = _repo_root()
    isolated_root = _pytest_isolated_write_root()

    if candidate.is_absolute():
        try:
            resolved_candidate = candidate.resolve()
        except OSError:
            resolved_candidate = candidate
        try:
            rel = resolved_candidate.relative_to(repo_root)
        except ValueError:
            # Genuinely outside the repository (e.g. a real OS-temp-dir
            # tmp_path some test built directly) -- leave untouched.
            return candidate
        if rel.parts and rel.parts[0] in _PYTEST_OWNED_REPO_SUBDIRS:
            return candidate
        target = isolated_root / rel
    else:
        target = isolated_root / candidate

    try:
        resolved_target = target.resolve()
    except OSError:
        resolved_target = target
    try:
        resolved_isolated_root = isolated_root.resolve()
    except OSError:
        resolved_isolated_root = isolated_root

    try:
        resolved_target.relative_to(resolved_isolated_root)
    except ValueError:
        return _escaped_fallback_path(path)
    return resolved_target


__all__ = [
    "SESSION_MARKER_ENV",
    "SESSION_ROOT_ENV",
    "isolate_canonical_path_for_pytest",
    "resolve_runtime_write_path",
    "running_under_pytest",
]
