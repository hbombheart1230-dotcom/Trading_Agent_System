from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.operator_visibility import (
    generate_decision_story_report,
    generate_operator_daily_summary,
    generate_run_card_report,
)
from libs.reporting.trade_explain import generate_trade_explain_report
from scripts.generate_daily_report import generate_daily_report
from scripts.generate_metrics_report import generate_metrics_report


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_commander_artifact(reports_root: Path, day: str, run_id: str, payload: dict) -> None:
    path = reports_root / "canonical" / day / run_id / "commander.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_report_metadata_alignment_smoke(tmp_path: Path) -> None:
    day = "2026-04-08"
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "events.jsonl"
    _write_jsonl(
        events_path,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "005930", "qty": 1, "reason": "entry"}}},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:01+00:00",
                "stage": "commander_router",
                "event": "route_selected",
                "payload": {"route_selected": "full_cycle"},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:02+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "blocked"},
            },
        ],
    )
    _write_commander_artifact(
        reports_root,
        day,
        "r1",
        {
            "route_selected": "monitor_only",
            "strategy_generation_mode": "cached",
            "strategist_call_decision": "skip",
        },
    )

    _, metrics_json = generate_metrics_report(events_path, reports_root / "metrics", day=day)
    _, daily_json = generate_daily_report(events_path, reports_root, day=day)
    operator_md, operator_json = generate_operator_daily_summary(events_path, reports_root / "operator_summary", day=day)
    _decision_md, decision_obj = generate_decision_story_report(events_path, reports_root / "decision_story", day=day, trade_only=False)
    _cards_md, cards_obj = generate_run_card_report(events_path, reports_root / "run_cards", day=day, trade_only=False)
    trade_md, trade_json, trade_obj = generate_trade_explain_report(
        events_path,
        reports_root / "dev" / "analysis" / "trade_explain",
        day=day,
    )

    generated = {
        "metrics": json.loads(metrics_json.read_text(encoding="utf-8")),
        "daily": json.loads(daily_json.read_text(encoding="utf-8")),
        "operator": json.loads(operator_json.read_text(encoding="utf-8")),
        "decision_story": decision_obj,
        "run_cards": cards_obj,
        "trade_explain": trade_obj,
    }

    for name, payload in generated.items():
        assert isinstance(payload.get("data_freshness"), dict), name
        assert isinstance(payload.get("route_provenance"), dict), name
        assert payload["data_freshness"]["freshness_status"] in {"fresh", "empty", "stale"}, name
        assert "source_window_summary" in payload["data_freshness"], name
        assert "route_source" in payload["route_provenance"], name
        assert "route_source_breakdown" in payload["route_provenance"], name

    assert generated["metrics"]["route_provenance"]["route_source"] == "canonical_commander_preferred"
    assert generated["daily"]["route_provenance"]["route_source"] == "canonical_commander_preferred"
    assert generated["operator"]["route_provenance"]["route_source"] == "canonical_commander_preferred"
    assert generated["decision_story"]["route_provenance"]["route_source"] == "canonical_commander_preferred"
    assert generated["run_cards"]["route_provenance"]["route_source"] == "canonical_commander_preferred"
    assert generated["trade_explain"]["route_provenance"]["route_source"] == "canonical_commander_preferred"

    assert operator_md.exists()
    assert trade_md.exists()
    assert trade_json.exists()
