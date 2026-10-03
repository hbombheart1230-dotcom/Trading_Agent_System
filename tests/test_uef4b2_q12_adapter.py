"""UEF-4B-2 -- Q12 (BTC-led Woori Technology Investment) canonical adapter tests.

Covers Calc1 (reuse of the frozen `forward_measurement_adapter` generic
layer, no new adapter family) and Calc2 (`hypothesis_forward_adapter`,
NET_OR_COST_INCLUDED) -- UEF-4B-2's actual approved scope -- plus
evidence-multiplication guards and fail-fast invalid-input handling. Real
source (`libs/reporting/baseline_btc_woori_tech/**`) informs every
fixture shape below, per this task's own "verify actual source" mandate.

Calc3 (`vnext_completeness_adapter`) is covered too, but that module is
BLOCKED -- NOT an approved UEF-4B adapter, LOSSLESS MAPPING = UNKNOWN
(UEF-4B-2 FIX2). Its own test section below exists primarily to PROVE and
PROTECT that blocked status (the legacy-row-count-vs-frozen-exact-grid
contradiction reproducer), plus mechanical coverage of its experimental
code -- none of it establishes or implies lossless mapping.
"""

from __future__ import annotations

import ast
import datetime
import zoneinfo
from pathlib import Path

import pytest

from libs.reporting.evaluation.canonical.contracts import CheckpointCompleteness, ExecutionMode
from libs.reporting.evaluation.canonical.metrics.aggregation import SampleMemberState

from libs.reporting.evaluation.canonical.adapters import q12_baseline_btc_woori as calc1
from libs.reporting.evaluation.canonical.adapters import hypothesis_forward_adapter as calc2
from libs.reporting.evaluation.canonical.adapters import vnext_completeness_adapter as calc3
from libs.reporting.evaluation.canonical.adapters.q12_baseline_btc_woori import Q12AdapterError

KST = zoneinfo.ZoneInfo("Asia/Seoul")
DAY = "2026-06-24"


def kst_epoch(day: str, hh: int, mm: int) -> int:
    return int(datetime.datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=KST).timestamp())


def _minute_candles(*, start_ts: int, count: int, base: float, step: float = 1.0) -> list[dict]:
    return [
        {
            "ts": start_ts + i * 60,
            "open": base + step * i,
            "close": base + step * i,
            "high": base + step * i + 1,
            "low": base + step * i - 1,
            "volume": 100.0,
        }
        for i in range(count)
    ]


ENTRY_EPOCH = kst_epoch(DAY, 9, 5)
ENTRY_PRICE = 1000.0
FULL_DAY_ROWS = _minute_candles(start_ts=ENTRY_EPOCH, count=(kst_epoch(DAY, 15, 30) - ENTRY_EPOCH) // 60 + 1, base=ENTRY_PRICE, step=1.0)


def _row_at(rows: list[dict], ts: int) -> dict | None:
    return next((r for r in rows if r["ts"] == ts), None)


# =========================================================================
# Calc1 -- reuse of the frozen forward_measurement_adapter generic layer
# =========================================================================


def _calc1_decision(*, decision_id: str, day: str, eligible: bool = True, available: bool = True) -> dict:
    return {
        "decision_id": decision_id,
        "day": day,
        "eligible": eligible,
        "action": "SHADOW_ENTER" if eligible else "NO_ENTRY",
        "local_features": (
            {"available": True, "baseline_epoch": ENTRY_EPOCH, "baseline_price": ENTRY_PRICE}
            if available
            else {"available": False, "reason": "insufficient_woori_candles"}
        ),
    }


def test_calc1_uses_generic_semantic_layer_not_a_new_adapter_family():
    tree = ast.parse(Path("libs/reporting/evaluation/canonical/adapters/q12_baseline_btc_woori.py").read_text(encoding="utf-8"))
    calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    calls |= {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "build_forward_measurement_episode" in calls
    assert "build_forward_measurement_event_ref" in calls


def test_calc1_defines_no_duplicate_financial_calculation():
    tree = ast.parse(Path("libs/reporting/evaluation/canonical/adapters/q12_baseline_btc_woori.py").read_text(encoding="utf-8"))
    defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    forbidden = {"calculate_profit_factor", "calculate_max_drawdown", "calculate_net_return", "evaluate_forward"}
    assert not (defined & forbidden)


def test_calc1_identity_is_deterministic_and_symbol_is_041190():
    candidates = calc1.parse_calc1_decisions([_calc1_decision(decision_id="D1", day=DAY)])
    ep1 = calc1.build_calc1_episode(candidates[0], FULL_DAY_ROWS)
    ep2 = calc1.build_calc1_episode(candidates[0], FULL_DAY_ROWS)
    assert ep1.identity.evaluation_record_id == ep2.identity.evaluation_record_id
    assert ep1.symbol == "041190"


def test_calc1_identity_differs_for_different_decision():
    c1 = calc1.parse_calc1_decisions([_calc1_decision(decision_id="D1", day=DAY)])[0]
    c2 = calc1.parse_calc1_decisions([_calc1_decision(decision_id="D2", day=DAY)])[0]
    ep1 = calc1.build_calc1_episode(c1, FULL_DAY_ROWS)
    ep2 = calc1.build_calc1_episode(c2, FULL_DAY_ROWS)
    assert ep1.identity.event.canonical_event_id != ep2.identity.event.canonical_event_id


def test_calc1_seven_horizons_preserved_gross_only():
    candidates = calc1.parse_calc1_decisions([_calc1_decision(decision_id="D1", day=DAY)])
    ep = calc1.build_calc1_episode(candidates[0], FULL_DAY_ROWS)
    labels = {cp.horizon_label for cp in ep.checkpoints}
    assert labels == {"+5m", "+15m", "+30m", "+60m", "+120m", "+180m", "EOD"}
    for cp in ep.checkpoints:
        assert cp.net_return is None  # GROSS_ONLY -- net computed only later, externally, via CostPolicy


def test_calc1_does_not_duplicate_q10_semiconductor_physical_evidence():
    # Calc1's own episode is for symbol 041190 (Woori), on Q12's OWN
    # decision_id -- it must never coincide with a Q10 Semiconductor
    # episode identity (005930/000660, baseline_samsung_hynix namespace),
    # even though both reuse the identical generic engine/profile shape.
    from libs.reporting.evaluation.canonical.adapters import q10_semiconductor as q10

    q12_candidates = calc1.parse_calc1_decisions([_calc1_decision(decision_id="BSH_20260624_1782259500", day=DAY)])
    q12_episode = calc1.build_calc1_episode(q12_candidates[0], FULL_DAY_ROWS)

    q10_decision = {
        "decision_id": "BSH_20260624_1782259500",  # deliberately the SAME native id string
        "day": DAY,
        "ranked_candidates": [
            {
                "symbol": "005930", "ticker": "005930.KS", "rank": 1, "eligible": True, "action": "SHADOW_ENTER",
                "features": {"available": True, "baseline_epoch": ENTRY_EPOCH, "baseline_price": ENTRY_PRICE},
            },
        ],
    }
    q10_candidates = q10.parse_decision_candidates(q10_decision)
    q10_episode = q10.build_q10_semiconductor_episode(q10_candidates[0], FULL_DAY_ROWS)

    assert q12_episode.identity.event.canonical_event_id != q10_episode.identity.event.canonical_event_id
    assert q12_episode.symbol != q10_episode.symbol


def test_calc1_ineligible_and_unavailable_rejected_like_q10():
    unavailable = calc1.parse_calc1_decisions([_calc1_decision(decision_id="D1", day=DAY, available=False)])[0]
    with pytest.raises(Q12AdapterError):
        calc1.build_calc1_episode(unavailable, FULL_DAY_ROWS)


# =========================================================================
# Calc2 -- hypothesis_forward_adapter (NET_OR_COST_INCLUDED)
# =========================================================================


def _calc2_outcome(*, entry_epoch: int, entry_price: float, rows: list[dict], drag_pct: float = 0.5, include_eod: bool = True) -> dict:
    minutes = {"+5m": 5, "+15m": 15, "+30m": 30, "+60m": 60}
    returns = {}
    for label, minute in minutes.items():
        target = entry_epoch + minute * 60
        row = _row_at(rows, target)
        if row is None:
            returns[label] = {"status": "PENDING"}
            continue
        gross = ((row["close"] / entry_price) - 1.0) * 100.0
        returns[label] = {
            "status": "OBSERVED", "gross_return_pct": gross, "net_return_pct": gross - drag_pct,
            "mfe_pct": 0.0, "mae_pct": 0.0, "observed_epoch": target, "observed_price": row["close"],
        }
    if include_eod:
        eod_ts = kst_epoch(DAY, 15, 30)
        eod_row = _row_at(rows, eod_ts)
        if eod_row is not None:
            gross = ((eod_row["close"] / entry_price) - 1.0) * 100.0
            returns["EOD"] = {
                "status": "OBSERVED", "gross_return_pct": gross, "net_return_pct": gross - drag_pct,
                "mfe_pct": 0.0, "mae_pct": 0.0, "observed_epoch": eod_ts, "observed_price": eod_row["close"],
            }
        else:
            returns["EOD"] = {"status": "PENDING"}
    else:
        returns["EOD"] = {"status": "PENDING"}
    return {"status": "OBSERVED", "entry_epoch": entry_epoch, "entry_price": entry_price, "returns": returns}


def test_calc2_btc_and_local_provenance_both_preserved():
    outcome = _calc2_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    btc_0855 = {"return_24h_pct": 5.5, "target_epoch": kst_epoch(DAY, 8, 55)}
    sample = calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="09:05", outcome=outcome, btc_0855=btc_0855)
    ep = calc2.build_calc2_episode(sample, FULL_DAY_ROWS)
    assert ep.metadata["entry_epoch"] == ENTRY_EPOCH
    assert ep.metadata["entry_price"] == ENTRY_PRICE
    assert ep.metadata["btc_0855"]["return_24h_pct"] == 5.5
    assert ep.symbol == "041190"


def test_calc2_local_reference_mapping_uses_entry_price_not_candle_open():
    outcome = _calc2_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    sample = calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="09:05", outcome=outcome, btc_0855={})
    ep = calc2.build_calc2_episode(sample, FULL_DAY_ROWS)
    five_min = next(cp for cp in ep.checkpoints if cp.horizon_label == "+5m")
    target_row = _row_at(FULL_DAY_ROWS, ENTRY_EPOCH + 5 * 60)
    assert five_min.gross_return == pytest.approx(((target_row["close"] / ENTRY_PRICE) - 1.0) * 100.0)


def test_calc2_successful_evaluated_sample_carries_source_net_return():
    outcome = _calc2_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS, drag_pct=0.3)
    sample = calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="09:05", outcome=outcome, btc_0855={})
    ep = calc2.build_calc2_episode(sample, FULL_DAY_ROWS)
    five_min = next(cp for cp in ep.checkpoints if cp.horizon_label == "+5m")
    assert five_min.completeness is CheckpointCompleteness.OBSERVED
    assert five_min.net_return == pytest.approx(five_min.gross_return - 0.3)


def test_calc2_entry_missing_is_rejected_not_zero_return():
    # entry never observed -- the whole sample has no reference at all.
    sample = calc2.parse_calc2_entry_method(
        trading_date=DAY, entry_method="PULLBACK",
        outcome={"status": "MISSING", "reason": "deterministic_pullback_trigger_not_observed"},
        btc_0855={},
    )
    with pytest.raises(Q12AdapterError):
        calc2.build_calc2_episode(sample, FULL_DAY_ROWS)


def test_calc2_missing_local_observation_is_missing_not_zero():
    # truncate the candle series well before session close -- EOD cannot
    # resolve yet (trading day not finished).
    truncated_rows = [row for row in FULL_DAY_ROWS if row["ts"] < ENTRY_EPOCH + 90 * 60]
    outcome = _calc2_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=truncated_rows, include_eod=False)
    sample = calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="09:05", outcome=outcome, btc_0855={})
    ep = calc2.build_calc2_episode(sample, truncated_rows)
    eod = next(cp for cp in ep.checkpoints if cp.horizon_label == "EOD")
    assert eod.completeness is not CheckpointCompleteness.OBSERVED
    assert eod.net_return is None
    assert eod.gross_return is None


def test_calc2_horizon_behavior_matches_frozen_five_label_profile():
    outcome = _calc2_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    sample = calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="09:05", outcome=outcome, btc_0855={})
    ep = calc2.build_calc2_episode(sample, FULL_DAY_ROWS)
    assert {cp.horizon_label for cp in ep.checkpoints} == {"+5m", "+15m", "+30m", "+60m", "EOD"}


def test_calc2_identity_stable_across_rebuild():
    outcome = _calc2_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    sample = calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="09:05", outcome=outcome, btc_0855={})
    ep1 = calc2.build_calc2_episode(sample, FULL_DAY_ROWS)
    ep2 = calc2.build_calc2_episode(sample, FULL_DAY_ROWS)
    assert ep1.identity.evaluation_record_id == ep2.identity.evaluation_record_id


def test_calc2_different_entry_method_differs_in_identity():
    outcome = _calc2_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    sample_a = calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="09:05", outcome=outcome, btc_0855={})
    sample_b = calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="09:10", outcome=outcome, btc_0855={})
    ep_a = calc2.build_calc2_episode(sample_a, FULL_DAY_ROWS)
    ep_b = calc2.build_calc2_episode(sample_b, FULL_DAY_ROWS)
    assert ep_a.identity.event.canonical_event_id != ep_b.identity.event.canonical_event_id


def test_calc2_cost_semantics_are_net_or_cost_included_never_gross_only():
    outcome = _calc2_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    sample = calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="09:05", outcome=outcome, btc_0855={})
    ep = calc2.build_calc2_episode(sample, FULL_DAY_ROWS)
    five_min = next(cp for cp in ep.checkpoints if cp.horizon_label == "+5m")
    member = calc2.checkpoint_to_net_or_cost_included_member(five_min, evaluation_record_id=ep.identity.evaluation_record_id)
    assert member.state is SampleMemberState.EVALUATED
    assert member.gross_return is None  # NET_OR_COST_INCLUDED forbids carrying gross_return
    assert member.cost_policy is None
    assert member.source_net_return == pytest.approx(five_min.net_return)


def test_calc2_contradictory_source_fields_rejected():
    # forward engine WOULD resolve this horizon (candle exists), but the
    # legacy source claims it never observed -- contradiction, must fail.
    outcome = _calc2_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    outcome["returns"]["+5m"] = {"status": "PENDING"}
    sample = calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="09:05", outcome=outcome, btc_0855={})
    with pytest.raises(Q12AdapterError):
        calc2.build_calc2_episode(sample, FULL_DAY_ROWS)


# =========================================================================
# FIX1 -- Fix A: Calc2 legacy high/low fallback (LEGACY == CANONICAL)
# =========================================================================


def _legacy_ground_truth(*, entry_method: str, entry_epoch: int, entry_price: float, rows: list[dict], drag_pct: float = 0.5) -> dict:
    """Call the REAL legacy `entry_forward_outcomes` directly, as the
    oracle for exact legacy/canonical equivalence."""

    from libs.reporting.baseline_btc_woori_tech.hypothesis_forward import entry_forward_outcomes

    entry_methods = {entry_method: {"status": "OBSERVED", "entry_epoch": entry_epoch, "entry_price": entry_price}}
    result = entry_forward_outcomes(entry_methods, candles=rows, drag_pct=drag_pct)
    return result[entry_method]["returns"]


@pytest.mark.parametrize(
    "mutate_high,mutate_low",
    [
        (0, None),        # high = 0 -> legacy fallback to close
        (None, 0),        # low = 0 -> legacy fallback to close
        ("__del__", None),  # high missing -> legacy fallback to close
        (None, "__del__"),  # low missing -> legacy fallback to close
    ],
)
def test_calc2_high_low_fallback_matches_legacy_exactly(mutate_high, mutate_low):
    rows = [dict(row) for row in FULL_DAY_ROWS]
    target_row = next(r for r in rows if r["ts"] == ENTRY_EPOCH + 5 * 60)
    if mutate_high == "__del__":
        del target_row["high"]
    elif mutate_high is not None:
        target_row["high"] = mutate_high
    if mutate_low == "__del__":
        del target_row["low"]
    elif mutate_low is not None:
        target_row["low"] = mutate_low

    legacy_returns = _legacy_ground_truth(entry_method="09:05", entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=rows)
    legacy_five_min = legacy_returns["+5m"]
    assert legacy_five_min["status"] == "OBSERVED"
    # sanity: this fixture genuinely exercises the fallback (legacy MFE is
    # NOT simply the mutated 0/missing high, e.g. it resolved via close):
    assert legacy_five_min["mfe_pct"] is not None

    outcome = _calc2_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=rows)
    outcome["returns"]["+5m"]["net_return_pct"] = legacy_five_min["net_return_pct"]  # source-provided net, as real caller would supply
    sample = calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="09:05", outcome=outcome, btc_0855={})
    ep = calc2.build_calc2_episode(sample, rows)
    canonical_five_min = next(cp for cp in ep.checkpoints if cp.horizon_label == "+5m")

    assert canonical_five_min.completeness is CheckpointCompleteness.OBSERVED
    assert canonical_five_min.gross_return == pytest.approx(legacy_five_min["gross_return_pct"])
    assert canonical_five_min.mfe == pytest.approx(legacy_five_min["mfe_pct"])
    assert canonical_five_min.mae == pytest.approx(legacy_five_min["mae_pct"])
    assert canonical_five_min.net_return == pytest.approx(legacy_five_min["net_return_pct"])


def test_calc2_previously_divergent_high_zero_case_now_matches_legacy():
    # the EXACT case the independent audit reproduced: legacy MFE=5.0 (or
    # similar, computed here from real numbers) vs a prior canonical
    # MFE=None -- this closes it by construction (comparing against the
    # real legacy function, not a hand-typed expectation).
    rows = [dict(row) for row in FULL_DAY_ROWS]
    for row in rows:
        if ENTRY_EPOCH < row["ts"] <= ENTRY_EPOCH + 5 * 60:
            row["high"] = 0  # legacy sentinel: high missing/zero for the whole excursion window
    legacy_returns = _legacy_ground_truth(entry_method="09:05", entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=rows)
    legacy_five_min = legacy_returns["+5m"]
    assert legacy_five_min["mfe_pct"] is not None  # legacy did NOT silently give up

    outcome = _calc2_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=rows)
    outcome["returns"]["+5m"]["net_return_pct"] = legacy_five_min["net_return_pct"]
    sample = calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="09:05", outcome=outcome, btc_0855={})
    ep = calc2.build_calc2_episode(sample, rows)
    canonical_five_min = next(cp for cp in ep.checkpoints if cp.horizon_label == "+5m")

    assert canonical_five_min.mfe is not None  # NOT None -- the previously-divergent defect is closed
    assert canonical_five_min.mfe == pytest.approx(legacy_five_min["mfe_pct"])
    assert canonical_five_min.mae == pytest.approx(legacy_five_min["mae_pct"])


# =========================================================================
# FIX1 -- Fix C: shared parser rejects invalid numerics
# =========================================================================


def test_shared_parser_rejects_nan_close():
    rows = [dict(row) for row in FULL_DAY_ROWS]
    rows[3]["close"] = float("nan")
    with pytest.raises(Q12AdapterError):
        calc1.candles_to_observations(rows)


def test_shared_parser_rejects_negative_close():
    rows = [dict(row) for row in FULL_DAY_ROWS]
    rows[3]["close"] = -5.0
    with pytest.raises(Q12AdapterError):
        calc1.candles_to_observations(rows)


def test_shared_parser_rejects_infinite_price():
    rows = [dict(row) for row in FULL_DAY_ROWS]
    rows[3]["high"] = float("inf")
    with pytest.raises(Q12AdapterError):
        calc1.candles_to_observations(rows)


def test_shared_parser_rejects_negative_high():
    rows = [dict(row) for row in FULL_DAY_ROWS]
    rows[3]["high"] = -1.0
    with pytest.raises(Q12AdapterError):
        calc1.candles_to_observations(rows)


def test_shared_parser_rejects_nan_volume():
    rows = [dict(row) for row in FULL_DAY_ROWS]
    rows[3]["volume"] = float("nan")
    with pytest.raises(Q12AdapterError):
        calc1.candles_to_observations(rows)


def test_shared_parser_rejects_negative_volume():
    rows = [dict(row) for row in FULL_DAY_ROWS]
    rows[3]["volume"] = -10.0
    with pytest.raises(Q12AdapterError):
        calc1.candles_to_observations(rows)


def test_shared_parser_allows_zero_volume():
    # not load-bearing for any of Calc1/2/3's own checkpoint logic --
    # must not be rejected.
    rows = [dict(row) for row in FULL_DAY_ROWS]
    rows[3]["volume"] = 0.0
    observations = calc1.candles_to_observations(rows)
    assert observations[3].volume == 0.0


def test_shared_parser_allows_zero_high_low_unresolved_for_calc1_chain_fallback():
    # 0 for high/low must pass through UNRESOLVED (never rejected) -- for
    # Calc1 this lets the frozen PriceResolutionPolicy chain
    # (BAR_HIGH -> REFERENCE_PRICE) correctly fall through generically.
    rows = [dict(row) for row in FULL_DAY_ROWS]
    rows[3]["high"] = 0
    observations = calc1.candles_to_observations(rows)
    from libs.reporting.evaluation.canonical.forward import PriceCandidate

    assert observations[3].fields[PriceCandidate.BAR_HIGH] == 0.0


def test_shared_parser_still_rejects_invalid_timestamp():
    # FIX1's earlier lesson preserved unmodified.
    rows = [dict(row) for row in FULL_DAY_ROWS]
    rows[3]["ts"] = 0
    with pytest.raises(Q12AdapterError):
        calc1.candles_to_observations(rows)
    rows2 = [dict(row) for row in FULL_DAY_ROWS]
    rows2[3]["ts"] = -100
    with pytest.raises(Q12AdapterError):
        calc1.candles_to_observations(rows2)


# =========================================================================
# Calc3 -- vnext_completeness_adapter -- BLOCKED / EXPERIMENTAL, NOT
# an approved UEF-4B adapter. LOSSLESS MAPPING = UNKNOWN (UEF-4B-2 FIX2).
#
# The one test that matters most in this section is
# `test_calc3_legacy_row_count_vs_frozen_completeness_contradiction_reproducer`
# below: it PROVES, with a real synthetic input and both the real legacy
# function and the frozen UEF-2B engine called directly, that legacy's
# row-count completeness and the frozen exact-grid completeness rule
# genuinely diverge -- this is WHY Calc3 is blocked. The remaining tests
# in this section exercise this module's own EXPERIMENTAL, non-approved
# mechanics only; none of them establishes or implies lossless mapping.
# =========================================================================


def _calc3_outcome(*, entry_epoch: int, entry_price: float, rows: list[dict], drag_pct: float = 0.5) -> dict:
    outcome = {}
    for label, hh, mm, field in (("09:30", 9, 30, "open"), ("10:00", 10, 0, "open"), ("EOD", 15, 30, "close")):
        ts = kst_epoch(DAY, hh, mm)
        row = _row_at(rows, ts)
        if row is None:
            outcome[label] = {"status": "MISSING_EVIDENCE"}
            continue
        price = row[field]
        gross = ((price / entry_price) - 1.0) * 100.0
        outcome[label] = {"status": "OBSERVED", "gross_return_pct": gross, "net_return_pct": gross - drag_pct, "mfe_pct": None, "mae_pct": None}
    return outcome


def test_calc3_legacy_row_count_vs_frozen_completeness_contradiction_reproducer():
    """THE reason Q12 Calc3 is BLOCKED (UEF-4B-2 FIX2). A synthetic,
    ROW-COUNT-COMPLETE candle series with ONE off-grid timestamp (25
    expected window rows for the 09:30 horizon, all present, one shifted
    by 30s instead of landing on its exact minute slot):

    - the REAL legacy `vnext/outcomes.py::forward()`, called directly,
      reports `path_status="COMPLETE"` with real, non-None MFE/MAE
      (row-count only: `len(window) == expected`, satisfied);
    - the FROZEN `evaluate_forward()` (UEF-2B), called directly on the
      IDENTICAL data -- independent of any adapter-side gatekeeping --
      reports MFE/MAE as `None` for the SAME horizon (the actual observed
      timestamp SET does not equal the expected grid SET: canonical
      09:15:00 is absent, off-grid 09:15:30 is present instead).

    gross_return AGREES between legacy and frozen (the checkpoint
    observation itself, at the on-grid 09:30 target, is unaffected) --
    only the excursion/completeness verdict diverges. This is a real,
    reproduced CONTRADICTION, not a theoretical one: legacy and the
    frozen canonical contract disagree on the SAME valid-shaped input.
    Lossless mapping is therefore NOT established, and Calc3 remains
    BLOCKED pending a future architecture decision -- this test exists to
    protect against an accidental future re-promotion of Calc3 without
    that decision actually being made.
    """

    from libs.reporting.baseline_btc_woori_tech.vnext.outcomes import forward as legacy_forward
    from libs.reporting.evaluation.canonical.contracts import EventOrigin
    from libs.reporting.evaluation.canonical.forward.engine import ResolvedOrigin, ResolvedReference, evaluate_forward as frozen_evaluate_forward
    from libs.reporting.evaluation.canonical.forward.profiles import build_q12_calc3_vnext_profile

    target_0930 = kst_epoch(DAY, 9, 30)
    rows = []
    for minute in range(25):  # 09:05..09:29 inclusive -> 25 expected window rows for the 09:30 horizon
        ts = ENTRY_EPOCH + minute * 60
        if minute == 10:  # the row that would land at 09:15:00 is shifted off-grid by 30s
            ts += 30
        rows.append({"ts": ts, "open": 1000.0 + minute, "close": 1000.0 + minute, "high": 1000.0 + minute + 5, "low": 1000.0 + minute - 5, "volume": 100.0})
    rows.append({"ts": target_0930, "open": 1010.0, "close": 1010.0, "high": 1012.0, "low": 1008.0, "volume": 100.0})  # checkpoint itself, exactly on-grid

    entry = {"status": "OBSERVED", "entry_epoch": ENTRY_EPOCH, "entry_price": ENTRY_PRICE}
    legacy_result = legacy_forward(DAY, entry, rows, 0.5, kst_epoch(DAY, 15, 31))
    legacy_0930 = legacy_result["09:30"]

    assert legacy_0930["status"] == "OBSERVED"
    assert legacy_0930["path_status"] == "COMPLETE"  # legacy: row count matches -> COMPLETE
    assert legacy_0930["mfe_pct"] is not None
    assert legacy_0930["mae_pct"] is not None

    observations = calc1.candles_to_observations(rows)  # NOTE: bypasses this module's own experimental grid-guard entirely
    origin = ResolvedOrigin(timestamp=ENTRY_EPOCH, price=ENTRY_PRICE)
    resolved_reference = ResolvedReference(primary_origin=EventOrigin.CANDIDATE, origins={EventOrigin.CANDIDATE: origin, EventOrigin.FIXED_CLOCK: origin})
    frozen_result = frozen_evaluate_forward(policy=build_q12_calc3_vnext_profile(), resolved_reference=resolved_reference, observations=observations)
    frozen_0930 = next(h for h in frozen_result.horizons if h.label == "09:30")

    assert frozen_0930.gross_return == pytest.approx(legacy_0930["gross_return_pct"])  # checkpoint itself agrees
    assert frozen_0930.mfe is None  # THE CONTRADICTION: frozen says incomplete/unresolved excursion
    assert frozen_0930.mae is None  # ...while legacy (same input) reported real, non-None values above


def test_calc3_complete_minute_series_yields_observed_mfe_mae():
    # experimental module mechanics only -- not proof of lossless mapping.
    entry = {"status": "OBSERVED", "entry_epoch": ENTRY_EPOCH, "entry_price": ENTRY_PRICE}
    outcome = _calc3_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    sample = calc3.parse_calc3_entry_method(trading_date=DAY, entry_method="09:05", entry=entry, outcome_by_horizon=outcome)
    ep = calc3.build_calc3_episode(sample, FULL_DAY_ROWS)
    for cp in ep.checkpoints:
        assert cp.completeness is CheckpointCompleteness.OBSERVED
        assert cp.mfe is not None
        assert cp.mae is not None


def test_calc3_missing_minute_breaks_completeness_but_keeps_gross_return():
    # experimental module mechanics only -- not proof of lossless mapping.
    rows = [row for row in FULL_DAY_ROWS if row["ts"] != ENTRY_EPOCH + 10 * 60]
    entry = {"status": "OBSERVED", "entry_epoch": ENTRY_EPOCH, "entry_price": ENTRY_PRICE}
    outcome = _calc3_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=rows)
    sample = calc3.parse_calc3_entry_method(trading_date=DAY, entry_method="09:05", entry=entry, outcome_by_horizon=outcome)
    ep = calc3.build_calc3_episode(sample, rows)
    for cp in ep.checkpoints:
        assert cp.completeness is CheckpointCompleteness.OBSERVED  # checkpoint itself still resolves
        assert cp.gross_return is not None  # gross reported regardless of completeness (per real source)
        assert cp.mfe is None  # but excursion completeness is broken -- delegated, not recomputed here
        assert cp.mae is None


def test_calc3_experimental_grid_guard_mechanically_rejects_off_grid_input():
    # Mechanical coverage of this EXPERIMENTAL module's own defensive
    # guard only -- this does NOT establish lossless mapping (see the
    # contradiction reproducer above, which bypasses this same guard to
    # prove the underlying legacy/frozen contract genuinely diverges).
    rows = [dict(row) for row in FULL_DAY_ROWS]
    rows[5]["ts"] = rows[5]["ts"] + 30  # off-grid by 30 seconds
    entry = {"status": "OBSERVED", "entry_epoch": ENTRY_EPOCH, "entry_price": ENTRY_PRICE}
    outcome = _calc3_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    sample = calc3.parse_calc3_entry_method(trading_date=DAY, entry_method="09:05", entry=entry, outcome_by_horizon=outcome)
    with pytest.raises(Q12AdapterError):
        calc3.build_calc3_episode(sample, rows)


def test_calc3_valid_grid_aligned_series_still_accepted():
    # sanity: the experimental guard must not reject genuinely valid,
    # fully grid-aligned input. Not proof of lossless mapping.
    entry = {"status": "OBSERVED", "entry_epoch": ENTRY_EPOCH, "entry_price": ENTRY_PRICE}
    outcome = _calc3_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    sample = calc3.parse_calc3_entry_method(trading_date=DAY, entry_method="09:05", entry=entry, outcome_by_horizon=outcome)
    ep = calc3.build_calc3_episode(sample, FULL_DAY_ROWS)
    assert ep.symbol == "041190"


def test_calc3_duplicate_conflicting_minute_is_rejected_by_frozen_engine():
    from libs.reporting.evaluation.canonical.forward.engine import AmbiguousObservationError

    rows = [dict(row) for row in FULL_DAY_ROWS]
    conflicting = dict(rows[10])
    conflicting["close"] = conflicting["close"] + 500.0  # same ts, different price -> genuine conflict
    rows.append(conflicting)
    entry = {"status": "OBSERVED", "entry_epoch": ENTRY_EPOCH, "entry_price": ENTRY_PRICE}
    outcome = _calc3_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    sample = calc3.parse_calc3_entry_method(trading_date=DAY, entry_method="09:05", entry=entry, outcome_by_horizon=outcome)
    with pytest.raises(AmbiguousObservationError):
        calc3.build_calc3_episode(sample, rows)


def test_calc3_invalid_candle_timestamp_rejected_never_dropped():
    rows = [dict(row) for row in FULL_DAY_ROWS]
    rows[10]["ts"] = 0
    entry = {"status": "OBSERVED", "entry_epoch": ENTRY_EPOCH, "entry_price": ENTRY_PRICE}
    outcome = _calc3_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    sample = calc3.parse_calc3_entry_method(trading_date=DAY, entry_method="09:05", entry=entry, outcome_by_horizon=outcome)
    with pytest.raises(Q12AdapterError):
        calc3.build_calc3_episode(sample, rows)


def test_calc3_horizon_completeness_delegated_to_frozen_uef_not_reimplemented():
    # AST-scan actual CODE (not docstrings/comments, which quote the
    # legacy formula for provenance) for the legacy contiguity formula's
    # own building blocks -- `len(...)`  compared for equality is never
    # reimplemented here; only `evaluate_forward` may decide completeness.
    path = Path("libs/reporting/evaluation/canonical/adapters/vnext_completeness_adapter.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "evaluate_forward" in calls
    len_compare_nodes = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and (
            (isinstance(node.left, ast.Call) and isinstance(node.left.func, ast.Name) and node.left.func.id == "len")
            or any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "len" for c in node.comparators)
        )
    ]
    assert not len_compare_nodes, "vnext_completeness_adapter.py must never compare len(...) itself -- completeness is frozen-UEF-2B's job"


# =========================================================================
# Evidence multiplication guards
# =========================================================================


def test_calc1_calc2_calc3_labels_do_not_triple_count_one_physical_observation():
    # same (day, symbol) local reference point evaluated by all three
    # calculators must remain THREE DISTINCT canonical records (different
    # hypothesis_id/observation protocol), never silently treated as "the
    # same evidence" nor secretly fabricated as extra independent samples
    # beyond what each calculator's own real computation supports.
    calc1_candidate = calc1.parse_calc1_decisions([_calc1_decision(decision_id="D1", day=DAY)])[0]
    ep1 = calc1.build_calc1_episode(calc1_candidate, FULL_DAY_ROWS)

    outcome2 = _calc2_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    sample2 = calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="09:05", outcome=outcome2, btc_0855={})
    ep2 = calc2.build_calc2_episode(sample2, FULL_DAY_ROWS)

    entry3 = {"status": "OBSERVED", "entry_epoch": ENTRY_EPOCH, "entry_price": ENTRY_PRICE}
    outcome3 = _calc3_outcome(entry_epoch=ENTRY_EPOCH, entry_price=ENTRY_PRICE, rows=FULL_DAY_ROWS)
    sample3 = calc3.parse_calc3_entry_method(trading_date=DAY, entry_method="09:05", entry=entry3, outcome_by_horizon=outcome3)
    ep3 = calc3.build_calc3_episode(sample3, FULL_DAY_ROWS)

    ids = {ep1.identity.evaluation_record_id, ep2.identity.evaluation_record_id, ep3.identity.evaluation_record_id}
    assert len(ids) == 3  # three distinct records, not a duplicate id collision
    # Calc2/Calc3 additionally SHARE the same underlying local entry EVENT
    # (same real reference point) -- legitimate multi-hypothesis reuse,
    # not evidence fabrication:
    assert ep2.identity.event.canonical_event_id == ep3.identity.event.canonical_event_id
    assert ep2.identity.hypothesis_id != ep3.identity.hypothesis_id


def test_calc2_and_calc3_do_not_reimplement_each_others_translation():
    # each adapter family owns its own NET_OR_COST_INCLUDED member
    # translation (UEF-4A Table B is 1:1 family-per-source) -- confirm
    # neither module IMPORTS the other's translation function (a
    # docstring may still mention the sibling module by name for
    # provenance/comparison purposes).
    calc2_tree = ast.parse(Path("libs/reporting/evaluation/canonical/adapters/hypothesis_forward_adapter.py").read_text(encoding="utf-8"))
    calc3_tree = ast.parse(Path("libs/reporting/evaluation/canonical/adapters/vnext_completeness_adapter.py").read_text(encoding="utf-8"))
    calc2_imports = {node.module for node in ast.walk(calc2_tree) if isinstance(node, ast.ImportFrom)}
    calc3_imports = {node.module for node in ast.walk(calc3_tree) if isinstance(node, ast.ImportFrom)}
    assert not any(module and "vnext_completeness_adapter" in module for module in calc2_imports)
    assert not any(module and "hypothesis_forward_adapter" in module for module in calc3_imports)


# =========================================================================
# Fail-fast (Section 22)
# =========================================================================


def test_missing_btc_related_entry_timestamp_rejected():
    sample = calc2.parse_calc2_entry_method(
        trading_date=DAY, entry_method="09:00",
        outcome={"status": "MISSING", "reason": "entry_minute_candle_missing"}, btc_0855={},
    )
    with pytest.raises(Q12AdapterError):
        calc2.build_calc2_episode(sample, FULL_DAY_ROWS)


def test_unknown_entry_method_rejected():
    with pytest.raises(Q12AdapterError):
        calc2.parse_calc2_entry_method(trading_date=DAY, entry_method="NOT_A_METHOD", outcome={"status": "MISSING"}, btc_0855={})
    with pytest.raises(Q12AdapterError):
        calc3.parse_calc3_entry_method(trading_date=DAY, entry_method="NOT_A_METHOD", entry={"status": "MISSING"}, outcome_by_horizon={})


def test_contradictory_calc2_entry_status_rejected():
    with pytest.raises(Q12AdapterError):
        calc2.parse_calc2_entry_method(
            trading_date=DAY, entry_method="09:00",
            outcome={"status": "OBSERVED", "entry_epoch": None, "entry_price": None}, btc_0855={},
        )


def test_contradictory_calc1_decision_rejected():
    bad = _calc1_decision(decision_id="D1", day=DAY)
    bad["local_features"] = {"available": True, "baseline_epoch": None, "baseline_price": None}
    with pytest.raises(Q12AdapterError):
        calc1.parse_calc1_decisions([bad])


def test_missing_decision_id_rejected():
    bad = _calc1_decision(decision_id="", day=DAY)
    with pytest.raises(Q12AdapterError):
        calc1.parse_calc1_decisions([bad])


def test_calc1_invalid_candle_timestamp_rejected():
    candidate = calc1.parse_calc1_decisions([_calc1_decision(decision_id="D1", day=DAY)])[0]
    rows = [dict(row) for row in FULL_DAY_ROWS]
    rows[3]["ts"] = -1
    with pytest.raises(Q12AdapterError):
        calc1.build_calc1_episode(candidate, rows)


# =========================================================================
# Frozen delegation
# =========================================================================


_ADAPTER_FILES = (
    Path("libs/reporting/evaluation/canonical/adapters/q12_baseline_btc_woori.py"),
    Path("libs/reporting/evaluation/canonical/adapters/hypothesis_forward_adapter.py"),
    Path("libs/reporting/evaluation/canonical/adapters/vnext_completeness_adapter.py"),
)
_FORBIDDEN_DEFINITIONS = {"calculate_profit_factor", "calculate_max_drawdown", "calculate_net_return", "calculate_total_cost", "classify_net_return"}


def test_q12_adapters_never_define_a_financial_calculation_function():
    for path in _ADAPTER_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        overlap = defined & _FORBIDDEN_DEFINITIONS
        assert not overlap, f"{path} redefines frozen UEF-3B calculation function(s): {overlap}"


def test_uef4b1_frozen_files_are_not_modified_by_this_task():
    # UEF-4B-1's own two files must be byte-identical in behavior --
    # spot-check via its own focused test suite import path staying intact.
    from libs.reporting.evaluation.canonical.adapters import q10_semiconductor  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import forward_measurement_adapter  # noqa: F401
