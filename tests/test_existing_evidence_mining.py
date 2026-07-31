from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from libs.research.existing_evidence_mining.analysis import (
    actual_trade_analysis,
    blocked_opportunity_analysis,
    discovery_cohorts,
    simulate_path_policies,
)
from libs.research.existing_evidence_mining.episodes import (
    candidate_integrity,
    source_class,
)
from libs.research.existing_evidence_mining.loaders import load_q9_candidate_windows
from libs.research.existing_evidence_mining.loaders import load_latest_q16_samples
from libs.research.existing_evidence_mining.loaders import load_quant_shadow_samples
from libs.research.existing_evidence_mining.report import render_markdown


def test_source_class_is_deterministic() -> None:
    assert source_class(["top_value", "top_volume"]) == "market_native_multi"
    assert source_class(["top_value"]) == "market_native_single"
    assert source_class(["sector_theme"]) == "sector_theme_only"
    assert source_class(["sector_theme", "top_change_rate"]) == "mixed_market_theme"
    assert source_class(["strategist_backfill"]) == "strategist_backfill"


def test_q9_loader_preserves_point_in_time_sources(tmp_path: Path) -> None:
    day = "2026-07-01"
    root = tmp_path / "operator_summary" / "daily" / day
    root.mkdir(parents=True)
    epoch = int(
        datetime(2026, 7, 1, 9, 30, tzinfo=timezone(timedelta(hours=9))).timestamp()
    )
    payload = {
        "windows": [
            {
                "window_type": "scanner_selection",
                "decision_id": "D1",
                "decision_epoch": epoch,
                "scanner_pre_strategist_universe": {
                    "intrinsic_ranked_top20": [
                        {"rank": 2, "symbol": "000660", "sources": ["top_volume"]},
                        {"rank": 1, "symbol": "005930", "sources": ["top_value", "top_volume"]},
                    ]
                },
            }
        ]
    }
    root.joinpath("q9_decision_windows.json").write_text(json.dumps(payload), encoding="utf-8")

    result = load_q9_candidate_windows(reports_root=tmp_path, start=day, end=day)

    assert result["canonical_window_count"] == 1
    assert [row["symbol"] for row in result["windows"][0]["candidates"]] == ["005930", "000660"]
    assert result["windows"][0]["candidates"][0]["sources"] == ["top_value", "top_volume"]


def test_q16_loader_deduplicates_same_symbol_and_baseline_minute(tmp_path: Path) -> None:
    day = "2026-07-30"
    root = tmp_path / "evaluation" / "daily" / day
    root.mkdir(parents=True)
    samples = []
    for decision_id, count in (("D1", 2), ("D2", 3)):
        samples.append(
            {
                "q9_decision_id": decision_id,
                "symbol": "005930",
                "shadow_forward_outcome": {
                    "available": True,
                    "baseline_epoch": 100,
                    "observed_checkpoint_count": count,
                    "checkpoints": {},
                },
            }
        )
    root.joinpath("q16_proxy_rejection_review.json").write_text(
        json.dumps({"start_day": day, "end_day": day, "samples": samples}),
        encoding="utf-8",
    )

    result = load_latest_q16_samples(reports_root=tmp_path, start=day, end=day)

    assert result["raw_sample_count"] == 2
    assert result["sample_count"] == 1
    assert (
        result["samples"][0]["shadow_forward_outcome"]["observed_checkpoint_count"]
        == 3
    )


def test_quant_shadow_loader_applies_symbol_spacing(tmp_path: Path) -> None:
    day = "2026-07-01"
    root = tmp_path / day
    root.mkdir(parents=True)
    for index, epoch in enumerate((1000, 1060, 1960), start=1):
        root.joinpath(f"{index}.json").write_text(
            json.dumps(
                {
                    "candidates": [
                        {
                            "symbol": "005930",
                            "reason": "entry_wait",
                            "shadow_forward_base": {
                                "available": True,
                                "baseline_epoch": epoch,
                                "baseline_price": 100.0,
                            },
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    result = load_quant_shadow_samples(
        logs_root=tmp_path,
        start=day,
        end=day,
        gap_sec=900,
    )

    assert result["raw_candidate_count"] == 3
    assert result["minute_deduped_count"] == 3
    assert result["spaced_sample_count"] == 2


def test_quant_shadow_loader_reads_one_snapshot_per_clock_bucket(tmp_path: Path) -> None:
    day = "2026-07-01"
    root = tmp_path / day
    root.mkdir(parents=True)
    for stamp, symbol in (("000001", "005930"), ("000059", "000660"), ("001501", "009150")):
        root.joinpath(f"20260701_{stamp}Z_x.json").write_text(
            json.dumps(
                {
                    "candidates": [
                        {
                            "symbol": symbol,
                            "shadow_forward_base": {
                                "available": True,
                                "baseline_epoch": 1000 + len(symbol),
                                "baseline_price": 100.0,
                            },
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    result = load_quant_shadow_samples(logs_root=tmp_path, start=day, end=day)

    assert result["source_file_count"] == 3
    assert result["sampled_source_file_count"] == 2


def test_quant_shadow_loader_labels_non_entered_disposition(tmp_path: Path) -> None:
    day = "2026-07-01"
    root = tmp_path / day
    root.mkdir(parents=True)
    root.joinpath("20260701_000001Z_x.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "symbol": "005930",
                        "guard_blocked": True,
                        "intent_submitted": False,
                        "shadow_forward_base": {
                            "available": True,
                            "baseline_epoch": 1000,
                            "baseline_price": 100.0,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = load_quant_shadow_samples(logs_root=tmp_path, start=day, end=day)

    assert result["samples"][0]["opportunity_disposition"] == "guard_blocked"


def test_candidate_integrity_identifies_theme_only_windows() -> None:
    result = candidate_integrity(
        [
            {"candidates": [{"symbol": "A", "sources": ["sector_theme"], "score_breakdown": {"momentum": 0}}]},
            {"candidates": [{"symbol": "B", "sources": ["top_value"], "score_breakdown": {"momentum": 1}}]},
        ]
    )
    assert result["sector_theme_only_window_count"] == 1
    assert result["market_native_window_count"] == 1
    assert result["score_component_quality"]["momentum"]["zero_rate"] == 0.5


def test_blocked_opportunity_cost_applies_live_cost() -> None:
    samples = [
        {
            "reason": "volume_confirmation_missing",
            "primary_failure_axis": "volume",
            "entry_lane": "pullback",
            "entry_quant_cost_floor_state": "met",
            "shadow_forward_outcome": {
                "checkpoints": {
                    "+15m": {
                        "status": "observed",
                        "return_pct": 0.5,
                        "mfe_pct": 0.8,
                        "mae_pct": -0.2,
                    }
                }
            },
        }
    ]
    result = blocked_opportunity_analysis(samples)
    row = result["by_reason"]["volume_confirmation_missing"]["+15m"]
    assert row["net_metrics"]["average_return_pct"] == 0.22
    assert row["blocked_net_winner_rate"] == 1.0


def test_path_policy_uses_conservative_same_bar_stop() -> None:
    episodes = [
        {
            "symbol": "005930",
            "day": "2026-07-01",
            "baseline_epoch": 100,
            "baseline_price": 100.0,
        }
    ]
    rows = {
        "005930": [
            {
                "ts": 100,
                "raw_ts": "20260701090000",
                "open": 100.0,
                "high": 103.0,
                "low": 98.0,
                "close": 101.0,
            }
        ]
    }
    result = simulate_path_policies(episodes, minute_rows_by_symbol=rows)
    first = result["target_1.0_stop_0.5_30m"]
    assert first["exit_reasons"]["stop"] == 1
    assert first["metrics"]["average_return_pct"] == -0.78


def test_discovery_cohort_keeps_calibration_and_retrospective_separate() -> None:
    def episode(day: str, value: float) -> dict:
        return {
            "day": day,
            "symbol": "005930",
            "time_bucket": "open_0_20m",
            "rank_bucket": "rank1",
            "checkpoints": {
                "+30m": {
                    "status": "observed",
                    "live_net_return_pct": value,
                    "gross_return_pct": value + 0.28,
                    "mfe_pct": 1.0,
                    "mae_pct": -0.5,
                }
            },
        }

    result = discovery_cohorts(
        [episode("2026-07-10", 1.0), episode("2026-07-13", -0.5)]
    )["opening_rank1"]

    assert result["calibration"]["+30m"]["metrics"]["average_return_pct"] == 1.0
    assert result["retrospective"]["+30m"]["metrics"]["average_return_pct"] == -0.5


def test_actual_trade_analysis_separates_early_exit_returns() -> None:
    rows = [
        {
            "realized_outcome": {"net_return_pct": -1.0, "holding_seconds": 30},
            "integrity": {"promotion_metric_eligible": True},
            "horizon_alignment": {
                "exited_before_min_hold": True,
                "horizon_violation_candidate": True,
                "strategy_horizon": "intraday",
            },
            "selection_context": {"selected_rank": 1},
        },
        {
            "realized_outcome": {"net_return_pct": 0.5, "holding_seconds": 600},
            "integrity": {"promotion_metric_eligible": True},
            "horizon_alignment": {
                "exited_before_min_hold": False,
                "horizon_violation_candidate": False,
                "strategy_horizon": "intraday",
            },
            "selection_context": {"selected_rank": 1},
        },
    ]

    result = actual_trade_analysis(rows)

    assert result["early_exit_metrics"]["average_return_pct"] == -1.0
    assert result["min_hold_compliant_metrics"]["average_return_pct"] == 0.5
    assert result["by_hold_bucket"]["under_60s"]["count"] == 1


def test_research_package_has_no_execution_dependencies() -> None:
    package = Path("libs/research/existing_evidence_mining")
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    for prohibited in ("OrderIntent", "submit_order", "graphs.nodes", "libs.execution"):
        assert prohibited not in source


def test_markdown_renders_opportunity_disposition() -> None:
    markdown = render_markdown(
        {
            "blocked_opportunity_analysis": {
                "by_disposition": {
                    "guard_blocked": {
                        "+30m": {
                            "population_count": 2,
                            "observed_count": 1,
                            "coverage": 0.5,
                            "net_metrics": {
                                "average_return_pct": 0.25,
                                "win_rate": 1.0,
                                "profit_factor": 2.0,
                            },
                        }
                    }
                },
                "by_reason": {},
            }
        }
    )

    assert "## Opportunity Disposition" in markdown
    assert "| guard_blocked | 2 | 1 | 50.0% | +0.2500% | 100.0% | 2.0000 |" in markdown
