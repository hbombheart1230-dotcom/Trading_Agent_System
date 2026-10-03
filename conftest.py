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


# --- Pytest basetemp: OS-temp, session-isolated, never repo-local ----------
# (P1.3 pytest performance cleanup, then pytest-artifact-hygiene follow-up)
#
# History: this repo used to pin a fixed, REPO-RELATIVE `--basetemp=
# .pytest-work` (pytest.ini). pytest's own tmp_path/tmp_path_factory
# fixtures derive each test's own temp directory name from *only* the
# test's own name under that fixed basetemp (e.g. `.pytest-work/
# test_foo0/`) -- two pytest PROCESSES running concurrently against
# overlapping test selections therefore raced to create/clean the
# identical directory, a hard PermissionError on Windows (confirmed
# directly: 299 spurious `[WinError 32] ... used by another process`
# errors from two overlapping invocations, no single test failing alone).
# The first fix made basetemp unique per PROCESS (`.pytest-work-<pid>`,
# still repo-relative) -- which fixed the collision but introduced a new
# problem: pytest never deletes its own basetemp directory at session end,
# so every invocation left a `.pytest-work-<pid>/` directory behind
# permanently inside the repository (confirmed directly: two such
# directories, `.pytest-work-11432` and `.pytest-work-1700`, found still
# present from earlier sessions this same day). A pre-existing, never-
# wired-in cleanup tool (scripts/cleanup_pytest_artifacts.py/.ps1/.cmd)
# existed for exactly this, but nothing ever called it automatically.
#
# Current fix: basetemp is now unique per PROCESS *and* lives entirely
# under the OS temp directory (`%TEMP%/Trading_Agent_System/pytest/
# <prefix>-<pid>/`), matching SESSION_ROOT_ENV's own placement above --
# never inside the repository at all, so "leaks" here can no longer grow
# the repository regardless of how a session ends (clean exit, Ctrl+C,
# crash, machine restart). Whatever pytest.ini's own `--basetemp` option
# says (if anything) is intentionally ignored; this is the sole owner of
# where pytest's temp roots live. Runs in pytest_configure -- before
# TempPathFactory.getbasetemp() is ever called lazily by the first
# tmp_path/tmp_path_factory fixture use.
#
# Retention stays bounded without an explicit count/age policy: a
# SUCCESSFUL session cleans up its own basetemp directory immediately (see
# pytest_sessionfinish below) -- nothing to retain. A session that fails,
# crashes, or is interrupted leaves its basetemp in place for forensic
# inspection, but the NEXT pytest invocation's own stale-directory sweep
# here removes it once its owning PID is confirmed dead -- so at most one
# leftover directory per PID that has not yet been reused survives between
# runs, never an unbounded accumulation.
_PYTEST_BASETEMP_ROOT = Path(tempfile.gettempdir()) / "Trading_Agent_System" / "pytest"
_PYTEST_BASETEMP_PREFIX = "basetemp"


def pytest_configure(config) -> None:  # noqa: D401 - pytest hook
    for name in ("fast", "p1_3", "heavy", "docker", "benchmark"):
        config.addinivalue_line(
            "markers",
            {
                "fast": "fast: pure in-process logic, no subprocess/multiprocessing, expected to run in well under a second.",
                "p1_3": "p1_3: part of the named P1.3 Docker/runtime-safety targeted regression file list.",
                "heavy": "heavy: spawns a real OS subprocess or multiprocessing.Process (interpreter cold-start cost) -- excluded from fast dev-iteration runs via `-m \"not heavy\"`, still included in a full/CI run.",
                "docker": "docker: exercises Docker-specific behavior (compose config shape, healthcheck script, image build) rather than pure Python runtime logic.",
                "benchmark": "benchmark: measures real wall-clock/memory characteristics (not just pass/fail) -- inherently slower and only meaningful run in isolation, not as part of a fast loop.",
            }[name],
        )

    parent = _PYTEST_BASETEMP_ROOT
    prefix = _PYTEST_BASETEMP_PREFIX
    # pytest's own TempPathFactory.getbasetemp() later does a plain
    # basetemp.mkdir(...) with no parents=True, assuming its parent
    # already exists (true for the old repo-relative ROOT parent, not
    # necessarily true the first time this OS-temp path is ever used on a
    # given machine) -- create the parent chain ourselves first.
    parent.mkdir(parents=True, exist_ok=True)

    if parent.is_dir():
        for entry in parent.iterdir():
            if not entry.is_dir() or not entry.name.startswith(f"{prefix}-"):
                continue
            stale_pid_str = entry.name[len(prefix) + 1:]
            try:
                stale_pid = int(stale_pid_str)
            except ValueError:
                continue
            if _owning_pid_still_alive(stale_pid):
                continue
            try:
                import shutil

                shutil.rmtree(entry, ignore_errors=True)
            except OSError:
                pass

    config.option.basetemp = str(parent / f"{prefix}-{os.getpid()}")


def _cleanup_own_basetemp_if_clean(config, *, clean: bool) -> None:
    """Clean up THIS session's own basetemp directory once it finishes
    cleanly (no test failures, no production-path write violation) --
    successful runs leave nothing behind at all, not even in the OS temp
    dir. A failing/dirty session's basetemp is kept for inspection; see
    this module's own basetemp-retention note above for why that is still
    bounded, not unlimited (the next session's own stale-PID sweep in
    pytest_configure removes it once this process has exited)."""
    if not clean:
        return
    try:
        basetemp = str(config.getoption("basetemp") or "")
    except (ValueError, KeyError):
        return
    if not basetemp:
        return
    path = Path(basetemp)
    if not path.is_dir():
        return
    try:
        parent = path.resolve().parent
    except OSError:
        parent = path.parent
    if parent != _PYTEST_BASETEMP_ROOT:
        return  # safety: only ever remove a directory we know we created
    import shutil

    shutil.rmtree(path, ignore_errors=True)


def _owning_pid_still_alive(pid: int) -> bool:
    """No new dependency (psutil is not installed in this venv) -- uses
    os.kill(pid, 0) directly. POSIX: raises ProcessLookupError (ESRCH) for
    a genuinely dead pid, no exception for a live one -- the standard
    pattern. Windows (verified directly in this environment, Python 3.14):
    os.kill(own_pid, 0) raises NOTHING for a live pid, but a dead/invalid
    pid raises a PLAIN OSError with winerror==87 ("the parameter is
    incorrect"), never ProcessLookupError -- catching only
    ProcessLookupError here would silently never detect a dead PID on
    Windows and this cleanup would never run. Any OTHER OSError (e.g.
    PermissionError for a live pid this user cannot signal) is treated as
    "alive/uncertain" -- the conservative answer, since this function's
    only use is deciding whether it is safe to delete a directory, and a
    false "alive" only costs a skipped cleanup, never a wrongly-deleted
    live process's own temp directory."""

    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError as exc:
        if getattr(exc, "winerror", None) == 87:
            return False
        return True


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


@pytest.fixture(autouse=True)
def _disable_open_order_reconciliation_guard_by_default(monkeypatch):
    """P0-A (real-readiness hardening, 2026-09-17): the deterministic
    open-order reconciliation guard (graphs/nodes/execute_from_packet.py::
    _evaluate_open_order_reconciliation_guard) fails CLOSED whenever
    state["open_order_snapshot"] was never populated -- correct for the
    real tick flow, where graphs/nodes/build_open_order_snapshot.py now
    runs unconditionally before execute_from_packet every tick, but wrong
    for the hundreds of existing tests across this repo that construct
    `state` directly and call execute_from_packet() without ever running
    the full tick flow -- they are not exercising this guard, and without
    this fixture they would all be blocked by it before ever reaching the
    guard/logic they actually test (confirmed: 35+34 such failures across
    13 files when this guard was first made deterministic).

    Global + autouse, same precedent as `_isolate_unknown_quarantine_guard`
    above, for the same reason: no test file should have to remember to
    opt out of a guard it isn't testing. The guard's own dedicated,
    opted-BACK-IN coverage lives in tests/test_p0a_open_order_reconciliation_guard.py
    and tests/test_p0_crash_matrix.py, each of which re-enables it via its
    own local autouse fixture (conftest.py fixtures of the same scope run
    before same-scope fixtures defined in the test module itself, so that
    local re-enable reliably wins).
    """
    monkeypatch.setenv("OPEN_ORDER_RECONCILIATION_GUARD_ENABLED", "false")


@pytest.fixture(autouse=True)
def _disable_execution_readiness_gate_by_default(monkeypatch):
    """P1 (execution readiness authority, 2026-09-17): the deterministic
    execution-readiness gate (graphs/nodes/execute_from_packet.py::
    _evaluate_execution_readiness_guard) fails CLOSED, in real mode, on any
    BUY/SELL whenever `state["execution_readiness"]["ready"]` isn't True --
    correct for the real tick flow, where graphs/nodes/build_execution_
    readiness.py now runs unconditionally before execute_from_packet every
    tick, but wrong for the many existing EXECUTION_MODE=real tests across
    this repo that construct `state` directly and call execute_from_packet()
    without ever running the full tick flow (no runtime_ownership, no
    portfolio_snapshot/open_order_snapshot health, no execution_readiness
    key at all) -- they are not exercising this new gate, and without this
    fixture they would all be blocked by it before ever reaching the
    guard/logic they actually test. Same precedent, same reasoning, as
    `_disable_open_order_reconciliation_guard_by_default` above (whose own
    introduction caused an identical, already-fixed regression the first
    time this session made an execution guard deterministic). This gate's
    own dedicated, opted-BACK-IN coverage lives in
    tests/test_p1_execution_readiness.py and
    tests/test_p1_e2e_execution_readiness_integrated_chain.py.
    """
    monkeypatch.setenv("EXECUTION_READINESS_GATE_ENABLED", "false")


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


def _scan_one_dir(path: str) -> Tuple[list, list]:
    """One directory's own (subdirs, [(abs_path, size, mtime_ns), ...]) --
    the unit of work handed to the thread pool below. Never raises: any
    per-entry or per-directory OSError (permission, mid-scan delete/rename
    race with the repo's own concurrent live writer) is swallowed exactly
    as the original sequential walk already did, so detection semantics
    are unchanged -- only the walk is now concurrent."""

    subdirs: list = []
    files: list = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        subdirs.append(entry.path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    st = entry.stat(follow_symlinks=False)
                    files.append((entry.path, st.st_size, st.st_mtime_ns))
                except OSError:
                    continue
    except OSError:
        pass
    return subdirs, files


def _root_level_manifest() -> Dict[str, Tuple[int, int]]:
    """The small, cheap, always-run root-level scan (Phase 1 P0 Fix 2) --
    shared by both the fast and full manifest builders below."""

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
    return manifest


def _build_manifest_full() -> Dict[str, Tuple[int, int]]:
    """Map relative_path -> (size, mtime_ns) for every watched file --
    exhaustive, every file, every directory, no depth limit. This is the
    HEAVY / opt-in audit tier (see _build_manifest's own docstring for why
    it is no longer the default).

    Perf (P1.3 pytest performance cleanup): the real reports/ + data/ trees
    are ~470-580k files under this concurrently-live-written repo -- a
    single-threaded os.scandir/stat walk of that tree measured ~115s on
    this machine. Concurrency is a real speedup with zero coverage change
    (same exact (path, size, mtime_ns) tuples as a sequential walk, just
    gathered concurrently): os.scandir/Path.stat release the GIL during
    the actual syscall, and this workload is latency-bound (many small
    syscalls), so a thread pool measured ~15-37s here (varies with
    concurrent host I/O contention) instead of ~115s. A directory-mtime-
    based skip was deliberately NOT used instead: an in-place content
    overwrite of an existing file does not reliably bump its parent
    directory's own mtime, which would have silently reintroduced exactly
    the "same-count swap escapes detection" gap this manifest-diff design
    was originally built to close -- that gap is acceptable ONLY in the
    fast/default tier below, which discloses it explicitly, never here.
    """
    from concurrent.futures import ThreadPoolExecutor

    manifest = _root_level_manifest()

    frontier = [str(ROOT / root_name) for root_name in _PRODUCTION_WATCH_ROOTS if (ROOT / root_name).exists()]
    if frontier:
        with ThreadPoolExecutor(max_workers=64) as pool:
            while frontier:
                next_frontier: list = []
                for subdirs, files in pool.map(_scan_one_dir, frontier):
                    next_frontier.extend(subdirs)
                    for abs_path, size, mtime_ns in files:
                        rel = str(Path(abs_path).relative_to(ROOT)).replace("\\", "/")
                        if _is_excluded(rel):
                            continue
                        manifest[rel] = (size, mtime_ns)
                frontier = next_frontier
    return manifest


# --- Fast/default production-write tier (P1.3 pytest performance cleanup) --
#
# Measured root cause: a FULL recursive walk of reports/+data/ costs ~76s
# on this machine even with ZERO stat() calls (is_dir()/is_file() from the
# scandir cache alone) -- 161k directories / 578k files, so the cost is the
# sheer number of os.scandir() calls itself (Windows directory-enumeration
# syscall latency at this scale), not the per-file stat. Any full-depth walk
# is therefore expensive regardless of what is collected per entry, and
# _build_manifest_full() above pays that cost twice per session (~230s
# total, unpatched) purely to protect an ever-growing, mostly-irrelevant
# production dataset that pytest's own isolation (libs/core/path_isolation.py)
# is already supposed to keep every test away from.
#
# Fast tier instead:
#   1. FULLY scan the small, high-value STATE subtrees (data/state/,
#      data/evidence_ledger/, data/strategy_memory/ -- 69+109+46 = 224
#      files total, measured) with full per-file size+mtime fidelity, same
#      as the heavy tier -- this is where a test-caused in-place overwrite
#      of an existing singleton state file (state.json-style) would land,
#      and it is cheap enough to never need sampling.
#   2. A BOUNDED-DEPTH (3 levels below reports/ and data/ themselves)
#      presence+mtime scan of the full trees -- measured ~2.4s for ~92k
#      entries. This catches any NEW top-level/day-level/run-level
#      directory or file appearing (the actual, repeatedly-observed real
#      write signature in this repo: `CREATED reports/canonical/<day>/
#      <run_id>/*.json`) without ever descending into the ~86k+ leaf
#      directories one level further, which is where the cost explodes
#      back toward the full scan.
# Disclosed, deliberate gap versus the heavy tier: an in-place content
# overwrite of an existing file sitting DEEPER than 3 levels below
# reports/or data/ (e.g. a file inside an already-existing run_id
# directory) is not detected by the fast tier. Run the heavy tier
# (PRODUCTION_WRITE_AUDIT_MODE=full) for an exhaustive audit -- e.g. before
# creating the P1.3 acceptance commit.
_FAST_TIER_FULL_SCAN_SUBTREES = ("data/state", "data/evidence_ledger", "data/strategy_memory")
_FAST_TIER_WATCH_DEPTH = 3

# Known external/host-owned churn -- FAST TIER ONLY (P1.3 pytest performance
# cleanup). Unlike _PRODUCTION_WATCH_EXCLUDE_PREFIXES above (shared by both
# tiers, kept empty), these apply only inside _build_manifest_fast(). The
# full/heavy audit tier (_build_manifest_full, PRODUCTION_WRITE_AUDIT_MODE=
# full) deliberately gets NEITHER exception -- it still sees every byte
# under data/+reports/, unweakened, for the controlled pre-freeze audit.
#
# data/logs/events.jsonl: this repo's live trading host appends to it
# continuously regardless of whether any test is running -- confirmed
# directly: caught mid-append (size growing between the before/after
# snapshot) during a single-file pytest run that performed zero writes of
# its own.
#
# data/logs/controlled_mock_lanes/<day>/: written by the REAL (non-test)
# libs/runtime/commander/execution.py as part of this host's own live
# commander loop -- confirmed directly: lane_evaluations.json's mtime
# landed inside a combined P1.3 targeted run's own window, but no test in
# that run touches libs/runtime/controlled_mock_lanes or commander/
# execution.py's real dispatch path (only mocked/monkeypatched call sites
# do). Day-partitioned, so this is a prefix, not one exact path.
#
# data/state/kiwoom_market_status_listener.json: confirmed directly --
# content shows status="registered" against a real
# wss://mockapi.kiwoom.com websocket URL, updated_at within ~30s of the
# check, immediately after (not during -- this file heartbeats every ~5s
# regardless) a combined P1.3 targeted run finished. Under pytest, any
# in-test KiwoomMarketStatusListener writes this SAME literal path through
# resolve_runtime_write_path(), which redirects it into the isolated root
# (see libs/runtime/kiwoom_market_status.py's own fail-closed pytest
# backstop, status="blocked_external_network_pytest" -- never "registered"
# under pytest) -- so a "registered" status on the real path can only come
# from this host's own live listener process, not a test.
_FAST_TIER_KNOWN_EXTERNAL_HOST_PATHS = frozenset({
    "data/logs/events.jsonl",
    "data/state/kiwoom_market_status_listener.json",
})
_FAST_TIER_KNOWN_EXTERNAL_HOST_PREFIXES = ("data/logs/controlled_mock_lanes/",)


def _is_excluded_fast_tier(rel_path: str) -> bool:
    if rel_path in _FAST_TIER_KNOWN_EXTERNAL_HOST_PATHS:
        return True
    for prefix in _FAST_TIER_KNOWN_EXTERNAL_HOST_PREFIXES:
        if rel_path.startswith(prefix) or rel_path == prefix.rstrip("/"):
            return True
    return _is_excluded(rel_path)


def _scan_subtree_full(base: Path, manifest: Dict[str, Tuple[int, int]]) -> None:
    if not base.exists():
        return
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            full = Path(dirpath) / name
            try:
                st = full.stat()
            except OSError:
                continue
            rel = str(full.relative_to(ROOT)).replace("\\", "/")
            if _is_excluded_fast_tier(rel):
                continue
            manifest[rel] = (st.st_size, st.st_mtime_ns)


def _build_manifest_fast() -> Dict[str, Tuple[int, int]]:
    """The default tier -- see the module comment above for the design and
    its disclosed coverage boundary versus _build_manifest_full()."""

    manifest = _root_level_manifest()

    for sub in _FAST_TIER_FULL_SCAN_SUBTREES:
        _scan_subtree_full(ROOT / sub, manifest)

    already_covered_prefixes = tuple(_FAST_TIER_FULL_SCAN_SUBTREES)
    for root_name in _PRODUCTION_WATCH_ROOTS:
        base = ROOT / root_name
        if not base.exists():
            continue
        frontier = [(base, 0)]
        while frontier:
            current, depth = frontier.pop()
            try:
                entries = list(os.scandir(current))
            except OSError:
                continue
            for entry in entries:
                try:
                    rel = str(Path(entry.path).relative_to(ROOT)).replace("\\", "/")
                    if _is_excluded_fast_tier(rel) or rel.startswith(already_covered_prefixes):
                        continue
                    is_dir = entry.is_dir(follow_symlinks=False)
                    st = entry.stat(follow_symlinks=False)
                    if is_dir:
                        # Sentinel size (-1): a directory entry itself, not
                        # a file -- still meaningful in the before/after
                        # diff (a NEW directory appearing, or an existing
                        # one's own mtime changing because a child was
                        # added/removed within it, both fire "modified").
                        manifest[rel] = (-1, st.st_mtime_ns)
                        # Only queue this dir for its OWN os.scandir() call
                        # (which happens unconditionally when popped, at
                        # the top of the outer while-loop) if doing so
                        # still stays within the depth budget -- queuing at
                        # depth==_FAST_TIER_WATCH_DEPTH would scandir a
                        # depth-4 listing, one level past the intended
                        # bound (measured: this off-by-one turned the
                        # "bounded" scan into a near-full-tree walk, 531k
                        # entries / 65s instead of the intended ~92k / ~2.4s).
                        if depth + 1 < _FAST_TIER_WATCH_DEPTH:
                            frontier.append((entry.path, depth + 1))
                    else:
                        manifest[rel] = (st.st_size, st.st_mtime_ns)
                except OSError:
                    continue
    return manifest


def _production_write_audit_mode() -> str:
    raw = (os.getenv("PRODUCTION_WRITE_AUDIT_MODE") or "fast").strip().lower()
    return raw if raw in ("fast", "full") else "fast"


def _build_manifest() -> Dict[str, Tuple[int, int]]:
    """Map relative_path -> (size, mtime_ns) for every watched file, in
    whichever tier PRODUCTION_WRITE_AUDIT_MODE selects (default: fast).
    See _build_manifest_fast/_build_manifest_full's own docstrings."""

    if _production_write_audit_mode() == "full":
        return _build_manifest_full()
    return _build_manifest_fast()


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
    production_write_detected = bool(created or deleted or modified)

    if not production_write_detected:
        _cleanup_own_basetemp_if_clean(
            session.config, clean=(getattr(session, "testsfailed", 0) == 0)
        )
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
        f"PRODUCTION PATH WRITE DETECTED DURING TEST SESSION (audit_mode={_production_write_audit_mode()})\n"
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
