"""libs/market_data/receipts.py -- raw archive + MarketDataReceipt contract tests."""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from libs.market_data import receipts as mdr


def _receipt(**overrides) -> mdr.MarketDataReceipt:
    fields = dict(
        receipt_schema=mdr.RECEIPT_SCHEMA, provider=mdr.PROVIDER_KIWOOM, producer_id=mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1,
        producer_version="1", symbol="005930", trading_date=None, interval="1m",
        source_window_start=1000, source_window_end=2000,
        raw_payload_sha256="a" * 64, raw_archive_ref="kiwoom/KIWOOM_HISTORICAL_MINUTE_V1/005930/aaaa.raw",
        normalized_candle_sha256="b" * 64, normalizer_id="x", normalizer_version="1",
        normalizer_implementation_digest="c" * 64, row_count=10, diagnostic={"fetched_at": "2026-09-28T00:00:00Z"},
    )
    fields.update(overrides)
    return mdr.MarketDataReceipt(**fields)


# ---------------------------------------------------------------------------
# raw archive: confined path
# ---------------------------------------------------------------------------

def test_confined_path_resolves_under_root(tmp_path):
    p = mdr.resolve_archive_path(tmp_path, "a/b/c.raw")
    assert p == (tmp_path / "a" / "b" / "c.raw").resolve()


@pytest.mark.parametrize("ref", ["/etc/passwd", "C:\\evil.raw", "\\\\server\\share\\x"])
def test_absolute_path_rejected(tmp_path, ref):
    with pytest.raises(mdr.ArchivePathError):
        mdr.resolve_archive_path(tmp_path, ref)


@pytest.mark.parametrize("ref", ["../escape.raw", "a/../../escape.raw", "a/../../../etc/passwd"])
def test_traversal_rejected(tmp_path, ref):
    with pytest.raises(mdr.ArchivePathError):
        mdr.resolve_archive_path(tmp_path, ref)


def test_empty_ref_rejected(tmp_path):
    with pytest.raises(mdr.ArchivePathError):
        mdr.resolve_archive_path(tmp_path, "")


def test_escape_via_resolve_rejected(tmp_path):
    # a deeply nested relative ref that, once resolved, lands outside the root even without ".." at
    # the string level is still caught by the containment check
    sibling = tmp_path.parent / "sibling_escape_test_dir"
    sibling.mkdir(exist_ok=True)
    try:
        with pytest.raises(mdr.ArchivePathError):
            mdr.resolve_archive_path(tmp_path, "../sibling_escape_test_dir/x.raw")
    finally:
        sibling.rmdir()


# ---------------------------------------------------------------------------
# raw archive: atomic create / no-clobber semantics
# ---------------------------------------------------------------------------

def test_atomic_create_and_no_clobber_idempotent_reuse(tmp_path):
    data = b"hello raw bytes"
    digest = mdr.persist_raw_artifact(tmp_path, "sym/x.raw", data)
    assert digest == hashlib.sha256(data).hexdigest()
    # same path + same content -> idempotent success
    digest2 = mdr.persist_raw_artifact(tmp_path, "sym/x.raw", data)
    assert digest2 == digest
    assert (tmp_path / "sym" / "x.raw").read_bytes() == data


def test_different_hash_conflict_is_hard_failure(tmp_path):
    mdr.persist_raw_artifact(tmp_path, "sym/x.raw", b"first")
    with pytest.raises(mdr.RawArchiveConflictError):
        mdr.persist_raw_artifact(tmp_path, "sym/x.raw", b"second")
    assert (tmp_path / "sym" / "x.raw").read_bytes() == b"first"  # never overwritten in place


def test_raw_missing_verification_fails(tmp_path):
    assert mdr.read_raw_artifact(tmp_path, "sym/nope.raw") is None
    assert mdr.verify_raw_archive(tmp_path, "sym/nope.raw", "0" * 64) is False


def test_raw_hash_mismatch_verification_fails(tmp_path):
    mdr.persist_raw_artifact(tmp_path, "sym/x.raw", b"actual bytes")
    assert mdr.verify_raw_archive(tmp_path, "sym/x.raw", "0" * 64) is False
    assert mdr.verify_raw_archive(tmp_path, "sym/x.raw", hashlib.sha256(b"actual bytes").hexdigest()) is True


def test_content_addressed_ref_is_deterministic():
    ref1 = mdr.content_addressed_ref(provider="kiwoom", producer_id="X", symbol="005930", raw_sha256="a" * 64)
    ref2 = mdr.content_addressed_ref(provider="kiwoom", producer_id="X", symbol="005930", raw_sha256="a" * 64)
    assert ref1 == ref2 == "kiwoom/X/005930/" + "a" * 64 + ".raw"


# ---------------------------------------------------------------------------
# receipt: deterministic digest, diagnostic exclusion
# ---------------------------------------------------------------------------

def test_receipt_digest_deterministic_and_excludes_diagnostic():
    r1 = _receipt(diagnostic={"fetched_at": "2026-09-28T00:00:00Z"})
    r2 = _receipt(diagnostic={"fetched_at": "2099-01-01T00:00:00Z", "host": "other"})
    assert r1.digest() == r2.digest()  # only diagnostic differs -- digest unchanged


def test_receipt_digest_changes_with_any_semantic_field():
    base = _receipt()
    for field, value in (("symbol", "000660"), ("raw_payload_sha256", "d" * 64), ("row_count", 11),
                         ("normalizer_implementation_digest", "e" * 64), ("interval", "5m")):
        import dataclasses
        changed = dataclasses.replace(base, **{field: value})
        assert changed.digest() != base.digest(), field


def test_receipt_to_dict_carries_digest_and_diagnostic_separately():
    r = _receipt()
    d = r.to_dict()
    assert d["receipt_digest"] == r.digest()
    assert d["diagnostic"] == dict(r.diagnostic)
    assert "receipt_digest" not in r.semantic_fields()


def test_receipt_no_clock_uuid_random_in_digest_inputs():
    fields = _receipt().semantic_fields()
    payload = json.dumps(fields)
    assert "uuid" not in payload.lower()


# ---------------------------------------------------------------------------
# receipt I/O: write-last, atomic replace, round-trip
# ---------------------------------------------------------------------------

def test_write_read_round_trip(tmp_path):
    r = _receipt()
    path = mdr.write_receipt(tmp_path, r)
    assert path.is_file()
    back = mdr.read_receipt(tmp_path, r.provider, r.producer_id, r.symbol)
    assert back is not None and back.digest() == r.digest()


def test_read_receipt_absent_returns_none(tmp_path):
    assert mdr.read_receipt(tmp_path, "kiwoom", "X", "005930") is None


def test_write_receipt_atomic_replace_no_partial_visibility(tmp_path):
    r1 = _receipt(row_count=1)
    r2 = _receipt(row_count=2)
    mdr.write_receipt(tmp_path, r1)
    mdr.write_receipt(tmp_path, r2)
    back = mdr.read_receipt(tmp_path, r2.provider, r2.producer_id, r2.symbol)
    assert back.row_count == 2  # atomically replaced, not merged/corrupted
    # no leftover temp file
    leftovers = [p for p in (tmp_path / r2.provider / r2.producer_id).iterdir() if ".tmp" in p.name]
    assert leftovers == []


def test_corrupt_receipt_file_reads_as_none(tmp_path):
    path = mdr.receipt_path(tmp_path, "kiwoom", "X", "005930")
    path.parent.mkdir(parents=True)
    path.write_text("not json{{{", encoding="utf-8")
    assert mdr.read_receipt(tmp_path, "kiwoom", "X", "005930") is None


# ---------------------------------------------------------------------------
# raw page bundle (multi-page completeness)
# ---------------------------------------------------------------------------

def test_raw_page_bundle_preserves_order_and_exact_page_text():
    pages = ['{"a":1}', '{"b":2}', '{"c":3}']
    bundle = mdr.raw_page_bundle_bytes(pages)
    decoded = json.loads(bundle.decode("utf-8"))
    assert decoded["pages"] == pages  # exact order, exact text, never re-serialized
    assert decoded["page_count"] == 3
    assert decoded["schema"] == mdr.RAW_PAGE_BUNDLE_SCHEMA


def test_raw_page_bundle_never_mutates_page_contents():
    pages = ['{"weird": "  spacing  ", "unicode": "\\uacf5"}']
    bundle = mdr.raw_page_bundle_bytes(pages)
    decoded = json.loads(bundle.decode("utf-8"))
    assert decoded["pages"][0] == pages[0]  # byte-for-byte, not re-parsed/re-serialized


def test_raw_page_bundle_deterministic():
    pages = ["p1", "p2", "p3"]
    assert mdr.raw_page_bundle_bytes(pages) == mdr.raw_page_bundle_bytes(list(pages))


def test_mutating_one_page_changes_the_bundle_hash():
    pages_a = ["page1", "page2", "page3"]
    pages_b = ["page1", "MUTATED", "page3"]
    ha = hashlib.sha256(mdr.raw_page_bundle_bytes(pages_a)).hexdigest()
    hb = hashlib.sha256(mdr.raw_page_bundle_bytes(pages_b)).hexdigest()
    assert ha != hb


# ---------------------------------------------------------------------------
# raw/normalized atomic publication (no partial visibility)
# ---------------------------------------------------------------------------

def test_raw_publication_leaves_no_temp_file_behind(tmp_path):
    mdr.persist_raw_artifact(tmp_path, "sym/x.raw", b"payload bytes")
    leftovers = [p for p in (tmp_path / "sym").iterdir() if ".tmp." in p.name]
    assert leftovers == []
    assert (tmp_path / "sym" / "x.raw").read_bytes() == b"payload bytes"


def test_raw_publication_final_path_never_partially_written(tmp_path, monkeypatch):
    """The final path is created via `os.link` from a fully-written, fsynced temp file -- simulate a
    reader racing the publish by asserting the final path is only ever created already-complete."""
    seen_sizes = []
    real_link = os.link

    def spying_link(src, dst, *a, **k):
        # at the moment of linking, the temp source must already contain the COMPLETE payload
        seen_sizes.append(os.path.getsize(src))
        return real_link(src, dst, *a, **k)

    monkeypatch.setattr(os, "link", spying_link)
    data = b"x" * 4096
    mdr.persist_raw_artifact(tmp_path, "sym/y.raw", data)
    assert seen_sizes == [len(data)]  # never linked until fully written


def test_normalized_artifact_reuses_same_atomic_no_clobber_semantics(tmp_path):
    """The attested normalized artifact uses the identical `persist_raw_artifact` primitive as raw --
    same idempotent-reuse / hard-conflict semantics, just under a different confined root."""
    data = b'{"schema_version":"kiwoom_historical_minute_cache.v1","symbol":"005930","row_count":0,"rows":[]}'
    d1 = mdr.persist_raw_artifact(tmp_path, "kiwoom/X/005930/n.normalized.json", data)
    d2 = mdr.persist_raw_artifact(tmp_path, "kiwoom/X/005930/n.normalized.json", data)
    assert d1 == d2
    with pytest.raises(mdr.RawArchiveConflictError):
        mdr.persist_raw_artifact(tmp_path, "kiwoom/X/005930/n.normalized.json", b"different bytes")


def test_normalized_content_ref_is_content_addressed():
    ref = mdr.normalized_content_ref(provider="kiwoom", producer_id="X", symbol="005930", normalized_sha256="b" * 64)
    assert ref == "kiwoom/X/005930/" + "b" * 64 + ".normalized.json"
