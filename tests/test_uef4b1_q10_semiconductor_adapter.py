"""UEF-4B-1 -- Q10 Semiconductor canonical adapter tests.

Covers: deterministic identity, forward/cost/missing/excluded semantic
mapping, Calc A/B/C view preservation (no duplicate primary evidence),
frozen-delegation (the adapter never computes PF/MDD/win-loss itself),
and fail-fast invalid-input handling. Real legacy artifact fixture
values (`reports/evaluation/baseline_samsung_hynix/2026-06-24/
baseline_samsung_hynix_forward_returns.json`) inform the shapes used
below, per this task's own "verify actual source" mandate.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from libs.reporting.evaluation.canonical.contracts import CheckpointCompleteness, ExecutionMode
from libs.reporting.evaluation.canonical.metrics import CostPolicy, MetricPolicy
from libs.reporting.evaluation.canonical.metrics.contracts import CostTiming
from libs.reporting.evaluation.canonical.contracts import ReturnUnit

from libs.reporting.evaluation.canonical.adapters import q10_semiconductor as q10
from libs.reporting.evaluation.canonical.adapters.q10_semiconductor import (
    Q10SemiconductorAdapterError,
    Q10SemiconductorView,
    adapt_q10_semiconductor_decisions,
    build_q10_semiconductor_episode,
    parse_decision_candidates,
)


def _cost_policy(**overrides) -> CostPolicy:
    defaults = dict(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.1, slippage=0.05, provenance="test_fixture")
    defaults.update(overrides)
    return CostPolicy(**defaults)


def _candles(*, base_epoch: int, base_price: float, step: float, count: int = 70) -> list[dict]:
    return [
        {
            "ts": base_epoch + i * 60,
            "open": base_price + step * i,
            "close": base_price + step * i,
            "high": base_price + step * i + 1,
            "low": base_price + step * i - 1,
            "volume": 100.0,
        }
        for i in range(count)
    ]


def _decision(*, decision_id: str, day: str, base_epoch: int, symbol_a_eligible: bool = True, symbol_b_eligible: bool = False) -> dict:
    return {
        "decision_id": decision_id,
        "day": day,
        "ranked_candidates": [
            {
                "symbol": "005930", "ticker": "005930.KS", "rank": 1, "eligible": symbol_a_eligible, "action": "SHADOW_ENTER",
                "features": {"available": True, "baseline_epoch": base_epoch, "baseline_price": 320000.0},
            },
            {
                "symbol": "000660", "ticker": "000660.KS", "rank": 2, "eligible": symbol_b_eligible, "action": "NO_ENTRY",
                "features": {"available": True, "baseline_epoch": base_epoch, "baseline_price": 180000.0},
            },
        ],
    }


BASE_EPOCH = 1782259500
MINUTE_ROWS = {
    "005930": _candles(base_epoch=BASE_EPOCH, base_price=320000.0, step=50.0),
    "000660": _candles(base_epoch=BASE_EPOCH, base_price=180000.0, step=-30.0),
}


# =========================================================================
# Identity
# =========================================================================


def test_identity_is_deterministic_for_same_source():
    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    ep1 = build_q10_semiconductor_episode(candidates[0], MINUTE_ROWS["005930"])
    ep2 = build_q10_semiconductor_episode(candidates[0], MINUTE_ROWS["005930"])
    assert ep1.identity.evaluation_record_id == ep2.identity.evaluation_record_id
    assert ep1.identity.event.canonical_event_id == ep2.identity.event.canonical_event_id


def test_identity_differs_for_different_symbol():
    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    ep_a = build_q10_semiconductor_episode(candidates[0], MINUTE_ROWS["005930"])
    ep_b = build_q10_semiconductor_episode(candidates[1], MINUTE_ROWS["000660"])
    assert ep_a.identity.event.canonical_event_id != ep_b.identity.event.canonical_event_id
    assert ep_a.identity.evaluation_record_id != ep_b.identity.evaluation_record_id


def test_identity_differs_for_different_decision_same_symbol():
    c1 = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))[0]
    c2 = parse_decision_candidates(_decision(decision_id="D2", day="2026-06-24", base_epoch=BASE_EPOCH + 300))[0]
    ep1 = build_q10_semiconductor_episode(c1, MINUTE_ROWS["005930"])
    ep2 = build_q10_semiconductor_episode(c2, MINUTE_ROWS["005930"])
    assert ep1.identity.event.canonical_event_id != ep2.identity.event.canonical_event_id


def test_missing_decision_id_rejected():
    bad = _decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH)
    bad["decision_id"] = ""
    with pytest.raises(Q10SemiconductorAdapterError):
        parse_decision_candidates(bad)


def test_missing_symbol_rejected():
    bad = _decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH)
    bad["ranked_candidates"][0]["symbol"] = ""
    with pytest.raises(Q10SemiconductorAdapterError):
        parse_decision_candidates(bad)


# =========================================================================
# Semantics: horizon / reference / return-unit / cost / missing / excluded
# =========================================================================


def test_horizon_mapping_covers_all_seven_frozen_labels():
    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    episode = build_q10_semiconductor_episode(candidates[0], MINUTE_ROWS["005930"])
    labels = {cp.horizon_label for cp in episode.checkpoints}
    assert labels == set(q10.all_horizon_labels())
    assert labels == {"+5m", "+15m", "+30m", "+60m", "+120m", "+180m", "EOD"}


def test_reference_price_mapping_uses_candidate_baseline_not_first_candle():
    # baseline_price=320000 (from features), NOT the first candle's own
    # close (320000 + 50*0 == same here by fixture construction, so use a
    # deliberately different first-candle price to prove the reference
    # comes from the candidate's own baseline, not the candle series).
    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    rows = _candles(base_epoch=BASE_EPOCH, base_price=999999.0, step=0.0)
    # overwrite the FIRST candle to be far from the declared baseline_price
    rows[0] = dict(rows[0])
    episode = build_q10_semiconductor_episode(candidates[0], rows)
    five_min = next(cp for cp in episode.checkpoints if cp.horizon_label == "+5m")
    # gross_return is computed against baseline_price=320000, never 999999
    assert five_min.gross_return == pytest.approx(((999999.0 / 320000.0) - 1.0) * 100.0)


def test_return_unit_is_percentage_points():
    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    episode = build_q10_semiconductor_episode(candidates[0], MINUTE_ROWS["005930"])
    for checkpoint in episode.checkpoints:
        assert checkpoint.return_unit is ReturnUnit.PERCENTAGE_POINTS


def test_cost_semantics_gross_only_requires_external_cost_policy_for_net():
    result = adapt_q10_semiconductor_decisions(
        [_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH)],
        minute_rows_by_symbol=MINUTE_ROWS, cost_policy=_cost_policy(), metric_policy=MetricPolicy(),
        aggregation_window_start="2026-06-24",
    )
    agg = result.aggregates[(Q10SemiconductorView.TOP1.value, "+5m")]
    assert agg.metrics["context"]["cost_policy_id"] == _cost_policy().policy_id
    # episode's own checkpoint carries gross_return only, never a net figure
    ep = next(e for e in result.episodes if e.symbol == "005930")
    five_min = next(cp for cp in ep.checkpoints if cp.horizon_label == "+5m")
    assert five_min.net_return is None
    assert five_min.gross_return is not None


def test_missing_semantics_never_becomes_zero_return():
    # +120m/+180m never resolve in this fixture (candle series too short
    # relative to origin -- see test setup: 70 minutes of candles, +120m
    # target is 120 minutes out).
    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    episode = build_q10_semiconductor_episode(candidates[0], MINUTE_ROWS["005930"])
    plus_120 = next(cp for cp in episode.checkpoints if cp.horizon_label == "+120m")
    assert plus_120.completeness is not CheckpointCompleteness.OBSERVED
    assert plus_120.gross_return is None  # never fabricated as 0.0


def test_excluded_semantics_ineligible_candidate_is_excluded_not_missing():
    decision = _decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH, symbol_a_eligible=True, symbol_b_eligible=False)
    result = adapt_q10_semiconductor_decisions(
        [decision], minute_rows_by_symbol=MINUTE_ROWS, cost_policy=_cost_policy(), metric_policy=MetricPolicy(),
        aggregation_window_start="2026-06-24", views=(Q10SemiconductorView.ELIGIBLE_ENTRIES,),
    )
    agg = result.aggregates[(Q10SemiconductorView.ELIGIBLE_ENTRIES.value, "+5m")]
    population = agg.metrics["sample_population"]
    assert population["excluded_count"] == 1
    assert population["missing_count"] == 0
    assert population["evaluated_count"] == 1
    assert population["exclusion_note"]


def test_unavailable_baseline_candidate_is_missing_not_dropped():
    decision = _decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH)
    decision["ranked_candidates"][1]["features"] = {"available": False, "reason": "insufficient_candles"}
    result = adapt_q10_semiconductor_decisions(
        [decision], minute_rows_by_symbol=MINUTE_ROWS, cost_policy=_cost_policy(), metric_policy=MetricPolicy(),
        aggregation_window_start="2026-06-24", views=(Q10SemiconductorView.ELIGIBLE_ENTRIES,),
    )
    # only one episode built (005930) -- 000660 never resolved a reference
    assert len(result.episodes) == 1
    agg = result.aggregates[(Q10SemiconductorView.ELIGIBLE_ENTRIES.value, "+5m")]
    population = agg.metrics["sample_population"]
    # 000660 is eligible=False by _decision()'s own default -> EXCLUDED wins
    # over MISSING (policy exclusion is checked before checkpoint availability)
    assert population["sample_count"] == 2
    assert population["excluded_count"] == 1
    assert population["evaluated_count"] == 1


def test_unavailable_baseline_candidate_is_missing_when_eligible():
    decision = _decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH, symbol_b_eligible=True)
    decision["ranked_candidates"][1]["features"] = {"available": False, "reason": "insufficient_candles"}
    result = adapt_q10_semiconductor_decisions(
        [decision], minute_rows_by_symbol=MINUTE_ROWS, cost_policy=_cost_policy(), metric_policy=MetricPolicy(),
        aggregation_window_start="2026-06-24", views=(Q10SemiconductorView.ELIGIBLE_ENTRIES,),
    )
    agg = result.aggregates[(Q10SemiconductorView.ELIGIBLE_ENTRIES.value, "+5m")]
    population = agg.metrics["sample_population"]
    assert population["missing_count"] == 1
    assert population["excluded_count"] == 0


# =========================================================================
# Views (Calc A/B/C + three legacy views) -- no duplicate primary evidence
# =========================================================================


def test_calc_a_b_c_horizon_sets_preserved_as_provenance():
    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    episode = build_q10_semiconductor_episode(candidates[0], MINUTE_ROWS["005930"])
    by_label = {cp.horizon_label: cp for cp in episode.checkpoints}
    assert by_label["+5m"].horizon_set_id == "baseline_samsung_hynix_calc_a"
    assert by_label["+120m"].horizon_set_id == "baseline_samsung_hynix_calc_b"
    assert by_label["EOD"].horizon_set_id == "baseline_samsung_hynix_calc_c"


def test_three_views_do_not_multiply_episode_count():
    decision = _decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH)
    result = adapt_q10_semiconductor_decisions(
        [decision], minute_rows_by_symbol=MINUTE_ROWS, cost_policy=_cost_policy(), metric_policy=MetricPolicy(),
        aggregation_window_start="2026-06-24",
    )
    # exactly 2 candidates -> exactly 2 EpisodeRecords, regardless of the
    # fact that 3 views x 7 horizons were aggregated from them
    assert len(result.episodes) == 2
    assert len(result.aggregates) == 3 * len(q10.all_horizon_labels())


def test_top1_view_is_one_member_per_decision_not_per_candidate():
    decision = _decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH)
    result = adapt_q10_semiconductor_decisions(
        [decision], minute_rows_by_symbol=MINUTE_ROWS, cost_policy=_cost_policy(), metric_policy=MetricPolicy(),
        aggregation_window_start="2026-06-24", views=(Q10SemiconductorView.TOP1,),
    )
    agg = result.aggregates[(Q10SemiconductorView.TOP1.value, "+5m")]
    assert agg.metrics["sample_population"]["sample_count"] == 1  # one decision -> one top1 member


def test_both_symbol_average_is_mean_of_observed_candidates():
    decision = _decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH)
    candidates = parse_decision_candidates(decision)
    ep_a = build_q10_semiconductor_episode(candidates[0], MINUTE_ROWS["005930"])
    ep_b = build_q10_semiconductor_episode(candidates[1], MINUTE_ROWS["000660"])
    gross_a = next(cp.gross_return for cp in ep_a.checkpoints if cp.horizon_label == "+5m")
    gross_b = next(cp.gross_return for cp in ep_b.checkpoints if cp.horizon_label == "+5m")
    expected_mean = (gross_a + gross_b) / 2.0

    result = adapt_q10_semiconductor_decisions(
        [decision], minute_rows_by_symbol=MINUTE_ROWS, cost_policy=_cost_policy(commission=0.0, slippage=0.0), metric_policy=MetricPolicy(),
        aggregation_window_start="2026-06-24", views=(Q10SemiconductorView.BOTH_SYMBOL_AVERAGE,),
    )
    agg = result.aggregates[(Q10SemiconductorView.BOTH_SYMBOL_AVERAGE.value, "+5m")]
    # zero cost policy -> net == gross == the plain mean computed above
    assert agg.metrics["profit_factor"]["sample"]["evaluated_count"] == 1
    win_loss = agg.metrics["profit_factor"]["population"]
    expected_win_loss = "win_count" if expected_mean > 0 else ("loss_count" if expected_mean < 0 else "flat_count")
    assert win_loss[expected_win_loss] == 1


def test_top1_rejects_decision_without_exactly_one_rank1_candidate():
    decision = _decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH)
    decision["ranked_candidates"][1]["rank"] = 1  # now two rank==1 candidates
    with pytest.raises(Q10SemiconductorAdapterError):
        adapt_q10_semiconductor_decisions(
            [decision], minute_rows_by_symbol=MINUTE_ROWS, cost_policy=_cost_policy(), metric_policy=MetricPolicy(),
            aggregation_window_start="2026-06-24", views=(Q10SemiconductorView.TOP1,),
        )


# =========================================================================
# Frozen delegation -- the adapter never computes PF/MDD/win-loss itself
# =========================================================================


_ADAPTER_FILES = (
    Path("libs/reporting/evaluation/canonical/adapters/forward_measurement_adapter.py"),
    Path("libs/reporting/evaluation/canonical/adapters/q10_semiconductor.py"),
)
_FORBIDDEN_DEFINITIONS = {"calculate_profit_factor", "calculate_max_drawdown", "calculate_net_return", "calculate_total_cost", "classify_net_return"}


def test_adapter_never_defines_a_financial_calculation_function():
    for path in _ADAPTER_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        overlap = defined & _FORBIDDEN_DEFINITIONS
        assert not overlap, f"{path} redefines frozen UEF-3B calculation function(s): {overlap}"


def test_adapter_delegates_aggregation_to_frozen_entry_point():
    tree = ast.parse(Path("libs/reporting/evaluation/canonical/adapters/q10_semiconductor.py").read_text(encoding="utf-8"))
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "aggregate_canonical_samples" in calls


def test_pf_and_mdd_values_trace_to_aggregate_canonical_samples_shape():
    decision = _decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH)
    result = adapt_q10_semiconductor_decisions(
        [decision], minute_rows_by_symbol=MINUTE_ROWS, cost_policy=_cost_policy(), metric_policy=MetricPolicy(),
        aggregation_window_start="2026-06-24", views=(Q10SemiconductorView.TOP1,),
    )
    agg = result.aggregates[(Q10SemiconductorView.TOP1.value, "+5m")]
    # exact shape produced only by aggregate_canonical_samples's own packaging
    assert set(agg.metrics.keys()) == {"metric_contract_schema_version", "context", "sample_population", "profit_factor", "max_drawdown"}
    assert agg.metric_semantics == "UEF3A_CANONICAL_V1"


# =========================================================================
# Invalid cases
# =========================================================================


def test_unknown_schema_missing_ranked_candidates_rejected():
    with pytest.raises(Q10SemiconductorAdapterError):
        parse_decision_candidates({"decision_id": "D1", "day": "2026-06-24"})


def test_invalid_rank_rejected():
    decision = _decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH)
    decision["ranked_candidates"][0]["rank"] = 0
    with pytest.raises(Q10SemiconductorAdapterError):
        parse_decision_candidates(decision)


def test_contradictory_available_and_missing_baseline_rejected():
    decision = _decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH)
    decision["ranked_candidates"][0]["features"] = {"available": True, "baseline_epoch": None, "baseline_price": None}
    with pytest.raises(Q10SemiconductorAdapterError):
        parse_decision_candidates(decision)


def test_building_episode_for_unavailable_candidate_rejected():
    decision = _decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH)
    decision["ranked_candidates"][0]["features"] = {"available": False, "reason": "insufficient_candles"}
    candidates = parse_decision_candidates(decision)
    with pytest.raises(Q10SemiconductorAdapterError):
        build_q10_semiconductor_episode(candidates[0], MINUTE_ROWS["005930"])


def test_execution_mode_is_shadow_never_broker_live():
    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    episode = build_q10_semiconductor_episode(candidates[0], MINUTE_ROWS["005930"])
    assert episode.execution_mode is ExecutionMode.SHADOW


# =========================================================================
# FIX1 -- invalid candle timestamp must be rejected, never silently dropped
# =========================================================================


def test_zero_candle_timestamp_is_rejected_not_dropped():
    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    rows = _candles(base_epoch=BASE_EPOCH, base_price=320000.0, step=50.0)
    rows[10] = dict(rows[10], ts=0)
    with pytest.raises(Q10SemiconductorAdapterError):
        build_q10_semiconductor_episode(candidates[0], rows)


def test_negative_candle_timestamp_is_rejected_not_dropped():
    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    rows = _candles(base_epoch=BASE_EPOCH, base_price=320000.0, step=50.0)
    rows[10] = dict(rows[10], ts=-1782259500)
    with pytest.raises(Q10SemiconductorAdapterError):
        build_q10_semiconductor_episode(candidates[0], rows)


def test_missing_candle_timestamp_key_is_rejected_not_dropped():
    # a candle with no "ts" key at all resolves to int(None or 0) == 0,
    # which must be rejected exactly like an explicit ts=0 -- never
    # silently treated as "no timestamp, skip this row".
    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    rows = _candles(base_epoch=BASE_EPOCH, base_price=320000.0, step=50.0)
    del rows[10]["ts"]
    with pytest.raises(Q10SemiconductorAdapterError):
        build_q10_semiconductor_episode(candidates[0], rows)


def test_invalid_timestamp_reproduces_the_previously_silently_accepted_path():
    """FIX1 regression: before this fix, a candle with ts<=0 was silently
    dropped via `continue`, and the episode was still accepted (the
    reduced candle series could change which observation a horizon
    resolves to, its MFE/MAE, or its missing state, all invisibly). This
    exact shape -- otherwise-valid candidate + candle data, one bad
    timestamp in the middle of an otherwise-complete series -- must now
    raise instead of silently building an episode."""

    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    valid_rows = _candles(base_epoch=BASE_EPOCH, base_price=320000.0, step=50.0)
    poisoned_rows = [dict(row) for row in valid_rows]
    poisoned_rows[5]["ts"] = 0  # exactly the +5m checkpoint's own candle

    with pytest.raises(Q10SemiconductorAdapterError):
        build_q10_semiconductor_episode(candidates[0], poisoned_rows)

    # sanity: the same candidate + the original, unpoisoned series still
    # builds a normal episode -- proves the rejection is specific to the
    # invalid timestamp, not a regression in the happy path.
    episode = build_q10_semiconductor_episode(candidates[0], valid_rows)
    five_min = next(cp for cp in episode.checkpoints if cp.horizon_label == "+5m")
    assert five_min.completeness is CheckpointCompleteness.OBSERVED


def test_valid_positive_timestamps_remain_accepted():
    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    episode = build_q10_semiconductor_episode(candidates[0], MINUTE_ROWS["005930"])
    five_min = next(cp for cp in episode.checkpoints if cp.horizon_label == "+5m")
    assert five_min.completeness is CheckpointCompleteness.OBSERVED
    assert five_min.gross_return is not None


def test_invalid_timestamp_is_never_normalized_or_repaired():
    # abs(ts), a default/current-time substitution, or coercion to the
    # baseline timestamp must never mask an invalid candle -- the only
    # allowed outcome is rejection.
    candidates = parse_decision_candidates(_decision(decision_id="D1", day="2026-06-24", base_epoch=BASE_EPOCH))
    rows = _candles(base_epoch=BASE_EPOCH, base_price=320000.0, step=50.0)
    rows[0]["ts"] = -1  # abs(-1) == 1, a valid-looking epoch if silently repaired
    with pytest.raises(Q10SemiconductorAdapterError):
        build_q10_semiconductor_episode(candidates[0], rows)
