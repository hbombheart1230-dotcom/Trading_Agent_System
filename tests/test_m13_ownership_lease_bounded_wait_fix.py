"""Regression coverage for the 2026-10-02 P1.3-R2 SQLite ownership-lease
restart-storm fix (second layer, found during P1.3-R1's own controlled
restart validation -- distinct from the already-fixed PID-1 file-lock
defect).

Confirmed symptom: killing a container and restarting it before the old
instance's lease (default 30s) naturally expired made
SQLiteRuntimeOwnershipStore.acquire() correctly refuse the still-valid
lease (ok=False, reason="owned_by_other_instance") -- this refusal itself
is NOT a bug, acquire() must never steal a live lease. The bug was the
CALLER (run_live_loop) giving up immediately on that refusal, so under
Docker's on-failure:5 restart policy, all 5 restarts completed faster than
the old lease's own expiry and the budget was exhausted before the
legitimate stale-takeover path was ever reachable -- ExitCode 6, container
left exited.

Fix: libs/runtime/live_loop_runner.py::_acquire_ownership_with_bounded_wait
retries, bounded by the REJECTED attempt's own observed lease_expires_at
(never a second, independently-hardcoded duration) plus a small safety
margin, until the existing store's own unmodified stale-takeover path
succeeds or the bound is exceeded (fail closed). Ownership semantics
themselves (acquire/refresh/release) are completely untouched.
"""

from __future__ import annotations

import time

from libs.runtime.live_loop_runner import _acquire_ownership_with_bounded_wait
from libs.runtime.runtime_ownership import SQLiteRuntimeOwnershipStore


def _store(tmp_path):
    return SQLiteRuntimeOwnershipStore(path=str(tmp_path / "runtime_ownership.db"))


# =============================================================================
# A -- no owner -> immediate acquire PASS
# =============================================================================


def test_a_no_owner_immediate_acquire(tmp_path):
    store = _store(tmp_path)
    result = _acquire_ownership_with_bounded_wait(
        store, instance_id="inst-A", lease_seconds=30.0, allow_stale_takeover=True,
        sleep_fn=lambda _s: (_ for _ in ()).throw(AssertionError("must not sleep when there is no prior owner")),
    )
    assert result.ok is True
    assert result.reason == "acquired_no_prior_owner"
    assert result.generation == 1


# =============================================================================
# B -- valid live owner -> must NOT steal (times out, fails closed, within a
# short bounded window -- using a tiny lease so the test itself stays fast)
# =============================================================================


def test_b_valid_live_owner_never_stolen_times_out_bounded(tmp_path):
    store = _store(tmp_path)
    first = store.acquire(instance_id="owner-live", lease_seconds=0.3, allow_stale_takeover=True)
    assert first.ok is True

    sleeps = {"n": 0}

    def _fake_sleep(seconds):
        sleeps["n"] += 1
        # The other owner keeps refreshing throughout -- it is genuinely
        # still alive for the whole bounded window, never actually expires.
        # A real (tiny) sleep so wall-clock time actually advances between
        # polls -- without it the loop busy-spins until its deadline.
        time.sleep(seconds)
        store.refresh(instance_id="owner-live", lease_seconds=0.3)

    result = _acquire_ownership_with_bounded_wait(
        store, instance_id="inst-B", lease_seconds=0.3, allow_stale_takeover=True,
        sleep_fn=_fake_sleep, wait_poll_sec=0.05, wait_margin_sec=0.1,
    )

    assert result.ok is False
    assert result.reason == "owned_by_other_instance"
    assert sleeps["n"] > 0, "must have actually waited, not given up instantly"
    # The live owner's lease is completely undisturbed.
    status = store.status()
    assert status["instance_id"] == "owner-live"
    assert status["generation"] == 1


# =============================================================================
# C -- dead/stale owner whose lease is ALREADY expired -> normal existing
# takeover PASS (no waiting needed at all)
# =============================================================================


def test_c_already_expired_lease_takes_over_without_waiting(tmp_path):
    store = _store(tmp_path)
    first = store.acquire(instance_id="dead-owner", lease_seconds=0.01, allow_stale_takeover=True)
    assert first.ok is True
    time.sleep(0.05)  # let the tiny lease genuinely expire

    def _boom(_seconds):
        raise AssertionError("an already-expired lease must take over on the first attempt, no wait needed")

    result = _acquire_ownership_with_bounded_wait(
        store, instance_id="inst-C", lease_seconds=30.0, allow_stale_takeover=True,
        sleep_fn=_boom,
    )
    assert result.ok is True
    assert result.reason == "acquired_stale_takeover"
    assert result.generation == 2


# =============================================================================
# D -- Docker-restart-before-expiry simulation: bounded wait, no storm,
# acquire succeeds once the real lease legitimately expires
# =============================================================================


def test_d_restart_before_expiry_waits_then_acquires_after_legitimate_expiry(tmp_path):
    store = _store(tmp_path)
    # A short-lived lease simulating the killed container's own lease,
    # NOT refreshed again (simulating a genuinely dead process) -- the new
    # instance must wait for it to elapse naturally, not steal it early.
    first = store.acquire(instance_id="killed-container", lease_seconds=0.15, allow_stale_takeover=True)
    assert first.ok is True

    def _real_short_sleep(seconds):
        time.sleep(seconds)

    started = time.time()
    result = _acquire_ownership_with_bounded_wait(
        store, instance_id="new-container", lease_seconds=30.0, allow_stale_takeover=True,
        sleep_fn=_real_short_sleep, wait_poll_sec=0.05, wait_margin_sec=0.2,
    )
    elapsed = time.time() - started

    assert result.ok is True
    assert result.reason == "acquired_stale_takeover"
    assert result.generation == 2
    assert elapsed < 2.0, "must not take anywhere near a full restart-storm's worth of wall-clock time"


# =============================================================================
# E -- owner remains valid for the ENTIRE bounded wait -> timeout / fail closed
# (same mechanics as B, stated as its own named case per the task's test
# matrix -- kept deliberately tiny/fast)
# =============================================================================


def test_e_owner_valid_through_entire_window_times_out_fail_closed(tmp_path):
    store = _store(tmp_path)
    first = store.acquire(instance_id="forever-owner", lease_seconds=0.3, allow_stale_takeover=True)
    assert first.ok is True

    def _refreshing_sleep(seconds):
        time.sleep(seconds)
        store.refresh(instance_id="forever-owner", lease_seconds=0.3)

    result = _acquire_ownership_with_bounded_wait(
        store, instance_id="inst-E", lease_seconds=0.3, allow_stale_takeover=True,
        sleep_fn=_refreshing_sleep, wait_poll_sec=0.05, wait_margin_sec=0.15,
    )
    assert result.ok is False
    assert result.reason == "owned_by_other_instance"


# =============================================================================
# F -- generation increments correctly after takeover (already asserted
# inline above in C/D; restated explicitly here for the task's own matrix)
# =============================================================================


def test_f_generation_increments_on_takeover(tmp_path):
    store = _store(tmp_path)
    first = store.acquire(instance_id="gen1", lease_seconds=0.01, allow_stale_takeover=True)
    assert first.generation == 1
    time.sleep(0.05)
    second = _acquire_ownership_with_bounded_wait(
        store, instance_id="gen2", lease_seconds=30.0, allow_stale_takeover=True,
        sleep_fn=lambda _s: None,
    )
    assert second.ok is True
    assert second.generation == 2


# =============================================================================
# G -- recovery_required semantics remain correct (unchanged: True only on
# a stale-takeover path, never on a no-prior-owner first acquire)
# =============================================================================


def test_g_recovery_required_semantics_unchanged(tmp_path):
    store = _store(tmp_path / "fresh")
    fresh = _acquire_ownership_with_bounded_wait(
        store, instance_id="fresh", lease_seconds=30.0, allow_stale_takeover=True,
        sleep_fn=lambda _s: None,
    )
    assert fresh.recovery_required is False

    store2 = _store(tmp_path / "takeover")  # a separate db -- independent scenario
    first = store2.acquire(instance_id="dies", lease_seconds=0.01, allow_stale_takeover=True)
    assert first.ok is True
    time.sleep(0.05)
    takeover = _acquire_ownership_with_bounded_wait(
        store2, instance_id="takes-over", lease_seconds=30.0, allow_stale_takeover=True,
        sleep_fn=lambda _s: None,
    )
    assert takeover.ok is True
    assert takeover.recovery_required is True


# =============================================================================
# H -- no Step5C/Step5D import surface in the modified module
# =============================================================================


def test_runner_module_still_never_imports_step5c_step5d_or_execution_surfaces():
    import libs.runtime.live_loop_runner as runner_mod
    from pathlib import Path

    source = Path(runner_mod.__file__).read_text(encoding="utf-8")
    assert "libs.supervisor.intent_state_store" not in source
    assert "libs.execution" not in source
    assert "step5d_crash_reconciliation" not in source
