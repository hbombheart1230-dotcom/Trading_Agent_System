"""UEF-2B -- generic forward-engine primitive tests.

Additive-only: exercises `libs/reporting/evaluation/canonical/forward/engine.py`
only, with hand-built fixture data (never a real legacy artifact -- that is
what `test_uef2b_profile_execution.py` does with the frozen profiles). No
existing evaluator/report/runtime module is imported.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from libs.reporting.evaluation.canonical.contracts import EventOrigin, ReturnUnit
from libs.reporting.evaluation.canonical.forward.contracts import (
    DataCompletenessKind,
    EvidenceVerificationState,
    ForwardSessionResolverAuthority,
    HorizonKind,
    MfeMaeWindowEnd,
    MissingObservationStatus,
    MissingResolutionPolicy,
    ObservationSelectionMode,
    PriceCandidate,
    TradeDirection,
)
from libs.reporting.evaluation.canonical.forward.policy import (
    DataCompletenessPolicy,
    ExcursionPolicy,
    FixedClockSpec,
    ForwardSessionSpec,
    GrossReturnPolicy,
    HorizonSpec,
    ObservationPolicy,
    PriceResolutionPolicy,
    SessionCloseSpec,
)
from libs.reporting.evaluation.canonical.forward.engine import (
    CanonicalObservation,
    EngineInputError,
    ResolvedOrigin,
    ResolvedReference,
    SessionContext,
    UEF2AFreezeBlocker,
    calculate_gross_return,
    resolve_excursion,
    resolve_forward_session,
    resolve_missing,
    resolve_observation,
    resolve_ordered_price,
    resolve_session_close,
    resolve_target,
    validate_completeness,
    validate_evidence,
)

KST = _dt.timezone(_dt.timedelta(hours=9))


def kst_epoch(date: str, hh: int, mm: int) -> int:
    return int(_dt.datetime.fromisoformat(date).replace(hour=hh, minute=mm, tzinfo=KST).timestamp())


def chain(*candidates: PriceCandidate) -> PriceResolutionPolicy:
    return PriceResolutionPolicy(authorities=candidates)


def make_reference(*, origin: EventOrigin = EventOrigin.SIGNAL, timestamp: int, price: float | None) -> ResolvedReference:
    return ResolvedReference.single(origin=origin, timestamp=timestamp, price=price)


def obs(ts: int, **fields) -> CanonicalObservation:
    mapped = {PriceCandidate[key.upper()]: value for key, value in fields.items() if key not in ("volume", "evidence")}
    return CanonicalObservation(timestamp=ts, fields=mapped, volume=fields.get("volume"), evidence=fields.get("evidence"))


# =========================================================================
# resolve_ordered_price / item 6, 34
# =========================================================================


def test_ordered_price_primary_present_returns_primary():
    ref = make_reference(timestamp=1000, price=100.0)
    o = obs(1000, bar_close=105.0, bar_high=110.0)
    result = resolve_ordered_price(chain(PriceCandidate.BAR_CLOSE, PriceCandidate.REFERENCE_PRICE), observation=o, resolved_reference=ref)
    assert result.price == 105.0
    assert result.candidate_used is PriceCandidate.BAR_CLOSE


def test_ordered_price_primary_absent_falls_back():
    ref = make_reference(timestamp=1000, price=100.0)
    o = obs(1000)  # BAR_CLOSE missing entirely
    result = resolve_ordered_price(chain(PriceCandidate.BAR_CLOSE, PriceCandidate.REFERENCE_PRICE), observation=o, resolved_reference=ref)
    assert result.price == 100.0
    assert result.candidate_used is PriceCandidate.REFERENCE_PRICE


def test_ordered_price_multiple_fallback_first_valid_wins():
    ref = make_reference(timestamp=1000, price=100.0)
    o = obs(1000, source_field_price=None, source_field_current_price=77.0, source_field_cur_price=88.0)
    result = resolve_ordered_price(chain(PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE, PriceCandidate.SOURCE_FIELD_CURRENT_PRICE, PriceCandidate.SOURCE_FIELD_CUR_PRICE), observation=o, resolved_reference=ref)
    assert result.price == 77.0
    assert result.candidate_used is PriceCandidate.SOURCE_FIELD_CURRENT_PRICE


def test_ordered_price_all_absent_is_missing():
    ref = make_reference(timestamp=1000, price=None)
    o = obs(1000)
    result = resolve_ordered_price(chain(PriceCandidate.BAR_CLOSE, PriceCandidate.REFERENCE_PRICE), observation=o, resolved_reference=ref)
    assert result.price is None
    assert result.candidate_used is None


def test_ordered_price_zero_and_negative_and_nonfinite_are_never_valid():
    ref = make_reference(timestamp=1000, price=100.0)
    o = obs(1000, bar_close=0.0, bar_open=-5.0, bar_high=float("nan"))
    assert resolve_ordered_price(chain(PriceCandidate.BAR_CLOSE, PriceCandidate.REFERENCE_PRICE), observation=o, resolved_reference=ref).candidate_used is PriceCandidate.REFERENCE_PRICE
    assert resolve_ordered_price(chain(PriceCandidate.BAR_OPEN, PriceCandidate.REFERENCE_PRICE), observation=o, resolved_reference=ref).candidate_used is PriceCandidate.REFERENCE_PRICE
    assert resolve_ordered_price(chain(PriceCandidate.BAR_HIGH, PriceCandidate.REFERENCE_PRICE), observation=o, resolved_reference=ref).candidate_used is PriceCandidate.REFERENCE_PRICE


def test_ordered_price_fixed_observed_price_reads_current_origin_not_observation():
    ref = ResolvedReference(primary_origin=EventOrigin.SIGNAL, origins={EventOrigin.SIGNAL: ResolvedOrigin(timestamp=1000, price=100.0), EventOrigin.ACTUAL_EXIT: ResolvedOrigin(timestamp=2000, price=250.0)})
    o = obs(2000)  # no fields at all
    result = resolve_ordered_price(chain(PriceCandidate.FIXED_OBSERVED_PRICE), observation=o, resolved_reference=ref, current_origin=ref.origin_for(EventOrigin.ACTUAL_EXIT))
    assert result.price == 250.0
    assert result.candidate_used is PriceCandidate.FIXED_OBSERVED_PRICE


def test_ordered_price_q11_exit_three_deep_chain_executes_generically():
    # The exact Q11 EXIT chain (BAR_HIGH -> BAR_CLOSE -> SOURCE_FIELD_PRICE)
    # run through the plain generic primitive, with no Q11-specific code.
    ref = make_reference(timestamp=1000, price=100.0)
    only_source_field = obs(1000, source_field_price=42.0)
    result = resolve_ordered_price(chain(PriceCandidate.BAR_HIGH, PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE), observation=only_source_field, resolved_reference=ref)
    assert result.price == 42.0
    assert result.candidate_used is PriceCandidate.SOURCE_FIELD_PRICE


# =========================================================================
# validate_evidence / item 16
# =========================================================================


def _obs_policy(**kwargs) -> ObservationPolicy:
    defaults = dict(selection_mode=ObservationSelectionMode.EXACT, price_resolution=chain(PriceCandidate.BAR_CLOSE), missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY)
    defaults.update(kwargs)
    return ObservationPolicy(**defaults)


def test_validate_evidence_none_requirement_always_passes():
    policy = _obs_policy()
    assert validate_evidence(policy, None) is True
    assert validate_evidence(policy, obs(1)) is True


def test_validate_evidence_matching_state_passes():
    policy = _obs_policy(price_resolution=chain(PriceCandidate.QUOTE), evidence_requirement=EvidenceVerificationState.VERIFIED)
    assert validate_evidence(policy, obs(1, quote=100.0, evidence=EvidenceVerificationState.VERIFIED)) is True


def test_validate_evidence_mismatched_state_fails():
    policy = _obs_policy(price_resolution=chain(PriceCandidate.BAR_CLOSE), missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY, evidence_requirement=EvidenceVerificationState.INVALID)
    assert validate_evidence(policy, obs(1, bar_close=100.0, evidence=EvidenceVerificationState.ABSENT)) is False


def test_validate_evidence_no_observation_with_requirement_fails():
    policy = _obs_policy(price_resolution=chain(PriceCandidate.QUOTE), evidence_requirement=EvidenceVerificationState.VERIFIED)
    assert validate_evidence(policy, None) is False


# =========================================================================
# validate_completeness / item 18, 35
# =========================================================================


def test_completeness_none_policy_always_complete():
    assert validate_completeness(None, window_start=0, window_end=1000, end_inclusive=False, observations_in_window=[]) is True


def test_completeness_expected_31_actual_31_is_complete():
    policy = DataCompletenessPolicy(kind=DataCompletenessKind.CONTIGUOUS_INTERVAL, interval_seconds=60.0)
    window = [obs(i * 60) for i in range(31)]
    assert validate_completeness(policy, window_start=0, window_end=31 * 60, end_inclusive=False, observations_in_window=window) is True


def test_completeness_expected_31_actual_30_is_incomplete():
    policy = DataCompletenessPolicy(kind=DataCompletenessKind.CONTIGUOUS_INTERVAL, interval_seconds=60.0)
    window = [obs(i * 60) for i in range(30)]
    assert validate_completeness(policy, window_start=0, window_end=31 * 60, end_inclusive=False, observations_in_window=window) is False


def test_completeness_end_inclusive_adds_one_expected():
    policy = DataCompletenessPolicy(kind=DataCompletenessKind.CONTIGUOUS_INTERVAL, interval_seconds=60.0)
    window = [obs(i * 60) for i in range(31)]  # 0..30 inclusive = 31 bars
    assert validate_completeness(policy, window_start=0, window_end=30 * 60, end_inclusive=True, observations_in_window=window) is True


# =========================================================================
# resolve_missing / item 17
# =========================================================================


@pytest.mark.parametrize(
    "missing_resolution,expected",
    [
        (MissingResolutionPolicy.KEEP_PENDING, MissingObservationStatus.TARGET_NOT_REACHED),
        (MissingResolutionPolicy.EXPIRE_AFTER_TOLERANCE, MissingObservationStatus.NO_OBSERVATION_WITHIN_TOLERANCE),
        (MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY, MissingObservationStatus.NO_DATA),
        (MissingResolutionPolicy.USE_SESSION_CLOSE_FALLBACK, MissingObservationStatus.SESSION_ENDED),
    ],
)
def test_resolve_missing_maps_every_policy_deterministically(missing_resolution, expected):
    fallback_spec = SessionCloseSpec(close_clock=FixedClockSpec(clock_label="15:30"), price_resolution=chain(PriceCandidate.BAR_CLOSE)) if missing_resolution is MissingResolutionPolicy.USE_SESSION_CLOSE_FALLBACK else None
    selection_mode = ObservationSelectionMode.FIRST_AT_OR_AFTER if missing_resolution is MissingResolutionPolicy.EXPIRE_AFTER_TOLERANCE else ObservationSelectionMode.EXACT
    lookahead = 90 if missing_resolution is MissingResolutionPolicy.EXPIRE_AFTER_TOLERANCE else None
    policy = _obs_policy(selection_mode=selection_mode, missing_resolution=missing_resolution, lookahead_seconds=lookahead, session_close_fallback=fallback_spec)
    assert resolve_missing(observation_policy=policy, evidence_ok=True) is expected


def test_resolve_missing_evidence_failure_overrides_missing_resolution():
    policy = _obs_policy(missing_resolution=MissingResolutionPolicy.KEEP_PENDING, lookahead_seconds=None)
    assert resolve_missing(observation_policy=policy, evidence_ok=False) is MissingObservationStatus.EVIDENCE_INVALID


# =========================================================================
# resolve_target -- fixed clock / session close / relative / item 8-11, 39, 40
# =========================================================================


def test_resolve_target_relative_seconds():
    ref = make_reference(timestamp=kst_epoch("2026-09-14", 9, 30), price=100.0)
    horizon = HorizonSpec(label="+5m", kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.SIGNAL, observation=_obs_policy(), relative_seconds=300)
    target = resolve_target(horizon, resolved_reference=ref, session_context=None)
    assert target.target_timestamp == kst_epoch("2026-09-14", 9, 35)


def test_resolve_target_fixed_clock_0930():
    ref = make_reference(origin=EventOrigin.FIXED_CLOCK, timestamp=kst_epoch("2026-09-14", 9, 0), price=100.0)
    horizon = HorizonSpec(label="09:30", kind=HorizonKind.FIXED_CLOCK_TARGET, origin=EventOrigin.FIXED_CLOCK, observation=_obs_policy(), fixed_clock=FixedClockSpec(clock_label="09:30"))
    target = resolve_target(horizon, resolved_reference=ref, session_context=None)
    assert target.target_timestamp == kst_epoch("2026-09-14", 9, 30)


def test_resolve_target_fixed_clock_1000():
    ref = make_reference(origin=EventOrigin.FIXED_CLOCK, timestamp=kst_epoch("2026-09-14", 9, 0), price=100.0)
    horizon = HorizonSpec(label="10:00", kind=HorizonKind.FIXED_CLOCK_TARGET, origin=EventOrigin.FIXED_CLOCK, observation=_obs_policy(), fixed_clock=FixedClockSpec(clock_label="10:00"))
    target = resolve_target(horizon, resolved_reference=ref, session_context=None)
    assert target.target_timestamp == kst_epoch("2026-09-14", 10, 0)


def test_resolve_target_fixed_clock_anchors_to_origin_own_calendar_date_not_hidden_today():
    # A reference far from "today" must still resolve on ITS OWN date -- proves
    # no hidden datetime.now()/date.today() is used (item 29).
    ref = make_reference(origin=EventOrigin.FIXED_CLOCK, timestamp=kst_epoch("2020-01-02", 9, 0), price=100.0)
    horizon = HorizonSpec(label="09:30", kind=HorizonKind.FIXED_CLOCK_TARGET, origin=EventOrigin.FIXED_CLOCK, observation=_obs_policy(), fixed_clock=FixedClockSpec(clock_label="09:30"))
    target = resolve_target(horizon, resolved_reference=ref, session_context=None)
    assert target.target_timestamp == kst_epoch("2020-01-02", 9, 30)


def test_resolve_target_session_close_eod():
    ref = make_reference(timestamp=kst_epoch("2026-09-14", 9, 0), price=100.0)
    horizon = HorizonSpec(label="EOD", kind=HorizonKind.SESSION_CLOSE, origin=EventOrigin.SIGNAL, observation=_obs_policy(selection_mode=ObservationSelectionMode.LAST_AVAILABLE, missing_resolution=MissingResolutionPolicy.KEEP_PENDING, lookahead_seconds=None), fixed_clock=FixedClockSpec(clock_label="15:30"))
    target = resolve_target(horizon, resolved_reference=ref, session_context=None)
    assert target.target_timestamp == kst_epoch("2026-09-14", 15, 30)
    # observed timestamp must stay separate from target timestamp (item 14/42):
    observations = [obs(kst_epoch("2026-09-14", 15, 25), bar_close=99.0), obs(kst_epoch("2026-09-14", 15, 40), bar_close=101.0)]
    found = resolve_observation(horizon.observation, target=target, observations=observations)
    assert found.timestamp == kst_epoch("2026-09-14", 15, 40)
    assert found.timestamp != target.target_timestamp


# =========================================================================
# resolve_forward_session / item 12-13, 36
# =========================================================================


def _fs_spec(offset: int, required: int) -> ForwardSessionSpec:
    return ForwardSessionSpec(resolver_authority=ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS, session_offset=offset, required_available_sessions=required)


def test_forward_session_required_1_have_1_resolves():
    ctx = SessionContext(future_session_dates=("2026-09-15",), sessions_with_observations=frozenset({"2026-09-15"}))
    date, missing = resolve_forward_session(_fs_spec(1, 1), origin_timestamp=0, session_context=ctx)
    assert date == "2026-09-15" and missing is None


def test_forward_session_required_3_have_3_resolves():
    ctx = SessionContext(future_session_dates=("2026-09-15", "2026-09-16", "2026-09-17"), sessions_with_observations=frozenset({"2026-09-15", "2026-09-16", "2026-09-17"}))
    date, missing = resolve_forward_session(_fs_spec(3, 3), origin_timestamp=0, session_context=ctx)
    assert date == "2026-09-17" and missing is None


def test_forward_session_required_5_have_5_resolves():
    dates = tuple(f"2026-09-{15 + i}" for i in range(5))
    ctx = SessionContext(future_session_dates=dates, sessions_with_observations=frozenset(dates))
    date, missing = resolve_forward_session(_fs_spec(5, 5), origin_timestamp=0, session_context=ctx)
    assert date == dates[-1] and missing is None


def test_forward_session_required_5_have_4_is_insufficient():
    dates = tuple(f"2026-09-{15 + i}" for i in range(4))
    ctx = SessionContext(future_session_dates=dates, sessions_with_observations=frozenset(dates))
    date, missing = resolve_forward_session(_fs_spec(5, 5), origin_timestamp=0, session_context=ctx)
    assert date is None
    assert missing is MissingObservationStatus.INSUFFICIENT_FUTURE_SESSIONS


def test_forward_session_never_substitutes_a_shorter_horizon():
    # required=5 with only 3 available and 3 having data -- must NOT fall
    # back to resolving as if it were d3 (item 13).
    dates = ("2026-09-15", "2026-09-16", "2026-09-17")
    ctx = SessionContext(future_session_dates=dates, sessions_with_observations=frozenset(dates))
    date, missing = resolve_forward_session(_fs_spec(5, 5), origin_timestamp=0, session_context=ctx)
    assert date is None
    assert missing is MissingObservationStatus.INSUFFICIENT_FUTURE_SESSIONS
    assert date != dates[-1]


def test_forward_session_intermediate_gap_is_insufficient_even_with_enough_calendar_days():
    dates = ("2026-09-15", "2026-09-16", "2026-09-17")
    ctx = SessionContext(future_session_dates=dates, sessions_with_observations=frozenset({"2026-09-15", "2026-09-17"}))  # day 2 missing data
    date, missing = resolve_forward_session(_fs_spec(3, 3), origin_timestamp=0, session_context=ctx)
    assert date is None
    assert missing is MissingObservationStatus.INSUFFICIENT_FUTURE_SESSIONS


# =========================================================================
# resolve_session_close / item 11
# =========================================================================


def test_resolve_session_close_epoch():
    spec = SessionCloseSpec(close_clock=FixedClockSpec(clock_label="15:30"), price_resolution=chain(PriceCandidate.BAR_CLOSE))
    assert resolve_session_close(spec, calendar_date="2026-09-14") == kst_epoch("2026-09-14", 15, 30)


# =========================================================================
# calculate_gross_return / item 23-25
# =========================================================================


def test_gross_return_percentage_points_long():
    policy = GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS, direction=TradeDirection.LONG)
    assert calculate_gross_return(reference_price=100.0, observed_price=110.0, policy=policy) == pytest.approx(10.0)


def test_gross_return_fraction_long_never_multiplied_by_100():
    policy = GrossReturnPolicy(return_unit=ReturnUnit.FRACTION, direction=TradeDirection.LONG)
    result = calculate_gross_return(reference_price=100.0, observed_price=110.0, policy=policy)
    assert -1.0 < result < 1.0
    assert result == pytest.approx(0.10)


def test_gross_return_short_inverts_sign():
    policy = GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS, direction=TradeDirection.SHORT)
    assert calculate_gross_return(reference_price=100.0, observed_price=110.0, policy=policy) == pytest.approx(-10.0)


# =========================================================================
# resolve_excursion / item 20-24, 37
# =========================================================================


def test_excursion_long_mfe_mae():
    ref = make_reference(timestamp=0, price=100.0)
    window = [obs(60, bar_high=112.0, bar_low=95.0), obs(120, bar_high=108.0, bar_low=90.0)]
    excursion = ExcursionPolicy(window_end=MfeMaeWindowEnd.UNBOUNDED_FORWARD, start_inclusive=True, end_inclusive=True, mfe_price_resolution=chain(PriceCandidate.BAR_HIGH), mae_price_resolution=chain(PriceCandidate.BAR_LOW))
    mfe, mae = resolve_excursion(excursion, window_observations=window, resolved_reference=ref, reference_price=100.0, return_unit=ReturnUnit.PERCENTAGE_POINTS, direction=TradeDirection.LONG, complete=True)
    assert mfe.price == 112.0 and mfe.move == pytest.approx(12.0)
    assert mae.price == 90.0 and mae.move == pytest.approx(-10.0)


def test_excursion_short_direction_aware_flips_extremes():
    # A SHORT, direction_aware excursion computes signed moves -- MFE is the
    # BEST directionally-signed move (a price DROP for SHORT), MAE the worst.
    ref = make_reference(timestamp=0, price=100.0)
    window = [obs(60, bar_close=112.0), obs(120, bar_close=90.0)]
    excursion = ExcursionPolicy(window_end=MfeMaeWindowEnd.UNBOUNDED_FORWARD, start_inclusive=True, end_inclusive=True, mfe_price_resolution=chain(PriceCandidate.BAR_CLOSE), mae_price_resolution=chain(PriceCandidate.BAR_CLOSE), direction_aware=True)
    mfe, mae = resolve_excursion(excursion, window_observations=window, resolved_reference=ref, reference_price=100.0, return_unit=ReturnUnit.PERCENTAGE_POINTS, direction=TradeDirection.SHORT, complete=True)
    assert mfe.price == 90.0 and mfe.move == pytest.approx(10.0)  # best for SHORT: price fell
    assert mae.price == 112.0 and mae.move == pytest.approx(-12.0)  # worst for SHORT: price rose


def test_excursion_floor_and_cap_zero():
    ref = make_reference(timestamp=0, price=100.0)
    window = [obs(60, bar_high=99.0, bar_low=101.0)]  # MFE would be negative, MAE would be positive
    excursion = ExcursionPolicy(window_end=MfeMaeWindowEnd.UNBOUNDED_FORWARD, start_inclusive=True, end_inclusive=True, mfe_price_resolution=chain(PriceCandidate.BAR_HIGH), mae_price_resolution=chain(PriceCandidate.BAR_LOW), mfe_floor_zero=True, mae_cap_zero=True)
    mfe, mae = resolve_excursion(excursion, window_observations=window, resolved_reference=ref, reference_price=100.0, return_unit=ReturnUnit.PERCENTAGE_POINTS, direction=TradeDirection.LONG, complete=True)
    assert mfe.move == 0.0
    assert mae.move == 0.0


def test_excursion_gated_off_entirely_when_incomplete():
    ref = make_reference(timestamp=0, price=100.0)
    window = [obs(60, bar_high=112.0, bar_low=95.0)]
    completeness = DataCompletenessPolicy(kind=DataCompletenessKind.CONTIGUOUS_INTERVAL, interval_seconds=60.0)
    excursion = ExcursionPolicy(window_end=MfeMaeWindowEnd.TARGET_TIMESTAMP, start_inclusive=True, end_inclusive=False, mfe_price_resolution=chain(PriceCandidate.BAR_HIGH), mae_price_resolution=chain(PriceCandidate.BAR_LOW), completeness=completeness)
    mfe, mae = resolve_excursion(excursion, window_observations=window, resolved_reference=ref, reference_price=100.0, return_unit=ReturnUnit.PERCENTAGE_POINTS, direction=TradeDirection.LONG, complete=False)
    assert mfe is None and mae is None


def test_excursion_mae_only_returns_none_for_mfe():
    ref = make_reference(timestamp=0, price=100.0)
    window = [obs(60, bar_high=112.0, bar_low=95.0)]
    excursion = ExcursionPolicy(window_end=MfeMaeWindowEnd.UNBOUNDED_FORWARD, start_inclusive=True, end_inclusive=True, mfe_price_resolution=None, mae_price_resolution=chain(PriceCandidate.BAR_LOW))
    mfe, mae = resolve_excursion(excursion, window_observations=window, resolved_reference=ref, reference_price=100.0, return_unit=ReturnUnit.PERCENTAGE_POINTS, direction=TradeDirection.LONG, complete=True)
    assert mfe is None
    assert mae is not None


# =========================================================================
# Missing price / item 41
# =========================================================================


def test_missing_price_when_all_candidates_absent_never_defaults_to_zero_or_reference():
    ref = make_reference(timestamp=0, price=None)
    o = obs(60)  # observation exists, but no field resolves
    result = resolve_ordered_price(chain(PriceCandidate.BAR_CLOSE, PriceCandidate.BAR_OPEN), observation=o, resolved_reference=ref)
    assert result.price is None
    assert result.candidate_used is None


# =========================================================================
# Architecture stop-gate / item 48
# =========================================================================


def test_unsupported_horizon_kind_raises_freeze_blocker_not_silently_branches():
    ref = make_reference(timestamp=0, price=100.0)

    class _FakeHorizon:
        label = "fake"
        kind = "NOT_A_REAL_KIND"
        origin = EventOrigin.SIGNAL

    with pytest.raises((UEF2AFreezeBlocker, AttributeError, ValueError)):
        resolve_target(_FakeHorizon(), resolved_reference=ref, session_context=None)


def test_missing_origin_in_resolved_reference_raises_engine_input_error():
    ref = make_reference(origin=EventOrigin.SIGNAL, timestamp=0, price=100.0)
    with pytest.raises(EngineInputError):
        ref.origin_for(EventOrigin.ACTUAL_EXIT)
