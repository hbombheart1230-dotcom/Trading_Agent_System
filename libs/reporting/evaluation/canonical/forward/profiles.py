"""UEF-2A BOUNDARY CLOSURE -- Source-Derived Semantic Profile registry.

This is the ONLY module in `canonical/forward` allowed to know a program
name (Q9/Q10/Q11/Q12/Opening). It declares, for each of the 14 real
checkpoint calculators, an explicit `ForwardPolicy` built PURELY by
composing the generic core (`contracts.py`/`policy.py`) -- no calculator's
own algorithm (e.g. Q10 Index's 0.5% retracement scan) is implemented
here; a profile only ever declares semantic SPECIFICATION, never
executable legacy-artifact-parsing/migration/adapter logic (that
distinction belongs to UEF-4, not here -- see item 8 of the Boundary
Closure request).

Every profile traces to a specific, re-verified file:line in a real
legacy calculator (cited in each builder function's docstring). Source
authority order (unchanged across every UEF-2A phase): real legacy source
code > real artifact > documented source constant > this profile > any
existing test.

Still computes nothing -- UEF-2B (not started) will consume
`CalculatorProfile.policy` generically; it must never need to import this
module's calculator-specific builder functions, only the resulting
`ForwardPolicy` objects via `PROFILE_REGISTRY`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..contracts import EventOrigin, ReturnUnit
from .contracts import (
    DataCompletenessKind,
    EvidenceVerificationState,
    ForwardSessionResolverAuthority,
    HorizonKind,
    MfeMaeWindowEnd,
    MissingResolutionPolicy,
    ObservationSelectionMode,
    PriceCandidate,
    ReferenceResolutionKind,
    SourceResultCostSemantics,
    TradeDirection,
)
from .policy import (
    DataCompletenessPolicy,
    ExcursionPolicy,
    FixedClockSpec,
    ForwardPolicy,
    ForwardSessionSpec,
    GrossReturnPolicy,
    HorizonSpec,
    ObservationPolicy,
    PriceResolutionPolicy,
    ReferenceResolutionPolicy,
    SessionCloseSpec,
)


def _chain(*candidates: PriceCandidate) -> PriceResolutionPolicy:
    return PriceResolutionPolicy(authorities=candidates)


def _external_ref(*, price: PriceResolutionPolicy, origin: EventOrigin) -> ReferenceResolutionPolicy:
    return ReferenceResolutionPolicy(kind=ReferenceResolutionKind.EXTERNAL_EVENT_TIMESTAMP, price_resolution=price, origin=origin)


def _pre_resolved_ref(*, provenance: str) -> ReferenceResolutionPolicy:
    return ReferenceResolutionPolicy(kind=ReferenceResolutionKind.PRE_RESOLVED_REFERENCE, price_resolution=_chain(PriceCandidate.FIXED_OBSERVED_PRICE), provenance=provenance)


def _obs(
    *, price: PriceResolutionPolicy, selection: ObservationSelectionMode = ObservationSelectionMode.FIRST_AT_OR_AFTER,
    lookahead: float | None = 90, lookback: float = 0.0, missing: MissingResolutionPolicy | None = None,
    **kwargs,
) -> ObservationPolicy:
    if missing is None:
        missing = MissingResolutionPolicy.KEEP_PENDING if lookahead is None else MissingResolutionPolicy.EXPIRE_AFTER_TOLERANCE
    return ObservationPolicy(selection_mode=selection, price_resolution=price, missing_resolution=missing, lookback_seconds=lookback, lookahead_seconds=lookahead, **kwargs)


@dataclass(frozen=True)
class CalculatorProfile:
    """One entry in the 14-calculator registry -- reproducible identity (item 10/11)."""

    number: int
    name: str
    source: str
    policy: ForwardPolicy

    @property
    def profile_id(self) -> str:
        return f"UEF2A_PROFILE_{self.number:02d}_{self.policy.policy_id}"

    @property
    def profile_version(self) -> str:
        return self.policy.policy_version


# =========================================================================
# 1. Q9 Horizon/Exit -- strategy_horizon_feedback.py
# =========================================================================


def build_q9_horizon_exit_profile() -> ForwardPolicy:
    """4-deep price chain, restated; EOD checkpoint chain+excursion FIXED (Boundary Closure item 26/27).

    Evidence for the fix: `update_post_exit_shadow_with_price_observations`
    normalizes EVERY row (intraday AND the EOD `close_row`) through the
    SAME 4-deep alias chain (`_row_price(raw,"close","price","current_price",
    "cur_price")`, `strategy_horizon_feedback.py:914`) before EITHER
    checkpoint reads `row["price"]`/`row["high"]`/`row["low"]`
    (`:958,966-967` intraday; `:983-984,993-994` EOD) -- so EOD's own
    checkpoint price chain and excursion chain must be IDENTICAL to the
    intraday checkpoints', never a shorter `BAR_CLOSE`-only chain with no
    excursion at all (the bug this profile fixes).
    """

    checkpoint_price_chain = _chain(PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE, PriceCandidate.SOURCE_FIELD_CURRENT_PRICE, PriceCandidate.SOURCE_FIELD_CUR_PRICE)
    excursion_high_chain = _chain(PriceCandidate.BAR_HIGH, PriceCandidate.SOURCE_FIELD_HIGH_PRICE, PriceCandidate.PRIMARY_PRICE_FALLBACK)
    excursion_low_chain = _chain(PriceCandidate.BAR_LOW, PriceCandidate.SOURCE_FIELD_LOW_PRICE, PriceCandidate.PRIMARY_PRICE_FALLBACK)
    fallback_spec = SessionCloseSpec(close_clock=FixedClockSpec(clock_label="15:30"), price_resolution=_chain(PriceCandidate.BAR_CLOSE))

    minute_labels = {"+5m": 300, "+15m": 900, "+30m": 1800, "+60m": 3600}
    horizons = tuple(
        HorizonSpec(
            label=label, kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.ACTUAL_EXIT,
            observation=ObservationPolicy(selection_mode=ObservationSelectionMode.FIRST_AT_OR_AFTER, price_resolution=checkpoint_price_chain, missing_resolution=MissingResolutionPolicy.USE_SESSION_CLOSE_FALLBACK, lookahead_seconds=None, session_close_fallback=fallback_spec),
            excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.OWN_CHECKPOINT_OBSERVATION, start_inclusive=True, end_inclusive=True, mfe_price_resolution=excursion_high_chain, mae_price_resolution=excursion_low_chain),
            relative_seconds=seconds,
        )
        for label, seconds in minute_labels.items()
    )
    eod = HorizonSpec(
        label="EOD", kind=HorizonKind.SESSION_CLOSE, origin=EventOrigin.ACTUAL_EXIT,
        observation=_obs(price=checkpoint_price_chain, selection=ObservationSelectionMode.LAST_AVAILABLE, lookahead=None, missing=MissingResolutionPolicy.KEEP_PENDING),
        excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.OWN_CHECKPOINT_OBSERVATION, start_inclusive=True, end_inclusive=True, mfe_price_resolution=excursion_high_chain, mae_price_resolution=excursion_low_chain),
        fixed_clock=FixedClockSpec(clock_label="15:30"),
    )
    return ForwardPolicy(
        legacy_program="q9_horizon_exit_post_exit_shadow", horizons=horizons + (eod,),
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.FRACTION),
        reference_resolution=_external_ref(price=_chain(PriceCandidate.FIXED_OBSERVED_PRICE), origin=EventOrigin.ACTUAL_EXIT),
        source_result_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
        cost_note="update_post_exit_shadow_with_price_observations only ever writes return_pct; no net_return_pct/cost/slippage field exists anywhere in strategy_horizon_feedback.py",
    )


# =========================================================================
# 2-4. Q10 Semiconductor Calc A/B/C -- quant_shadow_forward_outcomes.py /
#      baseline_samsung_hynix/forward_returns.py (unflagged, unchanged)
# =========================================================================


def build_q10_semiconductor_calc_a_profile() -> ForwardPolicy:
    """+5/15/30/60m: BAR_CLOSE->REFERENCE_PRICE checkpoint, TARGET_TIMESTAMP-bounded excursion.

    Evidence: `quant_shadow_forward_outcomes.py:337-339`, `future_end =
    bisect_right(same_day_epochs, target)` (nominal target, not observed epoch).
    """

    checkpoint_chain = _chain(PriceCandidate.BAR_CLOSE, PriceCandidate.REFERENCE_PRICE)
    excursion_high = _chain(PriceCandidate.BAR_HIGH, PriceCandidate.REFERENCE_PRICE)
    excursion_low = _chain(PriceCandidate.BAR_LOW, PriceCandidate.REFERENCE_PRICE)
    labels = {"+5m": 300, "+15m": 900, "+30m": 1800, "+60m": 3600}
    horizons = tuple(
        HorizonSpec(
            label=label, kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.CANDIDATE,
            observation=_obs(price=checkpoint_chain, lookahead=180),
            excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.TARGET_TIMESTAMP, start_inclusive=True, end_inclusive=True, mfe_price_resolution=excursion_high, mae_price_resolution=excursion_low),
            relative_seconds=seconds,
        )
        for label, seconds in labels.items()
    )
    return ForwardPolicy(
        legacy_program="baseline_samsung_hynix_calc_a", horizons=horizons,
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_external_ref(price=_chain(PriceCandidate.BAR_CLOSE), origin=EventOrigin.CANDIDATE),
        source_result_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
        cost_note="attach_forward_outcomes (quant_shadow_forward_outcomes.py) never computes a net/cost-adjusted field -- only the raw close/base_price ratio",
    )


def build_q10_semiconductor_calc_b_profile() -> ForwardPolicy:
    """+120/+180m: single-authority checkpoint/excursion, OWN_CHECKPOINT_OBSERVATION-bounded, start-exclusive."""

    labels = {"+120m": 7200, "+180m": 10800}
    horizons = tuple(
        HorizonSpec(
            label=label, kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.CANDIDATE,
            observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), lookahead=90),
            excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.OWN_CHECKPOINT_OBSERVATION, start_inclusive=False, end_inclusive=True, mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH), mae_price_resolution=_chain(PriceCandidate.BAR_LOW)),
            relative_seconds=seconds,
        )
        for label, seconds in labels.items()
    )
    return ForwardPolicy(
        legacy_program="baseline_samsung_hynix_calc_b", horizons=horizons,
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_external_ref(price=_chain(PriceCandidate.BAR_CLOSE), origin=EventOrigin.CANDIDATE),
        source_result_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
        cost_note="_extended_checkpoint (baseline_samsung_hynix/forward_returns.py) reuses the same gross-only close/base_price ratio, no net field",
    )


def build_q10_semiconductor_calc_c_profile() -> ForwardPolicy:
    """EOD inline override: single-authority checkpoint/excursion, OWN_CHECKPOINT_OBSERVATION-bounded."""

    eod = HorizonSpec(
        label="EOD", kind=HorizonKind.SESSION_CLOSE, origin=EventOrigin.CANDIDATE,
        observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), selection=ObservationSelectionMode.LAST_AVAILABLE, lookahead=None, missing=MissingResolutionPolicy.KEEP_PENDING),
        excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.OWN_CHECKPOINT_OBSERVATION, start_inclusive=True, end_inclusive=True, mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH), mae_price_resolution=_chain(PriceCandidate.BAR_LOW)),
        fixed_clock=FixedClockSpec(clock_label="15:30"),
    )
    return ForwardPolicy(
        legacy_program="baseline_samsung_hynix_calc_c", horizons=(eod,),
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_external_ref(price=_chain(PriceCandidate.BAR_CLOSE), origin=EventOrigin.CANDIDATE),
        source_result_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
        cost_note="EOD inline override reuses the same gross-only computation as Calc A/B, no net field",
    )


# =========================================================================
# 5-6. Q10 Index Calc F/G -- forward_validation/reaction_reader.py (unflagged, unchanged)
# =========================================================================


def build_q10_index_calc_f_profile() -> ForwardPolicy:
    """Fixed-clock opening + plain intraday points, UNBOUNDED_FORWARD excursion (genuinely unbounded in source)."""

    opening = HorizonSpec(
        label="09:00", kind=HorizonKind.FIXED_CLOCK_TARGET, origin=EventOrigin.FIXED_CLOCK,
        observation=_obs(price=_chain(PriceCandidate.BAR_OPEN), lookahead=180, require_positive_volume=True, require_positive_price=True),
        excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.UNBOUNDED_FORWARD, start_inclusive=True, end_inclusive=True, mfe_price_resolution=_chain(PriceCandidate.BAR_CLOSE), mae_price_resolution=_chain(PriceCandidate.BAR_CLOSE)),
        fixed_clock=FixedClockSpec(clock_label="09:00"),
    )
    plain_labels = ("09:03", "09:05", "09:10", "09:15")
    plain = tuple(
        HorizonSpec(
            label=label, kind=HorizonKind.FIXED_CLOCK_TARGET, origin=EventOrigin.FIXED_CLOCK,
            observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), lookahead=90),
            excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.UNBOUNDED_FORWARD, start_inclusive=True, end_inclusive=True, mfe_price_resolution=_chain(PriceCandidate.BAR_CLOSE), mae_price_resolution=_chain(PriceCandidate.BAR_CLOSE)),
            fixed_clock=FixedClockSpec(clock_label=label),
        )
        for label in plain_labels
    )
    return ForwardPolicy(
        legacy_program="baseline_samsung_hynix_calc_f", horizons=(opening,) + plain,
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_external_ref(price=_chain(PriceCandidate.BAR_OPEN), origin=EventOrigin.FIXED_CLOCK),
        source_result_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
        cost_note="reaction_reader.py::_stock_reaction/_forward_window only ever captures raw OHLCV points, never a cost/net-adjusted figure -- cost is applied only downstream by Calc H (shadow_comparison.py)",
    )


def _governed(label: str, *, selection: ObservationSelectionMode = ObservationSelectionMode.FIRST_AT_OR_AFTER, lookback: float = 0.0, lookahead: float | None = 90) -> tuple[HorizonSpec, HorizonSpec, HorizonSpec]:
    clock = "15:30" if label == "CLOSE" else label
    absent = HorizonSpec(
        label=label, kind=HorizonKind.FIXED_CLOCK_TARGET, origin=EventOrigin.FIXED_CLOCK,
        observation=ObservationPolicy(
            selection_mode=selection, price_resolution=_chain(PriceCandidate.BAR_CLOSE),
            missing_resolution=MissingResolutionPolicy.EXPIRE_AFTER_TOLERANCE, lookback_seconds=lookback, lookahead_seconds=lookahead,
            evidence_requirement=EvidenceVerificationState.ABSENT,
        ),
        fixed_clock=FixedClockSpec(clock_label=clock), horizon_set_id="collector_absent_legacy_fallback",
    )
    invalid = HorizonSpec(
        label=label, kind=HorizonKind.FIXED_CLOCK_TARGET, origin=EventOrigin.FIXED_CLOCK,
        observation=ObservationPolicy(selection_mode=ObservationSelectionMode.EXACT, price_resolution=_chain(PriceCandidate.QUOTE), missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY, evidence_requirement=EvidenceVerificationState.INVALID),
        fixed_clock=FixedClockSpec(clock_label=clock), horizon_set_id="collector_invalid",
    )
    verified = HorizonSpec(
        label=label, kind=HorizonKind.FIXED_CLOCK_TARGET, origin=EventOrigin.FIXED_CLOCK,
        observation=ObservationPolicy(selection_mode=ObservationSelectionMode.EXACT, price_resolution=_chain(PriceCandidate.QUOTE), missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY, evidence_requirement=EvidenceVerificationState.VERIFIED),
        fixed_clock=FixedClockSpec(clock_label=clock), horizon_set_id="collector_verified",
    )
    return absent, invalid, verified


def build_q10_index_calc_g_profile() -> ForwardPolicy:
    """Collector 3-state (ABSENT/INVALID/VERIFIED) governed checkpoints -- 09:30/10:00/CLOSE."""

    g_0930 = _governed("09:30")
    g_1000 = _governed("10:00")
    g_close = _governed("CLOSE", selection=ObservationSelectionMode.LAST_AVAILABLE, lookback=600, lookahead=60)
    return ForwardPolicy(
        legacy_program="baseline_samsung_hynix_calc_g", horizons=g_0930 + g_1000 + g_close,
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_external_ref(price=_chain(PriceCandidate.BAR_OPEN), origin=EventOrigin.FIXED_CLOCK),
        source_result_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
        cost_note="_index_reaction's collector-governed points capture raw evidence only (QUOTE/BAR_CLOSE), same as Calc F -- no cost adjustment at this stage",
    )


# =========================================================================
# 7. Q10 Index Calc H -- directional shadow, FIRST_PULLBACK_ENTRY
# =========================================================================


def build_q10_index_calc_h_profile() -> ForwardPolicy:
    """FIRST_PULLBACK_ENTRY ownership FIXED (Boundary Closure item 4-6, H1): now UPSTREAM_REFERENCE_RESOLUTION.

    Codex's final ruling reverses the Semantic Authority Reset's own
    conclusion: even though `_first_pullback_entry` (`shadow_comparison.py:
    43-64`) physically reads `reaction.get("path")` -- a candle series
    produced inside this SAME evaluation package by Calculator F/G -- its
    0.5% `pullback_retrace_pct` threshold, 60-minute lookback, and
    direction/OVERREACTION-gated scan ALGORITHM are a program-specific
    research technique, not a generic forward-measurement primitive.
    `ReferenceResolutionKind.PRE_RESOLVED_REFERENCE` replaces the removed
    `RETRACEMENT_SCAN`: UEF-2B never implements the scan, it only consumes
    an already-resolved reference (`provenance="FIRST_PULLBACK_ENTRY"`).
    """

    reference = _pre_resolved_ref(provenance="FIRST_PULLBACK_ENTRY")
    checkpoint = HorizonSpec(
        label="EOD", kind=HorizonKind.SESSION_CLOSE, origin=EventOrigin.FIXED_CLOCK,
        observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), selection=ObservationSelectionMode.LAST_AVAILABLE, lookahead=None, missing=MissingResolutionPolicy.KEEP_PENDING),
        excursion=ExcursionPolicy(
            window_end=MfeMaeWindowEnd.UNBOUNDED_FORWARD, start_inclusive=True, end_inclusive=True,
            mfe_price_resolution=_chain(PriceCandidate.BAR_CLOSE), mae_price_resolution=_chain(PriceCandidate.BAR_CLOSE),
            direction_aware=True,
        ),
        fixed_clock=FixedClockSpec(clock_label="15:30"),
    )
    return ForwardPolicy(
        legacy_program="baseline_samsung_hynix_forward_validation_shadow_comparison",
        horizons=(checkpoint,), gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS, direction=TradeDirection.SHORT),
        reference_resolution=reference,
        source_result_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        cost_note="build_shadow_comparison populates BOTH gross_eod_return_pct AND net_eod_return_pct=gross-total_cost in the same outcome row (shadow_comparison.py:112-113)",
    )


# =========================================================================
# 8. Q11 Opportunity Engine -- opportunity_engine/simulator.py (unflagged, unchanged)
# =========================================================================


def build_q11_opportunity_engine_profile() -> ForwardPolicy:
    """Zero-offset ACTUAL_EXIT outcome checkpoint, EOD with NO excursion at all, NET_OR_COST_INCLUDED provenance.

    Q11 EXIT FINAL FIDELITY PATCH (single-HIGH fix, re-verified against source):
    forward-horizon and EXIT excursion have DIFFERENT fallback chains --
    they must never share one `ExcursionPolicy`/chain object.

    - Reference/entry price (unchanged, PASS): `simulate_probe_v0` -- `price
      = float(candle.get("close") or features.get("price") or 0.0)`
      (`simulator.py:125`), carried into `position["entry_price"]` (`:138`)
      and read back as `entry_price` at trade-close time (`:163`). This is
      `BAR_CLOSE -> SOURCE_FIELD_PRICE`.
    - Q11_FORWARD_EXCURSION (+5/15/30/60m, unchanged, PASS): `_forward_
      returns` -- `high = max(float(row.get("high") or row.get("close") or
      0.0) for row in window)` / `low = min(float(row.get("low") or row.get
      ("close") or 0.0) ...)` (`:35-36`) -- this function has NO access to
      `features` at all (plain rows-based scan), so its fallback terminates
      at `BAR_CLOSE`: `BAR_HIGH -> BAR_CLOSE` / `BAR_LOW -> BAR_CLOSE`.
    - Q11_EXIT_EXCURSION (position tracking, FIXED this patch): `high =
      float(candle.get("high") or price)` / `low = float(candle.get("low")
      or price)` (`:147-148`), where `price` is THAT SAME row's own
      `candle.get("close") or features.get("price")`-resolved value
      recomputed every loop iteration (`:125`) -- the fallback chain is one
      level DEEPER than the forward horizons': `BAR_HIGH -> BAR_CLOSE ->
      SOURCE_FIELD_PRICE` / `BAR_LOW -> BAR_CLOSE -> SOURCE_FIELD_PRICE`.
      The prior profile incorrectly reused the SAME 2-deep chain as the
      forward horizons, silently dropping the `SOURCE_FIELD_PRICE` tail.
    - EOD (`:48-77`): unchanged, PASS -- still no `mfe_pct`/`mae_pct` key at
      all, `excursion=None`. Must never inherit EXIT's excursion.
    - `source_result_cost_semantics`: unchanged -- `NET_OR_COST_INCLUDED`.
    """

    q11_forward_excursion_mfe = _chain(PriceCandidate.BAR_HIGH, PriceCandidate.BAR_CLOSE)
    q11_forward_excursion_mae = _chain(PriceCandidate.BAR_LOW, PriceCandidate.BAR_CLOSE)
    q11_exit_excursion_mfe = _chain(PriceCandidate.BAR_HIGH, PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE)
    q11_exit_excursion_mae = _chain(PriceCandidate.BAR_LOW, PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE)
    forward_horizons = tuple(
        HorizonSpec(
            label=label, kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.SIGNAL,
            observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), lookahead=90),
            excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.OWN_CHECKPOINT_OBSERVATION, start_inclusive=True, end_inclusive=True, mfe_price_resolution=q11_forward_excursion_mfe, mae_price_resolution=q11_forward_excursion_mae),
            relative_seconds=seconds,
        )
        for label, seconds in (("+5m", 300), ("+15m", 900), ("+30m", 1800), ("+60m", 3600))
    )
    # EOD: real source populates status/return_pct/net_return_pct/observed_epoch
    # ONLY -- no mfe_pct/mae_pct key at all (simulator.py:56-77). excursion=None.
    eod = HorizonSpec(
        label="EOD", kind=HorizonKind.SESSION_CLOSE, origin=EventOrigin.SIGNAL,
        observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), selection=ObservationSelectionMode.LAST_AVAILABLE, lookahead=None, missing=MissingResolutionPolicy.KEEP_PENDING),
        excursion=None,
        fixed_clock=FixedClockSpec(clock_label="15:30"),
    )
    exit_checkpoint = HorizonSpec(
        label="EXIT", kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.ACTUAL_EXIT,
        observation=_obs(price=_chain(PriceCandidate.FIXED_OBSERVED_PRICE), selection=ObservationSelectionMode.EXACT, lookahead=0, missing=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY),
        excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.ACTUAL_EXIT, start_inclusive=True, end_inclusive=True, mfe_price_resolution=q11_exit_excursion_mfe, mae_price_resolution=q11_exit_excursion_mae),
        relative_seconds=0,
    )
    return ForwardPolicy(
        legacy_program="q11_opportunity_engine", horizons=forward_horizons + (eod, exit_checkpoint),
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_external_ref(price=_chain(PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE), origin=EventOrigin.SIGNAL),
        source_result_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        cost_note="simulator.py both return_pct(gross) and net_return_pct(cost_pct/slippage_pct-adjusted) present in the same result dict",
    )


# =========================================================================
# 9-10. Q12 Calc1 (shared-engine reuse)/Calc2 (unflagged, unchanged)
# =========================================================================


def build_q12_calc1_shared_engine_profile() -> ForwardPolicy:
    """Q12's own `attach_forward_returns` calls `attach_baseline_forward_returns` DIRECTLY -- 7 real checkpoints, not 4.

    Python free-variable resolution by DEFINING scope: `attach_baseline_
    forward_returns`'s `HORIZONS` reference always resolves to
    `baseline_samsung_hynix.contracts.HORIZONS` (its defining module),
    never Q12's own 4-element `baseline_btc_woori_tech.contracts.HORIZONS`
    -- confirmed against the real artifact (all 7 keys present).
    """

    checkpoint_chain = _chain(PriceCandidate.BAR_CLOSE, PriceCandidate.REFERENCE_PRICE)
    excursion_high = _chain(PriceCandidate.BAR_HIGH, PriceCandidate.REFERENCE_PRICE)
    excursion_low = _chain(PriceCandidate.BAR_LOW, PriceCandidate.REFERENCE_PRICE)
    calc_a_labels = {"+5m": 300, "+15m": 900, "+30m": 1800, "+60m": 3600}
    calc_a_horizons = tuple(
        HorizonSpec(
            label=label, kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.CANDIDATE,
            observation=_obs(price=checkpoint_chain, lookahead=180),
            excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.TARGET_TIMESTAMP, start_inclusive=True, end_inclusive=True, mfe_price_resolution=excursion_high, mae_price_resolution=excursion_low),
            relative_seconds=seconds,
        )
        for label, seconds in calc_a_labels.items()
    )
    calc_b_labels = {"+120m": 7200, "+180m": 10800}
    calc_b_horizons = tuple(
        HorizonSpec(
            label=label, kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.CANDIDATE,
            observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), lookahead=90),
            excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.OWN_CHECKPOINT_OBSERVATION, start_inclusive=False, end_inclusive=True, mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH), mae_price_resolution=_chain(PriceCandidate.BAR_LOW)),
            relative_seconds=seconds,
        )
        for label, seconds in calc_b_labels.items()
    )
    eod = HorizonSpec(
        label="EOD", kind=HorizonKind.SESSION_CLOSE, origin=EventOrigin.CANDIDATE,
        observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), selection=ObservationSelectionMode.LAST_AVAILABLE, lookahead=None, missing=MissingResolutionPolicy.KEEP_PENDING),
        excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.OWN_CHECKPOINT_OBSERVATION, start_inclusive=True, end_inclusive=True, mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH), mae_price_resolution=_chain(PriceCandidate.BAR_LOW)),
        fixed_clock=FixedClockSpec(clock_label="15:30"),
    )
    return ForwardPolicy(
        legacy_program="baseline_btc_woori_tech_calc1_shared_engine", horizons=calc_a_horizons + calc_b_horizons + (eod,),
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_external_ref(price=_chain(PriceCandidate.BAR_CLOSE), origin=EventOrigin.CANDIDATE),
        source_result_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
        cost_note="attach_baseline_forward_returns is the SAME quant_shadow_forward_outcomes.py engine as Calc A/B/C -- no net/cost field",
    )


def build_q12_calc2_hypothesis_forward_profile() -> ForwardPolicy:
    """5-label hypothesis_forward.py profile -- +5/15/30/60m + EOD."""

    from libs.reporting.baseline_btc_woori_tech.contracts import HYPOTHESIS_HORIZONS

    horizons = tuple(
        HorizonSpec(
            label=label, kind=HorizonKind.RELATIVE_SECONDS if label != "EOD" else HorizonKind.SESSION_CLOSE, origin=EventOrigin.CANDIDATE,
            observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), lookahead=90) if label != "EOD" else _obs(price=_chain(PriceCandidate.BAR_CLOSE), selection=ObservationSelectionMode.LAST_AVAILABLE, lookahead=None, missing=MissingResolutionPolicy.KEEP_PENDING),
            excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.OWN_CHECKPOINT_OBSERVATION, start_inclusive=True, end_inclusive=True, mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH), mae_price_resolution=_chain(PriceCandidate.BAR_LOW)),
            relative_seconds={"+5m": 300, "+15m": 900, "+30m": 1800, "+60m": 3600}.get(label),
            fixed_clock=FixedClockSpec(clock_label="15:30") if label == "EOD" else None,
        )
        for label in HYPOTHESIS_HORIZONS
    )
    return ForwardPolicy(
        legacy_program="baseline_btc_woori_tech_hypothesis_forward", horizons=horizons,
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_external_ref(price=_chain(PriceCandidate.BAR_CLOSE), origin=EventOrigin.CANDIDATE),
        source_result_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        cost_note="entry_forward_outcomes populates BOTH gross_return_pct AND net_return_pct=gross-drag_pct in the same result dict (hypothesis_forward.py:73-78)",
    )


# =========================================================================
# 11. Q12 Calc3 (vnext) -- baseline_btc_woori_tech/vnext/outcomes.py
# =========================================================================


def build_q12_calc3_vnext_profile() -> ForwardPolicy:
    """09:30/10:00/EOD, end-exclusive except EOD, NOW with continuous-minute completeness (item 12-14, H2).

    Evidence: `outcomes.py::forward` -- `window = [r for r in candles if t
    <= r['ts'] < target]` (`:14`, end-EXCLUSIVE; EOD appends `point` at
    `:22`, making it end-INCLUSIVE), `expected = (target - t) // 60 + (1 if
    horizon == 'EOD' else 0)` (`:23`), `complete = len(window) == expected`
    (`:24`), `mfe_pct`/`mae_pct` are `None` unless `complete` (`:28-29`) --
    a genuine 60-second contiguous-bar completeness gate on the EXCURSION
    scan specifically (the checkpoint's own `gross_return_pct` is reported
    regardless of `complete`). Checkpoint price differs by horizon:
    `exit_price = point['close'] if horizon == 'EOD' else point['open']`
    (`:20`) -- BAR_OPEN for 09:30/10:00, BAR_CLOSE for EOD.
    """

    def _completeness() -> DataCompletenessPolicy:
        return DataCompletenessPolicy(kind=DataCompletenessKind.CONTIGUOUS_INTERVAL, interval_seconds=60.0, require_all_expected_observations=True)

    def _intraday(label: str) -> HorizonSpec:
        return HorizonSpec(
            label=label, kind=HorizonKind.FIXED_CLOCK_TARGET, origin=EventOrigin.FIXED_CLOCK,
            observation=_obs(price=_chain(PriceCandidate.BAR_OPEN), selection=ObservationSelectionMode.EXACT, lookahead=0, missing=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY),
            excursion=ExcursionPolicy(
                window_end=MfeMaeWindowEnd.TARGET_TIMESTAMP, start_inclusive=True, end_inclusive=False,
                mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH), mae_price_resolution=_chain(PriceCandidate.BAR_LOW),
                mfe_floor_zero=True, mae_cap_zero=True, completeness=_completeness(),
            ),
            fixed_clock=FixedClockSpec(clock_label=label),
        )

    vnext_0930 = _intraday("09:30")
    vnext_1000 = _intraday("10:00")
    vnext_eod = HorizonSpec(
        label="EOD", kind=HorizonKind.SESSION_CLOSE, origin=EventOrigin.FIXED_CLOCK,
        observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), selection=ObservationSelectionMode.EXACT, lookahead=0, missing=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY),
        excursion=ExcursionPolicy(
            window_end=MfeMaeWindowEnd.TARGET_TIMESTAMP, start_inclusive=True, end_inclusive=True,
            mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH), mae_price_resolution=_chain(PriceCandidate.BAR_LOW),
            mfe_floor_zero=True, mae_cap_zero=True, completeness=_completeness(),
        ),
        fixed_clock=FixedClockSpec(clock_label="15:30"),
    )
    return ForwardPolicy(
        legacy_program="baseline_btc_woori_tech_vnext", horizons=(vnext_0930, vnext_1000, vnext_eod),
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_external_ref(price=_chain(PriceCandidate.FIXED_OBSERVED_PRICE), origin=EventOrigin.CANDIDATE),
        source_result_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        cost_note="outcomes.py::forward populates BOTH gross_return_pct AND net_return_pct=gross-drag_pct in the same result dict (vnext/outcomes.py:25-27)",
    )


# =========================================================================
# 12. Opening Shadow 1A -- opening_rank1_shadow/latent_forward.py::_observe
# =========================================================================


def build_opening_shadow_1a_profile() -> ForwardPolicy:
    """Entry/forward price chains DIFFER; excursion fallback FIXED to include REFERENCE_PRICE (item 21-22, H4).

    Evidence: `_observe` -- `high = max(_number(value.get("high")) or
    entry_price for value in window)` / `low = min(_number(value.get("low"))
    or entry_price ...)` (`latent_forward.py:122-123`) -- BAR_HIGH/BAR_LOW
    fall back to the episode's OWN already-resolved `entry_price`
    (`REFERENCE_PRICE`) when a candle's high/low is missing/zero, for BOTH
    the intraday checkpoints and EOD (EOD reuses the identical `high`/`low`
    computation at `:122-123` inside the same loop body). The prior profile
    omitted this fallback entirely (bare `BAR_HIGH`/`BAR_LOW`, no chain).
    """

    reference = _external_ref(price=_chain(PriceCandidate.BAR_OPEN, PriceCandidate.BAR_CLOSE), origin=EventOrigin.SIGNAL)
    excursion_high = _chain(PriceCandidate.BAR_HIGH, PriceCandidate.REFERENCE_PRICE)
    excursion_low = _chain(PriceCandidate.BAR_LOW, PriceCandidate.REFERENCE_PRICE)
    minute_labels = {"+5m": 300, "+15m": 900, "+30m": 1800, "+60m": 3600}
    horizons = tuple(
        HorizonSpec(
            label=label, kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.SIGNAL,
            observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE, PriceCandidate.REFERENCE_PRICE), lookahead=180),
            excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.TARGET_TIMESTAMP, start_inclusive=True, end_inclusive=True, mfe_price_resolution=excursion_high, mae_price_resolution=excursion_low),
            relative_seconds=seconds,
        )
        for label, seconds in minute_labels.items()
    )
    eod = HorizonSpec(
        label="EOD", kind=HorizonKind.SESSION_CLOSE, origin=EventOrigin.SIGNAL,
        observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE, PriceCandidate.REFERENCE_PRICE), selection=ObservationSelectionMode.LAST_AVAILABLE, lookahead=None, missing=MissingResolutionPolicy.KEEP_PENDING),
        excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.OWN_CHECKPOINT_OBSERVATION, start_inclusive=True, end_inclusive=True, mfe_price_resolution=excursion_high, mae_price_resolution=excursion_low),
        fixed_clock=FixedClockSpec(clock_label="15:20"),
    )
    return ForwardPolicy(
        legacy_program="opening_rank1_shadow_latent_forward", horizons=horizons + (eod,),
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS), reference_resolution=reference,
        source_result_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
        cost_note="_observe's checkpoints only ever carry gross_return_pct; cost/net figures are computed separately downstream in _summary() via cost_bases, never inside the per-episode checkpoint itself",
    )


# =========================================================================
# 13. Opening Shadow 1B -- opening_rank1_longitudinal/delayed_outcomes.py::forward_30m_net (unflagged)
# =========================================================================


def build_opening_shadow_1b_profile() -> ForwardPolicy:
    """Single +30m checkpoint; unbounded forward search; output already cost-net -- no separate gross field."""

    horizon = HorizonSpec(
        label="+30m", kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.MONITOR_DECISION,
        observation=_obs(price=_chain(PriceCandidate.BAR_OPEN, PriceCandidate.BAR_CLOSE), lookahead=None),
        excursion=None,
        relative_seconds=1800,
    )
    return ForwardPolicy(
        legacy_program="opening_rank1_longitudinal_forward_30m_net", horizons=(horizon,),
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_external_ref(price=_chain(PriceCandidate.BAR_OPEN, PriceCandidate.BAR_CLOSE), origin=EventOrigin.MONITOR_DECISION),
        source_result_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        cost_note="_net() bakes ROUND_TRIP_COST_PCT=0.28 into the only return figure this function produces; no separate gross field exists",
    )


# =========================================================================
# 14. Opening Shadow 1C -- opening_rank1_longitudinal/delayed_outcomes.py::delayed_path
# =========================================================================


def build_opening_shadow_1c_profile() -> ForwardPolicy:
    """d1/d3/d5: excursion window bound FIXED to FORWARD_SESSION_BOUND, missing FIXED to MARK_MISSING_IMMEDIATELY (item 16-20, H3).

    Evidence: `delayed_path` -- MFE (`d{n}_max_high_net_pct`) is scanned
    over `selected_rows = [row for day in selected_days for row in
    grouped.get(day) or []]` where `selected_days = future_days[:horizon]`
    (`delayed_outcomes.py:118,131-139`) -- EXACTLY the same bounded
    session-count window as the checkpoint itself, never an unbounded
    forward scan. And `d{n}_status = "INSUFFICIENT_FUTURE_DAYS"` fires
    IMMEDIATELY, in the same pass, whenever `len(selected_days) < horizon
    or missing_days` (`:125-130`) -- it never waits/expires, so
    `MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY` is the correct rule
    (canonically producing `MissingObservationStatus.INSUFFICIENT_FUTURE_
    SESSIONS`), not the prior `KEEP_PENDING` (under which that status was
    dangling/unreachable).
    """

    def _forward_session_horizon(label: str, offset: int) -> HorizonSpec:
        return HorizonSpec(
            label=label, kind=HorizonKind.FORWARD_SESSION, origin=EventOrigin.CUSTOM,
            observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), selection=ObservationSelectionMode.LAST_AVAILABLE, lookahead=None, missing=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY),
            excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.FORWARD_SESSION_BOUND, start_inclusive=True, end_inclusive=True, mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH)),  # MFE-only, no MAE
            forward_session=ForwardSessionSpec(resolver_authority=ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS, session_offset=offset, required_available_sessions=offset),
        )

    d1, d3, d5 = _forward_session_horizon("d1", 1), _forward_session_horizon("d3", 3), _forward_session_horizon("d5", 5)
    return ForwardPolicy(
        legacy_program="opening_rank1_longitudinal_delayed_path", horizons=(d1, d3, d5),
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_external_ref(price=_chain(PriceCandidate.FIXED_OBSERVED_PRICE), origin=EventOrigin.CUSTOM),
        source_result_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        cost_note="delayed_path uses the SAME _net() helper as forward_30m_net (ROUND_TRIP_COST_PCT=0.28 baked in) for every d{n}_max_high_net_pct/d{n}_close_net_pct field -- no separate gross field exists at all",
    )


# =========================================================================
# Registry
# =========================================================================

_BUILDERS: tuple[tuple[int, str, str, Callable[[], ForwardPolicy]], ...] = (
    (1, "q9_horizon_exit", "libs/runtime/strategy_horizon_feedback.py", build_q9_horizon_exit_profile),
    (2, "q10_semiconductor_calc_a", "libs/reporting/quant_shadow_forward_outcomes.py::attach_forward_outcomes", build_q10_semiconductor_calc_a_profile),
    (3, "q10_semiconductor_calc_b", "libs/reporting/baseline_samsung_hynix/forward_returns.py::_extended_checkpoint", build_q10_semiconductor_calc_b_profile),
    (4, "q10_semiconductor_calc_c", "libs/reporting/baseline_samsung_hynix/forward_returns.py (inline EOD override)", build_q10_semiconductor_calc_c_profile),
    (5, "q10_index_calc_f", "libs/reporting/baseline_samsung_hynix/forward_validation/reaction_reader.py::_stock_reaction/_forward_window", build_q10_index_calc_f_profile),
    (6, "q10_index_calc_g", "libs/reporting/baseline_samsung_hynix/forward_validation/reaction_reader.py::_index_reaction", build_q10_index_calc_g_profile),
    (7, "q10_index_calc_h", "libs/reporting/baseline_samsung_hynix/forward_validation/shadow_comparison.py::build_shadow_comparison", build_q10_index_calc_h_profile),
    (8, "q11_opportunity_engine", "libs/research/opportunity_engine/simulator.py::simulate_probe_v0", build_q11_opportunity_engine_profile),
    (9, "q12_calc1_shared_engine", "libs/reporting/baseline_btc_woori_tech/forward_returns.py::attach_forward_returns", build_q12_calc1_shared_engine_profile),
    (10, "q12_calc2_hypothesis_forward", "libs/reporting/baseline_btc_woori_tech/hypothesis_forward.py", build_q12_calc2_hypothesis_forward_profile),
    (11, "q12_calc3_vnext", "libs/reporting/baseline_btc_woori_tech/vnext/outcomes.py::forward", build_q12_calc3_vnext_profile),
    (12, "opening_shadow_1a", "libs/reporting/opening_rank1_shadow/latent_forward.py::_observe", build_opening_shadow_1a_profile),
    (13, "opening_shadow_1b", "libs/research/opening_rank1_longitudinal/delayed_outcomes.py::forward_30m_net", build_opening_shadow_1b_profile),
    (14, "opening_shadow_1c", "libs/research/opening_rank1_longitudinal/delayed_outcomes.py::delayed_path", build_opening_shadow_1c_profile),
)


def _build_registry() -> dict[int, CalculatorProfile]:
    registry: dict[int, CalculatorProfile] = {}
    for number, name, source, builder in _BUILDERS:
        registry[number] = CalculatorProfile(number=number, name=name, source=source, policy=builder())
    return registry


PROFILE_REGISTRY: dict[int, CalculatorProfile] = _build_registry()


def all_profiles() -> tuple[CalculatorProfile, ...]:
    return tuple(PROFILE_REGISTRY[number] for number in sorted(PROFILE_REGISTRY))


__all__ = ["CalculatorProfile", "PROFILE_REGISTRY", "all_profiles"]
