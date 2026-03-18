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
    state_path = tmp_path / "state.json"
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

    monkeypatch.setattr(
        mod,
        "_stop_live_loop_processes",
        lambda common: {
            "step_id": "closeout.stop_session_loop",
            "mode": "process_cleanup",
            "rc": 0,
            "ok": True,
            "stopped_pids": [],
            "stopped_total": 0,
            "stderr_tail": "",
            "error": "",
            "duration_sec": 0.001,
        },
    )
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
            "--state-path",
            str(state_path),
            "--event-log-path",
            str(events),
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["ok"] is True
    steps = out["phase_result"]["steps"]
    assert steps[0]["step_id"] == "closeout.stop_session_loop"
    assert steps[1]["step_id"] == "closeout.backup_liquidation"
    assert steps[1]["mode"] == "noop_already_flat"
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


def test_closeout_backup_liquidation_flattens_mock_positions(tmp_path: Path, capsys, monkeypatch):
    env_path = tmp_path / ".env"
    events = tmp_path / "events.jsonl"
    report_dir = tmp_path / "reports"
    state_path = tmp_path / "state.json"
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
    state_path.write_text(
        json.dumps(
            {
                "open_positions": 1,
                "mock_positions": [{"symbol": "000660", "qty": 2, "avg_price": 1005000.0}],
                "position_peak_price": {"000660": 1011000.0},
                "position_strategy_context": {"000660": {"playbook": "defensive"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mod,
        "_stop_live_loop_processes",
        lambda common: {
            "step_id": "closeout.stop_session_loop",
            "mode": "process_cleanup",
            "rc": 0,
            "ok": True,
            "stopped_pids": [],
            "stopped_total": 0,
            "stderr_tail": "",
            "error": "",
            "duration_sec": 0.001,
        },
    )
    monkeypatch.setattr(
        mod,
        "_run_subprocess",
        lambda **kwargs: {
            "step_id": str(kwargs["step_id"]),
            "command": list(kwargs["command"]),
            "cwd": str(kwargs["cwd"]),
            "rc": 0,
            "ok": True,
            "stdout_tail": "{}",
            "stderr_tail": "",
            "error": "",
            "duration_sec": 0.001,
        },
    )

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
            "--state-path",
            str(state_path),
            "--event-log-path",
            str(events),
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["ok"] is True
    backup_step = out["phase_result"]["steps"][1]
    assert backup_step["step_id"] == "closeout.backup_liquidation"
    assert backup_step["mode"] == "mock_backup_flatten"
    assert backup_step["positions_before"] == 1
    assert backup_step["qty_total_before"] == 2
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["open_positions"] == 0
    assert saved["mock_positions"] == []
    assert "position_peak_price" not in saved
    assert "position_strategy_context" not in saved
    assert saved["closeout_backup_liquidation"]["applied"] is True


def test_closeout_backup_liquidation_reports_non_mock_positions(tmp_path: Path, capsys, monkeypatch):
    env_path = tmp_path / ".env"
    events = tmp_path / "events.jsonl"
    report_dir = tmp_path / "reports"
    state_path = tmp_path / "state.json"
    _write_env(
        env_path,
        {
            "RUNTIME_PROFILE": "staging",
            "KIWOOM_MODE": "real",
            "APPROVAL_MODE": "manual",
            "ALLOW_REAL_EXECUTION": "false",
        },
    )
    events.write_text("", encoding="utf-8")
    state_path.write_text(
        json.dumps(
            {
                "open_positions": 1,
                "mock_positions": [{"symbol": "005930", "qty": 1, "avg_price": 70000.0}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mod,
        "_stop_live_loop_processes",
        lambda common: {
            "step_id": "closeout.stop_session_loop",
            "mode": "process_cleanup",
            "rc": 0,
            "ok": True,
            "stopped_pids": [],
            "stopped_total": 0,
            "stderr_tail": "",
            "error": "",
            "duration_sec": 0.001,
        },
    )
    monkeypatch.setattr(
        mod,
        "_run_subprocess",
        lambda **kwargs: {
            "step_id": str(kwargs["step_id"]),
            "command": list(kwargs["command"]),
            "cwd": str(kwargs["cwd"]),
            "rc": 0,
            "ok": True,
            "stdout_tail": "{}",
            "stderr_tail": "",
            "error": "",
            "duration_sec": 0.001,
        },
    )

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
            "--state-path",
            str(state_path),
            "--event-log-path",
            str(events),
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 3
    assert out["ok"] is False
    backup_step = out["phase_result"]["steps"][1]
    assert backup_step["step_id"] == "closeout.backup_liquidation"
    assert backup_step["mode"] == "non_mock_requires_manual_flatten"
    assert backup_step["ok"] is False
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["open_positions"] == 1
    assert len(saved["mock_positions"]) == 1


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
    monkeypatch.setattr(mod, "_existing_live_loop_step", lambda common: {})

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
    cmd = [str(x) for x in step["command"]]
    assert "--env-path" in cmd
    assert str(env_path) in cmd
    assert "--tick-pipeline" in cmd
    assert "integrated_chain" in cmd


def test_session_reuses_existing_live_loop_when_present(tmp_path: Path, capsys, monkeypatch):
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

    monkeypatch.setattr(
        mod,
        "_existing_live_loop_step",
        lambda common: {
            "step_id": "session.live_loop_existing",
            "mode": "existing",
            "rc": 0,
            "ok": True,
            "pid": 45678,
            "command_line": "python -m scripts.run_m13_live_loop --tick-pipeline integrated_chain",
            "duration_sec": 0.0,
        },
    )

    def fail_start(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("background start should not run when existing loop is alive")

    monkeypatch.setattr(mod, "_start_live_loop_background", fail_start)

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
    assert out["phase_result"]["reuse_existing"] is True
    step = (out["phase_result"]["steps"] or [])[0]
    assert step["step_id"] == "session.live_loop_existing"
    assert int(step["pid"]) == 45678


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
