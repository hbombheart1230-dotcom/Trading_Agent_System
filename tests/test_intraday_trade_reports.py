from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.intraday_trade_reports import generate_intraday_trade_artifacts


def test_intraday_trade_reports_generates_and_invalidates_cache(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    cache_dir = root / "data" / "operator_ui" / "brief_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "run-1.json"
    cache_path.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("OPERATOR_UI_CACHE_PATH", str(cache_dir))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))

    def fake_main(argv):  # type: ignore[no-untyped-def]
        out = {
            "run_bundles": [
                {
                    "run_id": "run-1",
                    "trade_id": "TRD_20260317_005930_01",
                    "story_id": "TRD_20260317_005930_01",
                    "report_status": "available",
                    "trade_report_json_path": str(root / "reports" / "trades" / "2026-03-17" / "TRD_20260317_005930_01" / "reports" / "ai_trade_report.json"),
                    "symbol": "005930",
                }
            ]
        }
        print(json.dumps(out, ensure_ascii=False))
        return 0

    monkeypatch.setattr("scripts.run_live_execution_bundle_report.main", fake_main)
    brief_json = root / "reports" / "trades" / "2026-03-17" / "TRD_20260317_005930_01" / "reports" / "operator_brief.json"
    brief_md = root / "reports" / "trades" / "2026-03-17" / "TRD_20260317_005930_01" / "reports" / "operator_brief.md"
    brief_json.parent.mkdir(parents=True, exist_ok=True)
    brief_json.write_text(json.dumps({"headline": "brief"}, ensure_ascii=False), encoding="utf-8")
    brief_md.write_text("# brief\n", encoding="utf-8")

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-1",
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "BUY", "symbol": "005930"},
            },
        },
        root=root,
    )

    assert out["ok"] is True
    assert out["status"] == "generated"
    assert out["trade_id"] == "TRD_20260317_005930_01"
    assert out["report_status"] == "available"
    assert cache_path.exists() is False
    assert out["operator_brief_json_path"] == str(brief_json)
    assert out["operator_brief_md_path"] == str(brief_md)
    assert brief_json.exists() is True
    assert brief_md.exists() is True


def test_intraday_trade_reports_skips_when_execution_failed(monkeypatch) -> None:
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-2",
            "execution": {
                "ok": False,
                "allowed": False,
                "order": {"action": "BUY", "symbol": "005930"},
            },
        }
    )
    assert out["ok"] is False
    assert out["reason"] == "execution_not_successful"
