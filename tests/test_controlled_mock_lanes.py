from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from libs.runtime.controlled_mock_lanes.coordinator import (
    finalize_controlled_mock_lane_submission,
    inject_controlled_mock_lane_intent,
)
from libs.runtime.controlled_mock_lanes.ledger import (
    load_attempts,
    load_evaluations,
    load_submissions,
    reconcile_submissions_with_broker_orders,
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
    assert second["controlled_mock_lanes"]["reason"] == "submission_pending_broker_result"


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


def test_broker_rejection_records_attempt_without_consuming_daily_limit(
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
    state = inject_controlled_mock_lane_intent(
        {
            "runtime_phase": "session",
            "now_epoch": _epoch(9, 5),
            "run_id": "rejected-run",
            "portfolio_snapshot": {"positions": []},
            "persisted_state": {},
            "intents": [],
        },
        reports_root=reports,
        ledger_root=ledger,
    )
    state["execution"] = {
        "allowed": True,
        "ok": False,
        "reason": "broker_rejected:20",
        "broker_code": "20",
        "broker_message": "mock restricted",
        "order": {"action": "BUY", "symbol": "041190", "qty": 1},
    }

    result = finalize_controlled_mock_lane_submission(state, ledger_root=ledger)

    assert result["controlled_mock_lanes"]["submission_state"] == "BROKER_REJECTED"
    assert len(load_attempts(DAY, root=ledger)) == 1
    assert load_submissions(DAY, root=ledger) == []


def test_missing_inputs_are_recorded_for_each_independent_lane(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_MODE", "real")
    ledger = tmp_path / "ledger"

    result = inject_controlled_mock_lane_intent(
        {
            "runtime_phase": "session",
            "now_epoch": _epoch(9, 5),
            "run_id": "missing-input-run",
            "portfolio_snapshot": {"positions": []},
            "persisted_state": {},
            "intents": [],
        },
        reports_root=tmp_path / "empty-reports",
        ledger_root=ledger,
    )

    rows = load_evaluations(DAY, root=ledger)
    assert result["controlled_mock_lanes"]["injected"] is False
    assert {row["lane_id"] for row in rows} == {
        "BTC_WOORI",
        "Q10_SEMICONDUCTOR",
        "Q10_INDEX",
    }
    assert {row["status"] for row in rows} == {"INPUT_MISSING"}


def test_controlled_submission_reconciles_to_broker_fill(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger"
    from libs.runtime.controlled_mock_lanes.ledger import record_accepted_submission, record_attempt

    candidate = {"lane_id": "Q10_INDEX", "symbol": "251340", "signal_id": "q10-index"}
    execution = {"order_id": "0013823", "broker_code": "0", "filled_qty": 0, "allowed": True, "ok": True}
    record_attempt(
        day=DAY,
        candidate=candidate,
        run_id="q10-run",
        recorded_at="2026-08-31T09:05:00+09:00",
        execution=execution,
        status="BROKER_ACCEPTED",
        root=ledger,
    )
    record_accepted_submission(
        day=DAY,
        candidate=candidate,
        run_id="q10-run",
        recorded_at="2026-08-31T09:05:00+09:00",
        execution=execution,
        root=ledger,
    )
    result = reconcile_submissions_with_broker_orders(
        day=DAY,
        broker_orders=[{
            "ord_no": "0013823", "symbol": "251340", "ord_qty": 1,
            "cntr_qty": 1, "ord_remnq": 0, "cntr_uv": 2525.0,
            "status": "FILLED",
        }],
        recorded_at="2026-08-31T09:06:00+09:00",
        root=ledger,
    )
    row = load_submissions(DAY, root=ledger)[0]
    assert result["updated"] == 1
    assert row["status"] == "FILLED"
    assert row["filled_qty"] == 1
    assert row["filled_price"] == 2525.0
    attempt = load_attempts(DAY, root=ledger)[0]
    assert result["attempts_updated"] == 1
    assert attempt["status"] == "FILLED"
    assert attempt["execution"]["filled_qty"] == 1
