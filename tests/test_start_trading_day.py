from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import scripts.start_trading_day as mod


def test_opening_macro_collector_is_part_of_the_observation_stack() -> None:
    config = mod.SHADOW_LOOPS["opening_macro_snapshots"]
    assert config["pattern"] == "run_opening_macro_snapshot_collector.py"
    assert all("OrderIntent" not in value for value in config["cmd"])


# --- 2026-09-05 PRE-STEP5C cleanup follow-up: Q10 Index observation
# collector wired into the trading-day shadow-loop lifecycle -----------
#
# The prior turn's report marked "Q10 09:30/10:00/CLOSE CAPTURE: PASS" at
# unit/integration test level only -- the collector was never registered
# in SHADOW_LOOPS, so start_trading_day.py's start/watchdog cycle would
# never actually launch it as a live subprocess. T1 below closes that gap
# and additionally traces the dispatch all the way to the actual
# subprocess.Popen call (not just "the dict entry exists"), matching how
# every other shadow loop is proven wired.


def test_q10_index_collector_is_part_of_the_observation_stack() -> None:
    """T1: trading-day startup configuration includes the Q10 Index
    observation collector, following the same contract as every other
    shadow loop (pattern used for process matching, script path in cmd,
    no OrderIntent/strategy coupling)."""
    config = mod.SHADOW_LOOPS["q10_index_observation"]
    assert config["pattern"] == "run_q10_index_observation_collector.py"
    assert "scripts/run_q10_index_observation_collector.py" in config["cmd"]
    assert "--loop" in config["cmd"]
    assert all("OrderIntent" not in value for value in config["cmd"])


def test_ensure_shadow_loops_actually_launches_q10_collector_subprocess(tmp_path: Path, monkeypatch) -> None:
    """Traces the dispatch beyond the SHADOW_LOOPS dict entry: when no
    matching process is currently running for today, `_ensure_shadow_loops`
    must issue a real `subprocess.Popen` call for the Q10 collector, with
    `--day <day>` appended exactly like every other shadow loop."""
    day = "2026-09-05"
    monkeypatch.setattr(mod, "_powershell_processes", lambda patterns: [])
    monkeypatch.setattr(mod, "RUNTIME_DIR", tmp_path / "runtime")

    launched: list[list[str]] = []

    class _FakeProcess:
        pid = 4242

    def _fake_popen(cmd, **kwargs):
        launched.append(list(cmd))
        return _FakeProcess()

    monkeypatch.setattr(mod.subprocess, "Popen", _fake_popen)

    result = mod._ensure_shadow_loops(day, replace_stale=False)

    q10_launch = next(
        (cmd for cmd in launched if any("run_q10_index_observation_collector.py" in part for part in cmd)),
        None,
    )
    assert q10_launch is not None, f"Q10 collector was never dispatched via subprocess.Popen: {launched}"
    assert "--loop" in q10_launch
    assert "--day" in q10_launch
    assert q10_launch[q10_launch.index("--day") + 1] == day
    assert "q10_index_observation" in (result.get("running") or {})


def test_has_day_arg_accepts_space_and_equals_forms() -> None:
    assert mod._has_day_arg("python scripts/run_baseline_samsung_hynix.py --day 2026-06-30", "2026-06-30")
    assert mod._has_day_arg("python scripts/run_baseline_samsung_hynix.py --day=2026-06-30", "2026-06-30")
    assert not mod._has_day_arg("python scripts/run_baseline_samsung_hynix.py --day 2026-06-26", "2026-06-30")


def test_session_stack_window_is_limited_to_regular_start_window() -> None:
    assert mod._session_stack_window_open(datetime(2026, 6, 30, 8, 40, tzinfo=mod.KST))
    assert mod._session_stack_window_open(datetime(2026, 6, 30, 15, 30, tzinfo=mod.KST))
    assert not mod._session_stack_window_open(datetime(2026, 6, 30, 8, 39, tzinfo=mod.KST))
    assert not mod._session_stack_window_open(datetime(2026, 6, 30, 15, 31, tzinfo=mod.KST))


def test_event_health_blocks_repeated_llm_failures_without_scanner(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    log = root / "data" / "logs" / "events.jsonl"
    log.parent.mkdir(parents=True)
    now = datetime.now(mod.KST).replace(microsecond=0)
    rows = []
    for i in range(3):
        rows.append({
            "ts_kst": now.isoformat(),
            "stage": "strategist_llm",
            "event_name": "strategist_llm.result",
            "payload": {
                "ok": False,
                "blocked_reason": "strategist_llm_failed",
            },
        })
        rows.append({
            "ts_kst": now.isoformat(),
            "stage": "commander_router",
            "event_name": "commander_router.fast_path",
            "payload": {"reason": "strategist_llm_failed"},
        })
    log.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", root)

    result = mod._event_health(now.date().isoformat(), lookback_min=10)

    assert result["status"] == "BLOCKED"
    assert result["blockers"][0]["code"] == "strategist_llm_failure_blocks_scanner"


def test_event_health_passes_when_scanner_events_exist(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    log = root / "data" / "logs" / "events.jsonl"
    log.parent.mkdir(parents=True)
    now = datetime.now(mod.KST).replace(microsecond=0)
    rows = [
        {
            "ts_kst": now.isoformat(),
            "stage": "strategist_llm",
            "event_name": "strategist_llm.result",
            "payload": {"ok": False, "blocked_reason": "strategist_llm_failed"},
        },
        {
            "ts_kst": now.isoformat(),
            "stage": "scanner",
            "event_name": "scanner.summary",
            "payload": {},
        },
    ]
    log.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", root)

    result = mod._event_health(now.date().isoformat(), lookback_min=10)

    assert result["status"] == "PASS"
    assert result["counts"]["scanner_events"] == 1


def test_event_health_counts_q9_monitor_decision_trace(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    log = root / "data" / "logs" / "events.jsonl"
    log.parent.mkdir(parents=True)
    now = datetime.now(mod.KST).replace(microsecond=0)
    row = {
        "ts_kst": now.isoformat(),
        "stage": "decision_trace",
        "event_name": "decision_trace.entry_exit_decision",
        "payload": {"agent": "monitor", "payload": {"entry_evaluated": True}},
    }
    log.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", root)

    result = mod._event_health(now.date().isoformat(), lookback_min=10)

    assert result["counts"]["q9_scanner_selection"] == 1


def test_watchdog_recovers_stale_runtime_and_writes_history(tmp_path: Path, monkeypatch) -> None:
    status_dir = tmp_path / "reports" / "runtime" / "trading_day_status"
    stale = {
        "running": True,
        "heartbeat_age_seconds": 360,
        "process_tree": {"logical_session_count": 1, "tree_state": "NORMAL_PROCESS_TREE"},
    }
    healthy = {
        "running": True,
        "heartbeat_age_seconds": 2,
        "process_tree": {"logical_session_count": 1, "tree_state": "NORMAL_PROCESS_TREE"},
    }
    live_rows = iter((stale, healthy))
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "STATUS_DIR", status_dir)
    monkeypatch.setattr(mod, "_session_stack_window_open", lambda *_: True)
    monkeypatch.setattr(mod, "_ensure_shadow_loops", lambda *_args, **_kwargs: {"running": {}})
    monkeypatch.setattr(mod, "_live_status", lambda: next(live_rows))
    monkeypatch.setattr(mod, "_start_live", lambda: {"started": True})
    monkeypatch.setattr(mod, "_event_health", lambda *_args, **_kwargs: {"available": True, "status": "PASS", "blockers": []})
    monkeypatch.setattr(mod, "_q10_closeout_recovery", lambda *_args, **_kwargs: {"availability": "MISSING"})

    result = mod.run_watchdog("2026-08-27", lookback_min=10)

    assert result["ok"] is True
    assert result["supervisor"]["decision"] == "RECOVER"
    assert result["supervisor"]["last_action"] == "RECOVERED"
    assert result["supervisor"]["restart_count"] == 1
    assert list((status_dir / "history" / "2026-08-27").glob("*_watchdog.json"))


# --- 2026-09-05 PRE-STEP5C CLEANUP FIX 2, item 7: watchdog/closeout
# lifecycle -- the Q10 collector's bounded CLOSE closeout re-query can
# still be legitimately pending a few minutes after the main session
# window closes at 15:30 (_session_stack_window_open), which is also when
# the watchdog stops trying to recover crashed shadow loops. These tests
# prove _q10_closeout_recovery runs in-process, independent of whether the
# collector subprocess itself is alive, in both the normal and the
# offhours (post-15:30) watchdog branches.


def test_t1_t2_q10_closeout_recovery_recovers_a_crashed_collectors_pending_close(tmp_path: Path, monkeypatch) -> None:
    """T1/T2: simulate the Q10 collector subprocess having crashed at
    15:32 -- CLOSE's primary attempt already failed (MISSING, not yet
    closeout-requeried) and is sitting on disk with no live process left
    to run the closeout re-query. Calling _q10_closeout_recovery directly
    (as run_watchdog now does) must recover it, in-process, with no
    dependency on that subprocess."""
    from libs.market.q10_index_observation_collector import capture_slot

    root = tmp_path
    monkeypatch.setattr(mod, "ROOT", root)
    day = "2026-08-27"  # any past day -- real "now" is always past its close+grace
    collector_root = root / "data" / "logs" / "q10_index_observations"
    capture_slot(
        day=day, slot="15:30", root=collector_root,
        now_fn=lambda: datetime(2026, 8, 27, 15, 30, tzinfo=mod.KST),
        capture=lambda **k: {"status": "unavailable", "source": "kiwoom.ka20009", "indices": {}, "error": "boom"},
    )
    assert (collector_root / day / "capture_manifest.json").exists()

    def _ok_capture(**kwargs):
        return {"status": "ok", "source": "kiwoom.ka20009", "indices": {"KOSPI": {"current": 3050.0}, "KOSDAQ": {"current": 810.0}}}

    result = mod._q10_closeout_recovery(day, _capture=_ok_capture, _now_fn=lambda: datetime(2026, 8, 27, 15, 36, tzinfo=mod.KST))

    assert result.get("availability") == "CLOSE_UNVERIFIED"
    assert result.get("closeout_requeried") is True


def test_t3_offhours_watchdog_branch_still_runs_q10_closeout_recovery(tmp_path: Path, monkeypatch) -> None:
    """T3: even when _session_stack_window_open() is False (past 15:30,
    the normal watchdog no-op path), run_watchdog must still perform the
    Q10 closeout recovery."""
    status_dir = tmp_path / "reports" / "runtime" / "trading_day_status"
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "STATUS_DIR", status_dir)
    monkeypatch.setattr(mod, "_session_stack_window_open", lambda *_: False)
    monkeypatch.setattr(mod, "_live_status", lambda: {"running": True})
    sentinel = {"availability": "AVAILABLE", "closeout_requeried": True}
    monkeypatch.setattr(mod, "_q10_closeout_recovery", lambda *_args, **_kwargs: dict(sentinel))

    result = mod.run_watchdog("2026-08-27", lookback_min=10)

    assert result["offhours_noop"] is True
    assert result["q10_closeout_recovery"] == sentinel


def test_t4_repeated_closeout_recovery_calls_issue_no_further_live_capture(tmp_path: Path, monkeypatch) -> None:
    """T4: once CLOSE has been recovered (closeout_requeried=True), further
    calls to _q10_closeout_recovery (e.g. on the next watchdog cycle) must
    not trigger another live capture -- the bounded one-shot logical
    closeout attempt has already been used."""
    from libs.market.q10_index_observation_collector import capture_slot

    root = tmp_path
    monkeypatch.setattr(mod, "ROOT", root)
    day = "2026-08-27"
    collector_root = root / "data" / "logs" / "q10_index_observations"
    capture_slot(
        day=day, slot="15:30", root=collector_root,
        now_fn=lambda: datetime(2026, 8, 27, 15, 30, tzinfo=mod.KST),
        capture=lambda **k: {"status": "unavailable", "source": "kiwoom.ka20009", "indices": {}, "error": "boom"},
    )
    calls: list[int] = []

    def _counting_capture(**kwargs):
        calls.append(1)
        return {"status": "ok", "source": "kiwoom.ka20009", "indices": {"KOSPI": {"current": 3050.0}, "KOSDAQ": {"current": 810.0}}}

    mod._q10_closeout_recovery(day, _capture=_counting_capture, _now_fn=lambda: datetime(2026, 8, 27, 15, 36, tzinfo=mod.KST))
    assert len(calls) == 1

    for _ in range(3):
        mod._q10_closeout_recovery(day, _capture=_counting_capture, _now_fn=lambda: datetime(2026, 8, 27, 15, 36, tzinfo=mod.KST))
    assert len(calls) == 1
