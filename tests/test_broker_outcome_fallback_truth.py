"""2026-09-05 PRE-STEP5C CLEANUP FIX 2, item 4 -- BrokerOutcome fallback
truth (Codex independent re-audit).

Root cause: libs/runtime/controlled_mock_lanes/coordinator.py::
_resolve_broker_outcome()'s fallback (used only when execution["broker_
outcome"] is absent -- e.g. hand-built test doubles/legacy call sites; the
Step5B-authoritative path via execute_from_packet.py's own
_normalize_execution is untouched and always wins) misclassified:
  - broker_code=="0" as REJECTED, even though "0" is Kiwoom's own
    no-business-error convention (see KiwoomMarketIndexReader._request).
  - a timeout/ambiguous broker_message as a confident REJECTED.
  - allowed=False as unconditional NOT_SENT, even when dispatch evidence
    (broker_code/broker_message/order_id/submission_attempts) proved
    otherwise.

Fixed by resolving strictly from dispatch evidence (Step5B fields
submission_attempts/submission_phase, plus response evidence broker_code/
broker_message/order_id), never guessing REJECTED without a positive
signal and never guessing NOT_SENT without proof of non-dispatch. The
Step5B classifier itself (execute_from_packet.py) is unmodified.
"""
from __future__ import annotations

from libs.runtime.controlled_mock_lanes.coordinator import _resolve_broker_outcome


# --- T1: broker_code "0" must never be read as REJECTED ------------------


def test_t1_broker_code_zero_is_never_rejected():
    outcome = _resolve_broker_outcome({"allowed": True, "ok": False, "broker_code": "0"})

    assert outcome != "REJECTED"
    assert outcome == "UNKNOWN"


# --- T2: timeout message must never be read as a confident REJECTED ------


def test_t2_timeout_message_is_unknown_not_rejected():
    outcome = _resolve_broker_outcome({
        "allowed": True, "ok": False, "reason": "broker_timeout", "broker_message": "request timeout",
    })

    assert outcome != "REJECTED"
    assert outcome == "UNKNOWN"


# --- T3: allowed=False but real dispatch evidence present -----------------


def test_t3_allowed_false_with_dispatch_evidence_is_not_forced_to_not_sent():
    outcome = _resolve_broker_outcome({
        "allowed": False, "ok": False, "broker_code": "20", "broker_message": "mock restricted",
    })

    assert outcome != "NOT_SENT"
    assert outcome == "REJECTED"


def test_t3b_allowed_false_with_submission_attempts_evidence_is_not_forced_to_not_sent():
    outcome = _resolve_broker_outcome({
        "allowed": False, "ok": True, "execution_ok": True, "submission_attempts": 1,
    })

    assert outcome == "UNKNOWN"  # Attempt count and booleans do not prove broker acceptance.


# --- T4: no dispatch evidence at all -> UNKNOWN, never guessed -----------


def test_t4_no_dispatch_evidence_is_unknown():
    outcome = _resolve_broker_outcome({"allowed": True, "ok": False})

    assert outcome == "UNKNOWN"


def test_t4b_guard_blocked_phase_with_no_other_evidence_is_not_sent():
    """submission_phase=="guard_blocked" (execute_from_packet.py's own
    Step5B field) IS positive proof of non-dispatch."""
    outcome = _resolve_broker_outcome({"allowed": False, "ok": False, "submission_phase": "guard_blocked"})

    assert outcome == "NOT_SENT"


# --- T5: explicit REJECTED is authoritative, unaffected by the fallback --


def test_t5_explicit_broker_outcome_rejected_is_authoritative():
    outcome = _resolve_broker_outcome({
        "broker_outcome": "REJECTED", "allowed": True, "ok": False, "broker_code": "0",
    })

    assert outcome == "REJECTED"


# --- T6: explicit UNKNOWN is authoritative, unaffected by the fallback ---


def test_t6_explicit_broker_outcome_unknown_is_authoritative():
    outcome = _resolve_broker_outcome({
        "broker_outcome": "UNKNOWN", "allowed": True, "ok": True, "execution_ok": True,
    })

    assert outcome == "UNKNOWN"


# --- T7: statistics truth -- REJECTED is reserved for genuine evidence ---


def test_t7_genuine_broker_rejection_still_classified_rejected():
    """A real, non-"0", non-ambiguous broker rejection code must still be
    classified REJECTED -- the fix removes false positives, not true ones."""
    outcome = _resolve_broker_outcome({
        "allowed": True, "ok": False, "broker_code": "20", "broker_message": "mock restricted",
    })

    assert outcome == "REJECTED"


def test_t7b_accepted_execution_still_classified_accepted():
    outcome = _resolve_broker_outcome({
        "allowed": True, "ok": True, "execution_ok": True, "order_id": "0099001",
    })

    assert outcome == "ACCEPTED"


# ===========================================================================
# 2026-09-05 PRE-STEP5C CLEANUP FIX 3 (item 7, second independent Codex
# re-audit -- FIX 2's fallback was still too willing to infer).
# ===========================================================================


def test_fix3_t1_empty_dict_is_unknown_not_not_sent():
    """Codex's exact reproduction: `{}` must never resolve to NOT_SENT --
    an empty dict proves nothing (an absent "allowed" key is not the same
    as an explicit allowed=False)."""
    outcome = _resolve_broker_outcome({})

    assert outcome != "NOT_SENT"
    assert outcome == "UNKNOWN"


def test_fix3_t2_pre_submit_and_rejected_text_alone_is_unknown_not_rejected():
    """Codex's exact reproduction: a "pre_submit"/"rejected" TEXTUAL
    description (no genuine broker_code) must never resolve to REJECTED."""
    outcome = _resolve_broker_outcome({
        "allowed": True, "reason": "pre_submit_check", "broker_message": "pre_submit validation rejected",
    })

    assert outcome != "REJECTED"
    assert outcome == "UNKNOWN"


def test_fix3_t3_broker_code_zero_with_success_text_is_unknown_not_rejected():
    """Codex's exact reproduction: broker_code="0" plus a "success"-ish
    reason must never resolve to REJECTED (still Kiwoom's own
    no-business-error convention)."""
    outcome = _resolve_broker_outcome({"allowed": True, "broker_code": "0", "reason": "success"})

    assert outcome != "REJECTED"
    assert outcome == "UNKNOWN"


def test_fix3_t4_dispatched_plus_timeout_is_unknown():
    outcome = _resolve_broker_outcome({"allowed": True, "broker_code": "5", "reason": "gateway_timeout"})

    assert outcome == "UNKNOWN"


def test_fix3_t5_explicit_rejected_authoritative():
    outcome = _resolve_broker_outcome({"broker_outcome": "REJECTED", "allowed": True, "broker_code": "0"})

    assert outcome == "REJECTED"


def test_fix3_t6_explicit_not_sent_authoritative():
    outcome = _resolve_broker_outcome({"broker_outcome": "NOT_SENT", "allowed": True, "ok": True})

    assert outcome == "NOT_SENT"


def test_fix3_t7_explicit_unknown_authoritative():
    outcome = _resolve_broker_outcome({"broker_outcome": "UNKNOWN", "allowed": True, "ok": True})

    assert outcome == "UNKNOWN"


def test_fix3_t8_finalizer_statistics_are_truthful(tmp_path, monkeypatch) -> None:
    """The controlled-lane finalizer's own attempt/status bookkeeping must
    reflect this tightened classification -- an empty-evidence execution
    must never be recorded as PRE_SUBMISSION_BLOCKED (the NOT_SENT label)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from libs.runtime.controlled_mock_lanes.coordinator import (
        finalize_controlled_mock_lane_submission,
        inject_controlled_mock_lane_intent,
    )
    from libs.runtime.controlled_mock_lanes.ledger import load_attempts

    KST = ZoneInfo("Asia/Seoul")
    day = "2026-09-05"
    reports = tmp_path / "reports"
    ledger = tmp_path / "ledger"
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_MODE", "real")
    (reports / "evaluation" / "baseline_btc_woori_tech" / day).mkdir(parents=True, exist_ok=True)
    import json as _json

    (reports / "evaluation" / "baseline_btc_woori_tech" / day / "q12_btc_woori_hypothesis_validation.json").write_text(
        _json.dumps({
            "contract_id": "q12_btc_woori_five_variable_validation.v1",
            "day": day,
            "features": {
                "btc_0855": {"status": "OBSERVED", "return_24h_pct": 5.2},
                "btc_daily_context": {"status": "OBSERVED", "surge_state": "FIRST_SURGE", "breakout_state": "60D_BREAKOUT"},
                "woori_opening": {"opening_gap_pct": 6.0},
                "entry_methods": {
                    "09:03": {"status": "OBSERVED", "entry_epoch": int(datetime(2026, 9, 5, 9, 3, tzinfo=KST).timestamp()), "entry_price": 6200.0, "local_confirmation": True, "volume_ratio": 1.4},
                    "09:05": {"status": "PENDING"},
                },
            },
        }),
        encoding="utf-8",
    )
    state = inject_controlled_mock_lane_intent(
        {
            "runtime_phase": "session",
            "now_epoch": int(datetime(2026, 9, 5, 9, 5, tzinfo=KST).timestamp()),
            "run_id": "fix3-empty-evidence-run",
            "portfolio_snapshot": {"positions": []},
            "persisted_state": {},
            "intents": [],
        },
        reports_root=reports,
        ledger_root=ledger,
    )
    # A non-empty but evidence-free execution result (an empty {} is
    # already handled earlier in the finalizer as EXECUTION_RESULT_MISSING
    # -- this specifically exercises _resolve_broker_outcome's own
    # fallback with insufficient evidence).
    state["execution"] = {"mode": "mock"}

    result = finalize_controlled_mock_lane_submission(state, ledger_root=ledger)

    assert result["controlled_mock_lanes"]["submission_state"] == "BROKER_OUTCOME_UNKNOWN"
    assert result["controlled_mock_lanes"]["submission_state"] != "PRE_SUBMISSION_BLOCKED"
    attempt = load_attempts(day, root=ledger)[0]
    assert attempt["status"] == "BROKER_OUTCOME_UNKNOWN"
    assert attempt["execution"]["broker_outcome"] == "UNKNOWN"
