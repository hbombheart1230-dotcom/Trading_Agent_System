from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from libs.reporting.evaluation.q16_proxy_rejection_review import (
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
            ],
        },
    )

    payload = build_q16_proxy_rejection_review(reports_root=reports, day=day)

    assert payload["counts"]["exact_proxy_only_rejection_count"] == 1
    assert payload["counts"]["legacy_cost_rejection_unattributed_count"] == 1
    assert payload["counts"]["exact_observed_30m_count"] == 1
    assert payload["evidence_status"] == "INSUFFICIENT_EVIDENCE"
    assert payload["decision"] == "INSUFFICIENT_EVIDENCE"
    assert "Legacy rows are shown for context only" in render_q16_proxy_rejection_review(payload)
