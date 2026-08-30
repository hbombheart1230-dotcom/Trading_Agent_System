from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from libs.runtime.controlled_mock_lanes.coordinator import (
    inject_controlled_mock_lane_intent,
)
from libs.runtime.controlled_mock_lanes.signals import (
    build_q10_index_candidate,
    build_q10_semiconductor_candidate,
    build_q12_candidate,
)


KST = ZoneInfo("Asia/Seoul")
DAY = "2026-08-31"


def _epoch(hour: int, minute: int) -> int:
    return int(datetime(2026, 8, 31, hour, minute, tzinfo=KST).timestamp())


def _q12_payload() -> dict:
    return {
        "contract_id": "q12_btc_woori_five_variable_validation.v1",
        "day": DAY,
        "features": {
            "btc_0855": {"status": "OBSERVED", "return_24h_pct": 5.2},
            "btc_daily_context": {
                "status": "OBSERVED",
                "surge_state": "FIRST_SURGE",
                "breakout_state": "60D_BREAKOUT",
            },
            "woori_opening": {"opening_gap_pct": 6.0},
            "entry_methods": {
                "09:03": {
                    "status": "OBSERVED",
                    "entry_epoch": _epoch(9, 3),
                    "entry_price": 6200.0,
                    "local_confirmation": True,
                    "volume_ratio": 1.4,
                },
                "09:05": {"status": "PENDING"},
            },
        },
    }


def _q10_payloads() -> tuple[dict, dict, dict]:
    preopen = {
        "capture_status": "CAPTURED",
        "day": DAY,
        "signals": {
            "sk_hynix": {
                "state": "STRONG_POSITIVE",
                "score": 2.0,
                "confidence": "HIGH",
                "confidence_score": 0.9,
            },
            "samsung": {
                "state": "POSITIVE",
                "score": 0.65,
                "confidence": "MEDIUM",
                "confidence_score": 0.5,
            },
            "hynix_extension": {"state": "FIRST_MOVE"},
            "korea_market": {
                "state": "RISK_ON",
                "score": 3.0,
                "evidence_status": "COMPLETE",
            },
        },
    }
    reactions = {
        "targets": {
            "sk_hynix": {
                "points": {
                    "09:00": {"status": "OBSERVED", "ts": _epoch(9, 0), "price": 100.0},
                    "09:03": {"status": "OBSERVED", "ts": _epoch(9, 3), "price": 101.5},
                }
            },
            "samsung": {
                "points": {
                    "09:00": {"status": "OBSERVED", "ts": _epoch(9, 0), "price": 100.0},
                    "09:03": {"status": "OBSERVED", "ts": _epoch(9, 3), "price": 100.2},
                }
            },
            "kospi": {
                "points": {
                    "09:00": {"status": "OBSERVED", "ts": _epoch(9, 0), "price": 100.0},
                    "09:03": {"status": "OBSERVED", "ts": _epoch(9, 3), "price": 100.4},
                }
            },
            "kosdaq": {
                "points": {
                    "09:00": {"status": "OBSERVED", "ts": _epoch(9, 0), "price": 100.0},
                    "09:03": {"status": "OBSERVED", "ts": _epoch(9, 3), "price": 100.8},
                }
            },
        }
    }
    expected = {
        "rows": [
            {"target": "sk_hynix", "reaction_state": "UNDERREACTION"},
            {"target": "samsung", "reaction_state": "FAIR_REACTION"},
            {"target": "kospi", "reaction_state": "FAIR_REACTION"},
            {"target": "kosdaq", "reaction_state": "UNDERREACTION"},
        ]
    }
    return preopen, reactions, expected


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_q12_requires_all_five_fixed_conditions() -> None:
    candidate = build_q12_candidate(_q12_payload(), now_epoch=_epoch(9, 5))
    failed = _q12_payload()
    failed["features"]["btc_daily_context"]["surge_state"] = "REPEATED_SURGE"

    assert candidate is not None
    assert candidate["lane_id"] == "BTC_WOORI"
    assert candidate["symbol"] == "041190"
    assert build_q12_candidate(failed, now_epoch=_epoch(9, 5)) is None


def test_q10_selects_strongest_confirmed_semiconductor_and_index() -> None:
    preopen, reactions, expected = _q10_payloads()
    semiconductor = build_q10_semiconductor_candidate(
        preopen=preopen,
        reactions=reactions,
        expected_actual=expected,
        now_epoch=_epoch(9, 5),
    )
    index = build_q10_index_candidate(
        preopen=preopen,
        reactions=reactions,
        expected_actual=expected,
        now_epoch=_epoch(9, 5),
    )

    assert semiconductor is not None
    assert semiconductor["symbol"] == "000660"
    assert index is not None
    assert index["symbol"] == "229200"
    assert index["evidence"]["target"] == "kosdaq"


def test_coordinator_injects_one_real_mock_intent_per_lane(
    tmp_path: Path, monkeypatch
) -> None:
    reports = tmp_path / "reports"
    ledger = tmp_path / "ledger"
    _write(
        reports
        / "evaluation"
        / "baseline_btc_woori_tech"
        / DAY
        / "q12_btc_woori_hypothesis_validation.json",
        _q12_payload(),
    )
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_MODE", "real")
    state = {
        "runtime_phase": "session",
        "now_epoch": _epoch(9, 5),
        "run_id": "test-run",
        "portfolio_snapshot": {"positions": [], "open_positions": 0},
        "persisted_state": {},
        "intents": [],
    }

    first = inject_controlled_mock_lane_intent(
        state, reports_root=reports, ledger_root=ledger
    )
    second = inject_controlled_mock_lane_intent(
        {**state, "intents": []}, reports_root=reports, ledger_root=ledger
    )

    assert first["controlled_mock_lanes"]["injected"] is True
    assert first["intents"][0]["symbol"] == "041190"
    assert first["intents"][0]["qty"] == 1
    assert first["intents"][0]["meta"]["position_strategy_snapshot"]["llm_used"] is False
    assert second["controlled_mock_lanes"]["injected"] is False
    assert second["controlled_mock_lanes"]["reason"] == "no_eligible_independent_lane"


def test_existing_monitor_intent_has_priority(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_MODE", "real")
    existing = {"symbol": "005930", "side": "BUY", "qty": 1}
    state = {
        "runtime_phase": "session",
        "now_epoch": _epoch(9, 5),
        "intents": [existing],
    }

    result = inject_controlled_mock_lane_intent(
        state, reports_root=tmp_path, ledger_root=tmp_path / "ledger"
    )

    assert result["intents"] == [existing]
    assert result["controlled_mock_lanes"]["reason"] == "existing_monitor_intent_has_priority"
