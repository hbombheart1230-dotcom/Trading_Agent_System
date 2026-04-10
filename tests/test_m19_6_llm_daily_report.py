from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pytest

from graphs.pipelines.m13_eod_report import run_m13_eod_report
from libs.reporting.llm_daily_summary import summarize_daily_report_with_artifact


def test_m19_6_llm_daily_report_appends_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    # Arrange
    monkeypatch.setenv("DRY_RUN", "1")

    events_path = tmp_path / "events.jsonl"
    events_path.write_text("", encoding="utf-8")
    report_dir = tmp_path / "reports"

    monkeypatch.setenv("EVENT_LOG_PATH", str(events_path))
    monkeypatch.setenv("REPORT_DIR", str(report_dir))

    state: Dict[str, Any] = {
        "policy": {"use_llm_daily_report": True},
        "mock_llm_daily_summary": "- 오늘은 테스트만 수행\n- 체결 없음\n\nTakeaway: 안정적",
    }

    # after close (KST) to trigger report generation
    dt = datetime(2026, 2, 13, 16, 10, 0)

    # Act
    out = run_m13_eod_report(state, dt=dt)

    # Assert
    rep = out.get("daily_report") or {}
    assert rep.get("llm_summary")
    md_path = Path(str(rep["md"]))
    text = md_path.read_text(encoding="utf-8")
    assert "## LLM Summary" in text
    assert "Takeaway" in text
    llm_path = Path(str(rep.get("daily_report_llm_response_json") or ""))
    assert llm_path.exists() is True
    llm_artifact = json.loads(llm_path.read_text(encoding="utf-8"))
    assert llm_artifact["component"] == "daily_report"
    assert llm_artifact["status"] == "fallback"


class _EmptyDailyRouter:
    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_EmptyDailyRouter":
        return _EmptyDailyRouter()

    def chat(self, role: str, messages: list[dict], *, policy: dict | None = None) -> str:
        return ""


class _CaptureDailyRouter:
    last_policy: dict | None = None

    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_CaptureDailyRouter":
        return _CaptureDailyRouter()

    def chat(self, role: str, messages: list[dict], *, policy: dict | None = None) -> str:
        _CaptureDailyRouter.last_policy = dict(policy or {})
        return "- 요약\nTakeaway: ok"


def test_m19_6_daily_summary_retries_and_records_failure_artifact(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
    monkeypatch.setenv("DAILY_REPORT_LLM_RETRY_MAX", "2")
    monkeypatch.setattr("libs.reporting.llm_daily_summary.LLMRouter", _EmptyDailyRouter)

    summary, artifact = summarize_daily_report_with_artifact(
        state={"eod_day": "2026-03-18", "daily_report": {"approvals": 1, "denials": 0, "runs": 3}},
        policy={},
    )

    assert summary == ""
    assert artifact["status"] == "empty_response"
    assert artifact["retry_count"] == 2
    assert len(artifact["attempts"]) == 3


def test_m19_6_daily_summary_uses_policy_execution_profile(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
    monkeypatch.setattr("libs.reporting.llm_daily_summary.LLMRouter", _CaptureDailyRouter)

    summary, artifact = summarize_daily_report_with_artifact(
        state={
            "eod_day": "2026-03-18",
            "daily_report": {"approvals": 1, "denials": 0, "runs": 3},
            "applied_policy": {
                "llm": {
                    "reporter": {
                        "daily": {
                            "primary": "moonshotai/kimi-k2.5",
                            "execution_profile": {
                                "name": "deep_review",
                                "temperature": 0.35,
                                "max_tokens": 1234,
                            },
                        }
                    }
                }
            },
        },
        policy={},
    )

    assert summary
    assert artifact["status"] == "ok"
    assert isinstance(_CaptureDailyRouter.last_policy, dict)
    assert _CaptureDailyRouter.last_policy["model"] == "moonshotai/kimi-k2.5"
    assert float(_CaptureDailyRouter.last_policy["temperature"]) == 0.35
    assert int(_CaptureDailyRouter.last_policy["max_tokens"]) == 1234
    assert artifact["llm_execution_profile_name"] == "deep_review"
    assert artifact["llm_execution_profile_source"] == "applied_policy"
    assert int(((artifact["llm_execution_effective_config"] or {}).get("retry") or {}).get("max_attempts") or 0) == 2


def test_m19_6_daily_summary_prefers_top_level_execution_profile(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
    monkeypatch.setattr("libs.reporting.llm_daily_summary.LLMRouter", _CaptureDailyRouter)

    summary, artifact = summarize_daily_report_with_artifact(
        state={
            "eod_day": "2026-03-18",
            "daily_report": {"approvals": 1, "denials": 0, "runs": 3},
            "applied_policy": {
                "llm": {
                    "execution_profile": {
                        "profile_name": "default_intraday",
                        "temperature": 0.41,
                        "max_tokens": 1500,
                        "timeout_sec": 9,
                        "retry": {"max_attempts": 4, "backoff_sec": 0.0},
                    },
                    "reporter": {
                        "daily": {
                            "primary": "moonshotai/kimi-k2.5",
                            "execution_profile": {
                                "name": "deep_review",
                                "temperature": 0.35,
                                "max_tokens": 1234,
                            },
                        }
                    },
                }
            },
        },
        policy={},
    )

    assert summary
    assert float(_CaptureDailyRouter.last_policy["temperature"]) == 0.41
    assert int(_CaptureDailyRouter.last_policy["max_tokens"]) == 1500
    assert float(_CaptureDailyRouter.last_policy["timeout_sec"]) == 9.0
    assert artifact["llm_execution_profile_name"] == "default_intraday"
    assert artifact["llm_execution_profile_source"] == "applied_policy"
