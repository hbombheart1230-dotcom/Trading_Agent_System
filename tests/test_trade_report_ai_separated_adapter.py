from __future__ import annotations

from unittest.mock import patch

from libs.reporting.trade_report_ai import build_separated_ai_trade_report


def test_build_separated_ai_trade_report_uses_reporter_agent_output() -> None:
    with patch(
        "libs.reporting.trade_read_model.build_trade_read_model",
        return_value={"applied_policy": {"llm": {"reporter": {"intraday": {"primary": "minimax/minimax-m2.5"}}}}},
    ), patch(
        "libs.agent.reporter.run_reporter_agent",
        return_value={
            "status": "ok",
            "metadata": {"trade_id": "TRD_1", "symbol": "005930"},
            "facts": {"trade_id": "TRD_1", "symbol": "005930"},
            "provenance": {"schema_version": "trade_read_model.v2"},
            "context": {"monitor_exit_trigger": "drawdown"},
            "narrative": {"status": "ok", "summary": "ok"},
        },
    ):
        out = build_separated_ai_trade_report("dummy/dir")
    trade = (out.get("fact_payload") or {}).get("trade") or {}
    assert trade.get("trade_id") == "TRD_1"
    assert isinstance(trade.get("facts"), dict)
    assert isinstance(trade.get("provenance"), dict)
    assert isinstance(trade.get("context"), dict)
    assert (out.get("reporter_agent") or {}).get("status") == "ok"
    assert (out.get("narrative") or {}).get("status") == "ok"


def test_build_separated_ai_trade_report_falls_back_to_legacy_when_agent_degraded_contract() -> None:
    sentinel = {"fact_payload": {"trade": {"legacy": True}}, "narrative": {"status": "skipped"}}
    with patch(
        "libs.reporting.trade_read_model.build_trade_read_model",
        return_value={"applied_policy": {"llm": {"reporter": {"intraday": {"primary": "minimax/minimax-m2.5"}}}}},
    ), patch(
        "libs.agent.reporter.run_reporter_agent",
        return_value={
            "status": "degraded",
            "metadata": {},
            "facts": {},
            "provenance": {},
            "context": {},
            "narrative": {"status": "skipped", "reason": "trade_read_model_facts_missing"},
        },
    ), patch(
        "libs.reporting.fact_narrative_report.build_separated_report",
        return_value=sentinel,
    ) as mock_legacy:
        out = build_separated_ai_trade_report("dummy/dir")

    assert out == sentinel
    assert mock_legacy.call_count == 1
    assert mock_legacy.call_args[1]["model"] == "minimax/minimax-m2.5"

