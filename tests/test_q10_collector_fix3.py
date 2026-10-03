"""2026-09-05 PRE-STEP5C CLEANUP FIX 3 (second independent Codex re-audit,
REJECTed FIX 2). Reproduces Codex's exact failure-boundary conditions
first, then verifies the invariant that closes each one:

  item 1 -- Observation Time / CLOSE Truth: local request-time proximity
            is NOT verification. A successful capture is
            OBSERVED_UNVERIFIED_TIME / CLOSE_UNVERIFIED unless genuine
            market-side evidence is present (never true against the real
            kiwoom.ka20009 contract today -- see
            _has_verification_evidence in the collector module).
  item 3 -- Persistent claim, Option A (strict at-most-once): a claim,
            once won, durably marks ATTEMPT_INCOMPLETE BEFORE the live
            API call. Nothing may ever automatically retry after that --
            not a dead pid, not staleness. Includes a REAL multiprocessing
            test (not just threads).
  item 4 -- Manifest structural validation: any manifest file that exists
            but is not well-formed (bad JSON, wrong top-level type, wrong
            day, malformed slot rows) is ManifestCorruptError -- never
            silently reset to empty.
  item 5 -- PARTIAL component-level validation: each index component is
            validated independently; completeness is "all required
            components individually valid", never `len(indices) == 2`.
"""
from __future__ import annotations

import json
import multiprocessing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from libs.market.q10_index_observation_collector import (
    ManifestCorruptError,
    _claim_path,
    _manifest_path,
    capture_slot,
    closeout_requery_if_missing,
    load_observations,
    observation_for_slot,
    run_due_slots,
)


KST = ZoneInfo("Asia/Seoul")
DAY = "2026-09-05"


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 9, 5, hour, minute, tzinfo=KST)


def _plain_packet(*, kospi: float = 3050.0, kosdaq: float = 810.0, current_date: str | None = None) -> dict:
    """A realistic kiwoom.ka20009 packet -- NO market-side timestamp or
    close-finalized evidence, matching the real reader's actual contract."""
    kospi_row: dict = {"current": kospi}
    kosdaq_row: dict = {"current": kosdaq}
    if current_date is not None:
        kospi_row["current_date"] = current_date
        kosdaq_row["current_date"] = current_date
    return {"status": "ok", "source": "kiwoom.ka20009", "indices": {"KOSPI": kospi_row, "KOSDAQ": kosdaq_row}}


def _verified_packet(*, kospi: float = 3050.0, kosdaq: float = 810.0, close_finalized: bool = False) -> dict:
    """A HYPOTHETICAL packet carrying genuine market-side evidence (a real
    observation timestamp, and -- for CLOSE -- a session-finalized flag).
    kiwoom.ka20009 never actually returns these fields; this fixture
    exists purely to prove the verification MECHANISM activates
    correctly the moment such evidence is present, per item 1's explicit
    A/B split ("실제 evidence가 존재한다면 그 evidence를 검증하여 사용")."""
    evidence = {"market_observed_at": "2026-09-05T15:30:03+09:00" if close_finalized else "2026-09-05T09:30:03+09:00"}
    if close_finalized:
        evidence["session_finalized"] = True
    return {
        "status": "ok", "source": "kiwoom.ka20009",
        "indices": {"KOSPI": {"current": kospi, **evidence}, "KOSDAQ": {"current": kosdaq, **evidence}},
    }


# ===========================================================================
# item 1 -- Observation Time / CLOSE Truth
# ===========================================================================


def test_item1_t1_current_quote_at_1005_cannot_become_verified_0930_without_evidence(tmp_path: Path) -> None:
    """Codex's exact reproduction: 10:05 first poll, 09:30 slot. Even
    though FIX 2's window check alone would have accepted a 5-minute-late
    fetch, NO amount of local-time proximity proves the price belongs to
    09:30 without market-side evidence -- so a plain (unverified) packet
    captured at 10:05 must be LATE_MISSED (outside window), and even a
    plain packet captured WITHIN the window must never become the fully
    "verified" AVAILABLE state."""
    root = tmp_path / "q10"
    late = capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(10, 5), capture=lambda **k: _plain_packet())
    assert late["availability"] == "LATE_MISSED"
    assert late["availability"] != "AVAILABLE"

    root2 = tmp_path / "q10_within_window"
    on_time = capture_slot(day=DAY, slot="09:30", root=root2, now_fn=lambda: _at(9, 31), capture=lambda **k: _plain_packet())
    assert on_time["availability"] == "OBSERVED_UNVERIFIED_TIME"
    assert on_time["availability"] != "AVAILABLE"
    assert on_time["verification_evidence_present"] is False


def test_item1_t2_previous_day_response_rejected(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    row = capture_slot(
        day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31),
        capture=lambda **k: _plain_packet(current_date="20260904"),
    )

    assert row["availability"] not in ("AVAILABLE", "OBSERVED_UNVERIFIED_TIME")
    assert row["indices"] == {}
    assert "KOSPI" in row["rejected_components"]
    assert row["rejected_components"]["KOSPI"]["reason"] == "component_date_mismatch"


def test_item1_t3_stale_1515_payload_cannot_become_close(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    row = capture_slot(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 15), capture=lambda **k: _plain_packet())

    assert row["availability"] != "AVAILABLE"
    assert row["availability"] != "CLOSE_UNVERIFIED"
    assert row["within_capture_window"] is False


def test_item1_t4_missing_source_timestamp_forbids_verified_close(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    row = capture_slot(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 30), capture=lambda **k: _plain_packet())

    assert row["source_market_timestamp_available"] is False
    assert row["availability"] == "CLOSE_UNVERIFIED"
    assert row["availability"] != "AVAILABLE"


def test_item1_t5_final_close_evidence_fixture_is_verified_close(tmp_path: Path) -> None:
    """Item 1's A-branch: when genuine evidence IS present (a fixture
    simulating a future reader capability), the mechanism verifies it --
    proving this is not just "always unverified" hardcoding."""
    root = tmp_path / "q10"
    row = capture_slot(
        day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 30),
        capture=lambda **k: _verified_packet(close_finalized=True),
    )

    assert row["verification_evidence_present"] is True
    assert row["availability"] == "AVAILABLE"


def test_item1_t5b_market_time_without_close_finalized_is_still_unverified_close(tmp_path: Path) -> None:
    """A real observation timestamp alone is NOT sufficient evidence that
    the CLOSE auction actually settled -- CLOSE specifically also
    requires an explicit finalized/session-closed signal."""
    root = tmp_path / "q10"
    row = capture_slot(
        day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 30),
        capture=lambda **k: _verified_packet(close_finalized=False),
    )

    assert row["availability"] == "CLOSE_UNVERIFIED"
    assert row["availability"] != "AVAILABLE"


def test_item1_t6_unverified_observation_is_stored_informationally(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=lambda **k: _plain_packet())

    stored = observation_for_slot(DAY, "09:30", root=root)
    assert stored["availability"] == "OBSERVED_UNVERIFIED_TIME"
    assert stored["indices"]["KOSPI"]["current"] == 3050.0  # still persisted, readable


def test_item1_t7_unverified_observation_is_not_calculation_usable(tmp_path: Path) -> None:
    """The collector-level contract itself: only AVAILABLE/PARTIAL are
    meant for calculation use (see reaction_reader.py's
    _COLLECTOR_VERIFIED_STATES, tested directly in
    test_q10_reaction_reader_collector_integration.py). Verified here at
    the collector level: the state name itself signals non-usability."""
    root = tmp_path / "q10"
    row = capture_slot(day=DAY, slot="10:00", root=root, now_fn=lambda: _at(10, 1), capture=lambda **k: _plain_packet())

    assert row["availability"] not in ("AVAILABLE", "PARTIAL")


# ===========================================================================
# item 3 -- Persistent claim, Option A (strict at-most-once)
# ===========================================================================


def test_item3_t1_sequential_duplicate_api_total_1(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    calls: list[int] = []

    def _capture(**kwargs):
        calls.append(1)
        return _plain_packet()

    capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=_capture)
    capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=_capture)

    assert len(calls) == 1


def test_item3_t2_process_a_claims_then_process_b_gets_zero_api(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    calls: list[int] = []

    def _capture(**kwargs):
        calls.append(1)
        return _plain_packet()

    from libs.market.q10_index_observation_collector import _acquire_slot_claim

    claimed = _acquire_slot_claim(DAY, "09:30", root=root)
    assert claimed is True

    # Process B: cannot acquire the claim (already held) -- must get zero
    # API calls even though no result has been persisted yet.
    result_b = capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=_capture)
    assert len(calls) == 0
    assert result_b["availability"] == "CORRUPT_STATE"


def test_item3_t3_crash_after_durable_attempted_before_api_no_implicit_replay(tmp_path: Path) -> None:
    """Simulates the exact "point of no return": the durable
    ATTEMPT_INCOMPLETE marker was persisted, but the process crashed
    before the live API was ever called. Per Option A, this is
    PERMANENT -- no automatic replay, regardless of how the claim state
    looks."""
    root = tmp_path / "q10"
    from libs.market.q10_index_observation_collector import _attempt_incomplete_row, _persist_row

    _persist_row(DAY, _attempt_incomplete_row("09:30", int(_at(9, 30).timestamp()), int(_at(9, 30).timestamp())), root=root)

    calls: list[int] = []

    def _capture(**kwargs):
        calls.append(1)
        return _plain_packet()

    result = capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=_capture)

    assert len(calls) == 0
    assert result["availability"] == "ATTEMPT_INCOMPLETE"


def test_item3_t4_crash_after_api_before_result_no_replay(tmp_path: Path) -> None:
    """Indistinguishable on disk from T3 (ATTEMPT_INCOMPLETE persisted,
    no final result) -- same guarantee: never automatically replayed."""
    root = tmp_path / "q10"
    from libs.market.q10_index_observation_collector import _attempt_incomplete_row, _persist_row

    _persist_row(DAY, _attempt_incomplete_row("15:30", int(_at(15, 30).timestamp()), int(_at(15, 30).timestamp())), root=root)

    calls: list[int] = []

    def _capture(**kwargs):
        calls.append(1)
        return _plain_packet()

    # Even via run_due_slots (the real poll-cycle entry point), restricted
    # to the CLOSE slot alone so the other (unrelated, genuinely
    # never-attempted) slots don't add unrelated call counts.
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(15, 36), capture=_capture, slots=("15:30",))

    assert len(calls) == 0
    assert observation_for_slot(DAY, "15:30", root=root)["availability"] == "ATTEMPT_INCOMPLETE"


def test_item3_t5_restart_does_not_replay_an_attempted_slot(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    calls: list[int] = []

    def _capture(**kwargs):
        calls.append(1)
        return _plain_packet()

    capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=_capture)
    # Simulated restart: a fresh run_due_slots call, as if the process had
    # just started again.
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(9, 32), capture=_capture)

    assert len(calls) == 1


def test_item3_t6_live_owner_older_than_120_sec_is_never_stolen(tmp_path: Path) -> None:
    """Option A explicitly rejects staleness-based reclaim (unlike FIX
    2's design, which this replaces): a claim, once created, is NEVER
    reclaimed by age alone, regardless of how old it is."""
    root = tmp_path / "q10"
    claim_path = _claim_path(DAY, "09:30", root=root)
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    ancient_epoch = int(_at(9, 30).timestamp()) - 10_000  # far older than any staleness window
    claim_path.write_text(json.dumps({"pid": 424242, "claimed_at_epoch": ancient_epoch}), encoding="utf-8")

    calls: list[int] = []

    def _capture(**kwargs):
        calls.append(1)
        return _plain_packet()

    result = capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=_capture)

    assert len(calls) == 0
    assert claim_path.exists()  # never stolen/removed


def test_item3_t7_corrupt_claim_fail_honest(tmp_path: Path) -> None:
    """A corrupt claim FILE (not JSON) still safely blocks capture -- the
    claim's mere existence (successful exclusive-create having already
    happened) is what matters; content is never parsed for logic."""
    root = tmp_path / "q10"
    claim_path = _claim_path(DAY, "09:30", root=root)
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    claim_path.write_text("{not valid json::", encoding="utf-8")

    calls: list[int] = []

    def _capture(**kwargs):
        calls.append(1)
        return _plain_packet()

    result = capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=_capture)

    assert len(calls) == 0


def test_item3_t8_corrupt_manifest_fail_honest(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    manifest_path = _manifest_path(DAY, root=root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{not valid json::", encoding="utf-8")

    try:
        load_observations(DAY, root=root)
        raised = False
    except ManifestCorruptError:
        raised = True
    assert raised is True

    calls: list[int] = []
    result = capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=lambda **k: calls.append(1) or _plain_packet())
    assert len(calls) == 0
    assert result["availability"] == "CORRUPT_STATE"


def test_item3_t9_different_days_independent(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    calls: list[int] = []

    def _capture(**kwargs):
        calls.append(1)
        return _plain_packet()

    capture_slot(day="2026-09-04", slot="09:30", root=root, now_fn=lambda: datetime(2026, 9, 4, 9, 31, tzinfo=KST), capture=_capture)
    capture_slot(day="2026-09-05", slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=_capture)

    assert len(calls) == 2


def test_item3_t10_different_slots_independent(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    calls: list[int] = []

    def _capture(**kwargs):
        calls.append(1)
        return _plain_packet()

    capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=_capture)
    capture_slot(day=DAY, slot="10:00", root=root, now_fn=lambda: _at(10, 1), capture=_capture)

    assert len(calls) == 2


# --- item 3, real OS multiprocessing (not threads) ------------------------


def _mp_capture_worker(barrier, root_str: str, day: str, slot: str, tick_dir: str) -> None:
    """Module-level (picklable) worker for a real, separate OS process --
    Windows multiprocessing uses spawn, which re-imports this module, so
    this function must be importable at module scope, not a closure."""
    import os
    import uuid
    from datetime import datetime as _dt
    from pathlib import Path as _Path
    from zoneinfo import ZoneInfo as _ZoneInfo

    from libs.market.q10_index_observation_collector import capture_slot as _capture_slot

    _kst = _ZoneInfo("Asia/Seoul")

    def _capture(**kwargs):
        _Path(tick_dir, f"{os.getpid()}_{uuid.uuid4().hex}.tick").write_text("1", encoding="utf-8")
        return {
            "status": "ok", "source": "kiwoom.ka20009",
            "indices": {"KOSPI": {"current": 1.0}, "KOSDAQ": {"current": 2.0}},
        }

    barrier.wait()
    _capture_slot(day=day, slot=slot, root=root_str, now_fn=lambda: _dt(2026, 9, 5, 9, 31, tzinfo=_kst), capture=_capture)


def test_item3_t1_t4_two_real_os_processes_same_slot_api_total_le_1(tmp_path: Path) -> None:
    """T1/T4: real, separate OS processes (multiprocessing.Process, not
    threads) racing to capture the SAME (day, slot). A physical side-
    effect file is written by each live "API call" so the count survives
    across process boundaries. Total live calls across BOTH processes
    must never exceed 1."""
    root = tmp_path / "q10"
    tick_dir = tmp_path / "ticks"
    tick_dir.mkdir()
    barrier = multiprocessing.Barrier(2)
    processes = [
        multiprocessing.Process(target=_mp_capture_worker, args=(barrier, str(root), DAY, "09:30", str(tick_dir)))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=60)
    for process in processes:
        assert process.exitcode == 0

    tick_count = len(list(tick_dir.glob("*.tick")))
    assert tick_count <= 1
    assert observation_for_slot(DAY, "09:30", root=root)["availability"] != "MISSING"


# ===========================================================================
# item 4 -- Manifest structural validation
# ===========================================================================


def test_item4_invalid_json_syntax_is_corrupt(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    manifest_path = _manifest_path(DAY, root=root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{broken", encoding="utf-8")

    try:
        load_observations(DAY, root=root)
        raised = False
    except ManifestCorruptError:
        raised = True
    assert raised is True


def test_item4_top_level_array_is_corrupt_not_empty_state(tmp_path: Path) -> None:
    """Codex's exact reproduction: `[]` at the top level must NOT be
    silently treated as an empty/fresh manifest."""
    root = tmp_path / "q10"
    manifest_path = _manifest_path(DAY, root=root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("[]", encoding="utf-8")

    try:
        load_observations(DAY, root=root)
        raised = False
    except ManifestCorruptError:
        raised = True
    assert raised is True

    calls: list[int] = []
    result = capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=lambda **k: calls.append(1) or _plain_packet())
    assert len(calls) == 0  # never blindly re-queried
    assert result["availability"] == "CORRUPT_STATE"


def test_item4_wrong_day_recorded_inside_manifest_is_corrupt_not_empty_state(tmp_path: Path) -> None:
    """Codex's exact reproduction: a manifest file present under today's
    path, but recording a DIFFERENT day inside it, must not be treated as
    "empty for today" (which would silently trigger a fresh API
    re-query)."""
    root = tmp_path / "q10"
    manifest_path = _manifest_path(DAY, root=root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"day": "2026-01-01", "slots": []}), encoding="utf-8")

    try:
        load_observations(DAY, root=root)
        raised = False
    except ManifestCorruptError:
        raised = True
    assert raised is True

    calls: list[int] = []
    result = capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=lambda **k: calls.append(1) or _plain_packet())
    assert len(calls) == 0
    assert result["availability"] == "CORRUPT_STATE"


def test_item4_malformed_slot_row_is_corrupt(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    manifest_path = _manifest_path(DAY, root=root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"day": DAY, "slots": ["not_a_dict"]}), encoding="utf-8")

    try:
        load_observations(DAY, root=root)
        raised = False
    except ManifestCorruptError:
        raised = True
    assert raised is True


def test_item4_absent_file_is_the_only_case_allowed_fresh(tmp_path: Path) -> None:
    root = tmp_path / "q10"  # no file created at all

    rows = load_observations(DAY, root=root)  # must not raise

    assert rows == []
    result = observation_for_slot(DAY, "09:30", root=root)
    assert result["availability"] == "MISSING"


# ===========================================================================
# item 5 -- PARTIAL component-level validation
# ===========================================================================


def test_item5_t1_valid_kospi_plus_previous_day_kosdaq_is_partial(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    packet = {
        "status": "ok", "source": "kiwoom.ka20009",
        "indices": {
            "KOSPI": {"current": 3050.0, "current_date": DAY.replace("-", "")},
            "KOSDAQ": {"current": 810.0, "current_date": "20260904"},  # previous day
        },
    }
    row = capture_slot(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 30), capture=lambda **k: packet)

    assert row["availability"] in ("PARTIAL", "PARTIAL_UNVERIFIED")
    assert "KOSPI" in row["indices"]
    assert "KOSDAQ" not in row["indices"]
    assert row["rejected_components"]["KOSDAQ"]["reason"] == "component_date_mismatch"


def test_item5_t2_valid_kospi_plus_outside_window_kosdaq_recovery_stays_partial(tmp_path: Path) -> None:
    """The PRIMARY attempt only has KOSPI (PARTIAL). A closeout recovery
    fetch that is itself outside ITS OWN capture window must not promote
    KOSDAQ into the merged result."""
    root = tmp_path / "q10"
    capture_slot(
        day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 30),
        capture=lambda **k: {"status": "partial", "source": "kiwoom.ka20009", "indices": {"KOSPI": {"current": 3050.0}}},
    )

    row = closeout_requery_if_missing(
        day=DAY, slot="15:30", root=root,
        now_fn=lambda: datetime(2026, 9, 5, 16, 0, tzinfo=KST),  # way outside the closeout window too
        capture=lambda **k: {"status": "ok", "source": "kiwoom.ka20009", "indices": {"KOSDAQ": {"current": 810.0}}},
        window_sec=15 * 60,
    )

    assert row["availability"] in ("PARTIAL", "PARTIAL_UNVERIFIED")
    assert "KOSDAQ" not in row["indices"]


def test_item5_t3_valid_kospi_plus_valid_kosdaq_is_complete(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    row = capture_slot(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 30), capture=lambda **k: _plain_packet())

    assert row["availability"] in ("AVAILABLE", "CLOSE_UNVERIFIED")
    assert "KOSPI" in row["indices"]
    assert "KOSDAQ" in row["indices"]


def test_item5_t4_invalid_recovery_does_not_overwrite_existing_component(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    capture_slot(
        day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 30),
        capture=lambda **k: {"status": "partial", "source": "kiwoom.ka20009", "indices": {"KOSPI": {"current": 3050.0}}},
    )

    row = closeout_requery_if_missing(
        day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 36),
        capture=lambda **k: {
            "status": "ok", "source": "kiwoom.ka20009",
            "indices": {"KOSPI": {"current": 9999.0}, "KOSDAQ": {"current": 810.0}},
        },
    )

    assert row["indices"]["KOSPI"]["current"] == 3050.0


def test_item5_t5_repeated_closeout_no_extra_logical_retry(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    calls: list[int] = []

    def _partial(**kwargs):
        calls.append(1)
        return {"status": "partial", "source": "kiwoom.ka20009", "indices": {"KOSPI": {"current": 3050.0}}}

    capture_slot(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 30), capture=_partial)
    closeout_requery_if_missing(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 36), capture=_partial)
    assert len(calls) == 2

    for minute in (40, 45, 50):
        closeout_requery_if_missing(day=DAY, slot="15:30", root=root, now_fn=lambda m=minute: _at(15, m), capture=_partial)
    assert len(calls) == 2


def test_item5_t6_component_validation_provenance_preserved(tmp_path: Path) -> None:
    root = tmp_path / "q10"
    packet = {
        "status": "ok", "source": "kiwoom.ka20009",
        "indices": {
            "KOSPI": {"current": 3050.0, "current_date": DAY.replace("-", "")},
            "KOSDAQ": {"current": 810.0, "current_date": "19990101"},
        },
    }
    row = capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 31), capture=lambda **k: packet)

    assert row["rejected_components"]["KOSDAQ"] == {"reason": "component_date_mismatch", "current_date": "19990101"}
    assert "KOSDAQ" not in row["indices"]
