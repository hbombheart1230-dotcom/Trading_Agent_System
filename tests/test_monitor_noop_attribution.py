from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.cost_basis_comparison import build_evaluation_cost_bases
from libs.reporting.evaluation.monitor_noop_attribution.episodes import (
    collapse_cycles_to_episodes,
    load_approved_noop_cycles,
)
from libs.reporting.evaluation.monitor_noop_attribution.report import (
    build_report_payload,
)
from libs.reporting.evaluation.monitor_noop_attribution.pipeline import (
    _read_candle_cache,
    _write_candle_cache,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_approved_noop_cycles_are_filtered_and_collapsed(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    logs = tmp_path / "data" / "logs" / "quant_shadow_candidates"
    day = "2026-08-03"
    windows = []
    for index, epoch in enumerate((1785715200, 1785715230, 1785715900)):
        windows.append({
            "decision_id": f"Q9_{index}",
            "decision_epoch": epoch,
            "generated_at": f"2026-08-03T00:{index:02d}:00+00:00",
            "scanner_control": {"top1_symbol": "005930"},
            "commander_final": {
                "decision": "approve",
                "selected_symbol": "005930",
                "monitor_intent": "NOOP",
                "monitor_reason": "volume_confirmation_missing",
                "monitor_observation": {"entry_primary_failure_axis": "volume_confirmation"},
            },
        })
        _write(logs / day / f"{index}.json", {
            "q9_decision_id": f"Q9_{index}",
            "q9_decision_candidates": [{
                "q9_decision_id": f"Q9_{index}",
                "symbol": "005930",
                "shadow_forward_base": {
                    "available": True,
                    "baseline_epoch": epoch,
                    "baseline_price": 70000,
                },
            }],
        })
    windows.append({
        "decision_id": "Q9_REJECT",
        "decision_epoch": 1785715260,
        "generated_at": "2026-08-03T00:03:00+00:00",
        "commander_final": {
            "decision": "reject", "selected_symbol": "005930",
            "monitor_intent": "NOOP", "monitor_reason": "volume_confirmation_missing",
        },
    })
    _write(reports / "operator_summary" / "daily" / day / "q9_decision_windows.json", {"windows": windows})

    cycles = load_approved_noop_cycles(reports_root=reports, log_root=logs, day=day)
    episodes = collapse_cycles_to_episodes(cycles)

    assert len(cycles) == 3
    assert len(episodes) == 2
    assert episodes[0]["cycle_count"] == 2
    assert episodes[0]["blocker_family"] == "VOLUME_CONFIRMATION"
    assert episodes[0]["shadow_forward_base"]["baseline_price"] == 70000


def test_report_applies_live_and_mock_costs_without_low_evidence_penalty() -> None:
    episodes = [{
        "blocker_family": "COST_EDGE",
        "shadow_forward_outcome": {
            "available": True,
            "checkpoints": {
                "+5m": {"status": "observed", "return_pct": 1.0, "mfe_pct": 1.2, "mae_pct": -0.2},
            },
        },
    }]
    bases = build_evaluation_cost_bases({"conservative_round_trip_cost_pct": 0.01}, slippage_pct=0.05)
    payload = build_report_payload(
        start="2026-08-03", end="2026-08-07", cycles=[{}], episodes=episodes,
        cost_bases=bases, candle_meta={},
    )
    row = next(item for item in payload["metrics"] if item["horizon"] == "+5m")
    assert row["gross"]["average_return_pct"] == 1.0
    assert row["live_net"]["average_return_pct"] == 0.72
    assert row["mock_net"]["average_return_pct"] == -0.05
    assert payload["evidence_status"] == "READY"
    assert payload["decision"]["decision"] == "RETAIN_CURRENT_MONITOR_GATES"


def test_report_marks_missing_forward_evidence() -> None:
    payload = build_report_payload(
        start="2026-08-03", end="2026-08-07", cycles=[{}],
        episodes=[{"blocker_family": "OTHER"}],
        cost_bases=build_evaluation_cost_bases({}), candle_meta={},
    )
    assert payload["evidence_status"] == "INSUFFICIENT_EVIDENCE"


def test_evidence_candle_cache_round_trip_is_deterministic(tmp_path: Path) -> None:
    rows = {"005930": [{"ts": 1, "close": 70000.0}]}
    _write_candle_cache(tmp_path, "2026-08-03", rows)
    assert _read_candle_cache(tmp_path, "2026-08-03", ("005930", "000660")) == {
        "005930": rows["005930"],
        "000660": [],
    }
