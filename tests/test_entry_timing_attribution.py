from __future__ import annotations

from datetime import datetime, timezone

from libs.reporting.evaluation.entry_timing_attribution import (
    build_entry_timing_attribution_report,
)


def _epoch(text: str) -> int:
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())


def _row(ts: str, close: float, *, high: float | None = None, low: float | None = None) -> dict:
    return {
        "ts": _epoch(ts),
        "close": close,
        "high": high if high is not None else close,
        "low": low if low is not None else close,
    }


def _model(
    *,
    trade_id: str,
    symbol: str,
    decision_id: str,
    entry_ts: str,
    entry_price: float,
    realized: float,
) -> dict:
    return {
        "trade_id": trade_id,
        "symbol": symbol,
        "entry": {"timestamp": entry_ts, "price": entry_price},
        "outcome": {"net_return_pct": realized},
        "selection": {
            "q9_decision_id": decision_id,
            "raw_scanner_top1": {"symbol": symbol, "rank": 1},
            "scanner_top1": {"symbol": symbol, "rank": 1},
            "selected_symbol": symbol,
            "selected_rank": 1,
            "selected_candidate": {"symbol": symbol, "rank": 1},
        },
    }


def test_entry_timing_labels_too_late_with_pre_entry_alpha(tmp_path):
    reports = tmp_path / "reports"
    day_dir = reports / "operator_summary" / "daily" / "2026-07-06"
    day_dir.mkdir(parents=True)
    decision_epoch = _epoch("2026-07-06T00:00:00+00:00")
    (day_dir / "q9_decision_windows.json").write_text(
        """
        {
          "windows": [
            {
              "decision_id": "D1",
              "decision_epoch": %d,
              "generated_at": "2026-07-06T00:00:00+00:00",
              "strategist_selection": {"post_strategist_top10": [{"symbol": "005930"}]}
            }
          ]
        }
        """ % decision_epoch,
        encoding="utf-8",
    )
    model = _model(
        trade_id="T1",
        symbol="005930",
        decision_id="D1",
        entry_ts="2026-07-06T00:05:00+00:00",
        entry_price=101.0,
        realized=-0.5,
    )
    candles = {
        "005930": [
            _row("2026-07-06T00:00:00+00:00", 100.0),
            _row("2026-07-06T00:05:00+00:00", 101.0),
            _row("2026-07-06T00:10:00+00:00", 100.8, high=101.0, low=100.7),
            _row("2026-07-06T00:20:00+00:00", 100.7, high=101.0, low=100.5),
            _row("2026-07-06T00:35:00+00:00", 100.5, high=101.0, low=100.3),
        ]
    }

    report = build_entry_timing_attribution_report(
        day="2026-07-06",
        models=[model],
        reports_root=reports,
        minute_rows_by_symbol=candles,
    )

    assert report["rows"][0]["label"] == "ENTRY_TOO_LATE"
    assert report["rows"][0]["scanner_to_entry_delay_sec"] == 300
    assert report["rows"][0]["pre_entry_move_pct"] == 1.0


def test_entry_timing_labels_too_early_with_immediate_adverse_move(tmp_path):
    reports = tmp_path / "reports"
    day_dir = reports / "operator_summary" / "daily" / "2026-07-06"
    day_dir.mkdir(parents=True)
    decision_epoch = _epoch("2026-07-06T00:00:00+00:00")
    (day_dir / "q9_decision_windows.json").write_text(
        f'{{"windows":[{{"decision_id":"D2","decision_epoch":{decision_epoch},"strategist_selection":{{}}}}]}}',
        encoding="utf-8",
    )
    model = _model(
        trade_id="T2",
        symbol="000660",
        decision_id="D2",
        entry_ts="2026-07-06T00:00:00+00:00",
        entry_price=100.0,
        realized=-1.0,
    )
    candles = {
        "000660": [
            _row("2026-07-06T00:00:00+00:00", 100.0),
            _row("2026-07-06T00:05:00+00:00", 99.3, high=100.0, low=99.2),
            _row("2026-07-06T00:15:00+00:00", 99.1, high=99.5, low=98.9),
            _row("2026-07-06T00:30:00+00:00", 99.0, high=99.4, low=98.8),
        ]
    }

    report = build_entry_timing_attribution_report(
        day="2026-07-06",
        models=[model],
        reports_root=reports,
        minute_rows_by_symbol=candles,
    )

    assert report["rows"][0]["label"] == "ENTRY_TOO_EARLY"
    assert "immediate_adverse_move_without_prior_alpha" in report["rows"][0]["label_reasons"]


def test_entry_timing_falls_back_to_insufficient_evidence(tmp_path):
    reports = tmp_path / "reports"
    model = _model(
        trade_id="T3",
        symbol="035420",
        decision_id="MISSING",
        entry_ts="2026-07-06T00:00:00+00:00",
        entry_price=100.0,
        realized=0.0,
    )

    report = build_entry_timing_attribution_report(
        day="2026-07-06",
        models=[model],
        reports_root=reports,
        minute_rows_by_symbol={},
    )

    assert report["rows"][0]["label"] == "INSUFFICIENT_EVIDENCE"
    assert report["rows"][0]["entry_forward_quality"]["forward_available"] is False


def test_entry_timing_excludes_confirmed_runtime_defect(tmp_path):
    model = _model(
        trade_id="T4",
        symbol="006800",
        decision_id="D4",
        entry_ts="2026-07-21T00:54:02+00:00",
        entry_price=100.0,
        realized=-0.92,
    )
    model["integrity"] = {"defects": ["confirmed_runtime_defect"]}

    report = build_entry_timing_attribution_report(
        day="2026-07-21",
        models=[model],
        reports_root=tmp_path / "reports",
        minute_rows_by_symbol={},
    )

    assert report["trade_count"] == 0
    assert report["excluded_trade_count"] == 1
