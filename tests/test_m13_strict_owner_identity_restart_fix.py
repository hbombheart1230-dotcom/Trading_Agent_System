"""Regression coverage for the 2026-10-02 Docker PID-1/M13 live-loop
restart-storm fix (P1.3-R1).

Confirmed root cause (RCA from the real 2026-10-01 production incident,
twice): every fresh Docker container gets PID 1 in its own PID namespace.
The OLD non-strict libs/runtime/live_loop_lock.py acquire path only ever
reclaimed a lock once it exceeded lock_stale_sec (age-based) -- but
Docker's default sub-second restart backoff meant a crashed container's
repeated restart attempts all completed well inside that window, so a
fresh container's own PID 1 was never old enough to reclaim the PID-1
lock a prior, now-dead container had left behind, even though that prior
container's process is conclusively gone. The restart budget (default 5)
exhausted itself this way every time, leaving the container permanently
exited until enough real wall-clock time passed for the age-based path to
finally kick in by coincidence.

The fix: libs/runtime/live_loop_runner.py::run_live_loop() now uses
libs/runtime/live_loop_lock.py's EXISTING strict_owner_identity=True mode
by default (the same primitive already proven for
libs/reporting/closeout_maintenance.py's single-owner guard -- not a
second locking subsystem). Strict mode reclaims on a conclusively dead pid
or confirmed pid reuse (OS process-creation-timestamp mismatch) -- NEVER
on age -- so a fresh container's PID 1 correctly reclaims a dead prior
container's PID-1 lock on its very first attempt, regardless of elapsed
time, while a genuinely live, identity-confirmed owner (the Host case)
can never be stolen from merely for running long.

refresh_live_loop_lock() previously had no strict-mode awareness at all --
calling it in strict mode would have silently overwritten the strict
schema (process_start_identity/owner_token) with the old heartbeat schema
on every tick, corrupting the very lock run_live_loop just acquired. This
file also covers refresh's new strict branch directly, since it has no
other test coverage anywhere in this repository.

Test matrix (A-J per the P1.3-R1 task spec). All synchronization is
deterministic (pre-seeding lock files / monkeypatching identity functions),
no sleep/thread timing, matching this repository's existing lock-test
conventions (tests/test_closeout_single_owner_guard.py).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from libs.runtime.live_loop_lock import (
    acquire_live_loop_lock,
    refresh_live_loop_lock,
    release_live_loop_lock,
)
from libs.runtime.live_loop_runner import run_live_loop

KST = timezone(timedelta(hours=9))


def _run_once(tmp_path: Path, *, lock_path: Path, lock_stale_sec: int = 1800, run_once_fn=None, strict_owner_identity: bool = True):
    calls = {"count": 0}

    def _default_run_once(state, dt=None):
        calls["count"] += 1
        state["last_dt"] = dt.isoformat()
        return state

    rc = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=True,
        sleep_sec=1,
        session_hard_gate=False,
        lock_path=lock_path,
        lock_stale_sec=lock_stale_sec,
        now_fn=lambda: datetime(2026, 4, 20, 9, 5, tzinfo=KST),
        run_once_fn=run_once_fn or _default_run_once,
        sleep_fn=lambda _: None,
        strict_owner_identity=strict_owner_identity,
    )
    return rc, calls


def _write_strict_lock(lock_path: Path, **fields) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")


# =============================================================================
# A -- normal single M13 owner -> acquire PASS
# =============================================================================


def test_a_normal_single_owner_acquires(tmp_path: Path) -> None:
    lock_path = tmp_path / "m13_live_loop.lock"
    rc, calls = _run_once(tmp_path, lock_path=lock_path)

    assert rc == 0
    assert calls["count"] == 1
    assert not lock_path.exists(), "a clean single-owner run must release its own lock on exit"


# =============================================================================
# B -- second live M13 owner -> BLOCKED
# =============================================================================


def test_b_second_live_owner_blocked(tmp_path: Path) -> None:
    lock_path = tmp_path / "m13_live_loop.lock"
    acquired, reason = acquire_live_loop_lock(
        lock_path, lock_stale_sec=1800, strict_owner_identity=True, owner_token="owner-A",
    )
    assert acquired is True
    assert reason == "ACQUIRED"

    def _boom(**_kwargs):
        raise AssertionError("run_once_fn must never be called when another owner holds the lock")

    rc, calls = _run_once(tmp_path, lock_path=lock_path, run_once_fn=_boom)

    assert rc == 4
    # The genuinely live owner's lock is completely undisturbed.
    still = json.loads(lock_path.read_text(encoding="utf-8"))
    assert still["owner_token"] == "owner-A"


# =============================================================================
# C -- dead owner -> reclaim PASS
# =============================================================================


def test_c_dead_owner_reclaimed(tmp_path: Path) -> None:
    lock_path = tmp_path / "m13_live_loop.lock"
    dead_pid = 999999  # essentially guaranteed not to correspond to a live process
    _write_strict_lock(
        lock_path, pid=dead_pid, process_start_identity="win:123", owner_token="dead-owner-token",
        acquired_at=0,
    )

    rc, calls = _run_once(tmp_path, lock_path=lock_path)

    assert rc == 0
    assert calls["count"] == 1


# =============================================================================
# D -- PID reused with a different process_start_identity -> reclaim PASS
# =============================================================================


def test_d_pid_reused_different_identity_reclaimed(tmp_path: Path) -> None:
    lock_path = tmp_path / "m13_live_loop.lock"
    # pid is genuinely alive (this test process itself) but the recorded
    # identity does not match its real creation identity -- simulating
    # "the process that originally held this pid is gone; the pid was
    # reused by a different process" (exactly a container-restart PID
    # collision, just without needing two literal real processes).
    _write_strict_lock(
        lock_path, pid=os.getpid(), process_start_identity="definitely-not-the-real-identity",
        owner_token="stale-owner-token", acquired_at=int(time.time()),
    )

    rc, calls = _run_once(tmp_path, lock_path=lock_path)

    assert rc == 0
    assert calls["count"] == 1


# =============================================================================
# E -- Docker-style repeated PID 1 simulation: a new process recovers a dead
# PID-1 lock INSTANTLY, with no dependency on elapsed wall-clock time. This
# is the direct regression test for the original bug: lock_stale_sec is set
# absurdly high (the OLD age-based path would have rejected this for
# centuries), yet the strict reclaim still succeeds on the very first
# attempt because it is identity-based, never age-based.
# =============================================================================


def test_e_docker_style_repeated_pid1_lock_recovered_instantly_regardless_of_age(tmp_path: Path) -> None:
    lock_path = tmp_path / "m13_live_loop.lock"
    # A prior, now-dead container's own PID 1 left this lock behind. PID 1
    # does not resolve to a real process on this Host, so it is
    # conclusively dead from this process's point of view -- exactly the
    # real Docker scenario (a fresh container's PID 1 checking a lock left
    # by a previous, exited container's own PID 1).
    _write_strict_lock(
        lock_path, pid=1, process_start_identity="win:1", owner_token="prior-dead-container",
        acquired_at=int(time.time()),  # acquired "just now" -- age is irrelevant to this path
    )

    # An absurdly large staleness window: under the OLD non-strict
    # behavior this alone would have been more than enough to block reclaim
    # for the lifetime of this test (and the original real-world bug).
    rc, calls = _run_once(tmp_path, lock_path=lock_path, lock_stale_sec=10_000_000)

    assert rc == 0, "a fresh owner must recover a dead PID-1 lock instantly, never waiting out an age window"
    assert calls["count"] == 1


# =============================================================================
# F -- identity unverifiable -> fail closed
# =============================================================================


def test_f_identity_unverifiable_fails_closed(tmp_path: Path, monkeypatch) -> None:
    lock_path = tmp_path / "m13_live_loop.lock"

    import libs.runtime.live_loop_lock as lock_mod

    monkeypatch.setattr(lock_mod, "_process_start_identity", lambda pid: None)

    def _boom(**_kwargs):
        raise AssertionError("run_once_fn must never be called when this process's own identity is unverifiable")

    rc, calls = _run_once(tmp_path, lock_path=lock_path, run_once_fn=_boom)

    assert rc == 4
    assert not lock_path.exists()


# =============================================================================
# G -- non-owner release -> blocked (direct primitive coverage: refresh's
# NEW strict branch has no other test coverage anywhere in this repo)
# =============================================================================


def test_g_non_owner_refresh_and_release_both_blocked(tmp_path: Path) -> None:
    lock_path = tmp_path / "m13_live_loop.lock"
    acquired, reason = acquire_live_loop_lock(
        lock_path, lock_stale_sec=1800, strict_owner_identity=True, owner_token="owner-A",
    )
    assert acquired is True

    refreshed, refresh_reason = refresh_live_loop_lock(
        lock_path, strict_owner_identity=True, owner_token="owner-B",
    )
    assert refreshed is False
    assert refresh_reason == "non_owner_refresh_rejected"

    released, release_reason = release_live_loop_lock(
        lock_path, strict_owner_identity=True, owner_token="owner-B",
    )
    assert released is False
    assert release_reason == "non_owner_release_rejected"

    # Untouched by either rejected attempt.
    still = json.loads(lock_path.read_text(encoding="utf-8"))
    assert still["owner_token"] == "owner-A"


# =============================================================================
# H -- exact-owner release -> PASS (and refresh preserves the strict schema
# across a heartbeat, proving the corruption risk described in this file's
# own module docstring is fixed)
# =============================================================================


def test_h_exact_owner_refresh_preserves_schema_and_release_succeeds(tmp_path: Path) -> None:
    lock_path = tmp_path / "m13_live_loop.lock"
    acquired, reason = acquire_live_loop_lock(
        lock_path, lock_stale_sec=1800, strict_owner_identity=True, owner_token="owner-A",
    )
    assert acquired is True
    before = json.loads(lock_path.read_text(encoding="utf-8"))

    refreshed, refresh_reason = refresh_live_loop_lock(
        lock_path, strict_owner_identity=True, owner_token="owner-A",
    )
    assert refreshed is True
    assert refresh_reason == "lock_heartbeat_updated"

    after = json.loads(lock_path.read_text(encoding="utf-8"))
    # The strict identity fields must survive a heartbeat completely
    # unchanged -- only a heartbeat timestamp is added.
    assert after["pid"] == before["pid"]
    assert after["process_start_identity"] == before["process_start_identity"]
    assert after["owner_token"] == before["owner_token"]
    assert after["acquired_at"] == before["acquired_at"]
    assert "heartbeat_epoch" in after and "heartbeat_ts" in after

    released, release_reason = release_live_loop_lock(
        lock_path, strict_owner_identity=True, owner_token="owner-A",
    )
    assert released is True
    assert release_reason == "released"
    assert not lock_path.exists()


def test_strict_refresh_of_missing_lock_fails_rather_than_silently_recreating(tmp_path: Path) -> None:
    """Unlike the non-strict path (which recreates a missing lock file),
    strict mode must never silently re-establish a claim via refresh --
    a missing lock means ownership was already lost (reclaimed, or
    released), and blindly recreating it here could race a legitimate new
    owner. See live_loop_lock.py's own refresh docstring."""
    lock_path = tmp_path / "m13_live_loop.lock"
    refreshed, reason = refresh_live_loop_lock(
        lock_path, strict_owner_identity=True, owner_token="owner-A",
    )
    assert refreshed is False
    assert reason == "LOCK_MISSING"
    assert not lock_path.exists()


# =============================================================================
# I / J -- no Step5C/Step5D semantics changed; no trading/broker mutation
# surface anywhere in the modified lock/runner modules
# =============================================================================


def test_lock_and_runner_modules_never_import_step5c_step5d_or_execution_surfaces():
    import libs.runtime.live_loop_lock as lock_mod
    import libs.runtime.live_loop_runner as runner_mod

    for mod in (lock_mod, runner_mod):
        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "libs.supervisor.intent_state_store" not in source
        assert "libs.execution" not in source
        assert "step5d_crash_reconciliation" not in source
