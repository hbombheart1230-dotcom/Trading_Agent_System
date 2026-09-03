"""2026-09-03 daily audit (P2-A, revised) -- KOSPI/KOSDAQ EOD close missing.

Root cause: KOSPI/KOSDAQ macro-indicator snapshots are a byproduct of the
Strategist node's own global_sentiment_breakdown cycle
(compute_global_sentiment_signal), not a dedicated, independently
schedulable capture job. Confirmed today: last snapshot 15:15:32 KST,
outside `_close_point`'s strict [-10min, +1min] window around 15:30 KST
close. Investigated and confirmed there is no existing safe path to force
a snapshot specifically at close (libs/market/opening_macro_snapshot_collector.py's
scheduled slots are hard-capped to the 08:50-09:20 preopen window by
design, unrelated to this gap).

Original fix (superseded): a bounded fallback that filled a non-real
close-window value directly into points["CLOSE"] -- rejected on review as
a real-vs-not-real data provenance risk for Q10 forward-validation
research data.

Revised fix: `_close_point` is back to its original, unmodified strict
behavior (no parameters, no fallback) -- CLOSE stays PENDING when no real
close-window row exists, for both stocks and indices, exactly as before
any P2-A change. A NEW, separate, purely informational field
`last_available_point_before_close` (opt-in via `last_available_lookback_sec`,
default 0/disabled) surfaces the last actually-observed point and its lag
when CLOSE is PENDING -- it is never written into points["CLOSE"], never
used in return/forward-window math, and is clearly labeled as
"last available," not "close." Only `_index_reaction` opts in; stocks are
completely unaffected. No Q10 scoring, threshold, or reaction-
classification logic is touched.
"""
from __future__ import annotations

from libs.reporting.baseline_samsung_hynix.forward_validation.reaction_reader import (
    _checkpoint_epoch,
    _close_point,
    _index_reaction,
    _last_available_point_before_close,
    _stock_reaction,
)


def _row(ts: int, close: float) -> dict:
    return {"ts": ts, "open": close, "high": close, "low": close, "close": close, "volume": 100.0}


CLOSE_EPOCH = _checkpoint_epoch("2026-09-03", "CLOSE")  # 15:30:00 KST, via the module's own clock


# --- _close_point: back to its original, unparameterized, strict behavior --


def test_close_point_signature_has_no_fallback_parameter():
    """_close_point takes no extra parameters -- confirms the fabricated-
    close-value fallback was fully removed, not just defaulted off."""
    import inspect

    sig = inspect.signature(_close_point)
    assert list(sig.parameters) == ["rows", "day"]


def test_close_point_none_when_strict_window_empty_stocks_and_indices_alike():
    rows = [_row(CLOSE_EPOCH - 930, 6580.0)]  # ~15.5 min before close, outside the strict window
    assert _close_point(rows, "2026-09-03") is None


def test_close_point_still_finds_a_real_in_window_row():
    rows = [_row(CLOSE_EPOCH - 930, 6580.0), _row(CLOSE_EPOCH - 30, 6600.0)]
    point = _close_point(rows, "2026-09-03")
    assert point["close"] == 6600.0


# --- _last_available_point_before_close: purely informational, separate field --


def test_last_available_point_before_close_bounded_and_labeled():
    rows = [_row(CLOSE_EPOCH - 930, 6581.89)]
    point = _last_available_point_before_close(rows, "2026-09-03", max_lookback_sec=1800)
    assert point == {"ts": CLOSE_EPOCH - 930, "price": 6581.89, "lag_sec": 930}


def test_last_available_point_before_close_none_when_too_stale():
    rows = [_row(CLOSE_EPOCH - 3600, 6580.0)]  # 1 hour before close -- too stale
    assert _last_available_point_before_close(rows, "2026-09-03", max_lookback_sec=1800) is None


def test_last_available_point_before_close_none_when_no_rows():
    assert _last_available_point_before_close([], "2026-09-03", max_lookback_sec=1800) is None


# --- _index_reaction: CLOSE stays PENDING; informational field is additive only --


def test_index_reaction_close_stays_pending_never_fabricated():
    rows = [
        {"ts": CLOSE_EPOCH - 22000, "open": 6500.0, "high": 6500.0, "low": 6500.0, "close": 6500.0, "volume": 100.0, "previous_close": 6490.0},
        _row(CLOSE_EPOCH - 930, 6581.89),
    ]
    result = _index_reaction(day="2026-09-03", target={"key": "kospi", "kind": "index", "symbol": "KOSPI"}, rows=rows)

    close_point = result["points"]["CLOSE"]
    assert close_point["status"] == "PENDING"
    assert close_point["price"] is None  # never backfilled with a non-real value

    informational = result["last_available_point_before_close"]
    assert informational == {"ts": CLOSE_EPOCH - 930, "price": 6581.89, "lag_sec": 930}

    # The informational field must never leak into return/forward-window math.
    for window in result["forward_windows"].values():
        assert window.get("status") in ("PENDING", "PARTIAL")
        assert window.get("return_to_close_pct") is None


def test_index_reaction_no_informational_field_when_nothing_available():
    rows = [{"ts": CLOSE_EPOCH - 22000, "open": 6500.0, "high": 6500.0, "low": 6500.0, "close": 6500.0, "volume": 100.0, "previous_close": 6490.0}]
    result = _index_reaction(day="2026-09-03", target={"key": "kosdaq", "kind": "index", "symbol": "KOSDAQ"}, rows=rows)
    assert result["points"]["CLOSE"]["status"] == "PENDING"
    assert result["last_available_point_before_close"] is None


def test_index_reaction_real_close_row_present_no_informational_field_needed():
    rows = [_row(CLOSE_EPOCH - 30, 6600.0)]
    result = _index_reaction(day="2026-09-03", target={"key": "kospi", "kind": "index", "symbol": "KOSPI"}, rows=rows)
    assert result["points"]["CLOSE"]["status"] == "OBSERVED"
    assert result["points"]["CLOSE"]["price"] == 6600.0
    assert result["last_available_point_before_close"] is None  # not needed -- CLOSE already OBSERVED


# --- stocks: completely unaffected (never opt into the informational lookup) --


def test_stock_reaction_close_gap_stays_pending_no_informational_field():
    rows = [
        {"ts": CLOSE_EPOCH - 22000, "open": 70000.0, "high": 70000.0, "low": 70000.0, "close": 70000.0, "volume": 100.0},
        _row(CLOSE_EPOCH - 930, 71000.0),
    ]
    result = _stock_reaction(
        day="2026-09-03",
        target={"key": "samsung", "kind": "stock", "symbol": "005930"},
        rows=rows,
        previous_close=69000.0,
    )
    assert result["points"]["CLOSE"]["status"] == "PENDING"
    assert result["last_available_point_before_close"] is None
