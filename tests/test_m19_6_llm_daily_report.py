from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pytest

from graphs.pipelines.m13_eod_report import run_m13_eod_report


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
