"""UEF-2A BOUNDARY CLOSURE -- per-profile registry tests.

Unlike `test_uef2a_forward_policy_contract.py` (which anchors each
calculator's semantics against a real artifact/source excerpt), this file
tests the SOURCE-DERIVED SEMANTIC PROFILE REGISTRY itself
(`libs/reporting/evaluation/canonical/forward/profiles.py`): that all 14
calculators are independently constructible, individually valid, and that
none of the 5 previously-flagged HIGH findings regress. Additive-only;
imports nothing from any existing evaluator/report/runtime module.
"""
from __future__ import annotations

import pytest

from libs.reporting.evaluation.canonical.forward import (
    DataCompletenessKind,
    ForwardPolicyValidationError,
    MfeMaeWindowEnd,
    MissingResolutionPolicy,
    PriceCandidate,
    ReferenceResolutionKind,
)
from libs.reporting.evaluation.canonical.forward.policy import HorizonKind
from libs.reporting.evaluation.canonical.forward.profiles import (
    PROFILE_REGISTRY,
    all_profiles,
)


def test_all_14_profiles_are_registered():
    assert set(PROFILE_REGISTRY.keys()) == set(range(1, 15))
    assert len(all_profiles()) == 14


@pytest.mark.parametrize("number", range(1, 15))
def test_profile_builds_a_valid_forward_policy(number):
    profile = PROFILE_REGISTRY[number]
    assert profile.policy.legacy_program
    assert len(profile.policy.horizons) > 0
    assert profile.profile_id.startswith(f"UEF2A_PROFILE_{number:02d}_")
    assert profile.profile_version == profile.policy.policy_version


def test_profile_ids_are_reproducible_and_program_name_independent_of_number():
    # Rebuilding the registry must yield byte-identical policy_ids -- the
    # content hash does not depend on registry iteration order.
    from libs.reporting.evaluation.canonical.forward.profiles import _build_registry

    rebuilt = _build_registry()
    for number, profile in PROFILE_REGISTRY.items():
        assert rebuilt[number].policy.policy_id == profile.policy.policy_id


# =========================================================================
# H1: FIRST_PULLBACK_ENTRY ownership = UPSTREAM_REFERENCE_RESOLUTION
# =========================================================================


def test_profile_7_q10_index_calc_h_uses_pre_resolved_reference():
    profile = PROFILE_REGISTRY[7]
    ref = profile.policy.reference_resolution
    assert ref.kind is ReferenceResolutionKind.PRE_RESOLVED_REFERENCE
    assert ref.provenance == "FIRST_PULLBACK_ENTRY"
    assert ref.price_resolution.authorities == (PriceCandidate.FIXED_OBSERVED_PRICE,)


def test_no_profile_uses_a_removed_retracement_scan_kind():
    # RETRACEMENT_SCAN no longer exists as an enum member at all -- this
    # test asserts the ENUM itself, so a re-introduction would fail at
    # import time (AttributeError) before this test body even runs.
    assert not hasattr(ReferenceResolutionKind, "RETRACEMENT_SCAN")
    assert {member.name for member in ReferenceResolutionKind} == {"EXTERNAL_EVENT_TIMESTAMP", "PRE_RESOLVED_REFERENCE"}


# =========================================================================
# H2: Q12 continuous-minute completeness
# =========================================================================


def test_profile_11_q12_vnext_has_completeness_on_every_horizon():
    profile = PROFILE_REGISTRY[11]
    assert {h.label for h in profile.policy.horizons} == {"09:30", "10:00", "EOD"}
    for horizon in profile.policy.horizons:
        assert horizon.excursion is not None
        assert horizon.excursion.completeness is not None
        assert horizon.excursion.completeness.kind is DataCompletenessKind.CONTIGUOUS_INTERVAL
        assert horizon.excursion.completeness.interval_seconds == 60.0


# =========================================================================
# H3: Opening d1/d3/d5 excursion bound
# =========================================================================


def test_profile_14_opening_shadow_1c_excursion_is_session_bounded():
    profile = PROFILE_REGISTRY[14]
    assert {h.label for h in profile.policy.horizons} == {"d1", "d3", "d5"}
    for horizon in profile.policy.horizons:
        assert horizon.kind is HorizonKind.FORWARD_SESSION
        assert horizon.excursion.window_end is MfeMaeWindowEnd.FORWARD_SESSION_BOUND
        assert horizon.excursion.window_end is not MfeMaeWindowEnd.UNBOUNDED_FORWARD
        assert horizon.observation.missing_resolution is MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY


# =========================================================================
# H4: price fallback profiles now match source exactly
# =========================================================================


def test_profile_1_q9_horizon_exit_eod_has_full_chain_and_excursion():
    profile = PROFILE_REGISTRY[1]
    eod = next(h for h in profile.policy.horizons if h.label == "EOD")
    full_chain = (PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE, PriceCandidate.SOURCE_FIELD_CURRENT_PRICE, PriceCandidate.SOURCE_FIELD_CUR_PRICE)
    assert eod.observation.price_resolution.authorities == full_chain
    assert eod.excursion is not None
    assert eod.excursion.mfe_price_resolution.authorities == (PriceCandidate.BAR_HIGH, PriceCandidate.SOURCE_FIELD_HIGH_PRICE, PriceCandidate.PRIMARY_PRICE_FALLBACK)


def test_profile_12_opening_shadow_1a_excursion_falls_back_to_reference_price():
    profile = PROFILE_REGISTRY[12]
    for horizon in profile.policy.horizons:
        assert horizon.excursion is not None
        assert horizon.excursion.mfe_price_resolution.authorities == (PriceCandidate.BAR_HIGH, PriceCandidate.REFERENCE_PRICE)
        assert horizon.excursion.mae_price_resolution.authorities == (PriceCandidate.BAR_LOW, PriceCandidate.REFERENCE_PRICE)


# =========================================================================
# Q11 EXIT FINAL FIDELITY PATCH (single HIGH, 13/14 -> 14/14): forward-
# horizon and EXIT excursion have DIFFERENT fallback chains, re-verified
# against opportunity_engine/simulator.py -- they must be represented as
# two distinct chain objects, never one shared/collapsed chain. Negative-
# regression tests pin the exact tuples so the prior bugs (bare BAR_OPEN
# reference, bare BAR_HIGH/BAR_LOW excursion, EXIT silently sharing the
# forward horizons' shorter 2-deep chain) cannot silently return.
# =========================================================================

_Q11_FORWARD_LABELS = ("+5m", "+15m", "+30m", "+60m")


def test_profile_8_q11_reference_price_is_bar_close_then_source_field_price():
    profile = PROFILE_REGISTRY[8]
    ref = profile.policy.reference_resolution
    assert ref.price_resolution.authorities == (PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE)


def test_profile_8_q11_reference_price_is_never_bar_open():
    profile = PROFILE_REGISTRY[8]
    ref = profile.policy.reference_resolution
    assert PriceCandidate.BAR_OPEN not in ref.price_resolution.authorities
    assert ref.price_resolution.authorities != (PriceCandidate.BAR_OPEN,)


def test_profile_8_q11_forward_excursion_is_high_low_then_close():
    profile = PROFILE_REGISTRY[8]
    forward_horizons = [h for h in profile.policy.horizons if h.label in _Q11_FORWARD_LABELS]
    assert len(forward_horizons) == 4
    for horizon in forward_horizons:
        assert horizon.excursion is not None
        assert horizon.excursion.mfe_price_resolution.authorities == (PriceCandidate.BAR_HIGH, PriceCandidate.BAR_CLOSE)
        assert horizon.excursion.mae_price_resolution.authorities == (PriceCandidate.BAR_LOW, PriceCandidate.BAR_CLOSE)


def test_profile_8_q11_exit_excursion_is_high_low_close_then_source_field_price():
    profile = PROFILE_REGISTRY[8]
    exit_horizon = next(h for h in profile.policy.horizons if h.label == "EXIT")
    assert exit_horizon.excursion is not None
    assert exit_horizon.excursion.mfe_price_resolution.authorities == (PriceCandidate.BAR_HIGH, PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE)
    assert exit_horizon.excursion.mae_price_resolution.authorities == (PriceCandidate.BAR_LOW, PriceCandidate.BAR_CLOSE, PriceCandidate.SOURCE_FIELD_PRICE)


def test_profile_8_q11_exit_excursion_never_regresses_to_forward_length():
    # The exact bug this patch fixes: EXIT silently sharing the forward
    # horizons' shorter 2-deep chain (missing the SOURCE_FIELD_PRICE tail).
    profile = PROFILE_REGISTRY[8]
    exit_horizon = next(h for h in profile.policy.horizons if h.label == "EXIT")
    assert exit_horizon.excursion.mfe_price_resolution.authorities != (PriceCandidate.BAR_HIGH, PriceCandidate.BAR_CLOSE)
    assert exit_horizon.excursion.mae_price_resolution.authorities != (PriceCandidate.BAR_LOW, PriceCandidate.BAR_CLOSE)


def test_profile_8_q11_forward_and_exit_excursion_chains_explicitly_differ():
    profile = PROFILE_REGISTRY[8]
    forward_horizon = next(h for h in profile.policy.horizons if h.label == "+5m")
    exit_horizon = next(h for h in profile.policy.horizons if h.label == "EXIT")
    assert forward_horizon.excursion.mfe_price_resolution.authorities != exit_horizon.excursion.mfe_price_resolution.authorities
    assert forward_horizon.excursion.mae_price_resolution.authorities != exit_horizon.excursion.mae_price_resolution.authorities


def test_profile_8_q11_excursion_is_never_a_bare_single_candidate_chain():
    profile = PROFILE_REGISTRY[8]
    for horizon in profile.policy.horizons:
        if horizon.excursion is None:
            continue
        assert horizon.excursion.mfe_price_resolution.authorities != (PriceCandidate.BAR_HIGH,)
        assert horizon.excursion.mae_price_resolution.authorities != (PriceCandidate.BAR_LOW,)


def test_profile_8_q11_eod_excursion_still_absent_and_never_inherits_exit_chain():
    profile = PROFILE_REGISTRY[8]
    eod = next(h for h in profile.policy.horizons if h.label == "EOD")
    assert eod.excursion is None


def test_profile_8_q11_exactly_five_horizons_carry_excursion():
    profile = PROFILE_REGISTRY[8]
    excursion_horizons = [h for h in profile.policy.horizons if h.excursion is not None]
    assert {h.label for h in excursion_horizons} == {"+5m", "+15m", "+30m", "+60m", "EXIT"}


def test_profile_8_q11_cost_semantics_unchanged():
    from libs.reporting.evaluation.canonical.forward import SourceResultCostSemantics

    profile = PROFILE_REGISTRY[8]
    assert profile.policy.source_result_cost_semantics is SourceResultCostSemantics.NET_OR_COST_INCLUDED


# =========================================================================
# H5: source cost provenance -- 14/14 explicit table
# =========================================================================


def test_all_14_profiles_have_explicit_cost_provenance_not_dangling_unknown():
    # Every profile must have made an explicit, evidence-backed choice.
    # UNKNOWN is legal ONLY where source evidence genuinely cannot answer
    # the question -- verified per-profile below (none in this inventory).
    from libs.reporting.evaluation.canonical.forward import SourceResultCostSemantics

    unknown_without_justification = [
        number for number, profile in PROFILE_REGISTRY.items()
        if profile.policy.source_result_cost_semantics is SourceResultCostSemantics.UNKNOWN and not profile.policy.cost_note
    ]
    assert unknown_without_justification == []


def test_cost_provenance_counts():
    from libs.reporting.evaluation.canonical.forward import SourceResultCostSemantics

    counts = {SourceResultCostSemantics.GROSS_ONLY: 0, SourceResultCostSemantics.NET_OR_COST_INCLUDED: 0, SourceResultCostSemantics.UNKNOWN: 0}
    for profile in PROFILE_REGISTRY.values():
        counts[profile.policy.source_result_cost_semantics] += 1
    # Re-verified against source for all 14: Q10 Index Calc H (7, gross_eod_
    # return_pct AND net_eod_return_pct both present), Q11 (8), Q12 Calc2
    # hypothesis_forward (10, gross_return_pct AND net_return_pct both
    # present), Q12 Calc3 vnext (11, same shape), Opening Shadow 1B (13) and
    # 1C (14, both use the same cost-baked _net() helper, no gross field at
    # all) are the six real NET_OR_COST_INCLUDED calculators; the remaining
    # eight report gross movement only, verified via source (never a dangling
    # UNKNOWN default).
    assert counts[SourceResultCostSemantics.NET_OR_COST_INCLUDED] == 6
    assert counts[SourceResultCostSemantics.GROSS_ONLY] == 8
    assert counts[SourceResultCostSemantics.UNKNOWN] == 0


# =========================================================================
# UEF-2B invariant (item 38/40/41): no program name anywhere in the generic core
# =========================================================================


def test_generic_core_public_symbols_never_encode_a_program_name():
    # Docstring EVIDENCE CITATIONS (e.g. "Q10 Index's FIRST_PULLBACK_ENTRY")
    # are expected and required (every member must trace to real source) --
    # what must never happen is a STRUCTURAL symbol (a class, enum member,
    # or field name) itself encoding a program name, since that would force
    # UEF-2B to import/branch on a specific calculator to use the contract.
    import inspect

    from libs.reporting.evaluation.canonical.forward import contracts, policy

    banned = ("q9", "q10", "q11", "q12", "opening", "samsung", "hynix", "woori", "btc", "kiwoom")
    for module in (contracts, policy):
        for name, obj in vars(module).items():
            if name.startswith("_") or not inspect.isclass(obj):
                continue
            lowered = name.lower()
            for term in banned:
                assert term not in lowered, f"{module.__name__}.{name} must not encode program name {term!r}"
            if issubclass(obj, __import__("enum").Enum):
                for member in obj:
                    member_lowered = member.name.lower()
                    for term in banned:
                        assert term not in member_lowered, f"{module.__name__}.{name}.{member.name} must not encode program name {term!r}"


def test_forward_policy_validation_error_is_still_the_only_raised_error_type():
    with pytest.raises(ForwardPolicyValidationError):
        PROFILE_REGISTRY[1].policy.__class__(legacy_program="", horizons=(), gross_return=PROFILE_REGISTRY[1].policy.gross_return, reference_resolution=PROFILE_REGISTRY[1].policy.reference_resolution)
