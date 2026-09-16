"""UEF-2B FIX1 -- focused regression tests for the independent audit's H1-H6 findings.

Each test is named after the finding it closes. Additive-only; exercises
`libs/reporting/evaluation/canonical/forward/engine.py` only.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from libs.reporting.evaluation.canonical.contracts import EventOrigin, ReturnUnit
from libs.reporting.evaluation.canonical.forward.contracts import (
    DataCompletenessKind,
    HorizonKind,
    MfeMaeWindowEnd,
    MissingResolutionPolicy,
    ObservationSelectionMode,
    PriceCandidate,
    ReferenceResolutionKind,
    TradeDirection,
)
from libs.reporting.evaluation.canonical.forward.policy import (
    DataCompletenessPolicy,
    ExcursionPolicy,
    FixedClockSpec,
    ForwardPolicy,
    GrossReturnPolicy,
    HorizonSpec,
    ObservationPolicy,
    PriceResolutionPolicy,
    ReferenceResolutionPolicy,
)
from libs.reporting.evaluation.canonical.forward.engine import (
    AmbiguousObservationError,
    CanonicalObservation,
    ResolvedOrigin,
    ResolvedReference,
    evaluate_forward,
    resolve_observation,
    TargetResolution,
    validate_completeness,
)

KST = _dt.timezone(_dt.timedelta(hours=9))


def kst(date: str, hh: int, mm: int, ss: int = 0) -> int:
    return int(_dt.datetime.fromisoformat(date).replace(hour=hh, minute=mm, second=ss, tzinfo=KST).timestamp())


def chain(*candidates: PriceCandidate) -> PriceResolutionPolicy:
    return PriceResolutionPolicy(authorities=candidates)


def obs(ts: int, **fields) -> CanonicalObservation:
    mapped = {PriceCandidate[key.upper()]: value for key, value in fields.items() if key not in ("volume", "evidence")}
    return CanonicalObservation(timestamp=ts, fields=mapped, volume=fields.get("volume"), evidence=fields.get("evidence"))


def _obs_policy(**kwargs) -> ObservationPolicy:
    defaults = dict(selection_mode=ObservationSelectionMode.EXACT, price_resolution=chain(PriceCandidate.BAR_CLOSE), missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY)
    defaults.update(kwargs)
    return ObservationPolicy(**defaults)


DAY = "2026-09-14"


# =========================================================================
# H1 -- Q12 timestamp continuity, not row count
# =========================================================================


def test_h1_31_expected_31_unique_contiguous_is_complete():
    start = kst(DAY, 9, 0)
    window = [obs(start + i * 60) for i in range(31)]
    assert validate_completeness(DataCompletenessPolicy(kind=DataCompletenessKind.CONTIGUOUS_INTERVAL, interval_seconds=60.0), window_start=start, window_end=start + 30 * 60, end_inclusive=True, observations_in_window=window) is True


def test_h1_31_expected_30_actual_is_incomplete():
    start = kst(DAY, 9, 0)
    window = [obs(start + i * 60) for i in range(30)]
    assert validate_completeness(DataCompletenessPolicy(kind=DataCompletenessKind.CONTIGUOUS_INTERVAL, interval_seconds=60.0), window_start=start, window_end=start + 30 * 60, end_inclusive=True, observations_in_window=window) is False


def test_h1_one_missing_minute_plus_one_duplicate_minute_is_incomplete_despite_matching_count():
    # The exact count-only bug: 31 rows total (matches expected=31), but
    # minute index 5 is missing and minute index 10 is duplicated instead.
    start = kst(DAY, 9, 0)
    window = [obs(start + i * 60) for i in range(31) if i != 5]  # 30 rows, minute 5 missing
    window.append(obs(start + 10 * 60))  # duplicate of minute 10 -> back to 31 rows total
    assert len(window) == 31  # count alone would wrongly say COMPLETE
    assert validate_completeness(DataCompletenessPolicy(kind=DataCompletenessKind.CONTIGUOUS_INTERVAL, interval_seconds=60.0), window_start=start, window_end=start + 30 * 60, end_inclusive=True, observations_in_window=window) is False


def test_h1_one_timestamp_off_grid_is_incomplete_despite_matching_count():
    start = kst(DAY, 9, 0)
    window = [obs(start + i * 60) for i in range(31) if i != 5]  # 30 rows, minute 5 missing
    window.append(obs(start + 5 * 60 + 30))  # an off-grid bar at :05:30 instead of :05:00
    assert len(window) == 31
    assert validate_completeness(DataCompletenessPolicy(kind=DataCompletenessKind.CONTIGUOUS_INTERVAL, interval_seconds=60.0), window_start=start, window_end=start + 30 * 60, end_inclusive=True, observations_in_window=window) is False


def test_h1_completeness_still_uses_frozen_policy_fields_only():
    # require_all_expected_observations=False -- expected slots must all be
    # PRESENT (a subset check), extras beyond the grid are tolerated.
    start = kst(DAY, 9, 0)
    window = [obs(start + i * 60) for i in range(31)] + [obs(start + 31 * 60)]  # one extra bar past the window
    policy = DataCompletenessPolicy(kind=DataCompletenessKind.CONTIGUOUS_INTERVAL, interval_seconds=60.0, require_all_expected_observations=False)
    assert validate_completeness(policy, window_start=start, window_end=start + 30 * 60, end_inclusive=True, observations_in_window=window) is True


# =========================================================================
# H2 -- duplicate timestamp determinism (order independence)
# =========================================================================


def test_h2_equal_duplicate_observations_are_order_independent():
    ts = kst(DAY, 9, 30)
    a = obs(ts, bar_close=101.0)
    b = obs(ts, bar_close=101.0)  # identical -- harmless duplicate
    target = TargetResolution(origin_timestamp=ts, target_timestamp=ts)
    result_ab = resolve_observation(_obs_policy(), target=target, observations=(a, b))
    result_ba = resolve_observation(_obs_policy(), target=target, observations=(b, a))
    assert result_ab == result_ba == a


def test_h2_conflicting_duplicate_observations_raise_deterministically_regardless_of_order():
    ts = kst(DAY, 9, 30)
    a = obs(ts, bar_close=101.0)
    b = obs(ts, bar_close=109.0)  # CONFLICTING value at the same timestamp

    from libs.reporting.evaluation.canonical.forward.engine import _validate_and_deduplicate

    with pytest.raises(AmbiguousObservationError):
        _validate_and_deduplicate([a, b])
    with pytest.raises(AmbiguousObservationError):
        _validate_and_deduplicate([b, a])


def test_h2_never_uses_input_order_as_a_tie_break_end_to_end():
    origin_ts = kst(DAY, 9, 0)
    target_ts = kst(DAY, 9, 5)
    a = obs(target_ts, bar_close=201.0)
    b = obs(target_ts, bar_close=305.0)
    horizon = HorizonSpec(label="+5m", kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.SIGNAL, observation=_obs_policy(selection_mode=ObservationSelectionMode.EXACT, missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY), relative_seconds=300)
    policy = ForwardPolicy(legacy_program="fix1_h2_probe", horizons=(horizon,), gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS), reference_resolution=ReferenceResolutionPolicy(kind=ReferenceResolutionKind.EXTERNAL_EVENT_TIMESTAMP, price_resolution=chain(PriceCandidate.BAR_CLOSE), origin=EventOrigin.SIGNAL))
    ref = ResolvedReference.single(origin=EventOrigin.SIGNAL, timestamp=origin_ts, price=100.0)
    with pytest.raises(AmbiguousObservationError):
        evaluate_forward(policy=policy, resolved_reference=ref, observations=[a, b])
    with pytest.raises(AmbiguousObservationError):
        evaluate_forward(policy=policy, resolved_reference=ref, observations=[b, a])


# =========================================================================
# H3 -- require_positive_volume actually executed
# =========================================================================


def test_h3_positive_volume_resolves():
    target = TargetResolution(origin_timestamp=0, target_timestamp=0)
    policy = _obs_policy(require_positive_volume=True)
    result = resolve_observation(policy, target=target, observations=[obs(0, bar_close=100.0, volume=50.0)])
    assert result is not None


def test_h3_zero_volume_does_not_resolve():
    target = TargetResolution(origin_timestamp=0, target_timestamp=0)
    policy = _obs_policy(require_positive_volume=True)
    result = resolve_observation(policy, target=target, observations=[obs(0, bar_close=100.0, volume=0.0)])
    assert result is None


def test_h3_missing_volume_does_not_resolve():
    target = TargetResolution(origin_timestamp=0, target_timestamp=0)
    policy = _obs_policy(require_positive_volume=True)
    result = resolve_observation(policy, target=target, observations=[obs(0, bar_close=100.0)])
    assert result is None


def test_h3_require_positive_volume_skips_ineligible_and_keeps_searching_forward():
    # FIRST_AT_OR_AFTER must SKIP an ineligible (zero-volume) candidate and
    # find the next eligible one, never just fail outright.
    target = TargetResolution(origin_timestamp=0, target_timestamp=100)
    policy = _obs_policy(selection_mode=ObservationSelectionMode.FIRST_AT_OR_AFTER, missing_resolution=MissingResolutionPolicy.EXPIRE_AFTER_TOLERANCE, lookahead_seconds=120, require_positive_volume=True)
    observations = [obs(100, bar_close=100.0, volume=0.0), obs(160, bar_close=101.0, volume=10.0)]
    result = resolve_observation(policy, target=target, observations=observations)
    assert result is not None and result.timestamp == 160


def test_h3_generic_no_program_special_case():
    # Same primitive, no Q10-specific code path -- proven by using an
    # arbitrary, non-Q10 label/profile shape.
    target = TargetResolution(origin_timestamp=0, target_timestamp=0)
    policy = _obs_policy(require_positive_volume=True, require_positive_price=True)
    ref = ResolvedReference.single(origin=EventOrigin.CUSTOM, timestamp=0, price=100.0)
    ok = resolve_observation(policy, target=target, observations=[obs(0, bar_close=50.0, volume=10.0)], resolved_reference=ref)
    assert ok is not None
    bad_price = resolve_observation(policy, target=target, observations=[obs(0, bar_close=-1.0, volume=10.0)], resolved_reference=ref)
    assert bad_price is None


# =========================================================================
# H4 -- LAST_AVAILABLE lookback actually reachable
# =========================================================================


def test_h4_target_1530_obs_1525_lookback_600_resolves():
    target_ts = kst(DAY, 15, 30)
    target = TargetResolution(origin_timestamp=target_ts, target_timestamp=target_ts)
    policy = _obs_policy(selection_mode=ObservationSelectionMode.LAST_AVAILABLE, missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY, lookback_seconds=600, lookahead_seconds=60)
    observation = obs(kst(DAY, 15, 25), bar_close=100.0)
    result = resolve_observation(policy, target=target, observations=[observation])
    assert result is observation


def test_h4_obs_1519_is_outside_the_lookback_window():
    target_ts = kst(DAY, 15, 30)
    target = TargetResolution(origin_timestamp=target_ts, target_timestamp=target_ts)
    policy = _obs_policy(selection_mode=ObservationSelectionMode.LAST_AVAILABLE, missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY, lookback_seconds=600, lookahead_seconds=60)
    observation = obs(kst(DAY, 15, 19), bar_close=100.0)  # 660s before target -- outside 600s lookback
    result = resolve_observation(policy, target=target, observations=[observation])
    assert result is None


def test_h4_1525_and_1529_present_selects_1529():
    target_ts = kst(DAY, 15, 30)
    target = TargetResolution(origin_timestamp=target_ts, target_timestamp=target_ts)
    policy = _obs_policy(selection_mode=ObservationSelectionMode.LAST_AVAILABLE, missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY, lookback_seconds=600, lookahead_seconds=60)
    early = obs(kst(DAY, 15, 25), bar_close=100.0)
    late = obs(kst(DAY, 15, 29), bar_close=101.0)
    result = resolve_observation(policy, target=target, observations=[early, late])
    assert result is late


def test_h4_does_not_confuse_lookback_with_lookahead():
    # An observation AFTER target, within lookahead, must still be pickable
    # (proves the lookback fix did not accidentally disable lookahead).
    target_ts = kst(DAY, 15, 30)
    target = TargetResolution(origin_timestamp=target_ts, target_timestamp=target_ts)
    policy = _obs_policy(selection_mode=ObservationSelectionMode.LAST_AVAILABLE, missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY, lookback_seconds=600, lookahead_seconds=60)
    after = obs(kst(DAY, 15, 30, 45), bar_close=102.0)  # 45s after target, within 60s lookahead
    result = resolve_observation(policy, target=target, observations=[after])
    assert result is after
    too_late = obs(kst(DAY, 15, 32), bar_close=103.0)  # 120s after target -- beyond lookahead
    assert resolve_observation(policy, target=target, observations=[too_late]) is None


# =========================================================================
# H5 -- forward-session target lineage preserved
# =========================================================================


def test_h5_horizon_result_preserves_target_session_date():
    from libs.reporting.evaluation.canonical.forward.contracts import ForwardSessionResolverAuthority
    from libs.reporting.evaluation.canonical.forward.policy import ForwardSessionSpec
    from libs.reporting.evaluation.canonical.forward.engine import SessionContext

    horizon = HorizonSpec(
        label="d1", kind=HorizonKind.FORWARD_SESSION, origin=EventOrigin.CUSTOM,
        observation=_obs_policy(selection_mode=ObservationSelectionMode.LAST_AVAILABLE, missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY),
        excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.FORWARD_SESSION_BOUND, start_inclusive=True, end_inclusive=True, mfe_price_resolution=chain(PriceCandidate.BAR_HIGH)),
        forward_session=ForwardSessionSpec(resolver_authority=ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS, session_offset=1, required_available_sessions=1),
    )
    policy = ForwardPolicy(legacy_program="fix1_h5_probe", horizons=(horizon,), gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS), reference_resolution=ReferenceResolutionPolicy(kind=ReferenceResolutionKind.EXTERNAL_EVENT_TIMESTAMP, price_resolution=chain(PriceCandidate.FIXED_OBSERVED_PRICE), origin=EventOrigin.CUSTOM))
    ref = ResolvedReference.single(origin=EventOrigin.CUSTOM, timestamp=kst(DAY, 9, 0), price=100.0)
    sc = SessionContext(future_session_dates=("2026-09-15",), sessions_with_observations=frozenset({"2026-09-15"}))
    observation = obs(kst("2026-09-15", 10, 0), bar_close=110.0, bar_high=115.0)
    result = evaluate_forward(policy=policy, resolved_reference=ref, observations=[observation], session_context=sc)
    d1 = result.horizons[0]
    assert d1.target_session_date == "2026-09-15"
    assert d1.target_timestamp is None  # correctly a session, not a nominal epoch -- never collapsed together
    assert d1.observed_timestamp == observation.timestamp


def test_h5_insufficient_sessions_also_preserves_no_lineage_falsely():
    from libs.reporting.evaluation.canonical.forward.contracts import ForwardSessionResolverAuthority, MissingObservationStatus
    from libs.reporting.evaluation.canonical.forward.policy import ForwardSessionSpec
    from libs.reporting.evaluation.canonical.forward.engine import SessionContext

    horizon = HorizonSpec(
        label="d3", kind=HorizonKind.FORWARD_SESSION, origin=EventOrigin.CUSTOM,
        observation=_obs_policy(selection_mode=ObservationSelectionMode.LAST_AVAILABLE, missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY),
        forward_session=ForwardSessionSpec(resolver_authority=ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS, session_offset=3, required_available_sessions=3),
    )
    policy = ForwardPolicy(legacy_program="fix1_h5_probe_b", horizons=(horizon,), gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS), reference_resolution=ReferenceResolutionPolicy(kind=ReferenceResolutionKind.EXTERNAL_EVENT_TIMESTAMP, price_resolution=chain(PriceCandidate.FIXED_OBSERVED_PRICE), origin=EventOrigin.CUSTOM))
    ref = ResolvedReference.single(origin=EventOrigin.CUSTOM, timestamp=kst(DAY, 9, 0), price=100.0)
    sc = SessionContext(future_session_dates=("2026-09-15",), sessions_with_observations=frozenset({"2026-09-15"}))
    result = evaluate_forward(policy=policy, resolved_reference=ref, observations=[], session_context=sc)
    d3 = result.horizons[0]
    assert d3.missing_status is MissingObservationStatus.INSUFFICIENT_FUTURE_SESSIONS
    assert d3.target_session_date is None  # never a fake/guessed date when unresolved


# =========================================================================
# H6 -- reference provenance: two distinct fields, no invented precedence
# =========================================================================


def test_h6_policy_declared_and_resolved_reference_provenance_kept_separate():
    horizon = HorizonSpec(label="EOD", kind=HorizonKind.SESSION_CLOSE, origin=EventOrigin.FIXED_CLOCK, observation=_obs_policy(selection_mode=ObservationSelectionMode.LAST_AVAILABLE, missing_resolution=MissingResolutionPolicy.KEEP_PENDING, lookahead_seconds=None), fixed_clock=FixedClockSpec(clock_label="15:30"))
    policy = ForwardPolicy(
        legacy_program="fix1_h6_probe", horizons=(horizon,), gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=ReferenceResolutionPolicy(kind=ReferenceResolutionKind.PRE_RESOLVED_REFERENCE, price_resolution=chain(PriceCandidate.FIXED_OBSERVED_PRICE), provenance="FIRST_PULLBACK_ENTRY"),
    )
    ref = ResolvedReference(primary_origin=EventOrigin.FIXED_CLOCK, origins={EventOrigin.FIXED_CLOCK: ResolvedOrigin(timestamp=kst(DAY, 9, 0), price=100.0)}, provenance="episode_7f2a_actual_resolution_run")
    result = evaluate_forward(policy=policy, resolved_reference=ref, observations=[obs(kst(DAY, 15, 30), bar_close=110.0)])
    assert result.policy_declared_reference_provenance == "FIRST_PULLBACK_ENTRY"
    assert result.resolved_reference_provenance == "episode_7f2a_actual_resolution_run"
    # neither value silently overwrites or masks the other:
    assert result.policy_declared_reference_provenance != result.resolved_reference_provenance


def test_h6_empty_resolved_reference_provenance_is_not_replaced_by_policy_value():
    horizon = HorizonSpec(label="+5m", kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.SIGNAL, observation=_obs_policy(selection_mode=ObservationSelectionMode.FIRST_AT_OR_AFTER, missing_resolution=MissingResolutionPolicy.EXPIRE_AFTER_TOLERANCE, lookahead_seconds=90), relative_seconds=300)
    policy = ForwardPolicy(legacy_program="fix1_h6_probe_b", horizons=(horizon,), gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS), reference_resolution=ReferenceResolutionPolicy(kind=ReferenceResolutionKind.EXTERNAL_EVENT_TIMESTAMP, price_resolution=chain(PriceCandidate.BAR_CLOSE), origin=EventOrigin.SIGNAL))
    ref = ResolvedReference.single(origin=EventOrigin.SIGNAL, timestamp=kst(DAY, 9, 0), price=100.0)  # provenance="" (caller did not attach one)
    result = evaluate_forward(policy=policy, resolved_reference=ref, observations=[obs(kst(DAY, 9, 5), bar_close=101.0)])
    assert result.policy_declared_reference_provenance == ""  # EXTERNAL_EVENT_TIMESTAMP never requires one
    assert result.resolved_reference_provenance == ""  # stays empty -- never silently filled from the policy field
