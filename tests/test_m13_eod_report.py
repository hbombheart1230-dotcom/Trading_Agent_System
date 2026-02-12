from datetime import datetime, timezone, timedelta
from pathlib import Path

from graphs.pipelines.m13_eod_report import run_m13_eod_report
from libs.runtime.market_hours import MarketHours

KST = timezone(timedelta(hours=9))

def test_eod_skips_before_close(tmp_path: Path):
    state = {}
    dt = datetime(2026, 2, 13, 15, 0, tzinfo=KST)  # Fri 15:00 < 15:30
    called = {"n": 0}

    def fake_generate(events_path: Path, report_dir: Path, day: str):
        called["n"] += 1
        return (tmp_path/"x.md", tmp_path/"x.json")

    out = run_m13_eod_report(state, dt=dt, market_hours=MarketHours(), generate=fake_generate, grace_minutes=0)
    assert out["eod_skipped"] is True
    assert out["eod_skip_reason"] == "before_close"
    assert called["n"] == 0

def test_eod_runs_once_after_close(tmp_path: Path):
    state = {}
    dt = datetime(2026, 2, 13, 15, 40, tzinfo=KST)  # Fri after close
    called = {"n": 0}

    def fake_generate(events_path: Path, report_dir: Path, day: str):
        called["n"] += 1
        md = tmp_path / f"{day}.md"
        js = tmp_path / f"{day}.json"
        md.write_text("ok", encoding="utf-8")
        js.write_text("{}", encoding="utf-8")
        return (md, js)

    out1 = run_m13_eod_report(state, dt=dt, market_hours=MarketHours(), generate=fake_generate, grace_minutes=0)
    assert out1["eod_skipped"] is False
    assert out1["daily_report"]["day"] == "2026-02-13"
    assert called["n"] == 1

    out2 = run_m13_eod_report(state, dt=dt, market_hours=MarketHours(), generate=fake_generate, grace_minutes=0)
    assert out2["eod_skipped"] is True
    assert out2["eod_skip_reason"] == "already_generated"
    assert called["n"] == 1
