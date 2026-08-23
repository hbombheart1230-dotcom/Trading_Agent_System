from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.baseline_samsung_hynix.contracts import (
    DECISIONS_SCHEMA,
    FORWARD_SCHEMA,
    HORIZONS,
)
from libs.reporting.baseline_samsung_hynix.forward_returns import (
    summarize_forward_returns,
)
from libs.reporting.baseline_samsung_hynix.data_provider import (
    load_existing_candles,
    load_market_timeline,
    market_snapshot_at,
)
from libs.reporting.baseline_samsung_hynix.pipeline import build_baseline_artifacts
from libs.reporting.baseline_samsung_hynix.q9_comparison import (
    build_q9_role_comparison,
)
from libs.reporting.baseline_samsung_hynix.report import render_daily_report
from libs.reporting.baseline_samsung_hynix.strategy import build_decision_snapshot
from libs.reporting.baseline_samsung_hynix.unified_comparison import (
    build_unified_comparison,
    render_unified_comparison,
)
from libs.reporting.evaluation.five_day_freeze import build_freeze_manifest


def _candles(
    *,
    start_epoch: int,
    start_price: float,
    price_step: float,
    volume_last: float = 300.0,
) -> list[dict]:
    rows = []
    for index in range(61):
        price = start_price + (price_step * index)
        rows.append(
            {
                "ts": start_epoch + (index * 60),
                "raw_ts": f"2026062409{index:02d}00",
                "open": price,
                "high": price + 1,
                "low": price - 1,
                "close": price,
                "volume": volume_last if index == 30 else 100.0,
            }
        )
    return rows


def test_deterministic_ranking() -> None:
    epoch = 1782261000
    candles = {
        "005930": _candles(start_epoch=epoch, start_price=80000, price_step=20),
        "000660": _candles(start_epoch=epoch, start_price=180000, price_step=200),
    }

    first = build_decision_snapshot(
        day="2026-06-24",
        as_of_epoch=epoch + (30 * 60),
        candles=candles,
        market_change_pct=0.5,
    )
    second = build_decision_snapshot(
        day="2026-06-24",
        as_of_epoch=epoch + (30 * 60),
        candles=dict(reversed(list(candles.items()))),
        market_change_pct=0.5,
    )

    assert [row["symbol"] for row in first["ranked_candidates"]] == [
        row["symbol"] for row in second["ranked_candidates"]
    ]
    assert first["ranked_candidates"][0]["symbol"] == "000660"


def test_fixed_universe_only() -> None:
    epoch = 1782261000
    result = build_decision_snapshot(
        day="2026-06-24",
        as_of_epoch=epoch + (30 * 60),
        candles={
            "005930": _candles(start_epoch=epoch, start_price=80000, price_step=10),
            "000660": _candles(start_epoch=epoch, start_price=180000, price_step=10),
            "035420": _candles(start_epoch=epoch, start_price=200000, price_step=1000),
        },
        market_change_pct=0.0,
    )

    assert {row["symbol"] for row in result["ranked_candidates"]} == {"005930", "000660"}
    assert result["universe"] == ["005930.KS", "000660.KS"]


def test_artifact_schema_and_shadow_constraints(tmp_path: Path) -> None:
    epoch = 1782261000
    cost_path = tmp_path / "cost.json"
    cost_path.write_text(
        json.dumps(
            {
                "source": "kiwoom.ka10170",
                "sample_count": 3,
                "conservative_round_trip_cost_pct": 0.002,
            }
        ),
        encoding="utf-8",
    )
    result = build_baseline_artifacts(
        day="2026-06-24",
        reports_root=tmp_path / "reports",
        cost_profile_path=cost_path,
        q9_root=tmp_path / "q9",
        candles={
            "005930": _candles(start_epoch=epoch, start_price=80000, price_step=10),
            "000660": _candles(start_epoch=epoch, start_price=180000, price_step=20),
        },
        market_change_pct=0.0,
        as_of_epoch=epoch + (30 * 60),
    )
    decisions = json.loads(Path(result["decisions"]).read_text(encoding="utf-8"))
    forward = json.loads(Path(result["forward_returns"]).read_text(encoding="utf-8"))

    assert decisions["schema_version"] == DECISIONS_SCHEMA
    assert forward["schema_version"] == FORWARD_SCHEMA
    assert decisions["measurement_contract_version"] == "q10_point_in_time_market.v2"
    assert forward["measurement_contract_version"] == "q10_extended_forward.v2"
    decision = decisions["decisions"][0]
    assert decision["order_execution_allowed"] is False
    assert decision["llm_used"] is False
    assert decision["strategist_used"] is False
    assert decision["commander_used"] is False
    assert decision["entry_rule_count"] <= 3
    assert decision["exit_rule_count"] <= 2


def test_cost_and_slippage_are_applied() -> None:
    summary = summarize_forward_returns(
        [
            {
                "baseline_decision_id": "D1",
                "rank": 1,
                "eligible": True,
                "returns": {"+5m": {"status": "observed", "return_pct": 1.0}},
            },
            {
                "baseline_decision_id": "D1",
                "rank": 2,
                "eligible": True,
                "returns": {"+5m": {"status": "observed", "return_pct": 0.0}},
            },
        ],
        cost_pct=0.2,
        slippage_pct=0.1,
    )
    row = next(item for item in summary["horizons"] if item["horizon"] == "+5m")

    assert row["top1_gross"]["average_return_pct"] == 1.0
    assert row["top1_net"]["average_return_pct"] == 0.7
    assert row["both_symbol_average_net"]["average_return_pct"] == 0.2


def test_comparison_report_generation(tmp_path: Path) -> None:
    baseline_summary = {
        "horizons": [
            {
                "horizon": horizon,
                "top1_net": {"expectancy_pct": 0.25},
                "both_symbol_average_net": {"average_return_pct": 0.1},
                "top1_minus_both_average_net_pct": 0.15,
            }
            for horizon in ("+5m", "+15m", "+30m", "EOD")
        ]
    }
    comparison = build_q9_role_comparison(
        day="2026-06-24",
        baseline_summary=baseline_summary,
        cost_pct=0.2,
        slippage_pct=0.1,
        q9_root=tmp_path,
    )
    markdown = render_daily_report(
        day="2026-06-24",
        decisions={"decisions": []},
        forward={
            "cost_model": {"round_trip_cost_pct": 0.2, "slippage_pct": 0.1},
            "summary": baseline_summary,
            "q9_comparison": comparison,
        },
    )

    assert len(comparison["roles"]) == len(HORIZONS) * 4
    assert comparison["roles"][0]["baseline_minus_q9_expectancy_pct"] is None
    assert "Comparison vs Q9 P/A/B/C" in markdown
    assert "P_SCANNER_PRE_STRATEGIST_UNIVERSE" in markdown


def test_q9_comparison_uses_one_representative_per_role_and_window(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from libs.reporting.baseline_samsung_hynix import q9_comparison

    def fake_load(*, day, root, state_path):
        rows = []
        for role in (
            "P_SCANNER_PRE_STRATEGIST_UNIVERSE",
            "A_SCANNER_CONTROL",
            "B_STRATEGIST_RANKED",
            "C_COMMANDER_FINAL",
        ):
            rows.extend(
                [
                    {
                        "q9_decision_id": "D1",
                        "q9_decision_role": role,
                        "rank": 1,
                        "q9_selected": role != "B_STRATEGIST_RANKED",
                        "q9_commander_decision": "approve" if role == "C_COMMANDER_FINAL" else "",
                        "shadow_forward_outcome": {
                            "checkpoints": {
                                "+5m": {"status": "observed", "return_pct": 1.0}
                            }
                        },
                    },
                    {
                        "q9_decision_id": "D1",
                        "q9_decision_role": role,
                        "rank": 2,
                        "q9_selected": role == "B_STRATEGIST_RANKED",
                        "q9_commander_decision": "approve" if role == "C_COMMANDER_FINAL" else "",
                        "shadow_forward_outcome": {
                            "checkpoints": {
                                "+5m": {"status": "observed", "return_pct": -10.0}
                            }
                        },
                    },
                ]
            )
        return rows

    monkeypatch.setattr(q9_comparison, "_load_q9_rows", fake_load)
    result = build_q9_role_comparison(
        day="2026-06-24",
        baseline_summary={"horizons": []},
        cost_pct=0.0,
        slippage_pct=0.0,
        q9_root=tmp_path,
    )
    five_minute = {
        row["role"]: row["q9_net"]
        for row in result["roles"]
        if row["horizon"] == "+5m"
    }

    assert result["comparison_unit"] == "decision_window_representative_candidate"
    assert result["cohort_scope"] == "complete_pabc_decision_windows_only"
    assert result["forward_data_source"] == "state_plus_kiwoom_minute_recovery"
    assert result["comparable_complete_window_count"] == 1
    assert five_minute["P_SCANNER_PRE_STRATEGIST_UNIVERSE"]["count"] == 1
    assert five_minute["P_SCANNER_PRE_STRATEGIST_UNIVERSE"]["average_return_pct"] == 1.0
    assert five_minute["B_STRATEGIST_RANKED"]["average_return_pct"] == -10.0


def _unified_payload(
    *,
    baseline_avg: float,
    baseline_count: int,
    p_avg: float,
    b_avg: float,
    c_avg: float,
    q9_count: int = 30,
) -> dict:
    horizons = []
    roles = []
    role_values = {
        "P_SCANNER_PRE_STRATEGIST_UNIVERSE": p_avg,
        "A_SCANNER_CONTROL": p_avg,
        "B_STRATEGIST_RANKED": b_avg,
        "C_COMMANDER_FINAL": c_avg,
    }
    for horizon in ("+5m", "+15m", "+30m", "EOD"):
        horizons.append(
            {
                "horizon": horizon,
                "top1_net": {
                    "count": baseline_count,
                    "win_rate": 0.6,
                    "average_return_pct": baseline_avg,
                    "profit_factor": 1.5,
                    "maximum_drawdown_pct": -1.0,
                },
            }
        )
        for role, avg in role_values.items():
            roles.append(
                {
                    "role": role,
                    "horizon": horizon,
                    "q9_net": {
                        "count": q9_count,
                        "win_rate": 0.55,
                        "average_return_pct": avg,
                        "profit_factor": 1.2,
                        "maximum_drawdown_pct": -2.0,
                    },
                }
            )
    return {
        "day": "2026-06-24",
        "cost_model": {"round_trip_cost_pct": 0.2, "slippage_pct": 0.1},
        "summary": {"horizons": horizons},
        "q9_comparison": {
            "roles": roles,
            "forward_data_source": "state_plus_kiwoom_minute_recovery",
            "cohort_scope": "complete_pabc_decision_windows_only",
        },
    }


def test_unified_comparison_reports_multi_agent_alpha() -> None:
    result = build_unified_comparison(
        _unified_payload(
            baseline_avg=0.2,
            baseline_count=30,
            p_avg=0.1,
            b_avg=0.25,
            c_avg=0.4,
        )
    )
    primary = result["overall"]["multi_agent_alpha"]

    assert primary["status"] == "UNPAIRED_OUTPERFORMANCE"
    assert primary["commander_minus_baseline_pct"] == 0.2
    assert primary["adds_alpha"] is None
    assert primary["causal_alpha_supported"] is False
    assert result["overall"]["best_performer"]["performer"] == "C_COMMANDER_FINAL"
    assert result["q9_forward_data_source"] == "state_plus_kiwoom_minute_recovery"
    assert result["q9_cohort_scope"] == "complete_pabc_decision_windows_only"


def test_unified_comparison_attributes_strategist_degradation() -> None:
    result = build_unified_comparison(
        _unified_payload(
            baseline_avg=0.3,
            baseline_count=30,
            p_avg=0.6,
            b_avg=0.1,
            c_avg=0.2,
        )
    )
    primary = result["overall"]["multi_agent_alpha"]

    assert primary["status"] == "UNPAIRED_UNDERPERFORMANCE"
    assert primary["root_cause"] == "strategy_weighting_degraded_scanner_intrinsic_edge"
    assert "Strategy-Weighted Scanner" in render_unified_comparison(result)


def test_unified_comparison_handles_missing_baseline_sample() -> None:
    result = build_unified_comparison(
        _unified_payload(
            baseline_avg=0.0,
            baseline_count=0,
            p_avg=0.1,
            b_avg=0.2,
            c_avg=0.3,
        )
    )
    primary = result["overall"]["multi_agent_alpha"]
    markdown = render_unified_comparison(result)

    assert primary["status"] == "INSUFFICIENT_EVIDENCE"
    assert primary["root_cause"] == "insufficient_comparable_forward_samples"
    assert "Unified Metrics" in markdown
    assert "Best Performer" in markdown


def test_q9_commander_rejection_is_cash_not_strategist_candidate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from libs.reporting.baseline_samsung_hynix import q9_comparison

    rows = []
    for role in (
        "P_SCANNER_PRE_STRATEGIST_UNIVERSE",
        "A_SCANNER_CONTROL",
        "B_STRATEGIST_RANKED",
        "C_COMMANDER_FINAL",
    ):
        rows.append(
            {
                "q9_decision_id": "D_REJECT",
                "q9_decision_role": role,
                "rank": 1,
                "q9_selected": role == "B_STRATEGIST_RANKED",
                "q9_commander_decision": "reject" if role == "C_COMMANDER_FINAL" else "",
                "q9_commander_no_trade": role == "C_COMMANDER_FINAL",
                "shadow_forward_outcome": {
                    "checkpoints": {
                        "+5m": {"status": "observed", "return_pct": 5.0},
                    }
                },
            }
        )

    monkeypatch.setattr(q9_comparison, "_load_q9_rows", lambda **_: rows)
    result = build_q9_role_comparison(
        day="2026-07-22",
        baseline_summary={"horizons": []},
        cost_pct=0.2,
        slippage_pct=0.1,
        q9_root=tmp_path,
    )
    commander = next(
        row
        for row in result["roles"]
        if row["role"] == "C_COMMANDER_FINAL" and row["horizon"] == "+5m"
    )

    assert commander["q9_net"]["average_return_pct"] == 0.0
    assert commander["cash_no_trade_count"] == 1
    assert commander["active_candidate_count"] == 0


def test_reconstruct_intraday_creates_forward_windows(tmp_path: Path) -> None:
    epoch = 1782262800
    cost_path = tmp_path / "cost.json"
    cost_path.write_text(
        json.dumps({"conservative_round_trip_cost_pct": 0.002}),
        encoding="utf-8",
    )
    result = build_baseline_artifacts(
        day="2026-06-24",
        reports_root=tmp_path / "reports",
        cost_profile_path=cost_path,
        q9_root=tmp_path / "q9",
        candles={
            "005930": _candles(start_epoch=epoch, start_price=80000, price_step=10),
            "000660": _candles(start_epoch=epoch, start_price=180000, price_step=20),
        },
        market_change_pct=0.0,
        reconstruct_intraday=True,
    )
    decisions = json.loads(Path(result["decisions"]).read_text(encoding="utf-8"))
    forward = json.loads(Path(result["forward_returns"]).read_text(encoding="utf-8"))
    five_minute = next(
        row for row in forward["summary"]["horizons"] if row["horizon"] == "+5m"
    )

    assert decisions["decision_count"] > 1
    assert five_minute["top1_observation_count"] > 0


def test_reconstruct_intraday_removes_off_grid_manual_snapshot(tmp_path: Path) -> None:
    epoch = 1782262800
    candles = {
        "005930": _candles(start_epoch=epoch, start_price=80000, price_step=10),
        "000660": _candles(start_epoch=epoch, start_price=180000, price_step=20),
    }
    build_baseline_artifacts(
        day="2026-06-24",
        reports_root=tmp_path / "reports",
        q9_root=tmp_path / "q9",
        candles=candles,
        market_change_pct=0.0,
        as_of_epoch=epoch + (31 * 60),
    )
    result = build_baseline_artifacts(
        day="2026-06-24",
        reports_root=tmp_path / "reports",
        q9_root=tmp_path / "q9",
        candles=candles,
        market_change_pct=0.0,
        reconstruct_intraday=True,
    )
    decisions = json.loads(Path(result["decisions"]).read_text(encoding="utf-8"))

    assert decisions["decisions"]
    assert all(int(row["as_of_epoch"]) % 300 == 0 for row in decisions["decisions"])


def test_data_provider_refreshes_stale_nonempty_cache(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "recent_minute_ohlcv_by_symbol": {
                    "005930": {
                        "rows": [
                            {
                                "ts": 1782262800,
                                "raw_ts": "20260624100000",
                                "close": 100.0,
                                "volume": 10.0,
                            }
                        ]
                        * 10
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    def fake_fetch(symbol, *, run_id):
        return [
            {
                "ts": 1782282600,
                "raw_ts": "20260624153000",
                "close": 110.0,
                "volume": 20.0,
            }
        ], {"ok": True}

    monkeypatch.setattr(
        "libs.reporting.post_exit_shadow_recap.fetch_fresh_minute_rows_for_symbol",
        fake_fetch,
    )
    result = load_existing_candles(
        state_path=state_path,
        day="2026-06-24",
        symbols=("005930",),
        allow_fresh_fetch=True,
    )

    assert result["005930"][-1]["raw_ts"] == "20260624153000"


def test_market_snapshot_is_resolved_at_decision_time(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-06-24"
    day_dir.mkdir()
    for name, generated_at, value in (
        ("090000_macro_indicators.json", "2026-06-24T00:00:00+00:00", -1.0),
        ("100000_macro_indicators.json", "2026-06-24T01:00:00+00:00", 2.0),
    ):
        (day_dir / name).write_text(
            json.dumps({"generated_at": generated_at, "index_moves": {"kospi_pct": value}}),
            encoding="utf-8",
        )

    timeline = load_market_timeline(day="2026-06-24", macro_root=tmp_path)
    snapshot = market_snapshot_at(timeline, epoch=1782261000)

    assert snapshot["kospi_pct"] == -1.0
    assert snapshot["snapshot_age_sec"] == 1800


def test_data_provider_retries_empty_fresh_response(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text("{}", encoding="utf-8")
    calls = []

    def fake_fetch(symbol, *, run_id):
        calls.append(run_id)
        if len(calls) == 1:
            return [], {"ok": False}
        return [{
            "ts": 1782282600,
            "raw_ts": "20260624153000",
            "close": 110.0,
            "volume": 20.0,
        }], {"ok": True}

    monkeypatch.setattr(
        "libs.reporting.post_exit_shadow_recap.fetch_fresh_minute_rows_for_symbol",
        fake_fetch,
    )
    result = load_existing_candles(
        state_path=state_path,
        day="2026-06-24",
        symbols=("005930",),
        allow_fresh_fetch=True,
        run_id_prefix="q9_comparison_forward_recovery",
    )

    assert len(calls) == 2
    assert all(
        run_id.startswith("q9_comparison_forward_recovery_2026-06-24_005930_")
        for run_id in calls
    )
    assert result["005930"][-1]["raw_ts"] == "20260624153000"


def test_five_day_freeze_manifest_is_behavior_locked() -> None:
    manifest = build_freeze_manifest()

    assert manifest["target_valid_trading_days"] == 5
    assert manifest["planned_weekdays"] == [
        "2026-06-29",
        "2026-06-30",
        "2026-07-01",
        "2026-07-02",
        "2026-07-03",
    ]
    assert manifest["window_id"] == "q9_q10_q11_q12_5d_20260629"
    assert manifest["behavior_changes_allowed"] is False
    assert manifest["observability_reporting_fixes_allowed"] is True
