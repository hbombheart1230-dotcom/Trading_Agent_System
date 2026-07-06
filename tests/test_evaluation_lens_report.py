from __future__ import annotations

from pathlib import Path

from libs.reporting.evaluation import evaluation_lens_report as mod


def _forward(return_pct: float, mfe_pct: float | None = None, mae_pct: float | None = None) -> dict:
    return {
        "shadow_forward_outcome": {
            "available": True,
            "checkpoints": {
                "+5m": {
                    "status": "observed",
                    "return_pct": return_pct,
                    "mfe_pct": mfe_pct if mfe_pct is not None else return_pct,
                    "mae_pct": mae_pct if mae_pct is not None else return_pct,
                },
                "+15m": {
                    "status": "observed",
                    "return_pct": return_pct + 0.1,
                    "mfe_pct": mfe_pct if mfe_pct is not None else return_pct + 0.1,
                    "mae_pct": mae_pct if mae_pct is not None else return_pct,
                },
                "+30m": {
                    "status": "observed",
                    "return_pct": return_pct + 0.2,
                    "mfe_pct": mfe_pct if mfe_pct is not None else return_pct + 0.2,
                    "mae_pct": mae_pct if mae_pct is not None else return_pct,
                },
                "EOD": {
                    "status": "observed",
                    "return_pct": return_pct + 0.3,
                    "mfe_pct": mfe_pct if mfe_pct is not None else return_pct + 0.3,
                    "mae_pct": mae_pct if mae_pct is not None else return_pct,
                },
            },
        }
    }


def test_evaluation_lens_report_is_observability_only(monkeypatch, tmp_path: Path) -> None:
    payloads = [
        {
            "generated_at": "2026-06-30T00:01:00+00:00",
            "candidates": [
                {
                    "symbol": "005930",
                    "reason": "below_vwap_reclaim_not_ready",
                    "entry_lane_observation": {"market_regime_rail": "risk_on_rebound"},
                    **_forward(0.4, mfe_pct=0.7, mae_pct=-0.1),
                },
                {
                    "symbol": "000660",
                    "reason": "volume_confirmation_missing",
                    "entry_lane_observation": {"market_regime_rail": "risk_on_rebound"},
                    **_forward(-0.2, mfe_pct=0.1, mae_pct=-0.4),
                },
            ],
            "q9_decision_candidates": [
                {
                    "q9_decision_id": "D1",
                    "q9_decision_role": "A_SCANNER_CONTROL",
                    "rank": 1,
                    **_forward(0.1),
                },
                {
                    "q9_decision_id": "D1",
                    "q9_decision_role": "B_STRATEGIST_RANKED",
                    "q9_selected": True,
                    "rank": 1,
                    **_forward(0.3),
                },
                {
                    "q9_decision_id": "D1",
                    "q9_decision_role": "C_COMMANDER_FINAL",
                    "rank": 1,
                    **_forward(0.2),
                },
            ],
        }
    ]
    monkeypatch.setattr(mod, "load_quant_shadow_candidate_payloads_for_range", lambda **_: payloads)
    monkeypatch.setattr(mod, "attach_forward_outcomes", lambda rows: list(rows))
    monkeypatch.setattr(mod, "_cost_floor_pct", lambda: 0.35)
    monkeypatch.setattr(
        mod,
        "_trade_models",
        lambda *_args, **_kwargs: [
            {
                "trade_id": "TRD1",
                "symbol": "005930",
                "exit": {"reason": "intraday_low_break"},
                "outcome": {"net_return_pct": -0.3},
                "monitor": {
                    "post_exit": {
                        "checkpoints": {
                            "+5m": {"return_pct": 0.2},
                            "+15m": {"return_pct": 0.4},
                            "+30m": {"return_pct": 0.5},
                            "EOD": {"return_pct": 0.1},
                        }
                    }
                },
            }
        ],
    )

    result = mod.build_evaluation_lens_report(
        reports_root=tmp_path / "reports",
        start="2026-06-30",
        end="2026-06-30",
    )

    assert result["behavior_effect"] == "evaluation_only"
    assert result["behavior_change_authorized"] is False
    assert result["evidence"]["candidate_count"] == 2
    blocker_rows = result["blocker_forward_review"]["by_blocker"]
    assert [row["name"] for row in blocker_rows] == [
        "below_vwap_reclaim_not_ready",
        "volume_confirmation_missing",
    ]
    assert blocker_rows[0]["+30m"]["cost_floor_reachable_rate"] == 1.0
    delta = result["strategist_delta_review"]["deltas_by_horizon"][0]
    assert delta["strategist_minus_scanner_control"]["average_return_pct"] == 0.2
    assert delta["commander_minus_strategist"]["average_return_pct"] == -0.1
    exit_rows = result["exit_hold_counterfactual_review"]["by_exit_reason"]
    assert exit_rows[0]["exit_reason"] == "intraday_low_break"
    assert exit_rows[0]["+5m"]["average_return_pct"] == 0.5


def test_write_evaluation_lens_report_writes_json_and_markdown(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        mod,
        "build_evaluation_lens_report",
        lambda **_: {
            "schema_version": "evaluation_lens_report.v1",
            "behavior_effect": "evaluation_only",
            "range": {"start": "2026-06-30", "end": "2026-06-30"},
            "evidence": {
                "shadow_payload_count": 0,
                "candidate_count": 0,
                "q9_candidate_count": 0,
                "trade_model_count": 0,
            },
            "blocker_forward_review": {"by_blocker": []},
            "strategist_delta_review": {
                "best_role_by_horizon": [],
                "deltas_by_horizon": [],
            },
            "exit_hold_counterfactual_review": {"by_exit_reason": []},
        },
    )

    paths = mod.write_evaluation_lens_report(
        reports_root=tmp_path / "reports",
        start="2026-06-30",
        end="2026-06-30",
    )

    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()
    assert "evaluation_only" in Path(paths["markdown"]).read_text(encoding="utf-8")
