"""UEF-5.2 canonical historical recompute runner.

Question answered: "What does the frozen UEF produce when applied to
admissible historical evidence?" It does NOT compare against legacy results
(UEF-5.3) and declares no parity.

Pipeline, per discovered source artifact:

    UEF-5.1 registry resolution (positive proof, record-level rules)
      + UEF adapter eligibility (independent fact; BLOCKED always wins)
      + required-field usability (FIELD_INVALID intersecting the fields the
        adapter needs => fail closed)
      -> approved UEF-4 adapter -> canonical EpisodeRecord(s)
      -> frozen UEF-3C aggregation -> canonical AggregateRecord(s)

Every discovered artifact ends in exactly ONE accounting bucket; nothing
disappears. Outputs live in a NEW namespace and never overwrite legacy reports.

Scope decisions (documented in docs/research/uef5_2_historical_recompute.md):
  * Aggregates are PER DAY. Legacy cost is day-varying (persisted cost_model),
    UEF-3C needs one CostPolicy per context, and no cross-day cost is invented.
  * GROSS_ONLY families get a CostPolicy built ONLY from the artifact's own
    persisted cost_model (drag = round_trip_cost_pct + slippage_pct, exactly the
    legacy sum, applied once inside the frozen engine). Q10 Index F/G persist no
    cost model, so they get an explicit zero-cost policy; NET_OR_COST_INCLUDED
    families get none and are never re-costed.
  * Candle inputs are read from two enumerated on-disk research caches, each
    file hashed into the input manifest. Missing candles => explicit
    SKIPPED_MISSING_INPUT, never a fabricated or zero-filled series.
  * Architecture-approved remediation (docs/decisions/ADR-0003_*): candle admission requires a
    verified `libs.market_data.receipts.MarketDataReceipt` (acquisition issues trust evidence; UEF
    only ever verifies it -- no caller boolean can grant FULL_SOURCE_AUTHORITY). A separate,
    UEF-owned `SessionPolicy` (09:00-15:30 KST) projects admitted candles to the canonical regular
    session before any frozen adapter call; a row outside it (e.g. 15:35) cannot affect
    LAST_AVAILABLE/EOD/MFE/MAE. The run id binds a bounded, explicit semantic implementation manifest
    (this orchestrator + the receipt/session verifiers + the UEF-5.1 registry modules + the exact
    UEF-4 adapters used + the frozen-core manifest digest) plus the effective run configuration.

Offline only: imports frozen canonical modules and UEF-5.1; nothing in
production/runtime imports this module. No wall-clock, no randomness.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from libs.reporting.evaluation.canonical.adapters import (
    forward_measurement_adapter as fma,
    hypothesis_forward_adapter as q12c2,
    q10_index_directional_shadow_adapter as q10h,
    q10_index_reaction_adapter as q10fg,
    q10_semiconductor as q10s,
    q12_baseline_btc_woori as q12c1,
    virtual_probe_adapter as q11,
)
from libs.reporting.evaluation.canonical.contracts import ReturnUnit
from libs.reporting.evaluation.canonical.identity import (
    build_event_ref,
    evaluation_record_id as _evaluation_record_id,
    evaluation_subject_id as _evaluation_subject_id,
)
from libs.reporting.evaluation.canonical.metrics import CostPolicy, MetricAggregationContext, MetricPolicy
from libs.reporting.evaluation.canonical.metrics.aggregation import (
    CanonicalSampleBatch,
    SampleMemberState,
    aggregate_canonical_samples,
)
from libs.reporting.evaluation.canonical.metrics.contracts import CostTiming
from libs.reporting.evaluation.canonical.record import AggregateIdentity, AggregateRecord, EpisodeRecord

from libs.market_data import receipts as mdr

from . import candle_authority as ca
from . import session_policy as sp
from . import clean_evidence_rules as rules
from .clean_evidence_coverage import (
    DEFAULT_FAMILIES,
    DEFAULT_MAX_PARSE_BYTES,
    FamilySpec,
    _discover,
    _file_descriptor,
    _load_payload,
    _record_descriptors,
    _run_verifiers,
    _spec_accepts,
    build_repo_registry,
)
from .clean_evidence_registry import EvidenceRegistry, EvidenceStatus, canonical_json, resolve_evidence_status

RECOMPUTE_SCHEMA_VERSION = "uef5_2_historical_recompute.v1"
RECOMPUTE_VERSION = "uef5_2.2026-09-28.v3"
OUTPUT_NAMESPACE = "reports/evaluation/uef5/historical_recompute"
KST = timezone(timedelta(hours=9))

CANDLE_SOURCE_DIRS = (
    "data/research/post_reclaim_alpha/minute_cache",
    "data/research/opening_rank1_shadow/minute_cache",
)
ELIGIBLE_ADAPTER_STATUSES = frozenset({"APPROVED_FROZEN", "PROVISIONAL_AWAITING_RATIFICATION"})
_AGG_NAMESPACE = "uef5_2_historical_recompute"
_Q10_INDEX_FILES = (
    "q10_actual_market_reactions.json",
    "q10_expected_vs_actual.json",
    "q10_shadow_entry_comparison.json",
)
_Q11_HORIZONS = ("+5m", "+15m", "+30m", "+60m", "EOD", "EXIT")
_Q10_H_EXCLUSION_NOTE = (
    "q10_index_calc_h: a NEUTRAL expected direction (direction 0) has no directional shadow entry and is "
    "excluded from the population for every entry policy by the approved adapter's own policy"
)


# ---------------------------------------------------------------------------
# status / bucket / reason vocabulary (stable strings)
# ---------------------------------------------------------------------------

class RunStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class Bucket(str, Enum):
    RECOMPUTED = "recomputed"
    SKIPPED_REGISTRY = "skipped_registry"
    SKIPPED_ADAPTER_BLOCKED = "skipped_adapter_blocked"
    SKIPPED_INVALID_REQUIRED_FIELD = "skipped_invalid_required_field"
    SKIPPED_MISSING_INPUT = "skipped_missing_input"
    BLOCKED_SECONDARY_AUTHORITY = "blocked_secondary_authority"
    SKIPPED_NOT_IMPLEMENTED = "skipped_not_implemented"
    PARSE_FAILURE = "parse_failures"
    ADAPTER_FAILURE = "adapter_failures"
    IDENTITY_COLLISION = "identity_collisions"


class Reason(str, Enum):
    REGISTRY_NOT_CLEAN = "REGISTRY_NOT_CLEAN"
    REGISTRY_QUARANTINED = "REGISTRY_QUARANTINED"
    REGISTRY_REVIEW_REQUIRED = "REGISTRY_REVIEW_REQUIRED"
    REGISTRY_NO_RULE = "REGISTRY_NO_RULE"
    REGISTRY_UNIT_INCOMPLETE = "REGISTRY_UNIT_INCOMPLETE"
    ADAPTER_BLOCKED = "ADAPTER_BLOCKED"
    REQUIRED_FIELD_INVALID = "REQUIRED_FIELD_INVALID"
    MISSING_REQUIRED_SOURCE_INPUT = "MISSING_REQUIRED_SOURCE_INPUT"
    SECONDARY_INPUT_AUTHORITY_NOT_PROVEN = "SECONDARY_INPUT_AUTHORITY_NOT_PROVEN"
    SECONDARY_INPUT_SCHEMA_INVALID = "SECONDARY_INPUT_SCHEMA_INVALID"
    SECONDARY_INPUT_SYMBOL_MISMATCH = "SECONDARY_INPUT_SYMBOL_MISMATCH"
    SECONDARY_INPUT_TIMESTAMP_INVALID = "SECONDARY_INPUT_TIMESTAMP_INVALID"
    SECONDARY_INPUT_VALUE_INVALID = "SECONDARY_INPUT_VALUE_INVALID"
    SECONDARY_INPUT_OHLC_INVALID = "SECONDARY_INPUT_OHLC_INVALID"
    SECONDARY_INPUT_RECEIPT_INVALID = "SECONDARY_INPUT_RECEIPT_INVALID"
    SECONDARY_INPUT_HASH_MISMATCH = "SECONDARY_INPUT_HASH_MISMATCH"
    SECONDARY_INPUT_SOURCE_SCOPE_VIOLATION = "SECONDARY_INPUT_SOURCE_SCOPE_VIOLATION"
    MISSING_AUTHORITATIVE_COST_POLICY = "MISSING_AUTHORITATIVE_COST_POLICY"
    COMPANION_ARTIFACT_MISSING = "COMPANION_ARTIFACT_MISSING"
    COMPANION_LINKAGE_MISMATCH = "COMPANION_LINKAGE_MISMATCH"
    UNEXPECTED_SOURCE_SCHEMA = "UNEXPECTED_SOURCE_SCHEMA"
    SOURCE_FILE_CHANGED = "SOURCE_FILE_CHANGED"
    PARSE_FAILURE = "PARSE_FAILURE"
    ADAPTER_FAILURE = "ADAPTER_FAILURE"
    CANONICAL_VALIDATION_FAILURE = "CANONICAL_VALIDATION_FAILURE"
    CANDLE_SOURCE_CONFLICT = "CANDLE_SOURCE_CONFLICT"
    CANONICAL_IDENTITY_COLLISION = "CANONICAL_IDENTITY_COLLISION"
    SERIALIZATION_FAILURE = "SERIALIZATION_FAILURE"
    PIPELINE_NOT_IMPLEMENTED = "PIPELINE_NOT_IMPLEMENTED"


class RecomputeError(Exception):
    reason: Reason = Reason.ADAPTER_FAILURE
    bucket: Bucket = Bucket.ADAPTER_FAILURE


class RegistryNotUsableError(RecomputeError):
    reason, bucket = Reason.REGISTRY_NOT_CLEAN, Bucket.SKIPPED_REGISTRY


class AdapterBlockedError(RecomputeError):
    reason, bucket = Reason.ADAPTER_BLOCKED, Bucket.SKIPPED_ADAPTER_BLOCKED


class MissingRequiredSourceFieldError(RecomputeError):
    reason, bucket = Reason.MISSING_REQUIRED_SOURCE_INPUT, Bucket.SKIPPED_MISSING_INPUT


class CompanionArtifactMissingError(MissingRequiredSourceFieldError):
    reason = Reason.COMPANION_ARTIFACT_MISSING


class CompanionLinkageError(RecomputeError):
    reason, bucket = Reason.COMPANION_LINKAGE_MISMATCH, Bucket.PARSE_FAILURE


class UnexpectedSourceSchemaError(RecomputeError):
    reason, bucket = Reason.UNEXPECTED_SOURCE_SCHEMA, Bucket.PARSE_FAILURE


class SourceFileChangedError(RecomputeError):
    reason, bucket = Reason.SOURCE_FILE_CHANGED, Bucket.PARSE_FAILURE


class CanonicalValidationError(RecomputeError):
    reason, bucket = Reason.CANONICAL_VALIDATION_FAILURE, Bucket.ADAPTER_FAILURE


class SecondaryInputAuthorityError(RecomputeError):
    """A secondary (candle) input lacks positive source authority -- the adapter is never called."""
    reason, bucket = Reason.SECONDARY_INPUT_AUTHORITY_NOT_PROVEN, Bucket.BLOCKED_SECONDARY_AUTHORITY

    def __init__(self, message: str, reason: Optional[Reason] = None, bucket: Optional[Bucket] = None) -> None:
        super().__init__(message)
        if reason is not None:
            self.reason = reason
        if bucket is not None:
            self.bucket = bucket


class CandleSourceConflictError(SecondaryInputAuthorityError):
    reason = Reason.CANDLE_SOURCE_CONFLICT


class PipelineNotImplementedError(RecomputeError):
    reason, bucket = Reason.PIPELINE_NOT_IMPLEMENTED, Bucket.SKIPPED_NOT_IMPLEMENTED


class CanonicalIdentityCollisionError(RecomputeError):
    reason, bucket = Reason.CANONICAL_IDENTITY_COLLISION, Bucket.IDENTITY_COLLISION


class RecomputeSerializationError(RecomputeError):
    reason, bucket = Reason.SERIALIZATION_FAILURE, Bucket.ADAPTER_FAILURE


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UnexpectedSourceSchemaError(f"cannot parse {path.name}: {type(exc).__name__}") from exc


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _kst_date(ts: Any) -> Optional[str]:
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=KST).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def cost_policy_from_persisted_cost_model(cost_model: Any, *, provenance: str) -> CostPolicy:
    """The legacy drag is `round_trip_cost_pct + slippage_pct` (a plain sum), which is
    exactly `CostPolicy.total_cost`. The round-trip figure is a conservative
    commission+tax profile that is not decomposed in the artifact, so it is carried as
    `other_cost` (no split invented) and applied ONCE by the frozen engine."""
    if not isinstance(cost_model, Mapping):
        raise MissingRequiredSourceFieldError("cost_model missing")
    rt, sl = _finite(cost_model.get("round_trip_cost_pct")), _finite(cost_model.get("slippage_pct"))
    if rt is None or sl is None or rt < 0 or sl < 0:
        raise MissingRequiredSourceFieldError("cost_model.round_trip_cost_pct/slippage_pct missing or invalid")
    return CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, other_cost=rt, slippage=sl, provenance=provenance)


# ---------------------------------------------------------------------------
# secondary candle inputs: positive authority per (symbol, day), exact per-unit file/hash linkage
# ---------------------------------------------------------------------------

_SECONDARY_BUCKET = {
    ca.R_MISSING_INPUT: (Bucket.SKIPPED_MISSING_INPUT, Reason.MISSING_REQUIRED_SOURCE_INPUT),
}


def _secondary_disposition(reason: Optional[str]) -> tuple[Bucket, Reason]:
    if reason in _SECONDARY_BUCKET:
        return _SECONDARY_BUCKET[reason]
    return Bucket.BLOCKED_SECONDARY_AUTHORITY, Reason(reason or Reason.SECONDARY_INPUT_AUTHORITY_NOT_PROVEN.value)


def _secondary_identity(v: "ca.VerifiedCandleInput", rows: list[dict[str, Any]], policy: sp.SessionPolicy) -> dict[str, Any]:
    """The final approved shape: source authority, evaluation policy and the projected-input digest kept
    explicitly separate (never merged into one opaque field)."""
    proj = sp.project_session(rows, policy) if rows else None
    receipt = v.receipt
    return {
        "source_authority": {
            "receipt_digest": v.receipt_digest,
            "raw_payload_sha256": receipt.raw_payload_sha256 if receipt else None,
            "raw_archive_ref": receipt.raw_archive_ref if receipt else None,
            "normalized_candle_sha256": receipt.normalized_candle_sha256 if receipt else None,
            "normalizer_implementation_digest": receipt.normalizer_implementation_digest if receipt else None,
            "verification_result": v.provenance_status.value,
        },
        "evaluation_policy": {
            "session_policy_id": policy.policy_id, "session_policy_digest": policy.digest(),
            "raw_row_count": proj.raw_row_count if proj else 0,
            "canonical_row_count": proj.canonical_row_count if proj else 0,
            "excluded_before_session_count": proj.excluded_before_session_count if proj else 0,
            "excluded_after_session_count": proj.excluded_after_session_count if proj else 0,
        },
        "canonical_projection_digest": proj.projection_digest if proj else None,
    }


class SecondaryCandleInputs:
    """Correction 1 (closes the legacy-cache-contamination and source-window-leakage defects Codex found
    in the first implementation): admission reads ONLY the receipt-bound, independently-stored ATTESTED
    NORMALIZED ARTIFACT (`candle_authority.verify_receipt_bound_candles`) -- never the legacy convenience
    merged cache a symbol's on-disk research directory may also contain. `source_dirs`/`CANDLE_SOURCE_DIRS`
    is retained ONLY to report, as a non-gating diagnostic, whether such a legacy file happens to exist;
    it is never read, hashed, or otherwise consulted for admission, so a fresh receipt can never
    retroactively attest pre-existing unattested rows merely by having been merged into the same file on
    disk. Every row released to a pipeline is individually verified to fall within the receipt's own
    source window (row-level, never day-level overlap).

    Phase 1 (`verify`) builds the per-unit manifest record BEFORE any recompute; phase 2 (`consume`)
    performs the FULL verification again from scratch (fresh disk reads, fresh hashing -- true TOCTOU
    safety, not a cached-result trust) and additionally requires the receipt identity to be unchanged
    since phase 1, then releases the CANONICAL-SESSION-PROJECTED rows to a pipeline.

    Admission is gated ONLY by a verified `libs.market_data.receipts.MarketDataReceipt` -- there is no
    boolean "trust me" flag anywhere in this class. `raw_archive_root`/`receipt_root`/`normalized_root`
    default to `None` (no receipt can ever resolve, so admission is unconditionally NOT_PROVEN -- the
    correct state for this repository's unattested legacy caches). Tests exercise the SAME
    `verify_receipt_bound_candles` path by constructing real receipts/raw/attested artifacts under a
    temporary root and passing them here -- never a bypass."""

    def __init__(
        self, repo_root: Path, source_dirs: Sequence[str] = CANDLE_SOURCE_DIRS, *,
        raw_archive_root: Optional[Path] = None, receipt_root: Optional[Path] = None,
        normalized_root: Optional[Path] = None, session_policy: sp.SessionPolicy = sp.KOREAN_REGULAR_SESSION,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.source_dirs = tuple(source_dirs)
        self.raw_archive_root = Path(raw_archive_root) if raw_archive_root is not None else None
        self.receipt_root = Path(receipt_root) if receipt_root is not None else None
        self.normalized_root = Path(normalized_root) if normalized_root is not None else None
        self.session_policy = session_policy

    def _receipt_for(self, symbol: str) -> Optional[mdr.MarketDataReceipt]:
        if self.receipt_root is None:
            return None
        return mdr.read_receipt(self.receipt_root, mdr.PROVIDER_KIWOOM, mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1, symbol)

    def _legacy_cache_present(self, symbol: str) -> bool:
        """Diagnostic only -- NEVER consulted for admission. Exists so the manifest can show that a
        legacy, unattested convenience cache may sit alongside an attested artifact without either one
        contaminating the other."""
        return any((self.repo_root / d / f"{symbol}.json").is_file() for d in self.source_dirs)

    def _verify(self, symbol: str, day: str, anchors: Sequence[ca.Anchor]) -> tuple["ca.VerifiedCandleInput", list[dict[str, Any]]]:
        receipt = self._receipt_for(symbol)
        return ca.verify_receipt_bound_candles(receipt, symbol=symbol, day=day, anchors=anchors,
                                               archive_root=self.raw_archive_root, normalized_root=self.normalized_root)

    def verify(self, symbol: str, day: str, anchors: Sequence[ca.Anchor]) -> list[dict[str, Any]]:
        v, rows = self._verify(symbol, day, anchors)
        record = v.to_dict()
        record["secondary_input_identity"] = _secondary_identity(v, rows, self.session_policy)
        record["legacy_cache_present_not_authoritative"] = self._legacy_cache_present(symbol)
        return [record]

    def consume(self, symbol: str, day: str, anchors: Sequence[ca.Anchor], recorded: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Returns ONLY the canonical-session-projected rows -- a frozen adapter never sees a row outside
        09:00-15:30 KST, so a row like 15:35 cannot affect LAST_AVAILABLE/EOD/MFE/MAE."""
        mine = [r for r in recorded if r.get("symbol") == symbol and r.get("trading_date") == day]
        if not mine:
            raise SecondaryInputAuthorityError(f"no verified secondary input recorded for {symbol} on {day}")
        recorded_digest = mine[0].get("secondary_input_identity", {}).get("source_authority", {}).get("receipt_digest")
        v, rows = self._verify(symbol, day, anchors)  # full fresh re-verification -- never trusts `recorded`'s status
        if not v.admitted:
            bucket, reason = _secondary_disposition(v.reason)
            raise SecondaryInputAuthorityError(f"{symbol} {day}: {v.detail}", reason, bucket)
        if v.receipt_digest != recorded_digest:
            raise SecondaryInputAuthorityError(
                f"{symbol}: receipt changed since the input manifest was built", Reason.SECONDARY_INPUT_HASH_MISMATCH)
        return list(sp.project_session(rows, self.session_policy).rows)


# ---------------------------------------------------------------------------
# aggregation helper (frozen UEF-3C entry point only)
# ---------------------------------------------------------------------------

def _aggregate(
    *, family_key: str, scope: str, hypothesis_id: str, horizon_label: str, members: Sequence[Any],
    cost_policy: Optional[CostPolicy], day: str, excluded_note: str = "",
) -> AggregateRecord:
    metric_policy = MetricPolicy()
    ref = build_event_ref(source_namespace=_AGG_NAMESPACE, native_id=f"uef5_2:{family_key}:{scope}:{horizon_label}:{day}")
    subject = _evaluation_subject_id(canonical_event_id=ref.canonical_event_id, hypothesis_id=hypothesis_id, observation_type="AGGREGATE")
    record = _evaluation_record_id(evaluation_subject_id=subject, execution_mode="OBSERVATION_ONLY")
    identity = AggregateIdentity(
        aggregate_ref=ref, aggregation_scope=f"{family_key}:{scope}", hypothesis_id=hypothesis_id,
        evaluator_version="", evaluation_subject_id=subject, evaluation_record_id=record,
    )
    ctx = MetricAggregationContext(
        aggregate_identity=identity, horizon_label=horizon_label,
        cost_policy_id=cost_policy.policy_id if cost_policy is not None else "",
        metric_policy_id=metric_policy.policy_id,
    )
    try:
        return aggregate_canonical_samples(
            context=ctx, batches=(CanonicalSampleBatch(context=ctx, members=tuple(members)),),
            metric_policy=metric_policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
            aggregation_window_start=day, aggregation_window_end=day, excluded_note=excluded_note,
        )
    except ValueError as exc:
        raise CanonicalValidationError(f"aggregation rejected ({type(exc).__name__}): {exc}") from exc


def _member_counts(members: Iterable[Any]) -> dict[str, int]:
    counts = {"evaluated": 0, "missing": 0, "excluded": 0}
    for m in members:
        counts[{SampleMemberState.EVALUATED: "evaluated", SampleMemberState.MISSING: "missing",
                SampleMemberState.EXCLUDED: "excluded"}[m.state]] += 1
    return counts


# ---------------------------------------------------------------------------
# accounting records
# ---------------------------------------------------------------------------

@dataclass
class InputArtifact:
    family_label: str
    family_key: str
    path: str
    schema_version: Optional[str]
    program_id: Optional[str]
    trading_date: Optional[str]
    sha256: Optional[str]
    source_state: str
    native_identity: dict[str, Any]
    registry_status: str
    evidence_level_status: str
    matched_rule_ids: list[str]
    record_level_rule_ids: list[str]
    invalid_fields: list[str]
    reason_codes: list[str]
    positive_verifier_ids: list[str]
    adapter_key: str
    adapter_status: str
    adapter_eligible: bool
    companions: list[dict[str, Optional[str]]] = field(default_factory=list)
    required_fields_usable: bool = True
    secondary_blocked: bool = False  # admitted by registry+adapter, then stopped by secondary-input authority
    secondary_inputs: list[dict[str, Any]] = field(default_factory=list)
    cost_authority: list[dict[str, Any]] = field(default_factory=list)
    bucket: Optional[str] = None
    bucket_reason: str = ""
    bucket_detail: str = ""  # deterministic exception type + message; outcome record only
    stages: dict[str, str] = field(default_factory=dict)  # outcome only (run_manifest), never the input manifest

    def identity_dict(self) -> dict[str, Any]:
        """Stable inputs only (no bucket outcome). Kept for back-compat callers; `compute_run_id` uses
        the three split accessors below so source authority, evaluation policy and cost authority are
        each their own named digest rather than one opaque blob."""
        return {**self.primary_identity_dict(), "secondary_inputs": self._secondary_identity_for_run_id(),
                "cost_authority": self.cost_authority}

    def primary_identity_dict(self) -> dict[str, Any]:
        """Primary-source identity only -- feeds `primary_input_manifest_digest`."""
        return {
            "family_key": self.family_key, "path": self.path, "sha256": self.sha256,
            "registry_status": self.registry_status, "evidence_level_status": self.evidence_level_status,
            "invalid_fields": sorted(self.invalid_fields), "adapter_key": self.adapter_key,
            "adapter_status": self.adapter_status, "companions": self.companions,
        }

    def _secondary_identity_for_run_id(self) -> list[dict[str, Any]]:
        return [{k: r.get(k) for k in ("attested_artifact_ref", "attested_artifact_sha256", "symbol", "trading_date",
                                       "secondary_input_verifier_id", "provenance_status", "reason_code",
                                       "required_row_scope", "secondary_input_identity")}
                for r in self.secondary_inputs]

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family_label, "family_key": self.family_key, "source_artifact": self.path,
            "source_schema": self.schema_version, "source_program_id": self.program_id,
            "trading_date": self.trading_date, "sha256": self.sha256, "source_state": self.source_state,
            "native_identity": self.native_identity,
            "registry_status": self.registry_status, "evidence_level_status": self.evidence_level_status,
            "matched_registry_rule_ids": sorted(self.matched_rule_ids),
            "record_level_rule_ids": sorted(self.record_level_rule_ids),
            "invalid_fields": sorted(self.invalid_fields), "registry_reason_codes": sorted(self.reason_codes),
            "positive_verifier_ids": sorted(self.positive_verifier_ids),
            "adapter_id": self.adapter_key, "adapter_status": self.adapter_status,
            "adapter_eligible": self.adapter_eligible, "companion_artifacts": self.companions,
            "primary_source_path": self.path, "primary_source_hash": self.sha256,
            "secondary_inputs": self.secondary_inputs, "cost_authority": self.cost_authority,
            "bucket": self.bucket, "bucket_reason": self.bucket_reason, "bucket_detail": self.bucket_detail,
        }


@dataclass
class UnitResult:
    episodes: list[EpisodeRecord] = field(default_factory=list)
    aggregates: list[tuple[AggregateRecord, dict[str, Any]]] = field(default_factory=list)
    records_considered: int = 0
    members: dict[str, int] = field(default_factory=lambda: {"evaluated": 0, "missing": 0, "excluded": 0})
    members_tracked: bool = True  # False when the approved adapter aggregates internally (no member list exposed)
    stages: dict[str, str] = field(default_factory=dict)
    blocked_missing_cost: bool = False
    companions: list[dict[str, Optional[str]]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# family pipelines
# ---------------------------------------------------------------------------

class RunContext:
    def __init__(self, repo_root: Path, candles: SecondaryCandleInputs) -> None:
        self.repo_root = Path(repo_root)
        self.candles = candles


def _dedupe_episodes(episodes: Iterable[EpisodeRecord]) -> list[EpisodeRecord]:
    """Identical repeats within ONE unit (an adapter rebuilds the same episode per horizon) collapse;
    same id with different content is a collision."""
    seen: dict[str, str] = {}
    out: list[EpisodeRecord] = []
    for ep in episodes:
        rid = ep.identity.evaluation_record_id
        body = canonical_json(ep.to_dict())
        if rid in seen:
            if seen[rid] != body:
                raise CanonicalIdentityCollisionError(f"episode {rid} produced with two different contents")
            continue
        seen[rid] = body
        out.append(ep)
    return out


def _add_members(unit: UnitResult, members: Sequence[Any]) -> None:
    for k, v in _member_counts(members).items():
        unit.members[k] += v


def _verify_unchanged(ctx: RunContext, entry: InputArtifact) -> None:
    if entry.sha256 and sha256_file(ctx.repo_root / entry.path) != entry.sha256:
        raise SourceFileChangedError(f"{entry.path} changed since the input manifest was built")


def _companion(ctx: RunContext, entry: InputArtifact, name: str) -> tuple[Any, dict[str, Optional[str]]]:
    rel = (Path(entry.path).parent / name).as_posix()
    p = ctx.repo_root / rel
    if not p.is_file():
        raise CompanionArtifactMissingError(f"companion {name} missing")
    return _read_json(p), {"role": name, "path": rel, "sha256": sha256_file(p)}


def _q10_semi_candle_needs(forward: Mapping[str, Any], decisions: Sequence[Any]) -> dict[str, list[ca.Anchor]]:
    """Symbols whose candles an adapter call would actually read (a decision candidate with an available
    reference), each with the persisted primary-artifact anchors the candle file must reproduce."""
    symbols = set()
    for d in decisions:
        for cand in q10s.parse_decision_candidates(d):
            if cand.available:
                symbols.add(cand.symbol)
    return {sym: ca.q10_semiconductor_anchors(forward, sym) for sym in sorted(symbols)}


def _pipeline_q10_semiconductor(ctx: RunContext, entries: Sequence[InputArtifact]) -> UnitResult:
    (entry,) = entries
    _verify_unchanged(ctx, entry)
    forward = _read_json(ctx.repo_root / entry.path)
    day = str(forward.get("day") or "")
    decisions_payload, companion = _companion(ctx, entry, "baseline_samsung_hynix_decisions.json")
    if (
        not isinstance(decisions_payload, dict)
        or decisions_payload.get("evaluation_program_id") != rules.Q10_SEMI_PROGRAM
        or decisions_payload.get("day") != day
        or not isinstance(decisions_payload.get("decisions"), list)
    ):
        raise UnexpectedSourceSchemaError("decisions companion does not match the admitted forward artifact")
    decisions = decisions_payload["decisions"]
    ids = {d.get("decision_id") for d in decisions if isinstance(d, dict)}
    forward_ids = {r.get("baseline_decision_id") for r in forward.get("rows", []) if isinstance(r, dict)}
    if not forward_ids <= ids:
        raise CompanionLinkageError("forward artifact rows reference decisions absent from the decisions companion")
    policy = cost_policy_from_persisted_cost_model(
        forward.get("cost_model"), provenance=f"persisted cost_model of {entry.path} (round_trip_cost_pct is undecomposed commission+tax)")
    needs = _q10_semi_candle_needs(forward, decisions)
    rows_by_symbol = {sym: ctx.candles.consume(sym, day, anchors, entry.secondary_inputs) for sym, anchors in sorted(needs.items())}
    try:
        result = q10s.adapt_q10_semiconductor_decisions(
            decisions, minute_rows_by_symbol=rows_by_symbol, cost_policy=policy,
            aggregation_window_start=day, aggregation_window_end=day)
    except ValueError as exc:
        raise CanonicalValidationError(f"{type(exc).__name__}: {exc}") from exc
    unit = UnitResult(companions=[companion], records_considered=len(decisions), members_tracked=False)
    unit.stages = {"source_admitted": "OK", "secondary_inputs": "VERIFIED", "episodes": "PRODUCED",
                   "checkpoints": "PRODUCED", "aggregates": "PRODUCED"}
    unit.episodes = _dedupe_episodes(result.episodes)
    for (view, horizon), agg in sorted(result.aggregates.items()):
        unit.aggregates.append((agg, {"family": entry.family_label, "unit": entry.path, "view": view, "horizon_label": horizon, "day": day}))
    return unit


def _q10_fg_episodes_without_cost(day_dir: Path) -> tuple[list[EpisodeRecord], dict[str, int]]:
    """Calc F (stock) / Calc G (index) canonical EPISODES from the approved adapter's own builders. The public
    entrypoints require a CostPolicy only to build GROSS_ONLY aggregation MEMBERS; episodes never depend on it.
    The reaction artifact persists no cost model, so no CostPolicy is created here and no F/G member/aggregate
    is built (the frozen aggregation always applies cost -- see MISSING_AUTHORITATIVE_COST_POLICY)."""
    payload = q10fg._read_verified_json(day_dir, q10fg._REACTIONS_ARTIFACT_FILENAME)
    day = str(payload.get("day") or "")
    targets = payload.get("targets")
    if not isinstance(targets, Mapping):
        raise q10fg.Q10IndexAdapterError("artifact.targets must be an object")
    episodes: list[EpisodeRecord] = []
    counts = {"F_targets": 0, "F_missing_reference": 0, "G_targets": 0, "G_missing_reference": 0}
    for key, row in targets.items():
        if not isinstance(row, Mapping):
            continue
        target = q10fg._parse_reaction_target(day=day, key=str(key), row=row)
        if target.kind == "stock":
            calc, build = "F", q10fg._build_calc_f_episode
        elif target.kind == "index":
            calc, build = "G", q10fg._build_calc_g_episode
        else:
            continue
        counts[f"{calc}_targets"] += 1
        if q10fg._resolve_open_reference(target) is None:
            counts[f"{calc}_missing_reference"] += 1  # MISSING population member: no episode, never a zero
            continue
        episodes.append(build(target))
    return episodes, counts


def _pipeline_q10_index(ctx: RunContext, entries: Sequence[InputArtifact]) -> UnitResult:
    for e in entries:
        _verify_unchanged(ctx, e)
    day_dir = (ctx.repo_root / Path(entries[0].path).parent)
    day = str(entries[0].trading_date)
    unit = UnitResult(records_considered=0)
    try:
        episodes, fg_counts = _q10_fg_episodes_without_cost(day_dir)
        unit.records_considered += fg_counts["F_targets"] + fg_counts["G_targets"]
        h_results = q10h.canonicalize_q10_index_calc_h_artifact(day_dir)
    except ValueError as exc:
        raise CanonicalValidationError(f"{type(exc).__name__}: {exc}") from exc
    by_policy: dict[str, list[Any]] = {}
    for r in h_results:
        by_policy.setdefault(r.policy, []).append(r)
    unit.records_considered += len(h_results)
    for policy in sorted(by_policy):
        rs = by_policy[policy]
        members = [r.member for r in rs]
        episodes.extend(r.episode for r in rs if r.episode is not None)
        _add_members(unit, members)
        agg = _aggregate(family_key=rules.F_Q10_INDEX, scope=f"calc_h:{policy}", hypothesis_id=q10h.policy_hypothesis_id(policy),
                         horizon_label=policy, members=members, cost_policy=None, day=day,
                         excluded_note=_Q10_H_EXCLUSION_NOTE)
        unit.aggregates.append((agg, {"family": entries[0].family_label, "unit": day_dir.relative_to(ctx.repo_root).as_posix(),
                                      "calc": "H", "policy": policy, "horizon_label": policy, "day": day}))
    unit.episodes = _dedupe_episodes(episodes)
    unit.blocked_missing_cost = True
    unit.stages = {
        "source_admitted": "OK", "episodes": "PRODUCED", "checkpoints": "PRODUCED",
        "aggregates_calc_f_g": "BLOCKED_MISSING_AUTHORITATIVE_COST_POLICY",
        "aggregates_calc_h": "PRODUCED" if unit.aggregates else "NOT_PRODUCED",
    }
    return unit


def _pipeline_q11_v2(ctx: RunContext, entries: Sequence[InputArtifact]) -> UnitResult:
    (entry,) = entries
    _verify_unchanged(ctx, entry)
    day = str(entry.trading_date)
    try:
        results = q11.canonicalize_q11_opportunity_engine_artifact(ctx.repo_root / entry.path)
    except ValueError as exc:  # includes the adapter's explicit v1 BLOCKED refusal
        raise CanonicalValidationError(f"{type(exc).__name__}: {exc}") from exc
    unit = UnitResult(records_considered=len(results))
    unit.episodes = _dedupe_episodes(r.episode for r in results)
    for label in _Q11_HORIZONS:
        members = []
        for ep in unit.episodes:
            cp = next((c for c in ep.checkpoints if c.horizon_label == label), None)
            members.append(q11.checkpoint_to_net_or_cost_included_member(cp, evaluation_record_id=ep.identity.evaluation_record_id))
        if not members:
            continue
        _add_members(unit, members)
        agg = _aggregate(family_key=rules.F_Q11, scope="trades", hypothesis_id=q11.HYPOTHESIS_ID, horizon_label=label,
                         members=members, cost_policy=None, day=day)
        unit.aggregates.append((agg, {"family": entry.family_label, "unit": entry.path, "horizon_label": label, "day": day}))
    return unit


def _calc1_candle_needs(forward: Mapping[str, Any], decisions: Sequence[Any]) -> dict[str, list[ca.Anchor]]:
    """Q12 Calc1 has one fixed target (041190); candles are needed only when at least one decision's
    candidate actually resolved a reference. Same anchor extraction as Q10 Semi (identical persisted shape)."""
    try:
        candidates = q12c1.parse_calc1_decisions(decisions)
    except q12c1.Q12AdapterError:
        return {}
    if any(c.available for c in candidates):
        return {"041190": ca.q10_semiconductor_anchors(forward, "041190")}
    return {}


def _calc2_candle_needs(payload: Mapping[str, Any]) -> dict[str, list[ca.Anchor]]:
    """Q12 Calc2 has the same one fixed target (041190); candles are needed only when at least one
    entry_method actually resolved (status OBSERVED)."""
    entry_outcomes = payload.get("entry_outcomes")
    if not isinstance(entry_outcomes, Mapping):
        return {}
    if any(isinstance(o, Mapping) and o.get("status") == "OBSERVED" for o in entry_outcomes.values()):
        return {"041190": ca.q12_calc2_anchors(payload)}
    return {}


def _pipeline_q12_calc1(ctx: RunContext, entries: Sequence[InputArtifact]) -> UnitResult:
    """CLEAN Calc1 primary artifact + verified authoritative 041190 candles + the approved frozen Q12
    Calc1 adapter (`parse_calc1_decisions`/`build_calc1_episode`, reused verbatim -- no Q12-specific
    evaluation logic invented here) -> canonical episode/checkpoint -> GROSS_ONLY aggregate via the
    frozen `forward_measurement_adapter.checkpoint_to_aggregation_member` (Calc1 reuses Q10 Semi's own
    generic GROSS_ONLY cost shape, per the adapter module's own docstring)."""
    (entry,) = entries
    _verify_unchanged(ctx, entry)
    forward = _read_json(ctx.repo_root / entry.path)
    day = str(forward.get("day") or "")
    decisions_payload, companion = _companion(ctx, entry, "baseline_btc_woori_decisions.json")
    if (
        not isinstance(decisions_payload, dict)
        or decisions_payload.get("evaluation_program_id") != rules.Q12_PROGRAM
        or decisions_payload.get("day") != day
        or not isinstance(decisions_payload.get("decisions"), list)
    ):
        raise UnexpectedSourceSchemaError("decisions companion does not match the admitted forward artifact")
    decisions = decisions_payload["decisions"]
    ids = {d.get("decision_id") for d in decisions if isinstance(d, dict)}
    forward_ids = {r.get("baseline_decision_id") for r in forward.get("rows", []) if isinstance(r, dict)}
    if not forward_ids <= ids:
        raise CompanionLinkageError("forward artifact rows reference decisions absent from the decisions companion")
    policy = cost_policy_from_persisted_cost_model(
        forward.get("cost_model"), provenance=f"persisted cost_model of {entry.path} (round_trip_cost_pct is undecomposed commission+tax)")
    needs = _calc1_candle_needs(forward, decisions)
    rows = ctx.candles.consume("041190", day, needs["041190"], entry.secondary_inputs) if needs else []
    try:
        candidates = q12c1.parse_calc1_decisions(decisions)
        pairs = [(c, q12c1.build_calc1_episode(c, rows) if c.available else None) for c in candidates]
    except q12c1.Q12AdapterError as exc:
        raise CanonicalValidationError(f"{type(exc).__name__}: {exc}") from exc
    episodes = _dedupe_episodes(ep for _c, ep in pairs if ep is not None)
    unit = UnitResult(companions=[companion], records_considered=len(decisions))
    unit.episodes = episodes
    for label in sorted({cp.horizon_label for ep in episodes for cp in ep.checkpoints}):
        members = [
            fma.checkpoint_to_aggregation_member(
                next((c for c in ep.checkpoints if c.horizon_label == label), None) if ep else None,
                evaluation_record_id=ep.identity.evaluation_record_id if ep else "", cost_policy=policy,
            )
            for _cand, ep in pairs
        ]
        _add_members(unit, members)
        agg = _aggregate(family_key=rules.F_Q12_CALC1, scope="decisions", hypothesis_id=q12c1.CALC1_HYPOTHESIS_ID,
                         horizon_label=label, members=members, cost_policy=policy, day=day)
        unit.aggregates.append((agg, {"family": entry.family_label, "unit": entry.path, "horizon_label": label, "day": day}))
    unit.stages = {"source_admitted": "OK", "secondary_inputs": "VERIFIED" if needs else "NOT_REQUIRED",
                   "episodes": "PRODUCED", "checkpoints": "PRODUCED", "aggregates": "PRODUCED"}
    return unit


def _pipeline_q12_calc2(ctx: RunContext, entries: Sequence[InputArtifact]) -> UnitResult:
    """CLEAN Calc2 primary artifact + verified authoritative 041190 candles + the approved frozen Q12
    Calc2 adapter (`parse_calc2_entry_method`/`build_calc2_episode`, reused verbatim) -> canonical
    episode/checkpoint -> NET_OR_COST_INCLUDED aggregate via the frozen
    `checkpoint_to_net_or_cost_included_member` (source net return; no cost re-application)."""
    (entry,) = entries
    _verify_unchanged(ctx, entry)
    payload = _read_json(ctx.repo_root / entry.path)
    day = str(payload.get("day") or "")
    entry_outcomes = payload.get("entry_outcomes")
    if not isinstance(entry_outcomes, Mapping):
        raise UnexpectedSourceSchemaError("entry_outcomes missing or not an object")
    features = payload.get("features") if isinstance(payload.get("features"), Mapping) else {}
    btc_0855 = features.get("btc_0855") if isinstance(features.get("btc_0855"), Mapping) else {}
    needs = _calc2_candle_needs(payload)
    rows = ctx.candles.consume("041190", day, needs["041190"], entry.secondary_inputs) if needs else []
    try:
        pairs = []
        for method in q12c2.ENTRY_METHODS:
            outcome = entry_outcomes.get(method)
            if not isinstance(outcome, Mapping):
                continue
            sample = q12c2.parse_calc2_entry_method(trading_date=day, entry_method=method, outcome=outcome, btc_0855=btc_0855)
            ep = q12c2.build_calc2_episode(sample, rows) if sample.status == "OBSERVED" else None
            pairs.append((sample, ep))
    except q12c2.Q12AdapterError as exc:
        raise CanonicalValidationError(f"{type(exc).__name__}: {exc}") from exc
    episodes = _dedupe_episodes(ep for _s, ep in pairs if ep is not None)
    unit = UnitResult(records_considered=len(pairs))
    unit.episodes = episodes
    for label in sorted({cp.horizon_label for ep in episodes for cp in ep.checkpoints}):
        members = [
            q12c2.checkpoint_to_net_or_cost_included_member(
                next((c for c in ep.checkpoints if c.horizon_label == label), None) if ep else None,
                evaluation_record_id=ep.identity.evaluation_record_id if ep else "",
            )
            for _sample, ep in pairs
        ]
        _add_members(unit, members)
        agg = _aggregate(family_key=rules.F_Q12_CALC2, scope="entry_methods", hypothesis_id=q12c2.HYPOTHESIS_ID,
                         horizon_label=label, members=members, cost_policy=None, day=day)
        unit.aggregates.append((agg, {"family": entry.family_label, "unit": entry.path, "horizon_label": label, "day": day}))
    unit.stages = {"source_admitted": "OK", "secondary_inputs": "VERIFIED" if needs else "NOT_REQUIRED",
                   "episodes": "PRODUCED", "checkpoints": "PRODUCED", "aggregates": "PRODUCED"}
    return unit


def _pipeline_not_wired(ctx: RunContext, entries: Sequence[InputArtifact]) -> UnitResult:
    raise PipelineNotImplementedError(f"{entries[0].family_label}: pipeline not wired in UEF-5.2 initial scope")


PIPELINES: dict[str, Callable[[RunContext, Sequence[InputArtifact]], UnitResult]] = {
    rules.F_Q10_SEMI: _pipeline_q10_semiconductor,
    rules.F_Q10_INDEX: _pipeline_q10_index,
    rules.F_Q11: _pipeline_q11_v2,
    rules.F_Q12_CALC1: _pipeline_q12_calc1,
    rules.F_Q12_CALC2: _pipeline_q12_calc2,
    rules.F_OPENING_1A: _pipeline_not_wired,
    rules.F_OPENING_1BC: _pipeline_not_wired,
}
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    rules.F_Q10_SEMI: ("forward_outcome", "forward_usable_coverage"),
    rules.F_Q12_CALC1: ("forward_outcome", "forward_usable_coverage"),
    rules.F_Q12_CALC2: ("forward_outcome",),
    rules.F_OPENING_1A: ("forward_outcome",),
    rules.F_OPENING_1BC: ("forward_outcome",),
    rules.F_Q10_INDEX: ("forward_outcome",),
    rules.F_Q11: ("forward_outcome",),
}
_COMPANION_NAMES = {
    rules.F_Q10_SEMI: ("baseline_samsung_hynix_decisions.json",),
    rules.F_Q12_CALC1: ("baseline_btc_woori_decisions.json",),
}


# ---------------------------------------------------------------------------
# input classification (the immutable input manifest)
# ---------------------------------------------------------------------------

def _record_ids(descs: Sequence[Any]) -> list[str]:
    ids = []
    for d in descs:
        for kind, value in d.native_ids:
            if kind in ("decision_id", "trade_id"):
                ids.append(value)
    return sorted(set(ids))


def classify_inputs(
    repo_root: Path, registry: EvidenceRegistry, invalid_days: frozenset,
    families: Sequence[FamilySpec] = DEFAULT_FAMILIES, *, max_parse_bytes: int = DEFAULT_MAX_PARSE_BYTES,
) -> list[InputArtifact]:
    repo_root = Path(repo_root)
    entries: list[InputArtifact] = []
    for spec in families:
        eligibility = rules.ADAPTER_ELIGIBILITY[spec.adapter_key]
        for rel in _discover(repo_root, spec):
            state, payload = _load_payload(repo_root / rel, max_parse_bytes)
            desc, file_date = _file_descriptor(spec, rel, payload if state == "ok" else None)
            if state == "ok" and not _spec_accepts(spec, desc.schema_version):
                continue
            records = _record_descriptors(spec, rel, payload, file_date) if state == "ok" else []
            audits = _run_verifiers(repo_root, registry, desc, payload, file_date, invalid_days) if state == "ok" else []
            res = resolve_evidence_status(desc, registry, audits=audits, records=records)
            ids = _record_ids(records)
            companions = []
            for name in _COMPANION_NAMES.get(spec.family_key, ()):
                cp = repo_root / (Path(rel).parent / name)
                companions.append({"role": name, "path": (Path(rel).parent / name).as_posix(),
                                   "sha256": sha256_file(cp) if cp.is_file() else None})
            required = REQUIRED_FIELDS.get(spec.family_key, ("forward_outcome",))
            entries.append(InputArtifact(
                family_label=spec.label, family_key=spec.family_key, path=rel, schema_version=desc.schema_version,
                program_id=desc.program_id, trading_date=file_date, sha256=sha256_file(repo_root / rel) if (repo_root / rel).is_file() else None,
                source_state=state,
                native_identity={"trading_date": file_date, "record_count": len(records),
                                 "record_id_first": ids[0] if ids else None, "record_id_last": ids[-1] if ids else None},
                registry_status=res.status.value, evidence_level_status=res.evidence_level_status.value,
                matched_rule_ids=list(res.matched_rule_ids), record_level_rule_ids=list(res.record_level_rule_ids),
                invalid_fields=list(res.invalid_fields), reason_codes=list(res.reason_codes),
                positive_verifier_ids=list(res.positive_verifier_ids), adapter_key=spec.adapter_key,
                adapter_status=eligibility["adapter_status"],
                adapter_eligible=eligibility["adapter_status"] in ELIGIBLE_ADAPTER_STATUSES,
                companions=companions,
                required_fields_usable=all(res.field_usable(f) for f in required)
                if res.evidence_level_status is EvidenceStatus.CLEAN else False,
            ))
    order = {s.label: i for i, s in enumerate(families)}
    entries.sort(key=lambda e: (order[e.family_label], e.path))
    return entries


def _pre_bucket(entry: InputArtifact) -> None:
    """Deterministic gating order: adapter BLOCKED > source state > registry > required field."""
    if not entry.adapter_eligible:
        entry.bucket, entry.bucket_reason = Bucket.SKIPPED_ADAPTER_BLOCKED.value, Reason.ADAPTER_BLOCKED.value
    elif entry.source_state != "ok":
        entry.bucket, entry.bucket_reason = Bucket.PARSE_FAILURE.value, Reason.PARSE_FAILURE.value
    elif entry.evidence_level_status != EvidenceStatus.CLEAN.value:
        reason = {"QUARANTINED": Reason.REGISTRY_QUARANTINED, "REVIEW_REQUIRED": Reason.REGISTRY_REVIEW_REQUIRED,
                  "NO_RULE": Reason.REGISTRY_NO_RULE}.get(entry.evidence_level_status, Reason.REGISTRY_NOT_CLEAN)
        entry.bucket, entry.bucket_reason = Bucket.SKIPPED_REGISTRY.value, reason.value
    elif not entry.required_fields_usable:
        entry.bucket, entry.bucket_reason = Bucket.SKIPPED_INVALID_REQUIRED_FIELD.value, Reason.REQUIRED_FIELD_INVALID.value


def _units(entries: Sequence[InputArtifact]) -> list[tuple[str, list[InputArtifact]]]:
    """Admissible entries (no bucket yet) grouped into recompute units. Q10 Index recomputes a day
    directory only when ALL THREE of its files are admissible; otherwise the admissible ones are
    reported as REGISTRY_UNIT_INCOMPLETE."""
    units: list[tuple[str, list[InputArtifact]]] = []
    q10_dirs: dict[str, list[InputArtifact]] = {}
    for e in entries:
        if e.bucket is not None:
            continue
        if e.family_key == rules.F_Q10_INDEX:
            q10_dirs.setdefault(str(Path(e.path).parent.as_posix()), []).append(e)
        else:
            units.append((e.path, [e]))
    for d, group in sorted(q10_dirs.items()):
        have = {Path(e.path).name for e in group}
        if have == set(_Q10_INDEX_FILES):
            units.append((d, sorted(group, key=lambda e: e.path)))
        else:
            for e in group:
                e.bucket, e.bucket_reason = Bucket.SKIPPED_REGISTRY.value, Reason.REGISTRY_UNIT_INCOMPLETE.value
    return sorted(units, key=lambda u: u[0])


def input_manifest_document(entries: Sequence[InputArtifact], registry: EvidenceRegistry) -> dict[str, Any]:
    return {
        "schema_version": RECOMPUTE_SCHEMA_VERSION, "document": "input_manifest", "recompute_version": RECOMPUTE_VERSION,
        "registry_version": registry.registry_version, "registry_digest": registry.digest(),
        "secondary_input_verifier_id": ca.VERIFIER_ID, "secondary_input_authority_basis": ca.AUTHORITY_BASIS,
        "artifacts": [e.to_dict() for e in entries],
    }


# Bounded, auditable dependency closure (architecture Section 6/16 -- never a recursive import walk):
#   A. frozen dependencies       -> represented ONLY by frozen_core_manifest_identity (never re-hashed here)
#   B. explicit UEF semantic roots + C. direct non-frozen semantic helpers -> exact hashes, listed below
#   D. the artifact-producing normalizer -> its digest travels inside the verified MarketDataReceipt,
#      never duplicated here (see candle_authority.verify_receipt / libs.market_data.receipts)
#   E. this list's OWN membership participates in the digest (adding/removing an entry changes identity)
_SEMANTIC_IMPLEMENTATION_FILES: tuple[str, ...] = (
    "libs/reporting/evaluation/uef5/historical_recompute.py",  # orchestrator: owns every gate/dispatch decision
    "libs/reporting/evaluation/uef5/candle_authority.py",  # secondary-input structural + receipt verifier
    "libs/reporting/evaluation/uef5/session_policy.py",  # evaluation SessionPolicy + canonical projection
    "libs/market_data/receipts.py",  # receipt schema, canonical serialization, digest, archive resolution
    "libs/reporting/evaluation/uef5/clean_evidence_registry.py",  # resolve_evidence_status resolution behavior
    "libs/reporting/evaluation/uef5/clean_evidence_rules.py",  # ADAPTER_ELIGIBILITY + admission authority
    "libs/reporting/evaluation/uef5/clean_evidence_coverage.py",  # input discovery/classification semantics
    "libs/reporting/evaluation/canonical/record.py",  # EpisodeRecord/AggregateRecord serialization shape
                                                        # (NOT in the 11-file freeze manifest -- confirmed by
                                                        # inspection; a genuine non-frozen dependency)
    "libs/reporting/evaluation/canonical/adapters/forward_measurement_adapter.py",
    "libs/reporting/evaluation/canonical/adapters/hypothesis_forward_adapter.py",
    "libs/reporting/evaluation/canonical/adapters/q10_index_directional_shadow_adapter.py",
    "libs/reporting/evaluation/canonical/adapters/q10_index_reaction_adapter.py",
    "libs/reporting/evaluation/canonical/adapters/q10_semiconductor.py",
    "libs/reporting/evaluation/canonical/adapters/q12_baseline_btc_woori.py",
    "libs/reporting/evaluation/canonical/adapters/virtual_probe_adapter.py",
)
# Back-compat alias (Fix2-era name); identical set.
_ADAPTER_IDENTITY_FILES = _SEMANTIC_IMPLEMENTATION_FILES


def semantic_implementation_identity(repo_root: Path, files: Sequence[str] = _SEMANTIC_IMPLEMENTATION_FILES) -> dict[str, str]:
    repo_root = Path(repo_root)
    return {f: sha256_file(repo_root / f) for f in files if (repo_root / f).is_file()}


# Back-compat alias.
adapter_implementation_identity = semantic_implementation_identity


_FREEZE_MANIFEST_PATH = "docs/research/uef_freeze_manifest.md"
_FREEZE_ROW_RE = re.compile(
    r"^\|\s*(?P<path>[^|]+?)\s*\|\s*[^|]+?\s*\|\s*[^|]+?\s*\|\s*(?P<sha256>[0-9a-f]{64})\s*\|\s*$", re.IGNORECASE)


def frozen_core_manifest_identity(repo_root: Path) -> dict[str, str]:
    """Read-only parse of the ONE authoritative freeze manifest (`docs/research/uef_freeze_manifest.md`,
    verified independently by `scripts/verify_uef_freeze_manifest.py`) -- captures ITS declared
    (path, sha256) rows so the run id detects any change to frozen UEF-1..3C identity. This never
    recomputes a hash itself; it only reads what the manifest already declares."""
    p = Path(repo_root) / _FREEZE_MANIFEST_PATH
    if not p.is_file():
        return {}
    rows: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        m = _FREEZE_ROW_RE.match(line.strip())
        if m and m.group("path") != "relative_path":
            rows[m.group("path")] = m.group("sha256")
    return rows


def effective_run_config(
    *, families: Sequence[FamilySpec], candle_source_dirs: Sequence[str], max_parse_bytes: int,
    session_policy: sp.SessionPolicy,
) -> dict[str, Any]:
    """The semantic subset of a run's own configuration (architecture Section 22/D). Never includes
    out_root, --no-write, logging verbosity or console formatting -- none of those can change semantic
    output."""
    return {
        "families": sorted(f.label for f in families), "candle_source_dirs": sorted(candle_source_dirs),
        "max_parse_bytes": max_parse_bytes, "session_policy_id": session_policy.policy_id,
        "session_policy_digest": session_policy.digest(),
        "recompute_schema_version": RECOMPUTE_SCHEMA_VERSION, "recompute_version": RECOMPUTE_VERSION,
    }


def _digest(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def compute_run_id(
    entries: Sequence[InputArtifact], registry: EvidenceRegistry, *,
    implementation_identity: Mapping[str, str], frozen_core_identity: Mapping[str, str],
    run_config: Mapping[str, Any],
) -> str:
    """run_id = implementation_manifest_digest + effective_run_config_digest + primary_input_manifest_digest
    + secondary_input_manifest_digest + registry_digest + cost_authority_digest -> canonical JSON -> SHA-256
    (architecture Section 26). Same data + a changed orchestrator/verifier/session-policy/adapter/registry
    implementation -> a different run id, with no manual version bump required. No clock, no UUID, no
    filesystem enumeration dependence (entries are already sorted by (family order, path) upstream)."""
    implementation_manifest_digest = _digest({
        "semantic_files": dict(sorted(implementation_identity.items())),
        "frozen_core_manifest_digest": _digest(dict(sorted(frozen_core_identity.items()))),
    })
    payload = {
        "schema": RECOMPUTE_SCHEMA_VERSION,
        "implementation_manifest_digest": implementation_manifest_digest,
        "effective_run_config_digest": _digest(dict(run_config)),
        "primary_input_manifest_digest": _digest([e.primary_identity_dict() for e in entries]),
        "secondary_input_manifest_digest": _digest([e._secondary_identity_for_run_id() for e in entries]),
        "registry_digest": registry.digest(),
        "cost_authority_digest": _digest([e.cost_authority for e in entries]),
    }
    return "UEF5RUN_" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:20]


_COST_MISSING_FG = {
    "scope": "calc_f_g", "cost_policy_id": None, "cost_source": None, "authority_status": "MISSING",
    "note": "GROSS_ONLY source with no persisted cost model; the frozen aggregation always applies cost, so no "
            "F/G aggregate/net metric is produced (MISSING_AUTHORITATIVE_COST_POLICY)",
}
_COST_NET_INCLUDED = {
    "cost_policy_id": None, "cost_source": "source net/cost-included return (no second cost application)",
    "authority_status": "NOT_APPLICABLE_NET_OR_COST_INCLUDED",
}


def _prepare_secondary_and_cost(ctx: "RunContext", entry: InputArtifact) -> None:
    """Phase 1 (before any recompute): per-unit cost authority + per-unit candle verification. A failing
    secondary input pre-buckets the artifact, so the adapter is never called for it."""
    key = entry.family_key
    if key == rules.F_Q10_INDEX:
        entry.cost_authority = [dict(_COST_MISSING_FG), {"scope": "calc_h", **_COST_NET_INCLUDED}]
        return
    if key == rules.F_Q11:
        entry.cost_authority = [{"scope": "all", **_COST_NET_INCLUDED}]
        return
    needs: dict[str, list[ca.Anchor]] = {}
    day = str(entry.trading_date)
    if key == rules.F_Q12_CALC1:
        try:
            _verify_unchanged(ctx, entry)
            forward = _read_json(ctx.repo_root / entry.path)
            decisions_payload, _c = _companion(ctx, entry, "baseline_btc_woori_decisions.json")
            needs = _calc1_candle_needs(forward, decisions_payload["decisions"])
        except (RecomputeError, ValueError, KeyError, TypeError):
            return
        try:
            pol = cost_policy_from_persisted_cost_model(forward.get("cost_model"), provenance=f"persisted cost_model of {entry.path}")
            entry.cost_authority = [{"scope": "all", "cost_policy_id": pol.policy_id,
                                     "cost_source": "persisted cost_model in the primary artifact",
                                     "authority_status": "PERSISTED_IN_SOURCE"}]
        except RecomputeError:
            entry.cost_authority = [{"scope": "all", "cost_policy_id": None, "cost_source": None, "authority_status": "MISSING"}]
    elif key == rules.F_Q12_CALC2:
        try:
            _verify_unchanged(ctx, entry)
            payload = _read_json(ctx.repo_root / entry.path)
            needs = _calc2_candle_needs(payload)
        except (RecomputeError, ValueError, KeyError, TypeError):
            return
        entry.cost_authority = [{"scope": "all", **_COST_NET_INCLUDED}]
    elif key == rules.F_Q10_SEMI:
        try:
            _verify_unchanged(ctx, entry)
            forward = _read_json(ctx.repo_root / entry.path)
            decisions_payload, _c = _companion(ctx, entry, "baseline_samsung_hynix_decisions.json")
            decisions = decisions_payload["decisions"]
            needs = _q10_semi_candle_needs(forward, decisions)
        except (RecomputeError, ValueError, KeyError, TypeError):
            return  # the pipeline re-raises the same classified error; nothing is admitted meanwhile
        try:
            pol = cost_policy_from_persisted_cost_model(forward.get("cost_model"), provenance=f"persisted cost_model of {entry.path}")
            entry.cost_authority = [{"scope": "all", "cost_policy_id": pol.policy_id,
                                     "cost_source": "persisted cost_model in the primary artifact",
                                     "authority_status": "PERSISTED_IN_SOURCE"}]
        except RecomputeError:
            entry.cost_authority = [{"scope": "all", "cost_policy_id": None, "cost_source": None, "authority_status": "MISSING"}]
    else:
        return
    records: list[dict[str, Any]] = []
    for sym, anchors in sorted(needs.items()):
        records.extend(ctx.candles.verify(sym, day, anchors))
    entry.secondary_inputs = records
    failing = sorted((r for r in records if r["provenance_status"] != ca.ProvenanceStatus.FULL_SOURCE_AUTHORITY.value),
                     key=lambda r: (r["symbol"], r["attested_artifact_ref"] or ""))
    if failing:
        bucket, reason = _secondary_disposition(failing[0].get("reason_code"))
        entry.bucket, entry.bucket_reason = bucket.value, reason.value
        entry.secondary_blocked = True
        entry.bucket_detail = f"{failing[0]['symbol']}: {failing[0].get('detail')}"[:300]


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@dataclass
class FamilyRun:
    label: str
    family_key: str
    intended_for_uef5: bool
    adapter_status: str
    counts: dict[str, Any]
    status: str
    reason_codes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"family": self.label, "family_key": self.family_key, "intended_for_uef5": self.intended_for_uef5,
                "adapter_status": self.adapter_status, "status": self.status, "reason_codes": sorted(self.reason_codes),
                **{k: v for k, v in sorted(self.counts.items())}}


@dataclass
class RecomputeRun:
    run_id: str
    status: RunStatus
    families: list[FamilyRun]
    summary: dict[str, Any]
    input_manifest: dict[str, Any]
    run_manifest: dict[str, Any]
    episodes: list[EpisodeRecord]
    aggregates: list[tuple[AggregateRecord, dict[str, Any]]]
    collisions: list[str]
    output_dir: Optional[Path] = None


def _check_collisions(episodes: Sequence[EpisodeRecord], aggregates: Sequence[tuple[AggregateRecord, dict[str, Any]]]) -> list[str]:
    problems: list[str] = []
    for label, items in (
        ("episode", [(e.identity.evaluation_record_id, e.identity.evaluation_subject_id) for e in episodes]),
        ("aggregate", [(a.identity.evaluation_record_id, a.identity.evaluation_subject_id) for a, _ in aggregates]),
    ):
        rec_seen: set[str] = set()
        sub_seen: set[str] = set()
        for rec, sub in items:
            if rec in rec_seen:
                problems.append(f"duplicate {label} evaluation_record_id {rec}")
            if sub in sub_seen:
                problems.append(f"duplicate {label} evaluation_subject_id {sub}")
            rec_seen.add(rec)
            sub_seen.add(sub)
    return problems


def _family_status(counts: dict[str, Any], secondary_reasons: Sequence[str] = ()) -> tuple[str, list[str]]:
    admissible = counts["admissible_units"]
    reasons: list[str] = []
    if counts["identity_collisions"]:
        return RunStatus.FAILED.value, [Reason.CANONICAL_IDENTITY_COLLISION.value]
    failures = counts["adapter_failures"] + counts["parse_failures"]
    done = counts["recomputed_units"]
    if admissible == 0:
        return RunStatus.COMPLETE.value, reasons
    if counts["blocked_missing_cost_policy"]:
        reasons.append(Reason.MISSING_AUTHORITATIVE_COST_POLICY.value)  # partial canonical stage, never COMPLETE
    if done == admissible and not reasons:
        return RunStatus.COMPLETE.value, reasons
    if counts["skipped_missing_input"]:
        reasons.append(Reason.MISSING_REQUIRED_SOURCE_INPUT.value)
    if counts["blocked_secondary_authority"]:
        reasons.extend(sorted(set(secondary_reasons)) or [Reason.MISSING_SECONDARY_INPUT_AUTHORITY.value])
    if counts["skipped_not_implemented"]:
        reasons.append(Reason.PIPELINE_NOT_IMPLEMENTED.value)
    if failures:
        reasons.append(Reason.ADAPTER_FAILURE.value)
    return (RunStatus.PARTIAL.value if done else RunStatus.BLOCKED.value), sorted(set(reasons))


def _serialize_episodes(episodes: Sequence[EpisodeRecord]) -> str:
    try:
        lines = [canonical_json(e.to_dict()) for e in sorted(episodes, key=lambda e: e.identity.evaluation_record_id)]
    except Exception as exc:  # noqa: BLE001 -- any serialization defect is a hard, classified failure
        raise RecomputeSerializationError(f"episode serialization failed ({type(exc).__name__})") from exc
    return "".join(line + "\n" for line in lines)


def _serialize_aggregates(aggregates: Sequence[tuple[AggregateRecord, dict[str, Any]]]) -> str:
    try:
        docs = [{"provenance": meta, "record": agg.to_dict()} for agg, meta in aggregates]
        docs.sort(key=lambda d: d["record"]["identity"]["evaluation_record_id"])
        return canonical_json({"schema_version": RECOMPUTE_SCHEMA_VERSION, "document": "aggregates", "aggregates": docs}) + "\n"
    except Exception as exc:  # noqa: BLE001
        raise RecomputeSerializationError(f"aggregate serialization failed ({type(exc).__name__})") from exc


def run_historical_recompute(
    repo_root: Path,
    out_root: Optional[Path] = None,
    *,
    registry: Optional[EvidenceRegistry] = None,
    day_validity: Optional[dict[str, Any]] = None,
    families: Sequence[FamilySpec] = DEFAULT_FAMILIES,
    candle_source_dirs: Sequence[str] = CANDLE_SOURCE_DIRS,
    max_parse_bytes: int = DEFAULT_MAX_PARSE_BYTES,
    raw_archive_root: Optional[Path] = None,
    receipt_root: Optional[Path] = None,
    normalized_root: Optional[Path] = None,
    session_policy: sp.SessionPolicy = sp.KOREAN_REGULAR_SESSION,
) -> RecomputeRun:
    """`raw_archive_root`/`receipt_root`/`normalized_root`: where `libs.market_data.receipts.
    MarketDataReceipt`s, their raw artifacts, and their independently-attested normalized artifacts live.
    All default to `None` -- no receipt can ever resolve, so candle admission is unconditionally
    NOT_PROVEN (the correct state for this repository's unattested legacy caches).
    `scripts/run_uef5_historical_recompute.py` never sets these either; a caller that wants production
    receipt verification passes real, pre-populated roots explicitly. Tests exercise the exact same
    `SecondaryCandleInputs`/`candle_authority.verify_receipt_bound_candles` path by constructing real
    receipts/attested artifacts under a temporary root -- never a bypass boolean."""
    repo_root = Path(repo_root)
    if registry is None:
        registry, day_validity = build_repo_registry(repo_root)
    invalid_days = frozenset((day_validity or {}).get("invalid_days", {}))
    candles = SecondaryCandleInputs(repo_root, candle_source_dirs, raw_archive_root=raw_archive_root,
                                    receipt_root=receipt_root, normalized_root=normalized_root, session_policy=session_policy)
    ctx = RunContext(repo_root, candles)
    implementation_identity = semantic_implementation_identity(repo_root)
    frozen_core_identity = frozen_core_manifest_identity(repo_root)
    run_config = effective_run_config(families=families, candle_source_dirs=candle_source_dirs,
                                      max_parse_bytes=max_parse_bytes, session_policy=session_policy)

    # 1. immutable input manifest (built BEFORE any recompute): gating is decided here, deterministically
    entries = classify_inputs(repo_root, registry, invalid_days, families, max_parse_bytes=max_parse_bytes)
    for e in entries:
        _pre_bucket(e)
    for e in entries:
        if e.bucket is None:
            _prepare_secondary_and_cost(ctx, e)  # per-unit candle authority + cost authority, still pre-recompute
    units = _units(entries)  # also finalizes Q10 Index unit-incomplete gating
    planned = {e.path: (e.bucket or "admissible", e.bucket_reason) for e in entries}
    input_manifest = input_manifest_document(entries, registry)
    for art in input_manifest["artifacts"]:
        disposition, reason = planned[art["source_artifact"]]
        art.pop("bucket", None)
        art.pop("bucket_reason", None)
        art["planned_disposition"], art["planned_reason"] = disposition, reason
    run_id = compute_run_id(entries, registry, implementation_identity=implementation_identity,
                            frozen_core_identity=frozen_core_identity, run_config=run_config)
    for e in entries:  # outcomes are recorded in run_manifest, never in the input manifest
        if e.path in planned and planned[e.path][0] == "admissible":
            e.bucket, e.bucket_reason = None, ""

    # 2. recompute admissible units
    all_episodes: list[EpisodeRecord] = []
    all_aggregates: list[tuple[AggregateRecord, dict[str, Any]]] = []
    per_family: dict[str, dict[str, Any]] = {}

    def fam(label: str) -> dict[str, Any]:
        return per_family.setdefault(label, {
            "episodes": 0, "checkpoints": 0, "aggregates": 0, "records_considered": 0,
            "admissible_units": 0, "recomputed_units": 0, "recomputed_episode_units": 0,
            "recomputed_aggregate_units": 0, "partial_aggregate_units": 0, "blocked_missing_cost_policy": 0,
            "members_evaluated": 0, "members_missing": 0, "members_excluded": 0,
            "member_counts_complete": True,
        })

    for unit_id, unit_entries in units:
        label = unit_entries[0].family_label
        counts = fam(label)
        counts["admissible_units"] += 1
        pipeline = PIPELINES.get(unit_entries[0].family_key)
        try:
            if pipeline is None:
                raise PipelineNotImplementedError(f"no pipeline for {label}")
            result = pipeline(ctx, unit_entries)
        except RecomputeError as exc:
            for e in unit_entries:
                e.bucket, e.bucket_reason = exc.bucket.value, exc.reason.value
                e.bucket_detail = f"{type(exc).__name__}: {exc}"[:300]
            continue
        except (ValueError, KeyError, TypeError) as exc:  # unexpected adapter/contract defect: classified, never silent
            for e in unit_entries:
                e.bucket, e.bucket_reason = Bucket.ADAPTER_FAILURE.value, Reason.ADAPTER_FAILURE.value
                e.bucket_detail = f"{type(exc).__name__}: {exc}"[:300]
            continue
        for e in unit_entries:
            e.bucket, e.bucket_reason = Bucket.RECOMPUTED.value, ""
            e.companions = result.companions or e.companions
            e.stages = dict(result.stages)
        counts["recomputed_units"] += 1
        counts["recomputed_episode_units"] += 1
        if result.blocked_missing_cost:
            counts["blocked_missing_cost_policy"] += 1
            if result.aggregates:
                counts["partial_aggregate_units"] += 1
        elif result.aggregates:
            counts["recomputed_aggregate_units"] += 1
        counts["episodes"] += len(result.episodes)
        counts["checkpoints"] += sum(len(ep.checkpoints) for ep in result.episodes)
        counts["aggregates"] += len(result.aggregates)
        counts["records_considered"] += result.records_considered
        counts["member_counts_complete"] = counts["member_counts_complete"] and result.members_tracked
        counts["members_evaluated"] += result.members["evaluated"]
        counts["members_missing"] += result.members["missing"]
        counts["members_excluded"] += result.members["excluded"]
        all_episodes.extend(result.episodes)
        all_aggregates.extend(result.aggregates)

    # 3. global identity collision detection (fail closed, no auto-dedup)
    collisions = _check_collisions(all_episodes, all_aggregates)
    if collisions:
        for e in entries:
            if e.bucket == Bucket.RECOMPUTED.value:
                e.bucket, e.bucket_reason = Bucket.IDENTITY_COLLISION.value, Reason.CANONICAL_IDENTITY_COLLISION.value
        all_episodes, all_aggregates = [], []

    # 4. accounting: every artifact in exactly one bucket
    family_runs: list[FamilyRun] = []
    for spec in families:
        mine = [e for e in entries if e.family_label == spec.label]
        counts = dict(fam(spec.label)) if spec.label in per_family else dict(fam(spec.label))
        counts.update({
            "discovered_source_artifacts": len(mine),
            "registry_CLEAN": sum(e.registry_status == "CLEAN" for e in mine),
            "registry_FIELD_INVALID": sum(e.registry_status == "FIELD_INVALID" for e in mine),
            "registry_REVIEW_REQUIRED": sum(e.registry_status == "REVIEW_REQUIRED" for e in mine),
            "registry_QUARANTINED": sum(e.registry_status == "QUARANTINED" for e in mine),
            "registry_NO_RULE": sum(e.registry_status == "NO_RULE" for e in mine),
            "adapter_eligible": sum(e.adapter_eligible for e in mine),
            "adapter_blocked": sum(not e.adapter_eligible for e in mine),
            **{b.value: sum(e.bucket == b.value for e in mine) for b in Bucket},
        })
        counts["admissible_units"] += sum(e.secondary_blocked for e in mine)  # admitted, then candle-blocked
        counts.update({
            "blocked_missing_candles": sum(e.bucket == Bucket.SKIPPED_MISSING_INPUT.value
                                           and e.bucket_reason == Reason.MISSING_REQUIRED_SOURCE_INPUT.value for e in mine),
            "registry_skipped": counts[Bucket.SKIPPED_REGISTRY.value],
            "parse_failed": counts[Bucket.PARSE_FAILURE.value], "adapter_failed": counts[Bucket.ADAPTER_FAILURE.value],
        })
        secondary_reasons = [e.bucket_reason for e in mine if e.bucket == Bucket.BLOCKED_SECONDARY_AUTHORITY.value]
        unaccounted = len(mine) - sum(counts[b.value] for b in Bucket)
        counts["unaccounted"] = unaccounted
        st, reasons = _family_status(counts, secondary_reasons)
        if unaccounted:
            st, reasons = RunStatus.FAILED.value, reasons + ["UNACCOUNTED_INPUT"]
        family_runs.append(FamilyRun(spec.label, spec.family_key, spec.intended_for_uef5,
                                     rules.ADAPTER_ELIGIBILITY[spec.adapter_key]["adapter_status"], counts, st, reasons))

    intended = [f for f in family_runs if f.intended_for_uef5]
    if any(f.status == RunStatus.FAILED.value for f in family_runs):
        status = RunStatus.FAILED
    else:
        touched = [f for f in intended if f.counts["admissible_units"]]
        done = sum(f.counts["recomputed_units"] for f in intended)
        if touched and all(f.status == RunStatus.COMPLETE.value for f in touched):
            status = RunStatus.COMPLETE
        elif done:
            status = RunStatus.PARTIAL
        elif touched:
            status = RunStatus.BLOCKED
        else:
            status = RunStatus.COMPLETE
    totals = {k: sum(f.counts.get(k, 0) for f in family_runs) for k in (
        "discovered_source_artifacts", "episodes", "checkpoints", "aggregates", "records_considered",
        "recomputed_episode_units", "recomputed_aggregate_units", "partial_aggregate_units", "blocked_missing_cost_policy",
        "blocked_missing_candles", *[b.value for b in Bucket])}
    summary = {
        "schema_version": RECOMPUTE_SCHEMA_VERSION, "document": "recompute_summary", "run_id": run_id,
        "status": status.value, "totals": totals, "families": [f.to_dict() for f in family_runs],
        "identity_collisions_detail": collisions,
        "note": "canonical recompute result only; no legacy comparison and no parity claim (UEF-5.3)",
    }
    run_manifest = {
        "schema_version": RECOMPUTE_SCHEMA_VERSION, "document": "run_manifest", "run_id": run_id,
        "status": status.value, "recompute_version": RECOMPUTE_VERSION, "registry_version": registry.registry_version,
        "registry_digest": registry.digest(),
        "semantic_implementation_identity": dict(sorted(implementation_identity.items())),
        "frozen_core_manifest_identity": dict(sorted(frozen_core_identity.items())),
        "effective_run_config": dict(sorted(run_config.items())),
        "families": [{"family": f.label, "status": f.status, "reason_codes": sorted(f.reason_codes)} for f in family_runs],
        "artifact_outcomes": [{"path": e.path, "bucket": e.bucket, "bucket_reason": e.bucket_reason,
                              "bucket_detail": e.bucket_detail, "stages": e.stages} for e in entries],
        "canonical_outputs": ["episodes.jsonl", "aggregates.json"] if not collisions else [],
    }
    run = RecomputeRun(run_id, status, family_runs, summary, input_manifest, run_manifest,
                       all_episodes, all_aggregates, collisions)
    if out_root is not None:
        write_run(run, Path(out_root))
    return run


def write_run(run: RecomputeRun, out_root: Path) -> Path:
    out_dir = Path(out_root) / run.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = {
        "input_manifest.json": canonical_json(run.input_manifest) + "\n",
        "run_manifest.json": canonical_json(run.run_manifest) + "\n",
        "recompute_summary.json": canonical_json(run.summary) + "\n",
    }
    if not run.collisions:
        docs["episodes.jsonl"] = _serialize_episodes(run.episodes)
        docs["aggregates.json"] = _serialize_aggregates(run.aggregates)
    for name, text in docs.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")
    run.output_dir = out_dir
    return out_dir


__all__ = [
    "Bucket", "CANDLE_SOURCE_DIRS", "SecondaryCandleInputs", "OUTPUT_NAMESPACE", "PIPELINES", "REQUIRED_FIELDS",
    "RECOMPUTE_SCHEMA_VERSION", "RECOMPUTE_VERSION", "Reason", "RecomputeError", "RecomputeRun", "RunStatus",
    "adapter_implementation_identity", "classify_inputs", "compute_run_id", "cost_policy_from_persisted_cost_model",
    "effective_run_config", "frozen_core_manifest_identity", "run_historical_recompute",
    "semantic_implementation_identity", "write_run",
]
