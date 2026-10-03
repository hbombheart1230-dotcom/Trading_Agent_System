"""UEF-7 pure normalizer over an already-built Alpha Research Board v2 payload.

Read-only: never calls ``canonicalize_board``/``build_alpha_research_board``
differently, never re-derives a metric, never merges or deletes a candidate
row. See module docstring in ``libs/reporting/evaluation/uef7/__init__.py``
for the full scope boundary.

Central distinctions this module enforces in code (never only in prose):
  - candidate row != independent evidence population
  - same source artifact != same evidence population
  - different source artifact != proven independent evidence
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from libs.reporting.alpha_research_board.contracts import ROW_COLUMNS

from .model import (
    CANONICAL_METRIC_LINK_NOT_PROVEN,
    INDEPENDENCE_NOT_PROVEN,
    METRIC_AUTHORITY_DERIVED_VIEW,
    POPULATION_NOT_PROVABLE,
    NormalizationSummary,
    NormalizedAlphaBoard,
    NormalizedCandidateRow,
    SourceOverlapGroup,
    SourceReference,
    REPORT_SCHEMA_VERSION,
    canonical_source_reference,
)
from .run_identity import alpha_board_semantic_digest, compute_uef7_run_id

_EXPECTED_SCHEMA_VERSION = "alpha_research_board.v2"

_OPERATION_TRUTH_FIELDS = (
    "status",
    "operation_status",
    "fixed_validation_status",
    "production_promotion_status",
    "decision",
)


class UEF7NormalizationError(Exception):
    """Base class for UEF-7-local normalization errors."""


class UEF7InputContractError(UEF7NormalizationError):
    """Raised when the supplied board payload does not satisfy Alpha Board
    v2's own structural contract. UEF-7 never normalizes a structurally
    invalid board."""


class UEF7OperationTruthMismatchError(UEF7NormalizationError):
    """Raised if a normalized row's copied operation/promotion truth field
    ever disagrees with the source board row it was copied from. This is a
    defensive re-verification (item 20) -- it should never fire given this
    module's own copy-verbatim construction; if it does, that is a UEF-7
    implementation defect, and normalization fails closed rather than
    silently emitting a wrong truth value."""


def _mapping(value: Any) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _validate_input_contract(board: Mapping[str, Any]) -> None:
    schema_version = board.get("schema_version")
    if schema_version != _EXPECTED_SCHEMA_VERSION:
        raise UEF7InputContractError(f"schema_version={schema_version!r} != {_EXPECTED_SCHEMA_VERSION!r}")

    candidates = board.get("candidates") or []
    declared_count = board.get("candidate_count")
    if declared_count != len(candidates):
        raise UEF7InputContractError(f"candidate_count={declared_count!r} != len(candidates)={len(candidates)!r}")

    # Row-key exact-match validation against the FROZEN, imported
    # ``ROW_COLUMNS`` authority (libs.reporting.alpha_research_board.contracts)
    # -- never a second, UEF-7-invented row schema, and never the board
    # payload's OWN ``row_columns`` field, which an adversarial input could
    # extend in lockstep with its candidate rows to smuggle a
    # contract-external field past validation while it still influences
    # the Board semantic digest. The board's published ``row_columns``
    # must itself match the frozen, ORDERED authority exactly (Alpha Board
    # v2 publishes it as an ordered contract -- reordering it is itself a
    # contract violation, not normalized/re-sorted away here). Only after
    # that top-level check passes is each candidate row's key SET checked
    # against the same frozen authority. Fail closed BEFORE anything can
    # reach the Board semantic digest, run-id generation, or
    # normalized-row production.
    declared_row_columns = tuple(board.get("row_columns") or ())
    if declared_row_columns != ROW_COLUMNS:
        raise UEF7InputContractError(
            f"board.row_columns={declared_row_columns!r} != the frozen Alpha Board v2 ROW_COLUMNS={ROW_COLUMNS!r}"
        )

    expected_row_keys = set(ROW_COLUMNS)
    for row in candidates:
        row_mapping = _mapping(row)
        actual_keys = set(row_mapping.keys())
        if actual_keys != expected_row_keys:
            missing = sorted(expected_row_keys - actual_keys)
            extra = sorted(actual_keys - expected_row_keys)
            raise UEF7InputContractError(
                f"candidate_id={row_mapping.get('candidate_id')!r} keys != frozen ROW_COLUMNS "
                f"(missing={missing}, extra={extra})"
            )

    row_ids = [str(_mapping(row).get("candidate_id")) for row in candidates]
    if len(set(row_ids)) != len(row_ids):
        duplicates = sorted({cid for cid in row_ids if row_ids.count(cid) > 1})
        raise UEF7InputContractError(f"duplicate candidate_id(s) in board.candidates: {duplicates}")

    declared_ids = list(board.get("candidate_ids") or [])
    if declared_ids != row_ids:
        raise UEF7InputContractError(
            f"board.candidate_ids={declared_ids!r} disagrees with candidates[].candidate_id order={row_ids!r}"
        )

    integrity_status = _mapping(board.get("integrity")).get("status")
    if integrity_status == "FAIL_CONTRACT":
        raise UEF7InputContractError("board.integrity.status == FAIL_CONTRACT -- refusing to normalize")


def _source_references(row: Mapping[str, Any]) -> tuple[tuple[SourceReference, ...], tuple[str, ...]]:
    raw = row.get("source_artifacts") or []
    refs: list[SourceReference] = []
    anomalies: list[str] = []
    candidate_id = str(row.get("candidate_id") or "")

    if not raw:
        anomalies.append(f"MISSING_SOURCE_REFERENCE:{candidate_id}")

    # Defect A fix: duplicate detection uses the FULL canonical
    # SourceReference (source_key + path + available + error) as its one
    # identity authority -- never a partial (source_key, path) key. Two
    # occurrences that agree on source_key/path but disagree on
    # available/error are DIFFERENT references, not a duplicate.
    seen: dict[str, int] = {}
    for entry in raw:
        entry = _mapping(entry)
        source_key = str(entry.get("source_key") or "")
        path = entry.get("path")
        available = entry.get("available")
        error = entry.get("error")
        ref = SourceReference(source_key=source_key, path=path, available=available, error=error)
        refs.append(ref)

        full_key = canonical_source_reference(ref)
        seen[full_key] = seen.get(full_key, 0) + 1
        if seen[full_key] > 1:
            anomalies.append(f"DUPLICATE_SOURCE_REFERENCE:{source_key}")
        if not path or not isinstance(path, str):
            anomalies.append(f"NON_FILE_SOURCE_DESCRIPTOR:{source_key}")
        if available is False:
            anomalies.append(f"UNAVAILABLE_SOURCE:{source_key}")
        if error:
            anomalies.append(f"SOURCE_ERROR:{source_key}:{error}")

    return tuple(refs), tuple(anomalies)


def _source_bundle_id(refs: Sequence[SourceReference]) -> str:
    """Canonical, order-independent, MULTIPLICITY-preserving digest over a
    row's own FULL source references (Defect A fix: the same canonical
    ``SourceReference`` serializer used everywhere else in this module,
    never a separate partial-key definition). Same full refs in different
    order -> same id; a ref added/removed/changed on ANY of its four
    fields (including available/error) -> different id; duplicate refs are
    never silently set-deduplicated before hashing."""

    rows = sorted(canonical_source_reference(r) for r in refs)
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _net_metrics_view(row: Mapping[str, Any]) -> dict:
    metrics = _mapping(row.get("net_metrics"))
    return {
        "evidence_cohort": metrics.get("cohort"),
        "sample_count": metrics.get("sample_count"),
        "window_count": metrics.get("window_count"),
        "win_rate": metrics.get("win_rate"),
        "avg_net_return_pct": metrics.get("avg_net_return_pct"),
        "profit_factor": metrics.get("profit_factor"),
        "max_drawdown_pct": metrics.get("max_drawdown_pct"),
        "coverage": metrics.get("coverage"),
        "avg_mfe_pct": metrics.get("avg_mfe_pct"),
        "avg_mae_pct": metrics.get("avg_mae_pct"),
    }


def _build_source_groups(rows: Sequence[Mapping[str, Any]], refs_by_candidate: Mapping[str, tuple[SourceReference, ...]]) -> tuple[SourceOverlapGroup, ...]:
    """Groups candidate rows by shared FULL source provenance reference
    (Defect A fix: source_key + path + available + error together -- the
    same canonical identity ``_source_bundle_id``/duplicate-detection use,
    never a separate partial (source_key, path) definition). Two rows
    citing the same source_key/path but disagreeing on available/error are
    NEVER placed in the same group. Membership is per-CANDIDATE (a row
    citing the same full reference twice still counts once in a group's
    candidate_ids -- the group answers "which candidates cite this exact
    provenance", not "how many times"). Only ever emitted for
    candidate_count > 1 (item 10)."""

    members: dict[str, tuple[SourceReference, list[str]]] = {}
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        seen_keys_this_row: set = set()
        for ref in refs_by_candidate.get(candidate_id, ()):
            key = canonical_source_reference(ref)
            if key in seen_keys_this_row:
                continue
            seen_keys_this_row.add(key)
            if key not in members:
                members[key] = (ref, [])
            members[key][1].append(candidate_id)

    groups: list[SourceOverlapGroup] = []
    for key in sorted(members.keys()):
        ref, candidate_ids = members[key]
        if len(candidate_ids) <= 1:
            continue
        group_id = "SRCGRP_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        groups.append(
            SourceOverlapGroup(
                source_group_id=group_id, source_key=ref.source_key, path=ref.path,
                available=ref.available, error=ref.error,
                candidate_ids=tuple(candidate_ids), candidate_count=len(candidate_ids),
            )
        )
    return tuple(groups)


def normalize_alpha_board(board: Mapping[str, Any], *, normalizer_implementation_digest_value: str) -> NormalizedAlphaBoard:
    """Pure normalization over an already-built Alpha Board v2 payload
    (from ``build_alpha_research_board``/``canonicalize_board`` -- never
    called differently or re-derived here). Fails closed on a structurally
    invalid board (``UEF7InputContractError``) or on a copied operation-
    truth field disagreeing with its source (``UEF7OperationTruthMismatchError``,
    defensive -- should never fire)."""

    _validate_input_contract(board)

    raw_rows = list(board.get("candidates") or [])

    refs_by_candidate: dict[str, tuple[SourceReference, ...]] = {}
    anomalies_by_candidate: dict[str, tuple[str, ...]] = {}
    for row in raw_rows:
        candidate_id = str(row.get("candidate_id") or "")
        refs, anomalies = _source_references(row)
        refs_by_candidate[candidate_id] = refs
        anomalies_by_candidate[candidate_id] = anomalies

    source_groups = _build_source_groups(raw_rows, refs_by_candidate)
    groups_by_candidate: dict[str, list[SourceOverlapGroup]] = {}
    for group in source_groups:
        for candidate_id in group.candidate_ids:
            groups_by_candidate.setdefault(candidate_id, []).append(group)

    normalized_rows: list[NormalizedCandidateRow] = []
    for row in raw_rows:
        candidate_id = str(row.get("candidate_id") or "")
        refs = refs_by_candidate[candidate_id]
        anomalies = anomalies_by_candidate[candidate_id]
        candidate_groups = groups_by_candidate.get(candidate_id, [])
        shared_source_group_ids = tuple(g.source_group_id for g in candidate_groups)
        shared_source_candidate_ids = tuple(
            sorted({cid for g in candidate_groups for cid in g.candidate_ids if cid != candidate_id})
        )

        metrics_view = _net_metrics_view(row)

        normalized_row = NormalizedCandidateRow(
            question_id=str(row.get("question_id") or ""),
            candidate_id=candidate_id,
            target_horizon=str(row.get("target_horizon") or ""),
            status=str(row.get("status") or ""),
            operation_status=str(row.get("operation_status") or ""),
            fixed_validation_status=str(row.get("fixed_validation_status") or ""),
            production_promotion_status=str(row.get("production_promotion_status") or ""),
            decision=str(row.get("decision") or ""),
            evidence_cohort=metrics_view["evidence_cohort"],
            sample_count=metrics_view["sample_count"],
            window_count=metrics_view["window_count"],
            win_rate=metrics_view["win_rate"],
            avg_net_return_pct=metrics_view["avg_net_return_pct"],
            profit_factor=metrics_view["profit_factor"],
            max_drawdown_pct=metrics_view["max_drawdown_pct"],
            coverage=metrics_view["coverage"],
            avg_mfe_pct=metrics_view["avg_mfe_pct"],
            avg_mae_pct=metrics_view["avg_mae_pct"],
            metric_authority=METRIC_AUTHORITY_DERIVED_VIEW,
            canonical_metric_link_status=CANONICAL_METRIC_LINK_NOT_PROVEN,
            source_references=refs,
            source_anomalies=anomalies,
            source_bundle_id=_source_bundle_id(refs),
            shared_source_group_ids=shared_source_group_ids,
            shared_source_candidate_ids=shared_source_candidate_ids,
            # No direct UEF-6-style aggregation-member population authority
            # is ever supplied to UEF-7 in this phase -- never inferred
            # from candidate_id/question_id/sample_count/target_horizon/
            # metric values/source path/source key/same day/same
            # hypothesis (item 3).
            population_identity_status=POPULATION_NOT_PROVABLE,
            evidence_independence_status=INDEPENDENCE_NOT_PROVEN,
        )
        for field_name in _OPERATION_TRUTH_FIELDS:
            if str(row.get(field_name) or "") != str(getattr(normalized_row, field_name)):
                raise UEF7OperationTruthMismatchError(
                    f"candidate_id={candidate_id!r} field={field_name!r}: normalized value "
                    f"{getattr(normalized_row, field_name)!r} != source board value {row.get(field_name)!r}"
                )
        normalized_rows.append(normalized_row)

    candidate_row_count = len(normalized_rows)
    rows_with_shared_source_count = sum(1 for r in normalized_rows if r.shared_source_group_ids)
    unresolved_population_candidate_count = sum(
        1 for r in normalized_rows if r.population_identity_status != "DIRECT_POPULATION_IDENTITY_PROVEN"
    )
    summary = NormalizationSummary(
        candidate_row_count=candidate_row_count,
        shared_source_group_count=len(source_groups),
        rows_with_shared_source_count=rows_with_shared_source_count,
        proven_population_group_count=0,
        unresolved_population_candidate_count=unresolved_population_candidate_count,
    )

    board_digest = alpha_board_semantic_digest(board)
    run_id = compute_uef7_run_id(
        source_board_semantic_digest=board_digest,
        normalizer_implementation_digest_value=normalizer_implementation_digest_value,
        normalization_schema_version=REPORT_SCHEMA_VERSION,
    )

    return NormalizedAlphaBoard(
        schema_version=REPORT_SCHEMA_VERSION,
        source_board_schema_version=str(board.get("schema_version") or ""),
        source_board_contract_version=str(board.get("contract_version") or ""),
        through_day=str(board.get("through_day") or ""),
        candidate_row_count=candidate_row_count,
        candidate_ids=tuple(r.candidate_id for r in normalized_rows),
        normalized_rows=tuple(normalized_rows),
        source_groups=source_groups,
        normalization_summary=summary,
        source_board_semantic_digest=board_digest,
        normalizer_implementation_digest=normalizer_implementation_digest_value,
        uef7_run_id=run_id,
    )


__all__ = [
    "UEF7NormalizationError",
    "UEF7InputContractError",
    "UEF7OperationTruthMismatchError",
    "normalize_alpha_board",
]
