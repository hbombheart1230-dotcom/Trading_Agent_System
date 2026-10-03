from __future__ import annotations

import sqlite3

import pytest

from pathlib import Path

from libs.core.path_isolation import _pytest_isolated_write_root, resolve_runtime_write_path
from libs.research.evidence_ledger import append_evidence_record
from libs.runtime.kiwoom_market_status import KiwoomMarketStatusListener
from libs.supervisor.intent_state_store import SQLiteIntentStateStore
from libs.supervisor.intent_store import IntentStore


_REPO_ROOT = Path(__file__).resolve().parents[1]


def _assert_contained(resolved: Path) -> None:
    isolated_root = _pytest_isolated_write_root().resolve()
    resolved.resolve().relative_to(isolated_root)  # raises ValueError if not contained


@pytest.mark.parametrize(
    "raw",
    [
        "data/x.json",
        "../data/x.json",
        "../../x.json",
        str(_REPO_ROOT / "data" / "x.json"),
        "\\data\\x.json",
        "C:data\\x.json",
        "reports/../data/x.json",
    ],
)
def test_resolve_runtime_write_path_never_escapes_isolated_root(raw: str):
    resolved = resolve_runtime_write_path(raw)
    _assert_contained(resolved)
    # Must never land literally inside the real repo's reports/ or data/.
    assert not str(resolved).startswith(str(_REPO_ROOT / "data"))
    assert not str(resolved).startswith(str(_REPO_ROOT / "reports"))


def test_resolve_runtime_write_path_redirects_repo_relative_literal():
    resolved = resolve_runtime_write_path("b.jsonl")
    assert resolved != _REPO_ROOT / "b.jsonl"
    assert not str(resolved).startswith(str(_REPO_ROOT / "b.jsonl"))


def test_resolve_runtime_write_path_passes_through_tmp_path(tmp_path: Path):
    # This repo's pytest.ini sets --basetemp=.pytest-work, so tmp_path
    # resolves *inside* the repository -- resolve_runtime_write_path must
    # not redirect it a second time.
    explicit = tmp_path / "custom.jsonl"
    assert resolve_runtime_write_path(explicit) == explicit


def test_evidence_ledger_default_path_never_touches_real_data_dir():
    rec = append_evidence_record(run_id="p0-fix2", agent="test", stage="isolation_check")
    assert rec["run_id"] == "p0-fix2"
    real_ledger = _REPO_ROOT / "data" / "evidence_ledger" / "events.jsonl"
    # Best-effort: the real ledger may already exist from production use;
    # what matters is this call didn't just append to it.
    before = real_ledger.stat().st_size if real_ledger.exists() else None
    rec2 = append_evidence_record(run_id="p0-fix2-second", agent="test", stage="isolation_check")
    after = real_ledger.stat().st_size if real_ledger.exists() else None
    assert before == after
    assert rec2["run_id"] == "p0-fix2-second"


def test_evidence_ledger_explicit_production_relative_path_is_also_redirected():
    # Codex's confirmed gap: an *explicit* log_path argument that still
    # happens to be production-relative must not bypass isolation just
    # because it was passed explicitly rather than left as the default.
    rec = append_evidence_record(
        run_id="p0-fix2-explicit",
        agent="test",
        stage="isolation_check",
        log_path="data/evidence_ledger/events.jsonl",
    )
    real_ledger = _REPO_ROOT / "data" / "evidence_ledger" / "events.jsonl"
    before = real_ledger.stat().st_size if real_ledger.exists() else None
    rec2 = append_evidence_record(
        run_id="p0-fix2-explicit-second",
        agent="test",
        stage="isolation_check",
        log_path="data/evidence_ledger/events.jsonl",
    )
    after = real_ledger.stat().st_size if real_ledger.exists() else None
    assert before == after
    assert rec2["run_id"] == "p0-fix2-explicit-second"


def test_kiwoom_market_status_listener_blocks_real_network_without_injected_factory():
    real_listener_path = _REPO_ROOT / "data" / "state" / "kiwoom_market_status_listener.json"
    before = real_listener_path.stat().st_mtime_ns if real_listener_path.exists() else None

    listener = KiwoomMarketStatusListener()
    # Call _run() synchronously (no thread) so the test doesn't need to
    # race a background thread -- the backstop check happens before
    # anything else in _run(), so this is deterministic either way.
    listener._run()

    after = real_listener_path.stat().st_mtime_ns if real_listener_path.exists() else None
    assert before == after


def test_kiwoom_market_status_listener_injected_factory_bypasses_backstop(tmp_path: Path):
    # Whether or not a valid token happens to be present in this test
    # environment's TokenCache determines whether the fake factory is
    # actually reached -- that timing isn't something this test should
    # depend on. What it *can* assert deterministically: providing a
    # connect_factory takes the DI branch instead of the fail-closed
    # backstop, so the "blocked_external_network_pytest" status must never
    # be written when a factory was explicitly injected.
    calls = {"count": 0}

    def fake_connect(url, **kwargs):
        calls["count"] += 1
        raise RuntimeError("test double: no real connection is made")

    listener_path = tmp_path / "listener_status.json"
    listener = KiwoomMarketStatusListener(connect_factory=fake_connect, listener_path=listener_path)
    listener.start()
    listener.stop()

    if listener_path.exists():
        import json

        status = json.loads(listener_path.read_text(encoding="utf-8")).get("status")
        assert status != "blocked_external_network_pytest"


def _wal_sidecar_paths(db_path: Path) -> tuple[Path, Path]:
    return db_path.with_name(db_path.name + "-wal"), db_path.with_name(db_path.name + "-shm")


@pytest.mark.parametrize(
    "ctor_path",
    ["data/state/intent_state.db", "data/custom.db", "custom.db"],
)
def test_sqlite_intent_state_store_never_touches_real_repo(ctor_path: str):
    real_db = _REPO_ROOT / "data" / "state" / "intent_state.db"
    real_custom = _REPO_ROOT / ctor_path
    before = real_db.stat().st_size if real_db.exists() else None
    before_custom = real_custom.stat().st_size if real_custom.exists() else None

    store = SQLiteIntentStateStore(ctor_path)
    _assert_contained(store.path)
    store.ensure_intent("p0-fix2-intent", initial_state="pending_approval")

    after = real_db.stat().st_size if real_db.exists() else None
    after_custom = real_custom.stat().st_size if real_custom.exists() else None
    assert before == after
    assert before_custom == after_custom

    # WAL/SHM sidecars, if sqlite created any for this connection mode,
    # must live alongside the isolated .db, never leak to the real repo.
    wal, shm = _wal_sidecar_paths(store.path)
    for sidecar in (wal, shm):
        if sidecar.exists():
            _assert_contained(sidecar)
    real_wal, real_shm = _wal_sidecar_paths(real_db)
    assert not real_wal.exists()
    assert not real_shm.exists()


def test_sqlite_intent_state_store_wal_mode_sidecars_stay_contained(tmp_path: Path):
    store = SQLiteIntentStateStore("data/state/intent_state.db")
    conn = sqlite3.connect(str(store.path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS p0_fix2_probe (x INTEGER)")
        conn.execute("INSERT INTO p0_fix2_probe VALUES (1)")
        conn.commit()
    finally:
        conn.close()
    wal, shm = _wal_sidecar_paths(store.path)
    if wal.exists():
        _assert_contained(wal)
    if shm.exists():
        _assert_contained(shm)
    real_db = _REPO_ROOT / "data" / "state" / "intent_state.db"
    real_wal, real_shm = _wal_sidecar_paths(real_db)
    assert not real_wal.exists()
    assert not real_shm.exists()


@pytest.mark.parametrize(
    "ctor_path",
    ["data/logs/intents.jsonl", "data/state/custom.jsonl", "custom.jsonl"],
)
def test_intent_store_never_touches_real_repo(ctor_path: str):
    real_target = _REPO_ROOT / ctor_path
    before = real_target.stat().st_size if real_target.exists() else None

    store = IntentStore(ctor_path)
    _assert_contained(store.path)

    after = real_target.stat().st_size if real_target.exists() else None
    assert before == after
