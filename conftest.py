import hashlib
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Tuple

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.path_isolation import SESSION_MARKER_ENV, SESSION_ROOT_ENV  # noqa: E402


# --- Explicit pytest session marker (Phase 1 P0 corrective commit) ----------
#
# libs/core/path_isolation.py::running_under_pytest() previously depended
# solely on PYTEST_CURRENT_TEST, which pytest only sets during a specific
# test's own setup/call/teardown phases -- it is unset during collection and
# during session-scoped fixture setup, so isolation could silently not
# apply to writes that happen in either of those windows. Set once here,
# for the whole session, before collection begins.
#
# This also fixes subprocess isolation: a test that spawns a child process
# via subprocess.run(...) without overriding env= inherits the *current*
# os.environ, including these two vars once set here -- so the child's own
# resolve_runtime_write_path() calls land in the exact same isolated root
# as the parent, rather than computing a different one from its own PID.
if not os.environ.get(SESSION_MARKER_ENV):
    os.environ[SESSION_MARKER_ENV] = "1"
if not os.environ.get(SESSION_ROOT_ENV):
    os.environ[SESSION_ROOT_ENV] = str(
        Path(tempfile.gettempdir())
        / "trading_agent_system_pytest"
        / f"{os.getpid()}-{uuid.uuid4().hex[:10]}"
        / "runtime_write_root"
    )


# --- Production-path write prevention (Phase 1 P0: pytest isolation) --------
#
# libs/runtime/canonical_artifacts.py::_reports_root() and the guard-path
# helpers in graphs/nodes/execute_from_packet.py already redirect their
# *default* (unset-env) production path via
# libs/core/path_isolation.py::isolate_canonical_path_for_pytest. That
# primitive only redirects when the resolved candidate is exactly equal to
# the canonical default -- by design, an *explicit* non-canonical override
# (e.g. a test's own tmp_path) passes through untouched.
#
# Root cause of the confirmed b.jsonl leak: application code sets
# EVENT_LOG_PATH / STATE_STORE_PATH directly on os.environ (e.g.
# libs/runtime/offhours_validation_runtime.py::apply_runtime_paths does
# os.environ["EVENT_LOG_PATH"] = ..., not monkeypatch.setenv, because that
# function's real job is to permanently repoint a *live* off-hours process's
# env -- it is not test-aware and should not become test-aware). Once such a
# raw write lands a real, non-canonical value like "b.jsonl" in os.environ,
# it survives past that one test's teardown (monkeypatch never tracked it,
# so it has nothing to undo) and leaks into every later test in the same
# pytest process that reads that env var without setting its own override.
#
# A per-test full os.environ snapshot/restore closes this leak class
# generically, for any current or future raw os.environ write, without
# forcing a non-default value onto tests that intentionally exercise
# "REPORTS_ROOT/EVENT_LOG_PATH left unset" behavior (several tests --
# e.g. tests/test_run_mock_exam_day.py -- assert the *canonical* resolved
# path as their expected value; injecting an isolated override
# unconditionally for every test broke those). Restoring to "whatever this
# test's environment was at its own setup time" preserves that class of
# test while still guaranteeing no raw write can outlive the test that made
# it.
@pytest.fixture(autouse=True)
def _restore_environ_after_each_test():
    snapshot = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)


@pytest.fixture(autouse=True)
def _isolate_unknown_quarantine_guard(monkeypatch, tmp_path):
    """Phase 1 Step 5B: the UNKNOWN-outcome quarantine guard
    (graphs/nodes/execute_from_packet.py::_evaluate_unknown_quarantine_guard)
    runs unconditionally for every BUY/SELL/CANCEL/MODIFY -- unlike the
    opt-in recent_buy/sell guard, it has no "disabled unless configured"
    default. Without a project-wide isolation fixture here, any test that
    exercises an UNKNOWN broker outcome would write a real quarantine record
    to data/state/execution_unknown_quarantine.json, silently blocking
    unrelated tests (and any other process) that later touch the same
    symbol. Global + autouse so no test file has to remember to opt in.
    """
    monkeypatch.setenv("UNKNOWN_QUARANTINE_GUARD_PATH", str(tmp_path / "unknown_quarantine.json"))
    # A fresh authoritative CAS database per test; subprocesses inherit it.
    monkeypatch.setenv('INTENT_STATE_DB_PATH', str(tmp_path / 'intent_state.db'))


# --- Production-path write detector (Phase 1 P0: manifest-based) ------------
#
# The prior detector only compared file *counts* under reports/ and data/ at
# session start vs. end. That misses: content modification of an existing
# file (count unchanged), a same-count swap (one file deleted, a different
# one created), and root-level files outside reports/+data/ entirely (e.g.
# b.jsonl lives at the project root). This replaces it with a manifest of
# (relative_path, size, mtime_ns) for every file under the watched roots,
# diffed at session end for create/delete/modify.
#
# Full content hashing of the *entire* baseline is not attempted: the real
# reports/ + data/ trees are ~470k files / ~90GB in this project, and hashing
# that twice (before/after) on every pytest invocation would make every test
# run infeasibly slow for marginal benefit (size+mtime_ns already reliably
# detects any write -- a write that reproduces the exact prior size and
# mtime_ns is not something an accidental leak or a normal writer produces).
# content_hash is therefore computed lazily, only for entries the
# size/mtime_ns diff already flagged as new or changed, purely to make the
# failure report more useful (not to widen detection coverage).
_PRODUCTION_WATCH_ROOTS = ("reports", "data")

# Phase 1 P0 Fix 2: root-level runtime artifacts (b.jsonl is exactly this --
# a file that lives directly at the repo root, never under reports/ or
# data/, so the recursive scan above never saw it). This is a *non-recursive*
# scan of the repo root's own files, filtered to extensions runtime code
# actually writes -- not a full repo walk (venv/, .git/, node_modules-style
# dirs are never touched by this).
_ROOT_LEVEL_WATCH_EXTENSIONS = (".jsonl", ".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3")
_ROOT_LEVEL_WATCH_SUFFIXES = ("-journal",)

# Explicit exclusions for paths that are expected to churn independent of
# any test (e.g. this repo has a concurrent external process writing to the
# live runtime tree during market hours -- see completion report). Kept
# empty by default; add glob-style relative prefixes here if a specific path
# is confirmed to be legitimate non-test churn.
_PRODUCTION_WATCH_EXCLUDE_PREFIXES: Tuple[str, ...] = ()


def _is_excluded(rel_path: str) -> bool:
    return any(rel_path.startswith(prefix) for prefix in _PRODUCTION_WATCH_EXCLUDE_PREFIXES)


def _is_root_level_watch_target(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(_ROOT_LEVEL_WATCH_EXTENSIONS) or lower.endswith(_ROOT_LEVEL_WATCH_SUFFIXES)


def _build_manifest() -> Dict[str, Tuple[int, int]]:
    """Map relative_path -> (size, mtime_ns) for every watched file."""
    manifest: Dict[str, Tuple[int, int]] = {}

    try:
        for entry in os.scandir(ROOT):
            try:
                if not entry.is_file(follow_symlinks=False):
                    continue
                if not _is_root_level_watch_target(entry.name):
                    continue
                rel = entry.name
                if _is_excluded(rel):
                    continue
                st = entry.stat(follow_symlinks=False)
                manifest[rel] = (st.st_size, st.st_mtime_ns)
            except OSError:
                continue
    except OSError:
        pass

    for root_name in _PRODUCTION_WATCH_ROOTS:
        base = ROOT / root_name
        if not base.exists():
            continue
        stack = [base]
        while stack:
            current = stack.pop()
            try:
                entries = list(os.scandir(current))
            except OSError:
                continue
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    rel = str(Path(entry.path).relative_to(ROOT)).replace("\\", "/")
                    if _is_excluded(rel):
                        continue
                    st = entry.stat(follow_symlinks=False)
                    manifest[rel] = (st.st_size, st.st_mtime_ns)
                except OSError:
                    continue
    return manifest


def _content_hash(rel_path: str) -> str:
    path = ROOT / rel_path
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError as exc:
        return f"<unreadable: {exc}>"


_production_manifest_before: Dict[str, Tuple[int, int]] = {}


def pytest_sessionstart(session):  # noqa: D401 - pytest hook
    global _production_manifest_before
    _production_manifest_before = _build_manifest()


def pytest_sessionfinish(session, exitstatus):  # noqa: D401 - pytest hook
    after = _build_manifest()
    before = _production_manifest_before

    created = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    modified = sorted(
        rel for rel in (set(after) & set(before)) if after[rel] != before[rel]
    )

    if not created and not deleted and not modified:
        return

    lines = []
    for rel in created:
        size, mtime_ns = after[rel]
        lines.append(f"  CREATED  {rel}  size={size} mtime_ns={mtime_ns} sha256={_content_hash(rel)}")
    for rel in deleted:
        size, mtime_ns = before[rel]
        lines.append(f"  DELETED  {rel}  (was size={size} mtime_ns={mtime_ns})")
    for rel in modified:
        before_size, before_mtime = before[rel]
        after_size, after_mtime = after[rel]
        lines.append(
            f"  MODIFIED {rel}  size={before_size}->{after_size} "
            f"mtime_ns={before_mtime}->{after_mtime} sha256_after={_content_hash(rel)}"
        )

    sys.stderr.write(
        "\n" + "=" * 78 + "\n"
        "PRODUCTION PATH WRITE DETECTED DURING TEST SESSION\n"
        + "\n".join(lines) + "\n"
        "One or more tests wrote under reports/, data/, or a watched\n"
        "root-level runtime artifact despite the\n"
        "project-wide pytest isolation in conftest.py / libs/core/path_isolation.py.\n"
        "Do not delete/clean these files automatically -- they may be\n"
        "real production artifacts (this repo also has a concurrent external\n"
        "process writing to the live runtime tree; check timestamps/paths\n"
        "before assuming a test caused this). Investigate which test(s) ran\n"
        "and fix their isolation before trusting this test run's results.\n"
        + "=" * 78 + "\n"
    )
    session.exitstatus = 1
