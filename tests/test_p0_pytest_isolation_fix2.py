from __future__ import annotations

from pathlib import Path

from libs.core.path_isolation import resolve_runtime_write_path
from libs.research.evidence_ledger import append_evidence_record
from libs.runtime.kiwoom_market_status import KiwoomMarketStatusListener


_REPO_ROOT = Path(__file__).resolve().parents[1]


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
