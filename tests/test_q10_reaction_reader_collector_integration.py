"""2026-09-05 PRE-STEP5C CLEANUP FIX 3, item 2/6 (second independent
Codex re-audit, REJECTed FIX 2's version of this integration).

Codex's exact reproduction: OPEN=100, collector CLOSE=110 (displayed),
legacy last price=90 -- FIX 2's collector_override only patched the
DISPLAYED checkpoint (`points["CLOSE"]`); `forward_windows`'s
`return_to_close_pct` was still computed from the legacy `regular` candle
series alone, so it silently used 90 instead of 110 -- displayed CLOSE=110
but return_to_close_pct=-10% (a genuine 10% GAIN mislabeled as a loss).

Fix: `_forward_window()` now takes `authoritative_close` (the SAME
`points["CLOSE"]` dict every display consumer reads) and uses it for
`return_to_close_pct`/`mfe_pct`/`mae_pct` whenever CLOSE is OBSERVED --
one authoritative observation set feeds both display and calculation, for
every entry checkpoint, not just the checkpoint currently being resolved.

Item 6, folded in here: `_collector_raw_row` returns a tri-state signal
(None=ABSENT -> legacy fallback allowed; a dict with `integrity_failure`
=INVALID -> legacy fallback FORBIDDEN, forced PENDING with the reason
attached; a plain raw-row dict=VERIFIED -> used directly). LATE_MISSED/
CORRUPT_STATE/an unverified-but-captured observation are all INVALID, not
ABSENT -- silently falling back to legacy for those would hide a proven
integrity problem.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from libs.market.q10_index_observation_collector import capture_slot
from libs.reporting.baseline_samsung_hynix.forward_validation.reaction_reader import (
    _index_reaction,
    _stock_reaction,
)


KST = ZoneInfo("Asia/Seoul")
DAY = "2026-09-05"
KOSPI_TARGET = {"key": "kospi", "symbol": "KOSPI", "ticker": "^KS11", "name": "KOSPI", "kind": "index"}


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 9, 5, hour, minute, tzinfo=KST)


def _legacy_row(ts: int, close: float) -> dict:
    return {"ts": ts, "open": close, "high": close, "low": close, "close": close, "volume": 100.0, "previous_close": 3000.0}


def _verified_close_packet(price: float) -> dict:
    """A hypothetical VERIFIED capture (real evidence fields -- see
    q10_index_observation_collector.py's _has_verification_evidence).
    Real kiwoom.ka20009 responses never actually carry these; this
    fixture exists to test the authority-consistency MECHANISM."""
    evidence = {"market_observed_at": "2026-09-05T15:30:03+09:00", "session_finalized": True}
    return {
        "status": "ok", "source": "kiwoom.ka20009",
        "indices": {"KOSPI": {"current": price, **evidence}, "KOSDAQ": {"current": 800.0, **evidence}},
    }


def _unverified_close_packet(price: float) -> dict:
    """A realistic (unverified) successful capture -- no evidence fields,
    matching the real reader's actual contract."""
    return {"status": "ok", "source": "kiwoom.ka20009", "indices": {"KOSPI": {"current": price}, "KOSDAQ": {"current": 800.0}}}


# --- item 2 T1/T2: display and calculation always use the same authority --


def test_t1_collector_0930_verified_wins_over_conflicting_legacy(tmp_path: Path) -> None:
    collector_root = tmp_path / "q10_index_observations"
    capture_slot(
        day=DAY, slot="09:30", root=collector_root, now_fn=lambda: _at(9, 31),
        capture=lambda **k: {
            "status": "ok", "source": "kiwoom.ka20009",
            "indices": {
                "KOSPI": {"current": 3111.0, "market_observed_at": "2026-09-05T09:30:03+09:00"},
                "KOSDAQ": {"current": 800.0, "market_observed_at": "2026-09-05T09:30:03+09:00"},
            },
        },
    )
    legacy_rows = [_legacy_row(int(_at(9, 30).timestamp()), 2999.0)]  # deliberately different value

    result = _index_reaction(day=DAY, target=KOSPI_TARGET, rows=legacy_rows, collector_root=collector_root)

    assert result["points"]["09:30"]["status"] == "OBSERVED"
    assert result["points"]["09:30"]["price"] == 3111.0
    assert result["points"]["09:30"]["source"] == "q10_index_observation_collector"


def test_t2_collector_close_110_return_to_close_also_uses_110(tmp_path: Path) -> None:
    """Codex's exact fixture: OPEN=100, collector CLOSE=110, legacy last
    price=90. Displayed CLOSE and return_to_close_pct must use the SAME
    110 -- never a silent 90 underneath."""
    collector_root = tmp_path / "q10_index_observations"
    capture_slot(day=DAY, slot="15:30", root=collector_root, now_fn=lambda: _at(15, 30), capture=lambda **k: _verified_close_packet(110.0))
    legacy_rows = [
        _legacy_row(int(_at(9, 0).timestamp()), 100.0),   # OPEN = 100
        _legacy_row(int(_at(15, 20).timestamp()), 90.0),  # legacy's own "last price" = 90
    ]

    result = _index_reaction(day=DAY, target=KOSPI_TARGET, rows=legacy_rows, collector_root=collector_root)

    assert result["points"]["CLOSE"]["price"] == 110.0
    # The 09:00 entry's return_to_close_pct must be computed against the
    # SAME 110 the CLOSE checkpoint displays -- a +10% gain, never the
    # legacy-only -10% FIX 2 would have silently produced.
    forward = result["forward_windows"]["09:00"]
    assert forward["status"] == "OBSERVED"
    assert forward["return_to_close_pct"] == 10.0
    assert forward["return_to_close_pct"] != -10.0


# --- item 2 T3: CLOSE missing + valid semantic legacy close -> fallback --


def test_t3_collector_missing_close_falls_back_to_valid_legacy_close(tmp_path: Path) -> None:
    collector_root = tmp_path / "q10_index_observations"  # nothing captured -- genuinely ABSENT
    legacy_rows = [_legacy_row(int(_at(15, 29).timestamp()), 3450.0)]  # inside the strict close window

    result = _index_reaction(day=DAY, target=KOSPI_TARGET, rows=legacy_rows, collector_root=collector_root)

    assert result["points"]["CLOSE"]["status"] == "OBSERVED"
    assert result["points"]["CLOSE"]["price"] == 3450.0


# --- item 2 T4/T5: INVALID (not ABSENT) forbids silent legacy fallback ---


def test_t4_late_missed_plus_legacy_preserves_integrity_failure_no_silent_fallback(tmp_path: Path) -> None:
    collector_root = tmp_path / "q10_index_observations"
    capture_slot(day=DAY, slot="15:30", root=collector_root, now_fn=lambda: _at(15, 15), capture=lambda **k: _unverified_close_packet(3400.0))
    assert (
        capture_slot(day=DAY, slot="15:30", root=collector_root, now_fn=lambda: _at(15, 15), capture=lambda **k: _unverified_close_packet(3400.0))
        ["availability"] == "LATE_MISSED"
    )
    legacy_rows = [_legacy_row(int(_at(15, 29).timestamp()), 3450.0)]  # valid legacy close exists too

    result = _index_reaction(day=DAY, target=KOSPI_TARGET, rows=legacy_rows, collector_root=collector_root)

    assert result["points"]["CLOSE"]["status"] == "PENDING"
    assert result["points"]["CLOSE"]["price"] is None
    assert result["points"]["CLOSE"]["price"] != 3450.0  # never a silent legacy substitute
    assert result["points"]["CLOSE"]["integrity_failure"] is True
    assert result["points"]["CLOSE"]["collector_status"] == "LATE_MISSED"


def test_t5_corrupt_state_plus_legacy_preserves_integrity_failure_no_silent_fallback(tmp_path: Path) -> None:
    collector_root = tmp_path / "q10_index_observations"
    manifest_path = collector_root / DAY / "capture_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{not valid json::", encoding="utf-8")
    legacy_rows = [_legacy_row(int(_at(15, 29).timestamp()), 3450.0)]

    result = _index_reaction(day=DAY, target=KOSPI_TARGET, rows=legacy_rows, collector_root=collector_root)

    assert result["points"]["CLOSE"]["status"] == "PENDING"
    assert result["points"]["CLOSE"]["price"] != 3450.0
    assert result["points"]["CLOSE"]["integrity_failure"] is True
    assert result["points"]["CLOSE"]["collector_status"] == "CORRUPT_STATE"


def test_t6_collector_close_unverified_plus_stale_legacy_stays_pending(tmp_path: Path) -> None:
    """An unverified-but-captured collector CLOSE (not evidence-backed)
    plus a legacy value that is ITSELF outside the strict close window
    (stale 15:25 is fine actually -- use a genuinely stale 15:10 legacy
    row, outside [-10min,+1min] of 15:30) -> CLOSE stays PENDING, no
    value promoted from either source."""
    collector_root = tmp_path / "q10_index_observations"
    capture_slot(day=DAY, slot="15:30", root=collector_root, now_fn=lambda: _at(15, 30), capture=lambda **k: _unverified_close_packet(3400.0))
    stale_legacy_rows = [_legacy_row(int(_at(15, 10).timestamp()), 3450.0)]  # well outside the close window

    result = _index_reaction(day=DAY, target=KOSPI_TARGET, rows=stale_legacy_rows, collector_root=collector_root)

    assert result["points"]["CLOSE"]["status"] == "PENDING"
    assert result["points"]["CLOSE"]["price"] is None
    assert result["points"]["CLOSE"]["integrity_failure"] is True


# --- item 2 T7: displayed checkpoint and calculated return always same authority --


def test_t7_displayed_checkpoint_and_calculated_return_always_same_authority(tmp_path: Path) -> None:
    collector_root = tmp_path / "q10_index_observations"
    capture_slot(day=DAY, slot="15:30", root=collector_root, now_fn=lambda: _at(15, 30), capture=lambda **k: _verified_close_packet(200.0))
    legacy_rows = [
        _legacy_row(int(_at(9, 0).timestamp()), 100.0),
        _legacy_row(int(_at(10, 0).timestamp()), 150.0),  # a different, wrong "close-ish" legacy value
    ]

    result = _index_reaction(day=DAY, target=KOSPI_TARGET, rows=legacy_rows, collector_root=collector_root)

    displayed_close = result["points"]["CLOSE"]["price"]
    assert displayed_close == 200.0
    for label in ("09:00",):
        window = result["forward_windows"][label]
        entry_price = result["points"][label]["price"]
        expected_return = round((displayed_close / entry_price - 1.0) * 100.0, 6)
        assert window["return_to_close_pct"] == expected_return


# --- historical-artifact compatibility (no collector data at all) --------


def test_no_collector_data_at_all_behaves_exactly_as_legacy_only(tmp_path: Path) -> None:
    collector_root = tmp_path / "q10_index_observations"  # empty
    legacy_rows = [_legacy_row(int(_at(9, 30).timestamp()), 3050.0), _legacy_row(int(_at(15, 29).timestamp()), 3070.0)]

    with_override = _index_reaction(day=DAY, target=KOSPI_TARGET, rows=legacy_rows, collector_root=collector_root)
    without_override = _stock_reaction(
        day=DAY, target=KOSPI_TARGET, rows=legacy_rows, previous_close=3000.0, last_available_lookback_sec=30 * 60,
    )

    assert with_override["points"]["09:30"] == without_override["points"]["09:30"]
    assert with_override["points"]["CLOSE"] == without_override["points"]["CLOSE"]


def test_stock_targets_never_receive_collector_override(tmp_path: Path) -> None:
    collector_root = tmp_path / "q10_index_observations"
    capture_slot(day=DAY, slot="09:30", root=collector_root, now_fn=lambda: _at(9, 31), capture=lambda **k: _unverified_close_packet(9999.0))

    legacy_rows = [_legacy_row(int(_at(9, 30).timestamp()), 71000.0)]
    result = _stock_reaction(day=DAY, target={"symbol": "005930", "kind": "stock"}, rows=legacy_rows, previous_close=70000.0)

    assert result["points"]["09:30"]["price"] == 71000.0
