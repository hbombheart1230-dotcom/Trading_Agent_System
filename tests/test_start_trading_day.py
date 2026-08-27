from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import scripts.start_trading_day as mod


def test_opening_macro_collector_is_part_of_the_observation_stack() -> None:
    config = mod.SHADOW_LOOPS["opening_macro_snapshots"]
    assert config["pattern"] == "run_opening_macro_snapshot_collector.py"
    assert all("OrderIntent" not in value for value in config["cmd"])


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

    result = mod.run_watchdog("2026-08-27", lookback_min=10)

    assert result["ok"] is True
    assert result["supervisor"]["decision"] == "RECOVER"
    assert result["supervisor"]["last_action"] == "RECOVERED"
    assert result["supervisor"]["restart_count"] == 1
    assert list((status_dir / "history" / "2026-08-27").glob("*_watchdog.json"))
