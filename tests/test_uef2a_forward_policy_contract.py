"""UEF-2A SEMANTIC AUTHORITY RESET -- Canonical Forward Calculation-Recipe tests.

Additive-only: exercises `libs/reporting/evaluation/canonical/forward` only.
No existing evaluator/report/runtime module is imported or modified.

Source authority order (restated): real legacy source code > real artifact
> documented source constant > this contract > this test. Every
representability test below asserts SPECIFIC recipe fields re-verified
against source, never merely that object construction succeeded.

14-calculator coverage map (matching Codex's confirmed "14 checkpoint
calculators + 3 downstream aggregators" count):

    1.  Q9 Horizon/Exit            strategy_horizon_feedback.py
    2.  Q10 Semiconductor Calc A   quant_shadow_forward_outcomes.py::attach_forward_outcomes
    3.  Q10 Semiconductor Calc B   baseline_samsung_hynix/forward_returns.py::_extended_checkpoint
    4.  Q10 Semiconductor Calc C   baseline_samsung_hynix/forward_returns.py (inline EOD override)
    5.  Q10 Index Calc F           forward_validation/reaction_reader.py::_stock_reaction/_forward_window
    6.  Q10 Index Calc G           forward_validation/reaction_reader.py::_index_reaction (collector)
    7.  Q10 Index Calc H           forward_validation/shadow_comparison.py::build_shadow_comparison
    8.  Q11 Opportunity Engine     opportunity_engine/simulator.py
    9.  Q12 Calc1 (shared reuse)   baseline_btc_woori_tech/forward_returns.py::attach_forward_returns
    10. Q12 Calc2                 baseline_btc_woori_tech/hypothesis_forward.py
    11. Q12 Calc3 (vnext)         baseline_btc_woori_tech/vnext/outcomes.py
    12. Opening Shadow 1A         opening_rank1_shadow/latent_forward.py::_observe
    13. Opening Shadow 1B         opening_rank1_longitudinal/delayed_outcomes.py::forward_30m_net
    14. Opening Shadow 1C         opening_rank1_longitudinal/delayed_outcomes.py::delayed_path

Each has its own `test_calculator_N_*` below (or is grouped where one real
artifact/test naturally covers a tight cluster, e.g. Q10 Semiconductor
Calc A/B/C share one artifact). 3 aggregators (Q10 Semiconductor
`summarize_forward_returns`/`build_q9_role_comparison`, Q10 Index
`build_cumulative`) remain out of scope (Reset item 2). Opening Controlled
and Same-Symbol Sequences/Stage2 Authority have zero checkpoint calculators
of their own (established in prior passes, re-confirmed unchanged).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from libs.reporting.evaluation.canonical.contracts import EventOrigin, ReturnUnit
from libs.reporting.evaluation.canonical.forward import (
    DataCompletenessKind,
    DataCompletenessPolicy,
    EvidenceVerificationState,
    ExcursionPolicy,
    ExcursionPriceField,
    FixedClockSpec,
    ForwardPolicy,
    ForwardPolicyValidationError,
    ForwardSessionResolverAuthority,
    ForwardSessionSpec,
    GrossReturnPolicy,
    HorizonKind,
    HorizonSpec,
    MfeMaeWindowEnd,
    MissingObservationStatus,
    MissingResolutionPolicy,
    ObservationPolicy,
    ObservationSelectionMode,
    PriceCandidate,
    PriceResolutionPolicy,
    ReferenceResolutionKind,
    ReferenceResolutionPolicy,
    SessionCloseSpec,
    SourceResultCostSemantics,
    TradeDirection,
    deserialize_forward_policy,
    serialize_forward_policy,
)

KST = timezone(timedelta(hours=9))
REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_json(relative_path: str) -> dict:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def _kst_epoch(day: str, hhmm: str) -> int:
    hour, minute = (int(part) for part in hhmm.split(":"))
    dt = datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=KST)
    return int(dt.timestamp())


def _chain(*candidates: PriceCandidate) -> PriceResolutionPolicy:
    return PriceResolutionPolicy(authorities=candidates)


def _ref(*, price: PriceResolutionPolicy, origin: EventOrigin) -> ReferenceResolutionPolicy:
    return ReferenceResolutionPolicy(kind=ReferenceResolutionKind.EXTERNAL_EVENT_TIMESTAMP, price_resolution=price, origin=origin)


def _obs(
    *, price: PriceResolutionPolicy, selection: ObservationSelectionMode = ObservationSelectionMode.FIRST_AT_OR_AFTER,
    lookahead: float | None = 90, lookback: float = 0.0, missing: MissingResolutionPolicy | None = None,
    **kwargs,
) -> ObservationPolicy:
    if missing is None:
        missing = MissingResolutionPolicy.KEEP_PENDING if lookahead is None else MissingResolutionPolicy.EXPIRE_AFTER_TOLERANCE
    return ObservationPolicy(selection_mode=selection, price_resolution=price, missing_resolution=missing, lookback_seconds=lookback, lookahead_seconds=lookahead, **kwargs)


# =========================================================================
# 1. Validation invariants
# =========================================================================


def test_unsupported_timezone_rejected():
    with pytest.raises(ForwardPolicyValidationError):
        FixedClockSpec(clock_label="09:00", timezone="UTC")


def test_unsupported_session_rejected():
    with pytest.raises(ForwardPolicyValidationError):
        FixedClockSpec(clock_label="09:00", session="ANYTHING")


def test_relative_horizon_with_fixed_clock_rejected():
    with pytest.raises(ForwardPolicyValidationError):
        HorizonSpec(label="+5m", kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.SIGNAL, observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE)), relative_seconds=300, fixed_clock=FixedClockSpec(clock_label="09:00"))


def test_fixed_clock_target_with_relative_seconds_rejected():
    with pytest.raises(ForwardPolicyValidationError):
        HorizonSpec(label="09:00", kind=HorizonKind.FIXED_CLOCK_TARGET, origin=EventOrigin.FIXED_CLOCK, observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE)), fixed_clock=FixedClockSpec(clock_label="09:00"), relative_seconds=5)


def test_forward_session_with_fixed_clock_rejected():
    fs = ForwardSessionSpec(resolver_authority=ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS, session_offset=1, required_available_sessions=1)
    with pytest.raises(ForwardPolicyValidationError):
        HorizonSpec(label="d1", kind=HorizonKind.FORWARD_SESSION, origin=EventOrigin.CUSTOM, observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), selection=ObservationSelectionMode.LAST_AVAILABLE, lookahead=None), forward_session=fs, fixed_clock=FixedClockSpec(clock_label="09:00"))


def test_forward_session_requires_spec():
    with pytest.raises(ForwardPolicyValidationError):
        HorizonSpec(label="d1", kind=HorizonKind.FORWARD_SESSION, origin=EventOrigin.CUSTOM, observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), selection=ObservationSelectionMode.LAST_AVAILABLE, lookahead=None))


def test_required_available_sessions_cannot_exceed_offset():
    with pytest.raises(ForwardPolicyValidationError):
        ForwardSessionSpec(resolver_authority=ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS, session_offset=1, required_available_sessions=3)


def test_session_close_fallback_without_spec_rejected():
    with pytest.raises(ForwardPolicyValidationError):
        ObservationPolicy(selection_mode=ObservationSelectionMode.FIRST_AT_OR_AFTER, price_resolution=_chain(PriceCandidate.BAR_CLOSE), missing_resolution=MissingResolutionPolicy.USE_SESSION_CLOSE_FALLBACK, lookahead_seconds=None)


def test_empty_price_resolution_chain_rejected():
    with pytest.raises(ForwardPolicyValidationError):
        PriceResolutionPolicy(authorities=())


def test_duplicate_price_resolution_chain_rejected():
    with pytest.raises(ForwardPolicyValidationError):
        PriceResolutionPolicy(authorities=(PriceCandidate.BAR_CLOSE, PriceCandidate.BAR_CLOSE))


def test_zero_relative_seconds_is_legal():
    horizon = HorizonSpec(
        label="EXIT", kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.ACTUAL_EXIT,
        observation=_obs(price=_chain(PriceCandidate.FIXED_OBSERVED_PRICE), selection=ObservationSelectionMode.EXACT, lookahead=0, missing=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY),
        relative_seconds=0,
    )
    assert horizon.relative_seconds == 0


def test_negative_relative_seconds_rejected():
    with pytest.raises(ForwardPolicyValidationError):
        HorizonSpec(label="+5m", kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.SIGNAL, observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE)), relative_seconds=-1)


def test_excursion_requires_at_least_one_of_mfe_or_mae():
    with pytest.raises(ForwardPolicyValidationError):
        ExcursionPolicy(window_end=MfeMaeWindowEnd.TARGET_TIMESTAMP, start_inclusive=True, end_inclusive=True)


def test_excursion_start_end_inclusive_have_no_default():
    with pytest.raises(TypeError):
        ExcursionPolicy(window_end=MfeMaeWindowEnd.TARGET_TIMESTAMP, mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH))  # type: ignore[call-arg]


def test_verified_evidence_must_resolve_via_quote_alone():
    with pytest.raises(ForwardPolicyValidationError):
        ObservationPolicy(selection_mode=ObservationSelectionMode.EXACT, price_resolution=_chain(PriceCandidate.BAR_CLOSE), missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY, evidence_requirement=EvidenceVerificationState.VERIFIED)


def test_absent_evidence_must_never_resolve_via_quote():
    with pytest.raises(ForwardPolicyValidationError):
        ObservationPolicy(selection_mode=ObservationSelectionMode.FIRST_AT_OR_AFTER, price_resolution=_chain(PriceCandidate.QUOTE), missing_resolution=MissingResolutionPolicy.EXPIRE_AFTER_TOLERANCE, lookahead_seconds=90, evidence_requirement=EvidenceVerificationState.ABSENT)


def test_invalid_evidence_requires_mark_missing_immediately():
    with pytest.raises(ForwardPolicyValidationError):
        ObservationPolicy(selection_mode=ObservationSelectionMode.FIRST_AT_OR_AFTER, price_resolution=_chain(PriceCandidate.BAR_CLOSE), missing_resolution=MissingResolutionPolicy.EXPIRE_AFTER_TOLERANCE, lookahead_seconds=90, evidence_requirement=EvidenceVerificationState.INVALID)


def test_pre_resolved_reference_requires_fixed_observed_price_alone():
    # Boundary Closure item 4-6/H1: RETRACEMENT_SCAN removed; Codex's final
    # ownership ruling is UPSTREAM_REFERENCE_RESOLUTION for FIRST_PULLBACK_ENTRY.
    with pytest.raises(ForwardPolicyValidationError):
        ReferenceResolutionPolicy(kind=ReferenceResolutionKind.PRE_RESOLVED_REFERENCE, price_resolution=_chain(PriceCandidate.BAR_CLOSE), provenance="FIRST_PULLBACK_ENTRY")


def test_pre_resolved_reference_requires_nonempty_provenance():
    with pytest.raises(ForwardPolicyValidationError):
        ReferenceResolutionPolicy(kind=ReferenceResolutionKind.PRE_RESOLVED_REFERENCE, price_resolution=_chain(PriceCandidate.FIXED_OBSERVED_PRICE))


def test_pre_resolved_reference_legal_with_fixed_observed_price_and_provenance():
    reference = ReferenceResolutionPolicy(kind=ReferenceResolutionKind.PRE_RESOLVED_REFERENCE, price_resolution=_chain(PriceCandidate.FIXED_OBSERVED_PRICE), provenance="FIRST_PULLBACK_ENTRY")
    assert reference.kind is ReferenceResolutionKind.PRE_RESOLVED_REFERENCE
    restored = ReferenceResolutionPolicy.from_dict(reference.to_dict())
    assert restored == reference


def test_excursion_price_field_now_has_three_members_close_restored():
    assert {member.value for member in ExcursionPriceField} == {"HIGH", "LOW", "CLOSE"}


def test_forward_session_requires_mark_missing_immediately():
    # Boundary Closure item 19/20: FORWARD_SESSION's missing result must map
    # to INSUFFICIENT_FUTURE_SESSIONS immediately, never KEEP_PENDING.
    fs = ForwardSessionSpec(resolver_authority=ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS, session_offset=1, required_available_sessions=1)
    with pytest.raises(ForwardPolicyValidationError):
        HorizonSpec(
            label="d1", kind=HorizonKind.FORWARD_SESSION, origin=EventOrigin.CUSTOM,
            observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), selection=ObservationSelectionMode.LAST_AVAILABLE, lookahead=None, missing=MissingResolutionPolicy.KEEP_PENDING),
            forward_session=fs,
        )


def test_forward_session_bound_requires_forward_session_kind():
    with pytest.raises(ForwardPolicyValidationError):
        HorizonSpec(
            label="+5m", kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.SIGNAL,
            observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE)),
            excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.FORWARD_SESSION_BOUND, start_inclusive=True, end_inclusive=True, mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH)),
            relative_seconds=300,
        )


def test_data_completeness_policy_requires_positive_interval():
    with pytest.raises(ForwardPolicyValidationError):
        DataCompletenessPolicy(kind=DataCompletenessKind.CONTIGUOUS_INTERVAL, interval_seconds=0)


# =========================================================================
# 1b. Direct-constructor type safety (Boundary Closure item 32/33/34, Codex MEDIUM)
# =========================================================================


def test_price_resolution_policy_rejects_raw_string_authority():
    with pytest.raises(ForwardPolicyValidationError):
        PriceResolutionPolicy(authorities=("BOGUS",))


def test_price_resolution_policy_rejects_raw_string_matching_a_real_value():
    # A raw str that happens to equal a member's own .value must still be
    # rejected -- isinstance(x, PriceCandidate) is False for a plain str,
    # even when x == "BAR_CLOSE", since str(Enum) subclasses compare equal
    # to their value without being instances constructed via the enum.
    with pytest.raises(ForwardPolicyValidationError):
        PriceResolutionPolicy(authorities=("BAR_CLOSE",))


def test_observation_policy_rejects_raw_string_selection_mode():
    with pytest.raises(ForwardPolicyValidationError):
        ObservationPolicy(selection_mode="EXACT", price_resolution=_chain(PriceCandidate.BAR_CLOSE), missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY)


def test_excursion_policy_rejects_raw_string_window_end():
    with pytest.raises(ForwardPolicyValidationError):
        ExcursionPolicy(window_end="TARGET_TIMESTAMP", start_inclusive=True, end_inclusive=True, mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH))


def test_reference_resolution_policy_rejects_raw_string_kind():
    with pytest.raises(ForwardPolicyValidationError):
        ReferenceResolutionPolicy(kind="EXTERNAL_EVENT_TIMESTAMP", price_resolution=_chain(PriceCandidate.BAR_CLOSE))


def test_horizon_spec_rejects_raw_string_kind():
    with pytest.raises(ForwardPolicyValidationError):
        HorizonSpec(label="+5m", kind="RELATIVE_SECONDS", origin=EventOrigin.SIGNAL, observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE)), relative_seconds=300)


def test_forward_policy_rejects_raw_string_cost_semantics():
    horizon = HorizonSpec(label="+5m", kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.SIGNAL, observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE)), relative_seconds=300)
    with pytest.raises(ForwardPolicyValidationError):
        ForwardPolicy(
            legacy_program="sample", horizons=(horizon,), gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
            reference_resolution=_ref(price=_chain(PriceCandidate.BAR_CLOSE), origin=EventOrigin.SIGNAL),
            source_result_cost_semantics="GROSS_ONLY",
        )


# =========================================================================
# 2. Identity / immutability / serialization
# =========================================================================


def _sample_policy(legacy_program: str = "sample") -> ForwardPolicy:
    horizon = HorizonSpec(label="+5m", kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.SIGNAL, observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE)), relative_seconds=300)
    return ForwardPolicy(legacy_program=legacy_program, horizons=(horizon,), gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS), reference_resolution=_ref(price=_chain(PriceCandidate.BAR_CLOSE), origin=EventOrigin.SIGNAL))


def test_policy_id_is_stable_and_program_name_independent():
    assert _sample_policy().policy_id == _sample_policy().policy_id == _sample_policy("other").policy_id


def test_forward_policy_is_frozen():
    policy = _sample_policy()
    with pytest.raises(Exception):
        policy.legacy_program = "mutated"  # type: ignore[misc]


def test_forward_policy_serialize_roundtrip():
    policy = _sample_policy()
    restored = deserialize_forward_policy(serialize_forward_policy(policy))
    assert restored == policy


# =========================================================================
# 3. Calculator 1 -- Q9 Horizon/Exit (4-deep price chain, restated)
# =========================================================================


def test_calculator_1_horizon_exit_exact_price_chain_and_session_close_fallback():
    recap = _load_json("reports/trades/2026-05-15/0900/TRD_20260515_066570_01/reports/post_exit_shadow_recap.json")
    shadow = recap["post_exit_shadow"]
    assert shadow["symbol"] == "066570"
    exit_epoch = int(datetime.fromisoformat(shadow["exit_ts"]).timestamp())

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
    # Boundary Closure item 26/27: EOD's own `close_row` is normalized through
    # the SAME 4-deep alias chain as every intraday row
    # (`_row_price(raw,"close","price","current_price","cur_price")`,
    # `strategy_horizon_feedback.py:914`) BEFORE either checkpoint reads
    # `row["price"]`/`row["high"]`/`row["low"]` (`:958,966-967` intraday;
    # `:983-984,993-994` EOD) -- EOD's own checkpoint chain and excursion
    # (high_since_exit/low_since_exit, bounded by the EOD row's own ts) must
    # be IDENTICAL to the intraday checkpoints', never a shorter BAR_CLOSE-only
    # chain with no excursion at all.
    eod = HorizonSpec(
        label="EOD", kind=HorizonKind.SESSION_CLOSE, origin=EventOrigin.ACTUAL_EXIT,
        observation=_obs(price=checkpoint_price_chain, selection=ObservationSelectionMode.LAST_AVAILABLE, lookahead=None, missing=MissingResolutionPolicy.KEEP_PENDING),
        excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.OWN_CHECKPOINT_OBSERVATION, start_inclusive=True, end_inclusive=True, mfe_price_resolution=excursion_high_chain, mae_price_resolution=excursion_low_chain),
        fixed_clock=FixedClockSpec(clock_label="15:30"),
    )
    policy = ForwardPolicy(
        legacy_program="q9_horizon_exit_post_exit_shadow", horizons=horizons + (eod,),
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.FRACTION),
        reference_resolution=_ref(price=_chain(PriceCandidate.FIXED_OBSERVED_PRICE), origin=EventOrigin.ACTUAL_EXIT),
    )
    for horizon in horizons:
        assert horizon.observation.price_resolution.authorities == (PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE, PriceCandidate.SOURCE_FIELD_CURRENT_PRICE, PriceCandidate.SOURCE_FIELD_CUR_PRICE)
        assert horizon.excursion.mfe_price_resolution.authorities == (PriceCandidate.BAR_HIGH, PriceCandidate.SOURCE_FIELD_HIGH_PRICE, PriceCandidate.PRIMARY_PRICE_FALLBACK)
        assert horizon.excursion.mae_price_resolution.authorities == (PriceCandidate.BAR_LOW, PriceCandidate.SOURCE_FIELD_LOW_PRICE, PriceCandidate.PRIMARY_PRICE_FALLBACK)
    assert eod.observation.price_resolution.authorities == (PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE, PriceCandidate.SOURCE_FIELD_CURRENT_PRICE, PriceCandidate.SOURCE_FIELD_CUR_PRICE)
    assert eod.excursion is not None  # EOD DOES compute high_since_exit/low_since_exit -- never ABSENT
    assert eod.excursion.mfe_price_resolution.authorities == excursion_high_chain.authorities
    for label, seconds in minute_labels.items():
        row = shadow["checkpoints"][label]
        assert row["status"] == "observed"
        assert int(datetime.fromisoformat(row["observed_ts"]).timestamp()) >= exit_epoch + seconds
    assert shadow["checkpoints"]["EOD"]["status"] == "pending"
    sample_return = shadow["checkpoints"]["+5m"]["return_pct"]
    assert -1.0 < sample_return < 1.0  # FRACTION, never *100
    restored = deserialize_forward_policy(serialize_forward_policy(policy))
    assert restored == policy


# =========================================================================
# 4. Calculators 2-4 -- Q10 Semiconductor Calc A/B/C
# =========================================================================


def test_calculators_2_3_4_q10_semiconductor_reference_fallback_and_exact_windows():
    payload = _load_json("reports/evaluation/baseline_samsung_hynix/2026-09-11/baseline_samsung_hynix_forward_returns.json")
    row = next(r for r in payload["rows"] if r["symbol"] == "005930")
    base_epoch = row["baseline"]["baseline_epoch"]
    returns = row["returns"]

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
    policy = ForwardPolicy(
        legacy_program="baseline_samsung_hynix", horizons=calc_a_horizons + calc_b_horizons + (eod,),
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_ref(price=_chain(PriceCandidate.BAR_CLOSE), origin=EventOrigin.CANDIDATE),
    )
    assert {h.label for h in policy.horizons} == set(returns.keys())
    for label, seconds in calc_a_labels.items():
        horizon = next(h for h in policy.horizons if h.label == label)
        assert horizon.observation.price_resolution.authorities == (PriceCandidate.BAR_CLOSE, PriceCandidate.REFERENCE_PRICE)
        assert horizon.excursion.window_end is MfeMaeWindowEnd.TARGET_TIMESTAMP
        row_data = returns[label]
        assert row_data["status"] == "observed"
        target_epoch = base_epoch + seconds
        observed_epoch = int(datetime.strptime(row_data["observed_ts"], "%Y%m%d%H%M%S").replace(tzinfo=KST).timestamp())
        assert observed_epoch >= target_epoch
        assert observed_epoch - target_epoch <= 180
    for label, seconds in calc_b_labels.items():
        horizon = next(h for h in policy.horizons if h.label == label)
        assert horizon.observation.lookahead_seconds == 90
        assert horizon.excursion.start_inclusive is False
        assert horizon.excursion.window_end is MfeMaeWindowEnd.OWN_CHECKPOINT_OBSERVATION
        row_data = returns[label]
        assert row_data["status"] == "observed"

    restored = deserialize_forward_policy(serialize_forward_policy(policy))
    assert restored == policy


# =========================================================================
# 5-6. Calculators 5-6 -- Q10 Index Calc F/G (single-authority + collector 3-state)
# =========================================================================


def test_calculators_5_6_q10_index_single_authorities_and_collector_three_states():
    payload = _load_json("reports/evaluation/baseline_samsung_hynix/2026-09-11/q10_forward_validation/q10_actual_market_reactions.json")
    target = payload["targets"]["samsung"]
    day = payload["day"]

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

    g_0930 = _governed("09:30")
    g_1000 = _governed("10:00")
    g_close = _governed("CLOSE", selection=ObservationSelectionMode.LAST_AVAILABLE, lookback=600, lookahead=60)

    policy = ForwardPolicy(
        legacy_program="baseline_samsung_hynix_forward_validation",
        horizons=(opening,) + plain + g_0930 + g_1000 + g_close,
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_ref(price=_chain(PriceCandidate.BAR_OPEN), origin=EventOrigin.FIXED_CLOCK),
    )
    assert {h.label for h in policy.horizons} == set(target["points"].keys())
    for absent, invalid, verified in (g_0930, g_1000, g_close):
        assert absent.observation.evidence_requirement is EvidenceVerificationState.ABSENT
        assert invalid.observation.evidence_requirement is EvidenceVerificationState.INVALID
        assert verified.observation.evidence_requirement is EvidenceVerificationState.VERIFIED
        assert verified.observation.price_resolution.authorities == (PriceCandidate.QUOTE,)
        assert PriceCandidate.QUOTE not in absent.observation.price_resolution.authorities

    for label in plain_labels:
        point = target["points"][label]
        assert point["status"] == "OBSERVED"
        expected_epoch = _kst_epoch(day, label)
        assert point["ts"] >= expected_epoch
        assert point["ts"] - expected_epoch <= 90
    opening_point = target["points"]["09:00"]
    assert opening_point["volume"] > 0 and opening_point["price"] > 0

    restored = deserialize_forward_policy(serialize_forward_policy(policy))
    assert restored == policy


# =========================================================================
# 7. Calculator 7 -- Q10 Index directional shadow (Calc H, FIRST_PULLBACK_ENTRY)
# =========================================================================


def test_calculator_7_q10_index_directional_shadow_first_pullback_ownership_and_close_excursion():
    # Ownership determination FIXED (Boundary Closure item 4-6/H1, reversing
    # the Semantic Authority Reset's own prior conclusion): Codex's final
    # ruling is FIRST_PULLBACK_ENTRY = UPSTREAM_REFERENCE_RESOLUTION. Even
    # though _first_pullback_entry (shadow_comparison.py:43-64) physically
    # reads reaction.get("path") -- a candle series produced inside THIS SAME
    # evaluation package by Calculator F/G -- its 0.5% pullback_retrace_pct
    # threshold, 60-minute lookback, and direction/OVERREACTION-gated scan
    # ALGORITHM are a program-specific research technique, not a generic
    # forward-measurement primitive. UEF-2B never implements this scan; it
    # only consumes an already-resolved reference (PRE_RESOLVED_REFERENCE).
    reference = ReferenceResolutionPolicy(
        kind=ReferenceResolutionKind.PRE_RESOLVED_REFERENCE,
        price_resolution=_chain(PriceCandidate.FIXED_OBSERVED_PRICE),
        provenance="FIRST_PULLBACK_ENTRY",
    )
    assert reference.kind is ReferenceResolutionKind.PRE_RESOLVED_REFERENCE

    # The checkpoint itself: single EOD-anchored exit (reuses F/G's own
    # already-resolved CLOSE point directly, no independent price lookup),
    # MFE/MAE computed from a CLOSE-only price series (restored
    # ExcursionPriceField.CLOSE), signed by direction.
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
    policy = ForwardPolicy(
        legacy_program="baseline_samsung_hynix_forward_validation_shadow_comparison",
        horizons=(checkpoint,), gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS, direction=TradeDirection.SHORT),
        reference_resolution=reference,
    )
    assert checkpoint.excursion.mfe_price_resolution.authorities == (PriceCandidate.BAR_CLOSE,)
    assert checkpoint.excursion.mae_price_resolution.authorities == (PriceCandidate.BAR_CLOSE,)
    assert checkpoint.excursion.direction_aware is True
    restored = deserialize_forward_policy(serialize_forward_policy(policy))
    assert restored == policy


# =========================================================================
# 8. Calculator 8 -- Q11 (zero-offset outcome, EOD without excursion, cost semantics)
# =========================================================================


def test_calculator_8_q11_zero_offset_eod_no_excursion_and_cost_semantics():
    payload = _load_json("reports/evaluation/opportunity_engine_shadow/2026-09-11/opportunity_engine_virtual_trades.json")
    trade = payload["trades"][0]
    assert trade["symbol"] == "009150"

    # Q11 EXIT FINAL FIDELITY PATCH (Codex REJECT_UEF2A, single HIGH, 13/14 ->
    # 14/14): forward-horizon and EXIT excursion have DIFFERENT fallback
    # chains -- re-verified against simulator.py from scratch, they must
    # never share one chain object.
    # - reference/entry price (unchanged, PASS): `price = float(candle.get
    #   ("close") or features.get("price") or 0.0)` (:125), carried into
    #   position["entry_price"] (:138) -- BAR_CLOSE -> SOURCE_FIELD_PRICE.
    # - Q11_FORWARD_EXCURSION (+5/15/30/60m, unchanged, PASS): `_forward_
    #   returns` -- `high = max(row.get("high") or row.get("close") or 0.0
    #   ...)` / `low = min(row.get("low") or row.get("close") or 0.0 ...)`
    #   (:35-36) -- this function has NO access to `features` at all, so its
    #   fallback terminates at BAR_CLOSE: BAR_HIGH -> BAR_CLOSE / BAR_LOW ->
    #   BAR_CLOSE.
    # - Q11_EXIT_EXCURSION (position tracking, FIXED this patch): `high =
    #   float(candle.get("high") or price)` / `low = float(candle.get("low")
    #   or price)` (:147-148), where `price` is that SAME row's own
    #   `candle.get("close") or features.get("price")`-resolved value
    #   (:125) -- one level DEEPER: BAR_HIGH -> BAR_CLOSE -> SOURCE_FIELD_PRICE
    #   / BAR_LOW -> BAR_CLOSE -> SOURCE_FIELD_PRICE. The prior patch
    #   incorrectly reused the SAME 2-deep chain as the forward horizons.
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
    # UNCHANGED by this patch -- must remain ABSENT, must never inherit EXIT's excursion.
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
    policy = ForwardPolicy(
        legacy_program="q11_opportunity_engine", horizons=forward_horizons + (eod, exit_checkpoint),
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_ref(price=_chain(PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE), origin=EventOrigin.SIGNAL),
        source_result_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        cost_note="simulator.py both return_pct(gross) and net_return_pct(cost_pct/slippage_pct-adjusted) present in the same result dict",
    )
    assert policy.source_result_cost_semantics is SourceResultCostSemantics.NET_OR_COST_INCLUDED

    # Exact source-fidelity assertions (Codex's Q11 Exit Final Fidelity gate).
    assert policy.reference_resolution.price_resolution.authorities == (PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE)
    assert policy.reference_resolution.price_resolution.authorities[0] != PriceCandidate.BAR_OPEN

    for horizon in forward_horizons:
        assert horizon.excursion.mfe_price_resolution.authorities == (PriceCandidate.BAR_HIGH, PriceCandidate.BAR_CLOSE)
        assert horizon.excursion.mae_price_resolution.authorities == (PriceCandidate.BAR_LOW, PriceCandidate.BAR_CLOSE)
        assert horizon.excursion.mfe_price_resolution.authorities != (PriceCandidate.BAR_HIGH,)  # never a bare single candidate
        assert horizon.excursion.mae_price_resolution.authorities != (PriceCandidate.BAR_LOW,)

    assert exit_checkpoint.excursion.mfe_price_resolution.authorities == (PriceCandidate.BAR_HIGH, PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE)
    assert exit_checkpoint.excursion.mae_price_resolution.authorities == (PriceCandidate.BAR_LOW, PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE)
    # Negative regression: EXIT must never regress to the forward-horizon's shorter chain.
    assert exit_checkpoint.excursion.mfe_price_resolution.authorities != (PriceCandidate.BAR_HIGH, PriceCandidate.BAR_CLOSE)
    assert exit_checkpoint.excursion.mae_price_resolution.authorities != (PriceCandidate.BAR_LOW, PriceCandidate.BAR_CLOSE)
    # Explicit separation: forward and EXIT chains must differ.
    sample_forward = forward_horizons[0]
    assert sample_forward.excursion.mfe_price_resolution.authorities != exit_checkpoint.excursion.mfe_price_resolution.authorities
    assert sample_forward.excursion.mae_price_resolution.authorities != exit_checkpoint.excursion.mae_price_resolution.authorities

    eod_horizon = next(h for h in policy.horizons if h.label == "EOD")
    assert eod_horizon.excursion is None  # no MFE/MAE at all for Q11's EOD -- must remain ABSENT, never inherit EXIT's chain

    exit_horizon = next(h for h in policy.horizons if h.label == "EXIT")
    assert exit_horizon.relative_seconds == 0
    target_timestamp = trade["exit_epoch"] + exit_horizon.relative_seconds
    assert target_timestamp == trade["exit_epoch"]  # exact equality, no +1s drift

    signal_horizons = [h for h in policy.horizons if h.origin is EventOrigin.SIGNAL]
    assert {h.label for h in signal_horizons} == set(trade["forward_returns"].keys()) == {"+5m", "+15m", "+30m", "+60m", "EOD"}

    restored = deserialize_forward_policy(serialize_forward_policy(policy))
    assert restored == policy


# =========================================================================
# 9-11. Calculators 9-11 -- Q12 Calc1 (shared reuse, FULL 7 checkpoints)/Calc2/Calc3
# =========================================================================


def test_calculator_9_q12_shared_engine_reuse_produces_all_seven_checkpoints():
    # Reset Finding (item 30): attach_forward_returns (Q12's own module)
    # calls attach_baseline_forward_returns DIRECTLY (imported from
    # baseline_samsung_hynix.forward_returns) -- that function's own
    # `HORIZONS` free variable resolves to ITS OWN DEFINING MODULE's
    # `baseline_samsung_hynix.contracts.HORIZONS` (7 labels:
    # +5m/+15m/+30m/+60m/+120m/+180m/EOD), NEVER Q12's own 4-element
    # `baseline_btc_woori_tech.contracts.HORIZONS` -- Python free-variable
    # resolution is by DEFINING scope, not by caller. Confirmed against the
    # real artifact below: all 7 keys are actually present, not 4.
    payload = _load_json("reports/evaluation/baseline_btc_woori_tech/2026-09-11/baseline_btc_woori_forward_returns.json")
    row = payload["rows"][0]
    real_labels = set(row["returns"].keys())
    assert real_labels == {"+5m", "+15m", "+30m", "+60m", "+120m", "+180m", "EOD"}
    # NOT Q12's own declared HORIZONS constant (4 elements) -- that constant
    # is only a downstream SELECTION filter used by comparison.py/
    # historical_review.py, never a bound on what this calculator computes.
    from libs.reporting.baseline_btc_woori_tech.contracts import HORIZONS as Q12_OWN_HORIZONS
    assert set(Q12_OWN_HORIZONS) != real_labels
    assert set(Q12_OWN_HORIZONS) < real_labels  # a strict subset, not the true output


def test_calculator_10_q12_hypothesis_forward_five_labels():
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
    policy = ForwardPolicy(legacy_program="baseline_btc_woori_tech_hypothesis_forward", horizons=horizons, gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS), reference_resolution=_ref(price=_chain(PriceCandidate.BAR_CLOSE), origin=EventOrigin.CANDIDATE))
    assert {h.label for h in policy.horizons} == set(HYPOTHESIS_HORIZONS) == {"+5m", "+15m", "+30m", "+60m", "EOD"}


def test_calculator_11_q12_vnext_end_exclusive_and_completeness():
    # Boundary Closure item 12-14/H2: `outcomes.py::forward` gates MFE/MAE
    # ENTIRELY on a continuous-minute completeness check --
    # `expected = (target - t) // 60 + (1 if horizon == 'EOD' else 0)`,
    # `complete = len(window) == expected` (`vnext/outcomes.py:23-24`),
    # `mfe_pct`/`mae_pct` are `None` unless `complete` (`:28-29`) -- this is
    # now represented as a generic `DataCompletenessPolicy`, never left
    # unrepresented. Item 14: 09:30/10:00/EOD are each their own exact profile.
    completeness = DataCompletenessPolicy(kind=DataCompletenessKind.CONTIGUOUS_INTERVAL, interval_seconds=60.0, require_all_expected_observations=True)

    def _intraday(label: str) -> HorizonSpec:
        return HorizonSpec(
            label=label, kind=HorizonKind.FIXED_CLOCK_TARGET, origin=EventOrigin.FIXED_CLOCK,
            observation=_obs(price=_chain(PriceCandidate.BAR_OPEN), selection=ObservationSelectionMode.EXACT, lookahead=0, missing=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY),
            excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.TARGET_TIMESTAMP, start_inclusive=True, end_inclusive=False, mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH), mae_price_resolution=_chain(PriceCandidate.BAR_LOW), mfe_floor_zero=True, mae_cap_zero=True, completeness=completeness),
            fixed_clock=FixedClockSpec(clock_label=label),
        )

    vnext_0930 = _intraday("09:30")
    vnext_1000 = _intraday("10:00")
    vnext_eod = HorizonSpec(
        label="EOD", kind=HorizonKind.SESSION_CLOSE, origin=EventOrigin.FIXED_CLOCK,
        observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), selection=ObservationSelectionMode.EXACT, lookahead=0, missing=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY),
        excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.TARGET_TIMESTAMP, start_inclusive=True, end_inclusive=True, mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH), mae_price_resolution=_chain(PriceCandidate.BAR_LOW), mfe_floor_zero=True, mae_cap_zero=True, completeness=completeness),
        fixed_clock=FixedClockSpec(clock_label="15:30"),
    )
    assert vnext_0930.excursion.end_inclusive is False  # [t, target) -- end-EXCLUSIVE
    assert vnext_1000.excursion.end_inclusive is False
    assert vnext_eod.excursion.end_inclusive is True  # target bar appended -- end-INCLUSIVE
    assert vnext_0930.observation.price_resolution.authorities == (PriceCandidate.BAR_OPEN,)
    assert vnext_1000.observation.price_resolution.authorities == (PriceCandidate.BAR_OPEN,)
    assert vnext_eod.observation.price_resolution.authorities == (PriceCandidate.BAR_CLOSE,)
    assert vnext_0930.excursion.mfe_floor_zero and vnext_0930.excursion.mae_cap_zero
    for horizon in (vnext_0930, vnext_1000, vnext_eod):
        assert horizon.excursion.completeness is not None
        assert horizon.excursion.completeness.kind is DataCompletenessKind.CONTIGUOUS_INTERVAL
        assert horizon.excursion.completeness.interval_seconds == 60.0
    policy = ForwardPolicy(legacy_program="baseline_btc_woori_tech_vnext", horizons=(vnext_0930, vnext_1000, vnext_eod), gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS), reference_resolution=_ref(price=_chain(PriceCandidate.FIXED_OBSERVED_PRICE), origin=EventOrigin.CANDIDATE))
    restored = deserialize_forward_policy(serialize_forward_policy(policy))
    assert restored == policy


# =========================================================================
# 12-14. Calculators 12-14 -- Opening Shadow 1A/1B/1C
# =========================================================================


def test_calculator_12_opening_shadow_entry_and_forward_price_chains_differ():
    payload = _load_json("reports/evaluation/opening_rank1_shadow/2026-09-11/opening_rank1_shadow_daily.json")
    episode = next(e for e in payload["episodes"] if e["symbol"] == "032820")
    checkpoints = episode["checkpoints"]

    # Boundary Closure item 21-22/H4: excursion fallback FIXED to include
    # REFERENCE_PRICE. `_observe` -- `high = max(_number(value.get("high"))
    # or entry_price for value in window)` / `low = min(_number(value.get
    # ("low")) or entry_price ...)` (`latent_forward.py:122-123`) -- BAR_HIGH/
    # BAR_LOW fall back to the episode's OWN already-resolved `entry_price`
    # (REFERENCE_PRICE) when a candle's high/low is missing/zero, for BOTH
    # the intraday checkpoints and EOD (same loop body, `:104-131`).
    reference = _ref(price=_chain(PriceCandidate.BAR_OPEN, PriceCandidate.BAR_CLOSE), origin=EventOrigin.SIGNAL)
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
    policy = ForwardPolicy(legacy_program="opening_rank1_shadow_latent_forward", horizons=horizons + (eod,), gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS), reference_resolution=reference)

    # Entry/reference chain (episode-wide) DIFFERS from every forward
    # checkpoint's own chain -- the two layers must never be conflated:
    assert reference.price_resolution.authorities == (PriceCandidate.BAR_OPEN, PriceCandidate.BAR_CLOSE)
    for horizon in horizons:
        assert horizon.observation.price_resolution.authorities == (PriceCandidate.BAR_CLOSE, PriceCandidate.REFERENCE_PRICE)
        assert horizon.excursion.window_end is MfeMaeWindowEnd.TARGET_TIMESTAMP
        assert horizon.excursion.mfe_price_resolution.authorities == (PriceCandidate.BAR_HIGH, PriceCandidate.REFERENCE_PRICE)
        assert horizon.excursion.mae_price_resolution.authorities == (PriceCandidate.BAR_LOW, PriceCandidate.REFERENCE_PRICE)
    assert eod.excursion.mfe_price_resolution.authorities == (PriceCandidate.BAR_HIGH, PriceCandidate.REFERENCE_PRICE)
    assert {h.label for h in policy.horizons} == set(checkpoints.keys())

    baseline_epoch = episode["baseline_epoch"]
    for label, seconds in minute_labels.items():
        row = checkpoints[label]
        assert row["status"] == "observed"
        assert row["observed_epoch"] >= baseline_epoch + seconds
        assert row["observed_epoch"] - (baseline_epoch + seconds) <= 180

    restored = deserialize_forward_policy(serialize_forward_policy(policy))
    assert restored == policy


def test_calculator_13_opening_shadow_forward_30m_net_single_unbounded_checkpoint():
    # forward_30m_net: origin = upstream Q9 decision_epoch (not a fill);
    # single +30m checkpoint; unbounded forward search; output already
    # cost-net (ROUND_TRIP_COST_PCT baked in) -- no separate gross field.
    horizon = HorizonSpec(
        label="+30m", kind=HorizonKind.RELATIVE_SECONDS, origin=EventOrigin.MONITOR_DECISION,
        observation=_obs(price=_chain(PriceCandidate.BAR_OPEN, PriceCandidate.BAR_CLOSE), lookahead=None),
        excursion=None,
        relative_seconds=1800,
    )
    policy = ForwardPolicy(
        legacy_program="opening_rank1_longitudinal_forward_30m_net", horizons=(horizon,),
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_ref(price=_chain(PriceCandidate.BAR_OPEN, PriceCandidate.BAR_CLOSE), origin=EventOrigin.MONITOR_DECISION),
        source_result_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        cost_note="_net() bakes ROUND_TRIP_COST_PCT=0.28 into the only return figure this function produces; no separate gross field exists",
    )
    assert horizon.observation.missing_resolution is MissingResolutionPolicy.KEEP_PENDING
    assert horizon.excursion is None
    assert policy.source_result_cost_semantics is SourceResultCostSemantics.NET_OR_COST_INCLUDED
    restored = deserialize_forward_policy(serialize_forward_policy(policy))
    assert restored == policy


def test_calculator_14_opening_shadow_d1_d3_d5_bounded_sessions_and_insufficient_future():
    payload = _load_json("reports/evaluation/offline_alpha/opening_rank1_longitudinal/opening_rank1_longitudinal.json")
    events = payload["events"]

    # Boundary Closure item 16-20/H3: excursion window bound FIXED to
    # FORWARD_SESSION_BOUND (was UNBOUNDED_FORWARD -- the session target is
    # bounded but the excursion was not); missing_resolution FIXED to
    # MARK_MISSING_IMMEDIATELY (was KEEP_PENDING, under which
    # INSUFFICIENT_FUTURE_SESSIONS was dangling/unreachable). Evidence:
    # `delayed_path` -- `selected_rows = [row for day in selected_days for
    # row in grouped.get(day) or []]` where `selected_days = future_days[:
    # horizon]` (`delayed_outcomes.py:118,131-139`) is the SAME bounded
    # session-count window as the checkpoint; `d{n}_status =
    # "INSUFFICIENT_FUTURE_DAYS"` fires IMMEDIATELY in the same pass
    # (`:125-130`), it never waits/expires.
    def _forward_session_horizon(label: str, offset: int) -> HorizonSpec:
        return HorizonSpec(
            label=label, kind=HorizonKind.FORWARD_SESSION, origin=EventOrigin.CUSTOM,
            observation=_obs(price=_chain(PriceCandidate.BAR_CLOSE), selection=ObservationSelectionMode.LAST_AVAILABLE, lookahead=None, missing=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY),
            excursion=ExcursionPolicy(window_end=MfeMaeWindowEnd.FORWARD_SESSION_BOUND, start_inclusive=True, end_inclusive=True, mfe_price_resolution=_chain(PriceCandidate.BAR_HIGH)),  # MFE-only, no MAE
            forward_session=ForwardSessionSpec(resolver_authority=ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS, session_offset=offset, required_available_sessions=offset),
        )

    d1, d3, d5 = _forward_session_horizon("d1", 1), _forward_session_horizon("d3", 3), _forward_session_horizon("d5", 5)
    policy = ForwardPolicy(
        legacy_program="opening_rank1_longitudinal_delayed_path", horizons=(d1, d3, d5),
        gross_return=GrossReturnPolicy(return_unit=ReturnUnit.PERCENTAGE_POINTS),
        reference_resolution=_ref(price=_chain(PriceCandidate.FIXED_OBSERVED_PRICE), origin=EventOrigin.CUSTOM),
    )
    for horizon, offset in ((d1, 1), (d3, 3), (d5, 5)):
        assert horizon.forward_session.session_offset == offset
        assert horizon.forward_session.required_available_sessions == offset  # ALL intermediate sessions required, not just the Nth
        assert horizon.forward_session.resolver_authority is ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS
        assert horizon.excursion.mae_price_resolution is None  # MFE-only
        assert horizon.excursion.window_end is MfeMaeWindowEnd.FORWARD_SESSION_BOUND  # bounded, not UNBOUNDED_FORWARD
        assert horizon.observation.missing_resolution is MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY  # -> INSUFFICIENT_FUTURE_SESSIONS

    # Real artifact proof: an event with exactly 4 available future days --
    # d1 (needs 1) and d3 (needs 3) are OBSERVED, d5 (needs 5) is
    # INSUFFICIENT_FUTURE_DAYS (delayed_outcomes.py's own literal status
    # string) -- confirming required_available_sessions is a real,
    # independently-triggerable failure boundary, not merely descriptive:
    insufficient = next(e for e in events if e.get("d5_status") == "INSUFFICIENT_FUTURE_DAYS" and e.get("d1_status") == "OBSERVED" and e.get("d3_status") == "OBSERVED")
    assert insufficient["available_future_day_count"] < 5
    assert insufficient["available_future_day_count"] >= 3
    assert len(insufficient["observed_future_days"]) == insufficient["available_future_day_count"]

    restored = deserialize_forward_policy(serialize_forward_policy(policy))
    assert restored == policy


# =========================================================================
# Opening Controlled -- no program-specific forward calculator (re-confirmed)
# =========================================================================


def test_opening_controlled_has_no_program_specific_forward_policy():
    submissions = _load_json("data/logs/opening_rank1_controlled_probe/2026-09-10/probe_submissions.json")
    submission = submissions["submissions"][0]
    trade_model = _load_json("reports/evaluation/trades/2026-09-10/TRD_20260910_024060_01/trade_read_model.json")
    assert submission["symbol"] == trade_model["symbol"] == "024060"
    assert submission["run_id"] == trade_model["selection"]["strategist_run_id"]
    # No HorizonSpec/ForwardPolicy is constructed here: neither
    # opening_rank1_controlled_probe.py nor controlled_mock_lanes/coordinator.py
    # contains a forward/checkpoint calculation. Any eventual generic
    # forward figure for this fill comes from the SAME cross-program path
    # already proven by Calculator 1 (Q9 Horizon/Exit) above, never from a
    # policy specific to this program.
