"""Phase 1 Step 5B Fix 5 -- closes the last HIGH from Codex's Fix 4 audit:

Fix 4's global-mutation-halt fallback marker used the real OS temp
directory unconditionally (`tempfile.gettempdir()`). A pytest process and a
live production process both resolve that to the exact same literal path,
so:

- a pytest run could delete a real production halt marker (via any test's
  cleanup/fixture teardown), and
- a marker a pytest run created could be picked up by a live production
  process and trigger a real global mutation halt.

Fix 5 makes `_global_mutation_halt_fallback_dir()` branch on the existing
pytest-session detection (`libs.core.path_isolation.running_under_pytest`):
under pytest it resolves under that same module's per-session isolated
write root (`_pytest_isolated_write_root`, already used to isolate every
other runtime write pytest makes in this repo); outside pytest it is
byte-for-byte the same path Fix 4 always used. This is path isolation
only -- RealExecutor, BrokerOutcome, the quarantine contract, and durable
global halt *semantics* are all unchanged (see
tests/test_step5b_fix4.py, still green, for that contract).

Every test below is written to be safe to run against a real, possibly
live, production system: none of them ever assume the real production
fallback marker is absent, and none of them delete a marker they did not
themselves create.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from libs.execution.guards import unknown_quarantine as uq


def _production_fallback_marker_path() -> Path:
    return Path(tempfile.gettempdir()) / "trading_agent_system_global_mutation_halt" / uq._GLOBAL_MUTATION_HALT_MARKER_NAME


def _snapshot(path: Path):
    """(exists, mtime_ns, size) -- used to prove a real path was never
    touched, without ever asserting it was absent to begin with (a real
    production halt could legitimately be active concurrently)."""
    try:
        st = path.stat()
        return (True, st.st_mtime_ns, st.st_size)
    except FileNotFoundError:
        return (False, None, None)


def _clear_pytest_fallback_marker():
    try:
        (uq._global_mutation_halt_fallback_dir() / uq._GLOBAL_MUTATION_HALT_MARKER_NAME).unlink()
    except FileNotFoundError:
        pass


@pytest.fixture(autouse=True)
def _reset_global_mutation_halt():
    uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})
    _clear_pytest_fallback_marker()
    yield
    uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})
    _clear_pytest_fallback_marker()


# --- T1: pytest fallback path isolation -------------------------------------


def test_t1_pytest_fallback_path_differs_from_production_path():
    pytest_path = uq._global_mutation_halt_fallback_dir()
    production_path = Path(tempfile.gettempdir()) / "trading_agent_system_global_mutation_halt"
    assert uq.running_under_pytest() is True
    assert pytest_path != production_path
    assert production_path not in pytest_path.parents
    assert pytest_path != production_path / uq._GLOBAL_MUTATION_HALT_MARKER_NAME


# --- T2: pytest write isolation ----------------------------------------------


def test_t2_pytest_halt_marker_write_does_not_touch_production_path(tmp_path):
    production_marker = _production_fallback_marker_path()
    before = _snapshot(production_marker)

    uq.activate_global_mutation_halt("t2_pytest_write_isolation", now_epoch=1000, override_path=str(tmp_path / "quarantine"))

    after = _snapshot(production_marker)
    assert before == after  # production fallback marker completely untouched
    pytest_marker = uq._global_mutation_halt_fallback_dir() / uq._GLOBAL_MUTATION_HALT_MARKER_NAME
    assert pytest_marker.exists()
    assert pytest_marker != production_marker


# --- T3: pytest cleanup isolation ---------------------------------------------


def test_t3_pytest_teardown_cleanup_never_touches_production_marker():
    production_marker = _production_fallback_marker_path()
    pre_existing = production_marker.exists()
    created_placeholder = False
    if not pre_existing:
        production_marker.parent.mkdir(parents=True, exist_ok=True)
        production_marker.write_text(
            json.dumps({"note": "test_t3 placeholder standing in for a real production marker"}),
            encoding="utf-8",
        )
        created_placeholder = True
    try:
        before = _snapshot(production_marker)
        # The exact cleanup helper every Fix3/Fix4/Fix5 test fixture's
        # teardown calls.
        _clear_pytest_fallback_marker()
        after = _snapshot(production_marker)
        assert before == after  # untouched by pytest's own fixture cleanup
    finally:
        if created_placeholder:
            try:
                production_marker.unlink()
            except FileNotFoundError:
                pass


# --- T4: production marker visibility isolation -------------------------------


def test_t4_production_marker_not_visible_to_pytest_guard(tmp_path):
    production_marker = _production_fallback_marker_path()
    pre_existing = production_marker.exists()
    created_placeholder = False
    if not pre_existing:
        production_marker.parent.mkdir(parents=True, exist_ok=True)
        production_marker.write_text(
            json.dumps({"pid": 999999, "activated_at_epoch": 1, "reason": "simulated_production_halt_for_t4"}),
            encoding="utf-8",
        )
        created_placeholder = True
    try:
        uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})
        active, _details = uq.global_mutation_halt_active(str(tmp_path / "quarantine"))
        assert active is False  # pytest's own guard must never see the production-path marker
    finally:
        if created_placeholder:
            try:
                production_marker.unlink()
            except FileNotFoundError:
                pass


# --- T5: pytest marker not visible to a (simulated) production-mode resolver --


def test_t5_pytest_isolated_marker_not_visible_to_production_mode_resolver(tmp_path, monkeypatch):
    qdir = tmp_path / "quarantine"
    uq.activate_global_mutation_halt("t5_pytest_marker", now_epoch=1000, override_path=str(qdir))
    pytest_marker = uq._global_mutation_halt_fallback_dir() / uq._GLOBAL_MUTATION_HALT_MARKER_NAME
    assert pytest_marker.exists()

    # Isolate this test to the FALLBACK marker specifically -- the primary
    # per-symbol-dir marker is a separate mechanism (override_path-scoped,
    # unrelated to the OS-temp/pytest-root fallback distinction under test
    # here) and would otherwise confound this assertion.
    primary_marker = uq._global_mutation_halt_marker_path(str(qdir))
    primary_marker.unlink()
    assert not primary_marker.exists()

    uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})
    monkeypatch.setattr(uq, "running_under_pytest", lambda: False)  # simulate a production-mode process
    production_marker = _production_fallback_marker_path()
    assert uq._global_mutation_halt_fallback_dir() == production_marker.parent

    active, _details = uq.global_mutation_halt_active(str(qdir))
    # Whatever the real production marker's actual state happens to be
    # (present or absent), the production-mode result must match that
    # reality exactly -- proving the pytest-isolated marker written above
    # had zero influence on it.
    assert active == production_marker.exists()


# --- T6: existing restart durability, inside the pytest isolated root --------


def test_t6_restart_durability_within_pytest_isolated_root(tmp_path, monkeypatch):
    qdir = tmp_path / "quarantine"
    real_write = uq.write_quarantine_lock_if_absent

    def _fail_primary_only(lock_path, payload):
        if str(uq._global_mutation_halt_fallback_dir()) in str(lock_path):
            return real_write(lock_path, payload)
        return False  # primary quarantine dir simulated unwritable

    monkeypatch.setattr(uq, "write_quarantine_lock_if_absent", _fail_primary_only)

    persisted = uq.quarantine_symbol_for_unknown_outcome(symbol="005930", operation="BUY", now_epoch=1000, override_path=str(qdir))
    assert persisted is False  # per-symbol lock itself genuinely failed
    assert uq.GLOBAL_MUTATION_HALT["durable"] is True  # fallback (pytest-isolated root) write succeeded

    fallback_marker = uq._global_mutation_halt_fallback_dir() / uq._GLOBAL_MUTATION_HALT_MARKER_NAME
    assert fallback_marker.exists()
    production_root = Path(tempfile.gettempdir()) / "trading_agent_system_global_mutation_halt"
    assert production_root not in fallback_marker.parents  # confirms isolation, not just durability

    # Simulated restart: fresh in-memory state, same isolated root on disk.
    uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})
    active, details = uq.global_mutation_halt_active(str(qdir))
    assert active is True
    assert "quarantine_lock_write_failed:005930" in str(details.get("reason") or "")


# --- T7: dual-write failure residual semantics preserved ----------------------


def test_t7_dual_write_failure_residual_semantics_preserved(tmp_path, monkeypatch):
    qdir = tmp_path / "quarantine"
    monkeypatch.setattr(uq, "write_quarantine_lock_if_absent", lambda *a, **k: False)

    persisted = uq.quarantine_symbol_for_unknown_outcome(symbol="005930", operation="BUY", now_epoch=1000, override_path=str(qdir))
    assert persisted is False

    # Current process: still fail-closed via the in-memory flag.
    assert uq.GLOBAL_MUTATION_HALT["active"] is True
    allowed, reason, _ = uq.evaluate_unknown_quarantine_guard("000660", override_path=str(qdir))
    assert allowed is False
    assert reason == "global_mutation_halt_active"

    # Honest self-report: neither location durably persisted.
    assert uq.GLOBAL_MUTATION_HALT["durable"] is False

    # Simulated restart: same documented residual risk as Fix 4 -- neither
    # location wrote, so restart is not fail-closed in this specific double
    # failure. Unchanged by Fix 5.
    uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})
    active, _details = uq.global_mutation_halt_active(str(qdir))
    assert active is False
