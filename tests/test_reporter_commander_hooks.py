from __future__ import annotations

from typing import Any, Dict

from graphs.commander_runtime import run_commander_runtime


class _NoopLogger:
    def log(
        self,
        *,
        run_id: str,
        stage: str,
        event: str,
        payload: Dict[str, Any],
        ts: str | None = None,
    ) -> Dict[str, Any]:
        return {
            "run_id": run_id,
            "stage": stage,
            "event": event,
            "payload": payload,
            "ts": ts,
        }


def test_reporter_hooks_are_disabled_by_default(monkeypatch) -> None:
    called = {"intraday": 0}

    def fake_intraday_summary(self, **kwargs: Any) -> Dict[str, Any]:
        called["intraday"] += 1
        return {"status": "generated", "executed": True}

    def integrated_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["path"] = "integrated_chain"
        state["runtime_status"] = "ok"
        state["decision_payload_marker"] = {"decision": "approve", "marker": "keep"}
        return state

    monkeypatch.setattr("libs.agent.reporter.Reporter.maybe_generate_intraday_summary", fake_intraday_summary)

    out = run_commander_runtime(
        {"runtime_mode": "integrated_chain", "event_logger": _NoopLogger()},
        integrated_runner=integrated_runner,
    )

    assert called["intraday"] == 0
    assert "reporter_hook_results" not in out
    assert out["decision_payload_marker"] == {"decision": "approve", "marker": "keep"}


def test_commander_can_invoke_intraday_reporter_hook_without_touching_decision_payload(monkeypatch) -> None:
    calls = {"intraday": 0}

    def fake_intraday_summary(self, **kwargs: Any) -> Dict[str, Any]:
        calls["intraday"] += 1
        return {
            "hook_name": "intraday_summary",
            "enabled": True,
            "status": "generated",
            "executed": True,
            "report_only": True,
            "execution_authority": False,
            "route_override_authority": False,
            "threshold_override_authority": False,
            "report_type": "operator_summary",
            "output_paths": {"json": "reports/daily/2026-04-08/operator_summary.json"},
        }

    def integrated_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["path"] = "integrated_chain"
        state["runtime_status"] = "ok"
        state["decision_payload_marker"] = {"decision": "approve", "marker": "keep"}
        return state

    monkeypatch.setattr("libs.agent.reporter.Reporter.maybe_generate_intraday_summary", fake_intraday_summary)

    out = run_commander_runtime(
        {
            "runtime_mode": "integrated_chain",
            "event_logger": _NoopLogger(),
            "reporter_integration": {
                "enabled": True,
                "hooks": {"intraday_summary": True},
                "emit_reports": False,
                "day": "2026-04-08",
            },
        },
        integrated_runner=integrated_runner,
    )

    assert calls["intraday"] == 1
    assert out["decision_payload_marker"] == {"decision": "approve", "marker": "keep"}
    assert out["reporter_hook_summary"]["report_only"] is True
    assert out["reporter_hook_results"]["intraday_summary"]["status"] == "generated"
    assert out["reporter_hook_results"]["intraday_summary"]["execution_authority"] is False


def test_commander_closeout_hooks_support_eod_and_strategist_feedback_placeholders(monkeypatch) -> None:
    calls = {"eod": 0, "feedback": 0}

    def fake_eod_reports(self, **kwargs: Any) -> Dict[str, Any]:
        calls["eod"] += 1
        return {
            "hook_name": "eod_reports",
            "enabled": True,
            "status": "generated",
            "executed": True,
            "report_only": True,
            "execution_authority": False,
            "route_override_authority": False,
            "threshold_override_authority": False,
            "generated_reports": ["daily_report", "operator_summary"],
        }

    def fake_feedback(self, **kwargs: Any) -> Dict[str, Any]:
        calls["feedback"] += 1
        return {
            "hook_name": "strategist_feedback",
            "enabled": True,
            "status": "reserved",
            "executed": False,
            "report_only": True,
            "execution_authority": False,
            "route_override_authority": False,
            "threshold_override_authority": False,
            "strategist_feedback_packet": {"available": False, "status": "reserved"},
        }

    def closeout_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["path"] = "closeout_idle"
        state["runtime_status"] = "closeout_ready"
        state["decision_payload_marker"] = {"decision": "noop", "marker": "keep"}
        return state

    monkeypatch.setattr("libs.agent.reporter.Reporter.maybe_generate_eod_reports", fake_eod_reports)
    monkeypatch.setattr("libs.agent.reporter.Reporter.maybe_generate_strategist_feedback", fake_feedback)

    out = run_commander_runtime(
        {
            "runtime_phase": "closeout",
            "event_logger": _NoopLogger(),
            "reporter_integration": {
                "enabled": True,
                "emit_reports": False,
                "day": "2026-04-08",
            },
        },
        closeout_runner=closeout_runner,
    )

    assert calls == {"eod": 1, "feedback": 1}
    assert out["decision_payload_marker"] == {"decision": "noop", "marker": "keep"}
    assert out["reporter_hook_results"]["eod_reports"]["status"] == "generated"
    assert out["reporter_hook_results"]["strategist_feedback"]["status"] == "reserved"
    assert out["reporter_hook_results"]["strategist_feedback"]["execution_authority"] is False
