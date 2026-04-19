from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from graphs.nodes.strategist_node import strategist_node
from libs.performance.performance_aggregator import (
    aggregate_performance_from_reports_root,
    load_lifecycle_bundles,
    write_performance_summary,
)
from libs.performance.playbook_stats import calculate_playbook_stats, write_playbook_stats
from libs.performance.strategy_memory import build_strategy_memory, load_strategy_memory_hint, write_strategy_memory


def _write_bundle(
    reports_root: Path,
    *,
    day: str,
    trade_id: str,
    symbol: str,
    playbook: str,
    market_regime: str,
    return_pct: float,
    pnl: float,
) -> Path:
    trade_dir = reports_root / "trades" / day / trade_id
    trade_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "lifecycle_bundle.v1",
        "day": day,
        "trade_id": trade_id,
        "symbol": symbol,
        "run_id": f"run-{trade_id}",
        "lifecycle": {"entry": {"symbol": symbol}, "hold": [], "exit": {"symbol": symbol}},
        "strategist_summary": {"playbook": playbook, "market_regime": market_regime},
        "trade_outcome": {"return_pct": return_pct, "pnl": pnl},
    }
    path = trade_dir / "lifecycle_bundle.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_performance_aggregation_correctness(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-03-20"
    _write_bundle(
        reports_root,
        day=day,
        trade_id="TRD_20260320_005930_01",
        symbol="005930",
        playbook="breakout",
        market_regime="risk_on",
        return_pct=1.5,
        pnl=1200.0,
    )
    _write_bundle(
        reports_root,
        day=day,
        trade_id="TRD_20260320_000660_01",
        symbol="000660",
        playbook="pullback",
        market_regime="neutral",
        return_pct=-0.8,
        pnl=-500.0,
    )
    _write_bundle(
        reports_root,
        day=day,
        trade_id="TRD_20260320_035420_01",
        symbol="035420",
        playbook="breakout",
        market_regime="risk_on",
        return_pct=0.6,
        pnl=400.0,
    )

    summary = aggregate_performance_from_reports_root(reports_root, day=day)
    assert summary["total_trades"] == 3
    assert round(float(summary["win_rate"]), 6) == round(2.0 / 3.0, 6)
    assert "breakout" in (summary.get("per_playbook_stats") or {})
    assert (summary.get("per_symbol_stats") or {}).get("005930", {}).get("trade_count") == 1

    persisted = write_performance_summary(reports_root, day=day, summary=summary)
    assert Path((persisted.get("artifacts") or {}).get("summary_json") or "").exists()
    assert Path((persisted.get("artifacts") or {}).get("symbol_stats_json") or "").exists()


def test_playbook_stats_calculation(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-03-20"
    _write_bundle(
        reports_root,
        day=day,
        trade_id="TRD_20260320_005930_01",
        symbol="005930",
        playbook="breakout",
        market_regime="risk_on",
        return_pct=1.1,
        pnl=100.0,
    )
    _write_bundle(
        reports_root,
        day=day,
        trade_id="TRD_20260320_000660_01",
        symbol="000660",
        playbook="breakout",
        market_regime="risk_on",
        return_pct=-0.2,
        pnl=-20.0,
    )
    _write_bundle(
        reports_root,
        day=day,
        trade_id="TRD_20260320_035420_01",
        symbol="035420",
        playbook="pullback",
        market_regime="neutral",
        return_pct=-0.7,
        pnl=-40.0,
    )
    bundles = load_lifecycle_bundles(reports_root, day=day)
    payload = calculate_playbook_stats(bundles, day=day, recent_window=2)

    breakout = (payload.get("playbooks") or {}).get("breakout") or {}
    pullback = (payload.get("playbooks") or {}).get("pullback") or {}
    assert breakout.get("usage_count") == 2
    assert isinstance(breakout.get("recent_performance"), list)
    assert pullback.get("usage_count") == 1

    persisted = write_playbook_stats(reports_root, day=day, bundles=bundles, recent_window=2)
    assert Path(str(persisted.get("artifact_path") or "")).exists()


def test_strategy_memory_generation(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-03-20"
    reporter_dir = reports_root / "dev" / "analysis" / "reporter_analysis"
    reporter_dir.mkdir(parents=True, exist_ok=True)
    trade_explain_dir = reports_root / "dev" / "analysis" / "trade_explain"
    trade_explain_dir.mkdir(parents=True, exist_ok=True)
    (trade_explain_dir / f"trade_explain_{day}.json").write_text(
        json.dumps(
            {
                "schema_version": "trade_explain.v1",
                "day": day,
                "route_summary": {
                    "route_source": "canonical_commander",
                    "route_selected_total": {
                        "monitor_only": 7,
                        "cached_strategist": 2,
                        "full_cycle": 1,
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (reporter_dir / f"reporter_analysis_{day}.json").write_text(
        json.dumps(
            {
                "schema_version": "reporter_analysis.v1",
                "day": day,
                "ai_run_grade": "B+",
                "ai_summary": "Repeated monitor-only bias and reclaim blockers dominated the day.",
                "ai_root_causes": ["monitor_only bias persisted"],
                "ai_improvement_suggestions": ["tighten reclaim readiness gating"],
                "report_focus_targets": ["exit_quality", "theme_accuracy"],
                "scanner_evaluation": {
                    "selection_status": "needs_review",
                    "candidate_source_top": {"market_rank": 4, "fallback_pool": 1},
                },
                "monitor_evaluation": {
                    "monitor_status": "overtrading_risk",
                    "monitor_reason_top": {
                        "exit_signal_pending_confirmation": 5,
                        "repeated_hold_monitor_only": 3,
                    },
                },
                "supervisor_activity": {
                    "blocked_reason_top": {"notional_limit": 2, "allowlist_block": 1},
                },
                "incident_postmortem": {"incident_total": 2},
                "operator_facing_summary": {
                    "system_health": "YELLOW",
                    "recommended_actions": ["Review reclaim evidence before refreshing strategy frame."],
                },
                "source_reports": {
                    "trade_explain_json": str(trade_explain_dir / f"trade_explain_{day}.json"),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    summary = {
        "schema_version": "performance_summary.v1",
        "day": day,
        "per_market_regime_stats": {
            "risk_on": {"avg_return": 1.2, "win_rate": 0.8, "trade_count": 4},
            "risk_off": {"avg_return": -0.6, "win_rate": 0.2, "trade_count": 3},
        },
    }
    playbook = {
        "schema_version": "playbook_stats.v1",
        "day": day,
        "playbooks": {
            "breakout": {"usage_count": 5, "win_rate": 0.8, "avg_return": 0.9, "drawdown": 0.3, "stability_score": 0.87},
            "pullback": {"usage_count": 4, "win_rate": 0.2, "avg_return": -0.7, "drawdown": 1.2, "stability_score": 0.22},
        },
    }
    memory = build_strategy_memory(summary, playbook)
    assert "breakout" in (memory.get("best_playbooks") or [])
    assert "pullback" in (memory.get("worst_playbooks") or [])
    assert (memory.get("market_condition_bias") or {}).get("preferred_regimes")
    assert "breakout" in (memory.get("playbook_performance_snapshot") or {})

    persisted = write_strategy_memory(reports_root, day=day, summary=summary, playbook_stats=playbook)
    assert Path(str(persisted.get("artifact_path") or "")).exists()
    assert (persisted.get("reporter_analysis_digest") or {}).get("ai_run_grade") == "B+"

    loaded = load_strategy_memory_hint(reports_root=reports_root, day=day, auto_build=False)
    assert loaded.get("status") in {"ok", "empty"}
    assert isinstance(loaded.get("best_playbooks"), list)
    assert (loaded.get("reporter_analysis_digest") or {}).get("available") is True
    assert (loaded.get("reporter_analysis_digest") or {}).get("top_improvement_suggestions") == [
        "tighten reclaim readiness gating"
    ]
    assert (loaded.get("reporter_analysis_digest") or {}).get("system_health") == "YELLOW"
    assert (loaded.get("reporter_analysis_digest") or {}).get("report_focus_targets") == ["exit_quality", "theme_accuracy"]
    assert (loaded.get("reporter_analysis_digest") or {}).get("scanner_selection_status") == "needs_review"
    assert (loaded.get("reporter_analysis_digest") or {}).get("monitor_status") == "overtrading_risk"
    assert (loaded.get("reporter_analysis_digest") or {}).get("top_monitor_reasons") == [
        "exit_signal_pending_confirmation",
        "repeated_hold_monitor_only",
    ]
    assert (loaded.get("reporter_analysis_digest") or {}).get("top_scanner_sources") == ["market_rank", "fallback_pool"]
    assert (loaded.get("reporter_analysis_digest") or {}).get("top_supervisor_blockers") == ["notional_limit", "allowlist_block"]
    assert (loaded.get("reporter_analysis_digest") or {}).get("incident_total") == 2
    assert ((loaded.get("reporter_analysis_digest") or {}).get("route_mix") or {}).get("route_selected_total") == {
        "monitor_only": 7,
        "cached_strategist": 2,
        "full_cycle": 1,
    }
    assert ((loaded.get("reporter_analysis_digest") or {}).get("route_mix") or {}).get("monitor_only_ratio") == 0.7
    assert ((loaded.get("reporter_analysis_digest") or {}).get("route_mix") or {}).get("cached_strategist_ratio") == 0.2
    assert ((loaded.get("reporter_analysis_digest") or {}).get("route_mix") or {}).get("full_cycle_ratio") == 0.1


class _DummyLogger:
    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []

    def log(self, run_id: str, stage: str, event: str, payload: Dict[str, Any]) -> None:
        self.rows.append({"run_id": run_id, "stage": stage, "event": event, "payload": dict(payload or {})})


class _FakeRoute:
    def __init__(self, model: str) -> None:
        self.model = model


class _FakeRouterCaptureMessages:
    last_messages: List[Dict[str, Any]] = []

    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_FakeRouterCaptureMessages":
        _FakeRouterCaptureMessages.last_messages = []
        return _FakeRouterCaptureMessages()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _FakeRoute:
        return _FakeRoute(str((policy or {}).get("model") or "minimax/minimax-m2.5"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        _FakeRouterCaptureMessages.last_messages = [dict(row or {}) for row in list(messages or []) if isinstance(row, dict)]
        return (
            '{"market_regime":"risk_on","market_sentiment":"bullish","themes":["semiconductor"],'
            '"avoid_themes":["high_gap_speculative"],"playbook":"breakout","scanner_bias":"momentum",'
            '"scanner_priority":["momentum","trend_strength"],'
            '"trade_aggressiveness":"medium","risk_tone":"normal","monitor_guidance":"hold_through_noise",'
            '"report_focus":["theme_accuracy","exit_quality"]}'
        )


def test_strategist_includes_strategy_memory_hints(monkeypatch, tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-03-20"
    (reports_root / "performance" / day).mkdir(parents=True, exist_ok=True)
    reporter_dir = reports_root / "dev" / "analysis" / "reporter_analysis"
    reporter_dir.mkdir(parents=True, exist_ok=True)
    (reporter_dir / f"reporter_analysis_{day}.json").write_text(
        json.dumps(
            {
                "schema_version": "reporter_analysis.v1",
                "day": day,
                "ai_run_grade": "A",
                "ai_summary": "Breakout fit improved while pullback underperformed.",
                "ai_root_causes": ["pullback underperformance"],
                "ai_improvement_suggestions": ["prefer breakout in risk_on"],
                "operator_facing_summary": {
                    "recommended_actions": ["Prefer breakout playbooks in risk_on sessions."],
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (reports_root / "performance" / day / "strategy_memory.json").write_text(
        json.dumps(
            {
                "schema_version": "strategy_memory.v1",
                "day": day,
                "status": "ok",
                "best_playbooks": ["breakout"],
                "worst_playbooks": ["pullback"],
                "recent_failures": ["playbook:pullback"],
                "recent_success_patterns": ["playbook:breakout"],
                "playbook_performance_snapshot": {
                    "breakout": {"usage_count": 5, "win_rate": 0.8, "avg_return": 0.9, "stability_score": 0.87}
                },
                "market_condition_bias": {"preferred_regimes": ["risk_on"], "avoid_regimes": ["risk_off"]},
                "reporter_analysis_digest": {
                    "available": True,
                    "ai_run_grade": "A",
                    "ai_summary": "Breakout fit improved while pullback underperformed.",
                    "top_improvement_suggestions": ["prefer breakout in risk_on"],
                    "recommended_actions": ["Prefer breakout playbooks in risk_on sessions."],
                    "dominant_risks": ["pullback underperformance"],
                    "system_health": "GREEN",
                    "report_focus_targets": ["theme_accuracy", "exit_quality"],
                    "scanner_selection_status": "appropriate",
                    "monitor_status": "stable",
                    "top_monitor_reasons": ["hold_through_noise"],
                    "top_scanner_sources": ["market_rank"],
                    "top_supervisor_blockers": [],
                    "incident_total": 0,
                    "route_mix": {
                        "route_selected_total": {"monitor_only": 8, "full_cycle": 4},
                        "monitor_only_ratio": 0.6667,
                        "cached_strategist_ratio": 0.0,
                        "full_cycle_ratio": 0.3333,
                        "route_source": "canonical_commander",
                    },
                },
                "advisory_only": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions")
    monkeypatch.setenv("USE_STRATEGY_PERFORMANCE_MEMORY", "true")
    monkeypatch.setenv("STRATEGY_PERFORMANCE_AUTO_BUILD", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterCaptureMessages)

    logger = _DummyLogger()
    out = strategist_node(
        {
            "run_id": "strategist-memory-test",
            "started_at": "2026-03-20T09:00:00+00:00",
            "reports_root": str(reports_root),
            "event_logger": logger,
            "themes": ["legacy_theme"],
            "candidate_symbols": ["005930", "000660"],
            "policy": {
                "use_global_sentiment": False,
                "use_news_analysis": False,
                "use_universe_builder": False,
            },
        }
    )

    strategy_memory = out.get("strategy_memory") or {}
    assert strategy_memory.get("status") == "ok"
    assert "breakout" in list(strategy_memory.get("best_playbooks") or [])
    strategist_output = out.get("strategist_output") or {}
    assert "pullback" in list((strategist_output.get("strategy_memory") or {}).get("worst_playbooks") or [])

    user_prompt = "\n".join(
        str(row.get("content") or "")
        for row in list(_FakeRouterCaptureMessages.last_messages or [])
        if str(row.get("role") or "").strip().lower() == "user"
    )
    assert "strategy_memory" in user_prompt
    assert "best_playbooks" in user_prompt
    assert "worst_playbooks" in user_prompt
    assert "playbook_performance_snapshot" in user_prompt
    assert "reporter_analysis_digest" in user_prompt
    assert "prefer breakout in risk_on" in user_prompt
    assert "theme_accuracy" in user_prompt
    assert "monitor_status" in user_prompt
    assert "market_rank" in user_prompt
    assert "monitor_only_ratio" in user_prompt
