from __future__ import annotations

import json
from pathlib import Path


def write_performance_day(
    reports_root: Path,
    day: str,
    rows: list[dict],
) -> None:
    target = reports_root / "performance" / day / "summary.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(
            {
                "schema_version": "performance_summary.v1",
                "day": day,
                "generated_at": f"{day}T07:00:00+00:00",
                "total_trades": len(rows),
                "trade_rows": rows,
            }
        ),
        encoding="utf-8",
    )


def trade_row(
    trade_id: str,
    day: str,
    value: float | None,
    pnl: float | None = None,
) -> dict:
    return {
        "trade_id": trade_id,
        "day": day,
        "symbol": "005930",
        "return": value,
        "pnl": pnl,
        "return_basis": "truth_surface_net" if value is not None else "lifecycle",
    }


def write_operator_day(
    reports_root: Path,
    day: str,
    positions: list[dict],
    *,
    reconciled: bool = True,
) -> None:
    target = (
        reports_root
        / "operator_summary"
        / "daily"
        / day
        / "daily_summary.json"
    )
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(
            {
                "schema_version": "daily_operator_summary.v1",
                "day": day,
                "generated_at": f"{day}T07:01:00+00:00",
                "residual_positions": {
                    "available": True,
                    "source": "state_snapshot",
                    "position_count": len(positions),
                    "positions": positions,
                    "account_snapshot_reconciliation": {
                        "available": reconciled,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def write_trade_bundle(
    reports_root: Path,
    day: str = "2026-08-10",
    symbol: str = "005930",
    sequence: str = "01",
    *,
    excluded: bool = False,
) -> tuple[str, Path]:
    compact_day = day.replace("-", "")
    trade_id = f"TRD_{compact_day}_{symbol}_{sequence}"
    root = reports_root / "trades" / day / "0900" / trade_id
    report_root = root / "reports"
    report_root.mkdir(parents=True)
    summary = {
        "schema_version": "ai_trade_summary_input.v1",
        "trade": {
            "trade_id": trade_id,
            "day": day,
            "symbol": symbol,
            "symbol_name": "Samsung Electronics",
            "themes": ["Semiconductor", "AI"],
            "status": "closed",
        },
        "truth_surface": {
            "buy_price": 100.0,
            "sell_price": 102.0,
            "pnl": 1800.0,
            "pnl_pct": 0.018,
            "result_label": "win",
            "cost_analysis": {"quantity": 10, "total_cost": 200.0},
        },
        "market_and_strategy": {"playbook": "breakout", "risk_tone": "balanced"},
        "strategy_horizon": {
            "strategist_horizon": "intraday",
            "commander_horizon": "intraday",
            "actual_hold_sec": 120.0,
        },
        "decision_flow": {
            "scanner_rank": 1,
            "scanner_chart_fit_score": 0.82,
            "selection_basis": "combined scanner ranking score",
            "entry_reason": "confirmed breakout",
            "exit_trigger": "target reached",
        },
        "quant_tactic": {
            "tactic_id": "confirmed_breakout",
            "tactic_suitability": {"score": 0.76},
        },
        "post_exit_shadow": {
            "checkpoints": {
                "+5m": {
                    "status": "observed",
                    "observed_ts": f"{day}T00:08:00+00:00",
                    "price": 103.0,
                    "return_pct": 0.0098,
                }
            }
        },
    }
    _write_json(report_root / "ai_trade_summary_input.json", summary)
    _write_json(
        root / "entry.json",
        {
            "ts": f"{day}T00:01:00+00:00",
            "action": "BUY",
            "symbol": symbol,
            "filled_price": 100.0,
            "filled_qty": 10,
            "reason_human": "confirmed breakout",
        },
    )
    _write_json(
        root / "hold.json",
        {
            "holding_events": [
                {
                    "ts": f"{day}T00:00:30+00:00",
                    "monitor_context": {"reason": "stale pre-entry row"},
                },
                {
                    "ts": f"{day}T00:02:00+00:00",
                    "monitor_context": {
                        "reason": "trend intact",
                        "current_price": 101.0,
                    },
                },
            ]
        },
    )
    _write_json(
        root / "exit.json",
        {
            "ts": f"{day}T00:03:00+00:00",
            "action": "SELL",
            "symbol": symbol,
            "filled_price": 102.0,
            "filled_qty": 10,
            "reason_human": "broker close confirmed",
        },
    )
    _write_json(
        root / "_health.json",
        {
            "lifecycle_status": "closed",
            "lifecycle_completeness": "complete",
            "completeness_score": 1.0,
            "broker_reconciliation": {"status": "closed_by_broker_truth"},
        },
    )
    _write_json(
        root / "_provenance.json",
        {"agent_sources": {"scanner": "canonical", "monitor": "canonical"}},
    )
    _write_json(
        report_root / "quant_trade_diagnosis.json",
        {
            "scanner_ranking": {"score_total": 0.63},
            "evidence": {"source_path": r"C:\secret\artifact.json"},
        },
    )
    _write_json(
        report_root / "post_exit_shadow_recap.json",
        {"trade_id": trade_id, "report_path": r"C:\secret\report.md"},
    )
    if excluded:
        _write_json(
            root / "evaluation_exclusion.json",
            {"active": True, "reason_code": "confirmed_runtime_defect"},
        )
    (report_root / "ai_trade_summary.md").write_text(
        "# Summary\n\nSafe text. C:\\secret\\report.json\n",
        encoding="utf-8",
    )
    (report_root / "quant_trade_diagnosis.md").write_text("# Diagnosis\n", encoding="utf-8")
    (report_root / "post_exit_shadow_recap.md").write_text("# Post Exit\n", encoding="utf-8")
    (root / "lifecycle_bundle.json").write_text("not read by M3", encoding="utf-8")
    return trade_id, root


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_opportunity_day(reports_root: Path, day: str) -> None:
    signal_root = reports_root / "evaluation" / "opportunity_engine_shadow" / day
    _write_json(
        signal_root / "opportunity_engine_signals.json",
        {
            "schema_version": "opportunity_engine_signals.v1",
            "behavior_effect": "shadow_only",
            "day": day,
            "signal_count": 2,
            "signals": [
                {
                    "signal_id": "S1",
                    "symbol": "005930",
                    "as_of_epoch": 1786500000,
                    "market": {"state": "RECOVERY"},
                    "symbol_features": {
                        "price": 100.0,
                        "market_relative_strength_proxy": 0.3,
                        "vwap_distance_pct": 0.2,
                        "robust_volume_ratio": 1.4,
                        "breakout_5m": False,
                    },
                    "opportunity": {
                        "score": 0.6,
                        "state": "WATCH",
                        "probe_candidate": False,
                        "probe_near_miss": True,
                        "probe_fail_reasons": ["volume_confirmation_missing"],
                    },
                },
                {
                    "signal_id": "S2",
                    "symbol": "005930",
                    "as_of_epoch": 1786500060,
                    "market": {"state": "RECOVERY"},
                    "symbol_features": {
                        "price": 101.0,
                        "market_relative_strength_proxy": 0.5,
                        "vwap_distance_pct": 0.4,
                        "robust_volume_ratio": 1.8,
                        "breakout_5m": True,
                    },
                    "opportunity": {
                        "score": 0.9,
                        "state": "READY",
                        "probe_candidate": True,
                        "probe_near_miss": False,
                        "probe_fail_reasons": [],
                    },
                },
            ],
        },
    )
    _write_json(
        reports_root
        / "operator_summary"
        / "daily"
        / day
        / "q8_shadow_blocker_review.json",
        {
            "schema_version": "q8_shadow_blocker_review.v1",
            "behavior_effect": "evaluation_only",
            "raw_candidate_count": 10,
            "deduped_candidate_count": 8,
            "duplicate_count": 2,
            "evaluation_trust_gate": {"trusted_forward_coverage": 0.75},
            "groups": [
                {
                    "reason": "volume_confirmation_missing",
                    "candidate_count": 4,
                    "observed_count": 3,
                    "coverage": 0.75,
                    "positive_latest_rate": 0.33,
                    "missed_opportunity_rate": 0.25,
                    "adverse_rate": 0.5,
                    "avg_latest_return_pct": -0.2,
                    "decision": "retain_under_observation",
                }
            ],
        },
    )
    _write_json(
        reports_root
        / "evaluation"
        / "opening_rank1_shadow"
        / day
        / "opening_rank1_shadow_daily.json",
        {
            "schema_version": "opening_rank1_shadow.v1",
            "behavior_effect": "observation_only",
            "day": day,
            "episodes": [
                {
                    "episode_id": f"OPEN:{day}:005930:1",
                    "symbol": "005930",
                    "rank": 1,
                    "score_total": 0.88,
                    "sources": ["top_value", "top_volume"],
                    "decision_time_kst": f"{day}T09:01:00+09:00",
                    "entry_time_kst": f"{day}T09:02:00+09:00",
                    "prospective_eligible": True,
                    "opening_observability": {
                        "asset_observation": {"symbol_name": "Samsung Electronics"}
                    },
                    "checkpoints": {
                        "+5m": {
                            "status": "observed",
                            "gross_return_pct": 1.0,
                            "live_net_return_pct": 0.72,
                            "mock_net_return_pct": 0.2,
                            "mfe_pct": 1.4,
                            "mae_pct": -0.3,
                        },
                        "+15m": {"status": "pending"},
                    },
                }
            ],
        },
    )


def write_market_day(logs_root: Path, day: str, *, kospi_change: float) -> None:
    _write_json(
        logs_root / "macro_indicators" / day / "latest.json",
        {
            "schema_version": "global_sentiment_macro_snapshot.v1",
            "generated_at": f"{day}T01:00:00+00:00",
            "global_sentiment": {"score": 0.2, "reason": "balanced", "status": "ok"},
            "korea_indices": {
                "rising": 600,
                "falling": 400,
                "unchanged": 50,
                "breadth": 0.2,
            },
            "korea_index_sanity": {"warning_count": 0, "warnings": []},
            "macro_indicators": {
                "indicators": {
                    "kospi": {
                        "key": "kospi",
                        "label": "KOSPI",
                        "category": "equity_index",
                        "current": 3000.0 + kospi_change,
                        "change": kospi_change,
                        "change_pct": kospi_change,
                        "unit": "index_point",
                        "status": "ok",
                        "source": "fixture",
                        "role": "korea_equity_market_direction",
                    },
                    "usdkrw": {
                        "key": "usdkrw",
                        "label": "USD/KRW",
                        "category": "fx",
                        "current": 1400.0,
                        "change_pct": -0.1,
                        "unit": "fx_rate",
                        "status": "ok",
                        "source": "fixture",
                        "role": "won_vs_dollar_pressure",
                    },
                }
            },
        },
    )
