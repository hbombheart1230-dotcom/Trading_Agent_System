import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --- Production-path write detector (Phase 1 Step 5B Safety Fix) ------------
#
# Primary protection is prevention: libs/runtime/canonical_artifacts.py's
# _reports_root(), and graphs/nodes/execute_from_packet.py's
# _unknown_quarantine_path()/_recent_buy_guard_path()/_recent_sell_guard_path(),
# now all route through libs/core/path_isolation.py::isolate_canonical_path_for_pytest,
# which redirects the *default* production path to a per-pid temp directory
# whenever running under pytest -- automatically, for every test file,
# without any test needing its own fixture. That is what actually stops the
# writes.
#
# This is the backstop: a session-wide (not per-test, to keep overhead low
# across thousands of tests) file-count snapshot of the real reports/ and
# data/ trees, compared at session end. It cannot pinpoint which test wrote
# something, but it reliably turns "isolation silently broken somewhere"
# into a hard, visible failure instead of quietly polluting production
# artifacts -- which is what happened before this Step (see the completion
# report for the incident this was written in response to).
_PRODUCTION_WRITE_SURFACES = ("reports", "data")


def _count_production_files() -> dict:
    counts: dict = {}
    for name in _PRODUCTION_WRITE_SURFACES:
        base = ROOT / name
        if not base.exists():
            counts[name] = 0
            continue
        try:
            counts[name] = sum(1 for p in base.rglob("*") if p.is_file())
        except OSError:
            counts[name] = -1  # unreadable -> don't claim a count, but don't crash collection either
    return counts


_production_snapshot_before: dict = {}


def pytest_sessionstart(session):  # noqa: D401 - pytest hook
    global _production_snapshot_before
    _production_snapshot_before = _count_production_files()


def pytest_sessionfinish(session, exitstatus):  # noqa: D401 - pytest hook
    after = _count_production_files()
    diffs = []
    for name in _PRODUCTION_WRITE_SURFACES:
        before_count = _production_snapshot_before.get(name, 0)
        after_count = after.get(name, 0)
        if before_count != after_count:
            diffs.append(f"{name}/: {before_count} -> {after_count} files")
    if diffs:
        sys.stderr.write(
            "\n" + "=" * 78 + "\n"
            "PRODUCTION PATH WRITE DETECTED DURING TEST SESSION\n"
            + "\n".join(f"  {d}" for d in diffs) + "\n"
            "One or more tests wrote under reports/ or data/ despite the\n"
            "project-wide pytest isolation in libs/core/path_isolation.py.\n"
            "Do not delete/clean these files automatically -- they may be\n"
            "real production artifacts. Investigate which test(s) ran and\n"
            "fix their isolation before trusting this test run's results.\n"
            + "=" * 78 + "\n"
        )
        session.exitstatus = 1


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
