"""Classifies one legacy-vs-canonical comparison unit.

This module makes NO network/file calls and computes NO metric of its own
(the one exception, ``CanonicalAggregate.derived_win_rate``, only reapplies
legacy's OWN ``win_count / evaluated_count`` arithmetic to canonical's real
counts -- it never invents a new formula). It reasons over already-loaded
legacy rows and canonical aggregates/outcomes and assigns a bounded
(source_alignment, result, reason) verdict, using the REAL frozen UEF-3A
metric contract (``MetricComputationStatus.VALID``, ``SamplePopulation.
evaluated_count``, ``WinLossFlatPopulation``) -- not the first delivery's
incorrect ``"COMPUTED"``/``episode_count==0`` assumptions.

Core Correction 1 (Codex audit) fixed:
 - HIGH-1: PF/MDD status comparisons now use ``VALID``, not ``"COMPUTED"``.
 - population comparisons now use ``SamplePopulation.evaluated_count``
   (matching legacy's own ``count`` = win+loss+flat definition), never
   ``AggregateRecord.episode_count`` (a lineage-only field).
 - MDD is now actually compared, gated on real population-alignment
   evidence (``sample_count_in_curve == evaluated_count``), never silently
   dropped.
 - win_count/loss_count/flat_count are now compared (canonical DOES persist
   them, on ``profit_factor.population``).
 - Q12 Calc1's missing "view" dimension is no longer used to *infer*
   population difference -- real counts are compared per candidate legacy
   view, and only genuinely-unmatched populations become NON_COMPARABLE.
 - NON_COMPARABLE is never used as a catch-all for a numeric disagreement,
   a missing join, or a reader bug -- those remain UNEXPLAINED until a real
   structural reason is established (item 15's guard).
"""

from __future__ import annotations

import math
from typing import Optional

from .canonical_run import CanonicalAggregate, CanonicalRun
from .comparison_unit import LEGACY_ONLY_METRIC_FIELDS, ComparisonRecord, ComparisonUnitIdentity
from .legacy_forward_returns import LegacyHorizonView
from .legacy_opportunity_engine import LegacyQ11ExitDay
from .taxonomy import ComparisonResult, DivergenceReason, SourceAlignment

PF_EPSILON = 1e-6
MDD_EPSILON = 1e-3
WIN_RATE_EPSILON = 1e-4

_COST_POLICY_REASON_MARKERS = ("COST_POLICY",)


def compute_hash_match(canonical_run: CanonicalRun, legacy_path: str, legacy_hash: str) -> str:
    """HASH_MATCH / HASH_MISMATCH / NO_RECORDED_HASH against UEF-5.2's own
    ``input_manifest.json['artifacts'][].primary_source_hash`` -- UEF-5.2's
    OWN recorded hash of the bytes it actually consumed for this artifact.
    Never fabricated: if UEF-5.2 recorded nothing, this says so explicitly."""

    recorded = canonical_run.recorded_source_hash_for_path(legacy_path)
    if recorded is None:
        return "NO_RECORDED_HASH"
    return "HASH_MATCH" if recorded == legacy_hash else "HASH_MISMATCH"


def source_alignment_for(hash_match: str) -> SourceAlignment:
    """Source-alignment micro-fix: ``source_alignment`` answers ONLY "did
    the two sides evaluate the same proven source evidence?" -- it is
    fully independent of the numeric comparison OUTCOME. A unit can
    legitimately be ``EXACT_SAME_SOURCE`` (positively proven, via UEF-5.2's
    own recorded hash, to be the exact bytes UEF-5.2 itself consumed) while
    its comparison result is ``UNEXPLAINED_DIVERGENCE`` (the two sides
    disagree on the same evidence) -- this is precisely one of the cases
    UEF-5.3 exists to surface, and coupling source identity to whether the
    metrics happened to match would hide it.

    ``HASH_MISMATCH`` must never produce ``EXACT_SAME_SOURCE`` (the current
    bytes are proven to differ from what UEF-5.2 consumed). ``NO_RECORDED_HASH``
    is unproven, not positively contradicted, so it also falls back to the
    existing, more conservative ``SAME_PRIMARY_DIFFERENT_SECONDARY`` state
    -- no new taxonomy member is introduced for either case."""

    if hash_match == "HASH_MATCH":
        return SourceAlignment.EXACT_SAME_SOURCE
    return SourceAlignment.SAME_PRIMARY_DIFFERENT_SECONDARY


def canonical_lineage_valid(aggregate: CanonicalAggregate) -> tuple:
    """Structurally verifies the canonical aggregate's OWN lineage claim --
    never trusts the ``lineage_status == "FULL"`` label by itself (UEF-5.3
    Final Population Proof Fix). The frozen canonical record contract
    (``canonical/record.py``'s ``AggregateRecord.__post_init__``) already
    enforces, at construction time, that a genuine ``FULL``-lineage
    ``AggregateRecord`` has no duplicate ``source_episode_ids`` and
    ``len(source_episode_ids) == episode_count`` -- but UEF-5.3 only reads
    already-serialized JSON off disk, which could (via corruption, a bug in
    a different producer, or an adversarial/malformed file) claim
    ``"FULL"`` without actually satisfying that invariant. This function
    re-derives the SAME structural check independently, rather than
    trusting the label, so a malformed claim can never smuggle a false
    population proof into UEF-5.3.

    Returns (valid: bool, reason: str)."""

    if aggregate.lineage_status != "FULL":
        return False, f"lineage_status={aggregate.lineage_status!r} is not 'FULL'"
    ids = aggregate.source_episode_ids
    if not ids:
        return False, "lineage_status='FULL' but source_episode_ids is empty/absent"
    if len(set(ids)) != len(ids):
        return False, "source_episode_ids contains duplicate IDs -- 'FULL' label does not structurally hold"
    if len(set(ids)) != aggregate.episode_count:
        return False, (
            f"len(unique(source_episode_ids))={len(set(ids))} != episode_count={aggregate.episode_count} "
            f"-- 'FULL' label does not structurally hold"
        )
    return True, "lineage_status='FULL' structurally verified: unique source_episode_ids fully cover episode_count"


def population_identity_proven(aggregate: CanonicalAggregate, legacy_member_ids: Optional[frozenset]) -> tuple:
    """Full population-identity proof gate (UEF-5.3 Final Population Proof
    Fix). Two conditions, BOTH required:

    1. ``canonical_lineage_valid(aggregate)`` -- the canonical side's own
       membership enumeration is structurally verified, not merely labeled.
    2. The legacy view's own member-identity set is available AND equals
       the canonical membership set EXACTLY (normalized set comparison).

    Neither condition alone is sufficient -- a structurally-valid canonical
    lineage does NOT by itself prove the legacy view's population is the
    SAME population; count equality, date equality, horizon equality, or
    symbol-count equality are NEVER accepted as substitutes. Never
    reconstructs, invents, or heuristically derives membership: when the
    legacy artifact does not persist member identities at all (the real,
    current situation -- see ``LegacyHorizonView.member_ids``'s own
    docstring), this correctly and honestly returns "not proven".

    Returns (proven: bool, reason: str)."""

    lineage_ok, lineage_reason = canonical_lineage_valid(aggregate)
    if not lineage_ok:
        return False, f"CANONICAL_POPULATION_LINEAGE_NOT_PROVEN: {lineage_reason}"
    if legacy_member_ids is None:
        return False, (
            "canonical lineage is structurally valid, but this legacy view's own member identities are not "
            "available from the current legacy artifact -- population equivalence cannot be positively "
            "established without them (count/date/horizon/symbol-count equality are never accepted as substitutes)"
        )
    canonical_ids = frozenset(aggregate.source_episode_ids)
    legacy_ids = frozenset(legacy_member_ids)
    if canonical_ids != legacy_ids:
        return False, (
            f"membership mismatch: canonical source_episode_ids={sorted(canonical_ids)} != "
            f"legacy member_ids={sorted(legacy_ids)}"
        )
    return True, "canonical lineage structurally valid and its member-ID set exactly equals the legacy view's own member-ID set"


def _map_blocked_reason(bucket: str, bucket_reason: str) -> DivergenceReason:
    reason_text = f"{bucket} {bucket_reason}".upper()
    if bucket == "blocked_secondary_authority":
        return DivergenceReason.LEGACY_DATA_AUTHORITY_BLOCKED
    if bucket == "skipped_registry":
        return DivergenceReason.ELIGIBILITY_DIFFERENCE
    if any(marker in reason_text for marker in _COST_POLICY_REASON_MARKERS):
        return DivergenceReason.COST_POLICY_DIFFERENCE
    return DivergenceReason.MISSING_INPUT


def _legacy_json(legacy: LegacyHorizonView) -> dict:
    return {
        "count": legacy.count,
        "win_count": legacy.win_count,
        "loss_count": legacy.loss_count,
        "flat_count": legacy.flat_count,
        "win_rate": legacy.win_rate,
        "average_return_pct": legacy.average_return_pct,
        "profit_factor": legacy.profit_factor,
        "maximum_drawdown_pct": legacy.maximum_drawdown_pct,
    }


def _canonical_json(aggregate: CanonicalAggregate) -> dict:
    return {
        "canonical_aggregate_id": aggregate.canonical_aggregate_id,
        "evaluation_record_id": aggregate.evaluation_record_id,
        "evaluated_count": aggregate.pf_sample.evaluated_count if aggregate.pf_sample else None,
        "sample_count": aggregate.pf_sample.sample_count if aggregate.pf_sample else None,
        "win_count": aggregate.pf_population.win_count,
        "loss_count": aggregate.pf_population.loss_count,
        "flat_count": aggregate.pf_population.flat_count,
        "derived_win_rate": aggregate.derived_win_rate(),
        "profit_factor_status": aggregate.profit_factor.status,
        "profit_factor_value": aggregate.profit_factor.value,
        "max_drawdown_status": aggregate.max_drawdown.status,
        "max_drawdown_value": aggregate.max_drawdown.value,
        "mdd_sample_count_in_curve": aggregate.mdd_sample_count_in_curve,
    }


def _make_unit(
    family_key: str,
    legacy: LegacyHorizonView,
    canonical_run_id: str,
    canonical_aggregate_id: str = "",
    canonical_content_digest: str = "",
    reader_profile_identity: str = "",
) -> ComparisonUnitIdentity:
    return ComparisonUnitIdentity(
        family=family_key,
        trading_date=legacy.day,
        source_path=legacy.path,
        legacy_content_hash=legacy.content_hash,
        canonical_run_id=canonical_run_id,
        canonical_aggregate_id=canonical_aggregate_id,
        canonical_content_digest=canonical_content_digest,
        reader_profile_identity=reader_profile_identity,
        view=legacy.view,
        horizon_label=legacy.horizon,
        cost_treatment=legacy.cost_treatment,
    )


def _compare_net_population_and_metrics(
    legacy: LegacyHorizonView,
    aggregate: CanonicalAggregate,
) -> tuple:
    """Returns (result, reason, detail, extra_canonical_fields,
    non_comparable_metric_fields) for one net-cost-treatment cell whose
    (view, horizon) join to a real canonical aggregate is already
    established. Implements the corrected population-first, then
    metric-by-metric comparison order."""

    return _compare_population_and_metrics(
        legacy_count=legacy.count,
        legacy_win=legacy.win_count,
        legacy_loss=legacy.loss_count,
        legacy_flat=legacy.flat_count,
        legacy_pf=legacy.profit_factor,
        legacy_mdd=legacy.maximum_drawdown_pct,
        aggregate=aggregate,
    )


def _compare_population_and_metrics(
    legacy_count: Optional[int],
    legacy_win: Optional[int],
    legacy_loss: Optional[int],
    legacy_flat: Optional[int],
    legacy_pf: Optional[float],
    legacy_mdd: Optional[float],
    aggregate: CanonicalAggregate,
) -> tuple:
    """Family-agnostic version of the population-first, then
    metric-by-metric comparison, taking primitives instead of a
    ``LegacyHorizonView`` so it can be reused by both Q10 Semiconductor/
    Q12 Calc1 (``summary.horizons[]`` shape) and Q11 v2
    (``summary.{trade_count,win_rate,profit_factor}`` shape -- win/loss/flat
    derived directly from the raw ``trades[].net_return_pct`` array using
    the UEF-3A contract's own WIN/LOSS/FLAT rule, never inferred from a
    rounded ``win_rate`` ratio)."""

    non_comparable_metric_fields: list = []
    comparisons: dict = {}

    def pop_entry(comparable, status, legacy_value, canonical_value, reason):
        comparisons["population"] = {
            "metric": "population", "comparable": comparable, "status": status,
            "legacy_value": legacy_value, "canonical_value": canonical_value, "reason": reason,
        }

    def not_attempted_entry(name, reason):
        comparisons[name] = {
            "metric": name, "comparable": False, "status": "NOT_ATTEMPTED",
            "legacy_value": None, "canonical_value": None, "reason": reason,
        }

    if aggregate.pf_sample is None:
        reason = "canonical aggregate has no recorded sample population (profit_factor.sample absent)"
        pop_entry(False, "NON_COMPARABLE", legacy_count, None, reason)
        for name in ("win_count", "loss_count", "flat_count", "profit_factor", "max_drawdown"):
            not_attempted_entry(name, "population comparison failed first")
        return (
            ComparisonResult.NON_COMPARABLE, DivergenceReason.MISSING_INPUT, reason,
            {"metric_comparisons": comparisons}, list(comparisons.keys() - {"population"}),
        )

    canonical_evaluated = aggregate.pf_sample.evaluated_count

    if legacy_count is None:
        reason = "legacy cell has no 'count' field to compare against canonical's evaluated_count"
        pop_entry(False, "NON_COMPARABLE", None, canonical_evaluated, reason)
        for name in ("win_count", "loss_count", "flat_count", "profit_factor", "max_drawdown"):
            not_attempted_entry(name, "population comparison failed first")
        return (
            ComparisonResult.NON_COMPARABLE, DivergenceReason.MISSING_INPUT, reason,
            {"metric_comparisons": comparisons}, list(comparisons.keys() - {"population"}),
        )

    if canonical_evaluated != legacy_count:
        reason = (
            f"legacy evaluated population (count)={legacy_count} vs canonical evaluated_count={canonical_evaluated} "
            f"-- both are the SAME population definition (missing-filtered win+loss+flat denominator; see "
            f"UEF-3A SamplePopulation contract) so this is a real, evidenced population-size difference"
        )
        pop_entry(True, "DIFFERENT", legacy_count, canonical_evaluated, reason)
        for name in ("win_count", "loss_count", "flat_count", "profit_factor", "max_drawdown"):
            not_attempted_entry(name, "population sizes differ")
        return (
            ComparisonResult.EXPLAINED_DIVERGENCE, DivergenceReason.SOURCE_POPULATION_DIFFERENCE, reason,
            {"metric_comparisons": comparisons}, list(comparisons.keys() - {"population"}),
        )

    if canonical_evaluated == 0:
        reason = "EXACT_EMPTY: both legacy and canonical evaluated populations are 0 for this cell"
        pop_entry(True, "MATCH", legacy_count, canonical_evaluated, reason)
        for name in ("win_count", "loss_count", "flat_count", "profit_factor", "max_drawdown"):
            not_attempted_entry(name, "population is empty on both sides")
        return (
            ComparisonResult.EXACT_MATCH, None, reason,
            {"metric_comparisons": comparisons}, list(comparisons.keys() - {"population"}),
        )

    pop_entry(True, "MATCH", legacy_count, canonical_evaluated, "populations align and are non-empty")

    # Compare each available metric independently before reducing the unit
    # verdict -- a non-comparable metric must never suppress a comparable
    # one (metric independence, preserved).
    differences = []
    matched = []

    def compare(name, available, left, right, epsilon=0, unavailable_reason=""):
        if not available:
            non_comparable_metric_fields.append(name)
            comparisons[name] = {
                "metric": name, "comparable": False, "status": "NON_COMPARABLE",
                "legacy_value": left, "canonical_value": right, "reason": unavailable_reason,
            }
            return
        equal = left == right if epsilon == 0 else math.isclose(left, right, rel_tol=0, abs_tol=epsilon)
        comparisons[name] = {
            "metric": name, "comparable": True, "status": "MATCH" if equal else "UNEXPLAINED",
            "legacy_value": left, "canonical_value": right,
            "reason": "" if equal else "same population but this metric's values differ; no established reason code",
        }
        if equal:
            matched.append(name)
        else:
            differences.append(f"{name} differs: legacy={left} canonical={right}")

    def numeric(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    for name, left, right in (
        ("win_count", legacy_win, aggregate.pf_population.win_count),
        ("loss_count", legacy_loss, aggregate.pf_population.loss_count),
        ("flat_count", legacy_flat, aggregate.pf_population.flat_count),
    ):
        compare(name, numeric(left) and numeric(right), left, right, unavailable_reason="one or both sides missing/non-numeric")

    pf = aggregate.profit_factor
    compare(
        "profit_factor", pf.is_valid() and numeric(pf.value) and numeric(legacy_pf), legacy_pf, pf.value, PF_EPSILON,
        unavailable_reason=f"canonical profit_factor status={pf.status!r} is not VALID" if not pf.is_valid() else "legacy or canonical value missing/non-numeric",
    )
    mdd = aggregate.max_drawdown
    mdd_population_aligned = aggregate.mdd_sample_count_in_curve == canonical_evaluated
    compare(
        "max_drawdown",
        mdd.is_valid() and numeric(mdd.value) and numeric(legacy_mdd) and mdd_population_aligned,
        legacy_mdd, mdd.value, MDD_EPSILON,
        unavailable_reason=(
            f"canonical max_drawdown status={mdd.status!r}" if not mdd.is_valid()
            else "mdd curve population misaligned with evaluated population" if not mdd_population_aligned
            else "legacy has no maximum_drawdown_pct"
        ),
    )
    extra = {"metric_comparisons": comparisons}
    unavailable = "; ".join(f"{name} NOT compared" for name in non_comparable_metric_fields)
    if differences:
        return (ComparisonResult.UNEXPLAINED_DIVERGENCE, DivergenceReason.UNEXPLAINED,
                "same evaluated population but " + "; ".join(differences) + "; " + unavailable,
                extra, non_comparable_metric_fields)
    if matched:
        return (ComparisonResult.EXACT_MATCH, None,
                "EXACT_NONEMPTY: comparable fields match: " + ", ".join(matched) + "; " + unavailable,
                extra, non_comparable_metric_fields)
    return (ComparisonResult.NON_COMPARABLE, DivergenceReason.MISSING_INPUT,
            "No metric has comparable values; " + unavailable, extra, non_comparable_metric_fields)


def classify_q10_semiconductor_cell(
    legacy: LegacyHorizonView,
    canonical_run: CanonicalRun,
    family_key: str,
    canonical_run_id: str,
    canonical_content_digest: str = "",
    reader_profile_identity: str = "",
) -> tuple:
    """Returns (ComparisonRecord, consumed_canonical_aggregate_or_None).

    ``consumed_canonical_aggregate`` is the exact ``CanonicalAggregate``
    object this legacy cell was joined against (identity-compared by the
    orchestrator to remove it from the canonical universe before computing
    canonical-only leftovers -- HIGH-3's independent-universe accounting)."""

    outcome = canonical_run.outcome_for_path(legacy.path)
    hash_match = compute_hash_match(canonical_run, legacy.path, legacy.content_hash)
    non_comparable_legacy_fields = list(LEGACY_ONLY_METRIC_FIELDS)

    def mk(canonical_aggregate_id=""):
        return _make_unit(family_key, legacy, canonical_run_id, canonical_aggregate_id, canonical_content_digest, reader_profile_identity)

    if outcome is None:
        return (
            ComparisonRecord(
                unit=mk(),
                source_alignment=SourceAlignment.MISSING_CANONICAL_SOURCE,
                result=ComparisonResult.NON_COMPARABLE,
                reason=DivergenceReason.MISSING_INPUT,
                detail="UEF-5.2 run has no artifact_outcome entry for this legacy source path at all",
                legacy=_legacy_json(legacy),
                canonical=None,
                non_comparable_legacy_fields=non_comparable_legacy_fields,
                hash_match=hash_match,
            ),
            None,
        )

    if outcome.bucket != "recomputed":
        return (
            ComparisonRecord(
                unit=mk(),
                source_alignment=SourceAlignment.LEGACY_UNATTESTED,
                result=ComparisonResult.BLOCKED,
                reason=_map_blocked_reason(outcome.bucket, outcome.bucket_reason),
                detail=outcome.bucket_detail or outcome.bucket_reason or outcome.bucket,
                legacy=_legacy_json(legacy),
                canonical={"bucket": outcome.bucket, "bucket_reason": outcome.bucket_reason},
                non_comparable_legacy_fields=non_comparable_legacy_fields,
                hash_match=hash_match,
            ),
            None,
        )

    candidates = [
        a
        for a in canonical_run.aggregates_for_path(legacy.path)
        if a.view == legacy.view and a.horizon_label == legacy.horizon
    ]
    if not candidates:
        return (
            ComparisonRecord(
                unit=mk(),
                source_alignment=SourceAlignment.SAME_PRIMARY_DIFFERENT_SECONDARY,
                result=ComparisonResult.UNEXPLAINED_DIVERGENCE,
                reason=DivergenceReason.UNEXPLAINED,
                detail=(
                    f"canonical run recomputed this source artifact but produced no aggregate for "
                    f"view={legacy.view!r} horizon={legacy.horizon!r} (canonical's own horizon set for this unit "
                    f"is otherwise a superset of legacy's, so this specific gap is not yet explained)"
                ),
                legacy=_legacy_json(legacy),
                canonical={"bucket": outcome.bucket},
                non_comparable_legacy_fields=non_comparable_legacy_fields,
                hash_match=hash_match,
            ),
            None,
        )

    aggregate = candidates[0]
    unit = mk(aggregate.canonical_aggregate_id)

    if legacy.cost_treatment == "gross":
        return (
            ComparisonRecord(
                unit=unit,
                source_alignment=SourceAlignment.SAME_PRIMARY_DIFFERENT_SECONDARY,
                result=ComparisonResult.NON_COMPARABLE,
                reason=DivergenceReason.COST_POLICY_DIFFERENCE,
                detail="canonical UEF-5.2 aggregates are always cost-applied; it persists no gross/uncosted aggregate to compare against",
                legacy=_legacy_json(legacy),
                canonical=_canonical_json(aggregate),
                non_comparable_legacy_fields=non_comparable_legacy_fields,
                hash_match=hash_match,
            ),
            aggregate,
        )

    result, reason, detail, extra, non_comparable_metric_fields = _compare_net_population_and_metrics(legacy, aggregate)
    record = ComparisonRecord(
        unit=unit,
        source_alignment=source_alignment_for(hash_match),
        result=result,
        reason=reason,
        detail=detail,
        legacy=_legacy_json(legacy),
        canonical=_canonical_json(aggregate),
        non_comparable_legacy_fields=non_comparable_legacy_fields + non_comparable_metric_fields,
        hash_match=hash_match,
        metric_comparisons=extra.get("metric_comparisons"),
    )
    return record, aggregate


def classify_q12_calc1_day(
    legacy_views: list,
    canonical_run: CanonicalRun,
    family_key: str,
    canonical_run_id: str,
    canonical_content_digest: str = "",
    reader_profile_identity: str = "",
) -> tuple:
    """Handles one (path, horizon) group of Q12 Calc1 legacy cells (up to 3
    views x 2 cost treatments) against canonical's single undifferentiated
    per-horizon aggregate -- WITHOUT inferring population difference merely
    from the missing view dimension (Core Correction 1 items 13-15).

    Population identity is established by REAL EVIDENCE: canonical's
    evaluated_count is compared against each candidate legacy view's own
    count. A view is only treated as "the" matched population when its
    count equals canonical's evaluated_count; if none match, or the
    situation cannot be resolved from evidence, the cells are NON_COMPARABLE
    with an evidence-based reason -- never silently assumed different.

    Returns (list[ComparisonRecord], consumed_canonical_aggregate_or_None).
    """

    assert legacy_views, "classify_q12_calc1_day requires at least one legacy view row"
    first = legacy_views[0]
    outcome = canonical_run.outcome_for_path(first.path)
    non_comparable_legacy_fields = list(LEGACY_ONLY_METRIC_FIELDS)
    records = []

    def hm(row):
        return compute_hash_match(canonical_run, row.path, row.content_hash)

    def mk(row, canonical_aggregate_id=""):
        return _make_unit(family_key, row, canonical_run_id, canonical_aggregate_id, canonical_content_digest, reader_profile_identity)

    if outcome is None:
        for row in legacy_views:
            unit = mk(row)
            records.append(
                ComparisonRecord(
                    unit=unit,
                    source_alignment=SourceAlignment.MISSING_CANONICAL_SOURCE,
                    result=ComparisonResult.NON_COMPARABLE,
                    reason=DivergenceReason.MISSING_INPUT,
                    detail="UEF-5.2 run has no artifact_outcome entry for this legacy source path at all",
                    legacy=_legacy_json(row),
                    canonical=None,
                    non_comparable_legacy_fields=non_comparable_legacy_fields,
                    hash_match=hm(row),
                )
            )
        return records, None

    if outcome.bucket != "recomputed":
        for row in legacy_views:
            unit = mk(row)
            records.append(
                ComparisonRecord(
                    unit=unit,
                    source_alignment=SourceAlignment.LEGACY_UNATTESTED,
                    result=ComparisonResult.BLOCKED,
                    reason=_map_blocked_reason(outcome.bucket, outcome.bucket_reason),
                    detail=outcome.bucket_detail or outcome.bucket_reason or outcome.bucket,
                    legacy=_legacy_json(row),
                    canonical={"bucket": outcome.bucket, "bucket_reason": outcome.bucket_reason},
                    non_comparable_legacy_fields=non_comparable_legacy_fields,
                    hash_match=hm(row),
                )
            )
        return records, None

    net_rows = [r for r in legacy_views if r.cost_treatment == "net"]
    gross_rows = [r for r in legacy_views if r.cost_treatment == "gross"]
    horizon = first.horizon

    candidates = [a for a in canonical_run.aggregates_for_path(first.path) if a.horizon_label == horizon]

    for row in gross_rows:
        unit = mk(row, candidates[0].canonical_aggregate_id if candidates else "")
        records.append(
            ComparisonRecord(
                unit=unit,
                source_alignment=SourceAlignment.SAME_PRIMARY_DIFFERENT_SECONDARY,
                result=ComparisonResult.NON_COMPARABLE,
                reason=DivergenceReason.COST_POLICY_DIFFERENCE,
                detail="canonical UEF-5.2 aggregates are always cost-applied; it persists no gross/uncosted aggregate to compare against",
                legacy=_legacy_json(row),
                canonical=_canonical_json(candidates[0]) if candidates else None,
                non_comparable_legacy_fields=non_comparable_legacy_fields,
                hash_match=hm(row),
            )
        )

    if not candidates:
        # Canonical recomputed this unit but built NO aggregate for this
        # horizon at all. Core Correction 2 item 5: an ABSENT aggregate is
        # NOT proof of a known-zero canonical population -- it is simply
        # unknown. This branch must NEVER produce EXACT_EMPTY, regardless
        # of the legacy count's value (0, a positive number, or None/missing).
        for row in net_rows:
            unit = mk(row)
            legacy_count_known = row.count is not None
            records.append(
                ComparisonRecord(
                    unit=unit,
                    source_alignment=SourceAlignment.NON_COMPARABLE,
                    result=ComparisonResult.NON_COMPARABLE,
                    reason=DivergenceReason.MISSING_INPUT,
                    detail=(
                        f"MISSING_CANONICAL_COMPARISON_UNIT: canonical produced no aggregate at all for this "
                        f"horizon (legacy count={'unknown/None' if not legacy_count_known else row.count} for "
                        f"view={row.view!r}) -- an absent aggregate is not evidence of a known-zero canonical "
                        f"population, so this is never classified EXACT_EMPTY, only NON_COMPARABLE"
                    ),
                    legacy=_legacy_json(row),
                    canonical={"bucket": outcome.bucket, "aggregate_present": False},
                    non_comparable_legacy_fields=non_comparable_legacy_fields,
                    hash_match=hm(row),
                )
            )
        return records, None

    aggregate = candidates[0]
    canonical_evaluated = aggregate.pf_sample.evaluated_count if aggregate.pf_sample else None

    # UEF-5.3 Final Population Proof Fix: count equality is NEVER, by
    # itself, sufficient proof of population equivalence, and a
    # `lineage_status=="FULL"` LABEL is never trusted by itself either --
    # `population_identity_proven` independently re-verifies the canonical
    # side's structural lineage AND requires the legacy view's own member
    # identities to exactly equal the canonical membership set. Metric
    # comparison proceeds ONLY when both are true.
    for row in net_rows:
        unit = mk(row, aggregate.canonical_aggregate_id)
        hash_match = hm(row)
        proven, proof_reason = population_identity_proven(aggregate, row.member_ids)
        if proven:
            result, reason, detail, extra, non_comparable_metric_fields = _compare_net_population_and_metrics(row, aggregate)
            records.append(
                ComparisonRecord(
                    unit=unit,
                    source_alignment=source_alignment_for(hash_match),
                    result=result,
                    reason=reason,
                    detail=detail,
                    legacy=_legacy_json(row),
                    canonical=_canonical_json(aggregate),
                    non_comparable_legacy_fields=non_comparable_legacy_fields + non_comparable_metric_fields,
                    hash_match=hash_match,
                    metric_comparisons=extra.get("metric_comparisons"),
                )
            )
        else:
            # Population identity is NOT proven -- terminate as
            # NON_COMPARABLE without ever attempting a PF/MDD comparison,
            # regardless of count/date/horizon/symbol-count equality.
            detail = (
                f"POPULATION_IDENTITY_NOT_PROVEN: {proof_reason} (canonical evaluated_count={canonical_evaluated}, "
                f"this view's count={row.count}) -- no PF/MDD/count comparison is attempted for this view"
            )
            comparisons = {
                "population": {
                    "metric": "population", "comparable": False, "status": "NON_COMPARABLE",
                    "legacy_value": row.count, "canonical_value": canonical_evaluated,
                    "reason": proof_reason,
                }
            }
            for name in ("win_count", "loss_count", "flat_count", "profit_factor", "max_drawdown"):
                comparisons[name] = {
                    "metric": name, "comparable": False, "status": "NOT_ATTEMPTED",
                    "legacy_value": None, "canonical_value": None, "reason": "population identity not proven",
                }
            records.append(
                ComparisonRecord(
                    unit=unit,
                    source_alignment=SourceAlignment.NON_COMPARABLE,
                    result=ComparisonResult.NON_COMPARABLE,
                    reason=DivergenceReason.MISSING_INPUT,
                    detail=detail,
                    legacy=_legacy_json(row),
                    canonical=_canonical_json(aggregate),
                    non_comparable_legacy_fields=non_comparable_legacy_fields,
                    hash_match=hash_match,
                    metric_comparisons=comparisons,
                )
            )

    # Always mark the aggregate as "considered" once real candidates exist,
    # regardless of whether population identity was established -- this
    # prevents it from ALSO showing up as an orphan canonical-only record
    # in the independent-universe accounting pass (it was not orphaned; it
    # was examined and classified NON_COMPARABLE with a stated reason).
    return records, aggregate


_Q11_NON_COMPARABLE_LEGACY_FIELDS = ("win_rate", "average_net_return_pct")


def classify_q11_exit_day(
    legacy: LegacyQ11ExitDay,
    canonical_run: CanonicalRun,
    family_key: str,
    canonical_run_id: str,
    canonical_content_digest: str = "",
    reader_profile_identity: str = "",
) -> tuple:
    """Q11 v2 EXIT: one undifferentiated per-day population, no view axis,
    no separate gross figure (see legacy_opportunity_engine.py's module
    docstring for the evidence establishing this equivalence). Returns
    (ComparisonRecord, consumed_canonical_aggregate_or_None).

    Reports PF/count parity only -- Q11's legacy artifact has no
    maximum-drawdown figure at all, so MDD parity is never claimed for
    this family (Core Correction 2 item 6)."""

    def legacy_json():
        return {
            "trade_count": legacy.trade_count,
            "win_count": legacy.win_count,
            "loss_count": legacy.loss_count,
            "flat_count": legacy.flat_count,
            "win_rate": legacy.win_rate,
            "profit_factor": legacy.profit_factor,
            "average_net_return_pct": legacy.average_net_return_pct,
        }

    unit_base = ComparisonUnitIdentity(
        family=family_key, trading_date=legacy.day, source_path=legacy.path,
        legacy_content_hash=legacy.content_hash, canonical_run_id=canonical_run_id,
        canonical_content_digest=canonical_content_digest, reader_profile_identity=reader_profile_identity,
        view=None, horizon_label="EXIT", cost_treatment="net",
    )
    hash_match = compute_hash_match(canonical_run, legacy.path, legacy.content_hash)

    outcome = canonical_run.outcome_for_path(legacy.path)
    if outcome is None:
        return (
            ComparisonRecord(
                unit=unit_base, source_alignment=SourceAlignment.MISSING_CANONICAL_SOURCE,
                result=ComparisonResult.NON_COMPARABLE, reason=DivergenceReason.MISSING_INPUT,
                detail="UEF-5.2 run has no artifact_outcome entry for this legacy source path at all",
                legacy=legacy_json(), canonical=None,
                non_comparable_legacy_fields=list(_Q11_NON_COMPARABLE_LEGACY_FIELDS), hash_match=hash_match,
            ),
            None,
        )

    if outcome.bucket != "recomputed":
        return (
            ComparisonRecord(
                unit=unit_base, source_alignment=SourceAlignment.LEGACY_UNATTESTED,
                result=ComparisonResult.BLOCKED, reason=_map_blocked_reason(outcome.bucket, outcome.bucket_reason),
                detail=outcome.bucket_detail or outcome.bucket_reason or outcome.bucket,
                legacy=legacy_json(), canonical={"bucket": outcome.bucket, "bucket_reason": outcome.bucket_reason},
                non_comparable_legacy_fields=list(_Q11_NON_COMPARABLE_LEGACY_FIELDS), hash_match=hash_match,
            ),
            None,
        )

    candidates = [
        a for a in canonical_run.aggregates_for_path(legacy.path)
        if a.horizon_label == "EXIT" and a.view is None
    ]
    if not candidates:
        # Core Correction 2 item 5: an ABSENT aggregate is never evidence of
        # a known-zero canonical population -- this must never become
        # EXACT_EMPTY, regardless of legacy.trade_count's value.
        return (
            ComparisonRecord(
                unit=unit_base, source_alignment=SourceAlignment.NON_COMPARABLE,
                result=ComparisonResult.NON_COMPARABLE, reason=DivergenceReason.MISSING_INPUT,
                detail=(
                    f"MISSING_CANONICAL_COMPARISON_UNIT: legacy trade_count={legacy.trade_count} but canonical "
                    f"produced no EXIT aggregate at all -- an absent aggregate is not evidence of a known-zero "
                    f"canonical population, so this is never classified EXACT_EMPTY, only NON_COMPARABLE"
                ),
                legacy=legacy_json(), canonical={"bucket": outcome.bucket, "aggregate_present": False},
                non_comparable_legacy_fields=list(_Q11_NON_COMPARABLE_LEGACY_FIELDS), hash_match=hash_match,
            ),
            None,
        )

    aggregate = candidates[0]
    unit = ComparisonUnitIdentity(
        family=family_key, trading_date=legacy.day, source_path=legacy.path,
        legacy_content_hash=legacy.content_hash, canonical_run_id=canonical_run_id,
        canonical_aggregate_id=aggregate.canonical_aggregate_id,
        canonical_content_digest=canonical_content_digest, reader_profile_identity=reader_profile_identity,
        view=None, horizon_label="EXIT", cost_treatment="net",
    )
    result, reason, detail, extra, non_comparable_metric_fields = _compare_population_and_metrics(
        legacy_count=legacy.trade_count, legacy_win=legacy.win_count, legacy_loss=legacy.loss_count,
        legacy_flat=legacy.flat_count, legacy_pf=legacy.profit_factor, legacy_mdd=None, aggregate=aggregate,
    )
    if "max_drawdown" not in non_comparable_metric_fields:
        non_comparable_metric_fields = non_comparable_metric_fields + ["max_drawdown"]
        if "NOT compared" not in detail and result == ComparisonResult.EXACT_MATCH:
            detail += "; max_drawdown NOT compared: legacy Q11 artifact has no maximum-drawdown figure at all"
    record = ComparisonRecord(
        unit=unit,
        source_alignment=source_alignment_for(hash_match),
        result=result, reason=reason, detail=detail,
        legacy=legacy_json(), canonical=_canonical_json(aggregate),
        non_comparable_legacy_fields=list(_Q11_NON_COMPARABLE_LEGACY_FIELDS) + non_comparable_metric_fields,
        metric_comparisons=extra.get("metric_comparisons"),
        hash_match=hash_match,
    )
    return record, aggregate
