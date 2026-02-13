from __future__ import annotations

from typing import Any, Dict


from graphs.trading_graph import run_trading_graph


def _noop(state: Dict[str, Any]) -> Dict[str, Any]:
    return state


def test_m17_rejects_when_risk_too_high():
    def scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["intents"] = [{"symbol": "005930", "risk_score": 0.95, "confidence": 0.9}]
        return state

    out = run_trading_graph(
        {"policy": {"max_risk": 0.7, "min_confidence": 0.6, "max_scan_retries": 1}},
        strategist=_noop,
        scanner=scanner,
        monitor=_noop,
    )

    assert out["decision"] == "reject"
    assert out.get("decision_reason") == "risk_too_high"
    assert out.get("execution_pending") is not True


def test_m17_retries_scan_on_low_confidence_then_approves():
    def scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        # first attempt: low confidence -> should trigger retry_scan
        # second attempt (retry_count_scan >= 1): good confidence -> approve
        attempt = int(state.get("retry_count_scan") or 0)
        if attempt == 0:
            state["intents"] = [{"symbol": "005930", "risk_score": 0.10, "confidence": 0.20}]
        else:
            state["intents"] = [{"symbol": "005930", "risk_score": 0.10, "confidence": 0.90}]
        return state

    out = run_trading_graph(
        {"policy": {"max_risk": 0.7, "min_confidence": 0.6, "max_scan_retries": 1}},
        strategist=_noop,
        scanner=scanner,
        monitor=_noop,
    )

    assert out["decision"] == "approve"
    assert out.get("retry_count_scan") == 1
    assert out.get("execution_pending") is True
