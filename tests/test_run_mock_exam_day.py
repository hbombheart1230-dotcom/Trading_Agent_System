from __future__ import annotations

import json
from pathlib import Path

import scripts.run_mock_exam_day as mod


def _write_env(path: Path, pairs: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"{k}={v}" for k, v in pairs.items()) + "\n"
    path.write_text(body, encoding="utf-8")


def test_preopen_fail_fast_blocks_after_first_failure(tmp_path: Path, capsys, monkeypatch):
    env_path = tmp_path / ".env"
    events = tmp_path / "events.jsonl"
    report_dir = tmp_path / "reports"
    _write_env(
        env_path,
        {
            "RUNTIME_PROFILE": "staging",
            "KIWOOM_MODE": "mock",
            "APPROVAL_MODE": "manual",
            "ALLOW_REAL_EXECUTION": "false",
        },
    )
    events.write_text("", encoding="utf-8")

    calls: list[str] = []

    def fake_run_subprocess(*, step_id, command, cwd, env=None, timeout_sec=1800):  # type: ignore[no-untyped-def]
        calls.append(str(step_id))
        return {
            "step_id": step_id,
            "command": list(command),
            "cwd": str(cwd),
            "rc": 3,
            "ok": False,
            "stdout_tail": "",
            "stderr_tail": "forced failure",
            "error": "forced",
            "duration_sec": 0.001,
        }

    monkeypatch.setattr(mod, "_run_subprocess", fake_run_subprocess)

    rc = mod.main(
        [
            "--phase",
            "preopen",
            "--day",
            "2026-03-09",
            "--env-path",
            str(env_path),
            "--report-dir",
            str(report_dir),
            "--event-log-path",
            str(events),
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 3
    assert out["ok"] is False
    assert out["phase_result"]["failure_reason"] == "m30_final_signoff_failed"
    assert calls == ["preopen.m30_final_signoff"]


def test_session_aborts_when_market_closed(tmp_path: Path, capsys):
    env_path = tmp_path / ".env"
    events = tmp_path / "events.jsonl"
    report_dir = tmp_path / "reports"
    _write_env(
        env_path,
        {
            "RUNTIME_PROFILE": "staging",
            "KIWOOM_MODE": "mock",
            "APPROVAL_MODE": "manual",
            "ALLOW_REAL_EXECUTION": "false",
        },
    )
    events.write_text("", encoding="utf-8")

    rc = mod.main(
        [
            "--phase",
            "session",
            "--day",
            "2026-03-09",
            "--env-path",
            str(env_path),
            "--report-dir",
            str(report_dir),
            "--event-log-path",
            str(events),
            "--now-kst",
            "2026-03-08T10:00:00+09:00",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 3
    assert out["ok"] is False
    assert str(out["phase_result"]["failure_reason"]).startswith("market_closed:")


def test_closeout_runs_steps_in_order(tmp_path: Path, capsys, monkeypatch):
    env_path = tmp_path / ".env"
    events = tmp_path / "events.jsonl"
    report_dir = tmp_path / "reports"
    _write_env(
        env_path,
        {
            "RUNTIME_PROFILE": "staging",
            "KIWOOM_MODE": "mock",
            "APPROVAL_MODE": "manual",
            "ALLOW_REAL_EXECUTION": "false",
        },
    )
    events.write_text("", encoding="utf-8")

    calls: list[str] = []

    def fake_run_subprocess(*, step_id, command, cwd, env=None, timeout_sec=1800):  # type: ignore[no-untyped-def]
        calls.append(str(step_id))
        return {
            "step_id": step_id,
            "command": list(command),
            "cwd": str(cwd),
            "rc": 0,
            "ok": True,
            "stdout_tail": "{}",
            "stderr_tail": "",
            "error": "",
            "duration_sec": 0.001,
        }

    monkeypatch.setattr(mod, "_run_subprocess", fake_run_subprocess)

    rc = mod.main(
        [
            "--phase",
            "closeout",
            "--day",
            "2026-03-09",
            "--env-path",
            str(env_path),
            "--report-dir",
            str(report_dir),
            "--event-log-path",
            str(events),
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["ok"] is True
    assert calls == [
        "closeout.m31_slo_incident",
        "closeout.metrics",
        "closeout.operator_summary",
        "closeout.decision_story",
        "closeout.run_cards",
        "closeout.daily",
        "closeout.reporter_analysis",
        "closeout.live_execution_bundles",
        "closeout.report_inventory",
    ]


def test_session_success_starts_background_loop(tmp_path: Path, capsys, monkeypatch):
    env_path = tmp_path / ".env"
    events = tmp_path / "events.jsonl"
    report_dir = tmp_path / "reports"
    _write_env(
        env_path,
        {
            "RUNTIME_PROFILE": "staging",
            "KIWOOM_MODE": "mock",
            "APPROVAL_MODE": "manual",
            "ALLOW_REAL_EXECUTION": "false",
        },
    )
    events.write_text("", encoding="utf-8")

    def fake_start(*, command, env, stdout_path, stderr_path):  # type: ignore[no-untyped-def]
        return {
            "step_id": "session.live_loop",
            "command": list(command),
            "mode": "background",
            "rc": 0,
            "ok": True,
            "pid": 12345,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "stderr_tail": "",
            "error": "",
            "duration_sec": 0.02,
        }

    monkeypatch.setattr(mod, "_start_live_loop_background", fake_start)

    rc = mod.main(
        [
            "--phase",
            "session",
            "--day",
            "2026-03-10",
            "--env-path",
            str(env_path),
            "--report-dir",
            str(report_dir),
            "--event-log-path",
            str(events),
            "--now-kst",
            "2026-03-10T10:00:00+09:00",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["ok"] is True
    step = (out["phase_result"]["steps"] or [])[0]
    assert int(step["pid"]) == 12345


def test_session_offhours_probe_mode_when_enabled(tmp_path: Path, capsys, monkeypatch):
    env_path = tmp_path / ".env"
    events = tmp_path / "events.jsonl"
    report_dir = tmp_path / "reports"
    _write_env(
        env_path,
        {
            "RUNTIME_PROFILE": "staging",
            "KIWOOM_MODE": "mock",
            "APPROVAL_MODE": "manual",
            "ALLOW_REAL_EXECUTION": "false",
        },
    )
    events.write_text("", encoding="utf-8")

    def fake_run_subprocess(*, step_id, command, cwd, env=None, timeout_sec=1800):  # type: ignore[no-untyped-def]
        if str(step_id) != "session.offhours_probe":
            raise AssertionError(f"unexpected step_id={step_id}")
        return {
            "step_id": step_id,
            "command": list(command),
            "cwd": str(cwd),
            "rc": 0,
            "ok": True,
            "stdout_tail": '{"ok": true, "decision": {"decision": "approve"}}',
            "stderr_tail": "",
            "error": "",
            "duration_sec": 0.01,
        }

    monkeypatch.setattr(mod, "_run_subprocess", fake_run_subprocess)

    rc = mod.main(
        [
            "--phase",
            "session",
            "--day",
            "2026-03-09",
            "--env-path",
            str(env_path),
            "--report-dir",
            str(report_dir),
            "--event-log-path",
            str(events),
            "--now-kst",
            "2026-03-08T10:00:00+09:00",
            "--allow-offhours-session-probe",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["ok"] is True
    assert out["phase_result"]["probe_mode"] == "offhours_session_probe"
    step = (out["phase_result"]["steps"] or [])[0]
    assert step["step_id"] == "session.offhours_probe"


def test_session_offhours_simulated_session_mode_when_enabled(tmp_path: Path, capsys, monkeypatch):
    env_path = tmp_path / ".env"
    events = tmp_path / "events.jsonl"
    state_path = tmp_path / "offhours_state.json"
    report_dir = tmp_path / "reports"
    _write_env(
        env_path,
        {
            "RUNTIME_PROFILE": "staging",
            "KIWOOM_MODE": "mock",
            "APPROVAL_MODE": "manual",
            "ALLOW_REAL_EXECUTION": "false",
        },
    )
    events.write_text("", encoding="utf-8")

    def fake_start(*, step_id, command, env, stdout_path, stderr_path):  # type: ignore[no-untyped-def]
        return {
            "step_id": step_id,
            "command": list(command),
            "mode": "background",
            "rc": 0,
            "ok": True,
            "pid": 56789,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "stderr_tail": "",
            "error": "",
            "duration_sec": 0.02,
        }

    monkeypatch.setattr(mod, "_start_background_command", fake_start)

    rc = mod.main(
        [
            "--phase",
            "session",
            "--day",
            "2026-03-09",
            "--env-path",
            str(env_path),
            "--report-dir",
            str(report_dir),
            "--event-log-path",
            str(events),
            "--state-path",
            str(state_path),
            "--now-kst",
            "2026-03-08T10:00:00+09:00",
            "--allow-offhours-simulated-session",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["ok"] is True
    assert out["phase_result"]["probe_mode"] == "offhours_simulated_session"
    step = (out["phase_result"]["steps"] or [])[0]
    assert step["step_id"] == "session.offhours_validation_loop"
    cmd = [str(x) for x in step["command"]]
    assert "--event-log-path" in cmd
    assert str(events) in cmd
    assert "--state-path" in cmd
    assert str(state_path) in cmd
