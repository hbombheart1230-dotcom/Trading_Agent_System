"""UEF-5.2 -- secondary-input (minute candle) authority verifier: architecture-approved remediation
(Correction 1: closes the legacy-cache-contamination and source-window-leakage defects Codex found in
the first implementation).

NO SOURCE AUTHORITY -> NO CANONICAL CLAIM. UNPROVEN SOURCE -> BLOCK.

CORE AUTHORITY INVARIANT: a normalized candle row may receive `FULL_SOURCE_AUTHORITY` IFF that exact row
is proven to derive from raw material represented by the verified `MarketDataReceipt` -- never merely
because it lives in a file that happens to share a symbol/date, or in a cache that has been merged with
attested data. Concretely this admission ONLY ever reads rows from the independently-stored, receipt-
bound ATTESTED NORMALIZED ARTIFACT (`libs.market_data.receipts.normalized_content_ref`, content-addressed
by `receipt.normalized_candle_sha256`) -- never from the legacy convenience merged cache a symbol's
on-disk research directory may also contain. That legacy cache is never resolved, hashed, or read by
anything in this module; it plays no role in admission, so a fresh receipt can never retroactively
attest pre-existing unattested rows merely by having been merged into the same file on disk.

Per the approved architecture (docs/decisions/ADR-0003_*): the acquisition component issues trust
evidence; UEF only ever VERIFIES it. There is no boolean "trust me" flag anywhere in this module --
`FULL_SOURCE_AUTHORITY` is reachable only by `verify_receipt_bound_candles` succeeding against a real,
resolvable, hash-matching receipt AND every individual row actually falling within the receipt's own
attested acquisition scope (row-level, never day-level overlap -- one out-of-scope row fails the whole
unit closed). Production and tests exercise the identical path; tests construct real receipts and real
attested artifacts under a temporary root, never a bypass.

Two dimensions stay explicitly separate:
- `structural_status`  (VALID / INVALID): the ATTESTED ARTIFACT's own internal well-formedness (schema,
  symbol, row_count, ts/raw_ts, ordering, 60s grid, duplicates, OHLC relations, volume).
- `provenance_status`  (FULL_SOURCE_AUTHORITY / NOT_PROVEN / INVALID): what a verified `MarketDataReceipt`
  actually proves about where the bytes came from.
`admitted` (structural VALID AND provenance FULL_SOURCE_AUTHORITY) is the only gate a pipeline may use.

Anchor comparison against a CLEAN primary artifact's own persisted checkpoints (Fix1's finding: it is
MATERIALLY INSUFFICIENT on its own, since intermediate bars carry no independent corroboration) is kept
as a `corroboration` diagnostic only -- it never gates admission and never appears in `reason`.

Offline only; deterministic; no clock, no randomness, no network.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from libs.market_data import receipts as mdr
from libs.reporting.evaluation.canonical.forward.engine import _is_valid_price  # frozen UEF-2B price validity (read-only)

VERIFIER_ID = "uef5_2.candle_authority.receipt_verified.v3"
EXPECTED_SCHEMA = "kiwoom_historical_minute_cache.v1"
MINUTE_GRID_SECONDS = 60
KST = timezone(timedelta(hours=9))

# The one recognized (provider, producer_id) pair, matching libs.market_data.receipts' own constants --
# a new pair is added only if a genuinely different acquisition/normalization implementation is ever
# built, never for per-strategy/Q decoration (see receipts.py's own docstring on this).
RECOGNIZED_PROVIDERS = frozenset({mdr.PROVIDER_KIWOOM})
RECOGNIZED_PRODUCERS = frozenset({mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1})
RECOGNIZED_RECEIPT_SCHEMAS = frozenset({mdr.RECEIPT_SCHEMA})

AUTHORITY_BASIS = (
    "structural validity is necessary but never sufficient for admission; anchor corroboration of the "
    "primary artifact's own persisted checkpoints is diagnostic only (intermediate bars are uncorroborated "
    "and materially affect MFE/MAE/aggregates); FULL_SOURCE_AUTHORITY is reachable only through a "
    "verified MarketDataReceipt (raw archive resolves and hash-matches, normalized artifact hash-matches, "
    "recognized provider/producer/schema, normalizer identity present, acquisition scope covers the day) "
    "-- no caller boolean and no data-plausibility inference can grant it"
)

# Stable reason strings (mapped to historical_recompute.Reason by the runner).
R_MISSING_INPUT = "MISSING_REQUIRED_SOURCE_INPUT"
R_AUTHORITY_NOT_PROVEN = "SECONDARY_INPUT_AUTHORITY_NOT_PROVEN"
R_RECEIPT_INVALID = "SECONDARY_INPUT_RECEIPT_INVALID"
R_SCHEMA = "SECONDARY_INPUT_SCHEMA_INVALID"
R_SYMBOL = "SECONDARY_INPUT_SYMBOL_MISMATCH"
R_TIMESTAMP = "SECONDARY_INPUT_TIMESTAMP_INVALID"
R_VALUE = "SECONDARY_INPUT_VALUE_INVALID"
R_OHLC = "SECONDARY_INPUT_OHLC_INVALID"
R_HASH = "SECONDARY_INPUT_HASH_MISMATCH"
R_SOURCE_SCOPE_VIOLATION = "SECONDARY_INPUT_SOURCE_SCOPE_VIOLATION"


class StructuralStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"


class ProvenanceStatus(str, Enum):
    FULL_SOURCE_AUTHORITY = "FULL_SOURCE_AUTHORITY"
    NOT_PROVEN = "NOT_PROVEN"
    INVALID = "INVALID"


@dataclass(frozen=True)
class Anchor:
    """One persisted fact of the primary artifact the candle file is compared against -- DIAGNOSTIC
    ONLY, never gates admission. Identity is by `epoch` when the source persisted an epoch, else by
    `raw_ts` (both real legacy artifact shapes occur in this repo)."""
    epoch: Optional[int]
    raw_ts: str
    close: float
    source: str

    def __post_init__(self) -> None:
        if self.epoch is None and not self.raw_ts:
            raise ValueError("Anchor requires at least one of epoch/raw_ts")

    def as_dict(self) -> dict[str, Any]:
        return {"epoch": self.epoch, "raw_ts": self.raw_ts, "close": self.close, "source": self.source}


@dataclass(frozen=True)
class VerifiedCandleInput:
    path: str
    sha256: Optional[str]
    symbol: str
    trading_date: str
    structural_status: StructuralStatus
    provenance_status: ProvenanceStatus
    reason: Optional[str]  # None only when admitted
    detail: str
    row_scope: Mapping[str, Any] = field(default_factory=dict)
    corroboration: Mapping[str, Any] = field(default_factory=dict)  # diagnostic only
    receipt_digest: Optional[str] = None
    receipt: Optional[mdr.MarketDataReceipt] = None
    verifier_id: str = VERIFIER_ID

    @property
    def admitted(self) -> bool:
        return self.structural_status is StructuralStatus.VALID and self.provenance_status is ProvenanceStatus.FULL_SOURCE_AUTHORITY

    def to_dict(self) -> dict[str, Any]:
        return {
            "attested_artifact_ref": self.path, "attested_artifact_sha256": self.sha256,
            "symbol": self.symbol, "trading_date": self.trading_date,
            "secondary_input_verifier_id": self.verifier_id,
            "structural_status": self.structural_status.value, "provenance_status": self.provenance_status.value,
            "reason_code": self.reason, "detail": self.detail,
            "required_row_scope": dict(self.row_scope), "corroboration": dict(self.corroboration),
            "receipt_digest": self.receipt_digest, "authority_basis": AUTHORITY_BASIS,
        }


def read_bytes_once(path: Path) -> tuple[Optional[bytes], Optional[str]]:
    """The single read the whole pipeline consumes: bytes + their sha256 (parse THESE bytes, never re-read)."""
    if not path.is_file():
        return None, None
    data = path.read_bytes()
    return data, hashlib.sha256(data).hexdigest()


def kst_date(ts: int) -> str:
    return datetime.fromtimestamp(ts, KST).strftime("%Y-%m-%d")


def _raw_to_epoch(raw: Any) -> Optional[int]:
    if not isinstance(raw, str) or len(raw) != 14 or not raw.isdigit():
        return None
    try:
        return int(datetime.strptime(raw, "%Y%m%d%H%M%S").replace(tzinfo=KST).timestamp())
    except ValueError:
        return None


def _fail(rel, sha, symbol, day, structural, provenance, reason, detail, scope=None, corrob=None, receipt_digest=None) -> VerifiedCandleInput:
    return VerifiedCandleInput(rel, sha, symbol, day, structural, provenance, reason, detail, scope or {}, corrob or {}, receipt_digest)


def verify_structure(
    data: Optional[bytes], sha256: Optional[str], *, rel: str, symbol: str, day: str,
) -> tuple[StructuralStatus, Optional[str], str, dict[str, Any], list[dict[str, Any]]]:
    """Structural well-formedness only -- never resolves provenance. Returns
    (structural_status, reason_if_invalid, detail, row_scope, day_rows). `day_rows` is populated
    whenever the file is structurally VALID and has rows for `day` (release of rows to a pipeline is
    still gated separately by receipt verification -- see `verify_receipt_bound_candles`)."""
    if data is None:
        return StructuralStatus.INVALID, R_MISSING_INPUT, "candle file absent", {}, []
    try:
        payload = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        return StructuralStatus.INVALID, R_SCHEMA, f"unparseable ({type(exc).__name__})", {}, []
    if not isinstance(payload, dict) or payload.get("schema_version") != EXPECTED_SCHEMA or not isinstance(payload.get("rows"), list):
        return StructuralStatus.INVALID, R_SCHEMA, "schema_version/rows not the persisted minute-cache contract", {}, []
    # `rel` may be a content-addressed ref (e.g. "<hash>.normalized.json"), not "{symbol}.json" -- the
    # caller (`verify_receipt_bound_candles`) already confirms `receipt.symbol == symbol` before this is
    # reached, so the ONLY symbol check that still makes sense here is the artifact's OWN declared payload.
    if payload.get("symbol") != symbol:
        return StructuralStatus.INVALID, R_SYMBOL, f"expected {symbol}; payload={payload.get('symbol')!r}", {}, []
    if payload.get("row_count") != len(payload["rows"]):
        return StructuralStatus.INVALID, R_SCHEMA, "row_count does not match rows", {}, []

    seen: dict[int, dict[str, Any]] = {}
    previous = None
    for i, row in enumerate(payload["rows"]):
        if not isinstance(row, dict):
            return StructuralStatus.INVALID, R_SCHEMA, f"row {i} is not an object", {}, []
        ts = row.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, int) or ts <= 0:
            return StructuralStatus.INVALID, R_TIMESTAMP, f"row {i}: ts not a positive integer", {}, []
        if ts % MINUTE_GRID_SECONDS != 0:
            return StructuralStatus.INVALID, R_TIMESTAMP, f"row {i}: ts {ts} is off the 60s minute grid", {}, []
        if _raw_to_epoch(row.get("raw_ts")) != ts:
            return StructuralStatus.INVALID, R_TIMESTAMP, f"row {i}: raw_ts does not equal ts (KST)", {}, []
        if previous is not None and ts < previous:
            return StructuralStatus.INVALID, R_TIMESTAMP, f"row {i}: timestamps not ordered", {}, []
        previous = ts
        if ts in seen:
            if seen[ts] != row:  # frozen UEF-2B: identical repeat is harmless, differing repeat is ambiguous
                return StructuralStatus.INVALID, R_TIMESTAMP, f"row {i}: ambiguous duplicate ts {ts}", {}, []
            continue
        for key in ("open", "high", "low", "close"):
            if not _is_valid_price(row.get(key)):
                return StructuralStatus.INVALID, R_VALUE, f"row {i}: {key} not a finite positive price", {}, []
        o, h, lo, c = (float(row[k]) for k in ("open", "high", "low", "close"))
        if not (h >= o and h >= c and h >= lo and lo <= o and lo <= c):
            return StructuralStatus.INVALID, R_OHLC, f"row {i}: OHLC relation violated (open={o} high={h} low={lo} close={c})", {}, []
        vol = row.get("volume")
        if isinstance(vol, bool) or not isinstance(vol, (int, float)) or not math.isfinite(vol) or vol < 0:
            return StructuralStatus.INVALID, R_VALUE, f"row {i}: volume not finite and non-negative", {}, []
        seen[ts] = row

    day_rows = [r for r in payload["rows"] if kst_date(r["ts"]) == day]
    if not day_rows:
        return StructuralStatus.VALID, R_MISSING_INPUT, f"no rows for {day} in this file", {"trading_date": day}, []
    scope = {"trading_date": day, "row_count": len(day_rows), "first_ts": day_rows[0]["ts"], "last_ts": day_rows[-1]["ts"],
             "first_raw_ts": day_rows[0]["raw_ts"], "last_raw_ts": day_rows[-1]["raw_ts"]}
    return StructuralStatus.VALID, None, "structurally valid", scope, day_rows


def _receipt_recognized(receipt: mdr.MarketDataReceipt, symbol: str) -> tuple[Optional[ProvenanceStatus], Optional[str], str]:
    """Field-level receipt checks that do not require touching any file. Returns `(None, None, "")` when
    all pass; otherwise the terminal (status, reason, detail)."""
    if receipt.receipt_schema not in RECOGNIZED_RECEIPT_SCHEMAS:
        return ProvenanceStatus.INVALID, R_RECEIPT_INVALID, f"unrecognized receipt_schema {receipt.receipt_schema!r}"
    if receipt.provider not in RECOGNIZED_PROVIDERS or receipt.producer_id not in RECOGNIZED_PRODUCERS:
        return ProvenanceStatus.NOT_PROVEN, R_AUTHORITY_NOT_PROVEN, \
            f"unrecognized provider/producer {receipt.provider!r}/{receipt.producer_id!r}"
    if receipt.symbol != symbol:
        return ProvenanceStatus.INVALID, R_RECEIPT_INVALID, f"receipt symbol {receipt.symbol!r} != {symbol!r}"
    if not receipt.normalizer_id or not receipt.normalizer_version or not receipt.normalizer_implementation_digest:
        return ProvenanceStatus.NOT_PROVEN, R_AUTHORITY_NOT_PROVEN, "receipt carries no normalizer identity"
    if receipt.row_count <= 0:
        return ProvenanceStatus.NOT_PROVEN, R_AUTHORITY_NOT_PROVEN, "receipt.row_count is not positive"
    return None, None, ""


def verify_receipt_bound_candles(
    receipt: Optional[mdr.MarketDataReceipt], *, symbol: str, day: str, anchors: Sequence[Anchor],
    archive_root: Optional[Path], normalized_root: Optional[Path],
) -> tuple[VerifiedCandleInput, list[dict[str, Any]]]:
    """The one entrypoint a pipeline uses. Structural gate order (architecture Section 14):
    receipt field checks -> raw archive resolves+hash-matches -> the ATTESTED NORMALIZED ARTIFACT
    (never the legacy convenience cache) resolves+hash-matches -> its own structural validity ->
    EVERY consumed row individually within the receipt's own source window -> admitted.

    Never reads, hashes, or otherwise consults any file at a "legacy cache" path -- the attested
    artifact is located solely via `mdr.normalized_content_ref(receipt.provider, receipt.producer_id,
    symbol, receipt.normalized_candle_sha256)`, so a receipt can only ever attest the rows an
    acquisition itself persisted there, never rows that merely happen to sit in the same merged file on
    disk (closes the legacy-cache-contamination defect)."""
    ref = mdr.normalized_content_ref(provider=receipt.provider, producer_id=receipt.producer_id, symbol=symbol,
                                     normalized_sha256=receipt.normalized_candle_sha256) if receipt is not None else ""
    if receipt is None:
        return _fail(ref, None, symbol, day, StructuralStatus.INVALID, ProvenanceStatus.NOT_PROVEN,
                     R_AUTHORITY_NOT_PROVEN, f"no MarketDataReceipt found for {symbol}"), []
    status, reason, detail = _receipt_recognized(receipt, symbol)
    if status is not None:
        return _fail(ref, None, symbol, day, StructuralStatus.INVALID, status, reason, detail, receipt_digest=receipt.digest()), []
    if archive_root is None:
        return _fail(ref, None, symbol, day, StructuralStatus.INVALID, ProvenanceStatus.NOT_PROVEN, R_AUTHORITY_NOT_PROVEN,
                     "no raw archive root configured to resolve the receipt against", receipt_digest=receipt.digest()), []
    raw_bytes = mdr.read_raw_artifact(archive_root, receipt.raw_archive_ref)
    if raw_bytes is None:
        return _fail(ref, None, symbol, day, StructuralStatus.INVALID, ProvenanceStatus.NOT_PROVEN, R_AUTHORITY_NOT_PROVEN,
                     f"raw_archive_ref {receipt.raw_archive_ref!r} does not resolve", receipt_digest=receipt.digest()), []
    if hashlib.sha256(raw_bytes).hexdigest() != receipt.raw_payload_sha256:
        return _fail(ref, None, symbol, day, StructuralStatus.INVALID, ProvenanceStatus.INVALID, R_RECEIPT_INVALID,
                     "raw archive bytes do not match receipt.raw_payload_sha256", receipt_digest=receipt.digest()), []
    if normalized_root is None:
        return _fail(ref, None, symbol, day, StructuralStatus.INVALID, ProvenanceStatus.NOT_PROVEN, R_AUTHORITY_NOT_PROVEN,
                     "no attested-normalized-artifact root configured", receipt_digest=receipt.digest()), []
    data = mdr.read_raw_artifact(normalized_root, ref)
    if data is None:
        return _fail(ref, None, symbol, day, StructuralStatus.INVALID, ProvenanceStatus.NOT_PROVEN, R_AUTHORITY_NOT_PROVEN,
                     f"attested normalized artifact {ref!r} does not resolve", receipt_digest=receipt.digest()), []
    sha256 = hashlib.sha256(data).hexdigest()
    if sha256 != receipt.normalized_candle_sha256:
        return _fail(ref, sha256, symbol, day, StructuralStatus.INVALID, ProvenanceStatus.INVALID, R_RECEIPT_INVALID,
                     "attested normalized artifact bytes do not match receipt.normalized_candle_sha256", receipt_digest=receipt.digest()), []

    structural, s_reason, s_detail, scope, day_rows = verify_structure(data, sha256, rel=ref, symbol=symbol, day=day)
    if structural is not StructuralStatus.VALID:
        return _fail(ref, sha256, symbol, day, structural, ProvenanceStatus.INVALID, s_reason, s_detail,
                     receipt_digest=receipt.digest()), []
    if not day_rows:  # the attested artifact is fine but has nothing for this specific day
        return _fail(ref, sha256, symbol, day, StructuralStatus.VALID, ProvenanceStatus.NOT_PROVEN, s_reason, s_detail,
                     scope, receipt_digest=receipt.digest()), []

    # Row-level source-scope check (never day-level overlap): EVERY consumed row must individually fall
    # within the receipt's own attested acquisition window. One row outside it fails the whole unit closed.
    out_of_scope = [r["ts"] for r in day_rows if not (receipt.source_window_start <= r["ts"] <= receipt.source_window_end)]
    if out_of_scope:
        return _fail(ref, sha256, symbol, day, StructuralStatus.VALID, ProvenanceStatus.NOT_PROVEN, R_SOURCE_SCOPE_VIOLATION,
                     f"{len(out_of_scope)} row(s) outside receipt source window "
                     f"[{receipt.source_window_start},{receipt.source_window_end}]: first={out_of_scope[0]}",
                     scope, receipt_digest=receipt.digest()), []

    corrob = _corroborate(day_rows, anchors)
    result = VerifiedCandleInput(ref, sha256, symbol, day, StructuralStatus.VALID, ProvenanceStatus.FULL_SOURCE_AUTHORITY,
                                 None, "receipt verified: raw archive and attested normalized artifact both hash-match, "
                                 "every consumed row within the receipt's own source window",
                                 scope, corrob, receipt.digest(), receipt)
    return result, day_rows


def _corroborate(day_rows: Sequence[Mapping[str, Any]], anchors: Sequence[Anchor]) -> dict[str, Any]:
    by_ts = {r["ts"]: r for r in day_rows}
    by_raw = {r["raw_ts"]: r for r in day_rows}
    matched = mismatched = missing = 0
    for a in anchors:
        row = by_ts.get(a.epoch) if a.epoch is not None else by_raw.get(a.raw_ts)
        if row is None:
            missing += 1
        elif row["close"] == a.close:
            matched += 1
        else:
            mismatched += 1
    status = "NO_ANCHORS" if not anchors else "CONTRADICTED" if mismatched else "MATCHED" if matched and not missing else (
        "INCOMPLETE" if matched else "NO_ANCHORS")
    return {"anchor_count": len(anchors), "anchor_matches": matched, "anchor_mismatches": mismatched,
            "anchor_missing": missing, "status": status}


def q10_semiconductor_anchors(forward_payload: Mapping[str, Any], symbol: str) -> list[Anchor]:
    """Every price fact the CLEAN Q10 Semi / Q12 Calc1 primary artifact persisted for `symbol` (both share
    the identical `rows[].{baseline,returns}` shape), in deterministic order. Diagnostic use only."""
    out: list[Anchor] = []
    for row in forward_payload.get("rows") or []:
        if not isinstance(row, Mapping) or row.get("symbol") != symbol:
            continue
        base = row.get("baseline")
        if isinstance(base, Mapping) and base.get("available"):
            epoch, raw, price = base.get("baseline_epoch"), base.get("baseline_raw_ts"), base.get("baseline_price")
            if isinstance(epoch, int) and isinstance(raw, str) and _is_valid_price(price):
                out.append(Anchor(epoch, raw, float(price), "baseline"))
        for label, ret in sorted((row.get("returns") or {}).items()):
            if isinstance(ret, Mapping) and ret.get("status") == "observed":
                raw, price = ret.get("observed_ts"), ret.get("price")
                if isinstance(raw, str) and _is_valid_price(price):
                    out.append(Anchor(None, raw, float(price), str(label)))
    return _dedupe_anchors(out)


def q12_calc2_anchors(payload: Mapping[str, Any]) -> list[Anchor]:
    """Every price fact the CLEAN Calc2 primary artifact persisted (epoch-keyed, no raw_ts -- a different
    legacy shape than Calc1/Q10 Semi). Diagnostic use only."""
    out: list[Anchor] = []
    for method, outcome in sorted((payload.get("entry_outcomes") or {}).items()):
        if not isinstance(outcome, Mapping) or outcome.get("status") != "OBSERVED":
            continue
        epoch, price = outcome.get("entry_epoch"), outcome.get("entry_price")
        if isinstance(epoch, int) and _is_valid_price(price):
            out.append(Anchor(epoch, "", float(price), f"entry:{method}"))
        for label, ret in sorted((outcome.get("returns") or {}).items()):
            if isinstance(ret, Mapping) and ret.get("status") == "OBSERVED":
                oep, oprice = ret.get("observed_epoch"), ret.get("observed_price")
                if isinstance(oep, int) and _is_valid_price(oprice):
                    out.append(Anchor(oep, "", float(oprice), f"entry:{method}:{label}"))
    return _dedupe_anchors(out)


def _dedupe_anchors(anchors: Sequence[Anchor]) -> list[Anchor]:
    dedup: dict[tuple[Any, ...], Anchor] = {}
    for a in anchors:
        dedup[(a.epoch, a.raw_ts, a.close, a.source)] = a
    return sorted(dedup.values(), key=lambda a: (a.raw_ts, a.epoch or 0, a.source))


__all__ = [
    "Anchor", "AUTHORITY_BASIS", "ProvenanceStatus", "RECOGNIZED_PRODUCERS", "RECOGNIZED_PROVIDERS",
    "RECOGNIZED_RECEIPT_SCHEMAS", "StructuralStatus", "VERIFIER_ID", "VerifiedCandleInput",
    "q10_semiconductor_anchors", "q12_calc2_anchors", "read_bytes_once", "verify_receipt_bound_candles",
    "verify_structure", "kst_date", "R_SOURCE_SCOPE_VIOLATION",
]
