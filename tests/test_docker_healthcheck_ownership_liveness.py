"""P1.3-R5-A (2026-10-02): Docker LIVENESS follows the canonical SQLite
ownership heartbeat/lease, not the tick-bound lock-file heartbeat.

Why: R3 keeps the SQLite lease fresh from a background thread regardless of
tick duration, but scripts/docker_healthcheck.py still judged liveness by the
lock file's heartbeat (rewritten only at tick boundaries, threshold 120s).
Legitimate ticks (p90 ~137s, max ~434s, closeout ~55 min) therefore made a
healthy runtime look unhealthy. These tests use fake time for the "long tick"
case (no real multi-minute test) and one short real-time integration with the
actual OwnershipHeartbeat.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import types
from pathlib import Path

import pytest

import scripts.docker_healthcheck as hc
from libs.runtime.live_loop_runner import OwnershipHeartbeat
from libs.runtime.runtime_ownership import SQLiteRuntimeOwnershipStore

HOST = "container-abc"
PID = "7"
NOW = 1_800_000_000.0


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(hc, "OWNERSHIP_DB_PATH", state / "runtime_ownership.db")
    monkeypatch.setattr(hc, "LOCK_PATH", state / "m13_live_loop.lock")
    monkeypatch.setattr(hc, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(hc, "INTENT_DB_PATH", state / "intent_state.db")
    monkeypatch.setattr(hc, "EXECUTION_READINESS_SNAPSHOT_PATH", state / "execution_readiness.json")
    monkeypatch.setattr(hc, "_own_hostname", lambda: HOST)
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")
    return types.SimpleNamespace(state=state, tmp=tmp_path)


def _fake_time(monkeypatch, now=NOW):
    monkeypatch.setattr(hc, "time", types.SimpleNamespace(time=lambda: now))


def _seed_owner(env, *, owner_id=f"{HOST}:{PID}", instance_id="inst-aaaaaaaaaaaa", heartbeat_at, lease_expires_at, generation=1):
    SQLiteRuntimeOwnershipStore(str(env.state / "runtime_ownership.db"))  # creates schema (test setup only)
    conn = sqlite3.connect(str(env.state / "runtime_ownership.db"))
    conn.execute(
        "INSERT OR REPLACE INTO runtime_ownership "
        "(id, owner_id, instance_id, boot_id, acquired_at, heartbeat_at, lease_expires_at, generation) "
        "VALUES (1, ?, ?, '', ?, ?, ?, ?)",
        (owner_id, instance_id, heartbeat_at - 10, heartbeat_at, lease_expires_at, generation),
    )
    conn.commit()
    conn.close()


def _write_lock(env, *, pid=PID, heartbeat_epoch):
    (env.state / "m13_live_loop.lock").write_text(
        json.dumps({"pid": int(pid), "process_start_identity": "posix:1", "owner_token": "t", "acquired_at": 1,
                    "heartbeat_epoch": int(heartbeat_epoch)}),
        encoding="utf-8",
    )


def _snapshot(env):
    files = {}
    for p in sorted(env.tmp.rglob("*")):
        if p.is_file():
            st = p.stat()
            files[str(p.relative_to(env.tmp))] = (hashlib.sha256(p.read_bytes()).hexdigest(), st.st_mtime_ns)
    return files


# ------------------------------------------------------------- long tick ----


def test_long_tick_with_fresh_sqlite_heartbeat_is_healthy_even_if_lock_heartbeat_is_old(env, monkeypatch):
    _fake_time(monkeypatch)
    # SQLite lease kept fresh by the background heartbeat; the tick-bound lock
    # heartbeat is 500s (>> the old 120s threshold) because a tick is running.
    _seed_owner(env, heartbeat_at=NOW - 5, lease_expires_at=NOW + 25, generation=3)
    _write_lock(env, heartbeat_epoch=NOW - 500)

    ok, detail = hc._check_liveness()

    assert ok is True, detail
    assert "source=sqlite_ownership" in detail
    assert "generation=3" in detail and "instance_id=inst-aaaaaaa" in detail
    assert "lock_tick_heartbeat_age_sec=500" in detail  # reported as diagnostic, not judged


def test_the_lock_heartbeat_is_not_an_authority_when_it_is_missing_or_torn(env, monkeypatch):
    _fake_time(monkeypatch)
    _seed_owner(env, heartbeat_at=NOW - 5, lease_expires_at=NOW + 25)
    ok, detail = hc._check_liveness()
    assert ok is True and "lock_diagnostic=missing" in detail

    (env.state / "m13_live_loop.lock").write_text('{"pid": 7, "proc', encoding="utf-8")  # torn read
    ok, detail = hc._check_liveness()
    assert ok is True and "lock_diagnostic=unreadable" in detail


# ------------------------------------------------------ genuine owner loss ---


def test_genuinely_stale_or_lost_ownership_is_unhealthy(env, monkeypatch):
    _fake_time(monkeypatch)
    _seed_owner(env, heartbeat_at=NOW - 90, lease_expires_at=NOW - 60)
    _write_lock(env, heartbeat_epoch=NOW - 1)  # a fresh LOCK heartbeat must not rescue it
    ok, detail = hc._check_liveness()
    assert ok is False and detail.startswith("no_valid_owner:lease_expired")

    conn = sqlite3.connect(str(env.state / "runtime_ownership.db"))
    conn.execute("DELETE FROM runtime_ownership")
    conn.commit()
    conn.close()
    ok, detail = hc._check_liveness()
    assert ok is False and detail.startswith("no_valid_owner:no_owner_row")


def test_a_valid_lease_held_by_another_runtime_is_not_this_containers_health(env, monkeypatch):
    _fake_time(monkeypatch)
    _seed_owner(env, owner_id="some-other-host:1", heartbeat_at=NOW - 5, lease_expires_at=NOW + 25)
    ok, detail = hc._check_liveness()
    assert ok is False and detail.startswith("owner_is_other_runtime")


# ---------------------------------------------------- disagreement / reasons -


def test_lock_and_sqlite_identity_disagreement_is_unhealthy_observable_and_mutates_nothing(env, monkeypatch):
    _fake_time(monkeypatch)
    _seed_owner(env, owner_id=f"{HOST}:7", heartbeat_at=NOW - 5, lease_expires_at=NOW + 25)
    _write_lock(env, pid="99", heartbeat_epoch=NOW - 1)
    before = _snapshot(env)

    ok, detail = hc._check_liveness()

    assert ok is False
    assert detail.startswith("ownership_identity_mismatch")
    assert "sqlite_owner_pid=7" in detail and "lock_pid=99" in detail
    assert _snapshot(env) == before


# --------------------------------------------------------------- read-only --


def test_healthcheck_is_strictly_read_only(env, monkeypatch, capsys):
    _fake_time(monkeypatch)
    _seed_owner(env, heartbeat_at=NOW - 5, lease_expires_at=NOW + 25)
    _write_lock(env, heartbeat_epoch=NOW - 500)
    (env.state / "execution_readiness.json").write_text(
        json.dumps({"computed_at_epoch": int(NOW) - 10, "execution_readiness": {"ready": True}}), encoding="utf-8"
    )
    before = _snapshot(env)

    rc = hc.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "LIVENESS=PASS" in out and "OWNERSHIP_STATUS=OWNERSHIP_ACTIVE" in out
    assert _snapshot(env) == before, "no file may be created, modified, or have its mtime changed"


def test_missing_ownership_db_is_reported_and_never_created(env, monkeypatch, capsys):
    _fake_time(monkeypatch)
    db = env.state / "runtime_ownership.db"
    assert not db.exists()
    rc = hc.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "LIVENESS=FAIL (ownership_db_unreadable" in out
    assert not db.exists(), "the healthcheck must never create the ownership database"


def test_healthcheck_never_acquires_refreshes_or_releases_ownership(env, monkeypatch):
    _fake_time(monkeypatch)
    _seed_owner(env, heartbeat_at=NOW - 5, lease_expires_at=NOW + 25, generation=4)
    for name in ("acquire", "refresh", "release"):
        monkeypatch.setattr(
            SQLiteRuntimeOwnershipStore, name,
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("healthcheck must be read-only")),
        )
    hc._check_liveness()
    hc._report_ownership_status()
    conn = sqlite3.connect(str(env.state / "runtime_ownership.db"))
    assert conn.execute("select generation, heartbeat_at, lease_expires_at from runtime_ownership").fetchone() == (4, NOW - 5, NOW + 25)
    conn.close()


# ------------------------------------------------ real R3 heartbeat, short ---


def test_integration_with_the_real_heartbeat_through_a_tick_longer_than_the_lease(env):
    store = SQLiteRuntimeOwnershipStore(str(env.state / "runtime_ownership.db"))
    first = store.acquire(instance_id="live-inst-0001", owner_id=f"{HOST}:{PID}", lease_seconds=0.4, allow_stale_takeover=True)
    _write_lock(env, heartbeat_epoch=int(time.time()) - 500)  # tick-bound lock heartbeat is "old"
    hb = OwnershipHeartbeat(store, instance_id="live-inst-0001", generation=first.generation, lease_seconds=0.4).start()
    try:
        deadline = time.time() + 1.2  # 3x the lease: a "long tick" with no tick-boundary refresh
        seen = 0
        while time.time() < deadline:
            ok, detail = hc._check_liveness()
            assert ok is True, detail
            seen += 1
            time.sleep(0.05)
        assert seen > 10
    finally:
        hb.stop()
    time.sleep(0.5)  # heartbeat gone (crash/loss) -> lease lapses
    ok, detail = hc._check_liveness()
    assert ok is False and detail.startswith("no_valid_owner:lease_expired")
