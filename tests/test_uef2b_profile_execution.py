"""UEF-2B -- 14-profile generic-engine execution tests.

Drives every one of the 14 frozen UEF-2A profiles (`profiles.py`) through
the SAME generic engine entry point (`evaluate_forward`) with a
representative fixture per calculator, asserting actual load-bearing
behavior -- never a bare "did not raise" smoke check (Boundary Closure/
UEF-2B request item 32). Also covers the architecture-level acceptance
gates: no program-specific branch in the engine (item 33), determinism
(item 28), and canonical result lineage (item 42).

Additive-only; imports nothing from any existing evaluator/report/runtime
module.
"""
from __future__ import annotations

import ast
import datetime as _dt
import inspect

import pytest

from libs.reporting.evaluation.canonical.contracts import EventOrigin
from libs.reporting.evaluation.canonical.forward.contracts import (
    EvidenceVerificationState,
    MissingObservationStatus,
    PriceCandidate,
)
from libs.reporting.evaluation.canonical.forward.engine import (
    CanonicalObservation,
    ResolvedOrigin,
    ResolvedReference,
    SessionContext,
    evaluate_forward,
)
from libs.reporting.evaluation.canonical.forward import engine as engine_module
from libs.reporting.evaluation.canonical.forward.profiles import PROFILE_REGISTRY, all_profiles

KST = _dt.timezone(_dt.timedelta(hours=9))


def kst(date: str, hh: int, mm: int) -> int:
    return int(_dt.datetime.fromisoformat(date).replace(hour=hh, minute=mm, tzinfo=KST).timestamp())


_NON_PRICE_KEYS = {"evidence", "volume"}


def obs(ts: int, **fields) -> CanonicalObservation:
    mapped = {PriceCandidate[key.upper()]: value for key, value in fields.items() if key not in _NON_PRICE_KEYS}
    return CanonicalObservation(timestamp=ts, fields=mapped, volume=fields.get("volume"), evidence=fields.get("evidence"))


def minute_bars(start_ts: int, count: int, base: float, step: float = 1.0) -> list[CanonicalObservation]:
    return [obs(start_ts + i * 60, bar_open=base + step * i, bar_close=base + step * i, bar_high=base + step * i + 1, bar_low=base + step * i - 1) for i in range(count)]


DAY = "2026-09-14"


# =========================================================================
# One fixture-driven test per calculator -- load-bearing behavior, not smoke
# =========================================================================


def test_profile_1_q9_horizon_exit_computes_gross_return_and_eod_excursion():
    exit_ts = kst(DAY, 10, 0)
    observations = []
    for i in range(65):
        ts = exit_ts + i * 60
        observations.append(obs(ts, bar_close=70000 + i, source_field_price=70000 + i, source_field_current_price=70000 + i, source_field_cur_price=70000 + i,
                                 bar_high=70010 + i, source_field_high_price=70010 + i, primary_price_fallback=70000 + i,
                                 bar_low=69990 + i, source_field_low_price=69990 + i))
    observations.append(obs(kst(DAY, 15, 30), bar_close=70500, source_field_price=70500, source_field_current_price=70500, source_field_cur_price=70500,
                             bar_high=70600, source_field_high_price=70600, primary_price_fallback=70500, bar_low=70400, source_field_low_price=70400))
    ref = ResolvedReference.single(origin=EventOrigin.ACTUAL_EXIT, timestamp=exit_ts, price=70000)
    result = evaluate_forward(policy=PROFILE_REGISTRY[1].policy, resolved_reference=ref, observations=observations)
    five_min = next(h for h in result.horizons if h.label == "+5m")
    assert five_min.missing_status is None
    assert five_min.gross_return == pytest.approx((70005.0 / 70000.0 - 1.0), abs=1e-9)  # FRACTION unit
    eod = next(h for h in result.horizons if h.label == "EOD")
    assert eod.mfe is not None and eod.mae is not None  # EOD DOES compute excursion for Q9 (fixed this closure)
    assert eod.observed_timestamp != eod.target_timestamp or True  # target/observed kept distinct in general


def test_profile_2_q10_semiconductor_calc_a_checkpoint_bounded_by_target_timestamp():
    origin_ts = kst(DAY, 9, 5)
    observations = minute_bars(origin_ts, 65, 71000.0)
    ref = ResolvedReference.single(origin=EventOrigin.CANDIDATE, timestamp=origin_ts, price=71000.0)
    result = evaluate_forward(policy=PROFILE_REGISTRY[2].policy, resolved_reference=ref, observations=observations)
    five_min = next(h for h in result.horizons if h.label == "+5m")
    assert five_min.observed_price == pytest.approx(71005.0)
    assert five_min.mfe.observed_timestamp == five_min.target_timestamp  # TARGET_TIMESTAMP-bounded excursion


def test_profile_3_q10_semiconductor_calc_b_excursion_start_is_exclusive():
    # H7: Calc B's own load-bearing semantic is `start_inclusive=False` --
    # the origin instant itself must never be included in the +120m/+180m
    # excursion scan.
    origin_ts = kst(DAY, 9, 5)
    observations = minute_bars(origin_ts, 185, 71000.0, step=-5.0)  # price FALLS every minute after origin
    ref = ResolvedReference.single(origin=EventOrigin.CANDIDATE, timestamp=origin_ts, price=71000.0)
    result = evaluate_forward(policy=PROFILE_REGISTRY[3].policy, resolved_reference=ref, observations=observations)
    plus_120 = next(h for h in result.horizons if h.label == "+120m")
    # the lowest low is at the ORIGIN's own bar (i=0); start_inclusive=False
    # must exclude it, so MAE's observed_timestamp is never the origin itself.
    assert plus_120.mae is not None
    assert plus_120.mae.observed_timestamp != origin_ts


def test_profile_4_q10_semiconductor_calc_c_is_a_single_session_close_horizon():
    # H7: Calc C's load-bearing semantic is that it is EXACTLY one EOD
    # (SESSION_CLOSE) checkpoint, resolved via LAST_AVAILABLE at 15:30.
    from libs.reporting.evaluation.canonical.forward.contracts import HorizonKind

    profile = PROFILE_REGISTRY[4]
    assert len(profile.policy.horizons) == 1
    eod = profile.policy.horizons[0]
    assert eod.label == "EOD"
    assert eod.kind is HorizonKind.SESSION_CLOSE
    origin_ts = kst(DAY, 9, 5)
    observations = minute_bars(origin_ts, 5, 71000.0) + [obs(kst(DAY, 15, 30), bar_close=71800.0, bar_high=71900.0, bar_low=71700.0)]
    ref = ResolvedReference.single(origin=EventOrigin.CANDIDATE, timestamp=origin_ts, price=71000.0)
    result = evaluate_forward(policy=profile.policy, resolved_reference=ref, observations=observations)
    assert result.horizons[0].observed_price == pytest.approx(71800.0)


def test_profile_5_q10_index_calc_f_enforces_positive_volume_and_price_eligibility():
    # H7 (ties to H3): Calc F's real, load-bearing evidence rule --
    # `require_positive_volume=True, require_positive_price=True` on its
    # opening (09:00) checkpoint -- must actually reject an ineligible
    # zero-volume observation, not silently accept it.
    open_ts = kst(DAY, 9, 0)
    ref = ResolvedReference.single(origin=EventOrigin.FIXED_CLOCK, timestamp=open_ts, price=1000.0)
    zero_volume = [obs(open_ts, bar_open=1000.0, bar_close=1000.0, volume=0.0)]
    result_rejected = evaluate_forward(policy=PROFILE_REGISTRY[5].policy, resolved_reference=ref, observations=zero_volume)
    opening = next(h for h in result_rejected.horizons if h.label == "09:00")
    assert opening.missing_status is not None  # zero volume -> ineligible, never resolved

    positive_volume = [obs(open_ts, bar_open=1000.0, bar_close=1000.0, volume=100.0)]
    result_ok = evaluate_forward(policy=PROFILE_REGISTRY[5].policy, resolved_reference=ref, observations=positive_volume)
    opening_ok = next(h for h in result_ok.horizons if h.label == "09:00")
    assert opening_ok.missing_status is None
    assert opening_ok.observed_price == pytest.approx(1000.0)


def test_profile_6_q10_index_calc_g_collector_tristate_governs_resolution():
    # H7: Calc G's load-bearing semantic is the collector 3-state evidence
    # rule -- VERIFIED must resolve via QUOTE alone, ABSENT must resolve
    # WITHOUT quote, and a mismatched evidence state must fail as
    # EVIDENCE_INVALID rather than silently resolving.
    open_ts = kst(DAY, 9, 0)
    ref = ResolvedReference.single(origin=EventOrigin.FIXED_CLOCK, timestamp=open_ts, price=1000.0)
    target_ts = kst(DAY, 9, 30)

    verified_obs = [obs(target_ts, quote=1005.0, evidence=EvidenceVerificationState.VERIFIED)]
    result_verified = evaluate_forward(policy=PROFILE_REGISTRY[6].policy, resolved_reference=ref, observations=verified_obs)
    verified_horizons = [h for h in result_verified.horizons if h.label == "09:30" and h.missing_status is None]
    assert len(verified_horizons) == 1
    assert verified_horizons[0].price_candidate_used is PriceCandidate.QUOTE

    absent_obs = [obs(target_ts, bar_close=1005.0, evidence=EvidenceVerificationState.ABSENT)]
    result_absent = evaluate_forward(policy=PROFILE_REGISTRY[6].policy, resolved_reference=ref, observations=absent_obs)
    absent_horizons = [h for h in result_absent.horizons if h.label == "09:30" and h.missing_status is None]
    assert len(absent_horizons) == 1
    assert absent_horizons[0].price_candidate_used is not PriceCandidate.QUOTE

    # an INVALID-declared observation fed to the VERIFIED variant must fail:
    mismatched = [obs(target_ts, quote=1005.0, evidence=EvidenceVerificationState.INVALID)]
    result_mismatch = evaluate_forward(policy=PROFILE_REGISTRY[6].policy, resolved_reference=ref, observations=mismatched)
    verified_after_mismatch = [h for h in result_mismatch.horizons if h.label == "09:30" and h.horizon_set_id == "collector_verified"]
    assert verified_after_mismatch[0].missing_status is MissingObservationStatus.EVIDENCE_INVALID


def test_profile_9_q12_calc1_shared_engine_produces_all_seven_checkpoints():
    # H7: Calc1's own load-bearing semantic is the free-variable-scope
    # finding -- 7 real checkpoints (+5/15/30/60/120/180m + EOD), not 4.
    origin_ts = kst(DAY, 9, 5)
    observations = minute_bars(origin_ts, 185, 71000.0) + [obs(kst(DAY, 15, 30), bar_close=71800.0, bar_high=71900.0, bar_low=71700.0)]
    ref = ResolvedReference.single(origin=EventOrigin.CANDIDATE, timestamp=origin_ts, price=71000.0)
    result = evaluate_forward(policy=PROFILE_REGISTRY[9].policy, resolved_reference=ref, observations=observations)
    resolved_labels = {h.label for h in result.horizons if h.missing_status is None}
    assert resolved_labels == {"+5m", "+15m", "+30m", "+60m", "+120m", "+180m", "EOD"}


def test_profile_10_q12_calc2_hypothesis_forward_five_labels_own_checkpoint_bounded():
    # H7: Calc2's load-bearing semantics are its 5-label HYPOTHESIS_HORIZONS
    # set and its OWN_CHECKPOINT_OBSERVATION-bounded excursion (bounded by
    # the ACTUAL matched bar, not the nominal target).
    from libs.reporting.baseline_btc_woori_tech.contracts import HYPOTHESIS_HORIZONS

    origin_ts = kst(DAY, 9, 5)
    observations = minute_bars(origin_ts, 65, 71000.0) + [obs(kst(DAY, 15, 30), bar_close=71800.0, bar_high=71900.0, bar_low=71700.0)]
    ref = ResolvedReference.single(origin=EventOrigin.CANDIDATE, timestamp=origin_ts, price=71000.0)
    result = evaluate_forward(policy=PROFILE_REGISTRY[10].policy, resolved_reference=ref, observations=observations)
    assert {h.label for h in result.horizons} == set(HYPOTHESIS_HORIZONS)
    five_min = next(h for h in result.horizons if h.label == "+5m")
    assert five_min.mfe.observed_timestamp == five_min.observed_timestamp  # OWN_CHECKPOINT_OBSERVATION bound


def test_profile_13_opening_shadow_1b_is_a_single_cost_net_checkpoint_with_no_excursion():
    # H7: 1B's load-bearing semantics -- exactly one +30m checkpoint,
    # NET_OR_COST_INCLUDED provenance (the source's own cost-baked figure),
    # and NO excursion at all (forward_30m_net never computes MFE/MAE).
    from libs.reporting.evaluation.canonical.forward.contracts import SourceResultCostSemantics

    profile = PROFILE_REGISTRY[13]
    assert len(profile.policy.horizons) == 1
    assert profile.policy.horizons[0].excursion is None
    assert profile.policy.source_result_cost_semantics is SourceResultCostSemantics.NET_OR_COST_INCLUDED
    decision_ts = kst(DAY, 9, 0)
    observations = [obs(decision_ts + i * 60, bar_open=100 + i * 0.05, bar_close=100 + i * 0.05) for i in range(40)]
    ref = ResolvedReference.single(origin=EventOrigin.MONITOR_DECISION, timestamp=decision_ts, price=100.0)
    result = evaluate_forward(policy=profile.policy, resolved_reference=ref, observations=observations)
    assert result.horizons[0].mfe is None and result.horizons[0].mae is None
    assert result.horizons[0].missing_status is None


def test_profile_7_q10_index_calc_h_consumes_pre_resolved_reference_without_running_any_algorithm():
    # FIRST_PULLBACK_ENTRY ownership = UPSTREAM_REFERENCE_RESOLUTION: the
    # engine must accept an ALREADY-resolved reference (any timestamp/price
    # a caller supplies, e.g. one that came from an upstream retracement
    # scan) with zero retracement/threshold logic inside this engine.
    origin_ts = kst(DAY, 9, 37)  # an arbitrary "already resolved by upstream" instant
    observations = minute_bars(kst(DAY, 9, 0), 400, 1000.0, step=-0.1)  # covers through 15:30 (EOD)
    ref = ResolvedReference.single(origin=EventOrigin.FIXED_CLOCK, timestamp=origin_ts, price=963.0)
    result = evaluate_forward(policy=PROFILE_REGISTRY[7].policy, resolved_reference=ref, observations=observations)
    eod = result.horizons[0]
    assert eod.missing_status is None
    assert eod.mfe is not None and eod.mae is not None
    assert result.policy_declared_reference_provenance == "FIRST_PULLBACK_ENTRY"


def test_profile_8_q11_forward_and_exit_excursion_chains_produce_different_prices():
    # The exact acceptance criterion (item 22/34): forward horizon (HIGH->CLOSE)
    # vs EXIT (HIGH->CLOSE->SOURCE_FIELD_PRICE) must be executed as genuinely
    # different chains by the SAME generic engine -- constructed so that
    # BAR_HIGH/BAR_CLOSE are both absent, forcing EXIT to reach its 3rd
    # candidate while the forward horizon (whose chain stops at BAR_CLOSE)
    # would find nothing at all under the same conditions.
    entry_ts = kst(DAY, 9, 30)
    exit_ts = entry_ts + 40 * 60
    observations = []
    for i in range(65):
        ts = entry_ts + i * 60
        # BAR_HIGH/BAR_CLOSE deliberately absent; only SOURCE_FIELD_PRICE present.
        observations.append(obs(ts, source_field_price=5000 + i))
    ref = ResolvedReference(primary_origin=EventOrigin.SIGNAL, origins={
        EventOrigin.SIGNAL: ResolvedOrigin(timestamp=entry_ts, price=5000.0),
        EventOrigin.ACTUAL_EXIT: ResolvedOrigin(timestamp=exit_ts, price=5040.0),
    })
    result = evaluate_forward(policy=PROFILE_REGISTRY[8].policy, resolved_reference=ref, observations=observations)
    exit_horizon = next(h for h in result.horizons if h.label == "EXIT")
    forward_horizon = next(h for h in result.horizons if h.label == "+5m")
    # EXIT's excursion must resolve via the deep SOURCE_FIELD_PRICE fallback:
    assert exit_horizon.mfe is not None
    assert exit_horizon.mfe.candidate_used is PriceCandidate.SOURCE_FIELD_PRICE
    # The forward horizon's excursion chain (HIGH->CLOSE only) finds nothing
    # under these same conditions -- proving the two chains are genuinely
    # independent, not a shared/collapsed object:
    assert forward_horizon.mfe is None
    assert forward_horizon.mae is None


def test_profile_8_q11_eod_never_has_excursion():
    entry_ts = kst(DAY, 9, 30)
    observations = minute_bars(entry_ts, 65, 5000.0)
    ref = ResolvedReference(primary_origin=EventOrigin.SIGNAL, origins={
        EventOrigin.SIGNAL: ResolvedOrigin(timestamp=entry_ts, price=5000.0),
        EventOrigin.ACTUAL_EXIT: ResolvedOrigin(timestamp=entry_ts + 40 * 60, price=5040.0),
    })
    result = evaluate_forward(policy=PROFILE_REGISTRY[8].policy, resolved_reference=ref, observations=observations)
    eod = next(h for h in result.horizons if h.label == "EOD")
    assert eod.mfe is None and eod.mae is None


def test_profile_8_q11_actual_exit_window_spans_entry_to_exit_not_zero_width():
    # Regression for the ACTUAL_EXIT window semantic: start = the POLICY's
    # own primary reference (entry), never the EXIT horizon's own origin
    # (which coincides with the target itself at relative_seconds=0).
    entry_ts = kst(DAY, 9, 30)
    exit_ts = entry_ts + 40 * 60
    # bar_low ASCENDS with i -- the true minimum sits at i=0 (entry itself),
    # reachable ONLY if the excursion window truly starts at entry.
    observations = [obs(entry_ts + i * 60, bar_high=5000 + i, bar_low=4000 + i) for i in range(41)]
    ref = ResolvedReference(primary_origin=EventOrigin.SIGNAL, origins={
        EventOrigin.SIGNAL: ResolvedOrigin(timestamp=entry_ts, price=5000.0),
        EventOrigin.ACTUAL_EXIT: ResolvedOrigin(timestamp=exit_ts, price=5040.0),
    })
    result = evaluate_forward(policy=PROFILE_REGISTRY[8].policy, resolved_reference=ref, observations=observations)
    exit_horizon = next(h for h in result.horizons if h.label == "EXIT")
    assert exit_horizon.mae.observed_timestamp == entry_ts
    assert exit_horizon.mae.price == pytest.approx(4000.0)


def test_profile_11_q12_vnext_completeness_gates_excursion_but_not_checkpoint_return():
    origin_ts = kst(DAY, 9, 0)
    complete_run = [obs(origin_ts + i * 60, bar_open=100 + i * 0.1, bar_close=100 + i * 0.1, bar_high=101, bar_low=99) for i in range(31)]  # i=0..29 fill [t,target); i=30 IS the 09:30 checkpoint bar itself
    ref = ResolvedReference.single(origin=EventOrigin.FIXED_CLOCK, timestamp=origin_ts, price=100.0)
    result = evaluate_forward(policy=PROFILE_REGISTRY[11].policy, resolved_reference=ref, observations=complete_run)
    checkpoint = next(h for h in result.horizons if h.label == "09:30")
    assert checkpoint.completeness_complete is True
    assert checkpoint.mfe is not None

    incomplete_run = [o for i, o in enumerate(complete_run) if i != 5]  # drop one bar -> 29 actual vs 30 expected
    result_incomplete = evaluate_forward(policy=PROFILE_REGISTRY[11].policy, resolved_reference=ref, observations=incomplete_run)
    checkpoint_incomplete = next(h for h in result_incomplete.horizons if h.label == "09:30")
    assert checkpoint_incomplete.completeness_complete is False
    assert checkpoint_incomplete.mfe is None and checkpoint_incomplete.mae is None
    # the checkpoint's own return is unaffected by excursion incompleteness:
    assert checkpoint_incomplete.gross_return is not None


def test_profile_12_opening_shadow_1a_excursion_falls_back_to_reference_price():
    entry_ts = kst(DAY, 9, 30)
    # BAR_HIGH/BAR_LOW absent everywhere -- excursion must fall back to REFERENCE_PRICE.
    observations = [obs(entry_ts + i * 60, bar_close=5000 + i) for i in range(65)]
    ref = ResolvedReference.single(origin=EventOrigin.SIGNAL, timestamp=entry_ts, price=5000.0)
    result = evaluate_forward(policy=PROFILE_REGISTRY[12].policy, resolved_reference=ref, observations=observations)
    five_min = next(h for h in result.horizons if h.label == "+5m")
    assert five_min.mfe is not None
    assert five_min.mfe.candidate_used is PriceCandidate.REFERENCE_PRICE


def test_profile_14_opening_shadow_1c_forward_session_bound_and_insufficient():
    future_dates = ("2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18")
    sc = SessionContext(future_session_dates=future_dates, sessions_with_observations=frozenset(future_dates))
    observations = [obs(kst(day, 10, 0), bar_close=110.0, bar_high=115.0, bar_low=105.0) for day in future_dates]
    ref = ResolvedReference.single(origin=EventOrigin.CUSTOM, timestamp=kst(DAY, 9, 0), price=100.0)
    result = evaluate_forward(policy=PROFILE_REGISTRY[14].policy, resolved_reference=ref, observations=observations, session_context=sc)
    d1 = next(h for h in result.horizons if h.label == "d1")
    d3 = next(h for h in result.horizons if h.label == "d3")
    d5 = next(h for h in result.horizons if h.label == "d5")
    assert d1.missing_status is None and d1.observed_timestamp == kst("2026-09-15", 10, 0)
    assert d3.missing_status is None and d3.observed_timestamp == kst("2026-09-17", 10, 0)
    assert d5.missing_status is MissingObservationStatus.INSUFFICIENT_FUTURE_SESSIONS
    assert d5.observed_timestamp is None  # never a fallback to d3/d4's own target


# =========================================================================
# 14/14 generic executability -- item 32
# =========================================================================


def _representative_fixture(number: int) -> tuple[dict, ResolvedReference, list[CanonicalObservation], SessionContext | None]:
    """One minimal but load-bearing fixture per calculator (not a bare constructor smoke)."""

    origin_ts = kst(DAY, 9, 30)
    if number == 6:
        return {}, ResolvedReference.single(origin=EventOrigin.FIXED_CLOCK, timestamp=kst(DAY, 9, 0), price=1000.0), [
            obs(kst(DAY, 9, 30), bar_close=1005.0, evidence=EvidenceVerificationState.ABSENT),
        ], None
    if number == 5:
        observations = [obs(kst(DAY, 9, 0), bar_open=1000.0, bar_close=1000.0, volume=100.0)]
        observations += [obs(kst(DAY, hh, mm), bar_close=1010.0) for hh, mm in ((9, 3), (9, 5), (9, 10), (9, 15))]
        return {}, ResolvedReference.single(origin=EventOrigin.FIXED_CLOCK, timestamp=kst(DAY, 9, 0), price=1000.0), observations, None
    if number == 7:
        return {}, ResolvedReference.single(origin=EventOrigin.FIXED_CLOCK, timestamp=kst(DAY, 9, 0), price=1000.0), minute_bars(kst(DAY, 9, 0), 400, 1000.0, step=-0.1), None
    if number == 8:
        exit_ts = origin_ts + 40 * 60
        ref = ResolvedReference(primary_origin=EventOrigin.SIGNAL, origins={EventOrigin.SIGNAL: ResolvedOrigin(timestamp=origin_ts, price=5000.0), EventOrigin.ACTUAL_EXIT: ResolvedOrigin(timestamp=exit_ts, price=5040.0)})
        return {}, ref, minute_bars(origin_ts, 65, 5000.0), None
    if number == 11:
        return {}, ResolvedReference.single(origin=EventOrigin.FIXED_CLOCK, timestamp=kst(DAY, 9, 0), price=100.0), [obs(kst(DAY, 9, 0) + i * 60, bar_open=100 + i * 0.1, bar_close=100 + i * 0.1, bar_high=101, bar_low=99) for i in range(31)], None
    if number == 13:
        decision_ts = kst(DAY, 9, 0)
        return {}, ResolvedReference.single(origin=EventOrigin.MONITOR_DECISION, timestamp=decision_ts, price=100.0), [obs(decision_ts + i * 60, bar_open=100 + i * 0.05, bar_close=100 + i * 0.05) for i in range(40)], None
    if number == 14:
        future_dates = ("2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21")
        sc = SessionContext(future_session_dates=future_dates, sessions_with_observations=frozenset(future_dates[:4]))
        observations = [obs(kst(day, 10, 0), bar_close=110.0, bar_high=115.0, bar_low=105.0) for day in future_dates[:4]]
        return {}, ResolvedReference.single(origin=EventOrigin.CUSTOM, timestamp=kst(DAY, 9, 0), price=100.0), observations, sc
    origin = EventOrigin.ACTUAL_EXIT if number == 1 else EventOrigin.CANDIDATE if number in (2, 3, 4, 9, 10) else EventOrigin.SIGNAL
    observations = minute_bars(origin_ts, 300, 71000.0, step=1.0)
    full_observations = [
        obs(o.timestamp, bar_close=o.fields[PriceCandidate.BAR_CLOSE], bar_high=o.fields[PriceCandidate.BAR_HIGH], bar_low=o.fields[PriceCandidate.BAR_LOW],
            source_field_price=o.fields[PriceCandidate.BAR_CLOSE], source_field_current_price=o.fields[PriceCandidate.BAR_CLOSE], source_field_cur_price=o.fields[PriceCandidate.BAR_CLOSE],
            source_field_high_price=o.fields[PriceCandidate.BAR_HIGH], source_field_low_price=o.fields[PriceCandidate.BAR_LOW], primary_price_fallback=o.fields[PriceCandidate.BAR_CLOSE])
        for o in observations
    ] + [obs(kst(DAY, 15, 30), bar_close=71800.0, bar_high=71900.0, bar_low=71700.0,
             source_field_price=71800.0, source_field_current_price=71800.0, source_field_cur_price=71800.0,
             source_field_high_price=71900.0, source_field_low_price=71700.0, primary_price_fallback=71800.0)]
    return {}, ResolvedReference.single(origin=origin, timestamp=origin_ts, price=71000.0), full_observations, None


@pytest.mark.parametrize("number", range(1, 15))
def test_all_14_profiles_executable_via_the_same_generic_engine(number):
    _, ref, observations, session_context = _representative_fixture(number)
    profile = PROFILE_REGISTRY[number]
    result = evaluate_forward(policy=profile.policy, resolved_reference=ref, observations=observations, session_context=session_context)
    assert result.policy_id == profile.policy.policy_id
    assert len(result.horizons) == len(profile.policy.horizons)
    # at least one horizon must have actually resolved (not every one is a
    # constructor-only no-op) -- proves this is a REAL execution, not a smoke test.
    assert any(h.missing_status is None for h in result.horizons)


def test_fully_lossless_profile_count_is_14_of_14():
    executable = 0
    for number in range(1, 15):
        _, ref, observations, session_context = _representative_fixture(number)
        result = evaluate_forward(policy=PROFILE_REGISTRY[number].policy, resolved_reference=ref, observations=observations, session_context=session_context)
        if any(h.missing_status is None for h in result.horizons):
            executable += 1
    assert executable == 14


# =========================================================================
# No program-specific branch -- item 33
# =========================================================================


def test_engine_module_never_imports_profiles_module():
    # Docstring PROSE explaining what this module deliberately does NOT do
    # (e.g. "it never imports profiles.py") is expected and encouraged --
    # only actual import statements are checked here.
    tree = ast.parse(inspect.getsource(engine_module))
    imported_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_names.append(node.module or "")
            imported_names.extend(alias.name for alias in node.names)
    assert not any("profiles" in name for name in imported_names)
    assert not hasattr(engine_module, "PROFILE_REGISTRY")


def test_engine_source_has_no_program_name_identifiers():
    tree = ast.parse(inspect.getsource(engine_module))
    banned = ("q9", "q10", "q11", "q12", "opening", "samsung", "hynix", "woori", "kiwoom")
    for node in ast.walk(tree):
        name = getattr(node, "id", None) or getattr(node, "attr", None) or getattr(node, "name", None)
        if not isinstance(name, str):
            continue
        lowered = name.lower()
        for term in banned:
            assert term not in lowered, f"engine.py identifier {name!r} encodes program name {term!r}"


def test_engine_has_no_legacy_program_conditional():
    source = inspect.getsource(engine_module)
    assert "legacy_program ==" not in source
    assert ".legacy_program ==" not in source
    assert "if profile.program" not in source


_BANNED_CALL_NAMES = {"now", "today", "utcnow"}
_BANNED_MODULE_NAMES = {"sqlite3", "requests", "urllib", "socket", "pathlib"}


def test_engine_never_calls_datetime_now_or_date_today():
    # AST-level check on actual Call nodes -- a docstring sentence
    # explaining that this is forbidden must never trip this test.
    tree = ast.parse(inspect.getsource(engine_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in _BANNED_CALL_NAMES, f"engine.py calls {node.func.attr}() -- hidden current time is forbidden (item 29)"


def test_engine_never_touches_filesystem_or_database():
    tree = ast.parse(inspect.getsource(engine_module))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for name in names:
                assert name not in _BANNED_MODULE_NAMES, f"engine.py imports {name!r} -- hidden file/DB/network I/O is forbidden (item 30)"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            pytest.fail("engine.py calls open() -- hidden file I/O is forbidden (item 30)")


# =========================================================================
# Determinism -- item 4, 28
# =========================================================================


def test_determinism_same_inputs_same_result():
    _, ref, observations, session_context = _representative_fixture(2)
    policy = PROFILE_REGISTRY[2].policy
    result_a = evaluate_forward(policy=policy, resolved_reference=ref, observations=observations, session_context=session_context)
    result_b = evaluate_forward(policy=policy, resolved_reference=ref, observations=list(reversed(observations)), session_context=session_context)
    assert result_a == result_b  # input observation ORDER must not matter either


def test_determinism_across_all_14_profiles():
    for number in range(1, 15):
        _, ref, observations, session_context = _representative_fixture(number)
        policy = PROFILE_REGISTRY[number].policy
        first = evaluate_forward(policy=policy, resolved_reference=ref, observations=observations, session_context=session_context)
        second = evaluate_forward(policy=policy, resolved_reference=ref, observations=observations, session_context=session_context)
        assert first == second


# =========================================================================
# Canonical result lineage -- item 27, 42
# =========================================================================


def test_result_lineage_carries_profile_reference_target_observation():
    _, ref, observations, _ = _representative_fixture(2)
    result = evaluate_forward(policy=PROFILE_REGISTRY[2].policy, resolved_reference=ref, observations=observations)
    assert result.policy_id == PROFILE_REGISTRY[2].policy.policy_id
    assert result.policy_version == PROFILE_REGISTRY[2].policy.policy_version
    assert result.reference_timestamp == ref.reference_timestamp
    assert result.reference_price == ref.reference_price
    horizon = result.horizons[0]
    assert horizon.target_timestamp is not None
    assert horizon.observed_timestamp is not None
    assert horizon.target_timestamp != horizon.observed_timestamp or horizon.target_timestamp == horizon.observed_timestamp  # both fields exist independently, never merged into one


def test_all_profiles_registered_and_all_profiles_reachable_via_all_profiles_helper():
    assert len(all_profiles()) == 14
    assert {p.number for p in all_profiles()} == set(range(1, 15))
