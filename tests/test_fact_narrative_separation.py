import json
import pytest
from libs.reporting.fact_narrative_report import build_fact_payload, generate_narrative, build_separated_report

def test_fact_payload_generation_is_deterministic():
    trade_model = {"trade_id": "T1", "pnl": 100}
    daily_model = {"run_count": 5}
    symbol_model = {"symbol": "AAPL", "win_rate": 0.8}

    payload = build_fact_payload(trade_model, daily_model, symbol_model)
    assert payload["trade"]["trade_id"] == "T1"
    assert payload["daily"]["run_count"] == 5
    assert payload["symbol"]["win_rate"] == 0.8

def test_llm_less_report_generation(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    report = build_separated_report(trade_model={"trade_id": "T1"})

    assert "fact_payload" in report
    assert "narrative" in report
    assert report["narrative"]["status"] == "skipped"
    assert report["narrative"]["reason"] == "explicit_model_not_provided"
    assert report["narrative"]["llm_call_skipped"] is True
    assert report["narrative"]["source"] == "llm"
    assert report["narrative"]["based_on"] == "fact_payload"

def test_system_works_without_narrative_on_llm_failure(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")

    class BoomRouter:
        client = object()
        def chat(self, *args, **kwargs):
            raise RuntimeError("LLM Boom")
        @classmethod
        def from_env(cls):
            return cls()

    monkeypatch.setattr("libs.reporting.fact_narrative_report.LLMRouter", BoomRouter)

    report = build_separated_report(trade_model={"trade_id": "T1"}, model="primary/model")
    assert report["fact_payload"]["trade"]["trade_id"] == "T1"
    assert report["narrative"]["status"] == "error"
    assert "LLM Boom" in report["narrative"]["error"]
    assert report["narrative"]["source"] == "llm"

def test_narrative_provenance_and_no_fact_mixing(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")

    class MockRouter:
        client = object()
        def chat(self, *args, **kwargs):
            return json.dumps({
                "summary": "Mock summary",
                "insight": "Mock insight",
                "recommendation": "Mock recommendation"
            })
        @classmethod
        def from_env(cls):
            return cls()

    monkeypatch.setattr("libs.reporting.fact_narrative_report.LLMRouter", MockRouter)

    report = build_separated_report(trade_model={"trade_id": "T1"}, model="primary/model")
    assert report["narrative"]["summary"] == "Mock summary"
    assert report["narrative"]["source"] == "llm"
    assert report["narrative"]["based_on"] == "fact_payload"
    assert report["narrative"]["status"] == "ok"

def test_narrative_uses_fallback_on_primary_failure(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")

    class FallbackRouter:
        client = object()
        def chat(self, route, messages, policy=None):
            if policy and policy.get("model") == "primary/model":
                raise RuntimeError("Primary Boom")
            return json.dumps({"summary": "Fallback summary", "insight": "Fallback insight", "recommendation": "Fallback rec"})
        @classmethod
        def from_env(cls):
            return cls()

    monkeypatch.setattr("libs.reporting.fact_narrative_report.LLMRouter", FallbackRouter)

    report = build_separated_report(trade_model={"trade_id": "T1"}, model="primary/model")
    assert report["narrative"]["status"] == "ok"
    assert report["narrative"]["summary"] == "Fallback summary"
    assert report["narrative"].get("fallback_used") is True
    assert report["narrative"].get("fallback_model") == "minimax/minimax-m2.5"


def test_narrative_records_execution_profile_observability(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")

    captured = {}

    class CaptureRouter:
        client = object()

        def chat(self, route, messages, policy=None):
            captured["policy"] = dict(policy or {})
            return json.dumps({"summary": "ok", "insight": "i", "recommendation": "r"})

        @classmethod
        def from_env(cls):
            return cls()

    monkeypatch.setattr("libs.reporting.fact_narrative_report.LLMRouter", CaptureRouter)

    report = build_separated_report(
        trade_model={"trade_id": "T1"},
        model="minimax/minimax-m2.5",
        execution_profile={
            "profile_name": "default_intraday",
            "policy_source": "applied_policy.llm.execution_profile",
            "temperature": 0.27,
            "max_tokens": 1500,
            "timeout_sec": 9,
            "retry": {"max_attempts": 3, "backoff_sec": 0.0},
        },
    )

    assert float(captured["policy"]["temperature"]) == 0.27
    assert int(captured["policy"]["max_tokens"]) == 1500
    assert float(captured["policy"]["timeout_sec"]) == 9.0
    assert report["narrative"]["llm_execution_profile_name"] == "default_intraday"
    assert report["narrative"]["llm_execution_profile_source"] == "applied_policy"


def test_narrative_skips_network_when_model_not_provided(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")

    class ExplodingRouter:
        client = object()

        def chat(self, *args, **kwargs):
            raise AssertionError("chat should not be called without explicit model")

        @classmethod
        def from_env(cls):
            return cls()

    monkeypatch.setattr("libs.reporting.fact_narrative_report.LLMRouter", ExplodingRouter)

    report = build_separated_report(trade_model={"trade_id": "T1"})
    assert report["narrative"]["status"] == "skipped"
    assert report["narrative"]["reason"] == "explicit_model_not_provided"
    assert report["narrative"]["llm_call_skipped"] is True
