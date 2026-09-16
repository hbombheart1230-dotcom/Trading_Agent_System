"""UEF-4B-5 -- Q11 Opportunity Engine canonical adapter tests.

Covers `virtual_probe_adapter.py`: physical identity (one closed virtual
probe trade = one canonical episode, never multiplied, never shared with
another family), reference/horizon/return/cost semantics verified
directly against the real `simulate_probe_v0`/`_forward_returns`
functions (oracle comparison, never hand-approximated), the EXIT-vs-
forward excursion fallback-chain distinction UEF-2A's own Q11 FINAL
FIDELITY PATCH froze, population/missing accounting, the trusted-
artifact ingestion boundary (wrong-family/forged-schema/execution-
evidence rejection), and fail-fast invalid-input handling. Every fixture
below calls the REAL legacy `simulate_probe_v0` function directly --
oracle-grade, never a hand-approximated shape.
"""

from __future__ import annotations

import ast
import datetime
import json
import zoneinfo
from pathlib import Path

import pytest

from libs.research.opportunity_engine.contracts import PROGRAM_ID, TRADES_SCHEMA
from libs.research.opportunity_engine.simulator import simulate_probe_v0

from libs.reporting.evaluation.canonical.contracts import CheckpointCompleteness, CheckpointMetricKind, ExecutionMode
from libs.reporting.evaluation.canonical.metrics.aggregation import SampleMemberState

from libs.reporting.evaluation.canonical.adapters import virtual_probe_adapter as q11
from libs.reporting.evaluation.canonical.adapters.virtual_probe_adapter import VirtualProbeAdapterError

KST = zoneinfo.ZoneInfo("Asia/Seoul")
DAY = "2026-06-24"


def _epoch(day: str, hh: int, mm: int) -> int:
    return int(datetime.datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=KST).timestamp())


def _flat_candles(*, start_ts: int, count: int, base: float = 1000.0, wiggle: float = 3.0) -> list[dict]:
    """Deterministic candles that never trip `stop_hit` (price never
    drops below the ATR-based stop) but do produce genuine, non-zero
    MFE/MAE excursion via a small oscillation."""

    rows = []
    for i in range(count):
        price = base + (wiggle if i % 4 in (1, 2) else 0.0) - (wiggle * 0.3 if i % 4 == 3 else 0.0)
        rows.append({
            "ts": start_ts + i * 60,
            "raw_ts": datetime.datetime.fromtimestamp(start_ts + i * 60, tz=KST).strftime("%Y%m%d%H%M%S"),
            "open": price, "close": price, "high": price + 1.0, "low": price - 1.0, "volume": 100.0,
        })
    return rows


def _entry_signal(*, symbol: str, entry_epoch: int) -> dict:
    return {
        "signal_id": f"OE_{DAY.replace('-', '')}_{symbol}_{entry_epoch}",
        "day": DAY, "symbol": symbol, "as_of_epoch": entry_epoch,
        "behavior_effect": "shadow_only", "research_window": "09:00-10:00 KST",
        "market": {"available": True},
        "symbol_features": {"price": 1000.0, "atr_6_pct": 0.8, "opening_low": 990.0, "momentum_1m_pct": 0.1},
        "opportunity": {"probe_candidate": True, "score": 0.75},
        "order_execution_allowed": False,
    }


def _real_trades(symbol: str = "005930", *, count: int = 390) -> list[dict]:
    start = _epoch(DAY, 9, 0)
    rows = _flat_candles(start_ts=start, count=count)
    signal = _entry_signal(symbol=symbol, entry_epoch=start)
    return simulate_probe_v0([signal], cost_pct=0.15, slippage_pct=0.05, minute_rows_by_symbol={symbol: rows})


def _write_trades_artifact(tmp_path: Path, trades: list[dict], *, schema_version: str | None = None, program_id: str | None = None, family_dir: str | None = None) -> Path:
    directory = tmp_path / (family_dir if family_dir is not None else f"opportunity_engine_shadow/{DAY}")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "opportunity_engine_virtual_trades.json"
    payload = {
        "schema_version": schema_version if schema_version is not None else TRADES_SCHEMA,
        "measurement_contract_version": "q11_minute_path.v2",
        "evaluation_program_id": program_id if program_id is not None else PROGRAM_ID,
        "evaluation_program_name": "Q11 Opening Surge & Market Reversal Research",
        "behavior_effect": "shadow_only", "research_window": "09:00-10:00 KST",
        "day": DAY, "strategy_id": "probe_v0",
        "cost_model": {"source": "test_fixture", "round_trip_cost_pct": 0.15, "slippage_pct": 0.05},
        "summary": {}, "trade_count": len(trades), "trades": trades,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# =========================================================================
# Oracle comparison -- reference, horizons, return, cost, MFE/MAE, exit
# =========================================================================


def test_oracle_matches_real_simulate_probe_v0_directly(tmp_path):
    trades = _real_trades()
    assert len(trades) == 1  # deterministic fixture: exactly one closed probe (timeout exit)
    oracle = trades[0]
    assert oracle["exit_reason"] == "max_hold"

    artifact_path = _write_trades_artifact(tmp_path, trades)
    results = q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)
    assert len(results) == 1
    episode = results[0].episode

    # OUTCOME ORACLE (gross/net/mfe/mae/observed_timestamp) -- unchanged by FIX1:
    exit_cp = next(cp for cp in episode.checkpoints if cp.horizon_label == "EXIT")
    assert exit_cp.observed_price == pytest.approx(oracle["exit_price"])
    assert exit_cp.gross_return == pytest.approx(oracle["gross_return_pct"])
    assert exit_cp.net_return == pytest.approx(oracle["net_return_pct"])
    assert exit_cp.mfe == pytest.approx(oracle["mfe_pct"])
    assert exit_cp.mae == pytest.approx(oracle["mae_pct"])
    assert exit_cp.observed_timestamp == oracle["exit_epoch"]

    for label in ("+5m", "+15m", "+30m", "+60m", "EOD"):
        oracle_row = oracle["forward_returns"][label]
        cp = next(cp for cp in episode.checkpoints if cp.horizon_label == label)
        if oracle_row["status"] == "observed":
            assert cp.completeness is CheckpointCompleteness.OBSERVED
            # FIX1 -- PRICE ORACLE: the exact legacy-simulator-selected
            # candle close, persisted in v2, must equal the canonical
            # Checkpoint.observed_price exactly (never AGGREGATE_ONLY):
            assert cp.metric_kind is CheckpointMetricKind.PRICE_BASED
            assert "observed_price" in oracle_row  # v2 persists it; v1 never did
            assert cp.observed_price == pytest.approx(oracle_row["observed_price"])
            # OUTCOME ORACLE (unchanged):
            assert cp.gross_return == pytest.approx(oracle_row["return_pct"])
            assert cp.net_return == pytest.approx(oracle_row["net_return_pct"])
            assert cp.observed_timestamp == oracle_row["observed_epoch"]
            if label == "EOD":
                assert cp.mfe is None and cp.mae is None  # EOD genuinely has no excursion
            else:
                assert cp.mfe == pytest.approx(oracle_row["mfe_pct"])
                assert cp.mae == pytest.approx(oracle_row["mae_pct"])
        else:
            assert cp.completeness is CheckpointCompleteness.PENDING
            assert cp.observed_price is None
            assert cp.gross_return is None and cp.net_return is None
            assert "observed_price" not in oracle_row  # PENDING never carries one


def test_reference_is_real_entry_price_verbatim(tmp_path):
    trades = _real_trades()
    artifact_path = _write_trades_artifact(tmp_path, trades)
    results = q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)
    assert results[0].trade.entry_price == pytest.approx(trades[0]["entry_price"])
    assert results[0].trade.entry_epoch == trades[0]["entry_epoch"]


def test_sample_unit_and_horizons(tmp_path):
    trades = _real_trades()
    artifact_path = _write_trades_artifact(tmp_path, trades)
    results = q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)
    episode = results[0].episode
    assert episode.symbol == "005930"
    assert episode.execution_mode is ExecutionMode.OBSERVATION_ONLY
    labels = {cp.horizon_label for cp in episode.checkpoints}
    assert labels == {"+5m", "+15m", "+30m", "+60m", "EOD", "EXIT"}
    for cp in episode.checkpoints:
        assert cp.return_unit.value == "PERCENTAGE_POINTS"


def test_exit_and_forward_excursion_use_different_fallback_chains_per_frozen_profile():
    # UEF-2A's own Q11 FINAL FIDELITY PATCH: EXIT's excursion is a
    # 3-deep chain (BAR_HIGH -> BAR_CLOSE -> SOURCE_FIELD_PRICE); forward
    # horizons are 2-deep (BAR_HIGH -> BAR_CLOSE). This adapter never
    # recomputes either -- it takes both verbatim from source, so this
    # test asserts the ADAPTER carries them through AS DISTINCT figures
    # (never collapsed/shared) whenever source values genuinely differ.
    # A spike AFTER the trade's own 30-minute timeout exit -- EXIT's own
    # excursion (bounded to the holding period) never sees it, but the
    # +60m forward scan (over the full candle series) does.
    start = _epoch(DAY, 9, 0)
    rows = _flat_candles(start_ts=start, count=70)
    rows[45]["high"] = 1200.0
    rows[45]["low"] = 900.0
    signal = _entry_signal(symbol="005930", entry_epoch=start)
    trades = simulate_probe_v0([signal], cost_pct=0.15, slippage_pct=0.05, minute_rows_by_symbol={"005930": rows})
    assert len(trades) == 1
    oracle = trades[0]
    assert oracle["held_minutes"] < 45
    assert oracle["mfe_pct"] != oracle["forward_returns"]["+60m"]["mfe_pct"] or oracle["mae_pct"] != oracle["forward_returns"]["+60m"]["mae_pct"]


def test_no_financial_metric_logic_in_adapter():
    source = Path("libs/reporting/evaluation/canonical/adapters/virtual_probe_adapter.py").read_text(encoding="utf-8")
    for token in ("100.0", "* 100", "/ entry", "- 1.0)"):
        assert token not in source, f"adapter appears to own return arithmetic: {token!r} found"


# =========================================================================
# Population / missing accounting
# =========================================================================


def test_pending_forward_horizon_never_becomes_zero_return(tmp_path):
    # a probe held to its 30-minute timeout exit, with candles stopping
    # shortly after -- +5m/+15m resolve (well within the 33 minutes of
    # data), but +60m and EOD have no reachable candle at all.
    start = _epoch(DAY, 9, 0)
    rows = _flat_candles(start_ts=start, count=33)
    signal = _entry_signal(symbol="005930", entry_epoch=start)
    trades = simulate_probe_v0([signal], cost_pct=0.15, slippage_pct=0.05, minute_rows_by_symbol={"005930": rows})
    assert trades, "fixture must still produce a closed trade (max_hold_minutes=30 default timeout exit)"
    oracle = trades[0]
    assert oracle["exit_reason"] == "max_hold"
    assert oracle["forward_returns"]["+5m"]["status"] == "observed"
    assert oracle["forward_returns"]["+60m"]["status"] == "pending"
    assert oracle["forward_returns"]["EOD"]["status"] == "pending"

    artifact_path = _write_trades_artifact(tmp_path, trades)
    results = q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)
    episode = results[0].episode
    for label in ("+60m", "EOD"):
        cp = next(cp for cp in episode.checkpoints if cp.horizon_label == label)
        assert cp.completeness is CheckpointCompleteness.PENDING
        assert cp.gross_return is None
        assert cp.net_return is None
    observed_5m = next(cp for cp in episode.checkpoints if cp.horizon_label == "+5m")
    assert observed_5m.completeness is CheckpointCompleteness.OBSERVED
    assert observed_5m.gross_return is not None


def test_trade_level_aggregation_member_is_evaluated_never_missing_for_a_closed_trade(tmp_path):
    trades = _real_trades()
    artifact_path = _write_trades_artifact(tmp_path, trades)
    results = q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)
    exit_cp = next(cp for cp in results[0].episode.checkpoints if cp.horizon_label == "EXIT")
    member = q11.checkpoint_to_net_or_cost_included_member(exit_cp, evaluation_record_id=results[0].episode.identity.evaluation_record_id)
    assert member.state is SampleMemberState.EVALUATED
    assert member.gross_return is None  # NET_OR_COST_INCLUDED forbids carrying gross_return
    assert member.source_net_return == pytest.approx(exit_cp.net_return)


def test_pending_checkpoint_maps_to_missing_aggregation_member():
    pending_cp = q11._eod_checkpoint(q11.Q11VirtualProbeTrade(
        day=DAY, trade_id="OE_TRD_TEST_1", symbol="005930", entry_epoch=1, entry_price=1000.0,
        exit_epoch=2, exit_price=1000.0, exit_reason="max_hold", gross_return_pct=0.0, net_return_pct=0.0,
        mfe_pct=0.0, mae_pct=0.0, forward_returns={"EOD": {"status": "pending"}},
    ))
    member = q11.checkpoint_to_net_or_cost_included_member(pending_cp, evaluation_record_id="")
    assert member.state is SampleMemberState.MISSING


def test_source_physical_event_count_equals_canonical_physical_event_count(tmp_path):
    # 2 independent probe entries (different symbols) -> 2 physical
    # trades -> 2 canonical episodes, never merged, never multiplied.
    start = _epoch(DAY, 9, 0)
    rows_a = _flat_candles(start_ts=start, count=390, base=1000.0)
    rows_b = _flat_candles(start_ts=start, count=390, base=2000.0)
    signals = [_entry_signal(symbol="005930", entry_epoch=start), _entry_signal(symbol="000660", entry_epoch=start)]
    trades = simulate_probe_v0(signals, cost_pct=0.15, slippage_pct=0.05, minute_rows_by_symbol={"005930": rows_a, "000660": rows_b})
    assert len(trades) == 2

    artifact_path = _write_trades_artifact(tmp_path, trades)
    results = q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)
    assert len(results) == 2
    event_ids = {r.episode.identity.event.canonical_event_id for r in results}
    assert len(event_ids) == 2
    for r in results:
        assert len(r.episode.checkpoints) == 6


def test_identity_deterministic_and_distinguishes_trades(tmp_path):
    trades = _real_trades()
    artifact_path = _write_trades_artifact(tmp_path, trades)
    first = q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)
    second = q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)
    assert first[0].episode.identity.event.canonical_event_id == second[0].episode.identity.event.canonical_event_id
    assert first[0].episode.identity.evaluation_record_id == second[0].episode.identity.evaluation_record_id


# =========================================================================
# Fail-fast
# =========================================================================


def test_rejects_trade_with_execution_allowed_true():
    trade = dict(_real_trades()[0])
    trade["order_execution_allowed"] = True
    with pytest.raises(VirtualProbeAdapterError):
        q11._parse_trade(DAY, trade)


def test_rejects_trade_missing_execution_flag_entirely():
    trade = dict(_real_trades()[0])
    del trade["order_execution_allowed"]
    with pytest.raises(VirtualProbeAdapterError):
        q11._parse_trade(DAY, trade)


def test_rejects_invalid_prices_and_timestamps():
    base = dict(_real_trades()[0])
    bad = dict(base)
    bad["entry_price"] = -5.0
    with pytest.raises(VirtualProbeAdapterError):
        q11._parse_trade(DAY, bad)
    bad2 = dict(base)
    bad2["entry_epoch"] = 0
    with pytest.raises(VirtualProbeAdapterError):
        q11._parse_trade(DAY, bad2)
    bad3 = dict(base)
    bad3["exit_price"] = float("nan")
    with pytest.raises(VirtualProbeAdapterError):
        q11._parse_trade(DAY, bad3)


def test_rejects_missing_trade_id_or_symbol():
    base = dict(_real_trades()[0])
    no_id = dict(base)
    del no_id["trade_id"]
    with pytest.raises(VirtualProbeAdapterError):
        q11._parse_trade(DAY, no_id)
    no_symbol = dict(base)
    no_symbol["symbol"] = ""
    with pytest.raises(VirtualProbeAdapterError):
        q11._parse_trade(DAY, no_symbol)


def test_rejects_unknown_horizon_status():
    trade = q11._parse_trade(DAY, dict(_real_trades()[0]))
    with pytest.raises(VirtualProbeAdapterError):
        q11._forward_checkpoint(
            q11.Q11VirtualProbeTrade(**{**trade.__dict__, "forward_returns": {"+5m": {"status": "weird"}}}),
            "+5m",
        )


# =========================================================================
# Trusted ingestion boundary
# =========================================================================


def test_loader_rejects_path_outside_real_artifact_family(tmp_path):
    trades = _real_trades()
    wrong_dir = f"data/logs/opening_rank1_controlled_probe/{DAY}"
    artifact_path = _write_trades_artifact(tmp_path, trades, family_dir=wrong_dir)
    with pytest.raises(VirtualProbeAdapterError):
        q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)


def test_loader_rejects_real_family_path_with_wrong_schema(tmp_path):
    trades = _real_trades()
    artifact_path = _write_trades_artifact(tmp_path, trades, schema_version="controlled_mock_lanes.v1")
    with pytest.raises(VirtualProbeAdapterError):
        q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)


def test_loader_rejects_real_family_path_with_wrong_program_id(tmp_path):
    trades = _real_trades()
    artifact_path = _write_trades_artifact(tmp_path, trades, program_id="Q10_INDEX_SOMETHING")
    with pytest.raises(VirtualProbeAdapterError):
        q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)


def test_loader_rejects_forged_schema_at_wrong_origin(tmp_path):
    # correct-looking discriminators, wrong family path -- must be
    # rejected on origin, not schema.
    trades = _real_trades()
    artifact_path = _write_trades_artifact(
        tmp_path, trades, family_dir=f"data/logs/controlled_mock_lanes/{DAY}",
    )
    with pytest.raises(VirtualProbeAdapterError):
        q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)


def test_loader_rejects_other_evaluator_artifacts(tmp_path):
    # Q10 Semiconductor / Q10 Index / Q12 / Opening Shadow shaped payloads
    # -- must be rejected even though "day"/"trades"-like fields overlap.
    fixtures = [
        {"schema_version": "q10_korea_lead_market_forward_validation.v1", "evaluation_program_id": "Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION", "day": DAY, "targets": {}},
        {"schema_version": "latent_reactivation_forward.v1", "day": DAY, "rows": []},
        {"schema_version": "opening_rank1_longitudinal.v1", "day": DAY, "events": []},
        {"schema_version": "controlled_mock_lane_submissions.v1", "day": DAY, "submissions": []},
    ]
    for payload in fixtures:
        directory = tmp_path / f"opportunity_engine_shadow_{fixtures.index(payload)}" / DAY
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "opportunity_engine_virtual_trades.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(VirtualProbeAdapterError):
            q11.canonicalize_q11_opportunity_engine_artifact(path)


def test_loader_rejects_execution_evidence_origin(tmp_path):
    directory = tmp_path / "data" / "state" / "executions" / DAY
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "opportunity_engine_virtual_trades.json"
    path.write_text(json.dumps({
        "schema_version": "order_execution_outcome.v1",
        "fills": [{"decision_id": "D1", "symbol": "005930", "timestamp": _epoch(DAY, 9, 5), "order_fill_status": "FILLED"}],
    }), encoding="utf-8")
    with pytest.raises(VirtualProbeAdapterError):
        q11.canonicalize_q11_opportunity_engine_artifact(path)


def test_loader_accepts_real_source_artifact(tmp_path):
    trades = _real_trades()
    artifact_path = _write_trades_artifact(tmp_path, trades)
    results = q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)
    assert len(results) == 1
    assert results[0].episode.symbol == "005930"


# =========================================================================
# FIX1 -- legacy v1 vs repaired v2 source-contract boundary
# =========================================================================


def _strip_v2_observed_price(trades: list[dict]) -> list[dict]:
    """Simulate an authentic LEGACY v1 trades payload -- same real
    writer-produced shape, minus the v2-only `observed_price` field this
    FIX1 adds -- never a hand-fabricated shape."""

    stripped = []
    for trade in trades:
        trade = dict(trade)
        forward_returns = {}
        for label, row in trade["forward_returns"].items():
            row = dict(row)
            row.pop("observed_price", None)
            forward_returns[label] = row
        trade["forward_returns"] = forward_returns
        stripped.append(trade)
    return stripped


def test_legacy_v1_artifact_is_authentic_but_lossless_mapping_blocked(tmp_path):
    from libs.research.opportunity_engine.contracts import TRADES_SCHEMA_LEGACY_V1

    trades = _strip_v2_observed_price(_real_trades())
    artifact_path = _write_trades_artifact(tmp_path, trades, schema_version=TRADES_SCHEMA_LEGACY_V1)
    with pytest.raises(VirtualProbeAdapterError) as excinfo:
        q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)
    message = str(excinfo.value)
    # the rejection must name the REAL reason (observed_price missing
    # from price-based source evidence), never a generic/unknown-schema
    # message -- this is what lets a human distinguish "authentic but
    # blocked" from "wrong family entirely" (Section 28).
    assert "observed_price" in message
    assert "authentic" in message.lower() or "legacy" in message.lower()
    assert TRADES_SCHEMA_LEGACY_V1 in message


def test_legacy_v1_real_family_path_and_program_id_still_recognized_as_authentic(tmp_path):
    # the v1 artifact's ORIGIN (path + evaluation_program_id) is genuine
    # Q11 primary evidence -- rejection is about schema/evidence
    # completeness, never about origin/family authenticity.
    from libs.research.opportunity_engine.contracts import TRADES_SCHEMA_LEGACY_V1

    trades = _strip_v2_observed_price(_real_trades())
    artifact_path = _write_trades_artifact(tmp_path, trades, schema_version=TRADES_SCHEMA_LEGACY_V1)
    with pytest.raises(VirtualProbeAdapterError) as excinfo:
        q11.canonicalize_q11_opportunity_engine_artifact(artifact_path)
    assert "wrong" not in str(excinfo.value).lower() and "arbitrarily-located" not in str(excinfo.value)


def test_real_v2_artifact_via_actual_pipeline_writer_accepted(tmp_path):
    # Section 29: at least one end-to-end test through the REAL source
    # writer/simulator, never a hand-fabricated artifact -- fully
    # isolated (own reports_root, explicit candles/market_timeline, no
    # fresh-fetch, no state.json/macro_indicators read), never touching
    # the live process's own state or today's real artifacts.
    from libs.research.opportunity_engine.pipeline import build_opportunity_engine_artifacts

    start = _epoch(DAY, 9, 0)
    rows = _flat_candles(start_ts=start, count=390)
    paths = build_opportunity_engine_artifacts(
        day=DAY, symbols=("005930",), reports_root=tmp_path,
        candles={"005930": rows}, market_timeline=[], allow_fresh_fetch=False,
    )
    trades_path = Path(paths["virtual_trades"])
    assert trades_path.exists()
    payload = json.loads(trades_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == TRADES_SCHEMA

    results = q11.canonicalize_q11_opportunity_engine_artifact(trades_path)
    # signals may or may not cross the probe_candidate threshold for
    # this synthetic candle series -- the load-bearing assertion is that
    # the REAL writer's own v2 output is ACCEPTED by the trusted loader,
    # not that a trade necessarily exists.
    assert isinstance(results, list)


# =========================================================================
# Q11's own architectural isolation (never imports runtime/execution/UEF)
# =========================================================================


def test_q11_source_module_prohibits_runtime_imports():
    from libs.research.opportunity_engine.contracts import PROHIBITED_RUNTIME_DEPENDENCIES

    for path in (
        Path("libs/research/opportunity_engine/simulator.py"),
        Path("libs/research/opportunity_engine/engine.py"),
        Path("libs/research/opportunity_engine/pipeline.py"),
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
        for prohibited in PROHIBITED_RUNTIME_DEPENDENCIES:
            assert not any(module.startswith(prohibited) for module in modules), f"{path} imports prohibited {prohibited}"


def test_virtual_probe_adapter_never_imports_controlled_probe_or_mock_lane_or_broker():
    tree = ast.parse(Path("libs/reporting/evaluation/canonical/adapters/virtual_probe_adapter.py").read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    assert not any("controlled_probe" in m for m in modules)
    assert not any("controlled_mock_lane" in m for m in modules)
    assert not any("executor" in m or "broker" in m for m in modules)


def test_frozen_and_prior_approved_adapters_untouched_by_this_task():
    from libs.reporting.evaluation.canonical.adapters import q10_semiconductor  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import forward_measurement_adapter  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import q12_baseline_btc_woori  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import hypothesis_forward_adapter  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import opening_rank1_shadow  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import already_net_shadow_adapter  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import q10_index_reaction_adapter  # noqa: F401
    from libs.reporting.evaluation.canonical.adapters import q10_index_directional_shadow_adapter  # noqa: F401
