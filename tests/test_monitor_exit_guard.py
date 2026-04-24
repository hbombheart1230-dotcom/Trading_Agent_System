from __future__ import annotations

from libs.skills.dto import MinuteOHLCVDTO
from libs.skills.runner import SkillRunResult

from graphs.nodes.monitor_node import _extract_monitor_strategy_frame, monitor_node
from libs.contracts.agent_outputs import build_monitor_output_artifact


class _FakeMinuteSkillRunner:
    def __init__(self, rows_by_symbol: dict[str, list[dict]] | None = None) -> None:
        self.rows_by_symbol = dict(rows_by_symbol or {})
        self.call_count = 0

    def run(self, *, run_id: str, skill: str, args: dict) -> dict:
        self.call_count += 1
        if skill != "market.minute_ohlcv":
            return {"result": {"action": "error", "meta": {"error_type": "unsupported_skill"}}}
        symbol = str(args.get("symbol") or "").strip().upper()
        rows = list(self.rows_by_symbol.get(symbol) or [])
        if not rows:
            return {"result": {"action": "error", "meta": {"error_type": "empty_response"}}}
        return {
            "result": {
                "action": "ready",
                "data": {
                    "symbol": symbol,
                    "timeframe_minutes": int(args.get("timeframe_minutes") or 1),
                    "rows": rows,
                },
            }
        }


class _FakeMinuteSkillRunnerDataclass:
    def __init__(self, rows_by_symbol: dict[str, list[dict]] | None = None) -> None:
        self.rows_by_symbol = dict(rows_by_symbol or {})
        self.call_count = 0

    def run(self, *, run_id: str, skill: str, args: dict) -> SkillRunResult:
        self.call_count += 1
        symbol = str(args.get("symbol") or "").strip().upper()
        rows = list(self.rows_by_symbol.get(symbol) or [])
        if not rows:
            return SkillRunResult(
                action="error",
                skill=skill,
                outputs="MinuteOHLCVDTO",
                data=None,
                missing=[],
                question="",
                meta={"error_type": "empty_response"},
            )
        return SkillRunResult(
            action="ready",
            skill=skill,
            outputs="MinuteOHLCVDTO",
            data=MinuteOHLCVDTO(
                symbol=symbol,
                timeframe_minutes=int(args.get("timeframe_minutes") or 1),
                rows=rows,
                raw={},
            ),
            missing=[],
            question="",
            meta={},
        )


class _FakeMinuteSkillRunnerSequence:
    def __init__(self, responses: list[list[dict]] | None = None) -> None:
        self.responses = list(responses or [])
        self.call_count = 0

    def run(self, *, run_id: str, skill: str, args: dict) -> dict:
        self.call_count += 1
        if skill != "market.minute_ohlcv":
            return {"result": {"action": "error", "meta": {"error_type": "unsupported_skill"}}}
        rows = list(self.responses.pop(0) if self.responses else [])
        if not rows:
            return {"result": {"action": "error", "meta": {"error_type": "empty_response"}}}
        symbol = str(args.get("symbol") or "").strip().upper()
        return {
            "result": {
                "action": "ready",
                "data": {
                    "symbol": symbol,
                    "timeframe_minutes": int(args.get("timeframe_minutes") or 1),
                    "rows": rows,
                },
            }
        }


def _base_state() -> dict:
    return {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "005930",
            "price": 71000.0,
            "features": {"engine_volatility20": 0.02},
        },
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 120}],
        },
        "policy": {
            "use_exit_policy": True,
            "exit_policy": {"take_profit_pct": 0.01},
        },
    }


def _with_commander_numeric_policy(
    state: dict,
    *,
    post_exit_sec: int = 180,
    sell_sec: int = 300,
    min_hold_seconds: int = 600,
    confirm_ticks: int = 2,
    eod_flat_cutoff_min: int = 10,
    scoring_threshold: float = 3.0,
) -> dict:
    out = dict(state or {})
    applied_policy = dict(out.get("applied_policy") or {}) if isinstance(out.get("applied_policy"), dict) else {}
    execution_policy = dict(applied_policy.get("execution") or {}) if isinstance(applied_policy.get("execution"), dict) else {}
    execution_policy["cooldowns"] = {
        "post_exit_sec": int(post_exit_sec),
        "sell_sec": int(sell_sec),
        "policy_source": "test_commander_applied_policy",
    }
    monitor_policy = dict(applied_policy.get("monitor") or {}) if isinstance(applied_policy.get("monitor"), dict) else {}
    monitor_policy["hold"] = {
        "min_hold_seconds": int(min_hold_seconds),
        "policy_source": "test_commander_applied_policy",
    }
    monitor_policy["exit"] = {
        "confirm_ticks": int(confirm_ticks),
        "eod_flat": {"cutoff_min": int(eod_flat_cutoff_min)},
        "policy_source": "test_commander_applied_policy",
    }
    entry_policy = dict((monitor_policy.get("entry") or {})) if isinstance(monitor_policy.get("entry"), dict) else {}
    entry_policy["scoring"] = {
        "enabled": False,
        "shadow_mode": True,
        "threshold": float(scoring_threshold),
        "entry_threshold": float(scoring_threshold),
        "policy_source": "test_commander_applied_policy",
    }
    monitor_policy["entry"] = entry_policy
    applied_policy["execution"] = execution_policy
    applied_policy["monitor"] = monitor_policy
    out["applied_policy"] = applied_policy
    return out


def _policy_with_entry_cooldown(seconds: int, base: dict | None = None) -> dict:
    out = dict(base or {})
    monitor_policy = dict(out.get("monitor_policy") or {}) if isinstance(out.get("monitor_policy"), dict) else {}
    monitor_policy["entry_intent_cooldown_sec"] = int(seconds)
    out["monitor_policy"] = monitor_policy
    return out


def _entry_wait_rows_reclaim() -> list[dict]:
    return [
        {"open": 100.0, "high": 100.5, "low": 99.9, "close": 100.4, "volume": 1000, "vwap": 100.1},
        {"open": 100.4, "high": 101.1, "low": 100.3, "close": 101.0, "volume": 1050, "vwap": 100.5},
        {"open": 101.0, "high": 101.8, "low": 100.9, "close": 101.6, "volume": 1100, "vwap": 100.9},
        {"open": 101.6, "high": 101.7, "low": 100.4, "close": 100.8, "volume": 950, "vwap": 100.9},
        {"open": 100.8, "high": 100.9, "low": 99.7, "close": 100.2, "volume": 980, "vwap": 100.6},
        {"open": 100.2, "high": 100.4, "low": 100.0, "close": 100.1, "volume": 600, "vwap": 100.8},
    ]


def _entry_ready_rows_reclaim() -> list[dict]:
    return [
        {"open": 100.0, "high": 100.5, "low": 99.9, "close": 100.4, "volume": 1000, "vwap": 100.1},
        {"open": 100.4, "high": 101.1, "low": 100.3, "close": 101.0, "volume": 1050, "vwap": 100.5},
        {"open": 101.0, "high": 101.8, "low": 100.9, "close": 101.6, "volume": 1100, "vwap": 100.9},
        {"open": 101.6, "high": 101.7, "low": 100.4, "close": 100.8, "volume": 950, "vwap": 100.9},
        {"open": 100.8, "high": 100.9, "low": 99.7, "close": 100.2, "volume": 980, "vwap": 100.6},
        {"open": 100.2, "high": 101.3, "low": 100.1, "close": 101.1, "volume": 1500, "vwap": 100.7},
    ]


def _entry_breakout_rows() -> list[dict]:
    return [
        {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
        {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
        {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
        {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
        {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 2500, "vwap": 101.2},
    ]


def test_monitor_exit_policy_respects_min_hold_guard(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "600")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "300")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    out = monitor_node(_base_state())
    assert out["intents"] == []
    assert out["monitor_exit"]["sell_guard_blocked"] is True
    assert "sell_guard_min_hold" in str(out["monitor_exit"]["sell_guard_reason"])
    assert out["monitor_exit"]["triggered"] is False


def test_monitor_exit_requires_confirmation_ticks(monkeypatch):
    s1 = _with_commander_numeric_policy(_base_state(), min_hold_seconds=0, sell_sec=0, confirm_ticks=2)
    out1 = monitor_node(s1)
    assert out1["intents"] == []
    assert out1["monitor_exit"]["triggered"] is False
    assert "exit_confirmation_pending:1/2" in str(out1["monitor_exit"]["sell_guard_reason"])

    out2 = monitor_node(out1)
    intents = out2.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert out2["monitor_exit"]["triggered"] is True


def test_monitor_exit_cooldown_suppresses_duplicate_sell_intents(monkeypatch):
    base = _with_commander_numeric_policy(_base_state(), min_hold_seconds=0, sell_sec=300, confirm_ticks=1)
    base["tick_ts"] = 1772850000
    out1 = monitor_node(base)
    intents1 = out1.get("intents") or []
    assert len(intents1) == 1
    assert intents1[0]["side"] == "SELL"

    out2 = monitor_node(out1)
    assert out2.get("intents") == []
    reason = str((out2.get("monitor_exit") or {}).get("sell_guard_reason") or "")
    assert "sell_guard_pending_exit_lock" in reason


def test_monitor_exit_cooldown_applies_after_position_closed(monkeypatch):
    s1 = _with_commander_numeric_policy(_base_state(), min_hold_seconds=0, sell_sec=300, confirm_ticks=1)
    s1["tick_ts"] = 1772850000
    out1 = monitor_node(s1)
    assert (out1.get("intents") or [{}])[0].get("side") == "SELL"

    s2 = dict(out1)
    s2["portfolio_snapshot"] = {"cash": 0.0, "positions": []}
    s2["use_position_sizing"] = True
    s2["tick_ts"] = 1772850001
    out2 = monitor_node(s2)
    assert out2.get("intents") == []

    s3 = dict(out2)
    s3["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 800}],
    }
    s3["tick_ts"] = 1772850002
    out3 = monitor_node(s3)
    assert out3.get("intents") == []
    reason = str((out3.get("monitor_exit") or {}).get("sell_guard_reason") or "")
    assert "sell_guard_cooldown" in reason
    assert (out3.get("monitor_exit") or {}).get("sell_cooldown_blocked") is True


def test_monitor_does_not_select_symbol_when_selected_missing(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": None,
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 900}],
        },
        "policy": {"use_exit_policy": True},
    }
    out = monitor_node(state)
    assert out.get("intents") == []
    assert (out.get("monitor_output") or {}).get("selected_symbol") is None


def test_monitor_blocks_new_buy_when_open_position_guard_enabled(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "true")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0}],
        },
        "policy": {},
    }
    out = monitor_node(state)
    assert out.get("intents") == []
    mon = out.get("monitor") or {}
    assert mon.get("open_position_count") == 1
    assert mon.get("buy_blocked_open_position") is True
    assert (out.get("monitor_output") or {}).get("entry_exit_reason") == "buy_blocked_open_position"


def test_monitor_waits_when_open_position_guard_disabled_but_minute_candles_missing(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0}],
        },
        "policy": {},
    }
    out = monitor_node(state)
    assert out.get("intents") == []
    monitor = out.get("monitor") or {}
    assert monitor.get("buy_blocked_open_position") is False
    assert monitor.get("entry_triggered") is False
    assert monitor.get("entry_reason") == "minute_candle_missing"
    assert (out.get("monitor_output") or {}).get("entry_exit_reason") == "minute_candle_missing"


def test_monitor_requires_intraday_entry_confirmation_when_ohlcv_available(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "minute_ohlcv_by_symbol": {
            "BBB": [
                {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
                {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
                {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
                {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
                {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
                {"open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 2500, "vwap": 101.2},
            ]
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    monitor = out.get("monitor") or {}
    assert monitor.get("entry_evaluated") is True
    assert monitor.get("entry_triggered") is True
    assert monitor.get("entry_pattern") == "breakout_vwap_hold"


def test_monitor_skips_buy_when_intraday_entry_signal_not_confirmed(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 103.2,
            "features": {"engine_vwap_distance": 0.020, "engine_volume_spike20": 1.6},
        },
        "minute_ohlcv_by_symbol": {
            "BBB": [
                {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
                {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
                {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
                {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
                {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
                {"open": 101.2, "high": 103.4, "low": 101.0, "close": 103.2, "volume": 2500, "vwap": 101.1},
            ]
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(
            0,
            base={"monitor_policy": {"entry_max_extended_from_vwap_pct": 0.02}},
        ),
    }

    out = monitor_node(state)
    assert out.get("intents") == []
    monitor = out.get("monitor") or {}
    assert monitor.get("entry_evaluated") is True
    assert monitor.get("entry_triggered") is False
    assert monitor.get("entry_reason") == "too_extended_from_vwap"
    assert monitor.get("entry_primary_failure_axis") == "overextension"
    assert "extension_ok" in list(monitor.get("entry_failed_checks") or [])
    assert (out.get("monitor_output") or {}).get("entry_exit_reason") == "too_extended_from_vwap"


def test_monitor_waits_when_minute_candles_missing(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.2,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.3},
        },
        "minute_ohlcv_by_symbol": {},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
    }

    out = monitor_node(state)
    assert out.get("intents") == []
    monitor = out.get("monitor") or {}
    assert monitor.get("entry_evaluated") is False
    assert monitor.get("entry_triggered") is False
    assert monitor.get("entry_reason") == "minute_candle_missing"
    assert (out.get("monitor_output") or {}).get("entry_exit_reason") == "minute_candle_missing"


def test_monitor_hydrates_selected_symbol_minute_ohlcv_from_skill_runner(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    rows = [
        {"ts": 1710000000, "open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
        {"ts": 1710000060, "open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
        {"ts": 1710000120, "open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
        {"ts": 1710000180, "open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
        {"ts": 1710000240, "open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"ts": 1710000300, "open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 2500, "vwap": 101.2},
    ]
    state = {
        "run_id": "run-monitor-minute-hydrate",
        "skill_runner": _FakeMinuteSkillRunner({"BBB": rows}),
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    assert "BBB" in (out.get("minute_ohlcv_by_symbol") or {})
    monitor = out.get("monitor") or {}
    metrics = monitor.get("entry_metrics") or {}
    assert metrics.get("minute_source_present") is True
    assert metrics.get("minute_source_used") == "state.minute_ohlcv_by_symbol"
    assert float(metrics.get("inferred_spacing_minutes") or 0.0) <= 1.1


def test_monitor_hydrates_selected_symbol_minute_ohlcv_from_dataclass_skill_result(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    rows = [
        {"ts": 1710000000, "open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
        {"ts": 1710000060, "open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
        {"ts": 1710000120, "open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
        {"ts": 1710000180, "open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
        {"ts": 1710000240, "open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"ts": 1710000300, "open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 2500, "vwap": 101.2},
    ]
    state = {
        "run_id": "run-monitor-minute-dataclass",
        "skill_runner": _FakeMinuteSkillRunnerDataclass({"BBB": rows}),
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    metrics = (out.get("monitor") or {}).get("entry_metrics") or {}
    assert metrics.get("minute_source_present") is True
    assert metrics.get("latest_candle_ts") == 1710000300


def test_monitor_keeps_fresh_minute_snapshot_without_refetch(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    rows = [
        {"ts": 1710000000, "open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
        {"ts": 1710000060, "open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
        {"ts": 1710000120, "open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
        {"ts": 1710000180, "open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
        {"ts": 1710000240, "open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"ts": 1710000300, "open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 2500, "vwap": 101.2},
    ]
    runner = _FakeMinuteSkillRunner({"BBB": rows})
    state = {
        "run_id": "run-monitor-minute-fresh",
        "tick_ts": 1710000360,
        "skill_runner": runner,
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "minute_ohlcv_by_symbol": {"BBB": list(rows)},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
    }

    out = monitor_node(state)
    metrics = (out.get("monitor") or {}).get("entry_metrics") or {}
    assert runner.call_count == 0
    assert metrics.get("minute_snapshot_was_stale") is False
    assert metrics.get("minute_refetch_attempted") is False
    assert metrics.get("minute_refetch_succeeded") is False
    assert metrics.get("minute_refetch_trigger_reason") == ""
    assert metrics.get("minute_refetch_failure_reason") == ""
    assert metrics.get("minute_refetch_produced_fresh_snapshot") is False
    assert metrics.get("latest_candle_ts") == 1710000300
    assert float(metrics.get("minute_snapshot_age_minutes") or 0.0) == 1.0


def test_monitor_refetches_stale_minute_snapshot_and_uses_new_latest_candle(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    stale_rows = [
        {"ts": 1710000000, "open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
        {"ts": 1710000060, "open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
        {"ts": 1710000120, "open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
        {"ts": 1710000180, "open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
        {"ts": 1710000240, "open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"ts": 1710000300, "open": 101.2, "high": 101.8, "low": 101.0, "close": 101.4, "volume": 1200, "vwap": 101.0},
    ]
    fresh_rows = [
        {"ts": 1710000300, "open": 101.2, "high": 101.4, "low": 101.0, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"ts": 1710000360, "open": 101.2, "high": 101.4, "low": 100.9, "close": 101.1, "volume": 1100, "vwap": 101.0},
        {"ts": 1710000420, "open": 101.1, "high": 101.5, "low": 101.0, "close": 101.3, "volume": 1120, "vwap": 101.1},
        {"ts": 1710000480, "open": 101.3, "high": 101.6, "low": 101.1, "close": 101.4, "volume": 1150, "vwap": 101.2},
        {"ts": 1710000540, "open": 101.4, "high": 101.7, "low": 101.2, "close": 101.5, "volume": 1180, "vwap": 101.25},
        {"ts": 1710000600, "open": 101.5, "high": 102.0, "low": 101.3, "close": 101.8, "volume": 2500, "vwap": 101.4},
    ]
    runner = _FakeMinuteSkillRunnerSequence([fresh_rows])
    state = {
        "run_id": "run-monitor-minute-stale-refresh",
        "tick_ts": 1710000600,
        "skill_runner": runner,
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "minute_ohlcv_by_symbol": {"BBB": list(stale_rows)},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
    }

    out = monitor_node(state)
    metrics = (out.get("monitor") or {}).get("entry_metrics") or {}
    assert runner.call_count == 1
    assert metrics.get("minute_refetch_attempted") is True
    assert metrics.get("minute_refetch_succeeded") is True
    assert metrics.get("minute_refetch_reason") == "stale_snapshot_age_exceeded"
    assert metrics.get("minute_refetch_trigger_reason") == "stale_snapshot_age_exceeded"
    assert metrics.get("minute_refetch_failure_reason") == ""
    assert metrics.get("minute_refetch_produced_fresh_snapshot") is True
    assert metrics.get("latest_candle_ts") == 1710000600
    assert metrics.get("minute_snapshot_was_stale") is False
    assert float(metrics.get("minute_snapshot_age_minutes") or 0.0) == 0.0
    assert (out.get("minute_ohlcv_by_symbol") or {}).get("BBB", [])[-1]["ts"] == 1710000600
    assert ((out.get("skill_results") or {}).get("market.minute_ohlcv_by_symbol") or {}).get("BBB")
    assert len(list(((out.get("skill_results_history") or {}).get("market.minute_ohlcv") or []))) == 1


def test_monitor_records_stale_snapshot_when_refetch_fails_without_changing_flow(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    stale_rows = [
        {"ts": 1710000000, "open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
        {"ts": 1710000060, "open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
        {"ts": 1710000120, "open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
        {"ts": 1710000180, "open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
        {"ts": 1710000240, "open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"ts": 1710000300, "open": 101.2, "high": 103.4, "low": 101.0, "close": 103.2, "volume": 2500, "vwap": 101.1},
    ]
    runner = _FakeMinuteSkillRunnerSequence([[]])
    state = {
        "run_id": "run-monitor-minute-stale-fail",
        "tick_ts": 1710000600,
        "skill_runner": runner,
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 103.2,
            "features": {"engine_vwap_distance": 0.020, "engine_volume_spike20": 1.6},
        },
        "minute_ohlcv_by_symbol": {"BBB": list(stale_rows)},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(
            0,
            base={"monitor_policy": {"entry_max_extended_from_vwap_pct": 0.02}},
        ),
    }

    out = monitor_node(state)
    metrics = (out.get("monitor") or {}).get("entry_metrics") or {}
    assert runner.call_count == 1
    assert out.get("intents") == []
    assert metrics.get("minute_refetch_attempted") is True
    assert metrics.get("minute_refetch_succeeded") is False
    assert metrics.get("minute_refetch_reason") == "stale_snapshot_age_exceeded"
    assert metrics.get("minute_refetch_trigger_reason") == "stale_snapshot_age_exceeded"
    assert str(metrics.get("minute_refetch_failure_reason") or "") in {"error", "refetch_empty_rows"}
    assert str(metrics.get("minute_refetch_failure_detail") or "") in {"error", "refetch_empty_rows"}
    assert metrics.get("minute_refetch_produced_fresh_snapshot") is False
    assert metrics.get("minute_snapshot_was_stale") is True
    assert metrics.get("latest_candle_ts") == 1710000300
    assert ((out.get("skill_results") or {}).get("market.minute_ohlcv_by_symbol") or {}).get("BBB")


def test_monitor_refetch_uses_fresh_runner_when_primary_runner_returns_empty(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    fresh_rows = [
        {"ts": 1710000300, "open": 101.2, "high": 101.4, "low": 101.0, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"ts": 1710000360, "open": 101.2, "high": 101.4, "low": 100.9, "close": 101.1, "volume": 1100, "vwap": 101.0},
        {"ts": 1710000420, "open": 101.1, "high": 101.5, "low": 101.0, "close": 101.3, "volume": 1120, "vwap": 101.1},
        {"ts": 1710000480, "open": 101.3, "high": 101.6, "low": 101.1, "close": 101.4, "volume": 1150, "vwap": 101.2},
        {"ts": 1710000540, "open": 101.4, "high": 101.7, "low": 101.2, "close": 101.5, "volume": 1180, "vwap": 101.25},
        {"ts": 1710000600, "open": 101.5, "high": 102.0, "low": 101.3, "close": 101.8, "volume": 2500, "vwap": 101.4},
    ]
    primary_runner = _FakeMinuteSkillRunnerSequence([[]])
    fresh_runner = _FakeMinuteSkillRunnerSequence([fresh_rows])
    monkeypatch.setattr("libs.skills.runner.CompositeSkillRunner.from_env", lambda: fresh_runner)

    state = {
        "run_id": "run-monitor-minute-fresh-fallback",
        "tick_ts": 1710000600,
        "skill_runner": primary_runner,
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
    }

    out = monitor_node(state)
    metrics = (out.get("monitor") or {}).get("entry_metrics") or {}
    assert primary_runner.call_count == 1
    assert fresh_runner.call_count == 1
    assert metrics.get("minute_source_present") is True
    assert metrics.get("minute_refetch_attempted") is True
    assert metrics.get("minute_refetch_succeeded") is True
    assert metrics.get("minute_refetch_runner_source") == "fresh.composite_skill_runner"
    assert metrics.get("minute_refetch_produced_fresh_snapshot") is True
    assert ((out.get("skill_results") or {}).get("market.minute_ohlcv_by_symbol") or {}).get("BBB")


def test_monitor_auto_bootstraps_skill_runner_for_hold_cycle_minute_fetch(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "true")

    class _AutoRunner:
        def __init__(self):
            self.call_count = 0

        def run(self, run_id, skill, args):
            self.call_count += 1
            assert skill == "market.minute_ohlcv"
            return {
                "result": {
                    "action": "ready",
                    "data": {
                        "rows": [
                            {"ts": 1710000300, "open": 101.2, "high": 101.4, "low": 101.0, "close": 101.2, "volume": 1080, "vwap": 100.9},
                            {"ts": 1710000360, "open": 101.2, "high": 101.4, "low": 100.9, "close": 101.1, "volume": 1100, "vwap": 101.0},
                            {"ts": 1710000420, "open": 101.1, "high": 101.5, "low": 101.0, "close": 101.3, "volume": 1120, "vwap": 101.1},
                            {"ts": 1710000480, "open": 101.3, "high": 101.6, "low": 101.1, "close": 101.4, "volume": 1150, "vwap": 101.2},
                            {"ts": 1710000540, "open": 101.4, "high": 101.7, "low": 101.2, "close": 101.5, "volume": 1180, "vwap": 101.25},
                            {"ts": 1710000600, "open": 101.5, "high": 102.0, "low": 101.3, "close": 101.8, "volume": 2500, "vwap": 101.4},
                        ]
                    },
                }
            }

    auto_runner = _AutoRunner()
    monkeypatch.setattr("libs.skills.runner.CompositeSkillRunner.from_env", lambda: auto_runner)
    state = {
        "run_id": "run-monitor-hold-auto-minute-fetch",
        "tick_ts": 1710000600,
        "m13_tick_pipeline": "integrated_chain",
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": [{"symbol": "BBB", "qty": 2, "avg_price": 100.0}]},
        "policy": {"use_exit_policy": True},
        "market_snapshot": {"symbol": "BBB", "price": 101.8},
    }

    out = monitor_node(state)
    metrics = (out.get("monitor") or {}).get("entry_metrics") or {}
    entry_detail = out.get("monitor_entry_decision_detail") or {}
    assert auto_runner.call_count == 1
    assert metrics.get("minute_source_present") is True
    assert metrics.get("minute_refetch_attempted") is True
    assert metrics.get("minute_refetch_succeeded") is True
    assert metrics.get("minute_refetch_runner_source") == "integrated_chain_auto.composite_skill_runner"
    assert metrics.get("minute_refetch_failure_reason") == ""
    assert isinstance(entry_detail.get("minute_fetch_meta"), dict)
    assert (entry_detail.get("minute_fetch_meta") or {}).get("minute_refetch_runner_source") == "integrated_chain_auto.composite_skill_runner"


def test_monitor_hold_cycle_runner_unavailable_keeps_observability(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setattr("libs.skills.runner.CompositeSkillRunner.from_env", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    state = {
        "run_id": "run-monitor-hold-runner-unavailable",
        "tick_ts": 1710000600,
        "m13_tick_pipeline": "integrated_chain",
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": [{"symbol": "BBB", "qty": 2, "avg_price": 100.0}]},
        "policy": {"use_exit_policy": True},
        "market_snapshot": {"symbol": "BBB", "price": 101.8},
    }

    out = monitor_node(state)
    metrics = (out.get("monitor") or {}).get("entry_metrics") or {}
    assert metrics.get("minute_source_present") is False
    assert metrics.get("minute_refetch_attempted") is True
    assert metrics.get("minute_refetch_succeeded") is False
    assert metrics.get("minute_refetch_failure_reason") == "skill_runner_unavailable"
    assert metrics.get("minute_refetch_failure_detail") == "integrated_chain_auto_runner_error"
    assert metrics.get("minute_refetch_runner_source") == "integrated_chain_auto_runner_error"


def test_monitor_waits_when_ohlcv_series_is_daily_seed_not_minute_data(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    start_ts = 1_710_000_000
    rows = []
    closes = [100.0, 101.5, 102.0, 103.0, 102.8, 104.0]
    for idx, close in enumerate(closes[:-1]):
        rows.append(
            {
                "ts": start_ts + idx * 86400,
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000 + idx * 20_000,
                "vwap": close - 0.2,
            }
        )
    rows.append(
        {
            "ts": start_ts + len(closes[:-1]) * 86400,
            "open": 104.0,
            "high": 104.0,
            "low": 104.0,
            "close": 104.0,
            "volume": 1.0,
            "vwap": 103.4,
        }
    )

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 104.0,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.3},
        },
        "ohlcv_by_symbol": {"BBB": rows},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
    }

    out = monitor_node(state)
    assert out.get("intents") == []
    monitor = out.get("monitor") or {}
    assert monitor.get("entry_evaluated") is False
    assert monitor.get("entry_triggered") is False
    assert monitor.get("entry_reason") == "minute_candle_missing"
    assert bool((monitor.get("entry_metrics") or {}).get("minute_source_present")) is False
    assert (out.get("monitor_output") or {}).get("entry_exit_reason") == "minute_candle_missing"


def test_monitor_allows_pullback_entry_when_reclaim_structure_is_valid(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.1,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.2},
        },
        "minute_ohlcv_by_symbol": {
            "BBB": [
                {"open": 100.0, "high": 100.5, "low": 99.9, "close": 100.4, "volume": 1000, "vwap": 100.1},
                {"open": 100.4, "high": 101.1, "low": 100.3, "close": 101.0, "volume": 1050, "vwap": 100.5},
                {"open": 101.0, "high": 101.8, "low": 100.9, "close": 101.6, "volume": 1100, "vwap": 100.9},
                {"open": 101.6, "high": 101.7, "low": 100.4, "close": 100.8, "volume": 950, "vwap": 100.9},
                {"open": 100.8, "high": 100.9, "low": 99.7, "close": 100.2, "volume": 980, "vwap": 100.6},
                {"open": 100.2, "high": 101.3, "low": 100.1, "close": 101.1, "volume": 900, "vwap": 100.7},
            ]
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "strategist_output": {"playbook": "pullback"},
        "policy": _policy_with_entry_cooldown(0),
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    monitor = out.get("monitor") or {}
    assert monitor.get("entry_triggered") is True
    assert monitor.get("entry_pattern") == "pullback_vwap_reclaim"
    thresholds = monitor.get("entry_thresholds") or {}
    assert float(thresholds.get("max_extended_from_vwap_pct") or 0.0) >= 0.045


def test_monitor_pullback_wait_records_failure_breakdown(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 106.0,
            "features": {"engine_vwap_distance": 0.050, "engine_volume_spike20": 1.2},
        },
        "minute_ohlcv_by_symbol": {
            "BBB": [
                {"open": 100.0, "high": 100.5, "low": 99.9, "close": 100.4, "volume": 1000, "vwap": 100.1},
                {"open": 100.4, "high": 101.1, "low": 100.3, "close": 101.0, "volume": 1050, "vwap": 100.5},
                {"open": 101.0, "high": 101.8, "low": 100.9, "close": 101.6, "volume": 1100, "vwap": 100.9},
                {"open": 101.6, "high": 101.7, "low": 100.4, "close": 100.8, "volume": 950, "vwap": 100.9},
                {"open": 100.8, "high": 100.9, "low": 99.7, "close": 100.2, "volume": 980, "vwap": 100.6},
                {"open": 100.2, "high": 106.2, "low": 100.1, "close": 106.0, "volume": 1200, "vwap": 100.7},
            ]
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "strategist_output": {"playbook": "pullback"},
        "policy": _policy_with_entry_cooldown(
            0,
            base={"monitor_policy": {"entry_max_extended_from_vwap_pct": 0.02}},
        ),
    }

    out = monitor_node(state)
    assert out.get("intents") == []
    monitor = out.get("monitor") or {}
    assert monitor.get("entry_reason") == "still_overextended_after_pullback"
    assert monitor.get("entry_primary_failure_axis") == "overextension"
    assert "extension_ok" in list(monitor.get("entry_failed_checks") or [])
    margins = monitor.get("entry_threshold_margins") or {}
    ext = margins.get("extended_from_vwap_pct") or {}
    assert float(ext.get("actual") or 0.0) > float(ext.get("max") or 0.0)


def test_monitor_pullback_with_defensive_guidance_can_still_buy_on_clean_reclaim(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.1,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.25},
        },
        "minute_ohlcv_by_symbol": {
            "BBB": [
                {"open": 100.0, "high": 100.5, "low": 99.9, "close": 100.4, "volume": 1000, "vwap": 100.1},
                {"open": 100.4, "high": 101.1, "low": 100.3, "close": 101.0, "volume": 1050, "vwap": 100.5},
                {"open": 101.0, "high": 101.8, "low": 100.9, "close": 101.6, "volume": 1100, "vwap": 100.9},
                {"open": 101.6, "high": 101.7, "low": 100.4, "close": 100.8, "volume": 950, "vwap": 100.9},
                {"open": 100.8, "high": 100.9, "low": 99.7, "close": 100.2, "volume": 980, "vwap": 100.6},
                {"open": 100.2, "high": 101.3, "low": 100.1, "close": 101.1, "volume": 1200, "vwap": 100.7},
            ]
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "strategist_output": {
            "playbook": "pullback",
            "monitor_guidance": "defensive_exit",
            "risk_tone": "conservative",
            "trade_aggressiveness": "low",
        },
        "policy": _policy_with_entry_cooldown(0),
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    thresholds = (out.get("monitor") or {}).get("entry_thresholds") or {}
    assert float(thresholds.get("max_extended_from_vwap_pct") or 0.0) >= 0.0425
    assert float(thresholds.get("volume_ratio_min") or 0.0) <= 1.1


def test_monitor_blocks_reentry_during_post_exit_cooldown(monkeypatch):
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = _with_commander_numeric_policy(
        {
            "tick_ts": 2000,
            "plan": {"thesis": "test"},
            "selected": {"symbol": "BBB"},
            "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
            "persisted_state": {"last_trade_side": "SELL", "last_trade_epoch": 1500},
            "policy": {},
        },
        post_exit_sec=600,
    )
    out = monitor_node(state)
    assert out.get("intents") == []
    mon = out.get("monitor") or {}
    assert mon.get("buy_blocked_post_exit_cooldown") is True
    assert mon.get("post_exit_cooldown_remaining_sec") == 100
    assert (out.get("monitor_output") or {}).get("entry_exit_reason") == "post_exit_cooldown"


def test_monitor_blocks_new_buy_inside_closeout_window(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "true")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "minute_ohlcv_by_symbol": {"BBB": _entry_breakout_rows()},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": {
            **_policy_with_entry_cooldown(0),
            "exit_policy": {"use_eod_flat": True, "eod_flat_cutoff_min": 10},
        },
        "market_context": {"minutes_to_close": 5},
    }

    out = monitor_node(state)
    mon = out.get("monitor") or {}
    blocker_surface = dict(out.get("monitor_entry_blocker_surface") or {})

    assert out.get("intents") == []
    assert mon.get("buy_blocked_closeout_window") is True
    assert mon.get("entry_guard_reason") == "buy_blocked_closeout_window"
    assert mon.get("minutes_to_close") == 5
    assert mon.get("eod_flat_cutoff_min") == 10
    assert mon.get("closeout_window_active") is True
    assert (out.get("monitor_output") or {}).get("entry_exit_reason") == "buy_blocked_closeout_window"
    assert blocker_surface.get("closeout_window_blocked") is True
    assert blocker_surface.get("minutes_to_close") == 5
    assert blocker_surface.get("eod_flat_cutoff_min") == 10


def test_monitor_blocks_new_buy_inside_closeout_window_when_market_context_missing_but_tick_ts_near_close(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "true")

    state = {
        "tick_ts": 1776407100,  # 2026-04-17 15:25:00 KST
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "minute_ohlcv_by_symbol": {"BBB": _entry_breakout_rows()},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": {
            **_policy_with_entry_cooldown(0),
            "exit_policy": {"use_eod_flat": True, "eod_flat_cutoff_min": 10},
        },
        "market_context": {},
    }

    out = monitor_node(state)
    mon = out.get("monitor") or {}

    assert out.get("intents") == []
    assert mon.get("buy_blocked_closeout_window") is True
    assert mon.get("entry_guard_reason") == "buy_blocked_closeout_window"
    assert float(mon.get("minutes_to_close") or 0.0) == 5.0
    assert mon.get("eod_flat_cutoff_min") == 10
    assert mon.get("closeout_window_active") is True
    assert (out.get("monitor_output") or {}).get("entry_exit_reason") == "buy_blocked_closeout_window"


def test_monitor_entry_intent_cooldown_suppresses_duplicate_buy_intents(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "tick_ts": 1772850000,
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "minute_ohlcv_by_symbol": {
            "BBB": [
                {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
                {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
                {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
                {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
                {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
                {"open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 2500, "vwap": 101.2},
            ]
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(60),
    }

    out1 = monitor_node(state)
    intents1 = out1.get("intents") or []
    assert len(intents1) == 1
    assert intents1[0]["side"] == "BUY"

    out2 = monitor_node(out1)
    assert out2.get("intents") == []
    monitor2 = out2.get("monitor") or {}
    assert monitor2.get("entry_guard_blocked") is True
    assert "entry_guard_cooldown" in str(monitor2.get("entry_guard_reason") or "")


def test_monitor_falls_back_to_held_symbol_for_exit_when_selected_has_no_position(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 3, "avg_price": 100.0, "hold_sec": 900}],
        },
        "market_snapshot": {"symbol": "AAA", "price": 95.0},
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }
    out = monitor_node(state)

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert intents[0]["symbol"] == "AAA"
    assert (out.get("monitor") or {}).get("exit_symbol_fallback") is True
    assert (out.get("monitor_exit") or {}).get("selected_symbol") == "BBB"
    assert (out.get("monitor_exit") or {}).get("symbol") == "AAA"


def test_monitor_uses_position_mark_price_when_quote_unavailable(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [
                {
                    "symbol": "AAA",
                    "qty": 3,
                    "avg_price": 100.0,
                    "unrealized_pnl": -15.0,
                    "hold_sec": 900,
                }
            ],
        },
        # quote intentionally unavailable for AAA to force position mark fallback.
        "market_snapshot": {"symbol": "BBB", "price": 120.0},
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }
    out = monitor_node(state)

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert intents[0]["symbol"] == "AAA"
    assert str((out.get("monitor_exit") or {}).get("reason") or "") == "stop_loss"
    assert (out.get("monitor_exit") or {}).get("exit_symbol_fallback") is True
    assert (out.get("monitor_exit") or {}).get("price_source") == "position.avg_plus_unrealized"


def test_monitor_prefers_position_current_price_over_derived_mark(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [
                {
                    "symbol": "AAA",
                    "qty": 3,
                    "avg_price": 100.0,
                    "current_price": 96.0,
                    "unrealized_pnl": -15.0,
                    "hold_sec": 900,
                }
            ],
        },
        "market_snapshot": {"symbol": "BBB", "price": 120.0},
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }
    out = monitor_node(state)

    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("price_source") == "position.current_price"
    assert float(exit_info.get("price") or 0.0) == 96.0
    assert "position.current_price" in str(exit_info.get("price_source_policy") or "")


def test_monitor_prefers_position_current_price_over_selected_same_symbol_price(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "AAA",
            "price": 101.0,
            "features": {"skill_quote_price": 101.0},
        },
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [
                {
                    "symbol": "AAA",
                    "qty": 3,
                    "avg_price": 100.0,
                    "current_price": 96.0,
                    "unrealized_pnl": -15.0,
                    "hold_sec": 900,
                }
            ],
        },
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("price_source") == "position.current_price"
    assert float(exit_info.get("price") or 0.0) == 96.0


def test_monitor_prefers_position_current_price_over_market_snapshot_when_quote_missing(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [
                {
                    "symbol": "AAA",
                    "qty": 3,
                    "avg_price": 100.0,
                    "current_price": 96.0,
                    "unrealized_pnl": -15.0,
                    "hold_sec": 900,
                }
            ],
        },
        "market_snapshot": {"symbol": "AAA", "price": 95.0},
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("price_source") == "position.current_price"
    assert float(exit_info.get("price") or 0.0) == 96.0


def test_monitor_crosschecks_account_unrealized_pnl_and_uses_more_conservative_exit_basis():
    state = _with_commander_numeric_policy(_base_state(), min_hold_seconds=0, sell_sec=0, confirm_ticks=1)
    state["selected"] = {"symbol": "AAA"}
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [
            {
                "symbol": "AAA",
                "qty": 1,
                "avg_price": 100.0,
                "current_price": 97.0,
                "unrealized_pnl": -4.5,
                "hold_sec": 900,
            }
        ],
    }
    state["policy"] = {"use_exit_policy": True, "stop_loss_pct": 0.04, "take_profit_pct": 0.10}

    out = monitor_node(state)

    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("price_source") == "position.current_price"
    assert float(exit_info.get("price") or 0.0) == 97.0
    assert float(exit_info.get("effective_price") or 0.0) == 95.5
    assert float(exit_info.get("account_mark_price") or 0.0) == 95.5
    assert round(float(exit_info.get("raw_pnl_ratio") or 0.0), 4) == -0.03
    assert round(float(exit_info.get("pnl_ratio") or 0.0), 4) == -0.045
    assert exit_info.get("pnl_crosscheck_applied") is True
    assert str(exit_info.get("pnl_crosscheck_reason") or "") == "account_unrealized_pnl_more_conservative"
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    artifact = build_monitor_output_artifact(out)
    assert float(artifact.get("effective_price") or 0.0) == 95.5
    assert float(artifact.get("account_mark_price") or 0.0) == 95.5
    assert round(float(artifact.get("account_pnl_ratio") or 0.0), 4) == -0.045
    assert artifact.get("pnl_crosscheck_applied") is True


def test_monitor_prefers_direct_account_pnl_ratio_when_present():
    state = _with_commander_numeric_policy(_base_state(), min_hold_seconds=0, sell_sec=0, confirm_ticks=1)
    state["selected"] = {"symbol": "AAA"}
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [
            {
                "symbol": "AAA",
                "qty": 1,
                "avg_price": 100.0,
                "current_price": 97.0,
                "unrealized_pnl": -3.0,
                "account_pnl_ratio": -0.0337,
                "account_pnl_ratio_source": "position.evlu_pfls_rt",
                "hold_sec": 900,
            }
        ],
    }
    state["policy"] = {"use_exit_policy": True, "stop_loss_pct": 0.032, "take_profit_pct": 0.10}

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert round(float(exit_info.get("account_pnl_ratio") or 0.0), 4) == -0.0337
    assert str(exit_info.get("account_pnl_ratio_source") or "") == "position.evlu_pfls_rt"
    assert round(float(exit_info.get("effective_price") or 0.0), 2) == 96.63
    assert round(float(exit_info.get("pnl_ratio") or 0.0), 4) == -0.0337
    assert str(exit_info.get("pnl_crosscheck_reason") or "") == "account_pnl_ratio_more_conservative"
    artifact = build_monitor_output_artifact(out)
    assert round(float(artifact.get("account_pnl_ratio") or 0.0), 4) == -0.0337
    assert str(artifact.get("account_pnl_ratio_source") or "") == "position.evlu_pfls_rt"


def test_monitor_flags_account_ratio_mark_anomaly_and_falls_back_before_exit():
    state = _with_commander_numeric_policy(_base_state(), min_hold_seconds=0, sell_sec=0, confirm_ticks=1)
    state["selected"] = {"symbol": "AAA"}
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [
            {
                "symbol": "AAA",
                "qty": 1,
                "avg_price": 100.0,
                "current_price": 97.0,
                "unrealized_pnl": -3.0,
                "account_pnl_ratio": -0.9,
                "account_pnl_ratio_source": "prft_rt",
                "hold_sec": 900,
            }
        ],
    }
    state["policy"] = {"use_exit_policy": True, "stop_loss_pct": 0.02, "take_profit_pct": 0.10}

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("price_anomaly_flag") is True
    assert "account_pnl_ratio_mark" in str(exit_info.get("price_anomaly_reason") or "")
    assert exit_info.get("pnl_fallback_applied") is True
    assert str(exit_info.get("fallback_price_source") or "") == "account_unrealized_mark"
    assert round(float(exit_info.get("effective_price") or 0.0), 2) == 97.0
    assert str(exit_info.get("effective_price_source") or "") == "account_unrealized_mark"
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    artifact = build_monitor_output_artifact(out)
    assert artifact.get("price_anomaly_flag") is True
    assert str(artifact.get("fallback_price_source") or "") == "account_unrealized_mark"


def test_monitor_stop_loss_bypasses_hold_confirmation_guards():
    state = _with_commander_numeric_policy(_base_state(), min_hold_seconds=600, sell_sec=300, confirm_ticks=3)
    state["selected"] = {"symbol": "AAA"}
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [
            {
                "symbol": "AAA",
                "qty": 1,
                "avg_price": 100.0,
                "current_price": 97.0,
                "unrealized_pnl": -3.0,
                "hold_sec": 120,
            }
        ],
    }
    state["policy"] = {"use_exit_policy": True, "stop_loss_pct": 0.02, "take_profit_pct": 0.10}

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert exit_info.get("triggered") is True
    assert str(exit_info.get("reason") or "") == "stop_loss"
    assert exit_info.get("sell_guard_blocked") is False
    assert exit_info.get("min_hold_blocked") is False
    assert int(exit_info.get("exit_confirm_count") or 0) == 0


def test_monitor_hold_block_reason_and_final_exit_thresholds_are_explicit():
    state = _with_commander_numeric_policy(_base_state(), min_hold_seconds=600, sell_sec=0, confirm_ticks=1)
    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("triggered") is False
    assert "take_profit" in str(exit_info.get("hold_block_reason") or "")
    assert "sell_guard_min_hold" in str(exit_info.get("hold_block_reason") or "")
    assert isinstance(exit_info.get("final_exit_thresholds"), dict)
    assert str(exit_info.get("exit_threshold_source") or "") != ""
    artifact = build_monitor_output_artifact(out)
    assert isinstance(artifact.get("final_exit_thresholds"), dict)
    assert str(artifact.get("exit_threshold_source") or "") != ""
    assert "sell_guard_min_hold" in str(artifact.get("hold_block_reason") or "")


def test_monitor_uses_feature_engine_snapshot_for_held_symbol_fallback(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 3, "avg_price": 100.0, "hold_sec": 900}],
        },
        "market_snapshot": {"symbol": "AAA", "price": 95.0},
        "feature_engine": {
            "by_symbol": {
                "AAA": {
                    "atr14": 2.5,
                    "volatility20": 0.03,
                    "vwap_distance": -0.01,
                    "signal_score": -0.4,
                    "regime": "trend",
                }
            }
        },
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }
    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("triggered") is True
    assert exit_info.get("symbol") == "AAA"
    assert exit_info.get("feature_source") == "feature_engine.by_symbol"
    assert exit_info.get("price_source") == "market_snapshot"


def test_monitor_uses_ohlcv_derived_features_for_held_symbol_fallback(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    candles = []
    px = 100.0
    for _ in range(40):
        candles.append(
            {
                "open": px,
                "high": px + 1.0,
                "low": px - 1.0,
                "close": px,
                "volume": 100000,
            }
        )
        px += 0.2

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 3, "avg_price": 100.0, "hold_sec": 900}],
        },
        "skill_results": {
            "market.quote": {
                "data": {
                    "AAA": {
                        "symbol": "AAA",
                        "price": 95.0,
                        "change_pct": -5.0,
                        "volume": 123456,
                        "value": 123456789.0,
                    }
                }
            }
        },
        "ohlcv_by_symbol": {"AAA": candles},
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }
    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("triggered") is True
    assert exit_info.get("symbol") == "AAA"


def test_monitor_can_approve_overnight_carry_near_close(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("EXIT_POLICY_USE_EOD_FLAT", "true")
    monkeypatch.setenv("EXIT_POLICY_EOD_FLAT_CUTOFF_MIN", "10")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "005930",
            "price": 100.6,
            "features": {
                "engine_volatility20": 0.02,
                "engine_trend_strength": 0.22,
                "engine_vwap_distance": 0.002,
            },
        },
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 3600}],
        },
        "policy": {"use_exit_policy": True, "exit_policy": {"use_eod_flat": True, "eod_flat_cutoff_min": 10}},
        "market_context": {"minutes_to_close": 8},
        "playbook": "breakout",
        "monitor_guidance": "hold_through_noise",
        "risk_tone": "balanced",
        "persisted_state": {},
    }

    out = monitor_node(state)
    assert out.get("intents") == []
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("eod_carry_evaluated") is True
    assert exit_info.get("eod_carry_approved") is True
    assert exit_info.get("monitor_reason") == "eod_carry_approved"
    persisted = out.get("persisted_state") or {}
    overnight = persisted.get("overnight_decision_by_symbol") or {}
    assert overnight.get("005930", {}).get("approved") is True


def test_monitor_flattens_near_close_when_overnight_carry_is_not_approved(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("EXIT_POLICY_USE_EOD_FLAT", "true")
    monkeypatch.setenv("EXIT_POLICY_EOD_FLAT_CUTOFF_MIN", "10")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "005930",
            "price": 99.1,
            "features": {
                "engine_volatility20": 0.02,
                "engine_trend_strength": -0.15,
                "engine_vwap_distance": -0.009,
            },
        },
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 3600}],
        },
        "policy": {"use_exit_policy": True, "exit_policy": {"use_eod_flat": True, "eod_flat_cutoff_min": 10}},
        "market_context": {"minutes_to_close": 8},
        "playbook": "defensive",
        "monitor_guidance": "defensive_exit",
        "risk_tone": "conservative",
        "persisted_state": {},
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("eod_carry_evaluated") is True
    assert exit_info.get("eod_carry_approved") is False
    assert str(exit_info.get("reason") or "") == "eod_flat"


def test_monitor_evaluates_overnight_carry_when_selected_missing_but_position_open(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("EXIT_POLICY_USE_EOD_FLAT", "true")
    monkeypatch.setenv("EXIT_POLICY_EOD_FLAT_CUTOFF_MIN", "10")

    state = {
        "plan": {"thesis": "test"},
        "selected": None,
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [
                {
                    "symbol": "005930",
                    "qty": 2,
                    "avg_price": 100.0,
                    "hold_sec": 3600,
                    "current_price": 100.6,
                }
            ],
        },
        "feature_engine": {
            "by_symbol": {
                "005930": {
                    "engine_trend_strength": 0.22,
                    "engine_vwap_distance": 0.002,
                }
            }
        },
        "policy": {"use_exit_policy": True, "exit_policy": {"use_eod_flat": True, "eod_flat_cutoff_min": 10}},
        "market_context": {"minutes_to_close": 8},
        "playbook": "breakout",
        "monitor_guidance": "hold_through_noise",
        "risk_tone": "balanced",
        "persisted_state": {},
    }

    out = monitor_node(state)
    assert out.get("intents") == []
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("symbol") == "005930"
    assert exit_info.get("eod_carry_evaluated") is True
    assert exit_info.get("eod_carry_approved") is True
    assert exit_info.get("monitor_reason") == "eod_carry_approved"
    persisted = out.get("persisted_state") or {}
    overnight = persisted.get("overnight_decision_by_symbol") or {}
    assert overnight.get("005930", {}).get("approved") is True


def test_monitor_flags_overnight_carry_anomaly_when_minutes_to_close_missing(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("EXIT_POLICY_USE_EOD_FLAT", "true")
    monkeypatch.setenv("EXIT_POLICY_EOD_FLAT_CUTOFF_MIN", "10")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "005930",
            "price": 100.6,
            "features": {
                "engine_volatility20": 0.02,
                "engine_trend_strength": 0.22,
                "engine_vwap_distance": 0.002,
            },
        },
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 3600}],
        },
        "policy": {"use_exit_policy": True, "exit_policy": {"use_eod_flat": True, "eod_flat_cutoff_min": 10}},
        "market_context": {},
        "playbook": "breakout",
        "monitor_guidance": "hold_through_noise",
        "risk_tone": "balanced",
        "persisted_state": {},
    }

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("eod_carry_evaluated") is False
    assert exit_info.get("eod_carry_anomaly") is True
    assert exit_info.get("eod_carry_anomaly_reason") == "minutes_to_close_missing"


def test_monitor_does_not_use_other_symbol_selected_price_for_held_position(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 120.0,
            "features": {"skill_quote_price": 120.0, "engine_vwap_distance": 0.02},
        },
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 3, "avg_price": 100.0, "hold_sec": 900}],
        },
        "skill_results": {
            "market.quote": {
                "data": {
                    "AAA": {
                        "symbol": "AAA",
                        "price": 95.0,
                        "change_pct": -5.0,
                        "volume": 123456,
                        "value": 123456789.0,
                    }
                }
            }
        },
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("symbol") == "AAA"
    assert exit_info.get("price_source") == "market.quote.price"
    assert float(exit_info.get("price") or 0.0) == 95.0


def test_monitor_prefers_quote_price_over_stale_selected_feature_quote(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "AAA",
            "price": 101.0,
            "features": {
                "skill_quote_price": 101.0,
                "engine_vwap_distance": 0.02,
            },
        },
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 3, "avg_price": 100.0, "hold_sec": 900}],
        },
        "skill_results": {
            "market.quote": {
                "data": {
                    "AAA": {
                        "symbol": "AAA",
                        "price": 95.0,
                        "change_pct": -5.0,
                        "volume": 123456,
                        "value": 123456789.0,
                    }
                }
            }
        },
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("price_source") == "market.quote.price"
    assert float(exit_info.get("price") or 0.0) == 95.0


def test_monitor_backfills_peak_price_from_open_position_when_missing(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "AAA"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 3, "avg_price": 100.0, "hold_sec": 900}],
        },
        "persisted_state": {},
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.20, "take_profit_pct": 0.20},
    }

    out = monitor_node(state)
    peak_map = ((out.get("persisted_state") or {}).get("position_peak_price") or {})
    assert float(peak_map.get("AAA") or 0.0) == 100.0
    exit_info = out.get("monitor_exit") or {}
    assert float(exit_info.get("peak_price") or 0.0) == 100.0


def test_monitor_selects_held_symbol_with_triggered_exit_among_multiple_positions(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [
                {"symbol": "AAA", "qty": 2, "avg_price": 100.0, "unrealized_pnl": -20.0, "hold_sec": 900},
                {"symbol": "CCC", "qty": 5, "avg_price": 100.0, "unrealized_pnl": 0.0, "hold_sec": 900},
            ],
        },
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.05, "take_profit_pct": 0.05},
    }
    out = monitor_node(state)

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert intents[0]["symbol"] == "AAA"
    exit_info = out.get("monitor_exit") or {}
    assert str(exit_info.get("reason") or "") == "stop_loss"
    assert bool(exit_info.get("exit_symbol_fallback")) is True


def test_monitor_ignores_invalid_live_like_positions(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "true")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "005930"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "A0082N0", "qty": 1, "avg_price": 63200.0, "hold_sec": 900}],
        },
        "policy": {"use_exit_policy": True},
    }
    out = monitor_node(state)
    intents = out.get("intents") or []
    assert intents == []
    mon = out.get("monitor") or {}
    assert mon.get("open_position_count") == 0
    assert mon.get("entry_reason") == "minute_candle_missing"
    exit_info = out.get("monitor_exit") or {}
    assert bool(exit_info.get("exit_symbol_fallback")) is False
    assert int(exit_info.get("qty") or 0) == 0


def test_monitor_applies_exit_policy_env_overrides(monkeypatch):
    monkeypatch.setenv("EXIT_POLICY_MAX_HOLD_SEC", "60")

    state = _with_commander_numeric_policy(
        {
            "plan": {"thesis": "test"},
            "selected": {"symbol": "AAA"},
            "portfolio_snapshot": {
                "cash": 2_000_000.0,
                "positions": [{"symbol": "AAA", "qty": 1, "avg_price": 100.0, "hold_sec": 120}],
            },
            "policy": {"use_exit_policy": True},
        },
        min_hold_seconds=0,
        sell_sec=0,
        confirm_ticks=1,
    )
    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert str((out.get("monitor_exit") or {}).get("reason") or "") == "max_hold"


def test_monitor_stop_take_env_are_fallback_only(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")
    monkeypatch.setenv("EXIT_POLICY_STOP_LOSS_PCT", "0.01")
    monkeypatch.setenv("EXIT_POLICY_TAKE_PROFIT_PCT", "0.01")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "AAA", "price": 103.0},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 1, "avg_price": 100.0, "hold_sec": 120}],
        },
        "market_snapshot": {"symbol": "AAA", "price": 103.0},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.05,
        },
    }
    out = monitor_node(state)
    assert out.get("intents") == []
    exit_info = out.get("monitor_exit") or {}
    effective = exit_info.get("effective_exit_policy") or {}
    assert float(effective.get("stop_loss_pct") or 0.0) >= 0.05
    assert float(effective.get("take_profit_pct") or 0.0) >= 0.05
    assert str(exit_info.get("reason") or "") == "hold"


def test_monitor_max_hold_respects_min_hold_guard(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "600")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")
    monkeypatch.setenv("EXIT_POLICY_MAX_HOLD_SEC", "60")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "AAA"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 1, "avg_price": 100.0, "hold_sec": 120}],
        },
        "policy": {"use_exit_policy": True},
    }
    out = monitor_node(state)
    assert out.get("intents") == []
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("triggered") is False
    assert exit_info.get("sell_guard_blocked") is False
    assert exit_info.get("min_hold_blocked") is False
    assert str(exit_info.get("reason") or "") == "hold"
    assert exit_info.get("monitor_reason") == "hold"
    thresholds = exit_info.get("thresholds") or {}
    assert int(thresholds.get("max_hold_sec") or 0) == 600
    adjustments = exit_info.get("exit_policy_guard_adjustments") or []
    assert "max_hold_sec_raised_to_min_hold:60->600" in adjustments
    assert exit_info.get("hard_exit") is False


def test_monitor_max_hold_requires_confirmation_ticks(monkeypatch):
    monkeypatch.setenv("EXIT_POLICY_MAX_HOLD_SEC", "60")

    state = _with_commander_numeric_policy(
        {
            "plan": {"thesis": "test"},
            "selected": {"symbol": "AAA"},
            "portfolio_snapshot": {
                "cash": 2_000_000.0,
                "positions": [{"symbol": "AAA", "qty": 1, "avg_price": 100.0, "hold_sec": 120}],
            },
            "policy": {"use_exit_policy": True},
        },
        min_hold_seconds=0,
        sell_sec=0,
        confirm_ticks=2,
    )
    out1 = monitor_node(state)
    assert out1.get("intents") == []
    exit1 = out1.get("monitor_exit") or {}
    assert exit1.get("triggered") is False
    assert "exit_confirmation_pending:1/2" in str(exit1.get("sell_guard_reason") or "")
    assert exit1.get("hard_exit") is False

    out2 = monitor_node(out1)
    intents = out2.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert str((out2.get("monitor_exit") or {}).get("reason") or "") == "max_hold"
    assert bool((out2.get("monitor_exit") or {}).get("hard_exit")) is False


def test_monitor_harmonizes_max_hold_when_shorter_than_min_hold(monkeypatch):
    monkeypatch.setenv("EXIT_POLICY_MAX_HOLD_SEC", "60")

    state = _with_commander_numeric_policy(
        {
            "plan": {"thesis": "test"},
            "selected": {"symbol": "AAA"},
            "portfolio_snapshot": {
                "cash": 2_000_000.0,
                "positions": [{"symbol": "AAA", "qty": 1, "avg_price": 100.0, "hold_sec": 620}],
            },
            "policy": {"use_exit_policy": True},
        },
        min_hold_seconds=600,
        sell_sec=0,
        confirm_ticks=1,
    )
    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("triggered") is True
    assert str(exit_info.get("reason") or "") == "max_hold"
    thresholds = exit_info.get("thresholds") or {}
    assert int(thresholds.get("max_hold_sec") or 0) == 600
    adjustments = exit_info.get("exit_policy_guard_adjustments") or []
    assert "max_hold_sec_raised_to_min_hold:60->600" in adjustments


def test_monitor_emergency_exit_bypasses_min_hold_and_confirmation(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "600")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "300")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "3")

    state = _base_state()
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 30}],
    }
    state["emergency_halt"] = True
    out = monitor_node(state)

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("emergency_exit") is True
    assert exit_info.get("monitor_reason") == "emergency_exit_signal"


def test_monitor_does_not_execute_orders_directly(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = _base_state()
    state["execution_result"] = {"status": "unmodified"}
    out = monitor_node(state)
    assert out.get("execution_result") == {"status": "unmodified"}
    assert (out.get("monitor") or {}).get("has_intent") in (True, False)


def test_monitor_applies_strategic_frame_guidance_to_exit_guards(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "600")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "300")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "2")

    state = _base_state()
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 300}],
    }
    state["strategist_output"] = {
        "monitor_guidance": "quick_take_profit",
        "risk_tone": "aggressive",
        "trade_aggressiveness": "high",
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"

    exit_info = out.get("monitor_exit") or {}
    assert int(exit_info.get("min_hold_sec") or 0) == 240
    assert int(exit_info.get("exit_confirm_ticks") or 0) == 1
    assert str(exit_info.get("monitor_guidance") or "") == "quick_take_profit"
    assert str(exit_info.get("risk_tone") or "") == "aggressive"
    assert str(exit_info.get("trade_aggressiveness") or "") == "high"


def test_monitor_uses_strategist_monitor_policy_over_env(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "1200")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "600")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "3")

    state = _base_state()
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 200}],
    }
    state["strategist_output"] = {
        "monitor_policy": {
            "min_hold_seconds": 0,
            "sell_cooldown_seconds": 30,
            "exit_confirm_ticks": 1,
        },
        "monitor_guidance": "quick_take_profit",
        "risk_tone": "normal",
        "trade_aggressiveness": "medium",
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    # Effective values come from strategist monitor_policy first, then strategy-frame adjustments.
    assert int(exit_info.get("min_hold_sec") or 0) <= 1
    assert int(exit_info.get("exit_confirm_ticks") or 0) == 1


def test_monitor_prefers_strategist_monitor_entry_policy_for_entry_thresholds(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.006, "engine_volume_spike20": 1.4},
        },
        "minute_ohlcv_by_symbol": {
            "BBB": [
                {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
                {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
                {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
                {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
                {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
                {"open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 900, "vwap": 101.2},
            ]
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
        "strategist_output": {
            "monitor_entry_policy": {
                "timeframe_minutes": 1,
                "breakout_lookback": 5,
                "volume_lookback": 5,
                "volume_ratio_min": 1.2,
                "max_extended_from_vwap_pct": 0.13,
                "pullback_min_pct": 0.008,
                "pullback_max_pct": 0.07,
                "reclaim_tolerance_pct": 0.0015,
                "breakout_buffer_pct": 0.0,
                "intent_cooldown_sec": 0,
                "require_vwap_reclaim": True,
                "require_rebound": True,
                "policy_source": "strategist",
            }
        },
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    monitor = out.get("monitor") or {}
    assert monitor.get("entry_triggered") is True
    assert monitor.get("entry_condition_path") == "breakout_path"
    applied_policy = monitor.get("entry_applied_policy") or {}
    contract = monitor.get("entry_policy_contract") or {}
    assert float(applied_policy.get("volume_ratio_min") or 0.0) > 0.68
    assert str(applied_policy.get("policy_source") or "") == "strategist"
    assert contract.get("selected_source") == "strategist_output.monitor_entry_policy"


def test_monitor_prefers_commander_applied_policy_over_strategist_monitor_entry_policy(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.006, "engine_volume_spike20": 1.4},
        },
        "minute_ohlcv_by_symbol": {
            "BBB": [
                {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
                {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
                {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
                {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
                {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
                {"open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 900, "vwap": 101.2},
            ]
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
        "commander_applied_policy": {
            "timeframe_minutes": 1,
            "breakout_lookback": 5,
            "volume_lookback": 5,
            "volume_ratio_min": 1.25,
            "max_extended_from_vwap_pct": 0.13,
            "pullback_min_pct": 0.008,
            "pullback_max_pct": 0.07,
            "reclaim_tolerance_pct": 0.0015,
            "breakout_buffer_pct": 0.0,
            "intent_cooldown_sec": 0,
            "require_vwap_reclaim": True,
            "require_rebound": True,
            "policy_source": "strategist",
            "threshold_policy": {
                "timeframe_minutes": 1,
                "breakout_lookback": 5,
                "volume_lookback": 5,
                "volume_ratio_min": 1.25,
                "max_extended_from_vwap_pct": 0.13,
                "pullback_min_pct": 0.008,
                "reclaim_tolerance_pct": 0.0015,
                "breakout_buffer_pct": 0.0,
                "intent_cooldown_sec": 0,
                "require_vwap_reclaim": True,
                "require_rebound": True,
                "policy_source": "strategist",
            },
            "interpretation_policy": {
                "entry_style": "breakout",
                "required_checks": ["volume_ok"],
                "preferred_checks": ["breakout_ok"],
                "relaxable_checks": ["reclaim_gate_ok"],
                "priority_hints": {"volume": "high", "breakout": "high"},
                "evidence_focus": {
                    "primary": ["breakout_ok", "volume_ok"],
                    "secondary": ["reclaim_gate_ok"],
                },
                "notes": ["explicit_breakout_policy"],
            },
        },
        "commander_applied_policy_meta": {
            "policy_source": "strategist",
            "policy_validation_status": "ok",
            "policy_fallback_used": False,
            "policy_fallback_reason": "",
            "override_reason": "",
            "applied_policy_source_chain": ["strategist", "validation", "commander_confirmed"],
        },
        "strategy_policy": {
            "market_policy": {},
            "scanner_policy": {},
            "monitor_policy": {
                "applied_policy": {
                    "timeframe_minutes": 1,
                    "volume_ratio_min": 1.25,
                    "pullback_min_pct": 0.008,
                    "policy_source": "strategist",
                    "threshold_policy": {
                        "timeframe_minutes": 1,
                        "volume_ratio_min": 1.25,
                        "pullback_min_pct": 0.008,
                        "policy_source": "strategist",
                    },
                    "interpretation_policy": {
                        "entry_style": "breakout",
                        "required_checks": ["volume_ok"],
                    },
                },
                "policy_source": "strategist",
                "policy_validation_status": "ok",
                "policy_fallback_used": False,
            },
            "decision_policy": {},
            "commander_context": {
                "applied_policy": {
                    "timeframe_minutes": 1,
                    "volume_ratio_min": 1.25,
                    "pullback_min_pct": 0.008,
                    "policy_source": "strategist",
                    "threshold_policy": {
                        "timeframe_minutes": 1,
                        "volume_ratio_min": 1.25,
                        "pullback_min_pct": 0.008,
                        "policy_source": "strategist",
                    },
                    "interpretation_policy": {
                        "entry_style": "breakout",
                        "required_checks": ["volume_ok"],
                    },
                },
                "policy_source": "strategist",
            },
        },
        "strategist_output": {
            "monitor_entry_policy": {
                "timeframe_minutes": 1,
                "breakout_lookback": 5,
                "volume_lookback": 5,
                "volume_ratio_min": 0.70,
                "max_extended_from_vwap_pct": 0.13,
                "pullback_min_pct": 0.008,
                "pullback_max_pct": 0.07,
                "reclaim_tolerance_pct": 0.0015,
                "breakout_buffer_pct": 0.0,
                "intent_cooldown_sec": 0,
                "require_vwap_reclaim": True,
                "require_rebound": True,
                "policy_source": "strategist",
            }
        },
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    monitor = out.get("monitor") or {}
    monitor_output = out.get("monitor_output") or {}
    applied_policy = monitor.get("entry_applied_policy") or {}
    received_policy = monitor.get("entry_received_policy") or {}
    effective_policy = monitor.get("entry_effective_policy") or {}
    contract = monitor.get("entry_policy_contract") or {}
    assert float(applied_policy.get("volume_ratio_min") or 0.0) > 0.70
    assert str(applied_policy.get("policy_source") or "") == "strategist"
    assert float(received_policy.get("volume_ratio_min") or 0.0) == 1.25
    assert str(monitor.get("entry_received_policy_source") or "") == "commander_applied_policy"
    assert float(effective_policy.get("volume_ratio_min") or 0.0) == float(applied_policy.get("volume_ratio_min") or 0.0)
    assert str(monitor.get("entry_effective_policy_source") or "") == "monitor_frame_adjusted"
    assert contract.get("contract_version") == "monitor_entry_policy_contract.v1"
    assert contract.get("selected_source") == "commander_applied_policy"
    assert (contract.get("selected_policy_schema") or {}).get("schema_version") == "monitor_entry_policy_schema_candidate.v1"
    assert (contract.get("selected_policy_schema") or {}).get("available") is True
    assert (contract.get("selected_policy_spec_health") or {}).get("schema_available") is True
    assert isinstance((contract.get("selected_policy_spec_health") or {}).get("normalized_policy_spec_count"), int)
    assert (contract.get("sources") or {}).get("strategist_output.monitor_entry_policy", {}).get("available") is True
    interpretation = monitor_output.get("policy_interpretation") or {}
    assert interpretation.get("policy_schema_available") is True
    assert interpretation.get("interpretation_basis") == "mixed"
    assert list(monitor.get("entry_effective_policy_deltas") or [])
    assert monitor.get("entry_triggered") is True
    assert monitor.get("entry_condition_path") == "breakout_path"


def test_monitor_records_wait_to_buy_transition_trace_for_reclaim_recovery(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    wait_state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 100.1,
            "features": {"engine_vwap_distance": -0.006, "engine_volume_spike20": 0.7},
        },
        "minute_ohlcv_by_symbol": {"BBB": _entry_wait_rows_reclaim()},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
        "strategist_output": {"playbook": "pullback"},
        "persisted_state": {},
    }

    wait_out = monitor_node(wait_state)
    wait_monitor = wait_out.get("monitor") or {}
    wait_trace = wait_monitor.get("entry_transition_trace") or {}

    assert wait_out.get("intents") == []
    assert wait_monitor.get("entry_triggered") is False
    assert wait_monitor.get("entry_reason") == "below_vwap_reclaim_not_ready"
    assert wait_trace.get("became_ready_this_cycle") is False
    assert wait_trace.get("last_blocking_axis") == "vwap_relationship"

    ready_state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.1,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.3},
        },
        "minute_ohlcv_by_symbol": {"BBB": _entry_ready_rows_reclaim()},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
        "strategist_output": {"playbook": "pullback"},
        "persisted_state": dict(wait_out.get("persisted_state") or {}),
    }

    ready_out = monitor_node(ready_state)
    intents = ready_out.get("intents") or []
    ready_monitor = ready_out.get("monitor") or {}
    ready_trace = ready_monitor.get("entry_transition_trace") or {}

    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    assert ready_monitor.get("entry_triggered") is True
    assert ready_monitor.get("entry_condition_path") == "pullback_volume_path"
    assert ready_trace.get("became_ready_this_cycle") is True
    assert ready_trace.get("last_blocking_axis") == "vwap_relationship"
    assert float(ready_trace.get("extended_from_vwap_improvement") or 0.0) > 0.0
    assert float(ready_trace.get("volume_ratio_improvement") or 0.0) > 0.0
    assert float(ready_trace.get("breakout_gap_improvement") or 0.0) > 0.0
    assert ready_trace.get("volume_recovery_recent") is True
    assert ready_trace.get("transition_happening_now") is True


def test_monitor_scoring_shadow_mode_preserves_legacy_buy_and_records_score(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.006, "engine_volume_spike20": 1.4},
        },
        "minute_ohlcv_by_symbol": {"BBB": _entry_breakout_rows()},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
        "applied_policy": {"monitor": {"entry": {"scoring": {"enabled": False, "shadow_mode": True, "entry_threshold": 8}}}},
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    monitor = out.get("monitor") or {}
    monitor_output = out.get("monitor_output") or {}

    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    assert monitor.get("entry_scoring_mode") == "shadow"
    assert monitor.get("entry_legacy_decision") == "BUY"
    assert monitor.get("entry_scoring_decision") == "WAIT"
    assert monitor.get("entry_score_passed") is False
    assert isinstance(monitor.get("entry_score_breakdown"), dict)
    assert isinstance(monitor.get("entry_policy_interpretation"), dict)
    assert isinstance(monitor.get("entry_signal_evidence"), dict)
    assert isinstance(monitor.get("entry_chart_structure_features"), dict)
    assert isinstance(monitor.get("entry_policy_interpreter_trace"), dict)
    assert isinstance(monitor.get("entry_policy_alignment_summary"), dict)
    assert isinstance(monitor.get("entry_policy_aware_gating"), dict)
    assert isinstance(monitor.get("entry_chart_structure_decision_hint"), dict)
    assert isinstance((monitor.get("entry_policy_interpretation") or {}).get("required_checks"), list)
    assert isinstance(monitor_output.get("policy_interpretation"), dict)
    assert isinstance(monitor_output.get("signal_evidence"), dict)
    assert isinstance(monitor_output.get("chart_structure_features"), dict)
    assert isinstance(monitor_output.get("policy_interpreter_trace"), dict)
    assert isinstance(monitor_output.get("policy_alignment_summary"), dict)
    assert isinstance(monitor_output.get("policy_aware_gating"), dict)
    assert isinstance(monitor_output.get("chart_structure_decision_hint"), dict)


def test_monitor_artifact_surfaces_entry_minute_and_chart_fields_top_level(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "600")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "run_id": "run-monitor-artifact-top-level",
        "started_at": "2026-04-08T01:00:00+00:00",
        "runtime_phase": "session",
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "005930",
            "price": 100.2,
            "features": {"engine_vwap_distance": 0.001, "engine_volume_spike20": 1.2},
        },
        "minute_ohlcv_by_symbol": {"005930": _entry_wait_rows_reclaim()},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.5, "hold_sec": 1200}],
        },
        "policy": {
            "use_exit_policy": True,
            "exit_policy": {"take_profit_pct": 0.1, "stop_loss_pct": 0.1},
        },
    }

    out = monitor_node(state)
    artifact = build_monitor_output_artifact(out)

    assert artifact["entry_minute_source_present"] is True
    assert artifact["entry_minute_source_used"] == "state.minute_ohlcv_by_symbol"
    assert isinstance(artifact["entry_minute_refetch_attempted"], bool)
    assert isinstance(artifact["entry_minute_refetch_succeeded"], bool)
    assert artifact["entry_minute_refetch_failure_reason"] == "skill_runner_unavailable"
    assert isinstance(artifact.get("entry_chart_structure_features"), dict)
    assert isinstance(artifact.get("policy_interpreter_trace"), dict)
    assert isinstance(artifact.get("policy_alignment_summary"), dict)


def test_monitor_scoring_enabled_no_longer_blocks_legacy_buy_when_score_below_threshold(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.006, "engine_volume_spike20": 1.4},
        },
        "minute_ohlcv_by_symbol": {"BBB": _entry_breakout_rows()},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
        "applied_policy": {"monitor": {"entry": {"scoring": {"enabled": True, "shadow_mode": False, "entry_threshold": 8}}}},
    }

    out = monitor_node(state)
    monitor = out.get("monitor") or {}

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    assert monitor.get("entry_scoring_mode") == "enabled"
    assert monitor.get("entry_legacy_decision") == "BUY"
    assert monitor.get("entry_scoring_decision") == "WAIT"
    assert monitor.get("entry_score_passed") is False
    assert monitor.get("entry_triggered") is True
    assert monitor.get("entry_reason") != "monitor_score_threshold_not_met"
    assert ((monitor.get("entry_signal_evidence") or {}).get("derived") or {}).get("weighted_score_passed") is False


def test_monitor_policy_aware_gating_can_promote_breakout_near_ready_reclaim(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    rows = _entry_breakout_rows()
    rows[-1]["vwap"] = 101.96

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": -0.0016, "engine_volume_spike20": 1.4},
        },
        "strategist_output": {"playbook": "breakout"},
        "minute_ohlcv_by_symbol": {"BBB": rows},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    monitor = out.get("monitor") or {}
    monitor_output = out.get("monitor_output") or {}

    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    assert monitor.get("entry_legacy_decision") == "WAIT"
    assert monitor.get("entry_triggered") is True
    assert monitor.get("entry_reason") == "breakout_above_recent_high_with_policy_reclaim_near_ready"
    assert ((monitor.get("entry_policy_aware_gating") or {}).get("applied")) is True
    assert "reclaim_gate_ok" in list(((monitor.get("entry_policy_aware_gating") or {}).get("relaxations_applied")) or [])
    assert isinstance(monitor_output.get("policy_aware_gating"), dict)
    assert (monitor_output.get("policy_aware_gating") or {}).get("applied") is True


def test_monitor_policy_aware_gating_surfaces_reclaim_tuning_provenance(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    rows = _entry_breakout_rows()
    rows[-1]["vwap"] = 102.12

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": -0.0031, "engine_volume_spike20": 1.4},
        },
        "strategist_output": {"playbook": "breakout"},
        "minute_ohlcv_by_symbol": {"BBB": rows},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
    }

    out = monitor_node(state)
    monitor = out.get("monitor") or {}
    monitor_output = out.get("monitor_output") or {}
    blocker_surface = dict(out.get("monitor_entry_blocker_surface") or monitor_output.get("entry_blocker_surface") or {})
    policy_gating = dict(monitor.get("entry_policy_aware_gating") or {})

    assert policy_gating.get("applied") is True
    assert policy_gating.get("reclaim_readiness_tuned") is True
    assert policy_gating.get("reclaim_tuning_version") == "small_relaxation_v1"
    assert policy_gating.get("reclaim_tuning_scope") == "below_vwap_reclaim_not_ready_only"
    assert "reclaim_small_relaxation_v1" in list(policy_gating.get("entry_tuning_flags") or [])
    assert blocker_surface.get("reclaim_readiness_tuned") is True
    assert blocker_surface.get("reclaim_tuning_version") == "small_relaxation_v1"
    assert blocker_surface.get("reclaim_tuning_scope") == "below_vwap_reclaim_not_ready_only"
    assert isinstance(monitor_output.get("entry_blocker_surface"), dict)
    assert isinstance(monitor_output.get("policy_aware_gating"), dict)


def test_monitor_records_received_vs_effective_policy_when_strategy_frame_tightens(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.006, "engine_volume_spike20": 1.4},
        },
        "minute_ohlcv_by_symbol": {
            "BBB": [
                {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
                {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
                {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
                {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
                {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
                {"open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 900, "vwap": 101.2},
            ]
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": _policy_with_entry_cooldown(0),
        "commander_applied_policy": {
            "timeframe_minutes": 1,
            "breakout_lookback": 5,
            "volume_lookback": 5,
            "volume_ratio_min": 0.68,
            "max_extended_from_vwap_pct": 0.13,
            "pullback_min_pct": 0.008,
            "pullback_max_pct": 0.07,
            "reclaim_tolerance_pct": 0.0015,
            "breakout_buffer_pct": 0.0,
            "intent_cooldown_sec": 0,
            "require_vwap_reclaim": True,
            "require_rebound": True,
            "policy_source": "strategist",
        },
        "strategy_policy": {
            "market_policy": {},
            "scanner_policy": {},
            "monitor_policy": {
                "applied_policy": {
                    "timeframe_minutes": 1,
                    "volume_ratio_min": 0.68,
                    "pullback_min_pct": 0.008,
                    "max_extended_from_vwap_pct": 0.13,
                    "policy_source": "strategist",
                },
                "policy_source": "strategist",
                "policy_validation_status": "partial_normalized",
                "policy_fallback_used": False,
                "policy_partial_normalized": True,
                "policy_default_filled_fields": ["enabled"],
                "policy_validation_missing_fields": ["enabled"],
                "policy_validation_invalid_fields": [],
            },
            "decision_policy": {},
            "commander_context": {
                "applied_policy": {
                    "timeframe_minutes": 1,
                    "volume_ratio_min": 0.68,
                    "pullback_min_pct": 0.008,
                    "max_extended_from_vwap_pct": 0.13,
                    "policy_source": "strategist",
                },
                "policy_source": "strategist",
                "policy_validation_status": "partial_normalized",
                "policy_fallback_used": False,
                "policy_partial_normalized": True,
                "policy_default_filled_fields": ["enabled"],
                "policy_validation_missing_fields": ["enabled"],
                "policy_validation_invalid_fields": [],
            },
        },
        "strategist_output": {
            "playbook": "defensive",
            "monitor_guidance": "defensive_exit",
            "risk_tone": "conservative",
            "trade_aggressiveness": "low",
        },
    }

    out = monitor_node(state)
    monitor = out.get("monitor") or {}
    output = out.get("monitor_output") or {}

    assert monitor.get("entry_received_policy", {}).get("volume_ratio_min") == 0.68
    assert round(float(monitor.get("entry_effective_policy", {}).get("volume_ratio_min") or 0.0), 2) == 0.75
    assert monitor.get("entry_effective_policy", {}).get("max_extended_from_vwap_pct") == 0.05
    assert output.get("policy_partial_normalized") is True
    assert output.get("policy_fallback_used") is False
    assert "enabled" in list(output.get("policy_default_filled_fields") or [])
    assert output.get("effective_policy_source") == "monitor_frame_adjusted"
    assert any((row or {}).get("field") == "volume_ratio_min" for row in list(output.get("effective_policy_deltas") or []))


def test_monitor_applies_strategist_exit_policy_over_env(monkeypatch):
    monkeypatch.setenv("EXIT_POLICY_STOP_LOSS_PCT", "0.01")
    monkeypatch.setenv("EXIT_POLICY_TAKE_PROFIT_PCT", "0.01")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = _base_state()
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 900}],
    }
    state["strategist_output"] = {
        "playbook": "breakout",
        "monitor_guidance": "hold_through_noise",
        "risk_tone": "aggressive",
        "trade_aggressiveness": "high",
        "exit_policy": {
            "stop_loss_pct": 0.025,
            "take_profit_pct": 0.060,
            "trailing_stop_pct": 0.020,
        },
    }

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    effective = exit_info.get("effective_exit_policy") or {}
    assert float(effective.get("stop_loss_pct") or 0.0) >= 0.025
    assert float(effective.get("take_profit_pct") or 0.0) >= 0.060
    assert float(effective.get("trailing_stop_pct") or 0.0) >= 0.020
    adjustments = exit_info.get("exit_policy_guard_adjustments") or []
    assert "strategist_exit_policy_override" in adjustments


def test_monitor_uses_strategy_policy_monitor_contract(monkeypatch):
    monkeypatch.setenv("EXIT_POLICY_STOP_LOSS_PCT", "0.01")
    monkeypatch.setenv("EXIT_POLICY_TAKE_PROFIT_PCT", "0.01")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "1200")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "600")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "3")

    state = _base_state()
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 200}],
    }
    state["selected"]["price"] = 68000.0
    state["strategist_output"] = {
        "strategy_policy": {
            "market_policy": {
                "playbook": "breakout",
                "monitor_guidance": "quick_take_profit",
                "risk_tone": "aggressive",
                "trade_aggressiveness": "high",
            },
            "monitor_policy": {
                "position_guards": {
                    "min_hold_seconds": 0,
                    "sell_cooldown_seconds": 30,
                    "exit_confirm_ticks": 1,
                },
                "adaptive_exit": {
                    "stop_loss_pct": 0.025,
                    "take_profit_pct": 0.060,
                    "trailing_stop_pct": 0.020,
                },
                "hard_risk_rails": {
                    "hard_stop_pct": 0.01,
                    "max_stop_pct_cap": 0.03,
                },
            },
        }
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    monitor_output = out.get("monitor_output") or {}
    effective = exit_info.get("effective_exit_policy") or {}
    thresholds = exit_info.get("thresholds") or {}
    assert float(effective.get("stop_loss_pct") or 0.0) >= 0.02
    assert float(effective.get("stop_loss_pct") or 0.0) <= 0.03
    assert float(effective.get("hard_stop_pct") or 0.0) == 0.01
    assert int(exit_info.get("exit_confirm_ticks") or 0) == 1
    assert str(exit_info.get("monitor_guidance") or "") == "quick_take_profit"
    assert float(thresholds.get("effective_stop_loss_pct") or 0.0) == 0.01
    assert str(thresholds.get("effective_stop_reason") or "") == "hard_stop"
    adjustments = exit_info.get("exit_policy_guard_adjustments") or []
    assert "strategist_exit_policy_override" in adjustments
    contract = monitor_output.get("policy_contract") or {}
    assert contract.get("contract_version") == "monitor_entry_policy_contract.v1"
    assert contract.get("selected_source") == "monitor_policy"
    assert contract.get("available") is False
    assert (contract.get("selected_policy_schema") or {}).get("schema_version") == "monitor_entry_policy_schema_candidate.v1"
    assert (contract.get("selected_policy_schema") or {}).get("available") is False
    assert (contract.get("selected_policy_spec_health") or {}).get("schema_available") is False


def test_monitor_hard_stop_triggers_before_wider_adaptive_stop(monkeypatch):
    monkeypatch.setenv("EXIT_POLICY_STOP_LOSS_PCT", "0.08")
    monkeypatch.setenv("EXIT_POLICY_TAKE_PROFIT_PCT", "0.02")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = _base_state()
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 900}],
    }
    state["selected"]["price"] = 69160.0
    state["strategist_output"] = {
        "strategy_policy": {
            "market_policy": {
                "playbook": "pullback",
                "monitor_guidance": "hold_through_noise",
                "risk_tone": "normal",
                "trade_aggressiveness": "medium",
            },
            "monitor_policy": {
                "adaptive_exit": {
                    "stop_loss_pct": 0.08,
                    "take_profit_pct": 0.03,
                    "trailing_stop_pct": 0.02,
                },
                "hard_risk_rails": {
                    "hard_stop_pct": 0.01,
                    "max_stop_pct_cap": 0.08,
                },
            },
        }
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert str(intents[0]["meta"].get("exit_reason") or "") == "hard_stop"
    exit_info = out.get("monitor_exit") or {}
    effective = exit_info.get("effective_exit_policy") or {}
    thresholds = exit_info.get("thresholds") or {}
    assert str(exit_info.get("reason") or "") == "hard_stop"
    assert float(effective.get("stop_loss_pct") or 0.0) >= 0.08
    assert float(effective.get("hard_stop_pct") or 0.0) == 0.01
    assert float(thresholds.get("effective_stop_loss_pct") or 0.0) == 0.01


def test_monitor_peak_drawdown_exit_uses_persisted_peak(monkeypatch):
    state = _with_commander_numeric_policy(
        _base_state(),
        min_hold_seconds=0,
        sell_sec=0,
        confirm_ticks=1,
    )
    state["selected"]["price"] = 104.0
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 900}],
    }
    state["persisted_state"] = {
        "position_peak_price": {"005930": 110.0},
    }
    state["policy"] = {
        "use_exit_policy": True,
        "peak_drawdown_exit_pct": 0.05,
        "take_profit_pct": 0.0,
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    assert str(exit_info.get("reason") or "") == "peak_drawdown"
    assert bool(exit_info.get("hard_exit")) is False
    assert bool(exit_info.get("peak_drawdown_armed")) is True
    assert float(exit_info.get("peak_drawdown") or 0.0) <= -0.05
    assert float(exit_info.get("max_runup_pct") or 0.0) >= 0.08
    assert float(exit_info.get("final_peak_drawdown_ratio") or 0.0) <= -0.05
    assert str(exit_info.get("peak_drawdown_source") or "") == "effective_price_vs_peak_price"
    assert str(exit_info.get("exit_trigger_metric_name") or "") == "peak_drawdown_ratio"
    assert float(exit_info.get("exit_trigger_metric_value") or 0.0) <= -0.05
    assert str(exit_info.get("exit_trigger_metric_source") or "") == "effective_price_vs_peak_price"
    artifact = build_monitor_output_artifact(out)
    assert float(artifact.get("final_peak_drawdown_ratio") or 0.0) <= -0.05
    assert str(artifact.get("peak_drawdown_source") or "") == "effective_price_vs_peak_price"
    assert str(artifact.get("exit_trigger_metric_name") or "") == "peak_drawdown_ratio"
    assert float(artifact.get("exit_trigger_metric_value") or 0.0) <= -0.05


def test_monitor_peak_drawdown_requires_confirmation_and_does_not_bypass_guard(monkeypatch):
    state = _with_commander_numeric_policy(
        _base_state(),
        min_hold_seconds=0,
        sell_sec=0,
        confirm_ticks=2,
    )
    state["selected"]["price"] = 104.0
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 900}],
    }
    state["persisted_state"] = {
        "position_peak_price": {"005930": 110.0},
    }
    state["policy"] = {
        "use_exit_policy": True,
        "peak_drawdown_exit_pct": 0.05,
        "profit_protection_activation_pct": 0.08,
        "take_profit_pct": 0.0,
    }

    out1 = monitor_node(state)
    assert out1.get("intents") == []
    exit1 = out1.get("monitor_exit") or {}
    assert str(exit1.get("reason") or "").startswith("exit_confirmation_pending:")
    assert "peak_drawdown:exit_confirmation_pending" in str(exit1.get("hold_block_reason") or "")
    assert bool(exit1.get("hard_exit")) is False
    assert bool(exit1.get("sell_guard_blocked")) is True
    assert "exit_confirmation_pending:1/2" in str(exit1.get("sell_guard_reason") or "")

    out2 = monitor_node(out1)
    intents = out2.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit2 = out2.get("monitor_exit") or {}
    assert str(exit2.get("reason") or "") == "peak_drawdown"
    assert bool(exit2.get("hard_exit")) is False
    assert int(exit2.get("exit_confirm_count") or 0) >= 2


def _entry_cascade_test_state() -> dict:
    return {
        "plan": {"thesis": "cascade test"},
        "selected": {"symbol": "AAA", "price": 100.0, "features": {"candidate_symbol": "AAA"}},
        "ranked_candidates": [
            {"symbol": "AAA", "price": 100.0, "score_total": 1.0},
            {"symbol": "BBB", "price": 101.0, "score_total": 0.95},
            {"symbol": "CCC", "price": 102.0, "score_total": 0.9},
        ],
        "scanner_output": {"quote_data_diagnostic": {"zero_quote_metric_symbols": []}},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": {"use_exit_policy": False},
        "tick_ts": 1772850000,
    }


def test_monitor_falls_back_to_runner_up_when_top_pick_waits(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    def _fake_selected(state, symbol, selected, *, position=None):
        row = dict(selected or {})
        row["symbol"] = symbol
        row["price"] = row.get("price") or 100.0
        row["features"] = {"candidate_symbol": symbol}
        return row

    def _fake_minute(state, symbol, timeframe_minutes, now_epoch, prefer_fresh_runner=False):
        rows = dict(state.get("minute_ohlcv_by_symbol") or {})
        rows[str(symbol)] = [{"ts": int(now_epoch), "close": 100.0, "vwap": 99.8, "volume": 1000}]
        state["minute_ohlcv_by_symbol"] = rows
        state["monitor_minute_ohlcv_fetch"] = {}
        return state

    def _fake_entry(rows, current_price, features, policy, scoring, frame, policy_contract):
        sym = str((features or {}).get("candidate_symbol") or "")
        base = {
            "enabled": True,
            "evaluated": True,
            "thresholds": {"intent_cooldown_sec": 0},
            "metrics": {"current_price": current_price},
            "failed_checks": [],
            "passed_checks": [],
            "signal_chain": [],
            "hard_filter_passed": True,
            "score_passed": False,
            "legacy_entry_decision": "WAIT",
            "scoring_entry_decision": "WAIT",
        }
        if sym == "AAA":
            return {**base, "triggered": False, "reason": "too_extended_from_vwap"}
        if sym == "BBB":
            return {
                **base,
                "triggered": True,
                "reason": "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation",
                "pattern": "breakout",
                "score_passed": True,
                "legacy_entry_decision": "BUY",
                "scoring_entry_decision": "BUY",
            }
        return {**base, "triggered": False, "reason": "breakout_not_ready"}

    monkeypatch.setattr("graphs.nodes.monitor_node._monitor_selected_snapshot_for_symbol", _fake_selected)
    monkeypatch.setattr("graphs.nodes.monitor_node._ensure_monitor_minute_ohlcv_for_symbol", _fake_minute)
    monkeypatch.setattr("graphs.nodes.monitor_node.evaluate_intraday_entry_signal", _fake_entry)
    monkeypatch.setattr(
        "graphs.nodes.monitor_node._resolve_entry_closeout_window_guard",
        lambda state, policy: {"active": False, "minutes_to_close": 120, "cutoff_min": 10},
    )

    out = monitor_node(_entry_cascade_test_state())

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["symbol"] == "BBB"
    assert (out.get("selected") or {}).get("symbol") == "BBB"
    cascade = (out.get("monitor_output") or {}).get("entry_candidate_cascade") or {}
    assert cascade.get("attempted") is True
    assert cascade.get("fallback_used") is True
    assert cascade.get("fallback_from_symbol") == "AAA"
    assert cascade.get("fallback_to_symbol") == "BBB"
    handoff = out.get("scanner_monitor_handoff") or {}
    assert handoff.get("scanner_selected_symbol") == "AAA"
    assert handoff.get("monitor_selected_symbol") == "BBB"


def test_monitor_falls_back_to_runner_up_when_top_pick_reclaim_waits(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    def _fake_selected(state, symbol, selected, *, position=None):
        row = dict(selected or {})
        row["symbol"] = symbol
        row["price"] = row.get("price") or 100.0
        row["features"] = {"candidate_symbol": symbol}
        return row

    def _fake_minute(state, symbol, timeframe_minutes, now_epoch, prefer_fresh_runner=False):
        rows = dict(state.get("minute_ohlcv_by_symbol") or {})
        rows[str(symbol)] = [{"ts": int(now_epoch), "close": 100.0, "vwap": 99.8, "volume": 1000}]
        state["minute_ohlcv_by_symbol"] = rows
        state["monitor_minute_ohlcv_fetch"] = {}
        return state

    def _fake_entry(rows, current_price, features, policy, scoring, frame, policy_contract):
        sym = str((features or {}).get("candidate_symbol") or "")
        base = {
            "enabled": True,
            "evaluated": True,
            "thresholds": {"intent_cooldown_sec": 0},
            "metrics": {"current_price": current_price},
            "failed_checks": [],
            "passed_checks": [],
            "signal_chain": [],
            "hard_filter_passed": True,
            "score_passed": False,
            "legacy_entry_decision": "WAIT",
            "scoring_entry_decision": "WAIT",
        }
        if sym == "AAA":
            return {**base, "triggered": False, "reason": "below_vwap_reclaim_not_ready"}
        if sym == "BBB":
            return {
                **base,
                "triggered": True,
                "reason": "pullback_rebound_above_vwap_with_volume_confirmation",
                "pattern": "pullback",
                "score_passed": True,
                "legacy_entry_decision": "BUY",
                "scoring_entry_decision": "BUY",
            }
        return {**base, "triggered": False, "reason": "breakout_not_ready"}

    monkeypatch.setattr("graphs.nodes.monitor_node._monitor_selected_snapshot_for_symbol", _fake_selected)
    monkeypatch.setattr("graphs.nodes.monitor_node._ensure_monitor_minute_ohlcv_for_symbol", _fake_minute)
    monkeypatch.setattr("graphs.nodes.monitor_node.evaluate_intraday_entry_signal", _fake_entry)
    monkeypatch.setattr(
        "graphs.nodes.monitor_node._resolve_entry_closeout_window_guard",
        lambda state, policy: {"active": False, "minutes_to_close": 120, "cutoff_min": 10},
    )

    out = monitor_node(_entry_cascade_test_state())

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["symbol"] == "BBB"
    cascade = (out.get("monitor_output") or {}).get("entry_candidate_cascade") or {}
    assert cascade.get("attempted") is True
    assert cascade.get("fallback_used") is True
    assert cascade.get("fallback_from_symbol") == "AAA"
    assert cascade.get("fallback_to_symbol") == "BBB"


def test_monitor_does_not_fallback_when_open_position_exists(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    monkeypatch.setattr(
        "graphs.nodes.monitor_node._monitor_selected_snapshot_for_symbol",
        lambda state, symbol, selected, *, position=None: {
            "symbol": symbol,
            "price": 100.0,
            "features": {"candidate_symbol": symbol},
        },
    )
    monkeypatch.setattr(
        "graphs.nodes.monitor_node._ensure_monitor_minute_ohlcv_for_symbol",
        lambda state, symbol, timeframe_minutes, now_epoch, prefer_fresh_runner=False: state,
    )
    monkeypatch.setattr(
        "graphs.nodes.monitor_node._resolve_entry_closeout_window_guard",
        lambda state, policy: {"active": False, "minutes_to_close": 120, "cutoff_min": 10},
    )

    def _fake_entry(rows, current_price, features, policy, scoring, frame, policy_contract):
        sym = str((features or {}).get("candidate_symbol") or "")
        if sym == "AAA":
            return {"enabled": True, "evaluated": True, "triggered": False, "reason": "too_extended_from_vwap", "thresholds": {"intent_cooldown_sec": 0}}
        return {"enabled": True, "evaluated": True, "triggered": True, "reason": "breakout", "pattern": "breakout", "thresholds": {"intent_cooldown_sec": 0}}

    monkeypatch.setattr("graphs.nodes.monitor_node.evaluate_intraday_entry_signal", _fake_entry)

    state = _entry_cascade_test_state()
    state["portfolio_snapshot"] = {"cash": 2_000_000.0, "positions": [{"symbol": "ZZZ", "qty": 1, "avg_price": 10.0, "hold_sec": 30}]}
    out = monitor_node(state)

    assert out.get("intents") == []
    cascade = (out.get("monitor_output") or {}).get("entry_candidate_cascade") or {}
    assert cascade.get("attempted") is False
    assert cascade.get("blocked_reason") == "open_position_present"


def test_monitor_allows_zero_quote_metric_runner_up_and_reaches_third_candidate(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    def _fake_selected(state, symbol, selected, *, position=None):
        return {"symbol": symbol, "price": 100.0, "features": {"candidate_symbol": symbol}}

    monkeypatch.setattr("graphs.nodes.monitor_node._monitor_selected_snapshot_for_symbol", _fake_selected)
    monkeypatch.setattr(
        "graphs.nodes.monitor_node._ensure_monitor_minute_ohlcv_for_symbol",
        lambda state, symbol, timeframe_minutes, now_epoch, prefer_fresh_runner=False: state,
    )
    monkeypatch.setattr(
        "graphs.nodes.monitor_node._resolve_entry_closeout_window_guard",
        lambda state, policy: {"active": False, "minutes_to_close": 120, "cutoff_min": 10},
    )

    def _fake_entry(rows, current_price, features, policy, scoring, frame, policy_contract):
        sym = str((features or {}).get("candidate_symbol") or "")
        if sym == "AAA":
            return {"enabled": True, "evaluated": True, "triggered": False, "reason": "too_extended_from_vwap", "thresholds": {"intent_cooldown_sec": 0}}
        if sym == "BBB":
            return {"enabled": True, "evaluated": True, "triggered": False, "reason": "breakout_not_ready", "thresholds": {"intent_cooldown_sec": 0}}
        return {
            "enabled": True,
            "evaluated": True,
            "triggered": True,
            "reason": "breakout",
            "pattern": "breakout",
            "thresholds": {"intent_cooldown_sec": 0},
        }

    monkeypatch.setattr("graphs.nodes.monitor_node.evaluate_intraday_entry_signal", _fake_entry)

    state = _entry_cascade_test_state()
    state["scanner_output"] = {"quote_data_diagnostic": {"zero_quote_metric_symbols": ["BBB"]}}
    out = monitor_node(state)

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["symbol"] == "CCC"
    cascade = (out.get("monitor_output") or {}).get("entry_candidate_cascade") or {}
    assert cascade.get("fallback_to_symbol") == "CCC"
    warnings = list(cascade.get("warnings") or [])
    assert {"symbol": "BBB", "reason": "quote_metrics_missing_monitor_fallback_allowed"} in warnings
    skipped = list(cascade.get("skipped") or [])
    assert {"symbol": "BBB", "reason": "quote_metrics_missing"} not in skipped


def test_monitor_runner_up_prefers_fresh_minute_runner_when_primary_runner_is_empty(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    top_rows = [
        {"ts": 1710000300, "open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
        {"ts": 1710000360, "open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
        {"ts": 1710000420, "open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
        {"ts": 1710000480, "open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
        {"ts": 1710000540, "open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"ts": 1710000600, "open": 101.2, "high": 101.8, "low": 101.0, "close": 101.4, "volume": 1200, "vwap": 101.0},
    ]
    runner_rows = [
        {"ts": 1710000300, "open": 101.2, "high": 101.4, "low": 101.0, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"ts": 1710000360, "open": 101.2, "high": 101.4, "low": 100.9, "close": 101.1, "volume": 1100, "vwap": 101.0},
        {"ts": 1710000420, "open": 101.1, "high": 101.5, "low": 101.0, "close": 101.3, "volume": 1120, "vwap": 101.1},
        {"ts": 1710000480, "open": 101.3, "high": 101.6, "low": 101.1, "close": 101.4, "volume": 1150, "vwap": 101.2},
        {"ts": 1710000540, "open": 101.4, "high": 101.7, "low": 101.2, "close": 101.5, "volume": 1180, "vwap": 101.25},
        {"ts": 1710000600, "open": 101.5, "high": 102.0, "low": 101.3, "close": 101.8, "volume": 2500, "vwap": 101.4},
    ]
    primary_runner = _FakeMinuteSkillRunnerSequence([[]])
    fresh_runner = _FakeMinuteSkillRunnerSequence([runner_rows])
    monkeypatch.setattr("libs.skills.runner.CompositeSkillRunner.from_env", lambda: fresh_runner)

    def _fake_selected(state, symbol, selected, *, position=None):
        row = dict(selected or {})
        row["symbol"] = symbol
        row["price"] = row.get("price") or 100.0
        row["features"] = {"candidate_symbol": symbol}
        return row

    def _fake_entry(rows, current_price, features, policy, scoring, frame, policy_contract):
        sym = str((features or {}).get("candidate_symbol") or "")
        base = {
            "enabled": True,
            "evaluated": True,
            "thresholds": {"intent_cooldown_sec": 0},
            "metrics": {"current_price": current_price, "bar_count": len(rows or [])},
            "failed_checks": [],
            "passed_checks": [],
            "signal_chain": [],
            "hard_filter_passed": True,
            "score_passed": False,
            "legacy_entry_decision": "WAIT",
            "scoring_entry_decision": "WAIT",
        }
        if sym == "AAA":
            return {**base, "triggered": False, "reason": "too_extended_from_vwap"}
        if not rows:
            return {**base, "triggered": False, "reason": "minute_candle_missing"}
        return {
            **base,
            "triggered": True,
            "reason": "breakout",
            "pattern": "breakout",
            "score_passed": True,
            "legacy_entry_decision": "BUY",
            "scoring_entry_decision": "BUY",
        }

    monkeypatch.setattr("graphs.nodes.monitor_node._monitor_selected_snapshot_for_symbol", _fake_selected)
    monkeypatch.setattr("graphs.nodes.monitor_node.evaluate_intraday_entry_signal", _fake_entry)
    monkeypatch.setattr(
        "graphs.nodes.monitor_node._resolve_entry_closeout_window_guard",
        lambda state, policy: {"active": False, "minutes_to_close": 120, "cutoff_min": 10},
    )

    state = _entry_cascade_test_state()
    state["selected"] = {"symbol": "AAA", "price": 100.0, "features": {"candidate_symbol": "AAA"}}
    state["minute_ohlcv_by_symbol"] = {"AAA": list(top_rows)}
    state["skill_runner"] = primary_runner
    state["tick_ts"] = 1710000600
    out = monitor_node(state)

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["symbol"] == "BBB"
    assert primary_runner.call_count == 0
    assert fresh_runner.call_count == 1
    cascade = (out.get("monitor_output") or {}).get("entry_candidate_cascade") or {}
    assert cascade.get("fallback_to_symbol") == "BBB"


def test_monitor_runner_up_uses_recent_minute_history_when_refetch_returns_empty(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    top_rows = [
        {"ts": 1710000300, "open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
        {"ts": 1710000360, "open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
        {"ts": 1710000420, "open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
        {"ts": 1710000480, "open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
        {"ts": 1710000540, "open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"ts": 1710000600, "open": 101.2, "high": 101.8, "low": 101.0, "close": 101.4, "volume": 1200, "vwap": 101.0},
    ]
    runner_rows = [
        {"ts": 1710000300, "open": 101.2, "high": 101.4, "low": 101.0, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"ts": 1710000360, "open": 101.2, "high": 101.4, "low": 100.9, "close": 101.1, "volume": 1100, "vwap": 101.0},
        {"ts": 1710000420, "open": 101.1, "high": 101.5, "low": 101.0, "close": 101.3, "volume": 1120, "vwap": 101.1},
        {"ts": 1710000480, "open": 101.3, "high": 101.6, "low": 101.1, "close": 101.4, "volume": 1150, "vwap": 101.2},
        {"ts": 1710000540, "open": 101.4, "high": 101.7, "low": 101.2, "close": 101.5, "volume": 1180, "vwap": 101.25},
        {"ts": 1710000600, "open": 101.5, "high": 102.0, "low": 101.3, "close": 101.8, "volume": 2500, "vwap": 101.4},
    ]
    primary_runner = _FakeMinuteSkillRunnerSequence([[]])
    fresh_runner = _FakeMinuteSkillRunnerSequence([[]])
    monkeypatch.setattr("libs.skills.runner.CompositeSkillRunner.from_env", lambda: fresh_runner)

    def _fake_selected(state, symbol, selected, *, position=None):
        row = dict(selected or {})
        row["symbol"] = symbol
        row["price"] = row.get("price") or 100.0
        row["features"] = {"candidate_symbol": symbol}
        return row

    def _fake_entry(rows, current_price, features, policy, scoring, frame, policy_contract):
        sym = str((features or {}).get("candidate_symbol") or "")
        base = {
            "enabled": True,
            "evaluated": True,
            "thresholds": {"intent_cooldown_sec": 0},
            "metrics": {"current_price": current_price, "bar_count": len(rows or [])},
            "failed_checks": [],
            "passed_checks": [],
            "signal_chain": [],
            "hard_filter_passed": True,
            "score_passed": False,
            "legacy_entry_decision": "WAIT",
            "scoring_entry_decision": "WAIT",
        }
        if sym == "AAA":
            return {**base, "triggered": False, "reason": "too_extended_from_vwap"}
        if not rows:
            return {**base, "triggered": False, "reason": "minute_candle_missing"}
        return {
            **base,
            "triggered": True,
            "reason": "breakout",
            "pattern": "breakout",
            "score_passed": True,
            "legacy_entry_decision": "BUY",
            "scoring_entry_decision": "BUY",
        }

    monkeypatch.setattr("graphs.nodes.monitor_node._monitor_selected_snapshot_for_symbol", _fake_selected)
    monkeypatch.setattr("graphs.nodes.monitor_node.evaluate_intraday_entry_signal", _fake_entry)
    monkeypatch.setattr(
        "graphs.nodes.monitor_node._resolve_entry_closeout_window_guard",
        lambda state, policy: {"active": False, "minutes_to_close": 120, "cutoff_min": 10},
    )

    state = _entry_cascade_test_state()
    state["selected"] = {"symbol": "AAA", "price": 100.0, "features": {"candidate_symbol": "AAA"}}
    state["minute_ohlcv_by_symbol"] = {"AAA": list(top_rows)}
    state["skill_runner"] = primary_runner
    state["tick_ts"] = 1710000600
    state["skill_results_history"] = {
        "market.minute_ohlcv": [
            {
                "symbol": "BBB",
                "record": {
                    "result": {
                        "action": "ready",
                        "data": {
                            "rows": list(runner_rows),
                        },
                    }
                },
            }
        ]
    }
    out = monitor_node(state)

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["symbol"] == "BBB"
    metrics = (out.get("monitor") or {}).get("entry_metrics") or {}
    assert metrics.get("minute_cache_fallback_used") is True
    assert metrics.get("minute_cache_fallback_source") == "skill_results_history.minute_ohlcv"


def test_monitor_runner_up_uses_persisted_minute_cache_when_refetch_and_history_are_empty(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    top_rows = [
        {"ts": 1710000300, "open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
        {"ts": 1710000360, "open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
        {"ts": 1710000420, "open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
        {"ts": 1710000480, "open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
        {"ts": 1710000540, "open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"ts": 1710000600, "open": 101.2, "high": 101.8, "low": 101.0, "close": 101.4, "volume": 1200, "vwap": 101.0},
    ]
    runner_rows = [
        {"ts": 1710000300, "open": 101.2, "high": 101.4, "low": 101.0, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"ts": 1710000360, "open": 101.2, "high": 101.4, "low": 100.9, "close": 101.1, "volume": 1100, "vwap": 101.0},
        {"ts": 1710000420, "open": 101.1, "high": 101.5, "low": 101.0, "close": 101.3, "volume": 1120, "vwap": 101.1},
        {"ts": 1710000480, "open": 101.3, "high": 101.6, "low": 101.1, "close": 101.4, "volume": 1150, "vwap": 101.2},
        {"ts": 1710000540, "open": 101.4, "high": 101.7, "low": 101.2, "close": 101.5, "volume": 1180, "vwap": 101.25},
        {"ts": 1710000600, "open": 101.5, "high": 102.0, "low": 101.3, "close": 101.8, "volume": 2500, "vwap": 101.4},
    ]
    primary_runner = _FakeMinuteSkillRunnerSequence([[]])
    fresh_runner = _FakeMinuteSkillRunnerSequence([[]])
    monkeypatch.setattr("libs.skills.runner.CompositeSkillRunner.from_env", lambda: fresh_runner)

    def _fake_selected(state, symbol, selected, *, position=None):
        row = dict(selected or {})
        row["symbol"] = symbol
        row["price"] = row.get("price") or 100.0
        row["features"] = {"candidate_symbol": symbol}
        return row

    def _fake_entry(rows, current_price, features, policy, scoring, frame, policy_contract):
        sym = str((features or {}).get("candidate_symbol") or "")
        base = {
            "enabled": True,
            "evaluated": True,
            "thresholds": {"intent_cooldown_sec": 0},
            "metrics": {"current_price": current_price, "bar_count": len(rows or [])},
            "failed_checks": [],
            "passed_checks": [],
            "signal_chain": [],
            "hard_filter_passed": True,
            "score_passed": False,
            "legacy_entry_decision": "WAIT",
            "scoring_entry_decision": "WAIT",
        }
        if sym == "AAA":
            return {**base, "triggered": False, "reason": "too_extended_from_vwap"}
        if not rows:
            return {**base, "triggered": False, "reason": "minute_candle_missing"}
        return {
            **base,
            "triggered": True,
            "reason": "breakout",
            "pattern": "breakout",
            "score_passed": True,
            "legacy_entry_decision": "BUY",
            "scoring_entry_decision": "BUY",
        }

    monkeypatch.setattr("graphs.nodes.monitor_node._monitor_selected_snapshot_for_symbol", _fake_selected)
    monkeypatch.setattr("graphs.nodes.monitor_node.evaluate_intraday_entry_signal", _fake_entry)
    monkeypatch.setattr(
        "graphs.nodes.monitor_node._resolve_entry_closeout_window_guard",
        lambda state, policy: {"active": False, "minutes_to_close": 120, "cutoff_min": 10},
    )

    state = _entry_cascade_test_state()
    state["selected"] = {"symbol": "AAA", "price": 100.0, "features": {"candidate_symbol": "AAA"}}
    state["minute_ohlcv_by_symbol"] = {"AAA": list(top_rows)}
    state["skill_runner"] = primary_runner
    state["tick_ts"] = 1710000600
    state["persisted_state"] = {
        "recent_minute_ohlcv_by_symbol": {
            "BBB": {
                "symbol": "BBB",
                "rows": list(runner_rows),
                "latest_candle_ts": 1710000600,
                "timeframe_minutes": 1,
                "stored_epoch": 1710000600,
            }
        }
    }

    out = monitor_node(state)

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["symbol"] == "BBB"
    metrics = (out.get("monitor") or {}).get("entry_metrics") or {}
    assert metrics.get("minute_cache_fallback_used") is True
    assert metrics.get("minute_cache_fallback_source") == "persisted_state.recent_minute_ohlcv_by_symbol"


def test_monitor_peak_drawdown_respects_min_hold_guard(monkeypatch):
    state = _with_commander_numeric_policy(
        _base_state(),
        min_hold_seconds=600,
        sell_sec=0,
        confirm_ticks=1,
    )
    state["selected"]["price"] = 104.0
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 120}],
    }
    state["persisted_state"] = {
        "position_peak_price": {"005930": 110.0},
    }
    state["policy"] = {
        "use_exit_policy": True,
        "peak_drawdown_exit_pct": 0.05,
        "profit_protection_activation_pct": 0.08,
        "take_profit_pct": 0.0,
    }

    out = monitor_node(state)
    assert out.get("intents") == []
    exit_info = out.get("monitor_exit") or {}
    assert str(exit_info.get("reason") or "").startswith("sell_guard_min_hold:")
    assert "peak_drawdown:sell_guard_min_hold" in str(exit_info.get("hold_block_reason") or "")
    assert bool(exit_info.get("hard_exit")) is False
    assert bool(exit_info.get("min_hold_blocked")) is True
    assert bool(exit_info.get("sell_guard_blocked")) is True
    assert "sell_guard_min_hold" in str(exit_info.get("sell_guard_reason") or "")


def test_monitor_vwap_breakdown_exit_uses_feature_signal(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = _base_state()
    state["selected"] = {
        "symbol": "005930",
        "price": 101.0,
        "features": {"engine_vwap_distance": -0.01},
    }
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 900}],
    }
    state["persisted_state"] = {
        "position_peak_price": {"005930": 102.0},
    }
    state["policy"] = {
        "use_exit_policy": True,
        "vwap_breakdown_pct": 0.005,
        "take_profit_pct": 0.0,
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    assert str(exit_info.get("reason") or "") == "vwap_breakdown"
    assert float(exit_info.get("vwap_distance") or 0.0) == -0.01


def test_monitor_intraday_low_break_exit_uses_ohlcv_structure(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    candles = [
        {"open": 100.0, "high": 100.5, "low": 99.8, "close": 100.2, "volume": 100000},
        {"open": 100.2, "high": 100.4, "low": 99.5, "close": 99.7, "volume": 120000},
        {"open": 99.7, "high": 99.9, "low": 98.7, "close": 98.8, "volume": 130000},
    ]
    state = _base_state()
    state["selected"] = {"symbol": "005930", "price": 98.8}
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 900}],
    }
    state["ohlcv_by_symbol"] = {"005930": candles}
    state["policy"] = {
        "use_exit_policy": True,
        "intraday_low_break_pct": 0.001,
        "take_profit_pct": 0.0,
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    assert str(exit_info.get("reason") or "") == "intraday_low_break"


def test_monitor_trend_breakdown_exit_uses_feature_signal(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = _base_state()
    state["selected"] = {
        "symbol": "005930",
        "price": 100.5,
        "features": {
            "engine_trend_strength": -0.25,
            "engine_vwap_distance": -0.01,
        },
    }
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 900}],
    }
    state["policy"] = {
        "use_exit_policy": True,
        "trend_strength_floor": -0.10,
        "take_profit_pct": 0.0,
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    assert str(exit_info.get("reason") or "") == "trend_breakdown"
    assert float(exit_info.get("vwap_distance") or 0.0) == -0.01


def test_monitor_exit_policy_prefers_commander_carry_overrides():
    state = _base_state()
    state["selected"] = {
        "symbol": "005930",
        "price": 99.4,
        "features": {
            "engine_trend_strength": -0.11,
            "engine_vwap_distance": -0.01,
        },
    }
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 900}],
    }
    state["policy"] = {
        "use_exit_policy": True,
        "hard_stop_pct": 0.03,
        "intraday_low_break_pct": 0.003,
        "trend_strength_floor": -0.20,
        "vwap_break_requires_profit": True,
        "take_profit_pct": 0.0,
    }
    state["applied_policy"] = {
        "monitor": {
            "exit": {
                "policy_overrides": {
                    "vwap_break_requires_profit": False,
                    "hard_stop_pct": 0.015,
                    "intraday_low_break_pct": 0.001,
                    "trend_strength_floor": -0.10,
                }
            }
        }
    }

    out = monitor_node(state)
    effective = (out.get("monitor_exit") or {}).get("effective_exit_policy") or {}
    assert bool(effective.get("vwap_break_requires_profit")) is False
    assert float(effective.get("hard_stop_pct") or 0.0) == 0.015
    assert float(effective.get("intraday_low_break_pct") or 0.0) == 0.001
    assert float(effective.get("trend_strength_floor") or 0.0) == -0.10


def test_monitor_extract_frame_reads_strategist_output():
    state = {
        "strategist_output": {
            "playbook": "defensive",
            "monitor_guidance": "defensive_exit",
            "risk_tone": "conservative",
            "trade_aggressiveness": "low",
        }
    }
    frame = _extract_monitor_strategy_frame(state)

    assert frame["playbook"] == "defensive"
    assert frame["monitor_guidance"] == "defensive_exit"
    assert frame["risk_tone"] == "conservative"
    assert frame["trade_aggressiveness"] == "low"


def test_monitor_extract_frame_includes_commander_context_and_strategist_plan():
    state = {
        "strategist_output": {
            "playbook": "defensive",
            "monitor_guidance": "defensive_exit",
            "risk_tone": "conservative",
            "trade_aggressiveness": "low",
            "strategy_policy": {
                "commander_context": {
                    "monitor_mission": "Wait for confirmation and protect downside.",
                    "flow_instruction": "observe_only",
                    "command_intent": "OBSERVE_ONLY",
                    "risk_mode": "balanced",
                    "no_trade_reason_code": "WAIT_FOR_CONFIRMATION",
                    "llm_policy": "SKIP",
                    "source_priority": ["shadow_commander", "runtime_observation", "strategist_fallback"],
                    "shadow_used": True,
                    "strategist_fallback_used": False,
                },
                "strategist_plan": {
                    "selected_playbook": "defensive",
                    "entry_plan": {"pattern": "wait_for_vwap_reclaim"},
                    "exit_plan": {"trigger": "vwap_breakdown"},
                    "symbol_constraints": {"max_gap_pct": 0.03},
                    "strategy_summary": "Prefer patience until confirmation arrives.",
                },
                "provenance": {
                    "shadow_used": True,
                    "strategist_fallback_used": False,
                },
            },
        }
    }

    frame = _extract_monitor_strategy_frame(state)

    assert frame["playbook"] == "defensive"
    assert frame["commander_context"]["monitor_mission"] == "Wait for confirmation and protect downside."
    assert frame["strategist_plan"]["selected_playbook"] == "defensive"
    assert frame["policy_provenance"]["shadow_used"] is True


def test_monitor_output_records_commander_context_consumption_without_overriding_wait(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": {},
        "strategist_output": {
            "playbook": "pullback",
            "monitor_guidance": "quick_take_profit",
            "risk_tone": "normal",
            "trade_aggressiveness": "medium",
            "strategy_policy": {
                "market_policy": {},
                "scanner_policy": {},
                "monitor_policy": {},
                "decision_policy": {},
                "commander_context": {
                    "monitor_mission": "Observe and wait for confirmation.",
                    "flow_instruction": "observe_only",
                    "command_intent": "OBSERVE_ONLY",
                    "risk_mode": "balanced",
                    "no_trade_reason_code": "WAIT_FOR_CONFIRMATION",
                    "llm_policy": "SKIP",
                    "source_priority": ["shadow_commander", "runtime_observation", "strategist_fallback"],
                    "shadow_used": True,
                    "strategist_fallback_used": False,
                },
                "strategist_plan": {
                    "selected_playbook": "pullback",
                    "entry_plan": {"pattern": "wait_for_vwap_reclaim"},
                    "exit_plan": {"trigger": "prior_low_break"},
                    "symbol_constraints": {"max_gap_pct": 0.03},
                    "strategy_summary": "Wait for reclaim before entry.",
                },
                "provenance": {
                    "shadow_used": True,
                    "strategist_fallback_used": False,
                },
            },
        },
    }

    out = monitor_node(state)
    monitor_output = out.get("monitor_output") or {}
    entry_detail = out.get("monitor_entry_decision_detail") or {}
    evaluation = out.get("monitor_evaluation") or {}
    action = out.get("monitor_action_decision") or {}

    assert out.get("intents") == []
    assert str((out.get("monitor") or {}).get("entry_reason") or "") == "minute_candle_missing"
    assert monitor_output.get("commander_context_consumed") is True
    assert "monitor_mission" in list(monitor_output.get("consumed_fields") or [])
    assert monitor_output.get("policy_ref", {}).get("flow_instruction") == "observe_only"
    assert monitor_output.get("policy_ref", {}).get("selected_playbook") == "pullback"
    assert entry_detail.get("flow_instruction_applied") is True
    assert entry_detail.get("no_trade_reason_applied") is True
    assert entry_detail.get("policy_ref", {}).get("monitor_mission") == "Observe and wait for confirmation."
    assert evaluation.get("commander_context_consumed") is True
    assert action.get("shadow_used") is True
    assert action.get("strategist_fallback_used") is False
