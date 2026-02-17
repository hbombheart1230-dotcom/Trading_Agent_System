from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import scripts.run_m25_ops_batch as batch_mod
from scripts.run_m25_ops_batch import main as batch_main


def test_m25_5_ops_batch_pass_writes_latest_status(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    lock_path = tmp_path / "batch.lock"
    status_path = tmp_path / "status_latest.json"

    rc = batch_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-17",
            "--lock-path",
            str(lock_path),
            "--status-json-path",
            str(status_path),
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    saved = json.loads(status_path.read_text(encoding="utf-8"))

    assert rc == 0
    assert obj["ok"] is True
    assert obj["rc"] == 0
    assert saved["ok"] is True
    assert saved["rc"] == 0
    assert lock_path.exists() is False


def test_m25_5_ops_batch_fail_propagates_rc_3(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    lock_path = tmp_path / "batch.lock"
    status_path = tmp_path / "status_latest.json"

    rc = batch_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-17",
            "--lock-path",
            str(lock_path),
            "--status-json-path",
            str(status_path),
            "--inject-critical-case",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["rc"] == 3
    assert obj["closeout"]["alert_policy"]["rc"] == 3


def test_m25_5_ops_batch_lock_active_returns_4(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    lock_path = tmp_path / "batch.lock"
    status_path = tmp_path / "status_latest.json"

    lock_path.write_text(
        json.dumps({"pid": 99999, "started_epoch": 9999999999, "started_ts": "future"}, ensure_ascii=False),
        encoding="utf-8",
    )

    rc = batch_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-17",
            "--lock-path",
            str(lock_path),
            "--status-json-path",
            str(status_path),
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 4
    assert obj["ok"] is False
    assert obj["reason"] == "lock_active"
    assert status_path.exists() is True


def test_m25_5_ops_batch_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m25_ops_batch.py"
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    lock_path = tmp_path / "batch.lock"
    status_path = tmp_path / "status_latest.json"

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-17",
            "--lock-path",
            str(lock_path),
            "--status-json-path",
            str(status_path),
            "--json",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True


def test_m25_5_ops_batch_can_fail_on_notify_error(monkeypatch, tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    lock_path = tmp_path / "batch.lock"
    status_path = tmp_path / "status_latest.json"

    def _fake_notify_batch_result(**kwargs):  # type: ignore[no-untyped-def]
        return {
            "ok": False,
            "provider": "webhook",
            "sent": True,
            "skipped": False,
            "reason": "http_error",
            "status_code": 500,
            "error": "boom",
        }

    monkeypatch.setattr(batch_mod, "notify_batch_result", _fake_notify_batch_result)

    rc = batch_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-17",
            "--lock-path",
            str(lock_path),
            "--status-json-path",
            str(status_path),
            "--notify-provider",
            "slack_webhook",
            "--notify-webhook-url",
            "https://example.invalid/hook",
            "--notify-on",
            "always",
            "--fail-on-notify-error",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 5
    assert obj["ok"] is False
    assert obj["rc"] == 5
    assert obj["notify"]["ok"] is False
    assert obj["notify"]["skipped"] is False


def test_m25_7_ops_batch_forwards_notify_noise_control_args(monkeypatch, tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    lock_path = tmp_path / "batch.lock"
    status_path = tmp_path / "status_latest.json"
    state_path = tmp_path / "notify_state.json"
    captured: dict = {}

    def _fake_notify_batch_result(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return {
            "ok": True,
            "provider": "webhook",
            "sent": True,
            "skipped": False,
            "reason": "sent",
            "status_code": 200,
            "error": "",
        }

    monkeypatch.setattr(batch_mod, "notify_batch_result", _fake_notify_batch_result)

    rc = batch_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-17",
            "--lock-path",
            str(lock_path),
            "--status-json-path",
            str(status_path),
            "--notify-provider",
            "slack_webhook",
            "--notify-webhook-url",
            "https://example.invalid/hook",
            "--notify-on",
            "always",
            "--notify-state-path",
            str(state_path),
            "--notify-dedup-window-sec",
            "120",
            "--notify-rate-limit-window-sec",
            "300",
            "--notify-max-per-window",
            "2",
            "--notify-retry-max",
            "2",
            "--notify-retry-backoff-sec",
            "0.2",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["notify"]["ok"] is True
    assert captured["provider"] == "slack_webhook"
    assert captured["state_path"] == str(state_path)
    assert captured["dedup_window_sec"] == 120
    assert captured["rate_limit_window_sec"] == 300
    assert captured["max_per_window"] == 2
    assert captured["retry_max"] == 2
    assert captured["retry_backoff_sec"] == 0.2
