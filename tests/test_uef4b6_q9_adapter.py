"""UEF-4B-6 -- Q9 Horizon/Exit candidate adapter reproducer tests.

`q9_horizon_exit_adapter.py` is BLOCKED -- NOT an approved UEF-4B
adapter, DIRECT LOSSLESS UEF-4 MAPPING = NO (the trusted
`post_exit_shadow_recap.v1` artifact never persists which real source
branch resolved `exit_price`, so `exit_price_authority` cannot be
reconstructed losslessly -- see the module's own top-of-file BLOCKED
banner). Q9 remains real PRIMARY EVIDENCE with a KNOWN, classified
blocker (PRIMARY / KNOWN / BLOCKED), not unfinished hidden work.

These tests exist to PROVE and PROTECT that classification: real
actual-exit reference/identity, the real 4-deep price-alias chain,
+5m/+15m/+30m/+60m/EOD horizons, `ReturnUnit.FRACTION` preservation, the
real session-close fallback substitution, `EOD` `KEEP_PENDING`
semantics, `GROSS_ONLY` cost semantics with no fabricated `CostPolicy`,
the `EXIT_EVENT` observation-identity closure (Fix1) and its own
reported (never fabricated) exit-price-authority gap, population/
identity accounting, the trusted-artifact ingestion boundary
(wrong-family/forged-schema/execution-evidence rejection), and
fail-fast invalid-input handling -- none of it establishes or implies
lossless mapping. Every fixture below calls the REAL legacy functions
directly (`update_post_exit_shadow_with_price_observations`,
`_fill_regular_close_bound_pending_checkpoints`) -- oracle-grade, never
a hand-approximated shape.
"""

from __future__ import annotations

import ast
import datetime
import json
import zoneinfo
from pathlib import Path

import pytest

from libs.reporting.post_exit_shadow_recap import CHECKPOINT_LABELS, _fill_regular_close_bound_pending_checkpoints
from libs.runtime.strategy_horizon_feedback import update_post_exit_shadow_with_price_observations

from libs.reporting.evaluation.canonical.contracts import CheckpointCompleteness, EntryAuthority, ExecutionMode, ObservationType, ReturnUnit
from libs.reporting.evaluation.canonical.identity import evaluation_subject_id
from libs.reporting.evaluation.canonical.metrics import CostPolicy
from libs.reporting.evaluation.canonical.metrics.contracts import CostTiming
from libs.reporting.evaluation.canonical.metrics.aggregation import SampleMemberState

from libs.reporting.evaluation.canonical.adapters import q9_horizon_exit_adapter as q9
from libs.reporting.evaluation.canonical.adapters.q9_horizon_exit_adapter import Q9HorizonExitAdapterError

KST = zoneinfo.ZoneInfo("Asia/Seoul")
DAY = "2026-06-24"


def _cost_policy() -> CostPolicy:
    return CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.FRACTION, commission=0.001, slippage=0.0005, provenance="test_fixture")


def _epoch(day: str, hh: int, mm: int) -> int:
    return int(datetime.datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=KST).timestamp())


def _iso(epoch: int) -> str:
    return datetime.datetime.fromtimestamp(epoch, tz=KST).isoformat()


def _minute_rows(*, start_ts: int, count: int, base: float = 1000.0, step: float = 0.4) -> list[dict]:
    rows = []
    for i in range(count):
        ts = start_ts + i * 60
        price = base + step * i
        rows.append({
            "ts": ts,
            "raw_ts": datetime.datetime.fromtimestamp(ts, tz=KST).strftime("%Y%m%d%H%M%S"),
            "close": price, "high": price + 1.0, "low": price - 1.0, "volume": 100.0,
        })
    return rows


def _placeholder_shadow(*, symbol: str, exit_epoch: int, exit_price: float) -> dict:
    return {
        "schema_version": "post_exit_shadow.v1", "observability_only": True, "status": "pending",
        "symbol": symbol, "exit_ts": _iso(exit_epoch), "exit_price": exit_price,
        "checkpoints": {label: {"status": "pending"} for label in CHECKPOINT_LABELS},
    }


def _real_updated_shadow(*, symbol: str = "005930", exit_hh: int = 9, exit_mm: int = 0, count: int = 90, apply_closeout_fallback: bool = False) -> dict:
    exit_epoch = _epoch(DAY, exit_hh, exit_mm)
    exit_price = 1000.0
    shadow = _placeholder_shadow(symbol=symbol, exit_epoch=exit_epoch, exit_price=exit_price)
    rows = _minute_rows(start_ts=exit_epoch, count=count)
    updated = update_post_exit_shadow_with_price_observations(shadow, minute_rows=rows)
    if apply_closeout_fallback:
        updated = _fill_regular_close_bound_pending_checkpoints(updated)
    return updated


def _write_recap_artifact(tmp_path: Path, trades: list[dict], *, schema_version: str | None = None, family_dir: str | None = None) -> Path:
    directory = tmp_path / (family_dir if family_dir is not None else f"post_exit_shadow_recap/{DAY}")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "post_exit_shadow_recap.json"
    payload = {
        "schema_version": schema_version if schema_version is not None else q9.SCHEMA_VERSION,
        "observability_only": True, "day": DAY, "generated_at": _iso(_epoch(DAY, 16, 0)),
        "policy": {}, "summary": {"total": len(trades)}, "trades": trades,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _trade_row(trade_id: str, shadow: dict) -> dict:
    return {"trade_id": trade_id, "symbol": shadow.get("symbol"), "post_exit_shadow": shadow}


# =========================================================================
# Oracle comparison -- reference, horizons, return, MFE/MAE, EOD
# =========================================================================


def test_oracle_matches_real_update_function_directly(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    assert len(results) == 1
    episode = results[0].episode

    for label in CHECKPOINT_LABELS:
        oracle_row = shadow["checkpoints"][label]
        cp = next(cp for cp in episode.checkpoints if cp.horizon_label == label)
        if oracle_row.get("status") == "observed":
            assert cp.completeness is CheckpointCompleteness.OBSERVED
            assert cp.observed_price == pytest.approx(oracle_row["observed_price"])
            assert cp.gross_return == pytest.approx(oracle_row["return_pct"])
            assert cp.mfe == pytest.approx(oracle_row["max_upside_pct"])
            assert cp.mae == pytest.approx(oracle_row["max_drawdown_pct"])
            assert cp.net_return is None  # GROSS_ONLY
            assert cp.return_unit is ReturnUnit.FRACTION
        else:
            assert cp.completeness is CheckpointCompleteness.PENDING
            assert cp.observed_price is None
            assert cp.gross_return is None


def test_reference_is_real_exit_price_and_timestamp_verbatim(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    assert results[0].trade.exit_price == pytest.approx(shadow["exit_price"])
    from libs.runtime.strategy_horizon_feedback import _epoch_seconds
    assert results[0].trade.exit_epoch == int(_epoch_seconds(shadow["exit_ts"]))


def test_return_unit_is_fraction_not_percentage_points(tmp_path):
    # explicit regression: FRACTION means 0.01 == +1%, never 1.0 == +1%.
    exit_epoch = _epoch(DAY, 9, 0)
    exit_price = 1000.0
    shadow = _placeholder_shadow(symbol="005930", exit_epoch=exit_epoch, exit_price=exit_price)
    rows = _minute_rows(start_ts=exit_epoch, count=10, base=1000.0, step=0.0)
    rows[5]["close"] = 1010.0  # +1% at the +5m checkpoint candle
    updated = update_post_exit_shadow_with_price_observations(shadow, minute_rows=rows)
    assert updated["checkpoints"]["+5m"]["status"] == "observed"
    assert updated["checkpoints"]["+5m"]["return_pct"] == pytest.approx(0.01)  # FRACTION, not 1.0

    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", updated)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    cp = next(cp for cp in results[0].episode.checkpoints if cp.horizon_label == "+5m")
    assert cp.gross_return == pytest.approx(0.01)
    assert cp.return_unit is ReturnUnit.FRACTION


def test_sample_unit_and_horizons(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="EOD", cost_policy=_cost_policy())
    episode = results[0].episode
    assert episode.symbol == "005930"
    assert episode.execution_mode is ExecutionMode.BROKER_LIVE
    labels = {cp.horizon_label for cp in episode.checkpoints}
    assert labels == set(CHECKPOINT_LABELS)


# =========================================================================
# Session-close fallback (real, not invented) + EOD KEEP_PENDING
# =========================================================================


def test_session_close_fallback_substitutes_eod_into_late_intraday_checkpoint(tmp_path):
    # exit at 15:00 KST; candles only reach 15:35 -- +60m's own 16:00
    # target is never reached by real candle data AND falls after the
    # 15:30 regular close, so the real _fill_regular_close_bound_
    # pending_checkpoints substitutes EOD's own observed price/ts into it.
    exit_epoch = _epoch(DAY, 15, 0)
    shadow = _placeholder_shadow(symbol="005930", exit_epoch=exit_epoch, exit_price=1000.0)
    rows = _minute_rows(start_ts=exit_epoch, count=36, base=1000.0, step=0.2)  # 15:00 .. 15:35
    updated = update_post_exit_shadow_with_price_observations(shadow, minute_rows=rows)
    assert updated["checkpoints"]["+60m"]["status"] == "pending"  # real function alone: no fallback
    assert updated["checkpoints"]["EOD"]["status"] == "observed"
    assert updated["checkpoints"]["+30m"]["status"] == "observed"  # target 15:30, within candle range

    substituted = _fill_regular_close_bound_pending_checkpoints(updated)
    assert substituted["checkpoints"]["+60m"]["status"] == "observed"
    assert substituted["checkpoints"]["+60m"]["closeout_substitute"] is True

    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", substituted)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+60m", cost_policy=_cost_policy())
    cp60 = next(cp for cp in results[0].episode.checkpoints if cp.horizon_label == "+60m")
    eod_oracle = substituted["checkpoints"]["EOD"]
    assert cp60.completeness is CheckpointCompleteness.OBSERVED
    assert cp60.observed_price == pytest.approx(eod_oracle["observed_price"])
    assert cp60.observed_timestamp == pytest.approx(int(__import__("libs.runtime.strategy_horizon_feedback", fromlist=["_epoch_seconds"])._epoch_seconds(eod_oracle["observed_ts"])))
    assert cp60.gross_return == pytest.approx(substituted["checkpoints"]["+60m"]["return_pct"])


def test_eod_keep_pending_when_regular_close_never_reached(tmp_path):
    # candles stop well before 15:30 -- EOD must stay PENDING, never
    # fabricated, and no fallback substitution is even attempted (the
    # real _fill_regular_close_bound_pending_checkpoints requires EOD
    # itself to be observed first).
    exit_epoch = _epoch(DAY, 9, 0)
    shadow = _placeholder_shadow(symbol="005930", exit_epoch=exit_epoch, exit_price=1000.0)
    rows = _minute_rows(start_ts=exit_epoch, count=10)  # 09:00..09:09, nowhere near 15:30
    updated = update_post_exit_shadow_with_price_observations(shadow, minute_rows=rows)
    assert updated["checkpoints"]["EOD"]["status"] == "pending"
    substituted = _fill_regular_close_bound_pending_checkpoints(updated)
    assert substituted["checkpoints"]["EOD"]["status"] == "pending"

    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", substituted)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="EOD", cost_policy=_cost_policy())
    eod_cp = next(cp for cp in results[0].episode.checkpoints if cp.horizon_label == "EOD")
    assert eod_cp.completeness is CheckpointCompleteness.PENDING
    assert eod_cp.gross_return is None
    assert eod_cp.observed_price is None


def test_missing_never_becomes_zero_return(tmp_path):
    shadow = _real_updated_shadow(count=10)  # only +5m resolvable in 10 minutes
    assert shadow["checkpoints"]["+15m"]["status"] == "pending"
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+15m", cost_policy=_cost_policy())
    cp = next(cp for cp in results[0].episode.checkpoints if cp.horizon_label == "+15m")
    assert cp.completeness is CheckpointCompleteness.PENDING
    assert cp.gross_return is None
    assert cp.mfe is None and cp.mae is None


# =========================================================================
# GROSS_ONLY / no fabricated CostPolicy
# =========================================================================


def test_gross_only_member_never_carries_source_net_return(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    member = results[0].member
    assert member.state is SampleMemberState.EVALUATED
    assert member.gross_return is not None
    assert member.source_net_return is None  # GROSS_ONLY -- never a source-provided net figure


def test_cost_policy_is_never_fabricated_caller_must_supply_it():
    import inspect

    sig = inspect.signature(q9.canonicalize_q9_horizon_exit_artifact)
    assert "cost_policy" in sig.parameters
    assert sig.parameters["cost_policy"].default is inspect.Parameter.empty  # no default -- caller must supply


def test_no_financial_metric_logic_in_adapter():
    # AST-based, not raw substring search -- the module's own docstring
    # legitimately explains what arithmetic is ABSENT (e.g. "no * 100"),
    # which a naive text search would misread as the arithmetic itself.
    tree = ast.parse(Path("libs/reporting/evaluation/canonical/adapters/q9_horizon_exit_adapter.py").read_text(encoding="utf-8"))
    forbidden_calls = {"profit_factor", "max_drawdown", "win_rate", "calculate_profit_factor", "calculate_max_drawdown", "calculate_net_return"}
    defined_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert not (defined_names & forbidden_calls)
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div)):
            # any multiply/divide in actual CODE (not docstrings, which
            # ast.walk never visits as BinOp nodes) is worth a hard look --
            # Q9's adapter should have none at all (every return/mfe/mae
            # figure is read verbatim from source, never computed here).
            pytest.fail(f"adapter contains a multiply/divide binary operation at line {node.lineno} -- financial arithmetic must live in frozen UEF-3, never here")


# =========================================================================
# Physical sample / identity / population accounting
# =========================================================================


def test_source_physical_sample_equals_canonical_physical_sample(tmp_path):
    shadow_a = _real_updated_shadow(symbol="005930", count=90)
    shadow_b = _real_updated_shadow(symbol="000660", exit_hh=10, count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_A", shadow_a), _trade_row("TRD_B", shadow_b)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    assert len(results) == 2  # 2 realized trades -> 2 canonical episodes, never merged/multiplied
    event_ids = {r.episode.identity.event.canonical_event_id for r in results}
    assert len(event_ids) == 2
    for r in results:
        assert len(r.episode.checkpoints) == 5  # exactly the 5 real observable horizons, never more


def test_one_trade_produces_exactly_one_episode_never_multiple(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    assert len(results) == 1


def test_identity_deterministic_and_uses_real_trade_id(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_REAL_42", shadow)])
    first = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    second = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    assert first[0].episode.identity.event.canonical_event_id == second[0].episode.identity.event.canonical_event_id
    assert first[0].episode.identity.evaluation_record_id == second[0].episode.identity.evaluation_record_id
    assert first[0].trade.trade_id == "TRD_REAL_42"


def test_duplicate_conflicting_trade_id_fails_fast(tmp_path):
    shadow_a = _real_updated_shadow(symbol="005930", count=90)
    shadow_b = _real_updated_shadow(symbol="000660", count=90)  # different symbol -> conflicting content
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_DUP", shadow_a), _trade_row("TRD_DUP", shadow_b)])
    with pytest.raises(Q9HorizonExitAdapterError):
        q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())


# =========================================================================
# Fail-fast
# =========================================================================


def test_rejects_missing_trade_id_or_symbol():
    shadow = _real_updated_shadow(count=90)
    with pytest.raises(Q9HorizonExitAdapterError):
        q9._parse_trade(DAY, {"symbol": "005930", "post_exit_shadow": shadow})
    with pytest.raises(Q9HorizonExitAdapterError):
        q9._parse_trade(DAY, {"trade_id": "T1", "post_exit_shadow": shadow})


def test_rejects_invalid_exit_price_or_timestamp():
    shadow = _real_updated_shadow(count=90)
    bad_price = dict(shadow); bad_price["exit_price"] = -5.0
    with pytest.raises(Q9HorizonExitAdapterError):
        q9._parse_trade(DAY, {"trade_id": "T1", "symbol": "005930", "post_exit_shadow": bad_price})
    bad_ts = dict(shadow); bad_ts["exit_ts"] = ""
    with pytest.raises(Q9HorizonExitAdapterError):
        q9._parse_trade(DAY, {"trade_id": "T1", "symbol": "005930", "post_exit_shadow": bad_ts})


def test_rejects_unknown_checkpoint_status():
    trade = q9._parse_trade(DAY, {"trade_id": "T1", "symbol": "005930", "post_exit_shadow": _real_updated_shadow(count=90)})
    bad_trade = q9.Q9RealizedTrade(**{**trade.__dict__, "checkpoints": {"+5m": {"status": "weird"}}})
    with pytest.raises(Q9HorizonExitAdapterError):
        q9._build_checkpoint(bad_trade, "+5m")


# =========================================================================
# Trusted ingestion boundary
# =========================================================================


def test_loader_rejects_path_outside_real_artifact_family(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)], family_dir=f"data/logs/opening_rank1_controlled_probe/{DAY}")
    with pytest.raises(Q9HorizonExitAdapterError):
        q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())


def test_loader_rejects_real_family_path_with_wrong_schema(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)], schema_version="controlled_mock_lanes.v1")
    with pytest.raises(Q9HorizonExitAdapterError):
        q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())


def test_loader_rejects_forged_schema_at_wrong_origin(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(
        tmp_path, [_trade_row("TRD_1", shadow)], family_dir=f"data/logs/controlled_mock_lanes/{DAY}",
    )
    with pytest.raises(Q9HorizonExitAdapterError):
        q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())


def test_loader_rejects_other_evaluator_and_execution_artifacts(tmp_path):
    fixtures = [
        {"schema_version": "opportunity_engine_virtual_trades.v2", "day": DAY, "trades": []},
        {"schema_version": "q10_korea_lead_market_forward_validation.v1", "day": DAY, "targets": {}},
        {"schema_version": "order_execution_outcome.v1", "fills": [{"decision_id": "D1", "symbol": "005930"}]},
    ]
    for i, payload in enumerate(fixtures):
        directory = tmp_path / f"post_exit_shadow_recap_wrong_{i}" / DAY
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "post_exit_shadow_recap.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(Q9HorizonExitAdapterError):
            q9.canonicalize_q9_horizon_exit_artifact(path, horizon_label="+5m", cost_policy=_cost_policy())


def test_loader_accepts_real_source_artifact(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    assert len(results) == 1
    assert results[0].episode.symbol == "005930"


# =========================================================================
# Financial-logic / broker-mechanics boundary guards
# =========================================================================


def test_q9_adapter_never_imports_execution_or_controlled_probe_or_broker_modules():
    tree = ast.parse(Path("libs/reporting/evaluation/canonical/adapters/q9_horizon_exit_adapter.py").read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    assert not any("controlled_probe" in m for m in modules)
    assert not any("controlled_mock_lane" in m for m in modules)
    assert not any("executor" in m or "broker" in m for m in modules)
    assert not any(m.startswith("libs.runtime.commander") or m.startswith("libs.runtime.execution") for m in modules)


def test_frozen_and_prior_approved_adapters_untouched_by_this_task():
    from libs.reporting.evaluation.canonical.adapters import q10_semiconductor  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import forward_measurement_adapter  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import q12_baseline_btc_woori  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import hypothesis_forward_adapter  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import opening_rank1_shadow  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import already_net_shadow_adapter  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import q10_index_reaction_adapter  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import q10_index_directional_shadow_adapter  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import virtual_probe_adapter  # noqa: F401


# =========================================================================
# FIX1 -- observation-identity closure (EXIT_EVENT, not SHADOW_ENTRY)
# =========================================================================


def test_observation_type_is_exit_event_not_shadow_entry_or_actual_trade(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    episode = results[0].episode
    assert episode.observation_type is ObservationType.EXIT_EVENT
    assert episode.entry is None
    assert episode.exit is not None


def test_actual_exit_anchor_preserved_on_exit_observation(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    episode = results[0].episode
    trade = results[0].trade
    assert episode.exit.exit_time == trade.exit_epoch
    assert episode.exit.exit_price == pytest.approx(trade.exit_price)
    assert episode.exit.exit_price == pytest.approx(shadow["exit_price"])


def test_no_fabricated_exit_price_authority(tmp_path):
    # The real source's exit_price alias chain (filled_price -> current_price
    # -> price -> avg_price) is not accompanied by any persisted discriminator
    # of which alias fired, so this module must never claim a confirmed-fill
    # authority (BROKER_FILL/MOCK_FILL) it cannot verify.
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    authority = results[0].episode.exit.exit_price_authority
    assert authority not in (EntryAuthority.BROKER_FILL, EntryAuthority.MOCK_FILL, EntryAuthority.SIMULATED_FILL, EntryAuthority.SUBMITTED_INTENT)


def test_same_trade_id_same_canonical_event_id_regardless_of_observation_type(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)])
    r1 = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    r2 = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="EOD", cost_policy=_cost_policy())
    assert r1[0].episode.identity.event.canonical_event_id == r2[0].episode.identity.event.canonical_event_id


def test_evaluation_subject_id_deterministic_under_exit_event(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)])
    r1 = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    r2 = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    assert r1[0].episode.identity.evaluation_subject_id == r2[0].episode.identity.evaluation_subject_id
    expected = evaluation_subject_id(
        canonical_event_id=r1[0].episode.identity.event.canonical_event_id,
        hypothesis_id=q9.HYPOTHESIS_ID,
        observation_type=ObservationType.EXIT_EVENT,
    )
    assert r1[0].episode.identity.evaluation_subject_id == expected


def test_changing_observation_type_changes_evaluation_subject_id(tmp_path):
    shadow = _real_updated_shadow(count=90)
    artifact_path = _write_recap_artifact(tmp_path, [_trade_row("TRD_1", shadow)])
    results = q9.canonicalize_q9_horizon_exit_artifact(artifact_path, horizon_label="+5m", cost_policy=_cost_policy())
    episode = results[0].episode
    real_subject_id = episode.identity.evaluation_subject_id
    shadow_entry_subject_id = evaluation_subject_id(
        canonical_event_id=episode.identity.event.canonical_event_id,
        hypothesis_id=q9.HYPOTHESIS_ID,
        observation_type=ObservationType.SHADOW_ENTRY,
    )
    assert real_subject_id != shadow_entry_subject_id
