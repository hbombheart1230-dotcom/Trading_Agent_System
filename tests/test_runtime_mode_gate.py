"""P1.3-R4 (2026-10-02): TRADING_RUNTIME_MODE gates ONLY the Host live-loop
launch; every collector/shadow loop the same scheduled tasks maintain is
unaffected.

Context: TradingAgent-MockExamDay-Session (09:00) and ...-SessionWatchdog
(09:05, every 5 min to 15:25) run scripts/start_trading_day.py, which starts
the Host M13 live loop (via scripts/restart_live_session.py) AND the Q10/Q11/
Q12, opportunity-engine and macro collectors that feed the Daily UEF
freshness contracts. Disabling the whole tasks would also stop the
collectors, so the mode is an explicit configuration switch instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import scripts.restart_live_session as restart_mod
import scripts.start_trading_day as mod
from libs.runtime.runtime_mode import (
    SKIP_REASON_DOCKER,
    SKIP_REASON_INVALID,
    host_live_start_decision,
    resolve_trading_runtime_mode,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADING_RUNTIME_MODE", raising=False)
    monkeypatch.setattr(mod, "ROOT", tmp_path)  # so the repo's real .env is never read
    monkeypatch.setattr(mod, "STATUS_DIR", tmp_path / "status")
    monkeypatch.setattr(mod, "_session_stack_window_open", lambda *_: True)
    monkeypatch.setattr(mod, "_supervisor_state", lambda day: {})
    monkeypatch.setattr(mod, "_event_health", lambda *_a, **_k: {"available": True, "status": "PASS", "blockers": []})
    monkeypatch.setattr(mod, "_q10_closeout_recovery", lambda *_a, **_k: {"availability": "MISSING"})


DEAD_LIVE = {"running": False, "process_tree": {}}
SHADOW_OK = {"running": {"q10_samsung_hynix": {"current_day_count": 1, "stale_count": 0}}}


class _Calls:
    def __init__(self):
        self.live_start = 0
        self.shadow = 0


def _wire(monkeypatch, calls: _Calls):
    def _start_live():
        calls.live_start += 1
        return {"started": True}

    def _shadow(*_a, **_k):
        calls.shadow += 1
        return SHADOW_OK

    monkeypatch.setattr(mod, "_start_live", _start_live)
    monkeypatch.setattr(mod, "_ensure_shadow_loops", _shadow)
    monkeypatch.setattr(mod, "_live_status", lambda: dict(DEAD_LIVE))


# ----------------------------------------------------------------- config --


def test_mode_resolution_default_env_file_and_precedence(tmp_path):
    env_file = tmp_path / ".env"
    assert resolve_trading_runtime_mode(env={}, env_file=env_file) == "host"  # default, no file
    env_file.write_text("OTHER=1\nTRADING_RUNTIME_MODE=docker  # comment\n", encoding="utf-8")
    assert resolve_trading_runtime_mode(env={}, env_file=env_file) == "docker"
    env_file.write_text('TRADING_RUNTIME_MODE="Docker"\n', encoding="utf-8")
    assert resolve_trading_runtime_mode(env={}, env_file=env_file) == "docker"
    # process environment wins over the file
    assert resolve_trading_runtime_mode(env={"TRADING_RUNTIME_MODE": "host"}, env_file=env_file) == "host"
    # a typo fails closed for the Host launch only
    allowed, mode, reason = host_live_start_decision(env={"TRADING_RUNTIME_MODE": "dokcer"})
    assert (allowed, reason) == (False, SKIP_REASON_INVALID)
    assert mode.startswith("invalid:")


# ------------------------------------------------------------------ A: host --


def test_a_host_mode_run_start_launches_live_unchanged(monkeypatch):
    calls = _Calls()
    _wire(monkeypatch, calls)
    payload = mod.run_start("2026-10-05")
    assert calls.live_start == 1
    assert payload["runtime_mode"] == "host"
    assert {"code": "live_session_not_running"} in payload["blockers"]  # unchanged host semantics


def test_a_host_mode_watchdog_still_recovers_live(monkeypatch):
    calls = _Calls()
    _wire(monkeypatch, calls)
    monkeypatch.setattr(mod, "evaluate_supervisor", lambda live, state, now: type("D", (), {"restart_allowed": True, "action": "RESTART", "reason": "dead"})())
    monkeypatch.setattr(mod, "record_watchdog_result", lambda state, *_a, **_k: state)
    monkeypatch.setattr(mod, "write_supervisor_state", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "_supervisor_state_path", lambda: Path("unused"))
    mod.run_watchdog("2026-10-05", lookback_min=10)
    assert calls.live_start == 1


# ----------------------------------------------------------------- B: docker --


def test_b_docker_mode_skips_host_live_start_and_logs_reason(monkeypatch, capsys):
    monkeypatch.setenv("TRADING_RUNTIME_MODE", "docker")
    calls = _Calls()
    _wire(monkeypatch, calls)
    payload = mod.run_start("2026-10-05")
    assert calls.live_start == 0
    assert payload["runtime_mode"] == "docker"
    assert payload["live_start"]["reason"] == SKIP_REASON_DOCKER
    assert payload["start_reason"] == SKIP_REASON_DOCKER
    assert SKIP_REASON_DOCKER in capsys.readouterr().out
    # the Host live loop's absence is intentional, so it is not a blocker
    assert {"code": "live_session_not_running"} not in payload["blockers"]


def test_b_invalid_mode_also_skips_host_live_start(monkeypatch):
    monkeypatch.setenv("TRADING_RUNTIME_MODE", "typo")
    calls = _Calls()
    _wire(monkeypatch, calls)
    payload = mod.run_start("2026-10-05")
    assert calls.live_start == 0
    assert payload["live_start"]["reason"] == SKIP_REASON_INVALID


def test_b_start_live_itself_refuses_in_docker_mode(monkeypatch):
    monkeypatch.setenv("TRADING_RUNTIME_MODE", "docker")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not launch")))
    result = mod._start_live()
    assert result["skipped"] is True and result["reason"] == SKIP_REASON_DOCKER


def test_b_restart_live_session_cli_does_nothing_in_docker_mode(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TRADING_RUNTIME_MODE", "docker")
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("docker mode must not stop/start/touch the lock"))
    monkeypatch.setattr(restart_mod, "_stop_existing_session", boom)
    monkeypatch.setattr(restart_mod, "_start_session", boom)
    assert restart_mod.main(["--json"]) == 0
    out = capsys.readouterr().out
    assert SKIP_REASON_DOCKER in out and '"skipped": true' in out


# ------------------------------------------------------ C: collectors continue --


def test_c_docker_mode_collectors_still_start(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_RUNTIME_MODE", "docker")
    launched = []

    class _FakeProc:
        pid = 4242

    monkeypatch.setattr(mod, "_powershell_processes", lambda patterns: [])
    monkeypatch.setattr(mod, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(mod.subprocess, "Popen", lambda cmd, **k: launched.append(list(cmd)) or _FakeProc())
    monkeypatch.setattr(mod, "_live_status", lambda: dict(DEAD_LIVE))
    monkeypatch.setattr(mod, "_start_live", lambda: (_ for _ in ()).throw(AssertionError("Host live must not start")))
    calls = _Calls()
    result = mod._ensure_shadow_loops("2026-10-05", replace_stale=True)
    scripts_launched = " ".join(" ".join(c) for c in launched)
    for name, spec in mod.SHADOW_LOOPS.items():
        assert spec["pattern"] in scripts_launched, f"collector {name} must still launch in docker mode"
    assert result


# --------------------------------------------------------- D: watchdog docker --


def test_d_docker_mode_watchdog_never_launches_or_touches_supervisor_state(monkeypatch):
    monkeypatch.setenv("TRADING_RUNTIME_MODE", "docker")
    calls = _Calls()
    _wire(monkeypatch, calls)
    forbidden = lambda *a, **k: (_ for _ in ()).throw(AssertionError("docker mode watchdog must make no Host live-recovery decision"))
    monkeypatch.setattr(mod, "evaluate_supervisor", forbidden)
    monkeypatch.setattr(mod, "record_watchdog_result", forbidden)
    monkeypatch.setattr(mod, "write_supervisor_state", forbidden)
    payload = mod.run_watchdog("2026-10-05", lookback_min=10)
    assert calls.live_start == 0
    assert calls.shadow == 1, "collectors/shadow loops are still maintained by the watchdog"
    assert payload["live_start"]["reason"] == SKIP_REASON_DOCKER
    assert payload["runtime_mode"] == "docker"
    assert {"code": "live_session_not_running"} not in payload["blockers"]


def test_d_docker_mode_watchdog_still_reports_a_dead_collector(monkeypatch):
    monkeypatch.setenv("TRADING_RUNTIME_MODE", "docker")
    calls = _Calls()
    _wire(monkeypatch, calls)
    monkeypatch.setattr(mod, "_ensure_shadow_loops", lambda *_a, **_k: {"running": {"q10_samsung_hynix": {"current_day_count": 0, "stale_count": 0}}})
    payload = mod.run_watchdog("2026-10-05", lookback_min=10)
    assert {"code": "q10_samsung_hynix_not_running_for_day"} in payload["blockers"]
    assert payload["ok"] is False


# --------------------------------------------------------- E: no dual-start --


def test_e_only_gated_code_can_launch_the_host_live_intraday_session():
    """Every executable launch of `run_session.py --mode live --phase
    intraday` in this repository must be inside the gated launcher. (Mock-
    exam-day launches use --mode mock; preopen/watch/closeout phases are
    not the mutation-capable loop.)"""
    hits = []
    for base in ("scripts", "libs", "graphs", "deploy", "apps"):
        for p in (ROOT / base).rglob("*"):
            if p.suffix.lower() not in (".py", ".bat", ".ps1", ".cmd") or "__pycache__" in p.parts:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            if "run_session.py" not in text:
                continue
            live = re.search(r'"--mode",\s*"live"', text) or re.search(r"--mode\s+live", text)
            intraday = re.search(r'"intraday"', text) or re.search(r"--phase\s+intraday", text)
            if live and intraday:
                hits.append(p.relative_to(ROOT).as_posix())
    assert hits == ["scripts/restart_live_session.py"], hits

    source = (ROOT / "scripts" / "restart_live_session.py").read_text(encoding="utf-8")
    gate = source.index("host_live_start_decision(")
    assert gate < source.index("stop = _stop_existing_session("), "gate must precede the stop/lock-removal step"
    assert gate < source.index("start = _start_session("), "gate must precede the launch"

    runner = (ROOT / "scripts" / "start_trading_day.py").read_text(encoding="utf-8")
    # both scheduled entrypoints decide via the explicit gate, never by inspecting Docker/PIDs
    assert runner.count("_host_live_gate()") >= 3


# ---------------------------------------------- F: UEF inputs unaffected --


def test_f_collector_set_is_identical_in_every_mode(monkeypatch):
    names_host = set(mod.SHADOW_LOOPS)
    monkeypatch.setenv("TRADING_RUNTIME_MODE", "docker")
    assert set(mod.SHADOW_LOOPS) == names_host
    for required in ("opening_macro_snapshots", "q10_samsung_hynix", "q11_opening_opportunity"):
        assert required in names_host
    # the mode switch only appears around the live launch in run_start / run_watchdog / _start_live
    source = Path(mod.__file__).read_text(encoding="utf-8")
    ensure = source[source.index("def _ensure_shadow_loops"):source.index("def _host_live_gate")]
    assert "runtime_mode" not in ensure and "host_live" not in ensure
