from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import libs.reporting.post_exit_shadow_recap as recap_mod
from libs.reporting.post_exit_shadow_recap import generate_post_exit_shadow_recap
from libs.reporting.trade_report_post_exit_shadow import build_post_exit_shadow_summary_lines


def _epoch(year: int, month: int, day: int, hour: int, minute: int) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp())


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_post_exit_shadow_recap_updates_from_state_cache_without_rewriting_report(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    report_path = (
        reports_root
        / "trades"
        / "2026-05-18"
        / "0900"
        / "TRD_20260518_005930_01"
        / "reports"
        / "ai_trade_report.json"
    )
    report = {
        "trade_id": "TRD_20260518_005930_01",
        "symbol": "005930",
        "post_exit_shadow": {
            "schema_version": "post_exit_shadow.v1",
            "observability_only": True,
            "status": "pending",
            "symbol": "005930",
            "exit_ts": "2026-05-18T00:00:00+00:00",
            "exit_price": 70000,
            "checkpoints": {
                "+5m": {"status": "pending"},
                "+15m": {"status": "pending"},
                "+30m": {"status": "pending"},
                "+60m": {"status": "pending"},
                "EOD": {"status": "pending"},
            },
        },
    }
    _write_json(report_path, report)
    original_report_text = report_path.read_text(encoding="utf-8")

    state_path = tmp_path / "state.json"
    _write_json(
        state_path,
        {
            "persisted_state": {
                "recent_minute_ohlcv_by_symbol": {
                    "005930": {
                        "rows": [
                            {"ts": _epoch(2026, 5, 18, 0, 5), "close": 70400, "high": 70500, "low": 69900, "raw_ts": "20260518090500"},
                            {"ts": _epoch(2026, 5, 18, 0, 15), "close": 71000, "high": 71200, "low": 70400, "raw_ts": "20260518091500"},
                            {"ts": _epoch(2026, 5, 18, 6, 30), "close": 71500, "high": 71800, "low": 69800, "raw_ts": "20260518153000"},
                        ]
                    }
                }
            }
        },
    )

    out = generate_post_exit_shadow_recap(
        reports_root=reports_root,
        report_dir=reports_root / "dev" / "analysis" / "post_exit_shadow_recap",
        day="2026-05-18",
        state_path=state_path,
    )

    assert out["summary"]["total"] == 1
    assert out["summary"]["observed"] == 1
    assert out["summary"]["eod_observed"] == 1
    trade = out["trades"][0]
    assert trade["checkpoints"]["+5m"]["status"] == "observed"
    assert trade["checkpoints"]["+15m"]["price"] == 71000.0
    assert trade["checkpoints"]["EOD"]["status"] == "observed"
    assert Path(trade["recap_json_path"]).exists()
    assert Path(trade["recap_md_path"]).exists()
    assert Path(out["report_json_path"]).exists()
    assert Path(out["report_md_path"]).exists()
    assert report_path.read_text(encoding="utf-8") == original_report_text


def test_post_exit_shadow_recap_uses_default_state_json_when_state_path_omitted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    reports_root = tmp_path / "reports"
    report_path = (
        reports_root
        / "trades"
        / "2026-05-18"
        / "0900"
        / "TRD_20260518_005930_01"
        / "reports"
        / "ai_trade_report.json"
    )
    _write_json(
        report_path,
        {
            "trade_id": "TRD_20260518_005930_01",
            "symbol": "005930",
            "post_exit_shadow": {
                "schema_version": "post_exit_shadow.v1",
                "observability_only": True,
                "symbol": "005930",
                "exit_ts": "2026-05-18T00:00:00+00:00",
                "exit_price": 70000,
                "checkpoints": {
                    "+5m": {"status": "pending"},
                    "+15m": {"status": "pending"},
                    "+30m": {"status": "pending"},
                    "+60m": {"status": "pending"},
                    "EOD": {"status": "pending"},
                },
            },
        },
    )
    _write_json(
        tmp_path / "data" / "state.json",
        {
            "persisted_state": {
                "recent_minute_ohlcv_by_symbol": {
                    "005930": {
                        "rows": [
                            {"ts": _epoch(2026, 5, 18, 0, 5), "close": 70400, "raw_ts": "20260518090500"},
                            {"ts": _epoch(2026, 5, 18, 0, 15), "close": 71000, "raw_ts": "20260518091500"},
                        ]
                    }
                }
            }
        },
    )

    out = generate_post_exit_shadow_recap(
        reports_root=reports_root,
        report_dir=reports_root / "dev" / "analysis" / "post_exit_shadow_recap",
        day="2026-05-18",
    )

    assert out["source"]["state_path"].endswith("data\\state.json") or out["source"]["state_path"].endswith("data/state.json")
    assert out["source"]["state_loaded"] is True
    assert out["summary"]["observed"] == 1
    assert out["trades"][0]["source_minute_rows"] == 2


def test_post_exit_shadow_recap_refreshes_trade_summary_markdown(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    reports_dir = (
        reports_root
        / "trades"
        / "2026-05-18"
        / "1200"
        / "TRD_20260518_005930_01"
        / "reports"
    )
    report_path = reports_dir / "ai_trade_report.json"
    _write_json(
        report_path,
        {
            "trade_id": "TRD_20260518_005930_01",
            "symbol": "005930",
            "post_exit_shadow": {
                "schema_version": "post_exit_shadow.v1",
                "observability_only": True,
                "symbol": "005930",
                "exit_ts": "2026-05-18T03:35:00+00:00",
                "exit_price": 282000,
                "checkpoints": {
                    "+5m": {"status": "pending"},
                    "+15m": {"status": "pending"},
                    "+30m": {"status": "pending"},
                    "+60m": {"status": "pending"},
                    "EOD": {"status": "pending"},
                },
            },
        },
    )
    (reports_dir / "ai_trade_summary.md").parent.mkdir(parents=True, exist_ok=True)
    (reports_dir / "ai_trade_summary.md").write_text("old pending summary\n", encoding="utf-8")
    _write_json(reports_dir / "ai_trade_summary_input.json", {"old": True})

    state_path = tmp_path / "state.json"
    _write_json(
        state_path,
        {
            "persisted_state": {
                "recent_minute_ohlcv_by_symbol": {
                    "005930": {
                        "rows": [
                            {"ts": _epoch(2026, 5, 18, 3, 40), "close": 284000, "high": 284000, "low": 282000, "raw_ts": "20260518124000"},
                            {"ts": _epoch(2026, 5, 18, 3, 50), "close": 282500, "high": 285000, "low": 282000, "raw_ts": "20260518125000"},
                        ]
                    }
                }
            }
        },
    )

    out = generate_post_exit_shadow_recap(
        reports_root=reports_root,
        report_dir=reports_root / "dev" / "analysis" / "post_exit_shadow_recap",
        day="2026-05-18",
        state_path=state_path,
    )

    trade = out["trades"][0]
    assert trade["summary_refresh"]["ok"] is True
    daily_recap = json.loads(Path(out["report_json_path"]).read_text(encoding="utf-8"))
    assert daily_recap["policy"]["refresh_trade_summary"] is True
    assert daily_recap["trades"][0]["summary_refresh"]["ok"] is True
    summary_md = (reports_dir / "ai_trade_summary.md").read_text(encoding="utf-8")
    assert "284,000" in summary_md
    summary_input = json.loads((reports_dir / "ai_trade_summary_input.json").read_text(encoding="utf-8"))
    assert summary_input["post_exit_shadow"]["checkpoints"]["+5m"]["price"] == 284000.0


def test_post_exit_shadow_summary_treats_zero_exit_price_as_unconfirmed_fill() -> None:
    report = {
        "post_exit_shadow": {
            "schema_version": "post_exit_shadow.v1",
            "observability_only": True,
            "symbol": "005930",
            "exit_ts": "",
            "exit_price": 0,
            "price_observation_status": "pending",
            "price_observation_reason": "missing_exit_time_or_price",
            "checkpoints": {
                "+5m": {"status": "pending"},
                "+15m": {"status": "pending"},
            },
        }
    }

    lines = build_post_exit_shadow_summary_lines(
        report,
        summary_money=lambda value: f"{int(float(value)):,}",
        fmt_pct=lambda value: "-" if value in (None, "") else f"{float(value) * 100:.2f}%",
        metadata_value=lambda value: str(value),
        num_opt=lambda value: None if value in (None, "") else float(value),
    )

    text = "\n".join(lines)
    assert "* 매도 기준가: -" in text
    assert "청산 체결 시각 또는 기준가가 확정되지 않아" in text


def test_post_exit_shadow_recap_does_not_use_next_trading_day_for_intraday_checkpoints(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    report_path = (
        reports_root
        / "trades"
        / "2026-05-15"
        / "1400"
        / "TRD_20260515_080220_01"
        / "reports"
        / "ai_trade_report.json"
    )
    _write_json(
        report_path,
        {
            "trade_id": "TRD_20260515_080220_01",
            "symbol": "080220",
            "post_exit_shadow": {
                "schema_version": "post_exit_shadow.v1",
                "observability_only": True,
                "status": "pending",
                "symbol": "080220",
                "exit_ts": "2026-05-15T05:45:00+00:00",
                "exit_price": 80000,
                "checkpoints": {
                    "+5m": {"status": "pending"},
                    "+15m": {"status": "pending"},
                    "+30m": {"status": "pending"},
                    "+60m": {"status": "pending"},
                    "EOD": {"status": "pending"},
                },
            },
        },
    )
    state_path = tmp_path / "state.json"
    _write_json(
        state_path,
        {
            "persisted_state": {
                "recent_minute_ohlcv_by_symbol": {
                    "080220": {
                        "rows": [
                            {"ts": _epoch(2026, 5, 15, 5, 50), "close": 81000, "high": 81200, "low": 79800, "raw_ts": "20260515145000"},
                            {"ts": _epoch(2026, 5, 15, 6, 35), "close": 80500, "high": 81500, "low": 79500, "raw_ts": "20260515153500"},
                            {"ts": _epoch(2026, 5, 18, 0, 0), "close": 86000, "high": 86500, "low": 85000, "raw_ts": "20260518090000"},
                        ]
                    }
                }
            }
        },
    )

    out = generate_post_exit_shadow_recap(
        reports_root=reports_root,
        report_dir=reports_root / "dev" / "analysis" / "post_exit_shadow_recap",
        day="2026-05-15",
        state_path=state_path,
    )

    trade = out["trades"][0]
    assert trade["checkpoints"]["+5m"]["status"] == "observed"
    assert trade["checkpoints"]["EOD"]["status"] == "observed"
    assert trade["checkpoints"]["+60m"]["status"] == "observed"
    assert trade["post_exit_shadow"]["checkpoints"]["+60m"]["closeout_substitute"] is True
    assert trade["best_exit_price"] != 86500.0


def test_post_exit_shadow_recap_fetches_fresh_minutes_when_cache_stops_before_mature_checkpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    reports_root = tmp_path / "reports"
    report_path = (
        reports_root
        / "trades"
        / "2020-01-02"
        / "1400"
        / "TRD_20200102_034220_02"
        / "reports"
        / "ai_trade_report.json"
    )
    _write_json(
        report_path,
        {
            "trade_id": "TRD_20200102_034220_02",
            "symbol": "034220",
            "post_exit_shadow": {
                "schema_version": "post_exit_shadow.v1",
                "observability_only": True,
                "status": "pending",
                "symbol": "034220",
                "exit_ts": "2020-01-02T05:43:35+00:00",
                "exit_price": 14780,
                "checkpoints": {
                    "+5m": {"status": "pending"},
                    "+15m": {"status": "pending"},
                    "+30m": {"status": "pending"},
                    "+60m": {"status": "pending"},
                    "EOD": {"status": "pending"},
                },
            },
        },
    )
    state_path = tmp_path / "state.json"
    _write_json(
        state_path,
        {
            "persisted_state": {
                "recent_minute_ohlcv_by_symbol": {
                    "034220": {
                        "rows": [
                            {"ts": _epoch(2020, 1, 2, 5, 49), "close": 14720, "high": 14790, "low": 14710, "raw_ts": "20200102144900"},
                            {"ts": _epoch(2020, 1, 2, 6, 14), "close": 14660, "high": 14790, "low": 14600, "raw_ts": "20200102151400"},
                        ]
                    }
                }
            }
        },
    )

    def fake_fetch(symbol: str, *, run_id: str = "post_exit_shadow_recap"):
        assert symbol == "034220"
        assert "TRD_20200102_034220_02" in run_id
        return [
            {"ts": _epoch(2020, 1, 2, 6, 44), "close": 14580, "high": 14620, "low": 14550, "raw_ts": "20200102154400"},
        ], {"attempted": True, "ok": True, "rows": 1, "source": "test"}

    monkeypatch.setattr(recap_mod, "fetch_fresh_minute_rows_for_symbol", fake_fetch)

    out = generate_post_exit_shadow_recap(
        reports_root=reports_root,
        report_dir=reports_root / "dev" / "analysis" / "post_exit_shadow_recap",
        day="2020-01-02",
        state_path=state_path,
    )

    trade = out["trades"][0]
    assert trade["fresh_minute_fetch"]["attempted"] is True
    assert trade["fresh_minute_fetch"]["ok"] is True
    assert trade["source_minute_rows"] == 3
    assert trade["checkpoints"]["+60m"]["status"] == "observed"
    assert trade["checkpoints"]["+60m"]["price"] == 14580.0
