"""libs/research/post_reclaim_alpha/kiwoom_history.py -- receipt-issuance lifecycle tests.

No network is used: `_issue_market_data_receipt`/`load_or_fetch_symbol_history` are exercised directly
with in-memory fetched rows and a fake reader, proving the finalization order, the legacy-cache
contamination fix, and receipt-failure observability without any Kiwoom credentials.
"""
from __future__ import annotations

import hashlib
import json
import logging

import pytest

from libs.market_data import receipts as mdr
from libs.research.post_reclaim_alpha import kiwoom_history as kh

SYMBOL = "005930"


def _row(ts: int, close: float = 100.0) -> dict:
    return {"ts": ts, "open": close, "high": close, "low": close, "close": close, "volume": 1.0,
           "raw_ts": str(ts)}


def _roots(tmp_path):
    return tmp_path / "archive", tmp_path / "receipts", tmp_path / "normalized"


def _meta(page_count=1):
    return {"page_count": page_count, "coverage_complete": True}


# ---------------------------------------------------------------------------
# HIGH-1 -- legacy cache contamination reproducer
# ---------------------------------------------------------------------------

def test_legacy_row_plus_fresh_receipt_does_not_contaminate(tmp_path):
    """Codex's exact reproducer: an old, unattested cache row A plus a freshly-fetched, raw-attested row
    B must NOT both become FULL_SOURCE_AUTHORITY just because they end up merged in one legacy file."""
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    row_a = _row(1_700_000_000, close=1.0)  # legacy, unattested
    kh._write_cache(cache_root / f"{SYMBOL}.json", symbol=SYMBOL, rows=[row_a])

    row_b = _row(1_700_000_060, close=2.0)  # freshly "fetched"

    class FakeReader:
        def fetch_until(self, *, symbol, minimum_epoch, max_pages):
            return [row_b], {"symbol": symbol, "page_count": 1, "row_count": 1,
                             "minimum_epoch_requested": minimum_epoch, "minimum_epoch_observed": row_b["ts"],
                             "maximum_epoch_observed": row_b["ts"], "coverage_complete": True, "error": "",
                             "raw_pages": ['{"page": "raw-response-for-B"}']}

    archive_root, receipt_root, normalized_root = _roots(tmp_path)
    rows, meta = kh.load_or_fetch_symbol_history(
        reader=FakeReader(), symbol=SYMBOL, minimum_epoch=1_699_999_000, cache_root=cache_root, max_pages=5,
        raw_archive_root=archive_root, receipt_root=receipt_root, normalized_root=normalized_root)
    assert {r["ts"] for r in rows} == {row_a["ts"], row_b["ts"]}  # the legacy convenience view still merges both

    receipt = mdr.read_receipt(receipt_root, mdr.PROVIDER_KIWOOM, mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1, SYMBOL)
    assert receipt is not None
    # the receipt's row_count/window must reflect ONLY the freshly fetched row, never the legacy one
    assert receipt.row_count == 1
    assert receipt.source_window_start == receipt.source_window_end == row_b["ts"]
    attested = mdr.read_raw_artifact(normalized_root, mdr.normalized_content_ref(
        provider=receipt.provider, producer_id=receipt.producer_id, symbol=SYMBOL, normalized_sha256=receipt.normalized_candle_sha256))
    attested_rows = json.loads(attested)["rows"]
    assert [r["ts"] for r in attested_rows] == [row_b["ts"]]  # row A never appears in the attested artifact
    assert hashlib.sha256(attested).hexdigest() == receipt.normalized_candle_sha256
    assert receipt.normalized_candle_sha256 != mdr.file_content_sha256(cache_root / f"{SYMBOL}.json")  # never the merged file


def test_no_fresh_rows_issues_no_receipt(tmp_path):
    """A cache-only load (fetch found nothing new) must never issue a receipt -- there is nothing new to
    attest, and the legacy rows stay unattested."""
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    kh._write_cache(cache_root / f"{SYMBOL}.json", symbol=SYMBOL, rows=[_row(1_700_000_000)])

    class EmptyReader:
        def fetch_until(self, *, symbol, minimum_epoch, max_pages):
            return [], {"symbol": symbol, "page_count": 0, "row_count": 0, "minimum_epoch_requested": minimum_epoch,
                       "minimum_epoch_observed": None, "maximum_epoch_observed": None, "coverage_complete": False,
                       "error": "", "raw_pages": []}

    archive_root, receipt_root, normalized_root = _roots(tmp_path)
    kh.load_or_fetch_symbol_history(reader=EmptyReader(), symbol=SYMBOL, minimum_epoch=1_699_999_000,
                                    cache_root=cache_root, max_pages=5, raw_archive_root=archive_root,
                                    receipt_root=receipt_root, normalized_root=normalized_root)
    assert mdr.read_receipt(receipt_root, mdr.PROVIDER_KIWOOM, mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1, SYMBOL) is None


# ---------------------------------------------------------------------------
# multi-page raw completeness
# ---------------------------------------------------------------------------

def test_multi_page_raw_bundle_represents_every_contributing_page(tmp_path):
    rows = [_row(1_700_000_000 + i * 60, close=float(i)) for i in range(5)]  # A/B from page1, C/D page2, E page3
    raw_pages = ['{"page":1,"rows":"A_B"}', '{"page":2,"rows":"C_D"}', '{"page":3,"rows":"E"}']
    archive_root, receipt_root, normalized_root = _roots(tmp_path)
    ok = kh._issue_market_data_receipt(
        symbol=SYMBOL, raw_pages=raw_pages, fetched_rows=rows, archive_root=archive_root,
        receipt_root=receipt_root, normalized_root=normalized_root, meta=_meta(page_count=3))
    assert ok
    receipt = mdr.read_receipt(receipt_root, mdr.PROVIDER_KIWOOM, mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1, SYMBOL)
    raw_bytes = mdr.read_raw_artifact(archive_root, receipt.raw_archive_ref)
    bundle = json.loads(raw_bytes)
    assert bundle["pages"] == raw_pages and bundle["page_count"] == 3
    assert receipt.row_count == 5


def test_removing_a_page_from_the_raw_archive_invalidates_authority(tmp_path):
    rows = [_row(1_700_000_000 + i * 60) for i in range(3)]
    raw_pages = ['{"page":1}', '{"page":2}', '{"page":3}']
    archive_root, receipt_root, normalized_root = _roots(tmp_path)
    kh._issue_market_data_receipt(symbol=SYMBOL, raw_pages=raw_pages, fetched_rows=rows, archive_root=archive_root,
                                  receipt_root=receipt_root, normalized_root=normalized_root, meta=_meta(3))
    receipt = mdr.read_receipt(receipt_root, mdr.PROVIDER_KIWOOM, mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1, SYMBOL)
    # tamper: overwrite the archived bundle with an incomplete page set (page 2 removed)
    tampered = mdr.raw_page_bundle_bytes([raw_pages[0], raw_pages[2]])
    path = mdr.resolve_archive_path(archive_root, receipt.raw_archive_ref)
    path.unlink()
    path.write_bytes(tampered)
    assert mdr.verify_raw_archive(archive_root, receipt.raw_archive_ref, receipt.raw_payload_sha256) is False


# ---------------------------------------------------------------------------
# exact normalized-artifact / receipt binding; merged cache never authoritative
# ---------------------------------------------------------------------------

def test_receipt_binds_exact_attested_artifact_not_merged_cache(tmp_path):
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    old = _row(1_699_000_000, close=0.5)
    kh._write_cache(cache_root / f"{SYMBOL}.json", symbol=SYMBOL, rows=[old])
    fresh = [_row(1_700_000_000 + i * 60) for i in range(2)]

    class FakeReader:
        def fetch_until(self, *, symbol, minimum_epoch, max_pages):
            return fresh, {"symbol": symbol, "page_count": 1, "row_count": 2, "minimum_epoch_requested": minimum_epoch,
                          "minimum_epoch_observed": fresh[0]["ts"], "maximum_epoch_observed": fresh[-1]["ts"],
                          "coverage_complete": True, "error": "", "raw_pages": ['{"p":1}']}

    archive_root, receipt_root, normalized_root = _roots(tmp_path)
    kh.load_or_fetch_symbol_history(reader=FakeReader(), symbol=SYMBOL, minimum_epoch=1_698_000_000,
                                    cache_root=cache_root, max_pages=5, raw_archive_root=archive_root,
                                    receipt_root=receipt_root, normalized_root=normalized_root)
    receipt = mdr.read_receipt(receipt_root, mdr.PROVIDER_KIWOOM, mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1, SYMBOL)
    assert receipt is not None
    merged_cache_sha = mdr.file_content_sha256(cache_root / f"{SYMBOL}.json")
    assert receipt.normalized_candle_sha256 != merged_cache_sha  # merged convenience cache is NOT receipt-authoritative
    lookup_by_symbol_and_date_overlap_only = receipt.symbol == SYMBOL  # deliberately naive check for contrast
    assert lookup_by_symbol_and_date_overlap_only  # true, but NOT sufficient -- the hash binding above is what matters
    resolved = mdr.read_raw_artifact(normalized_root, mdr.normalized_content_ref(
        provider=receipt.provider, producer_id=receipt.producer_id, symbol=SYMBOL, normalized_sha256=receipt.normalized_candle_sha256))
    assert {r["ts"] for r in json.loads(resolved)["rows"]} == {r["ts"] for r in fresh}


# ---------------------------------------------------------------------------
# finalization order / staged failure leaves no valid receipt
# ---------------------------------------------------------------------------

def test_receipt_last_finalization_order(tmp_path, monkeypatch):
    order: list[str] = []
    real_persist = mdr.persist_raw_artifact
    real_write = mdr.write_receipt

    def spy_persist(root, ref, data):
        order.append("raw_publish" if ".raw" in ref else "normalized_publish")
        return real_persist(root, ref, data)

    def spy_write(root, receipt):
        order.append("receipt_write")
        return real_write(root, receipt)

    monkeypatch.setattr(kh.mdr, "persist_raw_artifact", spy_persist)
    monkeypatch.setattr(kh.mdr, "write_receipt", spy_write)
    archive_root, receipt_root, normalized_root = _roots(tmp_path)
    ok = kh._issue_market_data_receipt(symbol=SYMBOL, raw_pages=['{"p":1}'], fetched_rows=[_row(1_700_000_000)],
                                       archive_root=archive_root, receipt_root=receipt_root,
                                       normalized_root=normalized_root, meta=_meta())
    assert ok
    assert order == ["raw_publish", "normalized_publish", "receipt_write"]


def test_staged_failure_before_receipt_leaves_no_valid_receipt(tmp_path, monkeypatch, caplog):
    archive_root, receipt_root, normalized_root = _roots(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("simulated normalized publish failure")

    monkeypatch.setattr(kh.mdr, "persist_raw_artifact", boom)
    with caplog.at_level(logging.WARNING, logger=kh._LOGGER.name):
        ok = kh._issue_market_data_receipt(symbol=SYMBOL, raw_pages=['{"p":1}'], fetched_rows=[_row(1_700_000_000)],
                                           archive_root=archive_root, receipt_root=receipt_root,
                                           normalized_root=normalized_root, meta=_meta())
    assert ok is False
    assert mdr.read_receipt(receipt_root, mdr.PROVIDER_KIWOOM, mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1, SYMBOL) is None


# ---------------------------------------------------------------------------
# receipt failure observability (no silent except: pass)
# ---------------------------------------------------------------------------

def test_receipt_failure_is_logged_not_silent(tmp_path, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("disk full (simulated)")

    monkeypatch.setattr(kh.mdr, "write_receipt", boom)
    archive_root, receipt_root, normalized_root = _roots(tmp_path)
    with caplog.at_level(logging.WARNING, logger=kh._LOGGER.name):
        ok = kh._issue_market_data_receipt(symbol=SYMBOL, raw_pages=['{"p":1}'], fetched_rows=[_row(1_700_000_000)],
                                           archive_root=archive_root, receipt_root=receipt_root,
                                           normalized_root=normalized_root, meta=_meta())
    assert ok is False
    messages = [r.message for r in caplog.records]
    assert any("market_data_receipt_issuance_failed" in m and "stage=receipt_write" in m and "RuntimeError" in m
              for m in messages)
    assert not any("disk full" in m for m in messages)  # exception class only -- message text/secrets never logged


def test_acquisition_still_returns_rows_when_receipt_issuance_fails(tmp_path, monkeypatch):
    """Acquisition/serving must never break because provenance issuance failed."""
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    fresh = [_row(1_700_000_000)]

    class FakeReader:
        def fetch_until(self, *, symbol, minimum_epoch, max_pages):
            return fresh, {"symbol": symbol, "page_count": 1, "row_count": 1, "minimum_epoch_requested": minimum_epoch,
                          "minimum_epoch_observed": fresh[0]["ts"], "maximum_epoch_observed": fresh[0]["ts"],
                          "coverage_complete": True, "error": "", "raw_pages": ['{"p":1}']}

    def boom(*a, **k):
        raise RuntimeError("simulated")

    monkeypatch.setattr(kh.mdr, "write_receipt", boom)
    archive_root, receipt_root, normalized_root = _roots(tmp_path)
    rows, meta = kh.load_or_fetch_symbol_history(
        reader=FakeReader(), symbol=SYMBOL, minimum_epoch=1_699_999_000, cache_root=cache_root, max_pages=5,
        raw_archive_root=archive_root, receipt_root=receipt_root, normalized_root=normalized_root)
    assert [r["ts"] for r in rows] == [fresh[0]["ts"]]  # rows still served
    assert mdr.read_receipt(receipt_root, mdr.PROVIDER_KIWOOM, mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1, SYMBOL) is None


# ---------------------------------------------------------------------------
# stale receipt cannot validate changed normalized bytes
# ---------------------------------------------------------------------------

def test_stale_receipt_cannot_validate_different_normalized_bytes(tmp_path):
    archive_root, receipt_root, normalized_root = _roots(tmp_path)
    kh._issue_market_data_receipt(symbol=SYMBOL, raw_pages=['{"p":1}'], fetched_rows=[_row(1_700_000_000)],
                                  archive_root=archive_root, receipt_root=receipt_root,
                                  normalized_root=normalized_root, meta=_meta())
    stale = mdr.read_receipt(receipt_root, mdr.PROVIDER_KIWOOM, mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1, SYMBOL)
    # a later acquisition with DIFFERENT rows issues its own, differently-content-addressed artifact+receipt
    kh._issue_market_data_receipt(symbol=SYMBOL, raw_pages=['{"p":2}'], fetched_rows=[_row(1_700_000_600, close=999.0)],
                                  archive_root=archive_root, receipt_root=receipt_root,
                                  normalized_root=normalized_root, meta=_meta())
    fresh = mdr.read_receipt(receipt_root, mdr.PROVIDER_KIWOOM, mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1, SYMBOL)
    assert stale.normalized_candle_sha256 != fresh.normalized_candle_sha256
    # the stale receipt's own attested artifact is untouched and still resolves to ITS OWN bytes only
    stale_attested = mdr.read_raw_artifact(normalized_root, mdr.normalized_content_ref(
        provider=stale.provider, producer_id=stale.producer_id, symbol=SYMBOL, normalized_sha256=stale.normalized_candle_sha256))
    assert hashlib.sha256(stale_attested).hexdigest() == stale.normalized_candle_sha256
    assert stale.normalized_candle_sha256 != fresh.normalized_candle_sha256  # can never cross-validate the other's bytes
