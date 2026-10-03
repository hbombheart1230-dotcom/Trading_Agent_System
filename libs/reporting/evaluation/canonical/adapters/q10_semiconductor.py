"""UEF-4B-1 -- Q10 Semiconductor canonical adapter.

Converts the real `baseline_samsung_hynix` legacy artifacts (Calc A/B/C --
`libs/reporting/quant_shadow_forward_outcomes.py::attach_forward_outcomes`
reused via `libs/reporting/baseline_samsung_hynix/forward_returns.py`) into
frozen UEF canonical inputs: one `EpisodeRecord` per ranked candidate, and
one `AggregateRecord` per (legacy view, horizon) via the frozen UEF-2B
forward engine and UEF-3A/3B/3C cost/metric/aggregation pipeline.

Read-only with respect to legacy evidence -- this module never writes a
legacy artifact file, never touches broker/runtime state, and is not
imported by any production/runtime module (offline canonicalization
only; see `docs/milestones/UEF.md`).

SOURCE AUTHORITY (verified against real artifacts and real source code,
not only `docs/research/uef4_legacy_family_inventory.md`):
- `libs/reporting/baseline_samsung_hynix/strategy.py::build_decision_snapshot`
  -- one legacy decision's shape: `decision_id = f"BSH_{day}_{as_of_epoch}"`,
  `ranked_candidates` (one row per fixed-universe symbol, always exactly
  2 -- `SYMBOLS` in `contracts.py`).
- `libs/reporting/baseline_samsung_hynix/forward_returns.py`
  ::`decision_candidate_rows`/`attach_baseline_forward_returns` -- the
  real candidate/baseline/checkpoint shape this adapter reads.
- Real artifact read: `reports/evaluation/baseline_samsung_hynix/2026-06-24/
  baseline_samsung_hynix_forward_returns.json` -- confirms the exact
  `rows[].{baseline_decision_id,symbol,ticker,rank,eligible,action,
  baseline,available,reason,returns}` shape.
- `libs/reporting/evaluation/canonical/forward/profiles.py`
  ::`build_q10_semiconductor_calc_{a,b,c}_profile` -- the frozen UEF-2A
  semantic mapping this adapter delegates ALL forward-measurement
  arithmetic to (no re-implementation here).

THREE-VIEWS AMBIGUITY (UEF-4A's preserved MEDIUM #1, resolved here per
this task's own Section 7 instruction, NOT silently picked):
`summarize_forward_returns` (`forward_returns.py:186-226`) computes THREE
overlapping views over the SAME evaluated candidate population --
`top1`, `both_symbol_average`, `eligible_entries`. This adapter builds
EXACTLY ONE `EpisodeRecord` per (decision, symbol) -- the primary
evidence -- and represents the three views as three separate
`MetricAggregationContext`s (`Q10SemiconductorView`) that each SELECT a
different subset/shape of members from that same canonical episode set,
never three duplicated EpisodeRecords for one physical candidate
observation:
- `ELIGIBLE_ENTRIES` -- every candidate is a member; an ineligible
  candidate (`eligible=False`) is `EXCLUDED` -- this is EXACTLY the
  motivating example in UEF-3A's own frozen `SamplePopulation` docstring
  ("an excluded sample was deliberately out of scope by POLICY, e.g. Q10
  Semiconductor's own `eligible` flag" -- `metrics/policy.py:372-375`).
- `TOP1` -- a DIFFERENT SAMPLE UNIT (one member per DECISION, its own
  rank==1 candidate), not a filter/exclusion over the eligible_entries
  population -- a non-rank1 candidate is not "excluded from being top1",
  it is simply not part of top1's population by definition, so it is
  never a member (neither EVALUATED nor EXCLUDED) of this view's batch.
- `BOTH_SYMBOL_AVERAGE` -- ALSO a different sample unit: one member per
  DECISION, the MEAN of that decision's own OBSERVED candidates' gross
  returns for one horizon (`forward_returns.py:202`,
  `both_gross.append(sum(value for _, value in observed) / len(observed))`).
  This is the one place this adapter computes a plain arithmetic mean --
  it is the SAMPLE UNIT DEFINITION for this legacy view (what one
  physical "both-symbol" observation IS), never a cost/PF/MDD
  calculation (those remain exclusively UEF-3B/3C's).  A decision with
  zero observed candidates for a horizon contributes a `MISSING` member
  (not silently dropped from the population, unlike the legacy code's
  own `if not observed: continue`) -- "no evidence -> no active
  semantic", never "no evidence -> invisible".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from libs.reporting.evaluation.canonical.contracts import (
    CheckpointCompleteness,
    EventOrigin,
    ExecutionMode,
    ObservationType,
    ReturnUnit,
)
from libs.reporting.evaluation.canonical.identity import (
    DerivedFieldKind,
    DerivedIdentityPart,
    build_event_ref,
    evaluation_record_id as _build_evaluation_record_id,
    evaluation_subject_id as _build_evaluation_subject_id,
)
from libs.reporting.evaluation.canonical.record import AggregateIdentity, AggregateRecord, Checkpoint, EpisodeRecord, Provenance
from libs.reporting.evaluation.canonical.forward import PriceCandidate, SourceResultCostSemantics
from libs.reporting.evaluation.canonical.forward.engine import CanonicalObservation, ResolvedReference
from libs.reporting.evaluation.canonical.forward.profiles import (
    build_q10_semiconductor_calc_a_profile,
    build_q10_semiconductor_calc_b_profile,
    build_q10_semiconductor_calc_c_profile,
)
from libs.reporting.evaluation.canonical.metrics import CostPolicy, MetricAggregationContext, MetricPolicy
from libs.reporting.evaluation.canonical.metrics.aggregation import (
    CanonicalAggregationMember,
    CanonicalSampleBatch,
    SampleMemberState,
    aggregate_canonical_samples,
)

from .forward_measurement_adapter import (
    ForwardMeasurementAdapterError,
    build_forward_measurement_episode,
    build_forward_measurement_event_ref,
    checkpoint_to_aggregation_member,
)


class Q10SemiconductorAdapterError(ForwardMeasurementAdapterError):
    """Raised for a Q10 Semiconductor legacy-input problem -- fail fast, never repair."""


SOURCE_NAMESPACE = "baseline_samsung_hynix_q10_semiconductor"
HYPOTHESIS_ID = "Q10_LARGECAP_BASELINE_CONTROL"  # real `evaluation_program_id` field, both decisions.json and forward_returns.json artifacts
_CALC_PROFILES: tuple[tuple[str, Any], ...] = (
    ("baseline_samsung_hynix_calc_a", build_q10_semiconductor_calc_a_profile()),
    ("baseline_samsung_hynix_calc_b", build_q10_semiconductor_calc_b_profile()),
    ("baseline_samsung_hynix_calc_c", build_q10_semiconductor_calc_c_profile()),
)


def all_horizon_labels() -> tuple[str, ...]:
    """The full set of horizon labels this family covers -- derived from the
    actual frozen profiles, never a hand-typed literal list."""

    labels: list[str] = []
    for _, policy in _CALC_PROFILES:
        for horizon in policy.horizons:
            if horizon.label not in labels:
                labels.append(horizon.label)
    return tuple(labels)


@dataclass(frozen=True)
class Q10SemiconductorCandidate:
    """One ranked candidate row, parsed from a real
    `baseline_samsung_hynix_decisions.json` decision -- an adapter-local
    DTO, not a new canonical record kind."""

    decision_id: str
    trading_date: str
    symbol: str
    ticker: str
    rank: int
    eligible: bool
    action: str
    available: bool
    baseline_epoch: int | None
    baseline_price: float | None


def parse_decision_candidates(decision: Mapping[str, Any]) -> list[Q10SemiconductorCandidate]:
    """Parse one real decision row (`decisions.json`'s `decisions[i]`) into
    its ranked candidates. Fail-fast on missing/invalid load-bearing
    fields -- never a silent default for symbol/decision_id/trading_date."""

    decision_id = str(decision.get("decision_id") or "").strip()
    if not decision_id:
        raise Q10SemiconductorAdapterError("parse_decision_candidates: decision.decision_id is required")
    trading_date = str(decision.get("day") or "").strip()
    if not trading_date:
        raise Q10SemiconductorAdapterError(f"parse_decision_candidates: decision {decision_id!r} has no 'day'")
    raw_candidates = decision.get("ranked_candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise Q10SemiconductorAdapterError(f"parse_decision_candidates: decision {decision_id!r} has no ranked_candidates")

    candidates: list[Q10SemiconductorCandidate] = []
    for row in raw_candidates:
        if not isinstance(row, Mapping):
            raise Q10SemiconductorAdapterError(f"parse_decision_candidates: decision {decision_id!r} has a non-mapping ranked_candidates entry")
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            raise Q10SemiconductorAdapterError(f"parse_decision_candidates: decision {decision_id!r} has a candidate with no symbol")
        rank = row.get("rank")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank <= 0:
            raise Q10SemiconductorAdapterError(f"parse_decision_candidates: decision {decision_id!r} symbol {symbol!r} has invalid rank={rank!r}")
        features = row.get("features")
        features = features if isinstance(features, Mapping) else {}
        available = bool(features.get("available"))
        baseline_epoch = features.get("baseline_epoch") if available else None
        baseline_price = features.get("baseline_price") if available else None
        if available and (baseline_epoch is None or baseline_price is None or float(baseline_price) <= 0):
            raise Q10SemiconductorAdapterError(
                f"parse_decision_candidates: decision {decision_id!r} symbol {symbol!r} declares "
                "features.available=true but baseline_epoch/baseline_price is missing/invalid -- contradictory source fields"
            )
        candidates.append(
            Q10SemiconductorCandidate(
                decision_id=decision_id,
                trading_date=trading_date,
                symbol=symbol,
                ticker=str(row.get("ticker") or "").strip(),
                rank=int(rank),
                eligible=bool(row.get("eligible")),
                action=str(row.get("action") or "").strip(),
                available=available,
                baseline_epoch=int(baseline_epoch) if baseline_epoch is not None else None,
                baseline_price=float(baseline_price) if baseline_price is not None else None,
            )
        )
    return candidates


def _candles_to_observations(rows: Sequence[Mapping[str, Any]]) -> list[CanonicalObservation]:
    """FIX1: a candle with an invalid/non-positive timestamp is REJECTED
    outright, never silently dropped. A silently dropped candle can change
    which observation a horizon resolves to, its MFE/MAE, and its missing
    state -- all without visibility, exactly the "no silent repair" defect
    this task's HIGH finding names. No normalization (`abs(ts)`, a default
    timestamp, coercion) is applied either -- an invalid load-bearing input
    is rejected, never repaired."""

    observations: list[CanonicalObservation] = []
    for row in rows:
        ts = int(row.get("ts") or 0)
        if ts <= 0:
            raise Q10SemiconductorAdapterError(
                f"_candles_to_observations: candle has invalid timestamp ts={ts!r} (raw={row.get('ts')!r}) -- "
                "a non-positive candle timestamp is rejected outright, never silently dropped"
            )
        fields: dict[PriceCandidate, float] = {}
        for key, candidate in (
            ("open", PriceCandidate.BAR_OPEN),
            ("close", PriceCandidate.BAR_CLOSE),
            ("high", PriceCandidate.BAR_HIGH),
            ("low", PriceCandidate.BAR_LOW),
        ):
            value = row.get(key)
            if value is not None:
                fields[candidate] = float(value)
        volume = row.get("volume")
        observations.append(CanonicalObservation(timestamp=ts, fields=fields, volume=float(volume) if volume is not None else None))
    return observations


def build_q10_semiconductor_episode(
    candidate: Q10SemiconductorCandidate,
    minute_rows: Sequence[Mapping[str, Any]],
) -> EpisodeRecord:
    """Build ONE canonical `EpisodeRecord` for one ranked candidate, merging
    Calc A (+5/15/30/60m) + Calc B (+120/180m) + Calc C (EOD) via the
    frozen, generic UEF-2B engine -- delegated entirely to
    `forward_measurement_adapter.build_forward_measurement_episode`."""

    if not candidate.available or candidate.baseline_epoch is None or candidate.baseline_price is None:
        raise Q10SemiconductorAdapterError(
            f"build_q10_semiconductor_episode: candidate decision_id={candidate.decision_id!r} symbol="
            f"{candidate.symbol!r} has no resolved baseline reference (features.available=false) -- caller "
            "must treat this candidate as a MISSING population member instead of building an episode for it"
        )
    observations = _candles_to_observations(minute_rows)
    resolved_reference = ResolvedReference.single(
        origin=EventOrigin.CANDIDATE, timestamp=candidate.baseline_epoch, price=candidate.baseline_price,
    )
    event_ref = build_forward_measurement_event_ref(
        source_namespace=SOURCE_NAMESPACE,
        trading_date=candidate.trading_date,
        symbol=candidate.symbol,
        extra_fields={"decision_id": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value=candidate.decision_id)},
    )
    return build_forward_measurement_episode(
        source_namespace=SOURCE_NAMESPACE,
        hypothesis_id=HYPOTHESIS_ID,
        execution_mode=ExecutionMode.SHADOW,
        trading_date=candidate.trading_date,
        symbol=candidate.symbol,
        horizon_origin=EventOrigin.CANDIDATE,
        event_ref=event_ref,
        resolved_reference=resolved_reference,
        observations=observations,
        profiles=_CALC_PROFILES,
        provenance=Provenance(
            legacy_program="baseline_samsung_hynix_q10_semiconductor",
            legacy_schema="baseline_samsung_hynix_forward_returns.v1",
            source_artifact="reports/evaluation/baseline_samsung_hynix/<day>/baseline_samsung_hynix_forward_returns.json",
            source_function="attach_baseline_forward_returns",
        ),
        metadata={
            "decision_id": candidate.decision_id,
            "rank": candidate.rank,
            "eligible": candidate.eligible,
            "action": candidate.action,
            "ticker": candidate.ticker,
        },
    )


def _checkpoint_for(episode: EpisodeRecord, horizon_label: str) -> Checkpoint | None:
    for checkpoint in episode.checkpoints:
        if checkpoint.horizon_label == horizon_label:
            return checkpoint
    return None


class Q10SemiconductorView(str, Enum):
    """The three legacy views `summarize_forward_returns` computes over one
    evaluated candidate population -- never three duplicated primary
    samples, see module docstring."""

    TOP1 = "TOP1"
    BOTH_SYMBOL_AVERAGE = "BOTH_SYMBOL_AVERAGE"
    ELIGIBLE_ENTRIES = "ELIGIBLE_ENTRIES"


@dataclass(frozen=True)
class Q10SemiconductorDecisionEpisodes:
    """One decision's parsed candidates, each paired with its own
    `EpisodeRecord` (or `None` if `available=False` -- no reference ever
    resolved, so no episode could be built)."""

    decision_id: str
    rows: tuple[tuple[Q10SemiconductorCandidate, EpisodeRecord | None], ...]


def build_decision_episodes(
    decisions: Sequence[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[Q10SemiconductorDecisionEpisodes]:
    """Parse every decision's candidates and build an `EpisodeRecord` for
    each one whose reference actually resolved."""

    out: list[Q10SemiconductorDecisionEpisodes] = []
    for decision in decisions:
        candidates = parse_decision_candidates(decision)
        rows: list[tuple[Q10SemiconductorCandidate, EpisodeRecord | None]] = []
        for candidate in candidates:
            if candidate.available:
                episode = build_q10_semiconductor_episode(
                    candidate, minute_rows_by_symbol.get(candidate.symbol) or (),
                )
            else:
                episode = None
            rows.append((candidate, episode))
        out.append(Q10SemiconductorDecisionEpisodes(decision_id=candidates[0].decision_id, rows=tuple(rows)))
    return out


def _decision_composite_evaluation_record_id(decision_id: str) -> str:
    """A stable id for the `BOTH_SYMBOL_AVERAGE` view's own derived,
    decision-level (not per-candidate) member -- `ObservationType.DAY_SYMBOL`
    names exactly this shape: one observation spanning the fixed 2-symbol
    universe for one decision, not one single-symbol candidate."""

    event_ref = build_event_ref(source_namespace=SOURCE_NAMESPACE, native_id=f"both_symbol_average:{decision_id}")
    subject_id = _build_evaluation_subject_id(
        canonical_event_id=event_ref.canonical_event_id, hypothesis_id=HYPOTHESIS_ID, observation_type=ObservationType.DAY_SYMBOL,
    )
    return _build_evaluation_record_id(evaluation_subject_id=subject_id, execution_mode=ExecutionMode.SHADOW)


def select_view_members(
    decisions: Sequence[Q10SemiconductorDecisionEpisodes],
    *,
    view: Q10SemiconductorView,
    horizon_label: str,
    cost_policy: CostPolicy,
) -> list[CanonicalAggregationMember]:
    """Select this view's members for one horizon from the SAME canonical
    episode set every view shares -- see module docstring for the
    per-view selection rule."""

    members: list[CanonicalAggregationMember] = []

    if view is Q10SemiconductorView.ELIGIBLE_ENTRIES:
        for decision in decisions:
            for candidate, episode in decision.rows:
                checkpoint = _checkpoint_for(episode, horizon_label) if episode is not None else None
                evaluation_record_id = episode.identity.evaluation_record_id if episode is not None else ""
                members.append(
                    checkpoint_to_aggregation_member(
                        checkpoint,
                        evaluation_record_id=evaluation_record_id,
                        cost_policy=cost_policy,
                        state_override=SampleMemberState.EXCLUDED if not candidate.eligible else None,
                    )
                )
        return members

    if view is Q10SemiconductorView.TOP1:
        for decision in decisions:
            top1_rows = [(candidate, episode) for candidate, episode in decision.rows if candidate.rank == 1]
            if len(top1_rows) != 1:
                raise Q10SemiconductorAdapterError(
                    f"select_view_members: decision {decision.decision_id!r} has {len(top1_rows)} rank==1 "
                    "candidates (expected exactly 1) -- ambiguous TOP1 mapping, never silently picked"
                )
            candidate, episode = top1_rows[0]
            checkpoint = _checkpoint_for(episode, horizon_label) if episode is not None else None
            evaluation_record_id = episode.identity.evaluation_record_id if episode is not None else ""
            members.append(
                checkpoint_to_aggregation_member(
                    checkpoint, evaluation_record_id=evaluation_record_id, cost_policy=cost_policy,
                )
            )
        return members

    if view is Q10SemiconductorView.BOTH_SYMBOL_AVERAGE:
        for decision in decisions:
            observed_returns: list[float] = []
            observed_timestamps: list[int] = []
            for _candidate, episode in decision.rows:
                if episode is None:
                    continue
                checkpoint = _checkpoint_for(episode, horizon_label)
                if checkpoint is None:
                    raise Q10SemiconductorAdapterError(
                        f"select_view_members: episode for decision {decision.decision_id!r} has no checkpoint "
                        f"for horizon_label={horizon_label!r} -- unknown horizon"
                    )
                if checkpoint.completeness is not CheckpointCompleteness.OBSERVED:
                    continue
                if checkpoint.gross_return is None or checkpoint.observed_timestamp is None:
                    continue
                observed_returns.append(checkpoint.gross_return)
                observed_timestamps.append(checkpoint.observed_timestamp)
            if not observed_returns:
                members.append(CanonicalAggregationMember(state=SampleMemberState.MISSING))
                continue
            mean_return = sum(observed_returns) / len(observed_returns)
            members.append(
                CanonicalAggregationMember(
                    state=SampleMemberState.EVALUATED,
                    evaluation_record_id=_decision_composite_evaluation_record_id(decision.decision_id),
                    gross_return=mean_return,
                    return_unit=ReturnUnit.PERCENTAGE_POINTS,
                    source_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
                    cost_policy=cost_policy,
                    observed_timestamp=max(observed_timestamps),
                    target_timestamp=None,
                )
            )
        return members

    raise Q10SemiconductorAdapterError(f"select_view_members: unknown view {view!r}")


def build_aggregation_context(
    *,
    view: Q10SemiconductorView,
    horizon_label: str,
    cost_policy: CostPolicy,
    metric_policy: MetricPolicy,
    aggregation_window_start: str,
    aggregation_window_end: str = "",
) -> MetricAggregationContext:
    """Build the `MetricAggregationContext` (one per view+horizon+window) --
    the aggregate's own `AggregateIdentity` (UEF-1, reused) has no market
    event of its own (Fix2 #16), so it is keyed on
    (view, horizon_label, window), never on a symbol/trading_date."""

    aggregate_ref = build_event_ref(
        source_namespace=SOURCE_NAMESPACE,
        native_id=f"q10_semiconductor:{view.value}:{horizon_label}:{aggregation_window_start}:{aggregation_window_end}",
    )
    subject_id = _build_evaluation_subject_id(
        canonical_event_id=aggregate_ref.canonical_event_id, hypothesis_id=HYPOTHESIS_ID, observation_type="AGGREGATE",
    )
    record_id = _build_evaluation_record_id(evaluation_subject_id=subject_id, execution_mode="OBSERVATION_ONLY")
    aggregate_identity = AggregateIdentity(
        aggregate_ref=aggregate_ref,
        aggregation_scope=f"q10_semiconductor:{view.value}",
        hypothesis_id=HYPOTHESIS_ID,
        evaluator_version="",
        evaluation_subject_id=subject_id,
        evaluation_record_id=record_id,
    )
    return MetricAggregationContext(
        aggregate_identity=aggregate_identity,
        horizon_label=horizon_label,
        cost_policy_id=cost_policy.policy_id,
        metric_policy_id=metric_policy.policy_id,
    )


@dataclass(frozen=True)
class Q10SemiconductorAdapterResult:
    episodes: tuple[EpisodeRecord, ...]
    aggregates: Mapping[tuple[str, str], AggregateRecord] = field(default_factory=dict)


def adapt_q10_semiconductor_decisions(
    decisions: Sequence[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    cost_policy: CostPolicy,
    metric_policy: MetricPolicy | None = None,
    aggregation_window_start: str,
    aggregation_window_end: str = "",
    views: Sequence[Q10SemiconductorView] = tuple(Q10SemiconductorView),
    horizon_labels: Sequence[str] | None = None,
) -> Q10SemiconductorAdapterResult:
    """The adapter's one top-level entry point: legacy decisions + candles
    in, canonical `EpisodeRecord`s + `AggregateRecord`s out. Delegates all
    forward-measurement math to UEF-2B and all cost/PF/MDD math to
    UEF-3B/3C -- this function only translates, selects population
    membership, and calls the frozen aggregation entry point."""

    resolved_metric_policy = metric_policy or MetricPolicy()
    decision_episodes = build_decision_episodes(decisions, minute_rows_by_symbol=minute_rows_by_symbol)
    all_episodes = tuple(episode for decision in decision_episodes for _candidate, episode in decision.rows if episode is not None)

    resolved_horizon_labels = tuple(horizon_labels) if horizon_labels is not None else all_horizon_labels()
    aggregates: dict[tuple[str, str], AggregateRecord] = {}
    for view in views:
        for horizon_label in resolved_horizon_labels:
            context = build_aggregation_context(
                view=view, horizon_label=horizon_label, cost_policy=cost_policy, metric_policy=resolved_metric_policy,
                aggregation_window_start=aggregation_window_start, aggregation_window_end=aggregation_window_end,
            )
            members = select_view_members(
                decision_episodes, view=view, horizon_label=horizon_label, cost_policy=cost_policy,
            )
            batch = CanonicalSampleBatch(context=context, members=tuple(members))
            aggregates[(view.value, horizon_label)] = aggregate_canonical_samples(
                context=context,
                batches=(batch,),
                metric_policy=resolved_metric_policy,
                input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
                aggregation_window_start=aggregation_window_start,
                aggregation_window_end=aggregation_window_end,
                excluded_note="q10_semiconductor eligible=false candidate excluded by legacy eligible_entries view policy",
            )
    return Q10SemiconductorAdapterResult(episodes=all_episodes, aggregates=aggregates)


__all__ = [
    "Q10SemiconductorAdapterError",
    "SOURCE_NAMESPACE",
    "HYPOTHESIS_ID",
    "all_horizon_labels",
    "Q10SemiconductorCandidate",
    "parse_decision_candidates",
    "build_q10_semiconductor_episode",
    "Q10SemiconductorView",
    "Q10SemiconductorDecisionEpisodes",
    "build_decision_episodes",
    "select_view_members",
    "build_aggregation_context",
    "Q10SemiconductorAdapterResult",
    "adapt_q10_semiconductor_decisions",
]
