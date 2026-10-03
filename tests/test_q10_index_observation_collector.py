"""2026-09-05 PRE-STEP5C cleanup (Codex audit item 3): Q10 Index EOD
observation acquisition path.

Root cause: KOSPI/KOSDAQ intraday snapshots have only ever arrived as a
byproduct of Strategist's global_sentiment_breakdown cycle -- irregular,
and (per the 2026-09-04 finding) capable of stopping well before the
15:30 KST close. There was no dedicated, independently-schedulable
capture path for 09:30 / 10:00 / CLOSE observations. This module adds
one, reusing the exact idempotent-per-slot + manifest pattern already
proven by libs/market/opening_macro_snapshot_collector.py and the same
live Korea-index data source (KiwoomMarketIndexReader / kiwoom.ka20009)
already used elsewhere -- no new external infrastructure. A missing/
failed capture is always honestly MISSING, never a fabricated CLOSE
substitute -- this test file does not touch, and does not need to touch,
reaction_reader.py's own CLOSE-provenance principle (tests for that
principle live in tests/test_q10_index_close_fallback.py, unmodified).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from libs.market.q10_index_observation_collector import (
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


def _ok_capture(*, indices=("KOSPI", "KOSDAQ"), reader_factory=None):
    return {
        "status": "ok",
        "source": "kiwoom.ka20009",
        "indices": {
            "KOSPI": {"current": 3050.12, "previous_close": 3020.5, "ts": 1},
            "KOSDAQ": {"current": 810.4, "previous_close": 805.1, "ts": 1},
        },
    }


def _partial_capture(*, indices=("KOSPI", "KOSDAQ"), reader_factory=None):
    return {
        "status": "partial",
        "source": "kiwoom.ka20009",
        "indices": {"KOSPI": {"current": 3050.12, "previous_close": 3020.5, "ts": 1}},
        "errors": {"KOSDAQ": "kiwoom_market_index_error:return_code=5"},
    }


def _failed_capture(*, indices=("KOSPI", "KOSDAQ"), reader_factory=None):
    return {"status": "unavailable", "source": "kiwoom.ka20009", "indices": {}, "error": "RuntimeError: token unavailable"}


# --- T1/T2: 09:30 and 10:00 valid capture ---------------------------------


def test_0930_slot_valid_capture(tmp_path: Path) -> None:
    root = tmp_path / "q10_index_observations"
    row = capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 30), capture=_ok_capture)

    assert row["availability"] == "OBSERVED_UNVERIFIED_TIME"
    assert row["requested_slot"] == "09:30"
    assert row["indices"]["KOSPI"]["current"] == 3050.12
    assert row["source"] == "kiwoom.ka20009"
    assert row["actual_lag_sec"] == 0


def test_1000_slot_valid_capture(tmp_path: Path) -> None:
    root = tmp_path / "q10_index_observations"
    row = capture_slot(day=DAY, slot="10:00", root=root, now_fn=lambda: _at(10, 1), capture=_ok_capture)

    assert row["availability"] == "OBSERVED_UNVERIFIED_TIME"
    assert row["requested_slot"] == "10:00"
    assert row["actual_lag_sec"] == 60


# --- T3: close-window valid capture ---------------------------------------


def test_close_window_valid_capture(tmp_path: Path) -> None:
    root = tmp_path / "q10_index_observations"
    row = capture_slot(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 30), capture=_ok_capture)

    assert row["availability"] == "CLOSE_UNVERIFIED"
    assert row["requested_slot"] == "15:30"
    assert row["indices"]["KOSDAQ"]["current"] == 810.4


# --- T4: close capture failure -> PENDING/MISSING, never fabricated ------


def test_close_capture_failure_is_missing_not_fabricated(tmp_path: Path) -> None:
    root = tmp_path / "q10_index_observations"
    row = capture_slot(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 30), capture=_failed_capture)

    assert row["availability"] == "MISSING"
    assert row["indices"] == {}
    assert row["error"]


def test_partial_capture_is_labeled_partial_not_available(tmp_path: Path) -> None:
    root = tmp_path / "q10_index_observations"
    row = capture_slot(day=DAY, slot="10:00", root=root, now_fn=lambda: _at(10, 0), capture=_partial_capture)

    assert row["availability"] == "PARTIAL_UNVERIFIED"
    assert "KOSPI" in row["indices"]
    assert "KOSDAQ" not in row["indices"]


# --- T5: a slot never substitutes another slot's (e.g. stale 15:15) data -


def test_slots_are_independent_no_cross_slot_substitution(tmp_path: Path) -> None:
    root = tmp_path / "q10_index_observations"
    capture_slot(day=DAY, slot="10:00", root=root, now_fn=lambda: _at(10, 0), capture=_ok_capture)

    close_row = observation_for_slot(DAY, "15:30", root=root)

    # 10:00 having real data must never leak into an unattempted CLOSE slot.
    assert close_row["availability"] == "MISSING"
    assert close_row["indices"] == {}


# --- T7/T8: closeout re-query -----------------------------------------


def test_closeout_requery_succeeds_when_close_slot_was_missing(tmp_path: Path) -> None:
    root = tmp_path / "q10_index_observations"
    capture_slot(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 30), capture=_failed_capture)

    row = closeout_requery_if_missing(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 40), capture=_ok_capture)

    assert row["availability"] == "CLOSE_UNVERIFIED"
    assert row["closeout_requeried"] is True
    stored = observation_for_slot(DAY, "15:30", root=root)
    assert stored["availability"] == "CLOSE_UNVERIFIED"


def test_closeout_requery_failure_stays_honestly_missing_and_bounded(tmp_path: Path) -> None:
    root = tmp_path / "q10_index_observations"
    capture_slot(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 30), capture=_failed_capture)

    first = closeout_requery_if_missing(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 40), capture=_failed_capture)
    assert first["availability"] == "MISSING"
    assert first["closeout_requeried"] is True

    calls = {"n": 0}

    def _counting_capture(**kwargs):
        calls["n"] += 1
        return _ok_capture(**kwargs)

    # A second call (e.g. next poll cycle) must NOT issue another live
    # fetch -- the one bounded re-query attempt has already been used.
    second = closeout_requery_if_missing(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 41), capture=_counting_capture)
    assert second["availability"] == "MISSING"
    assert calls["n"] == 0


def test_closeout_requery_is_a_noop_when_close_slot_already_available(tmp_path: Path) -> None:
    root = tmp_path / "q10_index_observations"
    capture_slot(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 30), capture=_ok_capture)

    calls = {"n": 0}

    def _counting_capture(**kwargs):
        calls["n"] += 1
        return _ok_capture(**kwargs)

    row = closeout_requery_if_missing(day=DAY, slot="15:30", root=root, now_fn=lambda: _at(15, 40), capture=_counting_capture)

    assert row["availability"] == "CLOSE_UNVERIFIED"
    assert calls["n"] == 0


# --- run_due_slots: end-to-end poll-cycle behaviour ------------------------


def test_run_due_slots_only_captures_slots_whose_time_has_arrived(tmp_path: Path) -> None:
    root = tmp_path / "q10_index_observations"
    captured = run_due_slots(day=DAY, root=root, now_fn=lambda: _at(9, 31), capture=_ok_capture)

    assert len(captured) == 1
    assert captured[0]["requested_slot"] == "09:30"
    assert observation_for_slot(DAY, "10:00", root=root)["availability"] == "MISSING"


def test_run_due_slots_never_retries_a_failed_non_close_slot_on_later_polls(tmp_path: Path) -> None:
    """2026-09-05: every slot gets exactly ONE primary attempt. If a
    non-CLOSE slot's (e.g. 09:30) live fetch fails, later poll ticks must
    not keep re-fetching it forever -- only CLOSE gets one bounded extra
    try, via closeout_requery_if_missing. Uses the full default slot list
    so CLOSE's legitimate one extra attempt doesn't get mistaken for a
    09:30 retry."""
    root = tmp_path / "q10_index_observations"
    calls = {"n": 0}

    def _failing_capture(**kwargs):
        calls["n"] += 1
        return {"status": "unavailable", "source": "kiwoom.ka20009", "indices": {}, "error": "boom"}

    # First real poll: 09:30, 10:00, and CLOSE all become due and each get
    # exactly one primary attempt (3 calls total).
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(15, 30), capture=_failing_capture)
    assert calls["n"] == 3
    # 09:30/10:00 are both hours outside their own capture window by 15:30
    # -- LATE_MISSED (timing rejection) takes precedence over MISSING
    # (empty payload); either way, empty AND late, and the point stands:
    # never retried.
    assert observation_for_slot(DAY, "09:30", root=root)["availability"] == "LATE_MISSED"
    assert observation_for_slot(DAY, "10:00", root=root)["availability"] == "LATE_MISSED"

    # Many further poll ticks, well past the closeout grace period: CLOSE
    # gets exactly one more (bounded) attempt; 09:30/10:00 get none.
    for minute in (36, 40, 50):
        run_due_slots(day=DAY, root=root, now_fn=lambda m=minute: _at(15, m), capture=_failing_capture)
    assert calls["n"] == 4
    assert observation_for_slot(DAY, "09:30", root=root)["availability"] == "LATE_MISSED"
    assert observation_for_slot(DAY, "10:00", root=root)["availability"] == "LATE_MISSED"
    close_row = observation_for_slot(DAY, "15:30", root=root)
    assert close_row["availability"] == "MISSING"
    assert close_row["closeout_requeried"] is True


def test_run_due_slots_triggers_closeout_requery_after_grace_period(tmp_path: Path) -> None:
    root = tmp_path / "q10_index_observations"
    # First poll cycle at close time: the live fetch fails.
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(15, 30), capture=_failed_capture)
    assert observation_for_slot(DAY, "15:30", root=root)["availability"] == "MISSING"

    # A later poll cycle, past the grace period, succeeds via the bounded
    # closeout re-query.
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(15, 40), capture=_ok_capture, closeout_grace_sec=300)

    assert observation_for_slot(DAY, "15:30", root=root)["availability"] == "CLOSE_UNVERIFIED"


# --- T9: reaction/scoring semantics unchanged ------------------------------


def test_module_does_not_import_or_touch_reaction_reader() -> None:
    """This collector is a standalone, additive observation store. It must
    not import reaction_reader.py's Q10 scoring/forward-window machinery
    -- proving this fix cannot have altered Q10 strategy semantics. (Doc
    comments referencing reaction_reader.py by name are fine; only real
    `import` statements would be a problem.)"""
    import libs.market.q10_index_observation_collector as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    import_lines = [line for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
    assert not any("reaction_reader" in line or "forward_validation" in line for line in import_lines)


def test_load_observations_returns_all_captured_slots(tmp_path: Path) -> None:
    root = tmp_path / "q10_index_observations"
    capture_slot(day=DAY, slot="09:30", root=root, now_fn=lambda: _at(9, 30), capture=_ok_capture)
    capture_slot(day=DAY, slot="10:00", root=root, now_fn=lambda: _at(10, 0), capture=_ok_capture)

    rows = load_observations(DAY, root=root)

    assert {row["requested_slot"] for row in rows} == {"09:30", "10:00"}
