from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from libs.runtime.market_hours import MarketHours, now_kst
from libs.runtime.mock_exam_day.closeout_phase import phase_template
from libs.runtime.mock_exam_day.common import parse_kst_datetime, read_env_file
from libs.runtime.runtime_output_helpers import parse_stdout_json


StepRunner = Callable[..., Dict[str, Any]]
CommonStep = Callable[[Dict[str, Any]], Dict[str, Any]]
RuntimeModeChecker = Callable[[Dict[str, str]], Dict[str, Any]]


def run_session_phase(
    args: Any,
    common: Dict[str, Any],
    *,
    root: Path,
    phase_name: str,
    run_subprocess: StepRunner,
    start_live_loop_background: StepRunner,
    start_background_command: StepRunner,
    existing_live_loop_step: CommonStep,
    runtime_mode_checks: RuntimeModeChecker,
    dt_now: Optional[Any] = None,
) -> Dict[str, Any]:
    out = phase_template(phase_name)
    env_obj = read_env_file(Path(common["env_path"]))
    mode = runtime_mode_checks(env_obj)
    out["runtime_mode"] = mode
    if not bool(mode.get("ok")):
        out["failure_reason"] = "runtime_mode_policy_failed"
        return out

    dt_override = parse_kst_datetime(str(args.now_kst or "")) if args.now_kst else None
    dt = dt_override or dt_now or now_kst()
    if not bool(MarketHours().is_open(dt)):
        return _run_offhours_session(
            args,
            common,
            root=root,
            out=out,
            dt=dt,
            run_subprocess=run_subprocess,
            start_background_command=start_background_command,
        )

    existing_step = existing_live_loop_step(common)
    if existing_step:
        out["steps"].append(existing_step)
        out["ok"] = True
        out["reuse_existing"] = True
        return out

    cmd = [
        str(common["python_path"]),
        str(root / "scripts" / "run_session.py"),
        "--mode",
        "mock",
        "--phase",
        "intraday",
        "--env-path",
        str(common["env_path"]),
        "--tick-pipeline",
        "integrated_chain",
        "--sleep-sec",
        str(int(args.sleep_sec)),
        "--lock-path",
        str(common["lock_path"]),
        "--lock-stale-sec",
        str(int(common["lock_stale_sec"])),
    ]

    proc_env = os.environ.copy()
    proc_env["ENV_PATH"] = str(common["env_path"])
    step = start_live_loop_background(
        command=cmd,
        env=proc_env,
        stdout_path=Path(common["session_stdout_path"]),
        stderr_path=Path(common["session_stderr_path"]),
    )
    out["steps"].append(step)
    out["ok"] = bool(step.get("ok"))
    if not out["ok"]:
        out["failure_reason"] = str(step.get("error") or "session_launch_failed")
    return out


def _run_offhours_session(
    args: Any,
    common: Dict[str, Any],
    *,
    root: Path,
    out: Dict[str, Any],
    dt: Any,
    run_subprocess: StepRunner,
    start_background_command: StepRunner,
) -> Dict[str, Any]:
    if bool(getattr(args, "allow_offhours_simulated_session", False)):
        cmd = [
            str(common["python_path"]),
            str(root / "scripts" / "run_session.py"),
            "--mode",
            "mock",
            "--phase",
            "intraday",
            "--simulated",
            "--env-path",
            str(common["env_path"]),
            "--event-log-path",
            str(common["event_log_path"]),
            "--sleep-sec",
            str(int(args.sleep_sec)),
            "--lock-path",
            str(common["lock_path"]),
            "--lock-stale-sec",
            str(int(common["lock_stale_sec"])),
        ]
        if common.get("state_path"):
            cmd += ["--state-path", str(common["state_path"])]
        probe_symbol = str(getattr(args, "probe_symbol", "") or os.getenv("SYMBOL", "005930")).strip() or "005930"
        if probe_symbol:
            cmd += ["--symbol", probe_symbol]
        proc_env = os.environ.copy()
        proc_env["ENV_PATH"] = str(common["env_path"])
        step = start_background_command(
            step_id="session.offhours_validation_loop",
            command=cmd,
            env=proc_env,
            stdout_path=Path(common["session_stdout_path"]),
            stderr_path=Path(common["session_stderr_path"]),
        )
        out["steps"].append(step)
        out["probe_mode"] = "offhours_simulated_session"
        out["ok"] = bool(step.get("ok"))
        if not out["ok"]:
            out["failure_reason"] = str(step.get("error") or "offhours_validation_launch_failed")
        return out

    if not bool(getattr(args, "allow_offhours_session_probe", False)):
        out["ok"] = True
        out["skipped"] = True
        out["skip_reason"] = "market_closed"
        out["market_closed_at"] = dt.isoformat()
        return out

    probe_symbol = str(getattr(args, "probe_symbol", "") or os.getenv("SYMBOL", "005930")).strip() or "005930"
    probe_price = float(getattr(args, "probe_price", 70000.0))
    probe_cash = float(getattr(args, "probe_cash", 2000000.0))
    step = run_subprocess(
        step_id="session.offhours_probe",
        command=[
            str(common["python_path"]),
            str(root / "scripts" / "run_session.py"),
            "--mode",
            "mock",
            "--phase",
            "intraday",
            "--probe",
            "--probe-symbol",
            probe_symbol,
            "--probe-price",
            str(probe_price),
            "--probe-cash",
            str(probe_cash),
            "--json",
        ],
        cwd=root,
        timeout_sec=int(common["timeout_sec"]),
    )
    out["steps"].append(step)
    probe_obj = parse_stdout_json(str(step.get("stdout_tail") or ""))
    out["probe_mode"] = "offhours_session_probe"
    out["probe_result"] = probe_obj
    out["ok"] = bool(step.get("ok")) and bool(probe_obj.get("ok"))
    if not out["ok"]:
        out["failure_reason"] = "offhours_probe_failed"
    return out
