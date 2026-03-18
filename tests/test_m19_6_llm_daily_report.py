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
