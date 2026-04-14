from __future__ import annotations

import json
import os
import subprocess
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


def test_intraday_trade_reports_respects_applied_policy_disable(monkeypatch) -> None:
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-disabled",
            "applied_policy": {"reporter": {"trade_report": {"enabled": False, "policy_source": "commander_applied_policy"}}},
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "BUY", "symbol": "005930"},
            },
        }
    )
    assert out["ok"] is False
    assert out["status"] == "disabled"
    assert out["reason"] == "reporter.trade_report.enabled is false"
    assert out["policy_source"] == "commander_applied_policy"


def test_intraday_trade_reports_skips_buy_when_generate_on_open_disabled(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._root_dir", lambda: root)

    popen_called = False

    def fake_popen(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal popen_called
        popen_called = True
        raise AssertionError("BUY should not spawn report bundle when generate_on_open is disabled")

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-buy-skip",
            "applied_policy": {"reporter": {"trade_report": {"enabled": True, "generate_on_open": False}}},
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "BUY", "symbol": "000660"},
            },
        },
    )

    assert out["ok"] is True
    assert out["status"] == "skipped"
    assert out["reason"] == "trade_report_generate_on_open_disabled"
    assert out["report_status"] == "pending"
    assert out["symbol"] == "000660"
    assert out["target_run_id"] == "run-buy-skip"
    assert popen_called is False


def test_intraday_trade_reports_queues_background_job_after_timeout(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))
    monkeypatch.setenv("INTRADAY_TRADE_REPORT_SYNC_TIMEOUT_SEC", "0.5")
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._root_dir", lambda: root)

    popen_calls: list[list[str]] = []

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args") or args[0], timeout=0.5)

    class DummyProc:
        pid = 43210

    def fake_popen(cmd, **kwargs):  # type: ignore[no-untyped-def]
        popen_calls.append(list(cmd))
        return DummyProc()

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-timeout",
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "SELL", "symbol": "069500"},
            },
        }
    )

    assert out["ok"] is True
    assert out["status"] == "queued"
    assert out["report_status"] == "queued"
    assert out["queue_mode"] == "background_subprocess"
    assert out["background_pid"] == 43210
    assert out["symbol"] == "069500"
    assert popen_calls
    flat_cmd = " ".join(popen_calls[0])
    assert "--max-runs" not in flat_cmd
    assert "--target-run-id run-timeout" in flat_cmd
    assert "--target-symbol 069500" in flat_cmd
    assert "--role intraday_trade_report_bundle" in flat_cmd


def test_intraday_trade_reports_dedupes_when_background_job_is_already_running(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._root_dir", lambda: root)

    lock_path = root / "reports" / "runtime" / "intraday_trade_report_bundle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "started_at_epoch": 9999999999.0,
                "script": "run_live_execution_bundle_report.py",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    popen_called = False

    def fake_popen(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal popen_called
        popen_called = True
        raise AssertionError("duplicate background job should not spawn")

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-dedupe",
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "SELL", "symbol": "005930"},
            },
        }
    )

    assert out["ok"] is True
    assert out["status"] == "skipped"
    assert out["reason"] == "bundle_job_already_running"
    assert out["report_status"] == "queued"
    assert out["queue_mode"] == "background_subprocess_deduped"
    assert out["background_pid"] == os.getpid()
    assert out["lock_path"] == str(lock_path)
    queue_path = root / "reports" / "runtime" / "intraday_trade_report_bundle.queue.json"
    queue_rows = json.loads(queue_path.read_text(encoding="utf-8"))
    assert len(queue_rows) == 1
    assert queue_rows[0]["target_run_id"] == "run-dedupe"
    assert queue_rows[0]["target_symbol"] == "005930"
    assert popen_called is False


def test_intraday_trade_reports_dedupes_when_background_process_is_already_running(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._root_dir", lambda: root)
    monkeypatch.setattr(
        "libs.reporting.intraday_trade_reports._active_bundle_process",
        lambda _root: {
            "pid": 65432,
            "script": "run_live_execution_bundle_report.py",
            "command_line": "python scripts/run_live_execution_bundle_report.py --json",
            "detection_source": "process_scan",
        },
    )

    popen_called = False

    def fake_popen(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal popen_called
        popen_called = True
        raise AssertionError("duplicate background job should not spawn")

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-dedupe-process",
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "SELL", "symbol": "005930"},
            },
        }
    )

    assert out["ok"] is True
    assert out["status"] == "skipped"
    assert out["reason"] == "bundle_job_already_running"
    assert out["report_status"] == "queued"
    assert out["queue_mode"] == "background_subprocess_deduped"
    assert out["background_pid"] == 65432
    assert out["dedupe_source"] == "process_scan"
    queue_path = root / "reports" / "runtime" / "intraday_trade_report_bundle.queue.json"
    queue_rows = json.loads(queue_path.read_text(encoding="utf-8"))
    assert len(queue_rows) == 1
    assert queue_rows[0]["target_run_id"] == "run-dedupe-process"
    assert queue_rows[0]["target_symbol"] == "005930"
    assert popen_called is False


def test_intraday_trade_reports_removes_stale_lock_then_queues_background_job(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._root_dir", lambda: root)

    lock_path = root / "reports" / "runtime" / "intraday_trade_report_bundle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "pid": 999999,
                "role": "intraday_trade_report_bundle",
                "started_at_epoch": 1.0,
                "touched_at_epoch": 1.0,
                "script": "run_live_execution_bundle_report.py",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    popen_calls: list[list[str]] = []

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args") or args[0], timeout=0.5)

    class DummyProc:
        pid = 54321

    def fake_popen(cmd, **kwargs):  # type: ignore[no-untyped-def]
        popen_calls.append(list(cmd))
        return DummyProc()

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-stale-lock",
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "SELL", "symbol": "005930"},
            },
        }
    )

    assert out["ok"] is True
    assert out["status"] == "queued"
    assert out["background_pid"] == 54321
    assert popen_calls
    lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert int(lock_payload["pid"]) == 54321
    assert str(lock_payload["role"]) == "intraday_trade_report_bundle"


def test_intraday_trade_reports_terminates_stale_orphan_process_then_queues_background_job(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._root_dir", lambda: root)
    monkeypatch.setattr(
        "libs.reporting.intraday_trade_reports._active_bundle_process",
        lambda _root: {
            "pid": 76543,
            "parent_pid": 111,
            "script": "run_live_execution_bundle_report.py",
            "command_line": "python scripts/run_live_execution_bundle_report.py --role intraday_trade_report_bundle",
            "detection_source": "process_scan",
            "age_sec": 999.0,
        },
    )

    terminated = {"called": False}

    def fake_terminate(pid):  # type: ignore[no-untyped-def]
        terminated["called"] = True
        return True

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args") or args[0], timeout=0.5)

    class DummyProc:
        pid = 65432

    def fake_popen(cmd, **kwargs):  # type: ignore[no-untyped-def]
        return DummyProc()

    monkeypatch.setattr("libs.reporting.intraday_trade_reports._terminate_process_tree", fake_terminate)
    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-stale-process",
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "SELL", "symbol": "005930"},
            },
        }
    )

    assert terminated["called"] is True
    assert out["ok"] is True
    assert out["status"] == "queued"
    assert out["background_pid"] == 65432
