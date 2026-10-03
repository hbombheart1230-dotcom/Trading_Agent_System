"""Regression coverage for pytest artifact hygiene (permanent fix).

This repo's pytest.ini used to pin --basetemp=.pytest-work (later made
per-process via conftest.py::pytest_configure to fix a concurrent-pytest
collision), which left a `.pytest-work-<pid>/` directory behind inside the
repository after every single invocation -- pytest never deletes its own
basetemp at session end. This suite proves the fix: basetemp now lives
entirely under the OS temp directory, a successful session cleans up its
own directory, and running a real nested pytest session leaves zero new
repo-local artifacts behind, including across repeated runs.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_root_conftest():
    """Load the repo-root conftest.py by absolute file path rather than
    `import conftest` -- this repo also has a nested tests/apps/api/
    conftest.py, and a plain `import conftest` can silently resolve to
    whichever one pytest's collection order happened to register in
    sys.modules['conftest'] last (confirmed directly: this test file's own
    `import conftest` intermittently picked up the nested one instead of
    the root one when both were collected in the same session, raising
    AttributeError for names that only exist on the root module)."""
    spec = importlib.util.spec_from_file_location("_root_conftest_direct", ROOT / "conftest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


root_conftest = _load_root_conftest()

_REPO_LOCAL_SCRATCH_GLOBS = (".pytest-work*", ".pytest-today-prep*", "pytest-work*")


def _repo_local_scratch_paths() -> set[str]:
    found: set[str] = set()
    for pattern in _REPO_LOCAL_SCRATCH_GLOBS:
        found.update(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern))
    return found


def test_basetemp_root_is_outside_the_repository() -> None:
    assert not str(root_conftest._PYTEST_BASETEMP_ROOT).startswith(str(ROOT))


def test_pytest_ini_does_not_pin_a_repo_local_basetemp() -> None:
    content = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "--basetemp" not in content


def test_three_repeated_nested_sessions_leave_no_repo_local_scratch() -> None:
    """Runs a small, fast, real nested pytest session three times in a row
    (a genuine subprocess, exercising pytest_configure/pytest_sessionfinish
    for real, not a mock) and asserts the repository gains zero new
    .pytest-work*/.pytest-today-prep*-style directories across all three."""
    before = _repo_local_scratch_paths()

    target = "tests/test_pytest_artifact_hygiene.py::test_basetemp_root_is_outside_the_repository"
    for _ in range(3):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", target],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    after = _repo_local_scratch_paths()
    new_paths = after - before
    assert new_paths == set(), f"new repo-local pytest scratch leaked: {sorted(new_paths)}"


def test_successful_session_basetemp_is_removed_by_sessionfinish(tmp_path: Path) -> None:
    """Runs one real nested session and confirms its own OS-temp basetemp
    directory does not survive past a clean (all-passing) exit."""
    import os

    target = "tests/test_pytest_artifact_hygiene.py::test_basetemp_root_is_outside_the_repository"
    before_dirs = (
        set(p.name for p in root_conftest._PYTEST_BASETEMP_ROOT.iterdir())
        if root_conftest._PYTEST_BASETEMP_ROOT.is_dir()
        else set()
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", target],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    after_dirs = (
        set(p.name for p in root_conftest._PYTEST_BASETEMP_ROOT.iterdir())
        if root_conftest._PYTEST_BASETEMP_ROOT.is_dir()
        else set()
    )
    # The child process's own basetemp must not remain -- allow for other
    # concurrently-running sessions' directories (this repo is sometimes
    # used from a shared/collaborative worktree), so assert no *net growth*
    # rather than an exact empty set.
    assert len(after_dirs - before_dirs) == 0


def test_stale_directory_from_a_dead_pid_is_swept_on_next_configure(tmp_path: Path) -> None:
    """A basetemp directory whose owning PID is confirmed dead must be
    removed the next time pytest_configure runs (bounded failure-evidence
    retention -- never indefinite accumulation)."""
    root = root_conftest._PYTEST_BASETEMP_ROOT
    root.mkdir(parents=True, exist_ok=True)
    dead_pid = 999999  # confirmed-nonexistent PID convention used elsewhere in this suite
    stale_dir = root / f"{root_conftest._PYTEST_BASETEMP_PREFIX}-{dead_pid}"
    stale_dir.mkdir(exist_ok=True)
    assert not root_conftest._owning_pid_still_alive(dead_pid)

    class _FakeOption:
        basetemp = ""

    class _FakeConfig:
        option = _FakeOption()

        def addinivalue_line(self, *_a, **_k):
            pass

        def getoption(self, _name):
            return ""

    root_conftest.pytest_configure(_FakeConfig())

    assert not stale_dir.exists()


def test_no_trading_or_uef_semantics_touched() -> None:
    """This is test-infrastructure-only work -- sanity check that the fix
    lives entirely in test/config surfaces, not runtime/execution code."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(root_conftest))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    forbidden = ("libs.execution", "libs.runtime.live_loop_runner")
    for name in imported:
        assert not name.startswith(forbidden), f"conftest.py must not import {name!r}"
