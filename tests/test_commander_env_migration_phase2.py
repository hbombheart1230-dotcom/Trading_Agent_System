from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from graphs.commander_runtime import _run_integrated_chain
from graphs.nodes.decide_trade import (
    _resolve_exit_policy_config as resolve_decide_exit_policy_config,
    _resolve_min_hold_sec as resolve_decide_min_hold_sec,
    _resolve_post_exit_cooldown_sec as resolve_decide_post_exit_cooldown_sec,
    _resolve_sell_cooldown_sec as resolve_decide_sell_cooldown_sec,
)
from graphs.nodes.monitor_node import (
    _resolve_exit_confirm_ticks as resolve_monitor_exit_confirm_ticks,
    _resolve_min_hold_sec as resolve_monitor_min_hold_sec,
    _resolve_monitor_entry_scoring_config,
    _resolve_post_exit_cooldown_sec as resolve_monitor_post_exit_cooldown_sec,
    _resolve_sell_cooldown_sec as resolve_monitor_sell_cooldown_sec,
)
from graphs.nodes.scanner_node import _resolve_condition_limit, _resolve_top_candidate_pool
from graphs.nodes.strategist_node import _load_recent_strategy_feedback


_REMOVED_NUMERIC_ENV_KEYS = [
    "POST_EXIT_COOLDOWN_SEC",
    "EXIT_POLICY_EOD_FLAT_CUTOFF_MIN",
    "MIN_HOLD_SECONDS",
    "SELL_COOLDOWN_SEC",
    "MONITOR_EXIT_CONFIRM_TICKS",
    "TOP_CANDIDATE_POOL",
    "KIWOOM_CANDIDATE_CONDITION_LIMIT",
    "MONITOR_ENTRY_SCORE_THRESHOLD",
    "STRATEGY_MEMORY_RECENT_RUNS",
]


def _commander_numeric_policy(
    *,
    post_exit_sec: int = 180,
    sell_sec: int = 300,
    min_hold_seconds: int = 600,
    confirm_ticks: int = 2,
    eod_flat_cutoff_min: int = 10,
    top_pool: int = 30,
    condition_limit: int = 200,
    scoring_threshold: float = 3.0,
    recent_runs: int = 12,
) -> Dict[str, Any]:
    return {
        "execution": {
            "cooldowns": {
                "post_exit_sec": int(post_exit_sec),
                "sell_sec": int(sell_sec),
            }
        },
        "monitor": {
            "hold": {
                "min_hold_seconds": int(min_hold_seconds),
            },
            "exit": {
                "confirm_ticks": int(confirm_ticks),
                "eod_flat": {"cutoff_min": int(eod_flat_cutoff_min)},
            },
            "entry": {
                "scoring": {
                    "enabled": True,
                    "shadow_mode": False,
                    "threshold": float(scoring_threshold),
                }
            },
        },
        "scanner": {
            "candidate": {"top_pool": int(top_pool)},
            "kiwoom": {"condition_limit": int(condition_limit)},
        },
        "strategist": {
            "memory_feedback": {
                "enabled": True,
                "recent_runs": int(recent_runs),
            }
        },
    }


def test_commander_env_migration_phase2_removed_numeric_keys_absent_from_env_example() -> None:
    text = Path("config/.env.example").read_text(encoding="utf-8")
    for key in _REMOVED_NUMERIC_ENV_KEYS:
        assert key not in text, key


def test_commander_env_migration_phase2_doc_is_utf8_and_has_keywords() -> None:
    text = Path("docs/report_plan/commander_env_migration_phase2.md").read_text(encoding="utf-8")
    lowered = text.lower()
    for keyword in (
        "commander env migration phase 2",
        "removed numeric env keys",
        "canonical applied policy paths",
        "runtime semantics unchanged",
    ):
        assert keyword in lowered


def test_commander_injects_numeric_policy_defaults_into_applied_policy(monkeypatch) -> None:
    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        state["portfolio_snapshot"] = {"cash": 1_000_000.0, "positions": [], "_health": {"reader_ok": True}}
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        state["strategist_output"] = {"playbook": "pullback"}
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["selected"] = {"symbol": "005930"}
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        state["decision"] = "hold"
        return state

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain({}, execute_fn=lambda state: state)
    applied = out.get("applied_policy") or {}

    assert (((applied.get("execution") or {}).get("cooldowns") or {}).get("post_exit_sec") == 180)
    assert (((applied.get("execution") or {}).get("cooldowns") or {}).get("sell_sec") == 300)
    assert (((applied.get("monitor") or {}).get("hold") or {}).get("min_hold_seconds") == 600)
    assert (((applied.get("monitor") or {}).get("exit") or {}).get("confirm_ticks") == 2)
    assert ((((applied.get("monitor") or {}).get("exit") or {}).get("eod_flat") or {}).get("cutoff_min") == 10)
    assert (((applied.get("scanner") or {}).get("candidate") or {}).get("top_pool") == 30)
    assert (((applied.get("scanner") or {}).get("kiwoom") or {}).get("condition_limit") == 200)
    assert ((((applied.get("monitor") or {}).get("entry") or {}).get("scoring") or {}).get("threshold") == 3.0)
    assert (((applied.get("strategist") or {}).get("memory_feedback") or {}).get("recent_runs") == 12)

    commander_decision = out.get("commander_decision") or {}
    numeric_fields = (commander_decision.get("commander_applied_policy_summary") or {}).get("numeric_fields") or {}
    assert numeric_fields.get("post_exit_cooldown_sec") == 180
    assert numeric_fields.get("strategy_memory_recent_runs") == 12
    assert "execution.cooldowns.post_exit_sec" in list((commander_decision.get("policy_sources") or {}).get("commander_owned_numeric_fields") or [])


def test_numeric_consumers_read_applied_policy_without_env(monkeypatch) -> None:
    monkeypatch.delenv("TOP_N_CANDIDATES", raising=False)
    state = {
        "applied_policy": _commander_numeric_policy(
            post_exit_sec=420,
            sell_sec=120,
            min_hold_seconds=45,
            confirm_ticks=4,
            eod_flat_cutoff_min=7,
            top_pool=17,
            condition_limit=55,
            scoring_threshold=6.5,
        ),
        "policy": {"use_exit_policy": True},
    }

    assert resolve_monitor_min_hold_sec(state, {}) == 45
    assert resolve_monitor_sell_cooldown_sec(state, {}) == 120
    assert resolve_monitor_exit_confirm_ticks(state, {}) == 4
    assert resolve_monitor_post_exit_cooldown_sec(state, {}, {}) == 420
    assert resolve_decide_min_hold_sec(state) == 45
    assert resolve_decide_sell_cooldown_sec(state) == 120
    assert resolve_decide_post_exit_cooldown_sec(state) == 420
    assert resolve_decide_exit_policy_config(state).get("eod_flat_cutoff_min") == 7
    assert _resolve_top_candidate_pool(state, {}, candidate_limit=5) == 17
    assert _resolve_condition_limit(state, {}, top_pool=17) == 55

    scoring = _resolve_monitor_entry_scoring_config(state, {})
    assert scoring["threshold"] == 6.5
    assert scoring["entry_threshold"] == 6.5


def test_strategy_memory_recent_runs_reads_commander_applied_policy(monkeypatch) -> None:
    captured: Dict[str, Any] = {}

    def fake_build_recent_strategy_feedback(last_n_runs: int) -> Dict[str, Any]:
        captured["last_n_runs"] = int(last_n_runs)
        return {"feedback_window_size": int(last_n_runs)}

    monkeypatch.setattr("graphs.nodes.strategist_node.build_recent_strategy_feedback", fake_build_recent_strategy_feedback)

    feedback = _load_recent_strategy_feedback(
        {
            "applied_policy": {
                "strategist": {
                    "memory_feedback": {
                        "enabled": True,
                        "recent_runs": 9,
                        "policy_source": "commander_applied_policy",
                    }
                }
            }
        },
        {},
    )

    assert captured["last_n_runs"] == 9
    assert feedback["requested_window_size"] == 9
    assert feedback["policy_source"] == "commander_applied_policy"
