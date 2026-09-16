"""UEF-1 Work Package A Fix2 focused tests.

Additive-only: nothing here imports or modifies any existing evaluator,
report, or runtime module except to READ real, already-generated JSON/MD
artifacts from ``reports/`` and ``data/logs/`` for the legacy-roundtrip
tests (no artifact is written to). These tests only exercise the new
``libs/reporting/evaluation/canonical`` package.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from libs.reporting.evaluation.canonical import (
    ALLOWED_RECORD_RELATION_TYPES,
    DerivedFieldKind,
    DerivedIdentityPart,
    DuplicateRelation,
    EntryAuthority,
    EntryObservation,
    EventDateRelation,
    EventOrigin,
    EventRef,
    EvidenceStatus,
    ExecutionMode,
    ExitObservation,
    IdentityKind,
    LineageStatus,
    ObservationType,
    Provenance,
    SampleStatus,
    build_derived_event_ref,
    build_event_ref,
    build_fixed_clock_event_ref,
    canonicalize_fixed_clock_label,
    canonicalize_symbol,
    canonicalize_trading_date,
    classify_duplicate_relation,
    cross_program_link_key,
    deserialize_record,
    epoch_seconds_to_kst_date,
    evaluation_record_id,
    evaluation_subject_id,
    normalize_enum_value,
    serialize_record,
    to_epoch_seconds,
    validate_event_ref,
)
from libs.reporting.evaluation.canonical.relations import (
    RecordRelationValidationError,
    validate_native_event_identity_consistency,
    validate_record_links,
)
from libs.reporting.evaluation.canonical.record import (
    AggregateIdentity,
    AggregateRecord,
    Checkpoint,
    CheckpointCompleteness,
    CheckpointMetricKind,
    CanonicalRecordValidationError,
    CanonicalSerializationError,
    EpisodeIdentity,
    EpisodeRecord,
    EvaluationCost,
    EvaluationQuality,
    PairIdentity,
    PairRecord,
    PairSide,
    RecordLink,
    SequenceIdentity,
    SequenceLeg,
    SequenceRecord,
    build_aggregate_record,
    build_episode_record,
    build_pair_record,
    build_sequence_record,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _real(path: str) -> Path:
    full = REPO_ROOT / path
    if not full.exists():
        pytest.skip(f"real artifact not present in this checkout: {path}")
    return full


def _load_json(path: str) -> dict:
    return json.loads(_real(path).read_text(encoding="utf-8"))


def _load_trade_read_model(day: str, trade_id: str) -> dict:
    return _load_json(f"reports/evaluation/trades/{day}/{trade_id}/trade_read_model.json")


def _episode(**overrides) -> EpisodeRecord:
    defaults = dict(
        source_namespace="test_namespace",
        hypothesis_id="TEST_HYPOTHESIS",
        observation_type=ObservationType.CANDIDATE,
        execution_mode=ExecutionMode.SHADOW,
        trading_date="2026-09-11",
        symbol="005930",
        native_id="TEST_NATIVE_ID_001",
        entry=EntryObservation(entry_time=1789084800, entry_price=10000.0, entry_authority=EntryAuthority.CANDIDATE_PRICE),
        checkpoints=(
            Checkpoint(horizon_label="+5m", horizon_origin=EventOrigin.CANDIDATE, observed_timestamp=1789085100,
                       observed_price=10100.0, gross_return=1.0, net_return=0.72, completeness=CheckpointCompleteness.OBSERVED),
        ),
    )
    defaults.update(overrides)
    return build_episode_record(**defaults)


# === 1. Enum/string canonicalization (H1) ================================

def test_str_of_str_enum_is_not_dot_value_confirming_the_real_defect():
    # Confirms the exact mechanism Codex flagged: Python's str,Enum mixin
    # does NOT make str(member) equal .value on this interpreter.
    assert str(EventOrigin.CANDIDATE) != EventOrigin.CANDIDATE.value


def test_normalize_enum_value_equates_member_and_raw_string():
    assert normalize_enum_value(EventOrigin.CANDIDATE, EventOrigin) == "CANDIDATE"
    assert normalize_enum_value("CANDIDATE", EventOrigin) == "CANDIDATE"
    assert normalize_enum_value(EventOrigin.CANDIDATE, EventOrigin) == normalize_enum_value("CANDIDATE", EventOrigin)


def test_evaluation_subject_id_identical_whether_enum_member_or_raw_string_passed():
    a = evaluation_subject_id(canonical_event_id="EVT_x", hypothesis_id="H", observation_type=ObservationType.CANDIDATE)
    b = evaluation_subject_id(canonical_event_id="EVT_x", hypothesis_id="H", observation_type="CANDIDATE")
    assert a == b


def test_evaluation_record_id_identical_whether_enum_member_or_raw_string_passed():
    subj = evaluation_subject_id(canonical_event_id="EVT_x", hypothesis_id="H", observation_type="CANDIDATE")
    a = evaluation_record_id(evaluation_subject_id=subj, execution_mode=ExecutionMode.SHADOW)
    b = evaluation_record_id(evaluation_subject_id=subj, execution_mode="SHADOW")
    assert a == b


# === 2. 60-second-bucket removed from identity; native id priority (H2/H3/#3-5) ===

def test_stage2_30s_polling_two_real_decisions_never_merge():
    # The exact real-world scenario Codex's re-audit found broken: two
    # genuinely independent Strategist Stage2 decisions landing in the
    # same wall-clock minute must NEVER collide, because each has its own
    # native decision_id.
    a = build_event_ref(source_namespace="strategist_stage2", native_id="Q9_20260911_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    b = build_event_ref(source_namespace="strategist_stage2", native_id="Q9_20260911_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    assert a.canonical_event_id != b.canonical_event_id
    assert a.identity_kind is IdentityKind.NATIVE
    assert b.identity_kind is IdentityKind.NATIVE


def test_no_timestamp_bucketing_function_participates_in_build_event_ref():
    # build_event_ref has no timestamp parameter of any kind -- confirmed
    # structurally, not just by convention.
    import inspect
    sig = inspect.signature(build_event_ref)
    assert "event_timestamp" not in sig.parameters
    assert "timestamp" not in sig.parameters


def test_native_id_preferred_over_derived_when_both_could_apply():
    ref = build_event_ref(source_namespace="q11_opportunity_engine", native_id="OE_TRD_009150_1789085100",
                          derived_fields={
                              "trading_date": DerivedIdentityPart(kind=DerivedFieldKind.TRADING_DATE, value="2026-09-11"),
                              "symbol": DerivedIdentityPart(kind=DerivedFieldKind.SYMBOL, value="009150"),
                          })
    assert ref.identity_kind is IdentityKind.NATIVE
    assert ref.source_id == "OE_TRD_009150_1789085100"


def test_derived_fallback_used_only_when_no_native_id():
    ref = build_event_ref(source_namespace="q10_lead_market", derived_fields={
        "trading_date": DerivedIdentityPart(kind=DerivedFieldKind.TRADING_DATE, value="2026-09-11"),
        "symbol": DerivedIdentityPart(kind=DerivedFieldKind.SYMBOL, value="005930"),
        "fixed_clock_label": DerivedIdentityPart(kind=DerivedFieldKind.FIXED_CLOCK_LABEL, value="09:00"),
    })
    assert ref.identity_kind is IdentityKind.DERIVED


def test_build_event_ref_requires_native_id_or_derived_parts():
    with pytest.raises(ValueError):
        build_event_ref(source_namespace="x")


# === 3. Identity recompute validation (H3, #19-21) ========================

def test_validate_event_ref_accepts_a_correctly_built_ref():
    ref = build_event_ref(source_namespace="q16", native_id="Q16_ROW_1")
    validate_event_ref(ref)  # must not raise


def test_validate_event_ref_rejects_hand_tampered_canonical_id():
    ref = build_event_ref(source_namespace="q16", native_id="Q16_ROW_1")
    tampered = EventRef(identity_kind=ref.identity_kind, source_namespace=ref.source_namespace,
                        source_id=ref.source_id, canonical_event_id="EVT_" + "0" * 20,
                        derivation_version=ref.derivation_version)
    with pytest.raises(ValueError):
        validate_event_ref(tampered)


def test_episode_record_rejects_evaluation_subject_id_recompute_mismatch():
    # Deliberately bypasses the builder to prove the raw dataclass
    # constructor still enforces recompute-consistency on its own.
    with pytest.raises(CanonicalRecordValidationError):
        EpisodeRecord(
            identity=EpisodeIdentity(
                event=build_event_ref(source_namespace="test_namespace", native_id="TEST_NATIVE_ID_001"),
                hypothesis_id="TEST_HYPOTHESIS",
                evaluation_subject_id="SUBJ_" + "a" * 20,  # not actually derived from the fields above
                evaluation_record_id="REC_" + "a" * 20,
            ),
            trading_date="2026-09-11", symbol="005930",
            observation_type=ObservationType.CANDIDATE, execution_mode=ExecutionMode.SHADOW,
        )


def test_episode_record_rejects_evaluation_record_id_recompute_mismatch():
    event = build_event_ref(source_namespace="test_namespace", native_id="TEST_NATIVE_ID_001")
    subj = evaluation_subject_id(canonical_event_id=event.canonical_event_id, hypothesis_id="TEST_HYPOTHESIS", observation_type=ObservationType.CANDIDATE)
    with pytest.raises(CanonicalRecordValidationError):
        EpisodeRecord(
            identity=EpisodeIdentity(
                event=event, hypothesis_id="TEST_HYPOTHESIS",
                evaluation_subject_id=subj,
                evaluation_record_id="REC_" + "b" * 20,  # not actually derived from subj+execution_mode
            ),
            trading_date="2026-09-11", symbol="005930",
            observation_type=ObservationType.CANDIDATE, execution_mode=ExecutionMode.SHADOW,
        )


def test_builder_is_the_easy_correct_path_hand_construction_is_hard_and_checked():
    # The builder always yields a self-consistent record.
    ep = _episode()
    assert ep.identity.evaluation_record_id.startswith("REC_")
    # Round-tripping through serialize/deserialize preserves consistency.
    restored = deserialize_record(serialize_record(ep))
    assert restored == ep


# === 4. Cross-program link key is non-authoritative (#6-8) ===============

def test_cross_program_link_key_has_no_timestamp_parameter():
    import inspect
    sig = inspect.signature(cross_program_link_key)
    assert "timestamp" not in sig.parameters
    assert set(sig.parameters) == {"trading_date", "symbol", "context_label"}


def test_cross_program_link_key_distinct_namespace_from_identity_ids():
    key = cross_program_link_key(trading_date="2026-09-11", symbol="024060", context_label="OPENING_WINDOW")
    assert key.startswith("LINK_")
    event = build_event_ref(source_namespace="opening_rank1_shadow", native_id="024060:1789085034")
    assert not event.canonical_event_id.startswith("LINK_")


def test_classify_duplicate_relation_signature_excludes_link_key():
    import inspect
    sig = inspect.signature(classify_duplicate_relation)
    assert "cross_program_link_key" not in sig.parameters
    assert "link_key" not in " ".join(sig.parameters).lower()


def test_two_different_events_can_share_a_link_key_and_this_is_correct():
    # Two Stage2 decisions AND an Opening Rank1 sighting all happening
    # "during the opening window" for the same symbol/day may share a
    # link key while being three entirely different canonical events.
    link = cross_program_link_key(trading_date="2026-09-11", symbol="024060", context_label="OPENING_WINDOW")
    stage2_event = build_event_ref(source_namespace="strategist_stage2", native_id="Q9_20260911_ccc")
    opening_event = build_event_ref(source_namespace="opening_rank1_shadow", native_id="024060:1789085034")
    assert stage2_event.canonical_event_id != opening_event.canonical_event_id
    # (link is computed independently -- shown here only to confirm it's a
    # distinct namespace/format from either event's own identity)
    assert link != stage2_event.canonical_event_id
    assert link != opening_event.canonical_event_id


# === 5. Duplicate relation classification (7 values) ======================

def _relation_ids(*, symbol_a, symbol_b, hyp_a, hyp_b, mode_a, mode_b, native_a, native_b, ns="test", ver_a="v1", ver_b="v1"):
    event_a = build_event_ref(source_namespace=ns, native_id=native_a)
    event_b = build_event_ref(source_namespace=ns, native_id=native_b)
    subj_a = evaluation_subject_id(canonical_event_id=event_a.canonical_event_id, hypothesis_id=hyp_a, observation_type="RANK_EVENT")
    subj_b = evaluation_subject_id(canonical_event_id=event_b.canonical_event_id, hypothesis_id=hyp_b, observation_type="RANK_EVENT")
    rec_a = evaluation_record_id(evaluation_subject_id=subj_a, execution_mode=mode_a)
    rec_b = evaluation_record_id(evaluation_subject_id=subj_b, execution_mode=mode_b)
    return dict(
        canonical_event_id_a=event_a.canonical_event_id, evaluation_subject_id_a=subj_a, evaluation_record_id_a=rec_a,
        symbol_a=symbol_a, hypothesis_id_a=hyp_a, evaluator_version_a=ver_a,
        canonical_event_id_b=event_b.canonical_event_id, evaluation_subject_id_b=subj_b, evaluation_record_id_b=rec_b,
        symbol_b=symbol_b, hypothesis_id_b=hyp_b, evaluator_version_b=ver_b,
    )


def test_accidental_duplicate():
    ids = _relation_ids(symbol_a="024060", symbol_b="024060", hyp_a="H", hyp_b="H", mode_a="SHADOW", mode_b="SHADOW",
                        native_a="EVT1", native_b="EVT1")
    assert classify_duplicate_relation(**ids) is DuplicateRelation.ACCIDENTAL_DUPLICATE


def test_legitimate_multi_hypothesis():
    ids = _relation_ids(symbol_a="024060", symbol_b="024060", hyp_a="IMMEDIATE_OPENING_PROBE", hyp_b="CONFIRMED_RECURRENT_RANK",
                        mode_a="OBSERVATION_ONLY", mode_b="OBSERVATION_ONLY", native_a="EVT1", native_b="EVT1")
    assert classify_duplicate_relation(**ids) is DuplicateRelation.LEGITIMATE_MULTI_HYPOTHESIS


def test_same_subject_different_evaluator_version():
    ids = _relation_ids(symbol_a="024060", symbol_b="024060", hyp_a="Q16", hyp_b="Q16",
                        mode_a="OBSERVATION_ONLY", mode_b="OBSERVATION_ONLY", native_a="EVT1", native_b="EVT1", ver_a="v1", ver_b="v2")
    assert classify_duplicate_relation(**ids) is DuplicateRelation.SAME_SUBJECT_DIFFERENT_EVALUATOR_VERSION


def test_same_subject_different_execution_mode():
    ids = _relation_ids(symbol_a="024060", symbol_b="024060", hyp_a="IMMEDIATE_OPENING_PROBE", hyp_b="IMMEDIATE_OPENING_PROBE",
                        mode_a="SHADOW", mode_b="CONTROLLED_MOCK", native_a="EVT1", native_b="EVT1")
    assert classify_duplicate_relation(**ids) is DuplicateRelation.SAME_SUBJECT_DIFFERENT_EXECUTION_MODE


def test_repeated_setup_same_hypothesis_different_event():
    ids = _relation_ids(symbol_a="024060", symbol_b="024060", hyp_a="IMMEDIATE_OPENING_PROBE", hyp_b="IMMEDIATE_OPENING_PROBE",
                        mode_a="OBSERVATION_ONLY", mode_b="OBSERVATION_ONLY", native_a="EVT_DAY1", native_b="EVT_DAY2")
    assert classify_duplicate_relation(**ids) is DuplicateRelation.REPEATED_SETUP


def test_same_symbol_different_episode_different_hypothesis():
    ids = _relation_ids(symbol_a="024060", symbol_b="024060", hyp_a="IMMEDIATE_OPENING_PROBE", hyp_b="CONFIRMED_RECURRENT_RANK",
                        mode_a="OBSERVATION_ONLY", mode_b="OBSERVATION_ONLY", native_a="EVT_DAY1", native_b="EVT_DAY2")
    assert classify_duplicate_relation(**ids) is DuplicateRelation.SAME_SYMBOL_DIFFERENT_EPISODE


def test_different_symbol():
    ids = _relation_ids(symbol_a="005930", symbol_b="000660", hyp_a="Q10", hyp_b="Q10",
                        mode_a="DIAGNOSTIC", mode_b="DIAGNOSTIC", native_a="EVT1", native_b="EVT2")
    assert classify_duplicate_relation(**ids) is DuplicateRelation.DIFFERENT_SYMBOL


# === 6. Fixed-clock identity (#10) ========================================

def test_fixed_clock_derived_identity_stable_across_reruns():
    a = build_fixed_clock_event_ref(source_namespace="q10_lead_market", trading_date="2026-09-11", symbol="005930", fixed_clock_label="09:00")
    b = build_fixed_clock_event_ref(source_namespace="q10_lead_market", trading_date="2026-09-11", symbol="005930", fixed_clock_label="09:00")
    assert a.canonical_event_id == b.canonical_event_id


def test_fixed_clock_different_checkpoint_label_different_identity():
    a = build_fixed_clock_event_ref(source_namespace="q10_lead_market", trading_date="2026-09-11", symbol="005930", fixed_clock_label="09:00")
    b = build_fixed_clock_event_ref(source_namespace="q10_lead_market", trading_date="2026-09-11", symbol="005930", fixed_clock_label="09:03")
    assert a.canonical_event_id != b.canonical_event_id


# === 6b. Typed derived-identity canonicalization (Fix3 H4) ===============

def test_canonicalize_fixed_clock_label_drops_seconds():
    assert canonicalize_fixed_clock_label("09:00:00") == "09:00"
    assert canonicalize_fixed_clock_label("09:00") == "09:00"
    assert canonicalize_fixed_clock_label(" close ") == "CLOSE"


def test_canonicalize_fixed_clock_label_rejects_invalid_clock_time():
    with pytest.raises(ValueError):
        canonicalize_fixed_clock_label("25:99")


def test_fixed_clock_09_00_and_09_00_00_produce_same_identity():
    a = build_fixed_clock_event_ref(source_namespace="q10_lead_market", trading_date="2026-09-11", symbol="005930", fixed_clock_label="09:00")
    b = build_fixed_clock_event_ref(source_namespace="q10_lead_market", trading_date="2026-09-11", symbol="005930", fixed_clock_label="09:00:00")
    assert a.canonical_event_id == b.canonical_event_id


def test_derived_event_ref_symbol_normalization_005930_vs_A005930():
    a = build_derived_event_ref(source_namespace="q11_opportunity_engine", trading_date="2026-09-11", symbol="005930")
    b = build_derived_event_ref(source_namespace="q11_opportunity_engine", trading_date="2026-09-11", symbol="A005930")
    assert a.canonical_event_id == b.canonical_event_id  # same real KRX symbol, per existing authority


def test_derived_event_ref_date_normalization_string_vs_date_object():
    import datetime as dt
    a = build_derived_event_ref(source_namespace="q11_opportunity_engine", trading_date="2026-09-11", symbol="005930")
    b = build_derived_event_ref(source_namespace="q11_opportunity_engine", trading_date=dt.date(2026, 9, 11), symbol="005930")
    assert a.canonical_event_id == b.canonical_event_id


def test_generic_build_event_ref_now_normalizes_symbol_fields_too():
    # Closure Reset Group A/#2-3: there is no longer a "raw arbitrary
    # dict -> hash" path AT ALL, even through the generic build_event_ref
    # entry point -- a field tagged SYMBOL is routed through
    # canonicalize_symbol() no matter which function call site declares
    # it. "005930" and "A005930" MUST be equivalent everywhere now, not
    # only through the convenience typed builders.
    a = build_event_ref(source_namespace="q12_btc_woori", derived_fields={
        "symbol": DerivedIdentityPart(kind=DerivedFieldKind.SYMBOL, value="005930"),
    })
    b = build_event_ref(source_namespace="q12_btc_woori", derived_fields={
        "symbol": DerivedIdentityPart(kind=DerivedFieldKind.SYMBOL, value="A005930"),
    })
    assert a.canonical_event_id == b.canonical_event_id


def test_raw_field_kind_is_the_only_remaining_unnormalized_escape_hatch():
    # RAW is the explicit, named escape hatch for genuinely opaque values
    # (e.g. a numeric epoch) that have no dedicated canonicalization
    # authority -- unlike the old bare dict, a caller must explicitly say
    # "this field is RAW" rather than accidentally getting an
    # unnormalized SYMBOL/TRADING_DATE field by omission.
    a = build_event_ref(source_namespace="q12_btc_woori", derived_fields={
        "target_epoch": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value=1789084500),
    })
    b = build_event_ref(source_namespace="q12_btc_woori", derived_fields={
        "target_epoch": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value=1789084500),
    })
    assert a.canonical_event_id == b.canonical_event_id


def test_derived_event_ref_extra_fields_are_carried_as_raw():
    # UEF-1 FINAL CLOSURE PATCH H2: extra_fields no longer accepts a plain
    # dict[str, Any] silently wrapped whole into one RAW part -- every
    # value must now be an explicit, already-kinded DerivedIdentityPart.
    a = build_derived_event_ref(source_namespace="strategist_stage2", trading_date="2026-09-11", symbol="233740",
                                extra_fields={"decision_id": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value="Q9_x"),
                                              "side": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value="before")})
    b = build_derived_event_ref(source_namespace="strategist_stage2", trading_date="2026-09-11", symbol="233740",
                                extra_fields={"decision_id": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value="Q9_x"),
                                              "side": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value="before")})
    assert a.canonical_event_id == b.canonical_event_id


def test_derived_event_ref_extra_fields_rejects_plain_dict_value():
    # The actual H2 defect: a plain dict/value in extra_fields must be
    # rejected outright, never silently promoted to RAW.
    with pytest.raises(ValueError):
        build_derived_event_ref(source_namespace="strategist_stage2", trading_date="2026-09-11", symbol="233740",
                                extra_fields={"decision_id": "Q9_x"})


def test_raw_field_named_symbol_is_rejected_even_though_untyped_raw_would_accept_it():
    # H2 negative test: a RAW-kinded part whose OWN field name is a
    # reserved canonical identity concept must be rejected outright --
    # RAW must never be used to bypass canonicalize_symbol().
    with pytest.raises(ValueError):
        build_event_ref(source_namespace="test_ns", derived_fields={
            "symbol": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value="A005930"),
        })


def test_raw_nested_symbol_bypass_is_rejected():
    # H2/#6 negative test: RAW {"symbol": "A005930"} must not be usable as
    # canonical event identity authority just because it is nested inside
    # a differently-named field.
    with pytest.raises(ValueError):
        build_event_ref(source_namespace="test_ns", derived_fields={
            "context": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value={"symbol": "A005930"}),
        })


def test_raw_deeply_nested_symbol_bypass_is_rejected():
    # H2/#6 negative test: nested even deeper, still must not bypass.
    with pytest.raises(ValueError):
        build_event_ref(source_namespace="test_ns", derived_fields={
            "context": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value={"outer": {"symbol": "A005930"}}),
        })


def test_raw_nested_trading_date_bypass_is_rejected():
    # Same bypass family, checked for trading_date too, not only symbol.
    with pytest.raises(ValueError):
        build_event_ref(source_namespace="test_ns", derived_fields={
            "context": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value={"trading_date": "2026-09-11"}),
        })


def test_raw_genuinely_opaque_value_still_works():
    # RAW remains valid for a genuinely opaque value with no reserved name
    # anywhere in it -- this is not a general RAW ban, only a targeted
    # bypass closure.
    ref = build_event_ref(source_namespace="test_ns", derived_fields={
        "decision_id": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value="Q9_20260911_abc123"),
    })
    assert ref.identity_kind is IdentityKind.DERIVED


# === 7. Date/symbol canonicalization strengthened (#24/#26) ==============

def test_invalid_calendar_date_rejected():
    with pytest.raises(ValueError):
        canonicalize_trading_date("2026-99-99")


def test_valid_calendar_date_accepted():
    assert canonicalize_trading_date("2026-09-11") == "2026-09-11"


def test_short_numeric_symbol_is_rejected_not_accepted_as_pseudo_symbol():
    # UEF-1 FINAL CLOSURE PATCH H1: Codex's final audit confirmed the
    # repo's actual production contract is "005930 valid, A005930 ->
    # 005930, 5930 REJECT" -- and found that UEF's own
    # canonicalize_symbol, while correctly NOT zero-padding "5930", was
    # still using allow_test_symbols=True and would fall through to the
    # pseudo-symbol path (since "5930" is composed only of characters the
    # pseudo-symbol pattern allows), silently ACCEPTING a production-
    # invalid symbol as if it were a legitimate pseudo-symbol label. This
    # superseded the Closure Reset's own "Case B" test below, which
    # asserted the wrong (accepting) behavior -- fixed by using
    # allow_test_symbols=False (the same authority every real production
    # symbol consumer in this repo uses) AND rejecting any purely-numeric
    # string outright rather than letting it reach the pseudo-symbol
    # fallback at all.
    with pytest.raises(ValueError):
        canonicalize_symbol("5930")


def test_production_symbol_authority_rejects_short_digit_form():
    # The production-only authority (allow_test_symbols=False) that this
    # repo's own real symbol consumers use rejects "5930" outright --
    # confirming it is not a legitimate real-world representation at all,
    # only a test-tolerant one.
    from libs.core.symbols import normalize_symbol
    assert normalize_symbol("5930", allow_test_symbols=False) == ""
    assert normalize_symbol("005930", allow_test_symbols=False) == "005930"


def test_krx_prefix_form_normalizes_correctly():
    assert canonicalize_symbol("A005930") == "005930"
    assert canonicalize_symbol("005930") == "005930"


# === 7b. Fix3 M1: canonical symbol storage in the record itself, not just in identity ==

def test_builder_stores_canonical_symbol_even_when_given_raw_krx_prefix_form():
    ep = _episode(symbol="A005930")
    assert ep.symbol == "005930"  # canonicalized by build_episode_record, not stored raw


def test_raw_constructor_rejects_non_canonical_symbol():
    with pytest.raises(CanonicalRecordValidationError):
        EpisodeRecord(
            identity=EpisodeIdentity(
                event=build_event_ref(source_namespace="test", native_id="X"),
                hypothesis_id="H",
                evaluation_subject_id=evaluation_subject_id(
                    canonical_event_id=build_event_ref(source_namespace="test", native_id="X").canonical_event_id,
                    hypothesis_id="H", observation_type=ObservationType.CANDIDATE,
                ),
                evaluation_record_id="REC_" + "a" * 20,
            ),
            trading_date="2026-09-11", symbol="A005930",  # raw, non-canonical form
            observation_type=ObservationType.CANDIDATE, execution_mode=ExecutionMode.SHADOW,
        )


def test_sequence_builder_stores_canonical_symbol():
    e1 = build_event_ref(source_namespace="same_symbol_sequences", native_id="LEG1")
    seq = build_sequence_record(
        source_namespace="same_symbol_sequences", hypothesis_id="H", trading_date="2026-09-11", symbol="A005930",
        legs=(SequenceLeg(leg_id="LEG1", event=e1, order_index=1),), native_id="seq_canon_symbol",
    )
    assert seq.symbol == "005930"


def test_pair_side_direct_constructor_accepts_canonical_symbol():
    # UEF-1 PAIRSIDE FINAL PATCH: a bare PairSide (built outside any
    # PairRecord) must accept an already-canonical production symbol.
    side = PairSide(event=build_event_ref(source_namespace="test", native_id="L"), symbol="005930",
                    observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC)
    assert side.symbol == "005930"


def test_pair_side_direct_constructor_accepts_krx_prefix_form():
    # Existing PairSide contract (test_pair_record_rejects_non_canonical_side_symbol
    # below): the bare constructor does not itself enforce canonical-form
    # equality -- that stricter check remains PairRecord.__post_init__'s
    # job once both sides are wrapped. "A005930" is still a legitimate
    # symbol representation (canonicalize_symbol accepts and normalizes
    # it), so it must not be rejected here.
    side = PairSide(event=build_event_ref(source_namespace="test", native_id="L"), symbol="A005930",
                    observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC)
    assert side.symbol == "A005930"


def test_pair_side_direct_constructor_rejects_production_invalid_short_digit_symbol():
    # UEF-1 PAIRSIDE FINAL PATCH H1 (Codex Final Freeze Audit blocker):
    # PairSide(symbol="5930") was previously ACCEPTED by the bare public
    # constructor -- production-invalid input must never survive the
    # direct construction path, independent of whether it is ever wrapped
    # in a PairRecord.
    with pytest.raises(ValueError):
        PairSide(event=build_event_ref(source_namespace="test", native_id="L"), symbol="5930",
                 observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC)


def test_pair_record_rejects_non_canonical_side_symbol():
    left = PairSide(event=build_event_ref(source_namespace="test", native_id="L"), symbol="A005930",
                    observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC)
    right = PairSide(event=build_event_ref(source_namespace="test", native_id="R"), symbol="000660",
                     observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC)
    with pytest.raises(CanonicalRecordValidationError):
        build_pair_record(
            source_namespace="test", hypothesis_id="H", pair_type="t", trading_date="2026-09-11",
            left=left, right=right, native_id="pair_bad_symbol",
        )


# === 8. Validation strictness (#28) =======================================

def test_actual_trade_requires_entry():
    with pytest.raises(CanonicalRecordValidationError):
        _episode(observation_type=ObservationType.ACTUAL_TRADE, execution_mode=ExecutionMode.BROKER_LIVE, entry=None)


def test_exit_event_requires_exit():
    with pytest.raises(CanonicalRecordValidationError):
        _episode(observation_type=ObservationType.EXIT_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC, exit=None)


def test_observed_checkpoint_requires_observed_timestamp():
    with pytest.raises(CanonicalRecordValidationError):
        _episode(checkpoints=(
            Checkpoint(horizon_label="+5m", horizon_origin=EventOrigin.CANDIDATE, observed_timestamp=None,
                       gross_return=1.0, completeness=CheckpointCompleteness.OBSERVED),
        ))


def test_observed_checkpoint_with_gross_return_requires_observed_price():
    with pytest.raises(CanonicalRecordValidationError):
        _episode(checkpoints=(
            Checkpoint(horizon_label="+5m", horizon_origin=EventOrigin.CANDIDATE, observed_timestamp=1789085100,
                       observed_price=None, gross_return=1.0, completeness=CheckpointCompleteness.OBSERVED),
        ))


def test_observed_checkpoint_with_net_return_only_still_requires_observed_price():
    # Fix3 M3: Fix2 only checked gross_return -- net_return/mfe/mae alone
    # (with gross_return absent) must be caught too.
    with pytest.raises(CanonicalRecordValidationError):
        _episode(checkpoints=(
            Checkpoint(horizon_label="+5m", horizon_origin=EventOrigin.CANDIDATE, observed_timestamp=1789085100,
                       observed_price=None, net_return=0.72, completeness=CheckpointCompleteness.OBSERVED),
        ))
    with pytest.raises(CanonicalRecordValidationError):
        _episode(checkpoints=(
            Checkpoint(horizon_label="+5m", horizon_origin=EventOrigin.CANDIDATE, observed_timestamp=1789085100,
                       observed_price=None, mfe=1.1, completeness=CheckpointCompleteness.OBSERVED),
        ))
    with pytest.raises(CanonicalRecordValidationError):
        _episode(checkpoints=(
            Checkpoint(horizon_label="+5m", horizon_origin=EventOrigin.CANDIDATE, observed_timestamp=1789085100,
                       observed_price=None, mae=-0.3, completeness=CheckpointCompleteness.OBSERVED),
        ))


def test_aggregate_only_checkpoint_is_the_explicit_escape_hatch():
    # A checkpoint-shaped value not anchored to one observed price must
    # declare metric_kind=AGGREGATE_ONLY explicitly -- then the
    # observed_price requirement does not apply.
    ep = _episode(checkpoints=(
        Checkpoint(horizon_label="+5m", horizon_origin=EventOrigin.CANDIDATE, observed_timestamp=1789085100,
                   observed_price=None, net_return=0.72, completeness=CheckpointCompleteness.OBSERVED,
                   metric_kind=CheckpointMetricKind.AGGREGATE_ONLY),
    ))
    assert ep.checkpoints[0].metric_kind is CheckpointMetricKind.AGGREGATE_ONLY


def test_complete_sample_status_contradicts_pending_checkpoint():
    with pytest.raises(CanonicalRecordValidationError):
        _episode(
            quality=EvaluationQuality(sample_status=SampleStatus.COMPLETE),
            checkpoints=(Checkpoint(horizon_label="+30m", horizon_origin=EventOrigin.ENTRY, completeness=CheckpointCompleteness.PENDING),),
        )


def test_observation_only_forbids_broker_fill_and_mock_fill():
    with pytest.raises(CanonicalRecordValidationError):
        _episode(execution_mode=ExecutionMode.OBSERVATION_ONLY, entry=EntryObservation(entry_authority=EntryAuthority.BROKER_FILL))
    with pytest.raises(CanonicalRecordValidationError):
        _episode(execution_mode=ExecutionMode.OBSERVATION_ONLY, entry=EntryObservation(entry_authority=EntryAuthority.MOCK_FILL))


def test_shadow_forbids_broker_and_mock_fill():
    with pytest.raises(CanonicalRecordValidationError):
        _episode(execution_mode=ExecutionMode.SHADOW, entry=EntryObservation(entry_authority=EntryAuthority.MOCK_FILL))


def test_diagnostic_with_broker_fill_allowed_for_post_hoc_analysis():
    ep = _episode(observation_type=ObservationType.ACTUAL_TRADE, execution_mode=ExecutionMode.DIAGNOSTIC,
                  entry=EntryObservation(entry_time=1789084800, entry_price=100.0, entry_authority=EntryAuthority.BROKER_FILL))
    assert ep.execution_mode is ExecutionMode.DIAGNOSTIC


def test_submitted_intent_requires_a_real_execution_attempt_mode():
    with pytest.raises(CanonicalRecordValidationError):
        _episode(execution_mode=ExecutionMode.SHADOW, entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT))


def test_submitted_intent_allowed_under_controlled_mock():
    ep = _episode(observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
                 entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT))
    assert ep.entry.entry_authority is EntryAuthority.SUBMITTED_INTENT


# === 9. Event/trading-date consistency (#25) ==============================

def test_same_day_entry_requires_same_day_declaration():
    entry_time = to_epoch_seconds("20260911090500")  # 2026-09-11 KST
    ep = _episode(trading_date="2026-09-11", entry=EntryObservation(entry_time=entry_time, entry_price=100.0),
                 event_date_relation=EventDateRelation.SAME_DAY)
    assert epoch_seconds_to_kst_date(entry_time) == "2026-09-11"
    assert ep.event_date_relation is EventDateRelation.SAME_DAY


def test_same_day_declared_but_actually_different_day_rejected():
    entry_time = to_epoch_seconds("20260912090500")  # actually 2026-09-12
    with pytest.raises(CanonicalRecordValidationError):
        _episode(trading_date="2026-09-11", entry=EntryObservation(entry_time=entry_time, entry_price=100.0),
                 event_date_relation=EventDateRelation.SAME_DAY)


def test_overnight_carry_must_be_declared_when_dates_differ():
    entry_time = to_epoch_seconds("20260912090500")
    ep = _episode(trading_date="2026-09-11", entry=EntryObservation(entry_time=entry_time, entry_price=100.0),
                 event_date_relation=EventDateRelation.OVERNIGHT_CARRY)
    assert ep.event_date_relation is EventDateRelation.OVERNIGHT_CARRY


def test_overnight_carry_declared_but_dates_actually_match_rejected():
    entry_time = to_epoch_seconds("20260911090500")
    with pytest.raises(CanonicalRecordValidationError):
        _episode(trading_date="2026-09-11", entry=EntryObservation(entry_time=entry_time, entry_price=100.0),
                 event_date_relation=EventDateRelation.OVERNIGHT_CARRY)


# === 10. JSON-safe serialization =========================================

def test_datetime_in_metadata_raises_explicitly():
    import datetime as dt
    episode = _episode()
    bad = EpisodeRecord(
        identity=episode.identity, trading_date=episode.trading_date, symbol=episode.symbol,
        observation_type=episode.observation_type, execution_mode=episode.execution_mode,
        metadata={"bad": dt.datetime(2026, 9, 11)},
    )
    with pytest.raises(CanonicalSerializationError):
        bad.to_dict()


def test_event_ref_serializes_and_restores_through_record_roundtrip():
    ep = _episode()
    restored = deserialize_record(serialize_record(ep))
    assert restored.identity.event == ep.identity.event
    assert isinstance(restored.identity.event, EventRef)


# === 11. PairRecord: dual independent event identity (#13) ===============

def test_pair_record_preserves_independent_left_right_event_identity():
    left_event = build_event_ref(source_namespace="strategist_stage2", native_id="Q9_20260911_left")
    right_event = build_event_ref(source_namespace="strategist_stage2", native_id="Q9_20260911_right")
    left = PairSide(event=left_event, symbol="233740", observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC)
    right = PairSide(event=right_event, symbol="032820", observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC)
    pair = build_pair_record(
        source_namespace="strategist_stage2", hypothesis_id="STRATEGIST_STAGE2_REFRESH_AUTHORITY_V1",
        pair_type="refresh_before_after", trading_date="2026-09-11", left=left, right=right,
        native_id="Q9_20260911_pairdecision",
    )
    assert pair.identity.left_event.canonical_event_id == left_event.canonical_event_id
    assert pair.identity.right_event.canonical_event_id == right_event.canonical_event_id
    assert pair.identity.left_event.canonical_event_id != pair.identity.right_event.canonical_event_id
    assert pair.left.symbol != pair.right.symbol
    restored = deserialize_record(serialize_record(pair))
    assert restored == pair


def test_pair_record_rejects_mismatched_identity_left_event():
    left_event = build_event_ref(source_namespace="strategist_stage2", native_id="Q9_left")
    other_event = build_event_ref(source_namespace="strategist_stage2", native_id="Q9_other")
    left = PairSide(event=left_event, symbol="233740", observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC)
    right = PairSide(event=build_event_ref(source_namespace="strategist_stage2", native_id="Q9_right"),
                     symbol="032820", observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC)
    with pytest.raises(CanonicalRecordValidationError):
        PairRecord(
            identity=PairIdentity(pair_event=build_event_ref(source_namespace="strategist_stage2", native_id="Q9_pair"),
                                  left_event=other_event, right_event=right.event,
                                  evaluation_subject_id="SUBJ_" + "a" * 20, evaluation_record_id="REC_" + "a" * 20),
            trading_date="2026-09-11", left=left, right=right,
        )


def test_pair_execution_mode_independent_of_left_and_right_execution_mode():
    # Closure Reset MEDIUM/#15: the pair's own evaluation_record_id must
    # not depend on whichever side happens to be "left" -- confirmed by
    # building two pairs with left/right SWAPPED but the same explicit
    # pair_execution_mode, and checking the pair's own record id is
    # unaffected by that swap (the two swapped pairs still differ, but
    # only because their pair_event native_id differs below -- the point
    # is pair_execution_mode, not left.execution_mode, drives the hash).
    left = PairSide(event=build_event_ref(source_namespace="strategist_stage2", native_id="Q9_left"),
                    symbol="233740", observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.BROKER_LIVE)
    right = PairSide(event=build_event_ref(source_namespace="strategist_stage2", native_id="Q9_right"),
                     symbol="032820", observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.SHADOW)
    pair_a = build_pair_record(
        source_namespace="strategist_stage2", hypothesis_id="H", pair_type="t", trading_date="2026-09-11",
        left=left, right=right, native_id="Q9_pair_x", pair_execution_mode=ExecutionMode.DIAGNOSTIC,
    )
    pair_b = build_pair_record(
        source_namespace="strategist_stage2", hypothesis_id="H", pair_type="t", trading_date="2026-09-11",
        left=left, right=right, native_id="Q9_pair_x", pair_execution_mode=ExecutionMode.CONTROLLED_MOCK,
    )
    # Same everything except pair_execution_mode -- the record id MUST
    # differ (it is a genuine identity input), proving pair_execution_mode
    # (not left.execution_mode, which is identical in both) drives it.
    assert pair_a.identity.evaluation_record_id != pair_b.identity.evaluation_record_id
    assert pair_a.pair_execution_mode is ExecutionMode.DIAGNOSTIC
    assert pair_b.pair_execution_mode is ExecutionMode.CONTROLLED_MOCK
    assert left.execution_mode is ExecutionMode.BROKER_LIVE  # unchanged, and irrelevant to the pair's own id


# === 12. SequenceRecord: real multi-leg fidelity (#15/#34) ===============

def test_real_multi_leg_same_symbol_sequence_two_legs():
    payload = _load_json("reports/evaluation/same_symbol_sequences/2026-07-10/same_symbol_sequence.json")
    seq_row = next(s for s in payload["sequences"] if s["day_symbol_sequence_id"] == "2026-07-10:005930")
    assert seq_row["trade_count"] == 2  # confirms this really is a multi-leg fixture, not a single-leg one
    legs = []
    for trade in seq_row["trades"]:
        event = build_event_ref(source_namespace="same_symbol_sequences", native_id=trade["trade_id"])
        legs.append(SequenceLeg(
            leg_id=trade["trade_id"], event=event, order_index=trade["trade_ordinal"],
            parent_leg_id=trade.get("prior_trade_id") or "",
            relation_to_previous=trade.get("prior_exit_outcome", "NOT_APPLICABLE"),
        ))
    seq = build_sequence_record(
        source_namespace="same_symbol_sequences", hypothesis_id="same_symbol_sequences",
        trading_date=seq_row["day"], symbol=seq_row["symbol"], legs=tuple(legs),
        native_id=seq_row["day_symbol_sequence_id"],
        sequence_metrics={"cumulative_return_pct": seq_row["cumulative_return_pct"],
                          "profit_giveback_pct": seq_row["profit_giveback_pct"]},
        provenance=Provenance(legacy_program="same_symbol_sequences", source_artifact="same_symbol_sequence.json"),
    )
    assert len(seq.legs) == 2
    assert seq.legs[0].order_index == 1
    assert seq.legs[1].order_index == 2
    assert seq.legs[1].parent_leg_id == seq.legs[0].leg_id == "TRD_20260710_005930_01"
    assert seq.legs[1].relation_to_previous == "LOSS"  # leg1's net_return_pct was negative
    assert seq.legs[0].event.canonical_event_id != seq.legs[1].event.canonical_event_id
    restored = deserialize_record(serialize_record(seq))
    assert restored == seq


def test_sequence_record_rejects_out_of_order_legs():
    e1 = build_event_ref(source_namespace="same_symbol_sequences", native_id="LEG1")
    e2 = build_event_ref(source_namespace="same_symbol_sequences", native_id="LEG2")
    with pytest.raises(CanonicalRecordValidationError):
        build_sequence_record(
            source_namespace="same_symbol_sequences", hypothesis_id="same_symbol_sequences",
            trading_date="2026-09-11", symbol="005930",
            legs=(SequenceLeg(leg_id="LEG2", event=e2, order_index=2), SequenceLeg(leg_id="LEG1", event=e1, order_index=1)),
            native_id="seq_bad_order",
        )


def test_real_multi_leg_same_symbol_sequence_three_legs():
    payload = _load_json("reports/evaluation/same_symbol_sequences/2026-07-02/same_symbol_sequence.json")
    seq_row = next(s for s in payload["sequences"] if s["day_symbol_sequence_id"] == "2026-07-02:041830")
    assert seq_row["trade_count"] == 3
    legs = tuple(
        SequenceLeg(
            leg_id=trade["trade_id"], event=build_event_ref(source_namespace="same_symbol_sequences", native_id=trade["trade_id"]),
            order_index=trade["trade_ordinal"], parent_leg_id=trade.get("prior_trade_id") or "",
            relation_to_previous=trade.get("prior_exit_outcome", "NOT_APPLICABLE"),
        )
        for trade in seq_row["trades"]
    )
    seq = build_sequence_record(
        source_namespace="same_symbol_sequences", hypothesis_id="same_symbol_sequences",
        trading_date=seq_row["day"], symbol=seq_row["symbol"], legs=legs, native_id=seq_row["day_symbol_sequence_id"],
    )
    assert [leg.order_index for leg in seq.legs] == [1, 2, 3]
    assert seq.legs[1].parent_leg_id == seq.legs[0].leg_id
    assert seq.legs[2].parent_leg_id == seq.legs[1].leg_id
    restored = deserialize_record(serialize_record(seq))
    assert restored == seq


def test_sequence_record_rejects_duplicate_order_index():
    e1 = build_event_ref(source_namespace="same_symbol_sequences", native_id="LEG1")
    e2 = build_event_ref(source_namespace="same_symbol_sequences", native_id="LEG2")
    with pytest.raises(CanonicalRecordValidationError):
        build_sequence_record(
            source_namespace="same_symbol_sequences", hypothesis_id="same_symbol_sequences",
            trading_date="2026-09-11", symbol="005930",
            legs=(SequenceLeg(leg_id="LEG1", event=e1, order_index=1), SequenceLeg(leg_id="LEG2", event=e2, order_index=1)),
            native_id="seq_dup_order",
        )


def test_sequence_record_rejects_missing_parent_reference():
    e1 = build_event_ref(source_namespace="same_symbol_sequences", native_id="LEG1")
    with pytest.raises(CanonicalRecordValidationError):
        build_sequence_record(
            source_namespace="same_symbol_sequences", hypothesis_id="same_symbol_sequences",
            trading_date="2026-09-11", symbol="005930",
            legs=(SequenceLeg(leg_id="LEG1", event=e1, order_index=1, parent_leg_id="LEG_DOES_NOT_EXIST"),),
            native_id="seq_missing_parent",
        )


def test_sequence_record_rejects_future_parent():
    e1 = build_event_ref(source_namespace="same_symbol_sequences", native_id="LEG1")
    e2 = build_event_ref(source_namespace="same_symbol_sequences", native_id="LEG2")
    with pytest.raises(CanonicalRecordValidationError):
        build_sequence_record(
            source_namespace="same_symbol_sequences", hypothesis_id="same_symbol_sequences",
            trading_date="2026-09-11", symbol="005930",
            legs=(
                SequenceLeg(leg_id="LEG1", event=e1, order_index=1, parent_leg_id="LEG2"),  # parent has a LATER order_index
                SequenceLeg(leg_id="LEG2", event=e2, order_index=2),
            ),
            native_id="seq_future_parent",
        )


def test_sequence_record_rejects_self_parent():
    e1 = build_event_ref(source_namespace="same_symbol_sequences", native_id="LEG1")
    with pytest.raises(CanonicalRecordValidationError):
        build_sequence_record(
            source_namespace="same_symbol_sequences", hypothesis_id="same_symbol_sequences",
            trading_date="2026-09-11", symbol="005930",
            legs=(SequenceLeg(leg_id="LEG1", event=e1, order_index=1, parent_leg_id="LEG1"),),
            native_id="seq_self_parent",
        )


def test_sequence_record_rejects_relation_without_parent():
    e1 = build_event_ref(source_namespace="same_symbol_sequences", native_id="LEG1")
    with pytest.raises(CanonicalRecordValidationError):
        build_sequence_record(
            source_namespace="same_symbol_sequences", hypothesis_id="same_symbol_sequences",
            trading_date="2026-09-11", symbol="005930",
            legs=(SequenceLeg(leg_id="LEG1", event=e1, order_index=1, relation_to_previous="LOSS"),),
            native_id="seq_orphan_relation",
        )


# === 13. AggregateRecord: no market-event identity, lineage status (#16-18) ==

def test_aggregate_record_never_requires_symbol_or_market_event():
    agg = build_aggregate_record(
        source_namespace="alpha_research_board", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        aggregation_scope="cohort", aggregation_window_start="2026-08-03", aggregation_window_end="2026-09-11",
        native_id="IMMEDIATE_OPENING_PROBE:cohort", episode_count=26,
        source_episode_ids=(), lineage_status=LineageStatus.UNKNOWN,
        metrics={"win_rate": 0.6538},
    )
    assert agg.symbol == ""  # never forced


def test_aggregate_identity_exposes_canonical_aggregate_id_not_event_naming():
    # Closure Reset LOW/#16: callers should read/write canonical_aggregate_id,
    # not canonical_event_id, for an aggregate -- an aggregate has no event.
    agg = build_aggregate_record(
        source_namespace="alpha_research_board", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        aggregation_scope="cohort", aggregation_window_start="2026-08-03",
        native_id="IMMEDIATE_OPENING_PROBE:cohort",
    )
    assert agg.identity.canonical_aggregate_id == agg.identity.aggregate_ref.canonical_event_id
    assert agg.identity.canonical_aggregate_id.startswith("EVT_")


def _ids(n: int) -> tuple[str, ...]:
    return tuple(f"REC_{i:020x}" for i in range(n))


def _build_agg(*, episode_count: int, id_count: int, lineage_status: LineageStatus) -> AggregateRecord:
    return build_aggregate_record(
        source_namespace="test", hypothesis_id="H", aggregation_scope="cohort", aggregation_window_start="2026-08-03",
        native_id=f"agg_{episode_count}_{id_count}_{lineage_status.value}",
        episode_count=episode_count, source_episode_ids=_ids(id_count), lineage_status=lineage_status,
    )


# Fix3 H1/#3: the exact fixture matrix Codex specified. FULL/PARTIAL/UNKNOWN
# each get a hard boundary -- no "close enough" is accepted.

def test_lineage_full_3_of_3_pass():
    agg = _build_agg(episode_count=3, id_count=3, lineage_status=LineageStatus.FULL)
    assert agg.lineage_status is LineageStatus.FULL


def test_lineage_full_2_of_3_fail():
    with pytest.raises(CanonicalRecordValidationError):
        _build_agg(episode_count=3, id_count=2, lineage_status=LineageStatus.FULL)


def test_lineage_partial_1_of_3_pass():
    agg = _build_agg(episode_count=3, id_count=1, lineage_status=LineageStatus.PARTIAL)
    assert agg.lineage_status is LineageStatus.PARTIAL


def test_lineage_partial_2_of_3_pass():
    agg = _build_agg(episode_count=3, id_count=2, lineage_status=LineageStatus.PARTIAL)
    assert agg.lineage_status is LineageStatus.PARTIAL


def test_lineage_partial_3_of_3_fail():
    # Fix2's rejected defect: this exact case (coverage == episode_count
    # declared PARTIAL) used to pass. Now must fail -- PARTIAL means
    # genuinely incomplete, never full coverage mislabeled.
    with pytest.raises(CanonicalRecordValidationError):
        _build_agg(episode_count=3, id_count=3, lineage_status=LineageStatus.PARTIAL)


def test_lineage_partial_4_of_3_fail():
    # Fix2's other rejected defect: coverage > episode_count used to pass.
    with pytest.raises(CanonicalRecordValidationError):
        _build_agg(episode_count=3, id_count=4, lineage_status=LineageStatus.PARTIAL)


def test_lineage_partial_0_of_3_fail():
    with pytest.raises(CanonicalRecordValidationError):
        _build_agg(episode_count=3, id_count=0, lineage_status=LineageStatus.PARTIAL)


def test_lineage_unknown_0_of_3_pass():
    agg = _build_agg(episode_count=3, id_count=0, lineage_status=LineageStatus.UNKNOWN)
    assert agg.lineage_status is LineageStatus.UNKNOWN


def test_lineage_unknown_1_of_3_fail():
    with pytest.raises(CanonicalRecordValidationError):
        _build_agg(episode_count=3, id_count=1, lineage_status=LineageStatus.UNKNOWN)


def test_lineage_episode_count_zero_unknown_allowed():
    agg = _build_agg(episode_count=0, id_count=0, lineage_status=LineageStatus.UNKNOWN)
    assert agg.episode_count == 0


def test_lineage_episode_count_zero_full_rejected():
    with pytest.raises(CanonicalRecordValidationError):
        _build_agg(episode_count=0, id_count=0, lineage_status=LineageStatus.FULL)


def test_lineage_episode_count_zero_partial_rejected():
    with pytest.raises(CanonicalRecordValidationError):
        _build_agg(episode_count=0, id_count=0, lineage_status=LineageStatus.PARTIAL)


def test_lineage_negative_episode_count_rejected():
    with pytest.raises(CanonicalRecordValidationError):
        build_aggregate_record(
            source_namespace="test", hypothesis_id="H", aggregation_scope="cohort", aggregation_window_start="2026-08-03",
            native_id="agg_negative", episode_count=-1, source_episode_ids=(), lineage_status=LineageStatus.UNKNOWN,
        )


def test_lineage_duplicate_source_episode_ids_rejected():
    # A repeated id would inflate coverage without any real additional lineage.
    with pytest.raises(CanonicalRecordValidationError):
        build_aggregate_record(
            source_namespace="test", hypothesis_id="H", aggregation_scope="cohort", aggregation_window_start="2026-08-03",
            native_id="agg_dup", episode_count=2, source_episode_ids=("REC_" + "a" * 20, "REC_" + "a" * 20),
            lineage_status=LineageStatus.FULL,
        )


# =========================================================================
# REAL LEGACY ARTIFACT ROUNDTRIP -- opens actual on-disk files.
# =========================================================================

def test_real_q10_semiconductor_fixed_clock_roundtrip():
    md = _real("reports/evaluation/baseline_samsung_hynix/2026-09-11/q10_forward_validation/q10_forward_validation_report.md").read_text(encoding="utf-8")
    row = re.search(r"^\| samsung \| (-?[\d.]+)% \| ([\d.]+) \| ([\d.]+) \|", md, re.MULTILINE)
    assert row
    gap_pct, price_0900, price_0903 = row.groups()
    # Closure Reset MEDIUM/#14: Q10 Semiconductor and Q10 Index are the
    # SAME experiment (Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION) evaluating
    # two different target cohorts -- distinguished by an explicit
    # hypothesis_id cohort suffix (Option A of Codex's own menu), never by
    # symbol metadata alone.
    episode = build_episode_record(
        source_namespace="q10_lead_market",
        experiment_id="Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION",
        hypothesis_id="Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION:SEMICONDUCTOR",
        observation_type=ObservationType.DAY_SYMBOL, execution_mode=ExecutionMode.DIAGNOSTIC,
        trading_date="2026-09-11", symbol="005930",
        event_ref=build_fixed_clock_event_ref(source_namespace="q10_lead_market", trading_date="2026-09-11", symbol="005930", fixed_clock_label="09:00"),
        entry=EntryObservation(entry_price=float(price_0900), entry_authority=EntryAuthority.FIXED_CLOCK_PRICE),
        checkpoints=(Checkpoint(horizon_label="09:03", horizon_origin=EventOrigin.FIXED_CLOCK,
                                observed_price=float(price_0903), completeness=CheckpointCompleteness.PARTIAL),),
        provenance=Provenance(legacy_program="Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION",
                              source_artifact="q10_forward_validation_report.md"),
        metadata={"q10": {"target": "samsung", "target_kind": "stock", "opening_gap_pct": float(gap_pct)}},
    )
    assert episode.identity.event.identity_kind is IdentityKind.DERIVED
    assert episode.entry.entry_price == float(price_0900)
    assert episode.identity.experiment_id == "Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION"
    assert episode.identity.hypothesis_id == "Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION:SEMICONDUCTOR"


def test_real_q10_index_fixed_clock_roundtrip():
    md = _real("reports/evaluation/baseline_samsung_hynix/2026-09-11/q10_forward_validation/q10_forward_validation_report.md").read_text(encoding="utf-8")
    row = re.search(r"^\| kospi \| (-?[\d.]+)% \| ([\d.]+) \|", md, re.MULTILINE)
    assert row
    gap_pct, price_0900 = row.groups()
    episode = build_episode_record(
        source_namespace="q10_lead_market",
        experiment_id="Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION",
        hypothesis_id="Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION:INDEX",
        observation_type=ObservationType.DAY_SYMBOL, execution_mode=ExecutionMode.DIAGNOSTIC,
        trading_date="2026-09-11", symbol="KOSPI200",
        event_ref=build_fixed_clock_event_ref(source_namespace="q10_lead_market", trading_date="2026-09-11", symbol="KOSPI200", fixed_clock_label="09:00"),
        entry=EntryObservation(entry_price=float(price_0900), entry_authority=EntryAuthority.FIXED_CLOCK_PRICE),
        provenance=Provenance(legacy_program="Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION"),
        metadata={"q10": {"target_kind": "index", "opening_gap_pct": float(gap_pct)}},
    )
    assert episode.symbol == "KOSPI200"
    assert episode.identity.event.identity_kind is IdentityKind.DERIVED
    assert episode.identity.experiment_id == "Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION"
    assert episode.identity.hypothesis_id == "Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION:INDEX"


def test_q10_semiconductor_and_index_share_experiment_but_never_merge_identity():
    semiconductor = build_episode_record(
        source_namespace="q10_lead_market", experiment_id="Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION",
        hypothesis_id="Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION:SEMICONDUCTOR",
        observation_type=ObservationType.DAY_SYMBOL, execution_mode=ExecutionMode.DIAGNOSTIC,
        trading_date="2026-09-11", symbol="005930",
        event_ref=build_fixed_clock_event_ref(source_namespace="q10_lead_market", trading_date="2026-09-11", symbol="005930", fixed_clock_label="09:00"),
    )
    index = build_episode_record(
        source_namespace="q10_lead_market", experiment_id="Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION",
        hypothesis_id="Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION:INDEX",
        observation_type=ObservationType.DAY_SYMBOL, execution_mode=ExecutionMode.DIAGNOSTIC,
        trading_date="2026-09-11", symbol="KOSPI200",
        event_ref=build_fixed_clock_event_ref(source_namespace="q10_lead_market", trading_date="2026-09-11", symbol="KOSPI200", fixed_clock_label="09:00"),
    )
    assert semiconductor.identity.experiment_id == index.identity.experiment_id  # same shared experiment
    assert semiconductor.identity.hypothesis_id != index.identity.hypothesis_id  # distinct target cohorts
    assert semiconductor.identity.evaluation_subject_id != index.identity.evaluation_subject_id
    assert semiconductor.identity.evaluation_record_id != index.identity.evaluation_record_id


def test_real_q10_largecap_baseline_control_roundtrip():
    payload = _load_json("reports/evaluation/baseline_samsung_hynix/2026-09-11/baseline_samsung_hynix_forward_returns.json")
    row = next(r for r in payload["rows"] if r["symbol"] == "005930")
    baseline = row["baseline"]
    cp5 = row["returns"]["+5m"]
    episode = build_episode_record(
        source_namespace="q10_largecap_baseline", hypothesis_id="Q10_LARGECAP_BASELINE_CONTROL",
        observation_type=ObservationType.CANDIDATE, execution_mode=ExecutionMode.DIAGNOSTIC,
        trading_date="2026-09-11", symbol=row["symbol"], native_id=row["baseline_decision_id"],
        entry=EntryObservation(entry_time=baseline["baseline_epoch"], entry_price=baseline["baseline_price"], entry_authority=EntryAuthority.CANDIDATE_PRICE),
        checkpoints=(Checkpoint(horizon_label="+5m", horizon_origin=EventOrigin.CANDIDATE,
                                observed_timestamp=to_epoch_seconds(cp5["observed_ts"]), observed_price=cp5["price"],
                                gross_return=cp5["return_pct"], mfe=cp5["mfe_pct"], mae=cp5["mae_pct"],
                                completeness=CheckpointCompleteness.OBSERVED),),
        provenance=Provenance(legacy_program="Q10_LARGECAP_BASELINE_CONTROL", source_artifact="baseline_samsung_hynix_forward_returns.json"),
    )
    assert episode.identity.event.identity_kind is IdentityKind.NATIVE
    assert episode.identity.event.source_id == row["baseline_decision_id"]
    assert episode.checkpoints[0].gross_return == cp5["return_pct"]
    restored = deserialize_record(serialize_record(episode))
    assert restored == episode


def test_real_q11_opportunity_engine_roundtrip():
    # UEF-1 FINAL CLOSURE PATCH M2/#16-17: strengthened representability
    # proof. The ORIGINAL version of this test only mapped ONE of the
    # real artifact's five forward-checkpoint horizons and never touched
    # stop_price/exit/MFE/MAE at all -- Codex's audit found this
    # insufficient evidence of representability for those load-bearing
    # fields. This version reads every one of them from the real artifact
    # and proves each has a canonical destination. No automatic Q11
    # adapter is added anywhere -- this remains a hand-written,
    # human-reviewed mapping in a test, which is exactly what UEF-1's own
    # representability bar (not UEF-4's full-adapter bar) requires.
    payload = _load_json("reports/evaluation/opportunity_engine_shadow/2026-09-11/opportunity_engine_virtual_trades.json")
    trade = payload["trades"][0]
    assert trade["symbol"] == "009150"

    forward_checkpoints = tuple(
        Checkpoint(
            horizon_label=label, horizon_origin=EventOrigin.SIGNAL,
            observed_timestamp=fwd.get("observed_epoch"),
            observed_price=trade["entry_price"] * (1 + (fwd.get("return_pct") or 0) / 100.0),
            gross_return=fwd.get("return_pct"), net_return=fwd.get("net_return_pct"),
            mfe=fwd.get("mfe_pct"), mae=fwd.get("mae_pct"),
            completeness=CheckpointCompleteness.OBSERVED if fwd.get("status") == "observed" else CheckpointCompleteness.PENDING,
        )
        for label, fwd in trade["forward_returns"].items()
    )
    # trade["exit_epoch"]/["exit_price"]/["gross_return_pct"]/["net_return_pct"]/
    # ["mfe_pct"]/["mae_pct"] describe the ACTUAL EXIT's own realized outcome --
    # a genuinely different anchor (EventOrigin.ACTUAL_EXIT) from the five
    # SIGNAL-anchored forward checkpoints above, exactly the Family-A-vs-
    # Family-B distinction this whole design already names (see
    # unified_evaluation_foundation.md problem statement). No new field is
    # needed: it is representable as one more Checkpoint, differently anchored.
    exit_checkpoint = Checkpoint(
        horizon_label="EXIT", horizon_origin=EventOrigin.ACTUAL_EXIT,
        observed_timestamp=trade["exit_epoch"], observed_price=trade["exit_price"],
        gross_return=trade["gross_return_pct"], net_return=trade["net_return_pct"],
        mfe=trade["mfe_pct"], mae=trade["mae_pct"], completeness=CheckpointCompleteness.OBSERVED,
    )
    episode = build_episode_record(
        source_namespace="q11_opportunity_engine", hypothesis_id="Q11_OPENING_SURGE_MARKET_REVERSAL",
        observation_type=ObservationType.SHADOW_ENTRY, execution_mode=ExecutionMode.SHADOW,
        trading_date="2026-09-11", symbol=trade["symbol"], native_id=trade["trade_id"],
        entry=EntryObservation(entry_time=trade["entry_epoch"], entry_price=trade["entry_price"], entry_authority=EntryAuthority.SIMULATED_FILL),
        exit=ExitObservation(exit_time=trade["exit_epoch"], exit_price=trade["exit_price"],
                             exit_price_authority=EntryAuthority.SIMULATED_FILL, exit_reason=trade["exit_reason"]),
        checkpoints=(exit_checkpoint,) + forward_checkpoints,
        provenance=Provenance(legacy_program="Q11_OPENING_SURGE_MARKET_REVERSAL", source_function="simulate_probe_v0"),
        # stop_price is strategy-specific RISK SETUP context (where the
        # strategy intended to cut the trade), not itself an evaluation
        # OUTCOME -- every outcome that could be computed from it
        # (gross/net/mfe/mae) is already independently present in the
        # artifact and already mapped onto core fields above. It has no
        # bearing on identity, checkpoints, or any UEF-1 validation rule,
        # so strategy-specific metadata is the correct, sufficient
        # canonical destination for it -- not a contract defect.
        metadata={"q11": {"stop_price": trade["stop_price"], "strategy_id": trade["strategy_id"],
                          "entry_signal_id": trade["entry_signal_id"]}},
    )
    assert episode.identity.event.source_id == trade["trade_id"]
    assert episode.symbol == trade["symbol"] == "009150"
    assert episode.exit.exit_time == trade["exit_epoch"]
    assert episode.exit.exit_price == trade["exit_price"]
    assert episode.exit.exit_reason == trade["exit_reason"] == "signal_faded"
    assert episode.metadata["q11"]["stop_price"] == trade["stop_price"]
    # All five real forward horizons are represented, not just one:
    signal_labels = {cp.horizon_label for cp in episode.checkpoints if cp.horizon_origin is EventOrigin.SIGNAL}
    assert signal_labels == set(trade["forward_returns"].keys()) == {"+5m", "+15m", "+30m", "+60m", "EOD"}
    for cp in episode.checkpoints:
        if cp.horizon_origin is EventOrigin.SIGNAL:
            fwd = trade["forward_returns"][cp.horizon_label]
            assert cp.mfe == fwd.get("mfe_pct")
            assert cp.mae == fwd.get("mae_pct")
    # The actual-exit-anchored checkpoint is present and distinct from every
    # signal-anchored one, carrying the trade's own realized MFE/MAE/return:
    exit_anchored = [cp for cp in episode.checkpoints if cp.horizon_origin is EventOrigin.ACTUAL_EXIT]
    assert len(exit_anchored) == 1
    assert exit_anchored[0].mfe == trade["mfe_pct"]
    assert exit_anchored[0].mae == trade["mae_pct"]
    assert exit_anchored[0].gross_return == trade["gross_return_pct"]
    assert exit_anchored[0].net_return == trade["net_return_pct"]
    # Full round-trip survives every field checked above:
    restored = deserialize_record(serialize_record(episode))
    assert restored.exit.exit_price == trade["exit_price"]
    restored_exit_anchored = [cp for cp in restored.checkpoints if cp.horizon_origin is EventOrigin.ACTUAL_EXIT]
    assert restored_exit_anchored[0].mfe == trade["mfe_pct"]


def test_real_q12_dual_horizon_set_preserved():
    # Fix3 H2: import the ACTUAL Q12 source-authority constants (never a
    # hand-copied tuple as truth) and preserve BOTH memberships for every
    # overlapping label as separate Checkpoint entries -- a label that
    # belongs to both sets must appear TWICE (once per horizon_set_id),
    # not once with two labels silently collapsed together.
    from libs.reporting.baseline_btc_woori_tech.contracts import HORIZONS as Q12_HORIZONS, HYPOTHESIS_HORIZONS as Q12_HYPOTHESIS_HORIZONS

    payload = _load_json("reports/evaluation/baseline_btc_woori_tech/2026-09-11/q12_candidate_input.json")
    btc_feature = payload["features"]["btc_0855"]
    checkpoints = tuple(
        Checkpoint(horizon_label=label, horizon_origin=EventOrigin.CANDIDATE, horizon_set_id="q12_main",
                  completeness=CheckpointCompleteness.PENDING)
        for label in Q12_HORIZONS
    ) + tuple(
        Checkpoint(horizon_label=label, horizon_origin=EventOrigin.CANDIDATE, horizon_set_id="q12_hypothesis",
                  completeness=CheckpointCompleteness.PENDING)
        for label in Q12_HYPOTHESIS_HORIZONS
    )
    episode = build_episode_record(
        source_namespace="q12_btc_woori", hypothesis_id="Q12_BTC_WOORI_TECH_BASELINE",
        observation_type=ObservationType.CANDIDATE, execution_mode=ExecutionMode.DIAGNOSTIC,
        trading_date=payload["day"], symbol="BTC-WOORI",
        derived_fields={
            "trading_date": DerivedIdentityPart(kind=DerivedFieldKind.TRADING_DATE, value=payload["day"]),
            "symbol": DerivedIdentityPart(kind=DerivedFieldKind.SYMBOL, value="BTC-WOORI"),
            "target_epoch": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value=btc_feature["target_epoch"]),
        },
        checkpoints=checkpoints,
        provenance=Provenance(legacy_program="Q12_BTC_WOORI_TECH_BASELINE", source_artifact="q12_candidate_input.json"),
        metadata={"q12": {"btc_return_24h_pct": btc_feature["return_24h_pct"]}},
    )
    main_labels = {cp.horizon_label for cp in episode.checkpoints if cp.horizon_set_id == "q12_main"}
    hyp_labels = {cp.horizon_label for cp in episode.checkpoints if cp.horizon_set_id == "q12_hypothesis"}
    # Full membership of BOTH real source sets, exactly as authored upstream:
    assert main_labels == set(Q12_HORIZONS)
    assert hyp_labels == set(Q12_HYPOTHESIS_HORIZONS)
    # Every overlapping label has independent membership in both sets:
    for label in ("+5m", "+15m", "+30m", "EOD"):
        assert label in main_labels and label in hyp_labels
    # +60m belongs ONLY to the hypothesis set, per the real source constant:
    assert "+60m" in hyp_labels and "+60m" not in main_labels
    # Total checkpoint count is the sum of both real sets' lengths -- no
    # accidental de-duplication of the overlapping labels occurred.
    assert len(episode.checkpoints) == len(Q12_HORIZONS) + len(Q12_HYPOTHESIS_HORIZONS)


def test_real_opening_submission_is_not_a_fill():
    # Fix2 #29: a bare submission record (no confirmed fill evidence in
    # this specific artifact) must use SUBMITTED_INTENT, never MOCK_FILL.
    payload = _load_json("data/logs/opening_rank1_controlled_probe/2026-09-10/probe_submissions.json")
    submission = payload["submissions"][0]
    submission_episode = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date=payload["day"], symbol=submission["symbol"], native_id=submission["run_id"],
        entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT),  # NOT MOCK_FILL: no confirmed fill here
        provenance=Provenance(legacy_program="opening_rank1_controlled_probe", source_artifact="probe_submissions.json"),
        metadata={"opening": {"opening_alpha_condition": submission["opening_alpha_condition"]["condition"]}},
    )
    assert submission_episode.entry.entry_authority is EntryAuthority.SUBMITTED_INTENT
    assert submission_episode.entry.entry_price is None  # no fill price exists in this artifact -- none fabricated

    # The SAME real-world event's actual confirmed fill lives in a SEPARATE
    # artifact (trade_read_model.json) -- represented as a genuinely
    # different EpisodeRecord with MOCK_FILL and a real fill price.
    trade_model = _load_trade_read_model("2026-09-10", "TRD_20260910_024060_01")
    fill_episode = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.ACTUAL_TRADE, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date=payload["day"], symbol=submission["symbol"], native_id="TRD_20260910_024060_01",
        entry=EntryObservation(entry_time=to_epoch_seconds(trade_model["entry"]["timestamp"]),
                               entry_price=trade_model["entry"]["price"], entry_authority=EntryAuthority.MOCK_FILL),
        provenance=Provenance(legacy_program="opening_rank1_controlled_probe", source_artifact="trade_read_model.json"),
        source_run_id=trade_model["selection"]["strategist_run_id"],
    )
    assert fill_episode.entry.entry_authority is EntryAuthority.MOCK_FILL
    assert fill_episode.entry.entry_price == 13340.0  # the real confirmed fill price
    assert submission_episode.entry.entry_authority != fill_episode.entry.entry_authority
    assert submission_episode.identity.event.canonical_event_id != fill_episode.identity.event.canonical_event_id

    # Fix3 M4: the two genuinely distinct records are now explicitly
    # linked -- a fact about their relationship, never a merge of
    # identity. The link points forward to the fill's own record id.
    linked_submission = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date=payload["day"], symbol=submission["symbol"], native_id=submission["run_id"],
        entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT),
        related_records=(RecordLink(
            relation_type="SUBMISSION_TO_FILL", target_record_id=fill_episode.identity.evaluation_record_id,
            provenance="same real-world 2026-09-10 024060 probe event",
        ),),
        provenance=Provenance(legacy_program="opening_rank1_controlled_probe", source_artifact="probe_submissions.json"),
        source_run_id=submission["run_id"],
    )
    assert linked_submission.related_records[0].relation_type == "SUBMISSION_TO_FILL"
    assert linked_submission.related_records[0].target_record_id == fill_episode.identity.evaluation_record_id
    assert linked_submission.identity.evaluation_record_id != fill_episode.identity.evaluation_record_id  # link never merges identity
    restored = deserialize_record(serialize_record(linked_submission))
    assert restored.related_records[0].target_record_id == fill_episode.identity.evaluation_record_id


def test_record_link_rejects_unknown_relation_type():
    with pytest.raises(CanonicalRecordValidationError):
        RecordLink(relation_type="MADE_UP_RELATION", target_record_id="REC_" + "a" * 20)


def test_record_link_allowed_types_is_the_single_source_of_truth():
    assert ALLOWED_RECORD_RELATION_TYPES == frozenset({"SUBMISSION_TO_FILL"})


# =========================================================================
# Closure Reset Group B: collection-level REFERENTIAL validation
# (relations.py::validate_record_links) -- real 2026-09-10 024060
# submission/fill pair, plus every negative case item 7 specifies.
# =========================================================================

def _real_opening_submission_and_fill():
    # UEF-1 FINAL CLOSURE PATCH H3: both episodes now carry the REAL,
    # verified shared native provenance -- probe_submissions.json's
    # submissions[0].run_id and trade_read_model.json's
    # selection.strategist_run_id are, in this real artifact pair, the
    # SAME value. Nothing is invented: this assertion is the actual
    # inventory step item 8 asked for.
    payload = _load_json("data/logs/opening_rank1_controlled_probe/2026-09-10/probe_submissions.json")
    submission = payload["submissions"][0]
    trade_model = _load_trade_read_model("2026-09-10", "TRD_20260910_024060_01")
    shared_run_id = submission["run_id"]
    assert trade_model["selection"]["strategist_run_id"] == shared_run_id
    fill_episode = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.ACTUAL_TRADE, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date=payload["day"], symbol=submission["symbol"], native_id="TRD_20260910_024060_01",
        entry=EntryObservation(entry_time=to_epoch_seconds(trade_model["entry"]["timestamp"]),
                               entry_price=trade_model["entry"]["price"], entry_authority=EntryAuthority.MOCK_FILL),
        source_run_id=shared_run_id,
    )
    submission_episode = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date=payload["day"], symbol=submission["symbol"], native_id=submission["run_id"],
        entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT),
        related_records=(RecordLink(relation_type="SUBMISSION_TO_FILL", target_record_id=fill_episode.identity.evaluation_record_id),),
        source_run_id=shared_run_id,
    )
    return submission_episode, fill_episode


def test_real_valid_submission_to_fill_relation_passes_referential_validation():
    submission_episode, fill_episode = _real_opening_submission_and_fill()
    validate_record_links([submission_episode, fill_episode])  # must not raise


def test_referential_validation_fails_when_target_does_not_exist():
    submission_episode, fill_episode = _real_opening_submission_and_fill()
    with pytest.raises(RecordRelationValidationError):
        validate_record_links([submission_episode])  # fill_episode deliberately NOT provided


def test_referential_validation_fails_when_target_is_another_submission():
    submission_episode, fill_episode = _real_opening_submission_and_fill()
    other_submission = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date="2026-09-10", symbol=submission_episode.symbol, native_id="another_run_id",
        entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT),
    )
    bad_submission = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date="2026-09-10", symbol=submission_episode.symbol, native_id="yet_another_run_id",
        entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT),
        related_records=(RecordLink(relation_type="SUBMISSION_TO_FILL", target_record_id=other_submission.identity.evaluation_record_id),),
    )
    with pytest.raises(RecordRelationValidationError):
        validate_record_links([bad_submission, other_submission])  # target has no fill evidence -- it's a submission too


def test_referential_validation_fails_when_target_has_no_fill_evidence():
    submission_episode, fill_episode = _real_opening_submission_and_fill()
    observation_only_target = build_episode_record(
        source_namespace="opening_rank1_shadow", hypothesis_id="OPEN_0_20_RANK1_30M",
        observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.OBSERVATION_ONLY,
        trading_date="2026-09-10", symbol=submission_episode.symbol, native_id="observation_only_row",
    )
    bad_submission = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date="2026-09-10", symbol=submission_episode.symbol, native_id="run_without_fill_target",
        entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT),
        related_records=(RecordLink(relation_type="SUBMISSION_TO_FILL", target_record_id=observation_only_target.identity.evaluation_record_id),),
    )
    with pytest.raises(RecordRelationValidationError):
        validate_record_links([bad_submission, observation_only_target])


def test_referential_validation_fails_when_target_is_different_symbol():
    submission_episode, fill_episode = _real_opening_submission_and_fill()
    different_symbol_fill = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.ACTUAL_TRADE, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date="2026-09-10", symbol="005930", native_id="TRD_different_symbol",
        entry=EntryObservation(entry_time=1789002000, entry_price=100.0, entry_authority=EntryAuthority.MOCK_FILL),
    )
    bad_submission = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date="2026-09-10", symbol=submission_episode.symbol, native_id="run_mismatched_symbol",
        entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT),
        related_records=(RecordLink(relation_type="SUBMISSION_TO_FILL", target_record_id=different_symbol_fill.identity.evaluation_record_id),),
    )
    assert bad_submission.symbol != different_symbol_fill.symbol
    with pytest.raises(RecordRelationValidationError):
        validate_record_links([bad_submission, different_symbol_fill])


def test_referential_validation_fails_when_target_is_different_trading_date():
    submission_episode, fill_episode = _real_opening_submission_and_fill()
    different_day_fill = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.ACTUAL_TRADE, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date="2026-09-09", symbol=submission_episode.symbol, native_id="TRD_different_day",
        entry=EntryObservation(entry_time=1788915600, entry_price=100.0, entry_authority=EntryAuthority.MOCK_FILL),
    )
    bad_submission = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date="2026-09-10", symbol=submission_episode.symbol, native_id="run_mismatched_day",
        entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT),
        related_records=(RecordLink(relation_type="SUBMISSION_TO_FILL", target_record_id=different_day_fill.identity.evaluation_record_id),),
    )
    with pytest.raises(RecordRelationValidationError):
        validate_record_links([bad_submission, different_day_fill])


def test_referential_validation_fails_when_run_id_does_not_match():
    # UEF-1 FINAL CLOSURE PATCH H3/item 11: same symbol + same trading_date
    # is NOT enough -- an unrelated fill for the same stock on the same day
    # must not satisfy SUBMISSION_TO_FILL just because symbol/date line up.
    # This is the exact gap Codex's audit required closed.
    submission_episode, fill_episode = _real_opening_submission_and_fill()
    unrelated_fill = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.ACTUAL_TRADE, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date=submission_episode.trading_date, symbol=submission_episode.symbol, native_id="TRD_unrelated_same_day",
        entry=EntryObservation(entry_time=1789002000, entry_price=999.0, entry_authority=EntryAuthority.MOCK_FILL),
        source_run_id="totally_unrelated_run_id",
    )
    bad_submission = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date=submission_episode.trading_date, symbol=submission_episode.symbol, native_id="run_id_that_does_not_match_the_fill",
        entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT),
        related_records=(RecordLink(relation_type="SUBMISSION_TO_FILL", target_record_id=unrelated_fill.identity.evaluation_record_id),),
        source_run_id="run_id_that_does_not_match_the_fill",
    )
    assert bad_submission.symbol == unrelated_fill.symbol
    assert bad_submission.trading_date == unrelated_fill.trading_date
    with pytest.raises(RecordRelationValidationError):
        validate_record_links([bad_submission, unrelated_fill])


def test_referential_validation_fails_when_source_run_id_is_missing_entirely():
    # Same symbol/date/fill-evidence as the real valid case, but neither
    # side declares source_run_id at all -- must still fail, not silently
    # pass on symbol/date alone.
    submission_episode, _fill_episode = _real_opening_submission_and_fill()
    fill_without_provenance = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.ACTUAL_TRADE, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date=submission_episode.trading_date, symbol=submission_episode.symbol, native_id="TRD_no_provenance",
        entry=EntryObservation(entry_time=1789002000, entry_price=999.0, entry_authority=EntryAuthority.MOCK_FILL),
    )
    submission_without_provenance = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date=submission_episode.trading_date, symbol=submission_episode.symbol, native_id="submission_no_provenance",
        entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT),
        related_records=(RecordLink(relation_type="SUBMISSION_TO_FILL", target_record_id=fill_without_provenance.identity.evaluation_record_id),),
    )
    with pytest.raises(RecordRelationValidationError):
        validate_record_links([submission_without_provenance, fill_without_provenance])


def test_validate_record_links_rejects_duplicate_evaluation_record_id():
    # M1: two independently-built EpisodeRecord objects that happen to
    # carry the SAME evaluation_record_id (identical identity inputs) must
    # not silently overwrite each other in the collection index -- that
    # would let referential validation pick whichever happened to be
    # indexed last and hide the duplicate entirely.
    submission_episode, fill_episode = _real_opening_submission_and_fill()
    duplicate_of_fill = build_episode_record(
        source_namespace="opening_rank1_controlled_probe",
        hypothesis_id=fill_episode.identity.hypothesis_id,
        observation_type=fill_episode.observation_type, execution_mode=fill_episode.execution_mode,
        trading_date=fill_episode.trading_date, symbol=fill_episode.symbol,
        native_id=fill_episode.identity.event.source_id,
        entry=fill_episode.entry,
    )
    assert duplicate_of_fill.identity.evaluation_record_id == fill_episode.identity.evaluation_record_id
    with pytest.raises(RecordRelationValidationError):
        validate_record_links([fill_episode, duplicate_of_fill, submission_episode])


# =========================================================================
# UEF-1 FINAL CLOSURE PATCH M3/items 18-21: native identity collision
# boundary check (validate_native_event_identity_consistency). Deliberately
# scoped to detecting a collision WITHIN one given collection -- verifying
# a real legacy source's native id actually has this property at scale is
# UEF-4's job, not UEF-1's (see the phase boundary table + "CURRENT
# AUTHORITATIVE UEF-1 IDENTITY MODEL" section in
# unified_evaluation_foundation.md).
# =========================================================================

def test_validate_native_event_identity_consistency_detects_collision():
    episode_a = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date="2026-09-10", symbol="024060", native_id="shared_native_id_collision",
        entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT),
    )
    episode_b = build_episode_record(
        source_namespace="opening_rank1_controlled_probe", hypothesis_id="CONFIRMED_RECURRENT_RANK",
        observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
        trading_date="2026-09-10", symbol="005930", native_id="shared_native_id_collision",
        entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT),
    )
    with pytest.raises(RecordRelationValidationError):
        validate_native_event_identity_consistency([episode_a, episode_b])


def test_validate_native_event_identity_consistency_allows_same_id_same_fact():
    # The SAME native id reused for the SAME symbol/trading_date fact
    # across two different hypotheses is LEGITIMATE_MULTI_HYPOTHESIS, not a
    # collision -- must NOT raise.
    episode_a = build_episode_record(
        source_namespace="opening_rank1_shadow", hypothesis_id="IMMEDIATE_OPENING_PROBE",
        observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.OBSERVATION_ONLY,
        trading_date="2026-09-10", symbol="024060", native_id="shared_native_id_legit",
    )
    episode_b = build_episode_record(
        source_namespace="opening_rank1_shadow", hypothesis_id="CONFIRMED_RECURRENT_RANK",
        observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.OBSERVATION_ONLY,
        trading_date="2026-09-10", symbol="024060", native_id="shared_native_id_legit",
    )
    validate_native_event_identity_consistency([episode_a, episode_b])  # must not raise


def test_validate_native_event_identity_consistency_covers_pair_sides():
    left = PairSide(event=build_event_ref(source_namespace="strategist_stage2", native_id="shared_native_id_pair"),
                    symbol="005930", observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC)
    right = PairSide(event=build_event_ref(source_namespace="strategist_stage2", native_id="shared_native_id_pair"),
                     symbol="000660", observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC)
    pair = build_pair_record(source_namespace="strategist_stage2", hypothesis_id="H", pair_type="before_after",
                             trading_date="2026-09-11", left=left, right=right, native_id="pair_native_for_collision_test")
    with pytest.raises(RecordRelationValidationError):
        validate_native_event_identity_consistency([pair])


def test_record_link_structural_self_reference_rejected_before_referential_check_even_runs():
    # A link cannot target its own record -- caught structurally at
    # EpisodeRecord construction time, never reaching the collection-level
    # validator at all.
    with pytest.raises(CanonicalRecordValidationError):
        submission_episode, _ = _real_opening_submission_and_fill()
        self_id = submission_episode.identity.evaluation_record_id
        build_episode_record(
            source_namespace="opening_rank1_controlled_probe", hypothesis_id="IMMEDIATE_OPENING_PROBE",
            observation_type=ObservationType.CONTROLLED_ENTRY, execution_mode=ExecutionMode.CONTROLLED_MOCK,
            trading_date="2026-09-10", symbol=submission_episode.symbol, native_id=submission_episode.identity.event.source_id,
            entry=EntryObservation(entry_authority=EntryAuthority.SUBMITTED_INTENT),
            related_records=(RecordLink(relation_type="SUBMISSION_TO_FILL", target_record_id=self_id),),
        )


def test_real_opening_rank1_shadow_roundtrip():
    payload = _load_json("reports/evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.json")
    real_episode = next(e for e in payload["episodes"] if e.get("day") == "2026-09-11")
    episode = build_episode_record(
        source_namespace="opening_rank1_shadow", hypothesis_id="OPEN_0_20_RANK1_30M",
        observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.OBSERVATION_ONLY,
        trading_date=real_episode["day"], symbol=real_episode["symbol"], native_id=real_episode["episode_id"],
        entry=EntryObservation(entry_time=real_episode.get("baseline_epoch"), entry_price=real_episode.get("baseline_price"),
                               entry_authority=EntryAuthority.SCANNER_REFERENCE),
        provenance=Provenance(legacy_program="OPEN_0_20_RANK1_30M", source_artifact="opening_rank1_shadow_cumulative.json"),
        metadata={"opening": {"rank": real_episode.get("rank")}},
    )
    assert episode.identity.event.identity_kind is IdentityKind.NATIVE
    assert episode.identity.event.source_id == real_episode["episode_id"]
    assert episode.symbol == real_episode["symbol"]


def test_real_strategist_stage2_pair_native_pair_derived_sides_different_symbols():
    # Fix3 H3: the real source artifact has exactly ONE native id for the
    # whole refresh comparison (decision_id) -- it has NO separate native
    # id for "the before candidate" or "the after candidate" individually.
    # Fabricating "{decision_id}:before" and calling it NATIVE violates
    # source-native provenance. The pair's OWN event is NATIVE (decision_id
    # really is the source's own stable id for this comparison); each
    # SIDE's event is honestly DERIVED (decision_id + side, canonicalized).
    payload = _load_json("reports/evaluation/agent_effectiveness/2026-09-11/strategist_stage2_authority_review.json")
    record = next(r for r in payload["records"] if r.get("before_symbol") and r.get("after_symbol") and r["before_symbol"] != r["after_symbol"])

    pair_event = build_event_ref(source_namespace="strategist_stage2", native_id=record["decision_id"])
    left_event = build_derived_event_ref(
        source_namespace="strategist_stage2", trading_date=record["day"], symbol=record["before_symbol"],
        extra_fields={"decision_id": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value=record["decision_id"]),
                      "side": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value="before")},
    )
    right_event = build_derived_event_ref(
        source_namespace="strategist_stage2", trading_date=record["day"], symbol=record["after_symbol"],
        extra_fields={"decision_id": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value=record["decision_id"]),
                      "side": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value="after")},
    )
    assert pair_event.identity_kind is IdentityKind.NATIVE
    assert pair_event.source_id == record["decision_id"]
    assert left_event.identity_kind is IdentityKind.DERIVED
    assert right_event.identity_kind is IdentityKind.DERIVED

    left = PairSide(event=left_event, symbol=record["before_symbol"], observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC,
                    entry=EntryObservation(entry_time=record.get("decision_epoch"), entry_authority=EntryAuthority.SCANNER_REFERENCE))
    right = PairSide(event=right_event, symbol=record["after_symbol"], observation_type=ObservationType.RANK_EVENT, execution_mode=ExecutionMode.DIAGNOSTIC,
                     entry=EntryObservation(entry_time=record.get("decision_epoch"), entry_authority=EntryAuthority.SCANNER_REFERENCE))
    pair = build_pair_record(
        source_namespace="strategist_stage2", hypothesis_id="STRATEGIST_STAGE2_REFRESH_AUTHORITY_V1",
        pair_type="refresh_before_after", trading_date=record["day"], left=left, right=right,
        native_id=record["decision_id"], delta_value=record.get("delta_pct"), delta_horizon="+30m",
        provenance=Provenance(legacy_program="STRATEGIST_STAGE2_REFRESH_AUTHORITY_V1"),
        metadata={"stage2": {"run_id": record.get("run_id"), "decision_id": record["decision_id"], "selected_symbol_decision": record.get("selected_symbol_decision")}},
    )
    assert pair.left.symbol == record["before_symbol"]
    assert pair.right.symbol == record["after_symbol"]
    assert pair.identity.left_event.identity_kind is IdentityKind.DERIVED
    assert pair.identity.right_event.identity_kind is IdentityKind.DERIVED
    assert pair.identity.left_event.canonical_event_id != pair.identity.right_event.canonical_event_id
    assert pair.identity.pair_event.identity_kind is IdentityKind.NATIVE
    assert pair.identity.pair_event.source_id == record["decision_id"]
    # both sides' derived identity is keyed off the SAME real decision_id
    # (carried explicitly in metadata, since a DERIVED source_id is itself
    # a hash and cannot literally contain the raw decision_id string):
    assert pair.metadata["stage2"]["decision_id"] == record["decision_id"]
    restored = deserialize_record(serialize_record(pair))
    assert restored == pair


def test_real_no_trade_attribution_day_level_is_aggregate():
    payload = _load_json("reports/evaluation/daily/2026-09-11/no_trade_attribution_report.json")
    q11_block = payload["q11_opening_opportunity"]
    agg = build_aggregate_record(
        source_namespace="no_trade_attribution", hypothesis_id="no_trade_attribution",
        aggregation_scope="day", aggregation_window_start=payload["day"],
        native_id=f"no_trade:{payload['day']}",
        episode_count=int(q11_block.get("virtual_trades") or 0),
        lineage_status=LineageStatus.UNKNOWN,  # the legacy artifact never carried per-episode ids
        metrics={"no_trade_class": payload["no_trade_class"], "q11_avg_net_return_pct": q11_block.get("avg_net_return_pct")},
        provenance=Provenance(legacy_program="no_trade_attribution_report"),
    )
    assert agg.metrics["no_trade_class"] == payload["no_trade_class"] == "FILTERING_REVIEW_REQUIRED"
    assert agg.symbol == ""


def test_real_horizon_exit_evaluation_exit_semantics_preserved():
    payload = _load_json("reports/evaluation/daily/2026-09-09/horizon_compliance_report.json")
    row = payload["rows"][0]
    trade_model = _load_trade_read_model("2026-09-09", row["trade_id"])
    entry_epoch = to_epoch_seconds(trade_model["entry"]["timestamp"])
    exit_epoch = to_epoch_seconds(trade_model["exit"]["timestamp"])
    episode = build_episode_record(
        source_namespace="horizon_exit_evaluation", hypothesis_id="horizon_exit_evaluation",
        observation_type=ObservationType.ACTUAL_TRADE, execution_mode=ExecutionMode.BROKER_LIVE,
        trading_date="2026-09-09", symbol=row["symbol"], native_id=row["trade_id"],
        entry=EntryObservation(entry_time=entry_epoch, entry_price=trade_model["entry"]["price"], entry_authority=EntryAuthority.BROKER_FILL),
        exit=ExitObservation(exit_time=exit_epoch, exit_price=trade_model["exit"]["price"],
                             exit_price_authority=EntryAuthority.BROKER_FILL, exit_reason=trade_model["exit"].get("reason", "")),
        checkpoints=(Checkpoint(horizon_label="target", horizon_origin=EventOrigin.ACTUAL_EXIT,
                                observed_timestamp=exit_epoch, observed_price=trade_model["exit"]["price"],
                                net_return=row.get("net_return_pct"), completeness=CheckpointCompleteness.OBSERVED,
                                source="post_exit_shadow_recap"),),
        cost=EvaluationCost(cost_profile_id="", applied_cost=None),  # Family B carries no cost model of its own
        provenance=Provenance(legacy_program="horizon_compliance_report", source_function="evaluate_horizon_contract"),
        metadata={"horizon_exit": {"strategy_horizon": row.get("strategy_horizon"), "bucket": row.get("bucket")}},
    )
    assert episode.exit is not None
    assert episode.exit.exit_price == trade_model["exit"]["price"]
    assert episode.exit.exit_reason == trade_model["exit"]["reason"]
    assert episode.cost.applied_cost is None
    restored = deserialize_record(serialize_record(episode))
    assert restored.exit.exit_reason == episode.exit.exit_reason


def test_real_q13_q14_aggregate_not_trade_shaped():
    q13_payload = _load_json("reports/evaluation/daily/2026-09-11/attribution_score_v0.json")
    axis = q13_payload["scores"]["entry_timing_score"]
    q13_agg = build_aggregate_record(
        source_namespace="q13_attribution_score", hypothesis_id="Q13_ATTRIBUTION_SCORE_V0",
        aggregation_scope="day", aggregation_window_start=q13_payload["day"],
        native_id=f"q13:{q13_payload['day']}", lineage_status=LineageStatus.UNKNOWN,
        metrics={"entry_timing_score_status": axis["status"], "entry_timing_score": axis.get("score")},
        provenance=Provenance(legacy_program="Q13_ATTRIBUTION_SCORE_V0"),
    )
    assert q13_agg.RECORD_KIND.value == "AGGREGATE"
    assert q13_agg.metrics["entry_timing_score_status"] == "INSUFFICIENT_EVIDENCE"

    q14_payload = _load_json("reports/evaluation/daily/2026-09-10/scanner_alignment_root_cause_report.json")
    row = q14_payload["rows"][0]
    q14_agg = build_aggregate_record(
        source_namespace="q14_scanner_alignment", hypothesis_id="Q14_SCANNER_ALIGNMENT_ROOT_CAUSE",
        aggregation_scope="day", aggregation_window_start="2026-09-10",
        native_id=f"q14:{row['trade_id']}", lineage_status=LineageStatus.UNKNOWN,
        metrics={"root_cause": row["root_cause"], "net_return_pct": row.get("net_return_pct")},
        provenance=Provenance(legacy_program="Q14_SCANNER_ALIGNMENT_ROOT_CAUSE"),
    )
    assert q14_agg.RECORD_KIND.value == "AGGREGATE"
    assert q14_agg.metrics["root_cause"] == "Aligned / No Alignment Issue"


def test_real_alpha_board_candidate_aggregate_lineage_unknown_honestly_reported():
    payload = _load_json("reports/evaluation/alpha_research_board/2026-09-11/alpha_research_board.json")
    row = next(r for r in payload["candidates"] if r["candidate_id"] == "IMMEDIATE_OPENING_PROBE")
    prospective = row.get("prospective_evidence") or row.get("net_metrics") or {}
    agg = build_aggregate_record(
        source_namespace="alpha_research_board", hypothesis_id=row["candidate_id"],
        aggregation_scope="cohort", aggregation_window_start="2026-08-03", aggregation_window_end="2026-09-11",
        native_id=row["candidate_id"],
        episode_count=int(prospective.get("sample_count") or 0),
        lineage_status=LineageStatus.UNKNOWN,  # honestly reported: the Board artifact carries no per-episode ids
        metric_semantics="LEGACY_SOURCE",
        metrics=dict(prospective),
        provenance=Provenance(legacy_program=row["candidate_id"], source_artifact="alpha_research_board.json"),
    )
    assert agg.lineage_status is LineageStatus.UNKNOWN
    assert agg.metric_semantics == "LEGACY_SOURCE"
    assert agg.identity.hypothesis_id == "IMMEDIATE_OPENING_PROBE"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
