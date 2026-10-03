"""libs/reporting/evaluation/uef5/session_policy.py -- SessionPolicy + canonical projection tests."""
from __future__ import annotations

import copy
import dataclasses
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from libs.reporting.evaluation.uef5 import session_policy as sp

KST = timezone(timedelta(hours=9))
DAY = "2026-07-31"


def _epoch(hhmm: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    return int(datetime.strptime(DAY, "%Y-%m-%d").replace(hour=h, minute=m, tzinfo=KST).timestamp())


def _row(hhmm: str, close: float = 100.0) -> dict:
    ts = _epoch(hhmm)
    return {"ts": ts, "open": close, "high": close, "low": close, "close": close, "volume": 1.0,
            "raw_ts": datetime.fromtimestamp(ts, KST).strftime("%Y%m%d%H%M%S")}


# ---------------------------------------------------------------------------
# policy identity
# ---------------------------------------------------------------------------

def test_policy_id_is_deterministic_content_derived():
    a = sp.KOREAN_REGULAR_SESSION
    b = dataclasses.replace(sp.KOREAN_REGULAR_SESSION)
    assert a.policy_id == b.policy_id
    assert a.policy_id.startswith("SESSIONPOL_")


def test_policy_id_changes_with_any_semantic_field():
    base = sp.KOREAN_REGULAR_SESSION
    for field, value in (("session_start", "09:30"), ("session_end", "15:00"), ("timezone", "UTC"),
                         ("start_inclusive", False), ("end_inclusive", False)):
        changed = dataclasses.replace(base, **{field: value})
        assert changed.policy_id != base.policy_id, field


def test_policy_id_has_no_uuid_or_clock():
    import json
    payload = json.dumps(sp.KOREAN_REGULAR_SESSION.semantic_fields())
    assert "uuid" not in payload.lower()


# ---------------------------------------------------------------------------
# canonical session (09:00 included, 15:30 included, pre-open / after-close excluded)
# ---------------------------------------------------------------------------

def test_09_00_included():
    assert sp.KOREAN_REGULAR_SESSION.in_session("09:00") is True


def test_15_30_included():
    assert sp.KOREAN_REGULAR_SESSION.in_session("15:30") is True


def test_pre_open_excluded():
    assert sp.KOREAN_REGULAR_SESSION.in_session("08:59") is False


def test_15_35_excluded():
    assert sp.KOREAN_REGULAR_SESSION.in_session("15:35") is False


# ---------------------------------------------------------------------------
# projection: order, digest, exclusions
# ---------------------------------------------------------------------------

def test_projection_orders_strictly_by_ts_ascending():
    rows = [_row("09:10"), _row("09:00"), _row("09:05")]
    result = sp.project_session(rows)
    assert [r["ts"] for r in result.rows] == sorted(r["ts"] for r in rows)


def test_projection_excludes_before_and_after_session():
    rows = [_row("08:55"), _row("09:00"), _row("12:00"), _row("15:30"), _row("15:35")]
    result = sp.project_session(rows)
    assert result.raw_row_count == 5
    assert result.canonical_row_count == 3
    assert result.excluded_before_session_count == 1
    assert result.excluded_after_session_count == 1
    kept_hhmm = {datetime.fromtimestamp(r["ts"], KST).strftime("%H:%M") for r in result.rows}
    assert kept_hhmm == {"09:00", "12:00", "15:30"}


def test_projection_digest_deterministic_same_input():
    rows = [_row("09:00"), _row("09:05")]
    d1 = sp.project_session(rows).projection_digest
    d2 = sp.project_session(list(reversed(rows))).projection_digest  # input order must not matter
    assert d1 == d2


def test_projection_digest_excludes_raw_ts_and_extra_fields():
    rows = [_row("09:00")]
    rows_with_extra = [dict(rows[0], raw_ts="DIFFERENT", extra_field="noise")]
    d1 = sp.project_session(rows).projection_digest
    d2 = sp.project_session(rows_with_extra).projection_digest
    assert d1 == d2  # raw_ts/extra fields never enter the digest


def test_projection_digest_changes_with_canonical_field_change():
    rows = [_row("09:00", close=100.0)]
    rows2 = [_row("09:00", close=101.0)]
    assert sp.project_session(rows).projection_digest != sp.project_session(rows2).projection_digest


def test_required_invariant_same_normalized_plus_same_policy_same_digest():
    rows = [_row("09:00"), _row("09:05"), _row("15:35")]
    r1 = sp.project_session(copy.deepcopy(rows), sp.KOREAN_REGULAR_SESSION)
    r2 = sp.project_session(copy.deepcopy(rows), sp.KOREAN_REGULAR_SESSION)
    assert r1.projection_digest == r2.projection_digest


def test_required_invariant_1535_change_does_not_move_projection_digest():
    """Adding/changing a 15:35 row while 09:00-15:30 rows are unchanged must change the *normalized
    artifact's own hash* (a caller concern) but leave canonical_projection_digest unchanged -- this
    proves the source changed while the canonical evaluation view did not."""
    base = [_row("09:00"), _row("15:30")]
    with_extended_a = base + [_row("15:35", close=1.0)]
    with_extended_b = base + [_row("15:35", close=999.0)]
    assert hashlib.sha256(str(with_extended_a).encode()).hexdigest() != hashlib.sha256(str(with_extended_b).encode()).hexdigest()
    assert sp.project_session(with_extended_a).projection_digest == sp.project_session(with_extended_b).projection_digest
    assert sp.project_session(base).projection_digest == sp.project_session(with_extended_a).projection_digest


def test_only_projected_rows_would_reach_an_adapter():
    rows = [_row("09:00"), _row("15:35")]
    result = sp.project_session(rows)
    assert all("09:00" <= datetime.fromtimestamp(r["ts"], KST).strftime("%H:%M") <= "15:30" for r in result.rows)
    assert len(result.rows) == 1
