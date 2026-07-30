from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from libs.reporting.evaluation.q16_proxy_rejection_review import (
    _q16_decision,
    build_q16_proxy_rejection_review,
    render_q16_proxy_rejection_review,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_q16_separates_exact_proxy_rejection_from_legacy_cost_rejection(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    data = tmp_path / "data"
    day = "2026-07-22"
    base = int(datetime(2026, 7, 22, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")).timestamp())
    _write(
        data / "state.json",
        {
            "recent_minute_ohlcv_by_symbol": {
                "005930": [
                    {"ts": base, "close": 100.0, "high": 100.0, "low": 100.0},
                    {"ts": base + 900, "close": 101.0, "high": 101.0, "low": 99.0},
                    {"ts": base + 1800, "close": 102.0, "high": 102.0, "low": 99.0},
                ]
            }
        },
    )
    _write(
        data / "logs" / "quant_shadow_candidates" / day / "sample.json",
        {
            "generated_at": datetime.fromtimestamp(base, tz=ZoneInfo("UTC")).isoformat(),
            "candidates": [
                {
                    "symbol": "005930",
                    "shadow_role": "top_pick",
                    "q9_decision_id": "D1",
                    "triggered": True,
                    "guard_blocked": True,
                    "entry_cost_filter": {
                        "passed": False,
                        "proxy_edge_available": True,
                        "directional_edge_available": False,
                        "allow_triggered_signal_proxy_edge": False,
                    },
                    "shadow_forward_base": {"baseline_epoch": base, "baseline_price": 100.0},
                },
                {
                    "symbol": "005930",
                    "shadow_role": "top_pick",
                    "q9_decision_id": "D2",
                    "triggered": True,
                    "guard_blocked": True,
                    "reason": "quant_entry_block:cost_edge_fail",
                    "entry_quant_cost_floor_state": "not_met",
                    "shadow_forward_base": {"baseline_epoch": base, "baseline_price": 100.0},
                },
                {
                    "symbol": "005930",
                    "shadow_role": "top_pick",
                    "q9_decision_id": "D3",
                    "triggered": True,
                    "guard_blocked": False,
                    "entry_cost_filter": {
                        "passed": True,
                        "proxy_edge_available": False,
                        "directional_edge_available": True,
                        "allow_triggered_signal_proxy_edge": False,
                    },
                    "shadow_forward_base": {"baseline_epoch": base, "baseline_price": 100.0},
                },
            ],
        },
    )

    payload = build_q16_proxy_rejection_review(reports_root=reports, day=day)

    assert payload["counts"]["exact_proxy_only_rejection_count"] == 1
    assert payload["counts"]["legacy_cost_rejection_unattributed_count"] == 1
    assert payload["counts"]["directional_admitted_count"] == 1
    assert payload["counts"]["exact_observed_30m_count"] == 1
    assert payload["evidence_status"] == "INSUFFICIENT_EVIDENCE"
    assert payload["decision"] == "INSUFFICIENT_EVIDENCE"
    rendered = render_q16_proxy_rejection_review(payload)
    assert "Legacy rows are shown for context only" in rendered
    assert "Q16 RETAIN/ROLL_BACK is unavailable" in rendered


def test_q16_rollback_requires_two_individually_positive_days() -> None:
    ready, decision, observed_days, positive_days = _q16_decision(
        20,
        [
            {"observed_30m_count": 10, "positive_30m_day": True},
            {"observed_30m_count": 10, "positive_30m_day": False},
        ],
    )
    assert ready is True
    assert observed_days == 2
    assert positive_days == 1
    assert decision == "RETAIN"

    ready, decision, _observed_days, positive_days = _q16_decision(
        20,
        [
            {"observed_30m_count": 10, "positive_30m_day": True},
            {"observed_30m_count": 10, "positive_30m_day": True},
        ],
    )
    assert ready is True
    assert positive_days == 2
    assert decision == "ROLL_BACK"


def test_q16_ready_markdown_reports_final_decision() -> None:
    rendered = render_q16_proxy_rejection_review(
        {
            "start_day": "2026-07-23",
            "end_day": "2026-07-24",
            "evidence_status": "DECISION_READY",
            "decision": "RETAIN",
            "counts": {},
            "horizons": [],
            "daily_exact_proxy_only": [],
        }
    )

    assert "decision is final under the fixed sample contract: **RETAIN**" in rendered
    assert "RETAIN/ROLL_BACK is unavailable" not in rendered


def test_q17_separates_below_cost_unavailable_and_missing_artifact(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    day = "2026-07-28"
    base = int(
        datetime(2026, 7, 28, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")).timestamp()
    )
    _write(
        tmp_path / "data" / "state.json",
        {
            "recent_minute_ohlcv_by_symbol": {
                "005930": [
                    {"ts": base, "close": 100.0},
                    {"ts": base + 1800, "close": 101.0},
                ]
            }
        },
    )
    common = {
        "symbol": "005930",
        "shadow_role": "top_pick",
        "triggered": True,
        "guard_blocked": True,
        "shadow_forward_base": {
            "baseline_epoch": base,
            "baseline_price": 100.0,
        },
    }
    _write(
        tmp_path
        / "data"
        / "logs"
        / "quant_shadow_candidates"
        / day
        / "sample.json",
        {
            "generated_at": datetime.fromtimestamp(
                base, tz=ZoneInfo("UTC")
            ).isoformat(),
            "candidates": [
                {
                    **common,
                    "q9_decision_id": "D1",
                    "directional_edge_estimate": {"available": True},
                    "entry_cost_filter": {
                        "passed": False,
                        "directional_edge_available": True,
                        "fail_reasons": [
                            "estimated_gross_edge_below_cost_floor"
                        ],
                    },
                },
                {
                    **common,
                    "q9_decision_id": "D2",
                    "directional_edge_estimate": {
                        "available": False,
                        "reason": "evidence_not_eligible",
                    },
                    "entry_cost_filter": {
                        "passed": False,
                        "proxy_edge_available": True,
                        "directional_edge_available": False,
                    },
                },
                {
                    **common,
                    "q9_decision_id": "D3",
                    "entry_cost_filter": {
                        "passed": False,
                        "proxy_edge_available": True,
                        "directional_edge_available": False,
                    },
                },
            ],
        },
    )

    payload = build_q16_proxy_rejection_review(reports_root=reports, day=day)
    q17 = payload["q17_directional_edge_validation"]

    assert q17["class_counts"]["DIRECTIONAL_BELOW_COST_REJECTION"] == 1
    assert q17["class_counts"]["DIRECTIONAL_EVIDENCE_UNAVAILABLE"] == 1
    assert q17["class_counts"]["DIRECTIONAL_ESTIMATE_ARTIFACT_MISSING"] == 1
    assert q17["unavailable_reasons"]["evidence_not_eligible"] == 1
    assert q17["unavailable_reasons"]["artifact_missing"] == 1
