"""MarketDataReceipt -- shared, UEF-independent market-data provenance contract.

Architecture (UEF-5.2 ADR, see docs/decisions/ADR-0003_*): the acquisition component issues trust
evidence; UEF only ever verifies it, never creates it. This module defines the contract, the
content-addressed raw-archive I/O, and the receipt I/O -- no verification/admission policy lives here
(that is UEF-5.2's responsibility, in `libs/reporting/evaluation/uef5/candle_authority.py`).

Finalization order (enforced by callers, not by this module alone -- see `kiwoom_history.py`):
    1. raw artifact persisted atomically (write-once, no-clobber)
    2. raw bytes re-read and re-hashed
    3. normalization performed
    4. normalized artifact persisted atomically
    5. normalized bytes re-read and re-hashed
    6. receipt written atomically LAST
No receipt may be visible for a partial acquisition -- a caller that fails any earlier step simply
never reaches step 6, so no half-written provenance record can ever exist.

Offline only; deterministic; no clock, no randomness are used by anything in THIS module (callers may
of course record diagnostic wall-clock metadata, which never participates in `receipt_digest`).
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

RECEIPT_SCHEMA = "market_data_receipt.v1"
RAW_PAGE_BUNDLE_SCHEMA = "kiwoom_raw_page_bundle.v1"

# One producer identity for the one real acquisition/normalization implementation in this repository.
# `libs/reporting/opening_rank1_shadow/candle_provider.py` imports and reuses
# `KiwoomHistoricalMinuteReader`/`load_or_fetch_symbol_history` from `kiwoom_history.py` verbatim -- it
# is not a semantically distinct acquisition path, so it is NOT given a separate producer id. A new
# producer id is introduced only if a genuinely different acquisition/normalization implementation is
# ever added -- never merely to decorate a different strategy/Q namespace.
PROVIDER_KIWOOM = "kiwoom"
PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1 = "KIWOOM_HISTORICAL_MINUTE_V1"

_SEMANTIC_FIELDS = (
    "receipt_schema", "provider", "producer_id", "producer_version",
    "symbol", "trading_date", "interval",
    "source_window_start", "source_window_end",
    "raw_payload_sha256", "raw_archive_ref",
    "normalized_candle_sha256",
    "normalizer_id", "normalizer_version", "normalizer_implementation_digest",
    "row_count",
)


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def file_content_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class MarketDataReceipt:
    receipt_schema: str
    provider: str
    producer_id: str
    producer_version: str
    symbol: str
    trading_date: Optional[str]  # may be None when one receipt spans a multi-day acquisition window --
                                  # source_window_start/end are then the authoritative scope (see below)
    interval: str
    source_window_start: int  # inclusive epoch seconds -- the PHYSICAL acquisition scope, never an
    source_window_end: int    # evaluation-session claim (that is SessionPolicy's, separate authority)
    raw_payload_sha256: str
    raw_archive_ref: str
    normalized_candle_sha256: str
    normalizer_id: str
    normalizer_version: str
    normalizer_implementation_digest: str
    row_count: int
    diagnostic: Mapping[str, Any] = field(default_factory=dict)  # never participates in receipt_digest

    def semantic_fields(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in _SEMANTIC_FIELDS}

    def digest(self) -> str:
        return hashlib.sha256(_canonical_json(self.semantic_fields()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        d = self.semantic_fields()
        d["diagnostic"] = dict(self.diagnostic)
        d["receipt_digest"] = self.digest()
        return d

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MarketDataReceipt":
        kwargs = {k: payload.get(k) for k in _SEMANTIC_FIELDS}
        return cls(**kwargs, diagnostic=dict(payload.get("diagnostic") or {}))


# ---------------------------------------------------------------------------
# raw archive: confined root, content-addressed, write-once/no-clobber
# ---------------------------------------------------------------------------

class ArchivePathError(ValueError):
    """`raw_archive_ref` is not a valid, confined reference (absolute, traversal, or root escape)."""


class RawArchiveConflictError(RuntimeError):
    """The archive already holds different bytes at this ref -- never silently overwritten."""


def resolve_archive_path(archive_root: Path, ref: str) -> Path:
    archive_root = Path(archive_root).resolve()
    if not ref or os.path.isabs(ref) or ref.startswith(("/", "\\")):
        raise ArchivePathError(f"raw_archive_ref must be a non-empty relative path: {ref!r}")
    if ".." in Path(ref).parts:
        raise ArchivePathError(f"raw_archive_ref must not contain '..': {ref!r}")
    candidate = (archive_root / ref).resolve()
    try:
        candidate.relative_to(archive_root)
    except ValueError:
        raise ArchivePathError(f"raw_archive_ref escapes the archive root: {ref!r}") from None
    return candidate


def content_addressed_ref(*, provider: str, producer_id: str, symbol: str, raw_sha256: str) -> str:
    """Deterministic ref: same bytes always produce the same ref, so re-acquiring identical raw content
    is naturally idempotent and distinct acquisitions never collide."""
    return f"{provider}/{producer_id}/{symbol}/{raw_sha256}.raw"


def normalized_content_ref(*, provider: str, producer_id: str, symbol: str, normalized_sha256: str) -> str:
    """Content-addressed location of an ATTESTED normalized artifact -- an independently-stored file
    containing ONLY the rows a specific receipt attests, never the legacy convenience merged cache. A
    receipt's own (provider, producer_id, symbol, normalized_candle_sha256) fields deterministically
    resolve to this path with no extra identity field needed."""
    return f"{provider}/{producer_id}/{symbol}/{normalized_sha256}.normalized.json"


def raw_page_bundle_bytes(pages: Sequence[str]) -> bytes:
    """Deterministic, lossless framing of every provider response page that contributed rows to an
    attested normalized artifact. Page ORDER and each page's EXACT text are preserved verbatim (never
    mutated/re-serialized) -- only the outer envelope is canonical JSON, and `sort_keys` never reorders
    the `pages` list itself (JSON arrays are order-preserving)."""
    payload = {"schema": RAW_PAGE_BUNDLE_SCHEMA, "page_count": len(pages), "pages": list(pages)}
    return _canonical_json(payload).encode("utf-8")


def persist_raw_artifact(archive_root: Path, ref: str, data: bytes) -> str:
    """Atomic publish, no-clobber. The complete content is written to a temp file (flushed + fsynced)
    THEN atomically linked into place -- `ref`'s final path is either fully absent or fully complete,
    never partially visible to a concurrent reader. Same path + same content -> idempotent success. Same
    path + different content -> RawArchiveConflictError. Never overwritten in place. (Used for both raw
    provider-response bundles and independently-attested normalized artifacts -- both are immutable,
    content-addressed blobs under a confined root.)"""
    path = resolve_archive_path(archive_root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    if path.is_file():
        existing_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if existing_digest == digest:
            return digest
        raise RawArchiveConflictError(f"{ref}: existing digest {existing_digest} != new digest {digest}")
    tmp = path.parent / f".{path.name}.tmp.{digest[:16]}.{os.getpid()}"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    try:
        os.link(tmp, path)  # atomic create: readers see `path` either absent or fully complete, never partial
    except FileExistsError:
        existing_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if existing_digest != digest:
            raise RawArchiveConflictError(f"{ref}: existing digest {existing_digest} != new digest {digest}") from None
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return digest


def read_raw_artifact(archive_root: Path, ref: str) -> Optional[bytes]:
    try:
        path = resolve_archive_path(archive_root, ref)
    except ArchivePathError:
        return None
    if not path.is_file():
        return None
    return path.read_bytes()


def verify_raw_archive(archive_root: Path, ref: str, expected_sha256: str) -> bool:
    """resolve(ref) -> bytes -> sha256(bytes) == expected_sha256. False on any failure to resolve."""
    data = read_raw_artifact(archive_root, ref)
    if data is None:
        return False
    return hashlib.sha256(data).hexdigest() == expected_sha256


# ---------------------------------------------------------------------------
# receipt I/O: one current receipt per (provider, producer_id, symbol), atomically replaced
# ---------------------------------------------------------------------------

def receipt_path(receipt_root: Path, provider: str, producer_id: str, symbol: str) -> Path:
    return Path(receipt_root) / provider / producer_id / f"{symbol}.json"


def write_receipt(receipt_root: Path, receipt: MarketDataReceipt) -> Path:
    """Atomic whole-record replace (temp file, flushed + fsynced, then `os.replace`). This is the LAST
    step of the acquisition lifecycle -- callers must only reach this after both the raw and normalized
    artifacts are confirmed persisted and re-hash-verified. `os.replace` is an atomic rename at the OS
    level, so `path` is never visible with partial JSON -- either the previous receipt or the complete
    new one. A receipt is a mutable pointer (unlike the immutable content-addressed raw/normalized
    blobs), so replacement -- not no-clobber -- is the correct semantic here; the content it points to
    can never be corrupted by a stale reference because raw/normalized identity is content-addressed."""
    path = receipt_path(receipt_root, receipt.provider, receipt.producer_id, receipt.symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(receipt.to_dict(), sort_keys=True, ensure_ascii=True, indent=2) + "\n"
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


def read_receipt(receipt_root: Path, provider: str, producer_id: str, symbol: str) -> Optional[MarketDataReceipt]:
    path = receipt_path(receipt_root, provider, producer_id, symbol)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        return MarketDataReceipt.from_dict(payload)
    except TypeError:
        return None


__all__ = [
    "ArchivePathError", "MarketDataReceipt", "PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1", "PROVIDER_KIWOOM",
    "RAW_PAGE_BUNDLE_SCHEMA", "RECEIPT_SCHEMA", "RawArchiveConflictError", "content_addressed_ref",
    "file_content_sha256", "normalized_content_ref", "persist_raw_artifact", "raw_page_bundle_bytes",
    "read_raw_artifact", "read_receipt", "receipt_path", "resolve_archive_path", "verify_raw_archive",
    "write_receipt",
]
