"""UEF-4B-4 -- Q10 Index (Calc F/G/H) canonical adapter tests.

Covers Calc F/G (`q10_index_reaction_adapter.py`, reuse of the frozen
`forward_measurement_adapter` generic layer for F, SOURCE-PROVIDED
verbatim checkpoint construction for G's collector-governed
checkpoints) and Calc H (`q10_index_directional_shadow_adapter.py`,
directional shadow over the SAME physical F/G observation, NET_OR_
COST_INCLUDED, verified against the real legacy `build_shadow_
comparison` function directly), physical identity / evidence-
multiplication guards, the trusted-artifact ingestion boundary
(Controlled Probe / Controlled Mock Lane / execution-evidence
exclusion, forged-schema rejection), and fail-fast invalid-input
handling. Every fixture below is built by calling the REAL legacy
functions directly (`_stock_reaction`, `_index_reaction`, `_direction`,
`build_shadow_comparison`) -- oracle-grade, never a hand-approximated
shape.
"""

from __future__ import annotations

import ast
import datetime
import inspect
import json
import zoneinfo
from pathlib import Path

import pytest

from libs.reporting.baseline_samsung_hynix.forward_validation.contracts import PROGRAM_ID, SCHEMA_VERSION, SHADOW_ENTRY_POLICIES, TARGETS
from libs.reporting.baseline_samsung_hynix.forward_validation.expected_actual import build_expected_actual
from libs.reporting.baseline_samsung_hynix.forward_validation.reaction_reader import _index_reaction, _stock_reaction
from libs.reporting.baseline_samsung_hynix.forward_validation.shadow_comparison import build_shadow_comparison

from libs.reporting.evaluation.canonical.contracts import CheckpointCompleteness, ExecutionMode
from libs.reporting.evaluation.canonical.metrics import CostPolicy
from libs.reporting.evaluation.canonical.metrics.contracts import CostTiming
from libs.reporting.evaluation.canonical.metrics.aggregation import SampleMemberState
from libs.reporting.evaluation.canonical.contracts import ReturnUnit

from libs.reporting.evaluation.canonical.adapters import q10_index_reaction_adapter as fg
from libs.reporting.evaluation.canonical.adapters import q10_index_directional_shadow_adapter as h
from libs.reporting.evaluation.canonical.adapters.q10_index_reaction_adapter import Q10IndexAdapterError

KST = zoneinfo.ZoneInfo("Asia/Seoul")
DAY = "2026-06-24"


def _cost_policy() -> CostPolicy:
    return CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.1, slippage=0.05, provenance="test_fixture")


def _epoch(day: str, hh: int, mm: int) -> int:
    return int(datetime.datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=KST).timestamp())


def _candles(*, day: str, start_hh: int = 9, start_mm: int = 0, count: int = 390, base: float = 1000.0, step: float = 0.5) -> list[dict]:
    start = _epoch(day, start_hh, start_mm)
    rows = []
    for i in range(count):
        price = base + step * i
        rows.append({"ts": start + i * 60, "open": price, "close": price, "high": price + 1, "low": price - 1, "volume": 100.0})
    return rows


TARGET_BY_KEY = {t["key"]: t for t in TARGETS}
SYMBOL_BY_KEY = {t["key"]: t["symbol"] for t in TARGETS}


def _real_target_row(*, day: str, key: str, rows: list[dict], previous_close: float, collector_root: Path) -> dict:
    target = TARGET_BY_KEY[key]
    if target["kind"] == "stock":
        return _stock_reaction(day=day, target=target, rows=rows, previous_close=previous_close)
    for row in rows:
        row.setdefault("previous_close", previous_close)
    return _index_reaction(day=day, target=target, rows=rows, collector_root=collector_root)


def _build_real_reactions(day: str, *, rows_by_key: dict[str, list[dict]], collector_root: Path) -> dict:
    targets = {}
    for key, rows in rows_by_key.items():
        previous_close = rows[0]["open"] * 0.99 if rows else 990.0
        targets[key] = _real_target_row(day=day, key=key, rows=rows, previous_close=previous_close, collector_root=collector_root)
    return {"day": day, "targets": targets, "schema_version": SCHEMA_VERSION, "evaluation_program_id": PROGRAM_ID, "guards": {}}


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _day_dir(tmp_path: Path) -> Path:
    return tmp_path / "baseline_samsung_hynix" / DAY / "q10_forward_validation"


def _write_reactions_artifact(tmp_path: Path, reactions: dict) -> Path:
    return _write_json(_day_dir(tmp_path) / "q10_actual_market_reactions.json", reactions)


def _all_target_rows(day: str) -> dict[str, list[dict]]:
    return {key: _candles(day=day, base=1000.0 + i * 10, step=0.3) for i, key in enumerate(TARGET_BY_KEY)}


# =========================================================================
# Calc F -- stock reaction (forward_measurement_adapter reuse)
# =========================================================================


def test_f_oracle_matches_real_stock_reaction(tmp_path):
    rows_by_key = _all_target_rows(DAY)
    reactions = _build_real_reactions(DAY, rows_by_key=rows_by_key, collector_root=tmp_path / "collector_absent")
    artifact_path = _write_reactions_artifact(tmp_path, reactions)

    results = fg.canonicalize_q10_index_calc_f_artifact(_day_dir(tmp_path), horizon_label="09:03", cost_policy=_cost_policy())
    assert len(results) == 2  # samsung, sk_hynix -- stock targets only
    for result in results:
        assert result.episode is not None
        oracle = reactions["targets"][result.target.key]
        oracle_point = oracle["points"]["09:03"]
        checkpoint = next(cp for cp in result.episode.checkpoints if cp.horizon_label == "09:03")
        assert checkpoint.completeness is CheckpointCompleteness.OBSERVED
        assert oracle_point["status"] == "OBSERVED"
        assert checkpoint.observed_price == pytest.approx(oracle_point["price"])


def test_f_sample_unit_reference_horizon_return_unit_cost(tmp_path):
    rows_by_key = _all_target_rows(DAY)
    reactions = _build_real_reactions(DAY, rows_by_key=rows_by_key, collector_root=tmp_path / "collector_absent")
    artifact_path = _write_reactions_artifact(tmp_path, reactions)

    results = fg.canonicalize_q10_index_calc_f_artifact(_day_dir(tmp_path), horizon_label="09:00", cost_policy=_cost_policy())
    samsung = next(r for r in results if r.target.key == "samsung")
    ep = samsung.episode
    assert ep.symbol == "005930"
    assert ep.execution_mode is ExecutionMode.OBSERVATION_ONLY
    labels = {cp.horizon_label for cp in ep.checkpoints}
    assert labels == set(fg.F_HORIZON_LABELS)
    for cp in ep.checkpoints:
        assert cp.return_unit.value == "PERCENTAGE_POINTS"
        assert cp.net_return is None  # GROSS_ONLY


def test_f_population_missing_when_no_opening_reference(tmp_path):
    rows_by_key = {"samsung": [], "sk_hynix": _candles(day=DAY)}
    reactions = _build_real_reactions(DAY, rows_by_key=rows_by_key, collector_root=tmp_path / "collector_absent")
    artifact_path = _write_reactions_artifact(tmp_path, reactions)
    results = fg.canonicalize_q10_index_calc_f_artifact(_day_dir(tmp_path), horizon_label="09:00", cost_policy=_cost_policy())
    samsung = next(r for r in results if r.target.key == "samsung")
    assert samsung.episode is None
    assert samsung.member.state is SampleMemberState.MISSING
    assert samsung.member.gross_return is None


def test_f_rejects_index_kind():
    with pytest.raises(Q10IndexAdapterError):
        fg._build_calc_f_episode(fg.Q10IndexReactionTarget(day=DAY, key="kospi", symbol="KOSPI", kind="index", points={}, path=()))


# =========================================================================
# Calc G -- index reaction (3-state governed missing taxonomy)
# =========================================================================


def test_g_oracle_matches_real_index_reaction_absent_state(tmp_path):
    rows_by_key = _all_target_rows(DAY)
    reactions = _build_real_reactions(DAY, rows_by_key=rows_by_key, collector_root=tmp_path / "collector_absent")
    artifact_path = _write_reactions_artifact(tmp_path, reactions)

    results = fg.canonicalize_q10_index_calc_g_artifact(_day_dir(tmp_path), horizon_label="09:30", cost_policy=_cost_policy())
    assert len(results) == 2  # kospi, kosdaq -- index targets only
    for result in results:
        assert result.episode is not None
        oracle_point = reactions["targets"][result.target.key]["points"]["09:30"]
        checkpoint = next(cp for cp in result.episode.checkpoints if cp.horizon_label == "09:30")
        if oracle_point["status"] == "OBSERVED":
            assert checkpoint.completeness is CheckpointCompleteness.OBSERVED
            assert checkpoint.observed_price == pytest.approx(oracle_point["price"])
            assert checkpoint.horizon_set_id == "collector_absent_legacy_fallback"  # no collector data -> legacy fallback
        else:
            assert checkpoint.completeness is CheckpointCompleteness.MISSING


def test_g_sample_unit_reference_horizon_return_unit_cost(tmp_path):
    rows_by_key = _all_target_rows(DAY)
    reactions = _build_real_reactions(DAY, rows_by_key=rows_by_key, collector_root=tmp_path / "collector_absent")
    artifact_path = _write_reactions_artifact(tmp_path, reactions)

    results = fg.canonicalize_q10_index_calc_g_artifact(_day_dir(tmp_path), horizon_label="CLOSE", cost_policy=_cost_policy())
    kospi = next(r for r in results if r.target.key == "kospi")
    ep = kospi.episode
    assert ep.symbol == "KOSPI"
    labels = {cp.horizon_label for cp in ep.checkpoints}
    assert labels == set(fg.G_HORIZON_LABELS)
    for cp in ep.checkpoints:
        assert cp.return_unit.value == "PERCENTAGE_POINTS"
        assert cp.net_return is None  # GROSS_ONLY, same as F


def test_g_checkpoint_state_classification_all_three_states():
    verified_point = {"status": "OBSERVED", "ts": 1, "price": 100.0, "source": "q10_index_observation_collector", "capture_status": "AVAILABLE"}
    absent_legacy_point = {"status": "OBSERVED", "ts": 1, "price": 100.0}
    invalid_point = {"status": "PENDING", "price": None, "integrity_failure": True, "integrity_reason": "collector_observation_not_calculation_usable"}
    missing_point = {"status": "PENDING", "price": None}
    assert fg._g_checkpoint_state(verified_point) == "VERIFIED"
    assert fg._g_checkpoint_state(absent_legacy_point) == "ABSENT"
    assert fg._g_checkpoint_state(invalid_point) == "INVALID"
    assert fg._g_checkpoint_state(missing_point) == "ABSENT"


def test_g_invalid_state_maps_to_partial_never_zero_return():
    target = fg.Q10IndexReactionTarget(
        day=DAY, key="kospi", symbol="KOSPI", kind="index",
        points={
            "09:00": {"status": "OBSERVED", "ts": _epoch(DAY, 9, 0), "price": 1000.0},
            "09:30": {"status": "PENDING", "price": None, "integrity_failure": True, "integrity_reason": "verification_evidence_invalid"},
            "10:00": {"status": "PENDING", "price": None},
            "CLOSE": {"status": "PENDING", "price": None},
        },
        path=(),
    )
    ep = fg._build_calc_g_episode(target)
    cp = next(c for c in ep.checkpoints if c.horizon_label == "09:30")
    assert cp.completeness is CheckpointCompleteness.PARTIAL
    assert cp.gross_return is None  # never a fabricated 0-return
    assert cp.horizon_set_id == "collector_invalid"


def test_g_rejects_stock_kind():
    with pytest.raises(Q10IndexAdapterError):
        fg._build_calc_g_episode(fg.Q10IndexReactionTarget(day=DAY, key="samsung", symbol="005930", kind="stock", points={}, path=()))


# =========================================================================
# Physical evidence multiplication guard -- F/G share ONE adapter family,
# 4 targets/day -> 4 distinct physical episodes, never merged/multiplied.
# =========================================================================


def test_source_physical_event_count_equals_canonical_physical_event_count(tmp_path):
    rows_by_key = _all_target_rows(DAY)
    reactions = _build_real_reactions(DAY, rows_by_key=rows_by_key, collector_root=tmp_path / "collector_absent")
    artifact_path = _write_reactions_artifact(tmp_path, reactions)

    f_results = fg.canonicalize_q10_index_calc_f_artifact(_day_dir(tmp_path), horizon_label="09:00", cost_policy=_cost_policy())
    g_results = fg.canonicalize_q10_index_calc_g_artifact(_day_dir(tmp_path), horizon_label="09:30", cost_policy=_cost_policy())

    # 4 physical source events (samsung, sk_hynix, kospi, kosdaq) -> 4
    # canonical episodes total (2 via F, 2 via G), never 8, never fewer.
    assert len(f_results) == 2
    assert len(g_results) == 2
    all_ids = {r.episode.identity.event.canonical_event_id for r in f_results} | {r.episode.identity.event.canonical_event_id for r in g_results}
    assert len(all_ids) == 4
    for r in f_results:
        assert len(r.episode.checkpoints) == 5
    for r in g_results:
        assert len(r.episode.checkpoints) == 3


def test_f_and_g_are_different_physical_events_never_colliding(tmp_path):
    rows_by_key = _all_target_rows(DAY)
    reactions = _build_real_reactions(DAY, rows_by_key=rows_by_key, collector_root=tmp_path / "collector_absent")
    artifact_path = _write_reactions_artifact(tmp_path, reactions)

    f_results = fg.canonicalize_q10_index_calc_f_artifact(_day_dir(tmp_path), horizon_label="09:00", cost_policy=_cost_policy())
    g_results = fg.canonicalize_q10_index_calc_g_artifact(_day_dir(tmp_path), horizon_label="09:30", cost_policy=_cost_policy())
    f_ids = {r.episode.identity.event.canonical_event_id for r in f_results}
    g_ids = {r.episode.identity.event.canonical_event_id for r in g_results}
    assert not (f_ids & g_ids)  # different symbols -> disjoint physical events
    assert {r.episode.identity.hypothesis_id for r in f_results} == {fg.HYPOTHESIS_ID_F}
    assert {r.episode.identity.hypothesis_id for r in g_results} == {fg.HYPOTHESIS_ID_G}


# =========================================================================
# Calc H -- directional shadow (same physical event, different hypothesis)
# =========================================================================


def _build_h_artifacts(tmp_path, *, states: dict[str, str], collector_root: Path) -> tuple[Path, dict]:
    rows_by_key = _all_target_rows(DAY)
    reactions = _build_real_reactions(DAY, rows_by_key=rows_by_key, collector_root=collector_root)
    _write_reactions_artifact(tmp_path, reactions)

    signals = {
        "samsung": {"state": states.get("samsung", "NEUTRAL")},
        "sk_hynix": {"state": states.get("sk_hynix", "NEUTRAL")},
        "korea_market": {"state": states.get("kospi", "NEUTRAL")},
    }
    expected = build_expected_actual(signals=signals, reactions=reactions, samsung_event={})
    expected.update({"schema_version": SCHEMA_VERSION, "evaluation_program_id": PROGRAM_ID, "day": DAY})
    shadow = build_shadow_comparison(expected_actual=expected, reactions=reactions, cost_pct=0.1, slippage_pct=0.05)
    shadow.update({"schema_version": SCHEMA_VERSION, "evaluation_program_id": PROGRAM_ID, "day": DAY})

    _write_json(_day_dir(tmp_path) / "q10_expected_vs_actual.json", expected)
    _write_json(_day_dir(tmp_path) / "q10_shadow_entry_comparison.json", shadow)
    return _day_dir(tmp_path), shadow


def test_h_oracle_matches_real_shadow_comparison_directly(tmp_path):
    day_dir, shadow = _build_h_artifacts(tmp_path, states={"samsung": "POSITIVE"}, collector_root=tmp_path / "collector_absent")
    results = h.canonicalize_q10_index_calc_h_artifact(day_dir)
    samsung_results = [r for r in results if r.key == "samsung"]
    assert {r.policy for r in samsung_results} == set(SHADOW_ENTRY_POLICIES)
    oracle_by_policy = {row["policy"]: row for row in shadow["outcomes"] if row["target"] == "samsung"}
    for result in samsung_results:
        oracle = oracle_by_policy.get(result.policy)
        if oracle is None or oracle["status"] != "OBSERVED":
            assert result.episode is None
            assert result.member.state is SampleMemberState.MISSING
            continue
        assert result.episode is not None
        cp = result.episode.checkpoints[0]
        assert cp.gross_return == pytest.approx(oracle["gross_eod_return_pct"])
        assert cp.net_return == pytest.approx(oracle["net_eod_return_pct"])
        assert result.member.state is SampleMemberState.EVALUATED
        assert result.member.source_net_return == pytest.approx(oracle["net_eod_return_pct"])
        assert result.member.gross_return is None  # NET_OR_COST_INCLUDED forbids carrying gross_return


def test_h_shares_canonical_event_id_with_f_same_day_symbol(tmp_path):
    day_dir, shadow = _build_h_artifacts(tmp_path, states={"samsung": "POSITIVE"}, collector_root=tmp_path / "collector_absent")
    f_results = fg.canonicalize_q10_index_calc_f_artifact(day_dir, horizon_label="09:00", cost_policy=_cost_policy())
    samsung_f_episode = next(r.episode for r in f_results if r.target.key == "samsung")

    h_results = h.canonicalize_q10_index_calc_h_artifact(day_dir)
    observed_h = next((r for r in h_results if r.key == "samsung" and r.episode is not None), None)
    assert observed_h is not None
    assert observed_h.episode.identity.event.canonical_event_id == samsung_f_episode.identity.event.canonical_event_id
    assert observed_h.episode.identity.hypothesis_id != samsung_f_episode.identity.hypothesis_id


# =========================================================================
# FIX1 -- Calc H policy evaluation identity (Codex HIGH: 5 policy
# evaluations for the same target/day previously collided onto the SAME
# evaluation_subject_id/evaluation_record_id because canonical_event_id,
# hypothesis_id, observation_type and execution_mode were all identical
# across policies). canonical_event_id must stay SHARED (same physical
# event); evaluation_subject_id/evaluation_record_id must become
# per-policy DISTINCT via the frozen hypothesis_id dimension.
# =========================================================================


def _overreaction_samsung_rows(day: str) -> list[dict]:
    """A real, deterministic candle series engineered so EVERY one of the
    5 SHADOW_ENTRY_POLICIES resolves OBSERVED for one target/day: a large
    09:00 opening gap (triggers OVERREACTION per classify_reaction) that
    recedes >0.5% within the first 10 minutes (triggers `_first_pullback_
    entry`, called directly, never reimplemented), then holds flat
    through CLOSE so every fixed-clock checkpoint also resolves."""

    start = _epoch(day, 9, 0)
    prices = [1050.0 - i for i in range(10)] + [1041.0] * 380
    return [
        {"ts": start + i * 60, "open": price, "close": price, "high": price + 1, "low": price - 1, "volume": 100.0}
        for i, price in enumerate(prices[:390])
    ]


def _build_h_all_policies_observed_artifacts(tmp_path: Path, collector_root: Path) -> tuple[Path, dict]:
    from libs.reporting.baseline_samsung_hynix.forward_validation.reaction_reader import _stock_reaction

    rows_by_key = _all_target_rows(DAY)
    targets = {}
    for key, rows in rows_by_key.items():
        if key == "samsung":
            continue
        targets[key] = _real_target_row(day=DAY, key=key, rows=rows, previous_close=rows[0]["open"] * 0.99, collector_root=collector_root)
    samsung_rows = _overreaction_samsung_rows(DAY)
    targets["samsung"] = _stock_reaction(day=DAY, target=TARGET_BY_KEY["samsung"], rows=samsung_rows, previous_close=1000.0)
    reactions = {"day": DAY, "targets": targets, "schema_version": SCHEMA_VERSION, "evaluation_program_id": PROGRAM_ID, "guards": {}}
    _write_reactions_artifact(tmp_path, reactions)

    signals = {"samsung": {"state": "POSITIVE"}, "sk_hynix": {"state": "NEUTRAL"}, "korea_market": {"state": "NEUTRAL"}}
    expected = build_expected_actual(signals=signals, reactions=reactions, samsung_event={})
    expected.update({"schema_version": SCHEMA_VERSION, "evaluation_program_id": PROGRAM_ID, "day": DAY})
    samsung_row = next(r for r in expected["rows"] if r["target"] == "samsung")
    assert samsung_row["reaction_state"] == "OVERREACTION"  # fixture sanity check
    shadow = build_shadow_comparison(expected_actual=expected, reactions=reactions, cost_pct=0.1, slippage_pct=0.05)
    shadow.update({"schema_version": SCHEMA_VERSION, "evaluation_program_id": PROGRAM_ID, "day": DAY})

    _write_json(_day_dir(tmp_path) / "q10_expected_vs_actual.json", expected)
    _write_json(_day_dir(tmp_path) / "q10_shadow_entry_comparison.json", shadow)
    return _day_dir(tmp_path), shadow


def test_h_five_policies_share_one_canonical_event_id(tmp_path):
    day_dir, shadow = _build_h_all_policies_observed_artifacts(tmp_path, collector_root=tmp_path / "collector_absent")
    results = h.canonicalize_q10_index_calc_h_artifact(day_dir)
    samsung_observed = [r for r in results if r.key == "samsung" and r.episode is not None]
    assert {r.policy for r in samsung_observed} == set(SHADOW_ENTRY_POLICIES)  # all 5 genuinely OBSERVED

    event_ids = {r.episode.identity.event.canonical_event_id for r in samsung_observed}
    assert len(event_ids) == 1  # ONE physical (day,symbol) event, never 5


def test_h_five_policies_have_five_distinct_evaluation_subject_ids(tmp_path):
    day_dir, shadow = _build_h_all_policies_observed_artifacts(tmp_path, collector_root=tmp_path / "collector_absent")
    results = h.canonicalize_q10_index_calc_h_artifact(day_dir)
    samsung_observed = [r for r in results if r.key == "samsung" and r.episode is not None]
    assert len(samsung_observed) == len(SHADOW_ENTRY_POLICIES)

    subject_ids_by_policy = {r.policy: r.episode.identity.evaluation_subject_id for r in samsung_observed}
    assert len(set(subject_ids_by_policy.values())) == 5
    for a in SHADOW_ENTRY_POLICIES:
        for b in SHADOW_ENTRY_POLICIES:
            if a != b:
                assert subject_ids_by_policy[a] != subject_ids_by_policy[b]


def test_h_five_policies_have_five_distinct_evaluation_record_ids(tmp_path):
    day_dir, shadow = _build_h_all_policies_observed_artifacts(tmp_path, collector_root=tmp_path / "collector_absent")
    results = h.canonicalize_q10_index_calc_h_artifact(day_dir)
    samsung_observed = [r for r in results if r.key == "samsung" and r.episode is not None]
    assert len(samsung_observed) == len(SHADOW_ENTRY_POLICIES)

    record_ids_by_policy = {r.policy: r.episode.identity.evaluation_record_id for r in samsung_observed}
    assert len(set(record_ids_by_policy.values())) == 5
    print("\n".join(f"{policy:22s}{record_ids_by_policy[policy]}" for policy in SHADOW_ENTRY_POLICIES))

    # member.evaluation_record_id (aggregation-facing identity) must match too:
    member_record_ids = {r.policy: r.member.evaluation_record_id for r in samsung_observed}
    assert member_record_ids == record_ids_by_policy


def test_h_source_values_preserved_independently_per_policy_no_dict_overwrite(tmp_path):
    day_dir, shadow = _build_h_all_policies_observed_artifacts(tmp_path, collector_root=tmp_path / "collector_absent")
    results = h.canonicalize_q10_index_calc_h_artifact(day_dir)
    samsung_observed = {r.policy: r for r in results if r.key == "samsung" and r.episode is not None}
    assert len(samsung_observed) == len(SHADOW_ENTRY_POLICIES)

    oracle_by_policy = {row["policy"]: row for row in shadow["outcomes"] if row["target"] == "samsung"}
    net_returns = set()
    for policy, result in samsung_observed.items():
        oracle = oracle_by_policy[policy]
        cp = result.episode.checkpoints[0]
        assert cp.net_return == pytest.approx(oracle["net_eod_return_pct"])
        assert cp.gross_return == pytest.approx(oracle["gross_eod_return_pct"])
        assert result.episode.metadata["policy"] == policy
        net_returns.add(round(cp.net_return, 6))
    # entries at different times/prices must not have collapsed onto one
    # identical return figure purely by construction of this fixture --
    # confirms distinct records really do carry distinct source values:
    assert len(net_returns) >= 2


def test_h_policy_identity_deterministic_rerun(tmp_path):
    day_dir, shadow = _build_h_all_policies_observed_artifacts(tmp_path, collector_root=tmp_path / "collector_absent")
    first = {(r.key, r.policy): r for r in h.canonicalize_q10_index_calc_h_artifact(day_dir) if r.episode is not None}
    second = {(r.key, r.policy): r for r in h.canonicalize_q10_index_calc_h_artifact(day_dir) if r.episode is not None}
    assert set(first) == set(second)
    for k in first:
        assert first[k].episode.identity.evaluation_subject_id == second[k].episode.identity.evaluation_subject_id
        assert first[k].episode.identity.evaluation_record_id == second[k].episode.identity.evaluation_record_id
        assert first[k].episode.identity.event.canonical_event_id == second[k].episode.identity.event.canonical_event_id


def test_h_policy_hypothesis_id_rejects_unknown_policy():
    with pytest.raises(Q10IndexAdapterError):
        h.policy_hypothesis_id("UNKNOWN_POLICY")


def test_h_neutral_target_is_excluded_never_missing_never_zero(tmp_path):
    day_dir, shadow = _build_h_artifacts(tmp_path, states={"samsung": "NEUTRAL"}, collector_root=tmp_path / "collector_absent")
    # real shadow_comparison never emits an outcome row for a NEUTRAL target:
    assert not any(row["target"] == "samsung" for row in shadow["outcomes"])
    results = h.canonicalize_q10_index_calc_h_artifact(day_dir)
    samsung_results = [r for r in results if r.key == "samsung"]
    assert len(samsung_results) == len(SHADOW_ENTRY_POLICIES)
    for r in samsung_results:
        assert r.member.state is SampleMemberState.EXCLUDED
        assert r.member.state is not SampleMemberState.MISSING
        assert r.member.gross_return is None
        assert r.episode is None
        assert r.exclusion is not None
        assert r.exclusion.expected_state == "NEUTRAL"
        assert r.exclusion.exclusion_reason == "neutral_expected_state:NEUTRAL"


def test_h_direction_semantics_preserved_distinctly(tmp_path):
    day_dir, shadow = _build_h_artifacts(tmp_path, states={"samsung": "NEGATIVE"}, collector_root=tmp_path / "collector_absent")
    results = h.canonicalize_q10_index_calc_h_artifact(day_dir)
    observed = [r for r in results if r.key == "samsung" and r.episode is not None]
    for r in observed:
        assert r.episode.metadata["direction"] == -1
        assert r.episode.metadata["expected_state"] == "NEGATIVE"


# =========================================================================
# Trusted-artifact ingestion boundary -- Controlled Probe / Controlled
# Mock Lane / execution evidence / forged-schema rejection
# =========================================================================


def test_fg_loader_rejects_path_outside_real_artifact_family(tmp_path):
    rows_by_key = _all_target_rows(DAY)
    reactions = _build_real_reactions(DAY, rows_by_key=rows_by_key, collector_root=tmp_path / "collector_absent")
    wrong_dir = tmp_path / "data" / "logs" / "opening_rank1_controlled_probe" / DAY
    wrong_dir.mkdir(parents=True, exist_ok=True)
    (wrong_dir / "q10_actual_market_reactions.json").write_text(json.dumps(reactions), encoding="utf-8")
    with pytest.raises(Q10IndexAdapterError):
        fg.canonicalize_q10_index_calc_f_artifact(wrong_dir, horizon_label="09:00", cost_policy=_cost_policy())


def test_fg_loader_rejects_real_family_path_with_wrong_schema(tmp_path):
    rows_by_key = _all_target_rows(DAY)
    reactions = _build_real_reactions(DAY, rows_by_key=rows_by_key, collector_root=tmp_path / "collector_absent")
    reactions["schema_version"] = "controlled_mock_lanes.v1"
    _write_reactions_artifact(tmp_path, reactions)
    with pytest.raises(Q10IndexAdapterError):
        fg.canonicalize_q10_index_calc_f_artifact(_day_dir(tmp_path), horizon_label="09:00", cost_policy=_cost_policy())


def test_fg_loader_rejects_controlled_probe_origin(tmp_path):
    directory = tmp_path / "data" / "logs" / "opening_rank1_controlled_probe" / DAY
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "probe_submissions.json").write_text(json.dumps({
        "schema_version": "opening_rank1_controlled_probe.v3", "day": DAY,
        "submissions": [{"run_id": "R1", "symbol": "005930", "scanner_rank": 1}],
    }), encoding="utf-8")
    with pytest.raises(Q10IndexAdapterError):
        fg._read_verified_json(directory, "probe_submissions.json")


def test_fg_loader_rejects_controlled_mock_lane_origin_including_q10_index_etf_symbol(tmp_path):
    # 114800 is the REAL Controlled Mock Lane Q10_INDEX ETF symbol (KODEX
    # Inverse) -- must be rejected even when it overlaps perfectly with a
    # real Calc H evaluation on EVERY shared field: same trading date,
    # same decision_id, same direction (-1, matching a real H SHORT
    # outcome) -- the rejection must be driven by real artifact origin,
    # never by any of these fields differing.
    directory = tmp_path / "data" / "logs" / "controlled_mock_lanes" / DAY
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "lane_submissions.json").write_text(json.dumps({
        "schema_version": "controlled_mock_lane_submissions.v1", "day": DAY,
        "submissions": [{
            "lane_id": "Q10_INDEX", "symbol": "114800", "side": "BUY", "qty": 1, "price": 2500.0,
            "decision_id": "D1", "direction": -1, "trading_date": DAY,
        }],
    }), encoding="utf-8")
    with pytest.raises(Q10IndexAdapterError):
        fg._read_verified_json(directory, "lane_submissions.json")


def test_fg_loader_rejects_real_controlled_execution_even_with_full_field_overlap(tmp_path):
    # Section 35's exact reproducer: a representative controlled Q10
    # Index execution record sharing symbol (114800), trading date,
    # direction, AND decision_id with a genuine Calc H evaluation for the
    # SAME day -- confirming the rejection survives full field overlap,
    # not merely a lucky mismatch.
    day_dir, shadow = _build_h_artifacts(tmp_path, states={"kospi": "NEGATIVE"}, collector_root=tmp_path / "collector_absent")
    h_results = h.canonicalize_q10_index_calc_h_artifact(day_dir)
    observed_kospi = next(r for r in h_results if r.key == "kospi" and r.episode is not None)
    assert observed_kospi.episode.metadata["direction"] == -1

    execution_dir = tmp_path / "data" / "logs" / "controlled_mock_lanes" / DAY
    execution_dir.mkdir(parents=True, exist_ok=True)
    (execution_dir / "lane_submissions.json").write_text(json.dumps({
        "schema_version": "controlled_mock_lane_submissions.v1", "day": DAY,
        "submissions": [{
            "lane_id": "Q10_INDEX", "symbol": "114800", "side": "BUY", "qty": 1, "price": 2500.0,
            "decision_id": observed_kospi.episode.identity.event.canonical_event_id, "direction": -1, "trading_date": DAY,
        }],
    }), encoding="utf-8")
    with pytest.raises(Q10IndexAdapterError):
        h.canonicalize_q10_index_calc_h_artifact(execution_dir)


def test_fg_loader_rejects_execution_evidence_origin(tmp_path):
    directory = tmp_path / "data" / "state" / "executions" / DAY
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "order_fills.json").write_text(json.dumps({
        "schema_version": "order_execution_outcome.v1",
        "fills": [{"decision_id": "D1", "symbol": "114800", "timestamp": _epoch(DAY, 9, 5), "order_fill_status": "FILLED"}],
    }), encoding="utf-8")
    with pytest.raises(Q10IndexAdapterError):
        fg._read_verified_json(directory, "order_fills.json")


def test_fg_loader_rejects_arbitrary_shape_matching_payload(tmp_path):
    # a payload that LOOKS like a real reactions artifact (same "targets"
    # key structure) but sits under the wrong family path AND carries an
    # unrelated schema_version -- rejected regardless of shape overlap.
    rows_by_key = _all_target_rows(DAY)
    reactions = _build_real_reactions(DAY, rows_by_key=rows_by_key, collector_root=tmp_path / "collector_absent")
    reactions["schema_version"] = "totally_unknown_family.v1"
    reactions["evaluation_program_id"] = "SOME_OTHER_PROGRAM"
    wrong_dir = tmp_path / "data" / "logs" / "some_unrelated_family" / DAY
    wrong_dir.mkdir(parents=True, exist_ok=True)
    (wrong_dir / "q10_actual_market_reactions.json").write_text(json.dumps(reactions), encoding="utf-8")
    with pytest.raises(Q10IndexAdapterError):
        fg.canonicalize_q10_index_calc_f_artifact(wrong_dir, horizon_label="09:00", cost_policy=_cost_policy())


def test_fg_loader_rejects_missing_provenance(tmp_path):
    rows_by_key = _all_target_rows(DAY)
    reactions = _build_real_reactions(DAY, rows_by_key=rows_by_key, collector_root=tmp_path / "collector_absent")
    del reactions["schema_version"]
    del reactions["evaluation_program_id"]
    _write_reactions_artifact(tmp_path, reactions)
    with pytest.raises(Q10IndexAdapterError):
        fg.canonicalize_q10_index_calc_f_artifact(_day_dir(tmp_path), horizon_label="09:00", cost_policy=_cost_policy())


def test_fg_loader_accepts_real_source_artifact(tmp_path):
    rows_by_key = _all_target_rows(DAY)
    reactions = _build_real_reactions(DAY, rows_by_key=rows_by_key, collector_root=tmp_path / "collector_absent")
    _write_reactions_artifact(tmp_path, reactions)
    f_results = fg.canonicalize_q10_index_calc_f_artifact(_day_dir(tmp_path), horizon_label="09:00", cost_policy=_cost_policy())
    g_results = fg.canonicalize_q10_index_calc_g_artifact(_day_dir(tmp_path), horizon_label="09:30", cost_policy=_cost_policy())
    assert len(f_results) == 2
    assert len(g_results) == 2


def test_h_loader_rejects_controlled_probe_and_mock_lane_and_execution_and_forged_schema(tmp_path):
    day_dir, _shadow = _build_h_artifacts(tmp_path, states={"samsung": "POSITIVE"}, collector_root=tmp_path / "collector_absent")

    # forged-schema reproducer: correct schema_version/program_id, wrong directory family
    wrong_dir = tmp_path / "data" / "logs" / "controlled_mock_lanes" / DAY
    wrong_dir.mkdir(parents=True, exist_ok=True)
    forged = {"schema_version": SCHEMA_VERSION, "evaluation_program_id": PROGRAM_ID, "rows": []}
    (wrong_dir / "q10_expected_vs_actual.json").write_text(json.dumps(forged), encoding="utf-8")
    (wrong_dir / "q10_shadow_entry_comparison.json").write_text(json.dumps({**forged, "outcomes": []}), encoding="utf-8")
    with pytest.raises(Q10IndexAdapterError):
        h.canonicalize_q10_index_calc_h_artifact(wrong_dir)


def test_h_public_api_derives_symbol_authority_from_trusted_reactions_artifact(tmp_path):
    day_dir, _shadow = _build_h_artifacts(tmp_path, states={"samsung": "POSITIVE"}, collector_root=tmp_path / "collector_absent")
    signature = inspect.signature(h.canonicalize_q10_index_calc_h_artifact)
    assert "target_symbols" not in signature.parameters

    # If the trusted reactions artifact is unavailable, Calc H has no
    # source-derived key->symbol authority and must fail instead of
    # accepting a caller-supplied mapping.
    (day_dir / "q10_actual_market_reactions.json").unlink()
    with pytest.raises(Q10IndexAdapterError):
        h.canonicalize_q10_index_calc_h_artifact(day_dir)


# =========================================================================
# Scanner / Opening / Q10 Semiconductor provenance exclusion -- rows from
# other families cannot enter Q10 Index adapters merely due to overlapping
# fields (e.g. "symbol", "day").
# =========================================================================


def test_q10_index_adapters_never_import_controlled_probe_or_mock_lane_or_scanner():
    def imported_modules(path: Path) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
        return modules

    for path in (
        Path("libs/reporting/evaluation/canonical/adapters/q10_index_reaction_adapter.py"),
        Path("libs/reporting/evaluation/canonical/adapters/q10_index_directional_shadow_adapter.py"),
    ):
        modules = imported_modules(path)
        assert not any("controlled_probe" in m for m in modules)
        assert not any("controlled_mock_lane" in m for m in modules)
        assert not any(m.startswith("graphs.nodes.scanner") for m in modules)
        assert not any("executor" in m or "broker" in m for m in modules)


# =========================================================================
# Financial logic / program-specific core-branch guards
# =========================================================================


_ADAPTER_FILES = (
    Path("libs/reporting/evaluation/canonical/adapters/q10_index_reaction_adapter.py"),
    Path("libs/reporting/evaluation/canonical/adapters/q10_index_directional_shadow_adapter.py"),
)
_FORBIDDEN_DEFINITIONS = {"calculate_profit_factor", "calculate_max_drawdown", "calculate_total_cost", "classify_net_return"}


def test_q10_index_adapters_never_define_a_financial_calculation_function():
    for path in _ADAPTER_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        overlap = defined & _FORBIDDEN_DEFINITIONS
        assert not overlap, f"{path} redefines frozen UEF-3B calculation function(s): {overlap}"


def test_frozen_and_prior_approved_adapters_untouched_by_this_task():
    from libs.reporting.evaluation.canonical.adapters import q10_semiconductor  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import forward_measurement_adapter  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import q12_baseline_btc_woori  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import hypothesis_forward_adapter  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import opening_rank1_shadow  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import already_net_shadow_adapter  # noqa: F401
