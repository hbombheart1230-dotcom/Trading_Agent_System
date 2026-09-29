"""Regression coverage for the 2026-09-30 closeout single-owner guard, and
its same-day critical correction (strict owner-identity lock).

Bounded safety fix (independent of the still-unknown 09/28 hang and 09/29
abnormal-termination causes, neither of which is claimed fixed here): the
tick-loop closeout trigger (libs/runtime/market_status_closeout.py) and the
scheduled-fallback CLI (scripts/run_closeout_maintenance.py) both used to
call run_closeout_maintenance() directly, with no coordination -- nothing
prevented both from executing concurrently and writing the same dated
report/artifact paths at once. run_closeout_maintenance_with_lock() (in
libs/reporting/closeout_maintenance.py) adds a single-owner guard by
reusing this repository's existing PID-based lock primitive
(libs/runtime/live_loop_lock.py, already proven for the m13 live loop's
own single-instance guard) -- not a new locking framework.

CRITICAL CORRECTION covered here: the first version of this guard used the
primitive's plain (age-based) reclaim, which could steal the lock from a
genuinely still-running closeout purely because it exceeded the staleness
window -- a real runtime safety defect, given a real closeout run has
already taken ~10m37s. The guard now uses strict_owner_identity=True: a
live, identity-confirmed owner (pid + real OS process-creation timestamp)
can NEVER lose the lock on age alone. `test_t2_*` below is the direct
regression test for this fix; it replaces the OLD test that proved the bug
(a stale-but-live-pid lock being reclaimed), per explicit instruction not
to leave that unsafe expectation in place.

All synchronization here is deterministic (pre-acquiring the lock with an
explicit owner_token, or hand-writing lock file metadata) -- no sleep-based
or thread-based timing tests, per explicit instruction.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from libs.reporting.closeout_maintenance import run_closeout_maintenance_with_lock
from libs.runtime.live_loop_lock import (
    _process_start_identity,
    acquire_live_loop_lock,
    release_live_loop_lock,
)


def _read_events(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _ownership_events(log_path: Path) -> list[dict]:
    """log_closeout_stage() always writes stage="closeout_maintenance" at
    the top level (the EventLogger's own stage field); the caller-supplied
    stage name lands in payload["closeout_stage"], and the phase lands in
    the event name as f"stage_{phase}"."""
    return [e for e in _read_events(log_path) if e.get("payload", {}).get("closeout_stage") == "closeout_ownership"]


def _phase(event: dict) -> str:
    return str(event.get("event") or "").removeprefix("stage_")


def _write_strict_lock(lock_path: Path, **fields) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")


def _stub_ok(**kwargs):
    return {"schema_version": "closeout_maintenance.v1", "day": kwargs["day"], "ok": True, "steps": {}}


# =============================================================================
# T1 -- live owner younger than threshold -> reject second
# =============================================================================


def test_t1_live_owner_younger_than_threshold_rejects_second(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    acquired, reason = acquire_live_loop_lock(
        lock_path, lock_stale_sec=1800, strict_owner_identity=True, owner_token="owner-A",
    )
    assert acquired is True
    assert reason == "ACQUIRED"

    calls = {"n": 0}

    def _boom_if_called(**_kwargs):
        calls["n"] += 1
        raise AssertionError("run_closeout_maintenance must not be called when ownership is not acquired")

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _boom_if_called)

    result = run_closeout_maintenance_with_lock(
        day="2026-09-30", trigger="kiwoom_market_status_4", lock_path=lock_path, lock_stale_sec=1800,
    )

    assert calls["n"] == 0
    assert result["skipped"] is True
    assert result["skip_reason"] == "ALREADY_RUNNING_VALID_OWNER"
    assert result["ok"] is False
    assert result["steps"] == {}

    events = _ownership_events(log_path)
    reject_events = [e for e in events if _phase(e) == "reject"]
    assert len(reject_events) == 1
    assert reject_events[0]["payload"]["trigger"] == "kiwoom_market_status_4"
    assert reject_events[0]["payload"]["reason"] == "lock_active"
    assert reject_events[0]["payload"]["active_owner_pid"] == os.getpid()
    assert reject_events[0]["payload"]["long_running_valid_owner"] is False


# =============================================================================
# T2 -- CRITICAL: live owner OLDER than the staleness threshold must still
# reject a second attempt. This is the direct regression test for the
# same-day fix; the lock must never be stolen from a genuinely alive,
# identity-confirmed owner merely because it has been running a long time.
# =============================================================================


def test_t2_live_owner_older_than_threshold_still_rejects_second(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    small_stale_sec = 5
    acquired, reason = acquire_live_loop_lock(
        lock_path, lock_stale_sec=small_stale_sec, strict_owner_identity=True, owner_token="owner-A",
    )
    assert acquired is True
    assert reason == "ACQUIRED"

    # Backdate the lock well past the (tiny) staleness threshold -- under
    # the OLD, buggy behavior this alone would have been enough to let a
    # second attempt steal the lock.
    obj = json.loads(lock_path.read_text(encoding="utf-8"))
    obj["acquired_at"] = int(time.time()) - 3600
    lock_path.write_text(json.dumps(obj), encoding="utf-8")

    calls = {"n": 0}

    def _boom_if_called(**_kwargs):
        calls["n"] += 1
        raise AssertionError("a long-running but genuinely live owner must never lose its lock on age alone")

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _boom_if_called)

    result = run_closeout_maintenance_with_lock(
        day="2026-09-30", trigger="run_closeout_maintenance_fallback", lock_path=lock_path,
        lock_stale_sec=small_stale_sec,
    )

    assert calls["n"] == 0
    assert result["skipped"] is True
    assert result["skip_reason"] == "ALREADY_RUNNING_VALID_OWNER"

    # The original lock file is untouched -- ownership was never disturbed.
    still = json.loads(lock_path.read_text(encoding="utf-8"))
    assert still["owner_token"] == "owner-A"

    events = _ownership_events(log_path)
    reject_events = [e for e in events if _phase(e) == "reject"]
    assert len(reject_events) == 1
    # Age is surfaced as diagnostic metadata only -- it does not change the
    # outcome (still rejected above).
    assert reject_events[0]["payload"]["long_running_valid_owner"] is True
    assert reject_events[0]["payload"]["lock_age_sec"] >= 3600


# =============================================================================
# T3 -- dead owner -> reclaim
# =============================================================================


def test_t3_dead_owner_lock_is_reclaimed(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    dead_pid = 999999  # essentially guaranteed not to correspond to a live process
    _write_strict_lock(
        lock_path, pid=dead_pid, process_start_identity="win:123", owner_token="dead-owner-token",
        acquired_at=0,
    )

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _stub_ok)

    result = run_closeout_maintenance_with_lock(day="2026-09-30", lock_path=lock_path, lock_stale_sec=1800)

    assert result["ok"] is True
    assert not result.get("skipped")

    events = _ownership_events(log_path)
    acquire_events = [e for e in events if _phase(e) == "acquire"]
    assert len(acquire_events) == 1
    assert acquire_events[0]["payload"]["acquire_reason"] == "DEAD_OWNER_RECLAIMED"


# =============================================================================
# T4 -- PID alive but process_start_identity differs (PID reuse) -> reclaim
# =============================================================================


def test_t4_pid_reused_different_process_identity_is_reclaimed(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    # pid is genuinely alive (this test process itself) but the recorded
    # identity does not match its real creation identity -- simulating
    # "the process that originally held this pid is gone; the pid was
    # reused by a different process".
    _write_strict_lock(
        lock_path, pid=os.getpid(), process_start_identity="definitely-not-the-real-identity",
        owner_token="stale-owner-token", acquired_at=int(time.time()),
    )

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _stub_ok)

    result = run_closeout_maintenance_with_lock(day="2026-09-30", lock_path=lock_path, lock_stale_sec=1800)

    assert result["ok"] is True
    assert not result.get("skipped")

    events = _ownership_events(log_path)
    acquire_events = [e for e in events if _phase(e) == "acquire"]
    assert len(acquire_events) == 1
    assert acquire_events[0]["payload"]["acquire_reason"] == "PID_REUSE_RECLAIMED"


# =============================================================================
# T5 -- wrong owner_token on release -> rejected, lock untouched
# =============================================================================


def test_t5_release_with_wrong_owner_token_is_rejected(tmp_path):
    lock_path = tmp_path / "closeout_maintenance.lock"
    acquired, reason = acquire_live_loop_lock(
        lock_path, lock_stale_sec=1800, strict_owner_identity=True, owner_token="owner-A",
    )
    assert acquired is True

    released, status = release_live_loop_lock(lock_path, strict_owner_identity=True, owner_token="owner-B")

    assert released is False
    assert status == "non_owner_release_rejected"
    assert lock_path.exists()
    assert json.loads(lock_path.read_text(encoding="utf-8"))["owner_token"] == "owner-A"


# =============================================================================
# T6 -- wrong process identity on release -> rejected, even with matching
# pid and owner_token (the lock file changed between acquire and release)
# =============================================================================


def test_t6_release_with_mismatched_process_identity_is_rejected(tmp_path):
    lock_path = tmp_path / "closeout_maintenance.lock"
    acquired, reason = acquire_live_loop_lock(
        lock_path, lock_stale_sec=1800, strict_owner_identity=True, owner_token="owner-A",
    )
    assert acquired is True

    # Tamper with the lock file's recorded identity only (pid + token
    # unchanged) -- release must still refuse, since it cannot prove this
    # is the same lock generation it acquired.
    obj = json.loads(lock_path.read_text(encoding="utf-8"))
    obj["process_start_identity"] = "tampered-identity"
    lock_path.write_text(json.dumps(obj), encoding="utf-8")

    released, status = release_live_loop_lock(lock_path, strict_owner_identity=True, owner_token="owner-A")

    assert released is False
    assert status == "non_owner_release_rejected"
    assert lock_path.exists()


def test_t6b_release_with_unverifiable_own_identity_fails_closed(tmp_path, monkeypatch):
    """CRITICAL hotfix regression: if the caller's OWN process identity
    cannot be verified at release time (the OS facility returns None), the
    old code's `if my_identity and existing_identity and ...` check was
    falsy and silently fell through to unlink -- an unverified identity is
    NOT proof of non-ownership, but it is also NOT proof of ownership, and
    must never be treated as a free pass. Release must fail closed and
    preserve the lock."""
    import libs.runtime.live_loop_lock as lock_mod

    lock_path = tmp_path / "closeout_maintenance.lock"
    acquired, reason = acquire_live_loop_lock(
        lock_path, lock_stale_sec=1800, strict_owner_identity=True, owner_token="owner-A",
    )
    assert acquired is True
    before = lock_path.read_text(encoding="utf-8")

    monkeypatch.setattr(lock_mod, "_process_start_identity", lambda pid: None)

    released, status = release_live_loop_lock(lock_path, strict_owner_identity=True, owner_token="owner-A")

    assert released is False
    assert status == "non_owner_release_rejected"
    assert lock_path.exists()
    assert lock_path.read_text(encoding="utf-8") == before


# =============================================================================
# T7 -- malformed lock -> fail closed, no silent unlink
# =============================================================================


def test_t7a_malformed_json_fails_closed(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("{not valid json", encoding="utf-8")

    calls = {"n": 0}

    def _boom_if_called(**_kwargs):
        calls["n"] += 1
        raise AssertionError("must not run closeout on malformed lock metadata")

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _boom_if_called)

    result = run_closeout_maintenance_with_lock(day="2026-09-30", lock_path=lock_path, lock_stale_sec=1800)

    assert calls["n"] == 0
    assert result["skipped"] is True
    assert result["skip_reason"] == "LOCK_METADATA_INVALID"
    # No silent unlink -- the malformed file is left exactly as it was.
    assert lock_path.read_text(encoding="utf-8") == "{not valid json"


def test_t7b_missing_required_fields_fails_closed(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"
    # Well-formed JSON, but missing owner_token and process_start_identity
    # (e.g. a lock written by the OLD non-strict schema).
    _write_strict_lock(lock_path, pid=os.getpid(), started_epoch=int(time.time()))

    calls = {"n": 0}
    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.run_closeout_maintenance",
        lambda **_k: calls.__setitem__("n", calls["n"] + 1),
    )

    result = run_closeout_maintenance_with_lock(day="2026-09-30", lock_path=lock_path, lock_stale_sec=1800)

    assert calls["n"] == 0
    assert result["skipped"] is True
    assert result["skip_reason"] == "LOCK_METADATA_INVALID"
    assert lock_path.exists()


# =============================================================================
# T8 -- process identity unverifiable -> fail closed (never treated as dead)
# =============================================================================


def test_t8a_existing_owner_identity_unverifiable_fails_closed(tmp_path, monkeypatch):
    import libs.runtime.live_loop_lock as lock_mod

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    fake_existing_pid = 424242
    _write_strict_lock(
        lock_path, pid=fake_existing_pid, process_start_identity="some-identity",
        owner_token="owner-X", acquired_at=int(time.time()),
    )

    real_pid_exists = lock_mod.pid_exists
    real_identity_fn = lock_mod._process_start_identity

    monkeypatch.setattr(
        lock_mod, "pid_exists",
        lambda pid: True if pid == fake_existing_pid else real_pid_exists(pid),
    )
    monkeypatch.setattr(
        lock_mod, "_process_start_identity",
        lambda pid: None if pid == fake_existing_pid else real_identity_fn(pid),
    )

    calls = {"n": 0}
    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.run_closeout_maintenance",
        lambda **_k: calls.__setitem__("n", calls["n"] + 1),
    )

    result = run_closeout_maintenance_with_lock(day="2026-09-30", lock_path=lock_path, lock_stale_sec=1800)

    assert calls["n"] == 0
    assert result["skipped"] is True
    assert result["skip_reason"] == "IDENTITY_UNVERIFIABLE"
    # Fail closed: the lock is left exactly as it was, never reclaimed on a guess.
    assert json.loads(lock_path.read_text(encoding="utf-8"))["pid"] == fake_existing_pid


def test_t8b_own_identity_unverifiable_fails_closed(tmp_path, monkeypatch):
    import libs.runtime.live_loop_lock as lock_mod

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"  # no lock exists yet

    monkeypatch.setattr(lock_mod, "_process_start_identity", lambda pid: None)

    calls = {"n": 0}
    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.run_closeout_maintenance",
        lambda **_k: calls.__setitem__("n", calls["n"] + 1),
    )

    result = run_closeout_maintenance_with_lock(day="2026-09-30", lock_path=lock_path, lock_stale_sec=1800)

    assert calls["n"] == 0
    assert result["skipped"] is True
    assert result["skip_reason"] == "IDENTITY_UNVERIFIABLE"
    assert not lock_path.exists()


# =============================================================================
# T9 -- concurrent atomic acquire -> exactly one owner (deterministic guard
# contention, no threads/sleep)
# =============================================================================


def test_t9a_fresh_acquire_is_atomic_second_immediate_attempt_rejected(tmp_path):
    lock_path = tmp_path / "closeout_maintenance.lock"

    acquired_1, reason_1 = acquire_live_loop_lock(
        lock_path, lock_stale_sec=1800, strict_owner_identity=True, owner_token="owner-A",
    )
    acquired_2, reason_2 = acquire_live_loop_lock(
        lock_path, lock_stale_sec=1800, strict_owner_identity=True, owner_token="owner-B",
    )

    assert acquired_1 is True
    assert reason_1 == "ACQUIRED"
    assert acquired_2 is False
    assert reason_2 == "lock_active"
    assert json.loads(lock_path.read_text(encoding="utf-8"))["owner_token"] == "owner-A"


def test_t9b_concurrent_reclaim_is_guarded_against_double_reclaim(tmp_path, monkeypatch):
    """The dead/PID-reuse reclaim path writes through a short-lived,
    exclusively-created guard file precisely so two processes racing to
    reclaim the same dead owner's lock cannot both succeed. Simulate the
    contended case deterministically by pre-holding that guard file
    ourselves."""
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    dead_pid = 999999
    _write_strict_lock(
        lock_path, pid=dead_pid, process_start_identity="win:1", owner_token="dead-owner",
        acquired_at=0,
    )
    guard_path = lock_path.with_name(lock_path.name + ".reclaim-guard")
    guard_path.write_text("held-by-a-concurrent-reclaim-attempt", encoding="utf-8")

    try:
        calls = {"n": 0}
        monkeypatch.setattr(
            "libs.reporting.closeout_maintenance.run_closeout_maintenance",
            lambda **_k: calls.__setitem__("n", calls["n"] + 1),
        )

        result = run_closeout_maintenance_with_lock(day="2026-09-30", lock_path=lock_path, lock_stale_sec=1800)

        assert calls["n"] == 0
        assert result["skipped"] is True
        assert result["skip_reason"] == "ALREADY_RUNNING_VALID_OWNER"
        # The dead-owner lock is untouched -- no double reclaim occurred.
        assert json.loads(lock_path.read_text(encoding="utf-8"))["owner_token"] == "dead-owner"
    finally:
        guard_path.unlink(missing_ok=True)


# =============================================================================
# T10 -- exception path: a valid owner still releases its own lock
# =============================================================================


def test_t10_exception_during_closeout_still_releases_lock(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    def _boom(**_kwargs):
        raise RuntimeError("simulated closeout maintenance failure")

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _boom)

    with pytest.raises(RuntimeError, match="simulated closeout maintenance failure"):
        run_closeout_maintenance_with_lock(day="2026-09-30", trigger="kiwoom_market_status_4", lock_path=lock_path)

    assert not lock_path.exists()

    events = _ownership_events(log_path)
    phases = [_phase(e) for e in events]
    assert phases == ["acquire", "release"]
    release_events = [e for e in events if _phase(e) == "release"]
    assert release_events[0]["payload"]["released"] is True
    assert release_events[0]["payload"]["release_status"] == "released"


def test_normal_completion_releases_lock(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _stub_ok)

    result = run_closeout_maintenance_with_lock(day="2026-09-30", trigger="kiwoom_market_status_4", lock_path=lock_path)

    assert result["ok"] is True
    assert not result.get("skipped")
    assert not lock_path.exists()

    # A subsequent acquire succeeds immediately -- the lock is genuinely free.
    acquired, reason = acquire_live_loop_lock(lock_path, lock_stale_sec=1800)
    assert acquired is True
    assert reason == ""

    events = _ownership_events(log_path)
    phases = [_phase(e) for e in events]
    assert phases == ["acquire", "release"]
    assert events[0]["payload"]["owner_pid"] == os.getpid()
    assert events[1]["payload"]["owner_pid"] == os.getpid()


# =============================================================================
# T11 -- later retry after owner death/release -> succeeds
# =============================================================================


def test_t11_later_explicit_retry_after_failure_is_permitted(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    def _boom(**_kwargs):
        raise RuntimeError("simulated closeout maintenance failure")

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _boom)
    with pytest.raises(RuntimeError):
        run_closeout_maintenance_with_lock(day="2026-09-30", trigger="manual_retry_1", lock_path=lock_path)

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _stub_ok)
    result = run_closeout_maintenance_with_lock(day="2026-09-30", trigger="manual_retry_2", lock_path=lock_path)

    assert result["ok"] is True
    assert not result.get("skipped")
    assert not lock_path.exists()


def test_t11b_retry_permitted_after_dead_owner_without_release(tmp_path, monkeypatch):
    """No release ever happened (simulating a hard crash, not a handled
    exception) -- a later invocation must still succeed once the dead pid
    is detected, with no manual cleanup and no permanent lock."""
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    _write_strict_lock(
        lock_path, pid=999999, process_start_identity="win:1", owner_token="crashed-owner",
        acquired_at=0,
    )

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _stub_ok)
    result = run_closeout_maintenance_with_lock(day="2026-09-30", lock_path=lock_path, lock_stale_sec=1800)

    assert result["ok"] is True
    assert not result.get("skipped")


# =============================================================================
# T12 -- closeout integration uses strict semantics end-to-end (both
# trigger paths), not just at the run_closeout_maintenance_with_lock unit
# =============================================================================


def test_t12a_market_status_trigger_respects_long_running_live_owner(tmp_path, monkeypatch):
    """End-to-end proof that the tick-loop trigger path is wired to strict
    semantics: a long-running (backdated) but genuinely alive owner must
    still block it -- not just at the wrapper-function level."""
    import libs.runtime.market_status_closeout as mod

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    monkeypatch.setattr(
        mod, "load_market_status",
        lambda: {
            "current": {},
            "events": [
                {"event_id": "evt-t12a", "received_at": "2026-09-30T06:30:00+00:00", "code": "4"}
            ],
        },
    )

    acquired, _ = acquire_live_loop_lock(
        lock_path, lock_stale_sec=5, strict_owner_identity=True, owner_token="owner-A",
    )
    assert acquired is True
    obj = json.loads(lock_path.read_text(encoding="utf-8"))
    obj["acquired_at"] = int(time.time()) - 3600
    lock_path.write_text(json.dumps(obj), encoding="utf-8")

    from libs.reporting import closeout_maintenance as closeout_mod

    monkeypatch.setattr(closeout_mod, "_DEFAULT_CLOSEOUT_LOCK_PATH", lock_path)
    monkeypatch.setattr(closeout_mod, "_DEFAULT_CLOSEOUT_LOCK_STALE_SEC", 5)

    calls = {"n": 0}
    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.run_closeout_maintenance",
        lambda **_k: calls.__setitem__("n", calls["n"] + 1),
    )

    state = {"persisted_state": {}}
    out_state = mod.apply_market_status_closeout_events(state)

    assert calls["n"] == 0
    still = json.loads(lock_path.read_text(encoding="utf-8"))
    assert still["owner_token"] == "owner-A"
    assert "evt-t12a" in out_state["persisted_state"]["processed_market_status_event_ids"]


def test_t12b_fallback_cli_respects_long_running_live_owner(tmp_path, monkeypatch):
    """Same end-to-end proof for the scheduled-fallback CLI path."""
    import scripts.run_closeout_maintenance as cli_mod
    from libs.reporting import closeout_maintenance as closeout_mod

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    monkeypatch.setattr(sys, "argv", ["run_closeout_maintenance.py", "--day", "2026-09-30"])
    lock_path = tmp_path / "closeout_maintenance.lock"

    acquired, _ = acquire_live_loop_lock(
        lock_path, lock_stale_sec=5, strict_owner_identity=True, owner_token="owner-A",
    )
    assert acquired is True
    obj = json.loads(lock_path.read_text(encoding="utf-8"))
    obj["acquired_at"] = int(time.time()) - 3600
    lock_path.write_text(json.dumps(obj), encoding="utf-8")

    monkeypatch.setattr(closeout_mod, "_DEFAULT_CLOSEOUT_LOCK_PATH", lock_path)
    monkeypatch.setattr(closeout_mod, "_DEFAULT_CLOSEOUT_LOCK_STALE_SEC", 5)

    calls = {"n": 0}
    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.run_closeout_maintenance",
        lambda **_k: calls.__setitem__("n", calls["n"] + 1),
    )

    exit_code = cli_mod.main()

    assert calls["n"] == 0
    assert exit_code == 0  # a safe skip, not a failure
    still = json.loads(lock_path.read_text(encoding="utf-8"))
    assert still["owner_token"] == "owner-A"


# =============================================================================
# No broker/order/execution side effect anywhere in the rejected path
# =============================================================================


def test_no_execution_side_effect_when_ownership_rejected(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"
    acquire_live_loop_lock(lock_path, lock_stale_sec=1800, strict_owner_identity=True, owner_token="owner-A")

    result = run_closeout_maintenance_with_lock(day="2026-09-30", lock_path=lock_path)
    assert result["skipped"] is True


# =============================================================================
# Callers skip report writing on ownership rejection (race avoidance) --
# preserved from the original single-owner-guard pass.
# =============================================================================


def test_market_status_trigger_skips_report_write_when_ownership_rejected(tmp_path, monkeypatch):
    """When another owner holds the closeout lock, the tick-loop trigger must
    not write a report itself -- that could race against whatever the real
    owner is concurrently writing to the same dated path."""
    import libs.runtime.market_status_closeout as mod

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))

    monkeypatch.setattr(
        mod, "load_market_status",
        lambda: {
            "current": {},
            "events": [
                {"event_id": "evt-skip-1", "received_at": "2026-09-30T06:30:00+00:00", "code": "4"}
            ],
        },
    )

    def _fake_with_lock(**kwargs):
        return {
            "schema_version": "closeout_maintenance.v1", "day": kwargs["day"], "ok": False,
            "skipped": True, "skip_reason": "ALREADY_RUNNING_VALID_OWNER", "steps": {},
        }

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance_with_lock", _fake_with_lock)

    report_calls = {"n": 0}
    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.write_closeout_maintenance_report",
        lambda *a, **k: report_calls.__setitem__("n", report_calls["n"] + 1) or {},
    )

    state = {"persisted_state": {}}
    out_state = mod.apply_market_status_closeout_events(state)

    assert report_calls["n"] == 0
    persisted = out_state["persisted_state"]
    assert "evt-skip-1" in persisted["processed_market_status_event_ids"]
    # The action itself was not recorded as processed -- a genuine concurrent
    # skip must not permanently prevent a later legitimate retry.
    assert persisted.get("processed_market_status_action_keys") == []


def test_fallback_cli_skips_report_write_when_ownership_rejected(tmp_path, monkeypatch):
    """Same race-avoidance rule applies to the scheduled-fallback CLI: a
    skipped run must not write a report, and must exit cleanly (0), since
    this is an expected outcome of the guard, not a failure."""
    import scripts.run_closeout_maintenance as mod

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    monkeypatch.setattr(sys, "argv", ["run_closeout_maintenance.py", "--day", "2026-09-30"])

    def _fake_with_lock(**kwargs):
        return {
            "schema_version": "closeout_maintenance.v1", "day": kwargs["day"], "ok": False,
            "skipped": True, "skip_reason": "ALREADY_RUNNING_VALID_OWNER", "steps": {},
        }

    monkeypatch.setattr(mod, "run_closeout_maintenance_with_lock", _fake_with_lock)

    report_calls = {"n": 0}
    monkeypatch.setattr(
        mod, "write_closeout_maintenance_report",
        lambda *a, **k: report_calls.__setitem__("n", report_calls["n"] + 1) or {},
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert report_calls["n"] == 0


# =============================================================================
# process_start_identity helper itself
# =============================================================================


def test_process_start_identity_is_stable_for_the_same_live_process():
    a = _process_start_identity(os.getpid())
    b = _process_start_identity(os.getpid())
    assert a is not None
    assert a == b


def test_process_start_identity_returns_none_for_a_dead_pid():
    assert _process_start_identity(999999) is None


# =============================================================================
# No broker/order/execution side effect (import-scan)
# =============================================================================


def test_single_owner_guard_never_imports_execution_or_broker_modules():
    import ast
    import inspect

    import libs.reporting.closeout_maintenance as closeout_mod

    forbidden = ("libs.execution", "libs.read.kiwoom_order", "libs.runtime.live_loop_runner")
    tree = ast.parse(inspect.getsource(closeout_mod.run_closeout_maintenance_with_lock))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for name in imported:
        assert not name.startswith(forbidden), f"run_closeout_maintenance_with_lock must never import {name!r}"


def test_strict_lock_primitive_never_imports_execution_or_broker_modules():
    import ast
    import inspect

    import libs.runtime.live_loop_lock as lock_mod

    forbidden = ("libs.execution", "libs.read.kiwoom_order", "libs.runtime.live_loop_runner")
    for fn_name in ("acquire_live_loop_lock", "release_live_loop_lock", "_process_start_identity"):
        tree = ast.parse(inspect.getsource(getattr(lock_mod, fn_name)))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for name in imported:
            assert not name.startswith(forbidden), f"{fn_name} must never import {name!r}"
