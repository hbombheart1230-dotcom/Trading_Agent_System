from pathlib import Path

from libs.reporting import operator_summary_refresh as mod


def test_refresh_operator_summaries_after_trade_updates_symbol_daily_weekly_monthly(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def fake_symbol(*, events_path: Path, reports_root: Path, symbol: str):
        calls.append(("symbol", symbol))
        root = reports_root / "operator_summary" / "symbols" / symbol
        root.mkdir(parents=True, exist_ok=True)
        return {
            "symbol_summary_md_path": str(root / "symbol_summary.md"),
            "symbol_summary_json_path": str(root / "symbol_summary.json"),
            "trade_history_path": str(root / "trade_history.json"),
        }

    def fake_daily(*, reports_root: Path, day: str, daily_report_payload=None):
        calls.append(("daily", day))
        root = reports_root / "operator_summary" / "daily" / day
        return root / "daily_summary.md", root / "daily_summary.json", {"metrics": {"trade_count": 1}}

    def fake_period(*, reports_root: Path, period_type: str, period_key: str):
        calls.append((period_type, period_key))
        root = reports_root / "operator_summary" / period_type / period_key
        return (
            root / f"{period_type}_summary.md",
            root / f"{period_type}_summary.json",
            {"metrics": {"trade_count": 1}},
        )

    monkeypatch.setattr(mod, "generate_symbol_trade_report", fake_symbol)
    monkeypatch.setattr(mod, "generate_operator_daily_summary_artifact", fake_daily)
    monkeypatch.setattr(mod, "generate_operator_period_summary", fake_period)

    result = mod.refresh_operator_summaries_after_trade(
        reports_root=tmp_path / "reports",
        event_log_path=tmp_path / "events.jsonl",
        day="2026-04-29",
        symbol="098460",
    )

    assert result["status"] == "ok"
    assert result["artifacts"]["symbol"]["json_path"].endswith("symbol_summary.json")
    assert result["artifacts"]["daily"]["json_path"].endswith("daily_summary.json")
    assert result["artifacts"]["weekly"]["period_key"] == "2026-W18"
    assert result["artifacts"]["monthly"]["period_key"] == "2026-04"
    assert calls == [
        ("symbol", "098460"),
        ("daily", "2026-04-29"),
        ("weekly", "2026-W18"),
        ("monthly", "2026-04"),
    ]

