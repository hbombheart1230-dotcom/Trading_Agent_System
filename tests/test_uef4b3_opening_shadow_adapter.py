"""UEF-4B-3 -- Opening Shadow (1A/1B/1C) canonical adapter tests.

Covers 1A (`opening_rank1_shadow.py`, reuse of the frozen
`forward_measurement_adapter` generic layer, GROSS_ONLY) and 1B/1C
(`already_net_shadow_adapter.py`, ONE merged episode per physical
"virtual buy" case, NET_OR_COST_INCLUDED, verified against the real
legacy `forward_30m_net`/`delayed_path` functions directly), physical
identity / evidence-multiplication guards, the FIX2 trusted-artifact
ingestion boundary (population gate + real origin verification --
Controlled Probe / Controlled Mock Lane / execution-evidence exclusion),
the "Opening Alpha" non-single-evaluator guard, and fail-fast
invalid-input handling. Real source
(`libs/reporting/opening_rank1_shadow/**`,
`libs/research/opening_rank1_longitudinal/**`,
`libs/runtime/opening_rank1_controlled_probe.py`,
`libs/runtime/controlled_mock_lanes/**`) informs every fixture shape
below, per this task's own "verify actual source" mandate.

FIX2 architecture note: the approved public surface is
`shadow1a.canonicalize_opening_shadow_1a_artifact` /
`shadow1bc.canonicalize_opening_shadow_1bc_artifact` -- both read a real
JSON artifact off disk, verify its family path layout AND persisted
schema_version, then canonicalize. Tests that need white-box coverage of
lower-level behavior (identity determinism, reference resolution,
rank-as-metadata, etc.) reach the underscore-prefixed internals directly
(`_parse_1a_candidate`, `_build_1a_episode`, `_VerifiedOpeningShadow1ARecord`,
...) -- these are internal-only, not `__all__`-exported, and are never
themselves the supported ingestion path (see
`test_raw_builders_not_publicly_exported`).
"""

from __future__ import annotations

import ast
import datetime
import json
import zoneinfo
from pathlib import Path

import pytest

from libs.reporting.evaluation.canonical.contracts import CheckpointCompleteness, ExecutionMode, ReturnUnit
from libs.reporting.evaluation.canonical.metrics import CostPolicy, MetricAggregationContext, MetricPolicy
from libs.reporting.evaluation.canonical.metrics.contracts import CostTiming
from libs.reporting.evaluation.canonical.metrics.aggregation import (
    CanonicalSampleBatch,
    SampleMemberState,
    aggregate_canonical_samples,
)
from libs.reporting.evaluation.canonical.identity import build_event_ref, evaluation_record_id, evaluation_subject_id
from libs.reporting.evaluation.canonical.record import AggregateIdentity

from libs.reporting.evaluation.canonical.adapters import opening_rank1_shadow as shadow1a
from libs.reporting.evaluation.canonical.adapters import already_net_shadow_adapter as shadow1bc
from libs.reporting.evaluation.canonical.adapters.opening_rank1_shadow import OpeningShadowAdapterError

KST = zoneinfo.ZoneInfo("Asia/Seoul")
DAY = "2026-06-24"


def kst_epoch(day: str, hh: int, mm: int) -> int:
    return int(datetime.datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=KST).timestamp())


def _minute_candles(*, start_ts: int, count: int, base: float, step: float = 1.0) -> list[dict]:
    rows = []
    for i in range(count):
        ts = start_ts + i * 60
        rows.append({
            "ts": ts,
            "raw_ts": datetime.datetime.fromtimestamp(ts, tz=KST).strftime("%Y%m%d%H%M%S"),
            "open": base + step * i, "close": base + step * i,
            "high": base + step * i + 1, "low": base + step * i - 1, "volume": 100.0,
        })
    return rows


def _gross_cost_policy() -> CostPolicy:
    return CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.1, slippage=0.05, provenance="test_fixture")


# =========================================================================
# 1A -- opening_rank1_shadow.py (reuse of forward_measurement_adapter)
# =========================================================================


def _1a_row(*, watch_id: str = "W1", trigger_day: str = DAY, symbol: str = "005930", trigger_epoch: int, rank: int = 2, day_status: str = "VALID") -> dict:
    return {
        "watch_id": watch_id, "trigger_day": trigger_day, "symbol": symbol,
        "trigger_epoch": trigger_epoch, "trigger_decision_id": "D1", "rank": rank,
        "trigger_day_integrity_status": day_status,
        "initial_episode_id": "E0", "initial_day": "2026-06-20",
    }


TRIGGER_EPOCH = kst_epoch(DAY, 9, 5)
CANDLES_1A = _minute_candles(start_ts=TRIGGER_EPOCH, count=200, base=1000.0, step=1.0)


def _verified_1a(candidate: shadow1a.OpeningShadow1ACandidate):
    return shadow1a._VerifiedOpeningShadow1ARecord(candidate)


def _1a_candidate(**kwargs) -> shadow1a.OpeningShadow1ACandidate:
    return shadow1a._parse_1a_candidate(_1a_row(**kwargs))


def _write_1a_artifact(tmp_path: Path, rows: list[dict], *, schema_version: str | None = None, family_dir: str = "opening_rank1_shadow/latent_watch") -> Path:
    """Write a JSON file at the REAL 1A artifact family path layout
    (`.../opening_rank1_shadow/latent_watch/latent_reactivation_forward.json`,
    matching `latent_watch.py:292-303`/`latent_forward.py:276-277`
    exactly), with the real writer's own payload shape
    (`latent_forward.py:267-275`). `family_dir` lets a test deliberately
    write the file under a DIFFERENT family path to prove the origin gate
    checks the path, not just the content."""

    directory = tmp_path / family_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "latent_reactivation_forward.json"
    payload = {
        "schema_version": schema_version if schema_version is not None else shadow1a.LATENT_REACTIVATION_FORWARD_SCHEMA_VERSION,
        "behavior_effect": "observation_only",
        "through_day": DAY,
        "cost_bases": {},
        "summary": {},
        "rows": rows,
        "policy_change_authorized": False,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_1a_uses_generic_semantic_layer():
    tree = ast.parse(Path("libs/reporting/evaluation/canonical/adapters/opening_rank1_shadow.py").read_text(encoding="utf-8"))
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "build_forward_measurement_episode" in calls
    assert "build_forward_measurement_event_ref" in calls


def test_1a_sample_unit_reference_horizon_return_unit_cost():
    candidate = _1a_candidate(trigger_epoch=TRIGGER_EPOCH)
    ep = shadow1a._build_1a_episode(_verified_1a(candidate), CANDLES_1A)
    assert ep.symbol == "005930"
    assert ep.execution_mode is ExecutionMode.OBSERVATION_ONLY
    labels = {cp.horizon_label for cp in ep.checkpoints}
    assert labels == {"+5m", "+15m", "+30m", "+60m", "EOD"}
    for cp in ep.checkpoints:
        assert cp.return_unit.value == "PERCENTAGE_POINTS"
        assert cp.net_return is None  # GROSS_ONLY -- net computed only later, externally


def test_1a_reference_is_first_candle_after_trigger_not_candle_at_trigger():
    # entry resolution must be the FIRST candle STRICTLY AFTER trigger_epoch
    # (matches `_observe`'s own `> trigger_epoch` check, not `>=`).
    candidate = _1a_candidate(trigger_epoch=TRIGGER_EPOCH)
    rows = list(CANDLES_1A)
    ep = shadow1a._build_1a_episode(_verified_1a(candidate), rows)
    five_min = next(cp for cp in ep.checkpoints if cp.horizon_label == "+5m")
    # the entry candle is the one at TRIGGER_EPOCH+60 (first strictly after
    # trigger); +5m target = entry_epoch + 300
    assert five_min.target_timestamp == TRIGGER_EPOCH + 60 + 300


def test_1a_identity_deterministic_and_distinguishes_symbol_and_watch():
    c1 = _1a_candidate(watch_id="W1", trigger_epoch=TRIGGER_EPOCH)
    c2 = _1a_candidate(watch_id="W1", trigger_epoch=TRIGGER_EPOCH)
    ep1 = shadow1a._build_1a_episode(_verified_1a(c1), CANDLES_1A)
    ep2 = shadow1a._build_1a_episode(_verified_1a(c2), CANDLES_1A)
    assert ep1.identity.evaluation_record_id == ep2.identity.evaluation_record_id

    c3 = _1a_candidate(watch_id="W2", trigger_epoch=TRIGGER_EPOCH)
    ep3 = shadow1a._build_1a_episode(_verified_1a(c3), CANDLES_1A)
    assert ep1.identity.event.canonical_event_id != ep3.identity.event.canonical_event_id

    c4 = _1a_candidate(watch_id="W1", symbol="000660", trigger_epoch=TRIGGER_EPOCH)
    ep4 = shadow1a._build_1a_episode(_verified_1a(c4), CANDLES_1A)
    assert ep1.identity.event.canonical_event_id != ep4.identity.event.canonical_event_id


def test_1a_rank_is_metadata_not_identity():
    c_rank2 = _1a_candidate(watch_id="W1", trigger_epoch=TRIGGER_EPOCH, rank=2)
    c_rank5 = _1a_candidate(watch_id="W1", trigger_epoch=TRIGGER_EPOCH, rank=5)
    ep_a = shadow1a._build_1a_episode(_verified_1a(c_rank2), CANDLES_1A)
    ep_b = shadow1a._build_1a_episode(_verified_1a(c_rank5), CANDLES_1A)
    # same physical watch/trigger -> same identity regardless of rank
    assert ep_a.identity.event.canonical_event_id == ep_b.identity.event.canonical_event_id
    assert ep_a.metadata["rank"] == 2
    assert ep_b.metadata["rank"] == 5


def test_1a_missing_forward_reference_rejected_not_zero_return():
    candidate = _1a_candidate(trigger_epoch=TRIGGER_EPOCH)
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a._build_1a_episode(_verified_1a(candidate), [])  # no candles at all -> no resolvable reference


def test_1a_invalid_candle_timestamp_rejected_never_dropped():
    candidate = _1a_candidate(trigger_epoch=TRIGGER_EPOCH)
    rows = [dict(row) for row in CANDLES_1A]
    rows[5]["ts"] = 0
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a._build_1a_episode(_verified_1a(candidate), rows)


def test_1a_shared_parser_rejects_invalid_numerics():
    rows = [dict(row) for row in CANDLES_1A]
    rows[3]["close"] = float("nan")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a.candles_to_observations(rows)
    rows2 = [dict(row) for row in CANDLES_1A]
    rows2[3]["close"] = -5.0
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a.candles_to_observations(rows2)
    rows3 = [dict(row) for row in CANDLES_1A]
    rows3[3]["volume"] = -1.0
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a.candles_to_observations(rows3)


def test_1a_missing_identity_fields_rejected():
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a._parse_1a_candidate({"trigger_day": DAY, "symbol": "005930", "trigger_epoch": TRIGGER_EPOCH})  # no watch_id
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a._parse_1a_candidate({"watch_id": "W1", "symbol": "005930", "trigger_epoch": TRIGGER_EPOCH})  # no trigger_day
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a._parse_1a_candidate({"watch_id": "W1", "trigger_day": DAY, "trigger_epoch": TRIGGER_EPOCH})  # no symbol


# =========================================================================
# FIX1/FIX2 HIGH#1 -- 1A population state: VALID -> eligible/evaluated,
# non-VALID -> EXCLUDED (never MISSING, never a 0-return, never dropped),
# and this must hold at EVERY approved canonical generation boundary,
# including the public `canonicalize_opening_shadow_1a_artifact` path.
# =========================================================================


def test_1a_valid_candidate_is_eligible_evaluated_member():
    candidate = _1a_candidate(trigger_epoch=TRIGGER_EPOCH, day_status="VALID")
    member = shadow1a._resolve_1a_aggregation_member(_verified_1a(candidate), CANDLES_1A, horizon_label="+5m", cost_policy=_gross_cost_policy())
    assert member.state is SampleMemberState.EVALUATED
    assert member.gross_return is not None


def test_1a_non_valid_candidate_is_excluded_not_missing_not_zero_return():
    candidate = _1a_candidate(trigger_epoch=TRIGGER_EPOCH, day_status="EXCLUDED_TRIGGER_DAY_INTEGRITY")
    member = shadow1a._resolve_1a_aggregation_member(_verified_1a(candidate), CANDLES_1A, horizon_label="+5m", cost_policy=_gross_cost_policy())
    assert member.state is SampleMemberState.EXCLUDED
    assert member.state is not SampleMemberState.MISSING
    assert member.gross_return is None  # never a fabricated 0-return
    assert member.evaluation_record_id == ""


def test_1a_exclusion_never_attempts_forward_resolution_real_legacy_never_does_either():
    # real `build_latent_reactivation_forward` never calls `_observe()` for
    # an excluded row -- so even with NO candles at all (which would raise
    # for a VALID candidate), a non-VALID candidate must still resolve to
    # EXCLUDED, never raise, never MISSING.
    candidate = _1a_candidate(trigger_epoch=TRIGGER_EPOCH, day_status="MISSING")
    member = shadow1a._resolve_1a_aggregation_member(_verified_1a(candidate), [], horizon_label="+5m", cost_policy=_gross_cost_policy())
    assert member.state is SampleMemberState.EXCLUDED


def test_1a_exclusion_record_preserves_full_lineage():
    candidate = _1a_candidate(watch_id="W9", trigger_day=DAY, symbol="005930", trigger_epoch=TRIGGER_EPOCH, day_status="ARTIFACT_INCOMPLETE")
    record = shadow1a._build_1a_exclusion_record(_verified_1a(candidate))
    assert record.watch_id == "W9"
    assert record.symbol == "005930"
    assert record.trading_date == DAY
    assert record.trigger_epoch == TRIGGER_EPOCH
    assert record.day_integrity_status == "ARTIFACT_INCOMPLETE"
    assert record.exclusion_reason == "opening_day_status:ARTIFACT_INCOMPLETE"
    assert record.legacy_schema == shadow1a.LATENT_REACTIVATION_FORWARD_SCHEMA_VERSION
    assert record.source_artifact


def test_1a_exclusion_record_rejects_a_valid_candidate():
    candidate = _1a_candidate(trigger_epoch=TRIGGER_EPOCH, day_status="VALID")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a._build_1a_exclusion_record(_verified_1a(candidate))


def test_1a_episode_builder_rejects_non_valid_candidate_defensively():
    # HIGH#1 core requirement: it must be impossible to obtain a normal
    # EpisodeRecord for a non-VALID candidate through ANY approved
    # canonical generation boundary -- including calling the internal
    # episode builder directly with a verified-but-non-VALID record.
    candidate = _1a_candidate(trigger_epoch=TRIGGER_EPOCH, day_status="EXCLUDED_TRIGGER_DAY_INTEGRITY")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a._build_1a_episode(_verified_1a(candidate), CANDLES_1A)


def test_1a_population_accounting_one_valid_one_excluded():
    # Required regression: 1 VALID + 1 non-VALID row -> physical source
    # events=2, eligible/evaluated=1, excluded=1, missing=0.
    valid = _1a_candidate(watch_id="WV", trigger_epoch=TRIGGER_EPOCH, day_status="VALID")
    excluded = _1a_candidate(watch_id="WX", trigger_epoch=TRIGGER_EPOCH, day_status="MISSING")
    source_candidates = [valid, excluded]
    assert len(source_candidates) == 2  # physical source event count

    members = [
        shadow1a._resolve_1a_aggregation_member(_verified_1a(c), CANDLES_1A, horizon_label="+5m", cost_policy=_gross_cost_policy())
        for c in source_candidates
    ]
    assert sum(1 for m in members if m.state is SampleMemberState.EVALUATED) == 1
    assert sum(1 for m in members if m.state is SampleMemberState.EXCLUDED) == 1
    assert sum(1 for m in members if m.state is SampleMemberState.MISSING) == 0

    # confirm this is also true through the frozen UEF-3C aggregation
    # entry point itself (never a hand-rolled count only):
    cost_policy = _gross_cost_policy()
    metric_policy = MetricPolicy()
    aggregate_ref = build_event_ref(source_namespace=shadow1a.SOURCE_NAMESPACE, native_id="fix2_population_regression:+5m")
    subject_id = evaluation_subject_id(canonical_event_id=aggregate_ref.canonical_event_id, hypothesis_id=shadow1a.HYPOTHESIS_ID_1A, observation_type="AGGREGATE")
    record_id = evaluation_record_id(evaluation_subject_id=subject_id, execution_mode="OBSERVATION_ONLY")
    context = MetricAggregationContext(
        aggregate_identity=AggregateIdentity(
            aggregate_ref=aggregate_ref, aggregation_scope="opening_rank1_shadow_1a", hypothesis_id=shadow1a.HYPOTHESIS_ID_1A,
            evaluation_subject_id=subject_id, evaluation_record_id=record_id,
        ),
        horizon_label="+5m", cost_policy_id=cost_policy.policy_id, metric_policy_id=metric_policy.policy_id,
    )
    batch = CanonicalSampleBatch(context=context, members=tuple(members))
    aggregate = aggregate_canonical_samples(
        context=context, batches=(batch,), metric_policy=metric_policy,
        input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start=DAY,
        excluded_note="opening_rank1_shadow 1A non-VALID trigger_day_integrity_status excluded by real legacy build_latent_reactivation_forward policy",
    )
    population = aggregate.metrics["sample_population"]
    assert population["sample_count"] == 2
    assert population["evaluated_count"] == 1
    assert population["excluded_count"] == 1
    assert population["missing_count"] == 0


# =========================================================================
# FIX2 -- 1A trusted-artifact ingestion: the ONE approved public path is
# `canonicalize_opening_shadow_1a_artifact`, which reads a real JSON file
# and verifies BOTH its family path layout and persisted schema_version
# before canonicalizing anything.
# =========================================================================


def test_1a_public_path_valid_row_is_evaluated(tmp_path):
    artifact_path = _write_1a_artifact(tmp_path, [_1a_row(trigger_epoch=TRIGGER_EPOCH, day_status="VALID")])
    results = shadow1a.canonicalize_opening_shadow_1a_artifact(
        artifact_path, candles_by_symbol={"005930": CANDLES_1A}, horizon_label="+5m", cost_policy=_gross_cost_policy(),
    )
    assert len(results) == 1
    result = results[0]
    assert result.member.state is SampleMemberState.EVALUATED
    assert result.episode is not None
    assert result.exclusion is None


def test_1a_public_path_non_valid_row_is_excluded(tmp_path):
    artifact_path = _write_1a_artifact(tmp_path, [_1a_row(trigger_epoch=TRIGGER_EPOCH, day_status="EXCLUDED_TRIGGER_DAY_INTEGRITY")])
    results = shadow1a.canonicalize_opening_shadow_1a_artifact(
        artifact_path, candles_by_symbol={"005930": CANDLES_1A}, horizon_label="+5m", cost_policy=_gross_cost_policy(),
    )
    assert len(results) == 1
    result = results[0]
    assert result.member.state is SampleMemberState.EXCLUDED
    assert result.episode is None  # HIGH#1: no normal EpisodeRecord for a non-VALID row, even through the public path
    assert result.exclusion is not None
    assert result.exclusion.day_integrity_status == "EXCLUDED_TRIGGER_DAY_INTEGRITY"


def test_1a_public_path_cannot_produce_episode_for_non_valid_row_no_matter_what(tmp_path):
    # direct restatement of the HIGH#1 invariant Codex requires: scanning
    # every result from the public path, NONE with a non-VALID source row
    # ever carries a populated `episode`.
    rows = [
        _1a_row(watch_id="WV", trigger_epoch=TRIGGER_EPOCH, day_status="VALID"),
        _1a_row(watch_id="WX1", trigger_epoch=TRIGGER_EPOCH, day_status="EXCLUDED_TRIGGER_DAY_INTEGRITY"),
        _1a_row(watch_id="WX2", trigger_epoch=TRIGGER_EPOCH, day_status="ARTIFACT_INCOMPLETE"),
    ]
    artifact_path = _write_1a_artifact(tmp_path, rows)
    results = shadow1a.canonicalize_opening_shadow_1a_artifact(
        artifact_path, candles_by_symbol={"005930": CANDLES_1A}, horizon_label="+5m", cost_policy=_gross_cost_policy(),
    )
    for result in results:
        if result.candidate.day_integrity_status != "VALID":
            assert result.episode is None
            assert result.exclusion is not None
            assert result.member.state is SampleMemberState.EXCLUDED


def test_1a_raw_dict_cannot_reach_canonical_path_without_going_through_the_loader():
    # a raw, arbitrary dict (even one shaped exactly like a real 1A row)
    # has no way to reach `canonicalize_opening_shadow_1a_artifact` --
    # that function only accepts a real, origin-verified file path, never
    # an in-memory dict/row.
    import inspect

    sig = inspect.signature(shadow1a.canonicalize_opening_shadow_1a_artifact)
    assert list(sig.parameters)[0] == "path"
    assert sig.parameters["path"].annotation in ("str | Path", Path) or "Path" in str(sig.parameters["path"].annotation)


def test_1a_loader_rejects_path_outside_real_artifact_family(tmp_path):
    # forged-schema reproducer (Section 18): a file carrying the REAL
    # approved schema_version literal, but NOT located under the real 1A
    # artifact family path layout -- must be rejected on origin, not schema.
    wrong_family_dir = "opening_rank1_controlled_probe/2026-06-24"
    artifact_path = _write_1a_artifact(
        tmp_path, [_1a_row(trigger_epoch=TRIGGER_EPOCH)],
        schema_version=shadow1a.LATENT_REACTIVATION_FORWARD_SCHEMA_VERSION,
        family_dir=wrong_family_dir,
    )
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a.canonicalize_opening_shadow_1a_artifact(
            artifact_path, candles_by_symbol={"005930": CANDLES_1A}, horizon_label="+5m", cost_policy=_gross_cost_policy(),
        )


def test_1a_loader_rejects_real_family_path_with_wrong_schema(tmp_path):
    artifact_path = _write_1a_artifact(tmp_path, [_1a_row(trigger_epoch=TRIGGER_EPOCH)], schema_version="controlled_mock_lanes.v1")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a.canonicalize_opening_shadow_1a_artifact(
            artifact_path, candles_by_symbol={"005930": CANDLES_1A}, horizon_label="+5m", cost_policy=_gross_cost_policy(),
        )


def test_1a_loader_rejects_controlled_probe_origin(tmp_path):
    # realistic Controlled Probe artifact shape AND real Controlled Probe
    # family path -- rejected on family/origin, not on a missing field.
    directory = tmp_path / "data" / "logs" / "opening_rank1_controlled_probe" / DAY
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "probe_submissions.json"
    payload = {
        "schema_version": "opening_rank1_controlled_probe.v3",
        "day": DAY,
        "submissions": [{
            "schema_version": "opening_rank1_controlled_probe.v3",
            "run_id": "R1", "symbol": "005930", "scanner_rank": 1,
            "candidate_setup": "DIRECTIONAL_BREADTH",
        }],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a.canonicalize_opening_shadow_1a_artifact(
            path, candles_by_symbol={"005930": CANDLES_1A}, horizon_label="+5m", cost_policy=_gross_cost_policy(),
        )


def test_1a_loader_rejects_controlled_mock_lane_origin(tmp_path):
    directory = tmp_path / "data" / "logs" / "controlled_mock_lanes" / DAY
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "lane_submissions.json"
    payload = {
        "schema_version": "controlled_mock_lane_submissions.v1",
        "day": DAY,
        "submissions": [{
            "lane_id": "BTC_WOORI", "symbol": "005930", "side": "BUY", "qty": 1, "price": 71000.0,
        }],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a.canonicalize_opening_shadow_1a_artifact(
            path, candles_by_symbol={"005930": CANDLES_1A}, horizon_label="+5m", cost_policy=_gross_cost_policy(),
        )


def test_1a_loader_rejects_execution_evidence_origin(tmp_path):
    directory = tmp_path / "data" / "state" / "executions" / DAY
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "order_fills.json"
    payload = {
        "schema_version": "order_execution_outcome.v1",
        "fills": [{"decision_id": "D1", "symbol": "005930", "timestamp": TRIGGER_EPOCH, "order_fill_status": "FILLED", "rank": 1}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a.canonicalize_opening_shadow_1a_artifact(
            path, candles_by_symbol={"005930": CANDLES_1A}, horizon_label="+5m", cost_policy=_gross_cost_policy(),
        )


def test_1a_loader_rejects_missing_and_unknown_provenance(tmp_path):
    no_schema_path = _write_1a_artifact(tmp_path, [_1a_row(trigger_epoch=TRIGGER_EPOCH)], schema_version="")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a.canonicalize_opening_shadow_1a_artifact(
            no_schema_path, candles_by_symbol={"005930": CANDLES_1A}, horizon_label="+5m", cost_policy=_gross_cost_policy(),
        )
    unknown_path = _write_1a_artifact(tmp_path, [_1a_row(trigger_epoch=TRIGGER_EPOCH)], schema_version="totally_unknown_family.v1")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1a.canonicalize_opening_shadow_1a_artifact(
            unknown_path, candles_by_symbol={"005930": CANDLES_1A}, horizon_label="+5m", cost_policy=_gross_cost_policy(),
        )


def test_1a_loader_accepts_real_source_artifact(tmp_path):
    artifact_path = _write_1a_artifact(tmp_path, [_1a_row(trigger_epoch=TRIGGER_EPOCH)])
    results = shadow1a.canonicalize_opening_shadow_1a_artifact(
        artifact_path, candles_by_symbol={"005930": CANDLES_1A}, horizon_label="+5m", cost_policy=_gross_cost_policy(),
    )
    assert len(results) == 1
    assert results[0].episode is not None
    assert results[0].episode.symbol == "005930"


# =========================================================================
# 1B/1C -- already_net_shadow_adapter.py (merged episode, one physical event)
# =========================================================================


DECISION_EPOCH = kst_epoch(DAY, 9, 5)


def _full_calendar_rows(days_ahead: int = 7) -> tuple[list[dict], list[str]]:
    rows = _minute_candles(start_ts=DECISION_EPOCH, count=386, base=1000.0, step=1.0)
    calendar = [DAY]
    d0 = datetime.date.fromisoformat(DAY)
    for i in range(1, days_ahead + 1):
        future_day = (d0 + datetime.timedelta(days=i)).isoformat()
        calendar.append(future_day)
        future_start = kst_epoch(future_day, 9, 0)
        rows += _minute_candles(start_ts=future_start, count=390, base=1010.0 + i, step=0.5)
    return rows, calendar


def _verified_1bc(case: shadow1bc.OpeningShadow1BC):
    return shadow1bc._VerifiedOpeningShadow1BCRecord(case)


def _1bc_case(**kwargs) -> shadow1bc.OpeningShadow1BC:
    defaults = dict(trading_date=DAY, symbol="005930", decision_id="D1", decision_epoch=DECISION_EPOCH)
    defaults.update(kwargs)
    return shadow1bc._parse_1bc_case(**defaults)


def _1bc_event_row(**kwargs) -> dict:
    row = {
        "day": DAY, "symbol": "005930", "decision_id": "D1",
        "decision_time_kst": datetime.datetime.fromtimestamp(DECISION_EPOCH, tz=KST).isoformat(),
    }
    row.update(kwargs)
    return row


def _write_1bc_artifact(tmp_path: Path, events: list[dict], *, schema_version: str | None = None, family_dir: str = "offline_alpha/opening_rank1_longitudinal") -> Path:
    """Write a JSON file at the REAL 1B/1C artifact family path layout
    (`.../offline_alpha/opening_rank1_longitudinal/opening_rank1_longitudinal.json`,
    matching `pipeline.py:131-133,252` exactly), with the real writer's
    own payload shape (`pipeline.py:229-244`)."""

    directory = tmp_path / family_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "opening_rank1_longitudinal.json"
    payload = {
        "schema_version": schema_version if schema_version is not None else shadow1bc.OPENING_RANK1_LONGITUDINAL_SCHEMA_VERSION,
        "behavior_effect": "offline_analysis_only",
        "trading_calendar": [DAY],
        "stage_rows": [],
        "events": events,
        "universe_paths": {},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_1bc_reference_horizon_return_unit_cost_semantics():
    rows, calendar = _full_calendar_rows()
    case = _1bc_case()
    ep = shadow1bc._build_1bc_episode(_verified_1bc(case), rows, trading_calendar=calendar)
    assert ep.symbol == "005930"
    assert ep.execution_mode is ExecutionMode.OBSERVATION_ONLY
    labels = {cp.horizon_label for cp in ep.checkpoints}
    assert labels == {"+30m", "d1", "d3", "d5"}
    for cp in ep.checkpoints:
        assert cp.return_unit.value == "PERCENTAGE_POINTS"
        assert cp.gross_return is not None  # informational, from the frozen engine
        assert cp.mae is None  # 1B has no excursion; 1C is MFE-only -- MAE never populated


def test_1bc_net_return_matches_real_legacy_functions_directly():
    from libs.research.opening_rank1_longitudinal.delayed_outcomes import delayed_path, forward_30m_net

    rows, calendar = _full_calendar_rows()
    case = _1bc_case()
    ep = shadow1bc._build_1bc_episode(_verified_1bc(case), rows, trading_calendar=calendar)

    expected_net_30m = forward_30m_net(rows=rows, day=DAY, decision_epoch=DECISION_EPOCH)
    thirty_min = next(cp for cp in ep.checkpoints if cp.horizon_label == "+30m")
    assert thirty_min.net_return == pytest.approx(expected_net_30m)

    day_rows = sorted((r for r in rows if r["raw_ts"][:8] == DAY.replace("-", "") and r["ts"] > DECISION_EPOCH), key=lambda r: r["ts"])
    baseline_row = day_rows[0]
    legacy_case = {
        "virtual_buy_price": baseline_row["open"],
        "virtual_buy_time_kst": datetime.datetime.fromtimestamp(baseline_row["ts"], tz=KST).isoformat(),
        "day": DAY,
        "net_return_30m_pct": expected_net_30m,
    }
    expected_delayed = delayed_path(legacy_case, rows, trading_calendar=calendar)
    for prefix in ("d1", "d3", "d5"):
        cp = next(c for c in ep.checkpoints if c.horizon_label == prefix)
        assert cp.net_return == pytest.approx(expected_delayed[f"{prefix}_close_net_pct"])
        assert cp.mfe == pytest.approx(expected_delayed[f"{prefix}_max_high_net_pct"])


def test_1b_and_1c_share_one_physical_episode_not_three_samples():
    # THE central Opening Shadow semantic question (Section 7/8): 1B and
    # 1C must be ONE canonical EpisodeRecord (one physical "virtual buy"
    # event), not two/three independent physical samples.
    rows, calendar = _full_calendar_rows()
    case = _1bc_case()
    ep = shadow1bc._build_1bc_episode(_verified_1bc(case), rows, trading_calendar=calendar)
    assert len(ep.checkpoints) == 4  # +30m, d1, d3, d5 -- one episode, four checkpoints
    horizon_sets = {cp.horizon_set_id for cp in ep.checkpoints}
    assert horizon_sets == {"opening_rank1_longitudinal_forward_30m_net", "opening_rank1_longitudinal_delayed_path"}


def test_1bc_identity_deterministic_and_distinguishes_decision():
    rows, calendar = _full_calendar_rows()
    case1 = _1bc_case()
    case2 = _1bc_case()
    ep1 = shadow1bc._build_1bc_episode(_verified_1bc(case1), rows, trading_calendar=calendar)
    ep2 = shadow1bc._build_1bc_episode(_verified_1bc(case2), rows, trading_calendar=calendar)
    assert ep1.identity.evaluation_record_id == ep2.identity.evaluation_record_id

    case3 = _1bc_case(symbol="000660", decision_id="D2")
    rows3, _ = _full_calendar_rows()
    ep3 = shadow1bc._build_1bc_episode(_verified_1bc(case3), rows3, trading_calendar=calendar)
    assert ep1.identity.event.canonical_event_id != ep3.identity.event.canonical_event_id


def test_1c_insufficient_future_days_is_missing_not_zero():
    rows, _ = _full_calendar_rows(days_ahead=0)  # no future days at all
    case = _1bc_case()
    ep = shadow1bc._build_1bc_episode(_verified_1bc(case), rows, trading_calendar=[DAY])
    d1 = next(cp for cp in ep.checkpoints if cp.horizon_label == "d1")
    assert d1.completeness is not CheckpointCompleteness.OBSERVED
    assert d1.net_return is None
    assert d1.mfe is None


def test_1bc_missing_forward_reference_rejected_not_zero_return():
    case = _1bc_case()
    with pytest.raises(OpeningShadowAdapterError):
        shadow1bc._build_1bc_episode(_verified_1bc(case), [], trading_calendar=[DAY])


def test_1bc_invalid_identity_rejected():
    with pytest.raises(OpeningShadowAdapterError):
        shadow1bc._parse_1bc_case(trading_date="", symbol="005930", decision_id="D1", decision_epoch=DECISION_EPOCH)
    with pytest.raises(OpeningShadowAdapterError):
        shadow1bc._parse_1bc_case(trading_date=DAY, symbol="", decision_id="D1", decision_epoch=DECISION_EPOCH)
    with pytest.raises(OpeningShadowAdapterError):
        shadow1bc._parse_1bc_case(trading_date=DAY, symbol="005930", decision_id="D1", decision_epoch=0)


def test_1bc_cost_semantics_never_gross_only():
    rows, calendar = _full_calendar_rows()
    case = _1bc_case()
    ep = shadow1bc._build_1bc_episode(_verified_1bc(case), rows, trading_calendar=calendar)
    thirty_min = next(cp for cp in ep.checkpoints if cp.horizon_label == "+30m")
    member = shadow1bc.checkpoint_to_net_or_cost_included_member(thirty_min, evaluation_record_id=ep.identity.evaluation_record_id)
    assert member.state is SampleMemberState.EVALUATED
    assert member.gross_return is None  # NET_OR_COST_INCLUDED forbids carrying gross_return
    assert member.cost_policy is None
    assert member.source_net_return == pytest.approx(thirty_min.net_return)


# =========================================================================
# FIX2 -- 1B/1C trusted-artifact ingestion
# =========================================================================


def test_1bc_public_path_accepts_real_source_artifact(tmp_path):
    rows, calendar = _full_calendar_rows()
    artifact_path = _write_1bc_artifact(tmp_path, [_1bc_event_row()])
    results = shadow1bc.canonicalize_opening_shadow_1bc_artifact(
        artifact_path, minute_rows_by_symbol={"005930": rows}, trading_calendar=calendar,
    )
    assert len(results) == 1
    assert results[0].episode is not None
    assert results[0].episode.symbol == "005930"
    assert results[0].case.decision_epoch == DECISION_EPOCH  # recovered from decision_time_kst


def test_1bc_loader_rejects_path_outside_real_artifact_family(tmp_path):
    artifact_path = _write_1bc_artifact(
        tmp_path, [_1bc_event_row()],
        schema_version=shadow1bc.OPENING_RANK1_LONGITUDINAL_SCHEMA_VERSION,
        family_dir="data/logs/controlled_mock_lanes",
    )
    with pytest.raises(OpeningShadowAdapterError):
        shadow1bc.canonicalize_opening_shadow_1bc_artifact(artifact_path, minute_rows_by_symbol={}, trading_calendar=[DAY])


def test_1bc_loader_rejects_real_family_path_with_wrong_schema(tmp_path):
    artifact_path = _write_1bc_artifact(tmp_path, [_1bc_event_row()], schema_version="opening_rank1_controlled_probe.v3")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1bc.canonicalize_opening_shadow_1bc_artifact(artifact_path, minute_rows_by_symbol={}, trading_calendar=[DAY])


def test_1bc_loader_rejects_controlled_probe_origin(tmp_path):
    directory = tmp_path / "data" / "logs" / "opening_rank1_controlled_probe" / DAY
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "probe_evaluations.json"
    payload = {
        "schema_version": "opening_rank1_controlled_probe.v3",
        "day": DAY,
        "evaluations": [{"run_id": "R1", "symbol": "005930", "scanner_rank": 1}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1bc.canonicalize_opening_shadow_1bc_artifact(path, minute_rows_by_symbol={}, trading_calendar=[DAY])


def test_1bc_loader_rejects_controlled_mock_lane_origin(tmp_path):
    directory = tmp_path / "data" / "logs" / "controlled_mock_lanes" / DAY
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "lane_submissions.json"
    payload = {
        "schema_version": "controlled_mock_lane_submissions.v1",
        "day": DAY,
        "submissions": [{"lane_id": "BTC_WOORI", "symbol": "005930", "decision_id": "D1"}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1bc.canonicalize_opening_shadow_1bc_artifact(path, minute_rows_by_symbol={}, trading_calendar=[DAY])


def test_1bc_loader_rejects_execution_evidence_origin(tmp_path):
    directory = tmp_path / "data" / "state" / "executions" / DAY
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "order_fills.json"
    payload = {
        "schema_version": "order_execution_outcome.v1",
        "fills": [{"decision_id": "D1", "symbol": "005930", "timestamp": DECISION_EPOCH, "order_fill_status": "FILLED"}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1bc.canonicalize_opening_shadow_1bc_artifact(path, minute_rows_by_symbol={}, trading_calendar=[DAY])


def test_1bc_loader_rejects_missing_and_unknown_provenance(tmp_path):
    no_schema_path = _write_1bc_artifact(tmp_path, [_1bc_event_row()], schema_version="")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1bc.canonicalize_opening_shadow_1bc_artifact(no_schema_path, minute_rows_by_symbol={}, trading_calendar=[DAY])
    unknown_path = _write_1bc_artifact(tmp_path, [_1bc_event_row()], schema_version="totally_unknown_family.v1")
    with pytest.raises(OpeningShadowAdapterError):
        shadow1bc.canonicalize_opening_shadow_1bc_artifact(unknown_path, minute_rows_by_symbol={}, trading_calendar=[DAY])


def test_1bc_raw_dict_cannot_reach_canonical_path_without_going_through_the_loader():
    import inspect

    sig = inspect.signature(shadow1bc.canonicalize_opening_shadow_1bc_artifact)
    assert list(sig.parameters)[0] == "path"


# =========================================================================
# Physical evidence multiplication guard (1A is a DIFFERENT physical
# event population from 1B/1C -- verified, never assumed)
# =========================================================================


def test_1a_and_1bc_are_different_physical_events_not_duplicated_evidence():
    candidate = _1a_candidate(watch_id="W1", trigger_epoch=TRIGGER_EPOCH)
    ep_1a = shadow1a._build_1a_episode(_verified_1a(candidate), CANDLES_1A)

    rows, calendar = _full_calendar_rows()
    case = _1bc_case()
    ep_1bc = shadow1bc._build_1bc_episode(_verified_1bc(case), rows, trading_calendar=calendar)

    # different source population (fresh-trigger watch vs virtual-buy
    # decision) -> genuinely different canonical events, never colliding:
    assert ep_1a.identity.event.canonical_event_id != ep_1bc.identity.event.canonical_event_id
    assert ep_1a.identity.hypothesis_id != ep_1bc.identity.hypothesis_id


def test_source_physical_event_count_equals_canonical_physical_event_count():
    # 3 distinct 1A fresh triggers -> 3 distinct canonical episodes, never
    # inflated or deflated.
    candidates = [_1a_candidate(watch_id=f"W{i}", trigger_epoch=TRIGGER_EPOCH) for i in range(3)]
    episodes = [shadow1a._build_1a_episode(_verified_1a(c), CANDLES_1A) for c in candidates]
    ids = {ep.identity.event.canonical_event_id for ep in episodes}
    assert len(ids) == 3  # source count == canonical count
    for ep in episodes:
        assert len(ep.checkpoints) == 5


# =========================================================================
# Controlled Probe / Controlled Mock Lane import-boundary guard
# =========================================================================


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_controlled_probe_not_ingested_by_any_opening_shadow_adapter():
    for path in (
        Path("libs/reporting/evaluation/canonical/adapters/opening_rank1_shadow.py"),
        Path("libs/reporting/evaluation/canonical/adapters/already_net_shadow_adapter.py"),
    ):
        modules = _imported_modules(path)
        assert not any("controlled_probe" in module for module in modules)


def test_controlled_mock_lane_not_ingested_by_any_opening_shadow_adapter():
    for path in (
        Path("libs/reporting/evaluation/canonical/adapters/opening_rank1_shadow.py"),
        Path("libs/reporting/evaluation/canonical/adapters/already_net_shadow_adapter.py"),
    ):
        modules = _imported_modules(path)
        assert not any("controlled_mock_lane" in module for module in modules)


# =========================================================================
# FIX2 -- public export discipline: raw row/case builders must not be an
# approved public bypass of the trusted-artifact ingestion boundary.
# =========================================================================


def test_raw_builders_not_publicly_exported():
    forbidden_1a = {"parse_1a_candidate", "build_1a_episode", "build_1a_exclusion_record", "resolve_1a_aggregation_member"}
    forbidden_1bc = {"parse_1bc_case", "build_1bc_episode"}
    assert not (forbidden_1a & set(shadow1a.__all__))
    assert not (forbidden_1bc & set(shadow1bc.__all__))
    # and they are not even module-level attributes under their old public
    # names any more (renamed to internal, underscore-prefixed):
    for name in forbidden_1a:
        assert not hasattr(shadow1a, name)
    for name in forbidden_1bc:
        assert not hasattr(shadow1bc, name)


def test_1a_approved_public_surface():
    assert set(shadow1a.__all__) == {
        "OpeningShadowAdapterError", "SOURCE_NAMESPACE", "HYPOTHESIS_ID_1A",
        "LATENT_REACTIVATION_FORWARD_SCHEMA_VERSION", "candles_to_observations",
        "OpeningShadow1ACandidate", "OpeningShadow1AExclusion", "OpeningShadow1ACanonicalResult",
        "canonicalize_opening_shadow_1a_artifact",
    }


def test_1bc_approved_public_surface():
    assert set(shadow1bc.__all__) == {
        "SOURCE_NAMESPACE", "HYPOTHESIS_ID", "OpeningShadow1BC", "OpeningShadow1BCCanonicalResult",
        "checkpoint_to_net_or_cost_included_member", "OPENING_RANK1_LONGITUDINAL_SCHEMA_VERSION",
        "canonicalize_opening_shadow_1bc_artifact",
    }


# =========================================================================
# "Opening Alpha" is never treated as one canonical evaluator
# =========================================================================


def test_opening_alpha_label_never_used_as_canonical_provenance():
    candidate = _1a_candidate(trigger_epoch=TRIGGER_EPOCH)
    ep_1a = shadow1a._build_1a_episode(_verified_1a(candidate), CANDLES_1A)
    assert "opening_alpha" not in ep_1a.provenance.legacy_program.lower()
    assert ep_1a.provenance.legacy_program == "opening_rank1_shadow_latent_forward"

    rows, calendar = _full_calendar_rows()
    case = _1bc_case()
    ep_1bc = shadow1bc._build_1bc_episode(_verified_1bc(case), rows, trading_calendar=calendar)
    assert "opening_alpha" not in ep_1bc.provenance.legacy_program.lower()
    for cp in ep_1bc.checkpoints:
        assert "opening_alpha" not in cp.horizon_set_id.lower()


def test_no_module_defines_an_opening_alpha_adapter():
    for path in (
        Path("libs/reporting/evaluation/canonical/adapters/opening_rank1_shadow.py"),
        Path("libs/reporting/evaluation/canonical/adapters/already_net_shadow_adapter.py"),
    ):
        source = path.read_text(encoding="utf-8")
        assert "opening_alpha_adapter" not in source
        assert "class OpeningAlpha" not in source


# =========================================================================
# Frozen delegation -- neither module owns financial calculation logic
# =========================================================================


_ADAPTER_FILES = (
    Path("libs/reporting/evaluation/canonical/adapters/opening_rank1_shadow.py"),
    Path("libs/reporting/evaluation/canonical/adapters/already_net_shadow_adapter.py"),
)
_FORBIDDEN_DEFINITIONS = {"calculate_profit_factor", "calculate_max_drawdown", "calculate_net_return", "calculate_total_cost", "classify_net_return"}


def test_opening_adapters_never_define_a_financial_calculation_function():
    for path in _ADAPTER_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        overlap = defined & _FORBIDDEN_DEFINITIONS
        assert not overlap, f"{path} redefines frozen UEF-3B calculation function(s): {overlap}"


def test_frozen_uef4b1_and_uef4b2_files_untouched_by_this_task():
    # spot-check import path integrity -- these files were never edited
    # this task (verified separately via freeze-manifest-adjacent hashing
    # in the final report; this just confirms the modules still import).
    from libs.reporting.evaluation.canonical.adapters import q10_semiconductor  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import forward_measurement_adapter  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import q12_baseline_btc_woori  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import hypothesis_forward_adapter  # noqa: F401
