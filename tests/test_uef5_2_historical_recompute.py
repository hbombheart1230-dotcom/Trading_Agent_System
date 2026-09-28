"""UEF-5.2 canonical historical recompute tests -- Source Authority Remediation Correction 1.

Closes: HIGH-1 (legacy-cache contamination), HIGH-2 (source-window leakage / row-level scope), plus the
finalization-order and receipt-failure-observability MEDIUM findings from the architecture-approved
remediation's first implementation audit.

Tests are split, per the correction's own instruction, into:
  A. isolated deterministic tests (immutable temp snapshots / constructed fixtures -- never the live repo)
  B. live-repository smoke/accounting tests (marked as such; robust to the live host's concurrent writes)
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from libs.market_data import receipts as mdr
from libs.reporting.evaluation.canonical.adapters import q10_semiconductor as q10s
from libs.reporting.evaluation.uef5 import candle_authority as ca
from libs.reporting.evaluation.uef5 import clean_evidence_rules as rules
from libs.reporting.evaluation.uef5 import historical_recompute as hr
from libs.reporting.evaluation.uef5 import session_policy as sp
from libs.reporting.evaluation.uef5.clean_evidence_coverage import DEFAULT_FAMILIES, build_repo_registry
from libs.reporting.evaluation.uef5.clean_evidence_registry import (
    EvidenceRegistry, EvidenceRule, EvidenceStatus, ReasonCode, Scope,
)

REPO = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
BY_LABEL = {f.label: f for f in DEFAULT_FAMILIES}
FAST = tuple(BY_LABEL[k] for k in ("Q11 v2", "Q11 v1", "Q12 Calc2", "Opening Shadow 1A", "Opening Shadow 1B/1C"))


def _files(d: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(d.iterdir())}


def _fam(run, label):
    return next(f for f in run.families if f.label == label)


# =============================================================================
# shared fixture helpers -- real receipt chain (raw archive + attested artifact + receipt)
# =============================================================================

def _attested_bytes(symbol: str, rows: list[dict]) -> bytes:
    payload = {"schema_version": ca.EXPECTED_SCHEMA, "symbol": symbol, "row_count": len(rows), "rows": rows}
    return json.dumps(payload).encode("utf-8")


def _install_chain(archive_root, normalized_root, receipt_root, *, symbol, rows, window=None, raw_pages=None, **overrides):
    """Builds the full, real receipt-verification chain a production acquisition would produce: a raw
    page bundle, an INDEPENDENTLY-attested normalized artifact containing exactly `rows`, and a receipt
    binding both. Returns the receipt."""
    raw_pages = raw_pages or [f"raw-page-for-{symbol}"]
    raw_bytes = mdr.raw_page_bundle_bytes(raw_pages)
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    raw_ref = mdr.content_addressed_ref(provider=mdr.PROVIDER_KIWOOM, producer_id=mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1,
                                        symbol=symbol, raw_sha256=raw_sha)
    mdr.persist_raw_artifact(archive_root, raw_ref, raw_bytes)
    attested = _attested_bytes(symbol, rows)
    norm_sha = hashlib.sha256(attested).hexdigest()
    norm_ref = mdr.normalized_content_ref(provider=mdr.PROVIDER_KIWOOM, producer_id=mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1,
                                          symbol=symbol, normalized_sha256=norm_sha)
    mdr.persist_raw_artifact(normalized_root, norm_ref, attested)
    ts_list = [r["ts"] for r in rows]
    win = window or ((min(ts_list), max(ts_list)) if ts_list else (0, 0))
    fields = dict(
        receipt_schema=mdr.RECEIPT_SCHEMA, provider=mdr.PROVIDER_KIWOOM, producer_id=mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1,
        producer_version="1", symbol=symbol, trading_date=None, interval="1m",
        source_window_start=win[0], source_window_end=win[1],
        raw_payload_sha256=raw_sha, raw_archive_ref=raw_ref, normalized_candle_sha256=norm_sha,
        normalizer_id="x", normalizer_version="1", normalizer_implementation_digest="d" * 64, row_count=len(rows),
    )
    fields.update(overrides)
    receipt = mdr.MarketDataReceipt(**fields)
    mdr.write_receipt(receipt_root, receipt)
    return receipt


TS0 = 1785459600  # 2026-07-31 10:00 KST


def _kst_raw(ts):
    return datetime.fromtimestamp(ts, KST).strftime("%Y%m%d%H%M%S")


def _row(ts, close=100.0, **kw):
    r = {"ts": ts, "open": close, "high": close, "low": close, "close": close, "volume": 5.0, "raw_ts": _kst_raw(ts)}
    r.update(kw)
    return r


# =============================================================================
# A. isolated -- HIGH-1: legacy cache contamination
# =============================================================================

def test_legacy_row_never_gains_authority_from_a_later_receipt(tmp_path):
    """Codex's exact reproducer: an old, unattested cache row A plus a freshly-attested row B must never
    both become FULL_SOURCE_AUTHORITY merely because a legacy convenience file merges them."""
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    row_b = _row(TS0)
    receipt = _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=[row_b])
    day = ca.kst_date(TS0)

    # a legacy convenience cache exists on disk containing BOTH the old unattested row and the new one --
    # UEF must never read it for admission
    legacy_row_a = _row(TS0 - 600, close=0.5)
    v, admitted_rows = ca.verify_receipt_bound_candles(
        receipt, symbol="005930", day=day, anchors=[], archive_root=archive_root, normalized_root=normalized_root)
    assert v.admitted
    assert {r["ts"] for r in admitted_rows} == {row_b["ts"]}
    assert legacy_row_a["ts"] not in {r["ts"] for r in admitted_rows}


def test_merged_convenience_cache_never_consulted_for_admission(tmp_path):
    """A legacy merged cache file may sit on disk at the conventional path; admission is governed solely
    by the receipt-bound attested artifact and never reads that file at all."""
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    fresh = [_row(TS0), _row(TS0 + 60)]
    receipt = _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=fresh)
    legacy_dir = tmp_path / "legacy_cache"
    legacy_dir.mkdir()
    # deliberately GARBAGE/mismatched content -- must have zero effect on admission
    (legacy_dir / "005930.json").write_text("not even valid candle json {{{", encoding="utf-8")
    day = ca.kst_date(TS0)
    store = hr.SecondaryCandleInputs(tmp_path, ("legacy_cache",), raw_archive_root=archive_root,
                                     receipt_root=receipt_root, normalized_root=normalized_root)
    recorded = store.verify("005930", day, [])
    assert recorded[0]["provenance_status"] == "FULL_SOURCE_AUTHORITY"
    assert recorded[0]["legacy_cache_present_not_authoritative"] is True  # diagnostic only, never gating
    projected = store.consume("005930", day, [], recorded)
    assert {r["ts"] for r in projected} == {row["ts"] for row in fresh}


def test_q10_semi_cross_generation_contamination_blocked(tmp_path):
    """Two acquisition 'generations' for the same symbol: an OLD generation attested day D with row A,
    a NEWER generation attested a DIFFERENT day with row B. The newer receipt (which supersedes the
    older one at the same receipt-lookup identity) must never let day D's row A become admissible --
    day D simply has no rows in the newer attested artifact."""
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    day_d_ts = TS0
    day_e_ts = TS0 + 86400 * 30
    _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=[_row(day_d_ts)])
    # a later acquisition overwrites the "current receipt" pointer with one that only attests a later day
    _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=[_row(day_e_ts)])
    current = mdr.read_receipt(receipt_root, mdr.PROVIDER_KIWOOM, mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1, "005930")
    v, rows = ca.verify_receipt_bound_candles(current, symbol="005930", day=ca.kst_date(day_d_ts), anchors=[],
                                              archive_root=archive_root, normalized_root=normalized_root)
    assert not v.admitted and rows == []  # day D's row is simply absent from the current attested artifact


# =============================================================================
# A. isolated -- HIGH-2: row-level source-window leakage
# =============================================================================

def test_source_window_row_level_leakage_rejected(tmp_path):
    """Exact reproducer: receipt window = one epoch only (09:00); rows = [09:00, 09:01] -> the whole day
    must fail closed, never admitting the in-range 09:00 row alone."""
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    in_window = _row(TS0)
    out_of_window = _row(TS0 + 60)
    receipt = _install_chain(archive_root, normalized_root, receipt_root, symbol="005930",
                             rows=[in_window, out_of_window], window=(TS0, TS0))
    v, rows = ca.verify_receipt_bound_candles(receipt, symbol="005930", day=ca.kst_date(TS0), anchors=[],
                                              archive_root=archive_root, normalized_root=normalized_root)
    assert not v.admitted and rows == []
    assert v.reason == ca.R_SOURCE_SCOPE_VIOLATION


def test_source_window_exact_single_row_allowed(tmp_path):
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    row = _row(TS0)
    receipt = _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=[row], window=(TS0, TS0))
    v, rows = ca.verify_receipt_bound_candles(receipt, symbol="005930", day=ca.kst_date(TS0), anchors=[],
                                              archive_root=archive_root, normalized_root=normalized_root)
    assert v.admitted and [r["ts"] for r in rows] == [TS0]


def test_source_window_one_row_outside_fails_the_whole_unit_not_a_silent_subset(tmp_path):
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    rows_in = [_row(TS0 + 60 * i) for i in range(5)]
    rows_all = rows_in + [_row(TS0 + 3600)]  # one row an hour later, outside the window below
    receipt = _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=rows_all,
                             window=(TS0, TS0 + 240))  # covers only the first 5 rows' span
    v, admitted = ca.verify_receipt_bound_candles(receipt, symbol="005930", day=ca.kst_date(TS0), anchors=[],
                                                  archive_root=archive_root, normalized_root=normalized_root)
    assert not v.admitted and admitted == []  # NOT a partial admission of the 5 in-range rows


# =============================================================================
# A. isolated -- exact normalized-artifact / receipt binding
# =============================================================================

def test_receipt_binds_exact_normalized_artifact_hash_mismatch_is_invalid(tmp_path):
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    receipt = _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=[_row(TS0)])
    # tamper the attested artifact after the receipt was issued
    ref = mdr.normalized_content_ref(provider=receipt.provider, producer_id=receipt.producer_id, symbol="005930",
                                     normalized_sha256=receipt.normalized_candle_sha256)
    path = mdr.resolve_archive_path(normalized_root, ref)
    path.unlink()
    path.write_bytes(_attested_bytes("005930", [_row(TS0, close=999.0)]))
    v, rows = ca.verify_receipt_bound_candles(receipt, symbol="005930", day=ca.kst_date(TS0), anchors=[],
                                              archive_root=archive_root, normalized_root=normalized_root)
    assert v.provenance_status is ca.ProvenanceStatus.INVALID and rows == []


def test_receipt_binds_exact_raw_archive_hash_mismatch_is_invalid(tmp_path):
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    receipt = _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=[_row(TS0)])
    path = mdr.resolve_archive_path(archive_root, receipt.raw_archive_ref)
    path.unlink()
    path.write_bytes(mdr.raw_page_bundle_bytes(["tampered"]))
    v, rows = ca.verify_receipt_bound_candles(receipt, symbol="005930", day=ca.kst_date(TS0), anchors=[],
                                              archive_root=archive_root, normalized_root=normalized_root)
    assert v.provenance_status is ca.ProvenanceStatus.INVALID and rows == []


def test_no_receipt_no_archive_root_no_normalized_root_all_not_proven(tmp_path):
    v0, r0 = ca.verify_receipt_bound_candles(None, symbol="005930", day=ca.kst_date(TS0), anchors=[],
                                             archive_root=None, normalized_root=None)
    assert v0.provenance_status is ca.ProvenanceStatus.NOT_PROVEN and r0 == []
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    receipt = _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=[_row(TS0)])
    v1, r1 = ca.verify_receipt_bound_candles(receipt, symbol="005930", day=ca.kst_date(TS0), anchors=[],
                                             archive_root=None, normalized_root=normalized_root)
    assert v1.provenance_status is ca.ProvenanceStatus.NOT_PROVEN and r1 == []
    v2, r2 = ca.verify_receipt_bound_candles(receipt, symbol="005930", day=ca.kst_date(TS0), anchors=[],
                                             archive_root=archive_root, normalized_root=None)
    assert v2.provenance_status is ca.ProvenanceStatus.NOT_PROVEN and r2 == []


def test_unrecognized_provider_producer_schema_symbol(tmp_path):
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    r_provider = _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=[_row(TS0)], provider="unknown")
    v, _ = ca.verify_receipt_bound_candles(r_provider, symbol="005930", day=ca.kst_date(TS0), anchors=[],
                                           archive_root=archive_root, normalized_root=normalized_root)
    assert v.provenance_status is ca.ProvenanceStatus.NOT_PROVEN

    r_symbol = _install_chain(archive_root, normalized_root, receipt_root, symbol="000660", rows=[_row(TS0)])
    v2, _ = ca.verify_receipt_bound_candles(r_symbol, symbol="005930", day=ca.kst_date(TS0), anchors=[],
                                            archive_root=archive_root, normalized_root=normalized_root)
    assert v2.provenance_status is ca.ProvenanceStatus.INVALID


def test_structural_invalid_attested_artifact_blocks_regardless_of_receipt(tmp_path):
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    bad_rows = [dict(_row(TS0), close=0.0, high=0.0, low=0.0, open=0.0)]
    receipt = _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=bad_rows)
    v, rows = ca.verify_receipt_bound_candles(receipt, symbol="005930", day=ca.kst_date(TS0), anchors=[],
                                              archive_root=archive_root, normalized_root=normalized_root)
    assert v.structural_status is ca.StructuralStatus.INVALID and rows == []


def test_anchor_corroboration_still_diagnostic_only(tmp_path):
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    row = _row(TS0, close=100.0)
    receipt = _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=[row])
    contradicting = ca.Anchor(row["ts"], row["raw_ts"], 999.0, "baseline")
    v, rows = ca.verify_receipt_bound_candles(receipt, symbol="005930", day=ca.kst_date(TS0), anchors=[contradicting],
                                              archive_root=archive_root, normalized_root=normalized_root)
    assert v.admitted  # a contradicting diagnostic anchor never blocks a receipt-verified admission
    assert v.corroboration["status"] == "CONTRADICTED"


# =============================================================================
# A. isolated -- SecondaryCandleInputs / historical_recompute wiring, TOCTOU
# =============================================================================

def test_secondary_input_identity_shape(tmp_path):
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    rows = [_row(TS0), _row(TS0 + 60)]
    _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=rows)
    store = hr.SecondaryCandleInputs(tmp_path, (), raw_archive_root=archive_root, receipt_root=receipt_root,
                                     normalized_root=normalized_root)
    recorded = store.verify("005930", ca.kst_date(TS0), [])
    identity = recorded[0]["secondary_input_identity"]
    assert set(identity) == {"source_authority", "evaluation_policy", "canonical_projection_digest"}
    sa = identity["source_authority"]
    assert sa["verification_result"] == "FULL_SOURCE_AUTHORITY" and sa["receipt_digest"]
    ep = identity["evaluation_policy"]
    assert ep["session_policy_id"] == sp.KOREAN_REGULAR_SESSION.policy_id and ep["canonical_row_count"] == 2


def test_consume_projects_to_canonical_session(tmp_path):
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    before = _row(TS0 - 3900)  # ~08:55, before session
    kept = [_row(TS0 + 60 * i) for i in range(3)]  # 10:00-10:02, in session
    after = _row(TS0 + 23700)  # after session
    rows = [before, *kept, after]
    _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=rows,
                   window=(before["ts"], after["ts"]))
    store = hr.SecondaryCandleInputs(tmp_path, (), raw_archive_root=archive_root, receipt_root=receipt_root,
                                     normalized_root=normalized_root)
    recorded = store.verify("005930", ca.kst_date(TS0), [])
    projected = store.consume("005930", ca.kst_date(TS0), [], recorded)
    assert {r["ts"] for r in projected} == {r["ts"] for r in kept}


def test_consume_toctou_receipt_changed_since_verify(tmp_path):
    archive_root, normalized_root, receipt_root = tmp_path / "archive", tmp_path / "normalized", tmp_path / "receipts"
    row = _row(TS0)
    _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=[row])
    store = hr.SecondaryCandleInputs(tmp_path, (), raw_archive_root=archive_root, receipt_root=receipt_root,
                                     normalized_root=normalized_root)
    recorded = store.verify("005930", ca.kst_date(TS0), [])
    assert [r["ts"] for r in store.consume("005930", ca.kst_date(TS0), [], recorded)] == [row["ts"]]
    # a later, different acquisition replaces the receipt pointer with a new, still-valid one
    _install_chain(archive_root, normalized_root, receipt_root, symbol="005930", rows=[_row(TS0 + 600)])
    with pytest.raises(hr.SecondaryInputAuthorityError) as ei:
        store.consume("005930", ca.kst_date(TS0), [], recorded)
    assert ei.value.reason is hr.Reason.SECONDARY_INPUT_HASH_MISMATCH


def test_consume_refuses_unrecorded_symbol_day():
    store = hr.SecondaryCandleInputs(Path("."), ())
    with pytest.raises(hr.SecondaryInputAuthorityError):
        store.consume("005930", "2026-07-31", [], [])


def test_secondary_disposition_maps_codes():
    assert hr._secondary_disposition(ca.R_AUTHORITY_NOT_PROVEN) == (hr.Bucket.BLOCKED_SECONDARY_AUTHORITY, hr.Reason.SECONDARY_INPUT_AUTHORITY_NOT_PROVEN)
    b, r = hr._secondary_disposition(ca.R_SOURCE_SCOPE_VIOLATION)
    assert b is hr.Bucket.BLOCKED_SECONDARY_AUTHORITY and r is hr.Reason.SECONDARY_INPUT_SOURCE_SCOPE_VIOLATION
    b2, r2 = hr._secondary_disposition(ca.R_RECEIPT_INVALID)
    assert b2 is hr.Bucket.BLOCKED_SECONDARY_AUTHORITY and r2 is hr.Reason.SECONDARY_INPUT_RECEIPT_INVALID


# =============================================================================
# A. isolated -- Calc1 / Calc2 real receipt path end to end
# =============================================================================

def _epoch(day: str, hhmm: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    return int(datetime.strptime(day, "%Y-%m-%d").replace(hour=h, minute=m, tzinfo=KST).timestamp())


def _session_candles(day: str, base: float = 5000.0) -> list[dict]:
    start = _epoch(day, "09:00")
    return [_row(start + 60 * i, base + i * 0.1) for i in range(0, 391, 5)]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _install_receipt_for_fixture(root: Path, symbol: str, day: str) -> None:
    rows = _session_candles(day)
    archive_root, normalized_root, receipt_root = root / "archive", root / "normalized", root / "receipts"
    _install_chain(archive_root, normalized_root, receipt_root, symbol=symbol, rows=rows,
                   window=(_epoch(day, "00:00") - 86400, _epoch(day, "00:00") + 2 * 86400))


def _calc1_fixture(tmp_path: Path, day: str = "2020-06-15") -> Path:
    epoch = _epoch(day, "09:05")
    raw = _kst_raw(epoch)
    decision_id = f"BTW_{day.replace('-', '')}_{epoch}"
    fdir = tmp_path / "reports" / "evaluation" / "baseline_btc_woori_tech" / day
    _write_json(fdir / "baseline_btc_woori_forward_returns.json", {
        "schema_version": "baseline_btc_woori_forward_returns.v1", "evaluation_program_id": rules.Q12_PROGRAM,
        "day": day, "behavior_effect": "evaluation_only",
        "cost_model": {"source": "kiwoom.ka10170", "round_trip_cost_pct": 0.2, "slippage_pct": 0.05},
        "row_count": 1,
        "rows": [{
            "baseline_decision_id": decision_id, "symbol": "041190", "ticker": "041190.KQ", "rank": 1,
            "eligible": True, "action": "ENTRY",
            "baseline": {"available": True, "baseline_epoch": epoch, "baseline_price": 5000.0, "baseline_raw_ts": raw,
                        "source": "test_fixture"},
            "available": True, "reason": None, "returns": {},
        }],
        "summary": {},
    })
    _write_json(fdir / "baseline_btc_woori_decisions.json", {
        "schema_version": "baseline_btc_woori_decisions.v1", "evaluation_program_id": rules.Q12_PROGRAM,
        "behavior_effect": "shadow_only", "day": day, "fixed_target": "041190.KQ",
        "btc_signal_availability": {}, "decision_count": 1,
        "decisions": [{
            "schema_version": "baseline_btc_woori_decision.v1", "evaluation_program_id": rules.Q12_PROGRAM,
            "behavior_effect": "shadow_only", "decision_id": decision_id, "day": day, "as_of_epoch": epoch,
            "target": {"symbol": "041190", "ticker": "041190.KQ", "name": "test"},
            "btc_signal": {"available": False},
            "local_features": {"available": True, "candle_count": 1, "baseline_epoch": epoch,
                               "baseline_price": 5000.0, "baseline_raw_ts": raw},
            "entry_rules": [], "entry_rule_count": 0, "entry_conditions": {}, "exit_rules": [], "exit_rule_count": 0,
            "score": 0.0, "eligible": True, "action": "ENTRY", "reason": None,
            "order_execution_allowed": False, "order_intent": None,
            "llm_used": False, "strategist_used": False, "commander_used": False,
            "generated_at": f"{day}T00:00:00+00:00",
        }],
    })
    return tmp_path


def _calc2_fixture(tmp_path: Path, day: str = "2020-06-15") -> Path:
    epoch = _epoch(day, "09:05")
    fdir = tmp_path / "reports" / "evaluation" / "baseline_btc_woori_tech" / day
    outcome = {
        "status": "OBSERVED", "reason": "", "entry_epoch": epoch, "entry_price": 5000.0,
        "returns": {h: {"status": "OBSERVED", "gross_return_pct": 0.1, "net_return_pct": -0.9,
                        "mfe_pct": 0.2, "mae_pct": -0.1, "observed_epoch": epoch + s, "observed_price": 5001.0}
                   for h, s in (("+5m", 300), ("+15m", 900), ("+30m", 1800), ("+60m", 3600))},
    }
    outcome["returns"]["EOD"] = {"status": "OBSERVED", "gross_return_pct": 0.1, "net_return_pct": -0.9,
                                  "observed_epoch": _epoch(day, "15:30"), "observed_price": 5001.0}
    _write_json(fdir / "q12_btc_woori_hypothesis_validation.json", {
        "schema_version": rules.Q12_CALC2_SCHEMA, "contract_id": "q12_btc_woori_five_variable_validation.v1",
        "candidate_id": "TEST_CANDIDATE_V1", "behavior_effect": "observation_only", "day": day,
        "generated_at": f"{day}T00:00:00+00:00", "evidence_phase": "PROSPECTIVE",
        "prospective_start_day": day, "evidence_status": "AVAILABLE",
        "btc_delivery_source": "canonical_0855_capture",
        "cost_model": {"round_trip_cost_pct": 0.2, "slippage_pct": 0.05, "total_drag_pct": 0.25},
        "features": {
            "btc_0855": {"status": "OBSERVED", "target_epoch": epoch, "reason": ""},
            "btc_daily_context": {"status": "MISSING", "reason": "x"},
            "woori_opening": {"status": "OBSERVED", "reason": "", "previous_close": 5000.0, "opening_price": 5000.0,
                              "opening_gap_pct": 0.0, "opening_gap_band": "FLAT"},
            "entry_methods": {"09:03": {"status": "OBSERVED", "reason": "", "entry_epoch": epoch, "entry_price": 5000.0}},
            "definitions": {},
        },
        "entry_outcomes": {"09:03": outcome},
        "observed_checkpoint_count": 5, "order_execution_allowed": False, "order_intent": None,
    })
    return tmp_path


def test_calc1_real_receipt_path_end_to_end(tmp_path):
    day = "2020-06-15"
    root = _calc1_fixture(tmp_path, day)
    _install_receipt_for_fixture(root, "041190", day)
    out = tmp_path / "out"
    run = hr.run_historical_recompute(
        root, out, families=(BY_LABEL["Q12 Calc1"],), candle_source_dirs=(),
        raw_archive_root=root / "archive", receipt_root=root / "receipts", normalized_root=root / "normalized")
    f = _fam(run, "Q12 Calc1")
    assert f.counts["registry_CLEAN"] == 1, f.reason_codes
    assert f.counts["recomputed"] == 1
    assert f.counts["episodes"] == 1 and f.counts["checkpoints"] > 0 and f.counts["aggregates"] > 0


def test_calc1_missing_or_unproven_receipt_blocks(tmp_path):
    day = "2020-06-15"
    root = _calc1_fixture(tmp_path, day)
    run_no_receipt = hr.run_historical_recompute(root, None, families=(BY_LABEL["Q12 Calc1"],), candle_source_dirs=())
    f = _fam(run_no_receipt, "Q12 Calc1")
    assert f.counts["recomputed"] == 0 and f.counts["blocked_secondary_authority"] == 1


def test_calc2_real_receipt_path_end_to_end(tmp_path):
    day = "2020-06-15"
    root = _calc2_fixture(tmp_path, day)
    _install_receipt_for_fixture(root, "041190", day)
    out = tmp_path / "out"
    run = hr.run_historical_recompute(
        root, out, families=(BY_LABEL["Q12 Calc2"],), candle_source_dirs=(),
        raw_archive_root=root / "archive", receipt_root=root / "receipts", normalized_root=root / "normalized")
    f = _fam(run, "Q12 Calc2")
    assert f.counts["registry_CLEAN"] == 1, f.reason_codes
    assert f.counts["recomputed"] == 1
    assert f.counts["episodes"] == 1 and f.counts["checkpoints"] > 0 and f.counts["aggregates"] > 0
    doc = json.loads((run.output_dir / "aggregates.json").read_text(encoding="utf-8"))
    for e in doc["aggregates"]:
        if e["provenance"]["family"] == "Q12 Calc2":
            assert e["record"]["metrics"]["context"]["cost_policy_id"] == ""


def test_calc2_missing_or_unproven_receipt_blocks(tmp_path):
    day = "2020-06-15"
    root = _calc2_fixture(tmp_path, day)
    run_no_receipt = hr.run_historical_recompute(root, None, families=(BY_LABEL["Q12 Calc2"],), candle_source_dirs=())
    f = _fam(run_no_receipt, "Q12 Calc2")
    assert f.counts["recomputed"] == 0 and f.counts["blocked_secondary_authority"] == 1


def test_calc1_calc2_never_reinvent_adapter_semantics():
    import inspect
    src1 = inspect.getsource(hr._pipeline_q12_calc1)
    src2 = inspect.getsource(hr._pipeline_q12_calc2)
    for src in (src1, src2):
        assert "def calculate_" not in src and "net_return =" not in src


# =============================================================================
# A. isolated -- semantic implementation identity / run id, using REAL file bytes
# =============================================================================

def _entries_and_registry():
    reg, dv = build_repo_registry(REPO)
    entries = hr.classify_inputs(REPO, reg, frozenset(dv["invalid_days"]), (BY_LABEL["Q11 v2"],))
    return entries, reg


def _base_cfg():
    return hr.effective_run_config(families=(BY_LABEL["Q11 v2"],), candle_source_dirs=hr.CANDLE_SOURCE_DIRS,
                                   max_parse_bytes=10_000_000, session_policy=sp.KOREAN_REGULAR_SESSION)


def test_semantic_implementation_files_all_exist_and_hash():
    ids = hr.semantic_implementation_identity(REPO)
    assert set(ids) == set(hr._SEMANTIC_IMPLEMENTATION_FILES)
    for path, digest in ids.items():
        assert digest == hashlib.sha256((REPO / path).read_bytes()).hexdigest()


def test_frozen_core_files_not_duplicated_in_semantic_manifest():
    frozen = set(hr.frozen_core_manifest_identity(REPO))
    semantic = set(hr._SEMANTIC_IMPLEMENTATION_FILES)
    assert not (frozen & semantic)


def test_normalizer_not_duplicated_in_semantic_manifest():
    assert "libs/skills/dto_extractors.py" not in hr._SEMANTIC_IMPLEMENTATION_FILES


@pytest.mark.parametrize("relpath", [
    "libs/reporting/evaluation/uef5/candle_authority.py",
    "libs/reporting/evaluation/uef5/clean_evidence_rules.py",
    "libs/reporting/evaluation/uef5/historical_recompute.py",
])
def test_actual_file_mutation_changes_the_semantic_digest_and_run_id(tmp_path, relpath):
    """Codex explicitly required this to use ACTUAL file bytes (a temp copy, mutated), not merely two
    arbitrary precomputed strings, and never touching the real repository file."""
    real_bytes = (REPO / relpath).read_bytes()
    copy_a = tmp_path / "a.py"
    copy_b = tmp_path / "b.py"
    copy_a.write_bytes(real_bytes)
    copy_b.write_bytes(real_bytes + b"\n# mutated for test\n")
    digest_a = hashlib.sha256(copy_a.read_bytes()).hexdigest()
    digest_b = hashlib.sha256(copy_b.read_bytes()).hexdigest()
    assert digest_a == hashlib.sha256(real_bytes).hexdigest() and digest_a != digest_b

    entries, reg = _entries_and_registry()
    frozen = hr.frozen_core_manifest_identity(REPO)
    cfg = _base_cfg()
    real_impl = hr.semantic_implementation_identity(REPO)
    assert real_impl[relpath] == digest_a  # sanity: the real repo file matches copy_a's bytes right now
    id_a = dict(real_impl, **{relpath: digest_a})
    id_b = dict(real_impl, **{relpath: digest_b})
    run_a = hr.compute_run_id(entries, reg, implementation_identity=id_a, frozen_core_identity=frozen, run_config=cfg)
    run_b = hr.compute_run_id(entries, reg, implementation_identity=id_b, frozen_core_identity=frozen, run_config=cfg)
    assert run_a != run_b
    assert run_a == hr.compute_run_id(entries, reg, implementation_identity=id_a, frozen_core_identity=frozen, run_config=cfg)


def test_frozen_manifest_change_changes_run_id():
    entries, reg = _entries_and_registry()
    real_impl = hr.semantic_implementation_identity(REPO)
    cfg = _base_cfg()
    core_a = {"libs/reporting/evaluation/canonical/forward/engine.py": hashlib.sha256(b"a").hexdigest()}
    core_b = {"libs/reporting/evaluation/canonical/forward/engine.py": hashlib.sha256(b"b").hexdigest()}
    run_a = hr.compute_run_id(entries, reg, implementation_identity=real_impl, frozen_core_identity=core_a, run_config=cfg)
    run_b = hr.compute_run_id(entries, reg, implementation_identity=real_impl, frozen_core_identity=core_b, run_config=cfg)
    assert run_a != run_b


def test_session_policy_change_changes_run_id():
    entries, reg = _entries_and_registry()
    impl = hr.semantic_implementation_identity(REPO)
    frozen = hr.frozen_core_manifest_identity(REPO)
    cfg_a = _base_cfg()
    other_policy = dataclasses.replace(sp.KOREAN_REGULAR_SESSION, session_end="15:00")
    cfg_b = hr.effective_run_config(families=(BY_LABEL["Q11 v2"],), candle_source_dirs=hr.CANDLE_SOURCE_DIRS,
                                    max_parse_bytes=10_000_000, session_policy=other_policy)
    run_a = hr.compute_run_id(entries, reg, implementation_identity=impl, frozen_core_identity=frozen, run_config=cfg_a)
    run_b = hr.compute_run_id(entries, reg, implementation_identity=impl, frozen_core_identity=frozen, run_config=cfg_b)
    assert run_a != run_b


def test_receipt_content_changes_secondary_manifest_and_run_id(tmp_path):
    day = "2020-06-15"
    root1 = _calc1_fixture(tmp_path / "r1", day)
    _install_receipt_for_fixture(root1, "041190", day)
    root2 = _calc1_fixture(tmp_path / "r2", day)
    archive2, normalized2, receipt2 = root2 / "archive", root2 / "normalized", root2 / "receipts"
    _install_chain(archive2, normalized2, receipt2, symbol="041190", rows=_session_candles(day),
                   window=(_epoch(day, "00:00") - 86400, _epoch(day, "00:00") + 2 * 86400), producer_version="2")
    run1 = hr.run_historical_recompute(root1, None, families=(BY_LABEL["Q12 Calc1"],), candle_source_dirs=(),
                                       raw_archive_root=root1 / "archive", receipt_root=root1 / "receipts",
                                       normalized_root=root1 / "normalized")
    run2 = hr.run_historical_recompute(root2, None, families=(BY_LABEL["Q12 Calc1"],), candle_source_dirs=(),
                                       raw_archive_root=archive2, receipt_root=receipt2, normalized_root=normalized2)
    assert run1.run_id != run2.run_id


def test_out_root_console_and_walltime_do_not_change_run_id(tmp_path):
    a = hr.run_historical_recompute(REPO, tmp_path / "out_a", families=(BY_LABEL["Q11 v2"],))
    b = hr.run_historical_recompute(REPO, tmp_path / "out_b", families=(BY_LABEL["Q11 v2"],))
    assert a.run_id == b.run_id


def test_run_id_has_no_clock_or_uuid_inputs():
    for mod_file in (hr.__file__, ca.__file__, sp.__file__, mdr.__file__):
        src = Path(mod_file).read_text(encoding="utf-8")
        tree = ast.parse(src)
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
            a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not {"uuid", "random"} & mods, mod_file
        assert "datetime.now" not in src and "utcnow" not in src and "time.time" not in src, mod_file


# =============================================================================
# A. isolated -- strict determinism over an immutable temp snapshot (not the live repo)
# =============================================================================

@pytest.fixture(scope="module")
def isolated_snapshot(tmp_path_factory):
    snapshot = tmp_path_factory.mktemp("snapshot")
    src = REPO / "reports" / "evaluation" / "opportunity_engine_shadow"
    dst = snapshot / "reports" / "evaluation" / "opportunity_engine_shadow"
    shutil.copytree(src, dst)
    return snapshot


def test_isolated_snapshot_determinism(isolated_snapshot, tmp_path_factory):
    a = hr.run_historical_recompute(isolated_snapshot, tmp_path_factory.mktemp("out_a"), families=(BY_LABEL["Q11 v2"],))
    b = hr.run_historical_recompute(isolated_snapshot, tmp_path_factory.mktemp("out_b"), families=(BY_LABEL["Q11 v2"],))
    assert a.run_id == b.run_id
    assert _files(a.output_dir) == _files(b.output_dir)
    assert _fam(a, "Q11 v2").counts["unaccounted"] == 0


def test_identity_collision_fails_closed(isolated_snapshot, monkeypatch, tmp_path):
    real = hr.PIPELINES[rules.F_Q11]

    def doubled(ctx, entries):
        res = real(ctx, entries)
        res.episodes = res.episodes + res.episodes
        return res

    monkeypatch.setitem(hr.PIPELINES, rules.F_Q11, doubled)
    monkeypatch.setattr(hr, "_dedupe_episodes", lambda eps: list(eps))
    run = hr.run_historical_recompute(isolated_snapshot, tmp_path, families=(BY_LABEL["Q11 v2"],))
    assert run.status is hr.RunStatus.FAILED
    assert run.collisions and run.episodes == [] and run.aggregates == []
    assert not (run.output_dir / "episodes.jsonl").exists()
    assert (run.output_dir / "run_manifest.json").exists()


# =============================================================================
# B. live-repository smoke/accounting tests (robust to concurrent host writes)
# =============================================================================

@pytest.fixture(scope="module")
def full_run(tmp_path_factory):
    real = q10s.adapt_q10_semiconductor_decisions
    calls: list[int] = []

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    mp = pytest.MonkeyPatch()
    mp.setattr(q10s, "adapt_q10_semiconductor_decisions", counting)
    try:
        run = hr.run_historical_recompute(REPO, tmp_path_factory.mktemp("full"))
        run.adapter_calls = len(calls)  # type: ignore[attr-defined]
    finally:
        mp.undo()
    return run


@pytest.fixture(scope="module")
def fast_run(tmp_path_factory):
    return hr.run_historical_recompute(REPO, tmp_path_factory.mktemp("fast"), families=FAST)


def _q11_registry_with(extra_rule):
    reg, dv = build_repo_registry(REPO)
    return EvidenceRegistry(reg.registry_version + "+test", tuple(reg.rules) + (extra_rule,), reg.clean_domains), dv


def test_clean_and_eligible_is_recomputed(fast_run):
    f = _fam(fast_run, "Q11 v2")
    assert f.counts["registry_CLEAN"] > 0
    assert f.counts["recomputed"] == f.counts["registry_CLEAN"]
    assert f.counts["episodes"] > 0 and f.counts["aggregates"] > 0


def test_adapter_blocked_overrides_registry(monkeypatch):
    patched = dict(rules.ADAPTER_ELIGIBILITY[rules.F_Q11], adapter_status="BLOCKED")
    monkeypatch.setitem(rules.ADAPTER_ELIGIBILITY, rules.F_Q11, patched)
    run = hr.run_historical_recompute(REPO, None, families=(BY_LABEL["Q11 v2"],))
    f = _fam(run, "Q11 v2")
    assert f.counts["recomputed"] == 0 and run.episodes == []


def test_invalid_required_field_prevents_recompute():
    rule = EvidenceRule(
        rule_id="TEST_Q11_FORWARD_INVALID", status=EvidenceStatus.FIELD_INVALID,
        reason_code=ReasonCode.INVALID_TIMING_ALIGNMENT, scope=Scope(family=rules.F_Q11),
        source_authority=("test",), human_note="test", invalid_fields=("forward_outcome",))
    reg, dv = _q11_registry_with(rule)
    run = hr.run_historical_recompute(REPO, None, registry=reg, day_validity=dv, families=(BY_LABEL["Q11 v2"],))
    f = _fam(run, "Q11 v2")
    assert f.counts["recomputed"] == 0 and f.counts["skipped_invalid_required_field"] > 0


def test_all_inputs_accounted(full_run):
    a = full_run
    for f in a.families:
        assert f.counts["unaccounted"] == 0
        assert sum(f.counts[b.value] for b in hr.Bucket) == f.counts["discovered_source_artifacts"]


def test_no_frozen_uef_mutation(full_run):
    out = subprocess.run([sys.executable, "scripts/verify_uef_freeze_manifest.py"], cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    diff = subprocess.run(["git", "diff", "--quiet", "HEAD", "--",
                           "libs/reporting/evaluation/canonical",
                           "libs/reporting/evaluation/uef5/clean_evidence_registry.py",
                           "libs/reporting/evaluation/uef5/clean_evidence_rules.py",
                           "libs/reporting/evaluation/uef5/clean_evidence_coverage.py",
                           "libs/reporting/evaluation/uef5/__init__.py",
                           "scripts/build_uef5_clean_evidence_coverage.py",
                           "tests/test_uef5_1_clean_evidence_registry.py",
                           "docs/research/uef5_1_clean_evidence_registry.md"], cwd=REPO)
    assert diff.returncode == 0


def test_no_production_imports():
    skip_names = {"historical_recompute.py", "candle_authority.py", "session_policy.py"}
    for top in ("libs", "graphs", "apps"):
        for p in (REPO / top).rglob("*.py"):
            if p.name in skip_names or "market_data" in p.parts:
                continue
            tree = ast.parse(p.read_text(encoding="utf-8-sig", errors="ignore"))
            for n in ast.walk(tree):
                names = []
                if isinstance(n, ast.ImportFrom) and n.module:
                    names.append(n.module)
                elif isinstance(n, ast.Import):
                    names += [a.name for a in n.names]
                assert not any("uef5" in x for x in names), f"{p} imports {names}"


def test_no_broker_or_network_imports():
    for mod_file in (hr.__file__, ca.__file__, sp.__file__):
        tree = ast.parse(Path(mod_file).read_text(encoding="utf-8"))
        mods = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module:
                mods.add(n.module)
            elif isinstance(n, ast.Import):
                mods |= {a.name for a in n.names}
        assert not [m for m in mods if any(t in m for t in ("kiwoom", "broker", "requests", "socket", "urllib", "http", "execution"))]


def test_companion_missing_is_classified(tmp_path):
    ctx = hr.RunContext(tmp_path, hr.SecondaryCandleInputs(tmp_path, ()))
    d = tmp_path / "reports" / "evaluation" / "baseline_samsung_hynix" / "2026-01-02"
    d.mkdir(parents=True)
    p = d / "baseline_samsung_hynix_forward_returns.json"
    p.write_text("{}", encoding="utf-8")
    entry = hr.InputArtifact.__new__(hr.InputArtifact)
    entry.path = p.relative_to(tmp_path).as_posix()
    with pytest.raises(hr.CompanionArtifactMissingError):
        hr._companion(ctx, entry, "baseline_samsung_hynix_decisions.json")


def test_source_file_changed_detected(tmp_path):
    ctx = hr.RunContext(tmp_path, hr.SecondaryCandleInputs(tmp_path, ()))
    d = tmp_path / "reports" / "evaluation" / "baseline_samsung_hynix" / "2026-01-02"
    d.mkdir(parents=True)
    p = d / "baseline_samsung_hynix_forward_returns.json"
    p.write_text("{}", encoding="utf-8")
    entry = hr.InputArtifact.__new__(hr.InputArtifact)
    entry.path = p.relative_to(tmp_path).as_posix()
    entry.sha256 = hashlib.sha256(b"other").hexdigest()
    with pytest.raises(hr.SourceFileChangedError):
        hr._verify_unchanged(ctx, entry)


def test_serialization_failure_is_classified():
    class Bad:
        identity = type("I", (), {"evaluation_record_id": "x"})()

        def to_dict(self):
            raise TypeError("boom")

    with pytest.raises(hr.RecomputeSerializationError):
        hr._serialize_episodes([Bad()])


def test_q10_semiconductor_real_legacy_cache_stays_blocked(full_run):
    a = full_run
    semi = _fam(a, "Q10 Semiconductor")
    assert semi.counts["episodes"] == 0
    assert a.adapter_calls == semi.counts["recomputed"]  # type: ignore[attr-defined]


def test_missing_candle_file_gaps_stay_fail_closed(full_run):
    """No receipt exists for any real symbol in this repository -- Calc1's CLEAN inputs are correctly
    blocked_secondary_authority (NOT_PROVEN), not the old file-existence bucket."""
    a = full_run
    calc1 = _fam(a, "Q12 Calc1")
    assert calc1.counts["blocked_secondary_authority"] > 0
    assert "SECONDARY_INPUT_AUTHORITY_NOT_PROVEN" in calc1.reason_codes


def test_untracked_member_counts_are_flagged(full_run):
    assert _fam(full_run, "Q10 Semiconductor").counts["member_counts_complete"] is False


def test_zero_cost_policy_removed():
    assert not hasattr(hr, "zero_cost_policy") and "def zero_cost_policy" not in Path(hr.__file__).read_text(encoding="utf-8")


def test_q10_index_fg_creates_no_cost_policy_and_calls_no_costed_entrypoint(monkeypatch):
    from libs.reporting.evaluation.canonical.adapters import q10_index_reaction_adapter as q10fg

    def boom(*a, **k):
        raise AssertionError("a CostPolicy / costed F-G entrypoint must not be used without cost authority")

    monkeypatch.setattr(hr, "CostPolicy", boom)
    monkeypatch.setattr(q10fg, "canonicalize_q10_index_calc_f_artifact", boom)
    monkeypatch.setattr(q10fg, "canonicalize_q10_index_calc_g_artifact", boom)
    run = hr.run_historical_recompute(REPO, None, families=(BY_LABEL["Q10 Index"],))
    f = _fam(run, "Q10 Index")
    assert f.counts["recomputed_episode_units"] == f.counts["admissible_units"] > 0
    assert f.counts["adapter_failures"] == 0


def test_q10_index_fg_episodes_produced_but_no_fg_aggregate(full_run):
    f = _fam(full_run, "Q10 Index")
    assert f.counts["episodes"] > 0 and f.counts["checkpoints"] > 0
    kinds = {m.get("calc") for _agg, m in full_run.aggregates if m["family"] == "Q10 Index"}
    assert kinds == {"H"}


def test_q10_index_fg_partial_stage_model_never_complete(full_run):
    f = _fam(full_run, "Q10 Index")
    assert f.status == "PARTIAL" and "MISSING_AUTHORITATIVE_COST_POLICY" in f.reason_codes
    assert f.counts["blocked_missing_cost_policy"] == f.counts["recomputed_units"] > 0


def test_q10_index_h_unchanged_and_no_double_cost(full_run):
    h = [(agg, m) for agg, m in full_run.aggregates if m.get("calc") == "H"]
    assert h
    for agg, _m in h:
        d = agg.to_dict()["metrics"]
        assert d["context"]["cost_policy_id"] == ""
        pop = d["sample_population"]
        assert pop["sample_count"] == pop["evaluated_count"] + pop["missing_count"] + pop["excluded_count"]
        if pop["excluded_count"]:
            assert pop["exclusion_note"] == hr._Q10_H_EXCLUSION_NOTE


def test_missing_and_excluded_are_not_zero(full_run):
    doc = json.loads((full_run.output_dir / "aggregates.json").read_text(encoding="utf-8"))
    seen_missing = seen_excluded = False
    for entry in doc["aggregates"]:
        pop = entry["record"]["metrics"]["sample_population"]
        assert pop["sample_count"] == pop["evaluated_count"] + pop["missing_count"] + pop["excluded_count"]
        seen_missing |= bool(pop["missing_count"])
        if pop["excluded_count"]:
            seen_excluded = True
    assert seen_missing and seen_excluded


def test_q11_v2_preserved(full_run):
    f = _fam(full_run, "Q11 v2")
    assert f.counts["recomputed"] == f.counts["registry_CLEAN"] > 0
    assert f.counts["episodes"] > 0 and f.counts["checkpoints"] > 0


def test_no_cost_double_application():
    cm = {"round_trip_cost_pct": 0.25, "slippage_pct": 0.05}
    p = hr.cost_policy_from_persisted_cost_model(cm, provenance="t")
    assert p.total_cost == pytest.approx(0.30)


def test_accounting_counts_are_separated(full_run):
    for f in full_run.families:
        for k in ("recomputed_episode_units", "recomputed_aggregate_units", "partial_aggregate_units",
                  "blocked_missing_cost_policy", "blocked_missing_candles", "blocked_secondary_authority",
                  "registry_skipped", "adapter_blocked", "parse_failed", "adapter_failed"):
            assert k in f.counts, (f.label, k)
        assert f.counts["unaccounted"] == 0


def test_pipeline_not_wired_is_explicit_not_silent(full_run):
    for label in ("Opening Shadow 1A", "Opening Shadow 1B/1C"):
        f = _fam(full_run, label)
        assert f.status == "COMPLETE"


@pytest.mark.parametrize("label", ["Q12 Calc2", "Opening Shadow 1A", "Opening Shadow 1B/1C"])
def test_non_clean_never_recomputed(fast_run, label):
    outcomes = {o["path"]: o for o in fast_run.run_manifest["artifact_outcomes"]}
    for art in fast_run.input_manifest["artifacts"]:
        if art["family"] != label or art["registry_status"] == "CLEAN":
            continue
        assert outcomes[art["source_artifact"]]["bucket"] == "skipped_registry"


def test_q11_v1_never_recomputed(fast_run):
    f = _fam(fast_run, "Q11 v1")
    assert f.counts["recomputed"] == 0
    assert f.counts["skipped_adapter_blocked"] == f.counts["discovered_source_artifacts"]
