from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import libs.reporting.single_trade_report as single_trade_report
import libs.reporting.trade_report_ai as trade_report_ai
from libs.reporting.intraday_trade_reports import build_same_day_reporter_linkage
from libs.reporting.trade_read_model import build_trade_read_model


def _state() -> Dict[str, Any]:
    return {
        "day": "2026-04-14",
        "run_id": "run-sell-1",
        "ts": "2026-04-14T01:23:45+00:00",
        "applied_policy": {
            "reporter": {
                "trade_report": {
                    "enabled": True,
                    "generate_on_open": False,
                    "policy_source": "commander_applied_policy",
                }
            }
        },
        "execution": {
            "ok": True,
            "allowed": True,
            "reason": "Allowed",
            "broker_env": "real",
            "execution_mode": "real",
            "payload": {
                "order_id": "ORD-1",
                "avg_fill_price": 207000.0,
                "filled_qty": 1,
            },
            "order": {
                "action": "SELL",
                "symbol": "005930",
                "qty": 1,
                "avg_fill_price": 207000.0,
            },
        },
        "monitor_output": {
            "decision": "SELL",
            "decision_summary": "Exit: peak_drawdown",
            "primary_reason_code": "peak_drawdown",
            "position_age_seconds": 125,
            "position_snapshot": {
                "qty": 1,
                "avg_price": 206000.0,
                "current_price": 207000.0,
            },
        },
        "scanner_output": {
            "selected": {"symbol": "005930", "why": "Selected as rank #1 candidate"},
            "top_stock": "005930",
        },
        "strategist_output": {
            "playbook": "pullback",
            "market_regime": "neutral",
            "market_sentiment": "neutral",
        },
        "commander_decision": {
            "selected_route": "full_cycle",
            "route_reason_text": "",
        },
        "persisted_state": {
            "position_strategy_context": {
                "005930": {
                    "output": {
                        "playbook": "pullback",
                        "market_regime": "neutral",
                        "market_sentiment": "neutral",
                    },
                    "generated_epoch": 1,
                    "source": "buy_execution",
                }
            }
        },
    }


def _fake_ai_report(story_input: Dict[str, Any], *, enabled: bool | None = None, model: str | None = None, temperature: float | None = None, max_tokens: int | None = None) -> Dict[str, Any]:
    return {
        "trade_id": str(story_input.get("trade_id") or ""),
        "story_id": str(story_input.get("story_id") or ""),
        "symbol": str(story_input.get("symbol") or ""),
        "status": str(story_input.get("status") or ""),
        "generation": {
            "status": "ok",
            "mode": "ai",
            "model": str(model or "minimax/minimax-m2.5"),
        },
        "ai_trade_report_status": "ok",
        "llm_response_artifact": {
            "status": "ok",
            "llm_status": "ok",
            "model_info": {"provider": "OpenRouter", "model": str(model or "minimax/minimax-m2.5")},
        },
    }


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_single_trade_report_generates_without_bundle(tmp_path: Path, monkeypatch) -> None:
    popen_called = False
    run_called = False

    def fail_popen(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal popen_called
        popen_called = True
        raise AssertionError("single trade report should not spawn subprocesses")

    def fail_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal run_called
        run_called = True
        raise AssertionError("single trade report should not invoke bundle script")

    call_count = {"count": 0}

    def fake_build_ai_trade_report(*args, **kwargs):  # type: ignore[no-untyped-def]
        call_count["count"] += 1
        return _fake_ai_report(*args, **kwargs)

    monkeypatch.setattr("subprocess.Popen", fail_popen)
    monkeypatch.setattr("subprocess.run", fail_run)
    monkeypatch.setattr(single_trade_report, "build_ai_trade_report", fake_build_ai_trade_report)
    monkeypatch.setattr(single_trade_report, "render_trade_report_markdown", lambda report: "# report")

    state = _state()
    trade_id = single_trade_report.build_single_trade_report_id(state, root=tmp_path)
    out = single_trade_report.generate_single_trade_report(trade_id, state=state, root=tmp_path)

    trade_root = tmp_path / "reports" / "trades" / "2026-04-14" / trade_id
    assert out["ok"] is True
    assert out["trade_id"] == trade_id
    assert out["bundle_used"] is False
    assert call_count["count"] == 1
    exit_payload = json.loads((trade_root / "exit.json").read_text(encoding="utf-8"))
    assert exit_payload["execution_details"]["order_id"] == "ORD-1"
    assert (trade_root / "reports" / "ai_trade_report.json").exists()
    assert (trade_root / "reports" / "ai_trade_report.md").exists()
    assert (trade_root / "reports" / "ai_trade_report_llm_response.json").exists()
    assert (trade_root / "reports" / "report_generation_state.json").exists()
    assert popen_called is False
    assert run_called is False


def test_single_trade_report_preserves_provenance_and_traces_when_canonical_exists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(single_trade_report, "build_ai_trade_report", _fake_ai_report)
    monkeypatch.setattr(single_trade_report, "render_trade_report_markdown", lambda report: "# report")

    state = _state()
    canonical_dir = tmp_path / "reports" / "canonical" / "2026-04-14" / "run-sell-1"
    _write_json(
        canonical_dir / "scanner.json",
        {
            "selected_symbol": "005930",
            "ranked_candidates": [
                {"symbol": "005930", "score_total": 0.92},
                {"symbol": "000660", "score_total": 0.71},
            ],
            "selection_reason": "Selected as the highest-quality candidate.",
            "selected_symbol_score_drivers": {"volume": 0.8, "trend": 0.7},
        },
    )
    _write_json(
        canonical_dir / "monitor.json",
        {
            "threshold_snapshot": {
                "hard_stop_pct": 0.03,
                "take_profit_pct": 0.05,
                "trailing_stop_pct": 0.02,
            },
            "entry_check_summary": "monitor review",
            "entry_blockers": ["breakout_not_ready"],
        },
    )
    _write_json(canonical_dir / "strategist.json", {"playbook": "pullback"})
    _write_json(canonical_dir / "commander.json", {"selected_route": "full_cycle"})
    _write_json(canonical_dir / "supervisor.json", {"allowed": True, "reason": "Allowed"})
    _write_json(canonical_dir / "executor.json", {"execution_ok": True, "broker_env": "real"})
    reporter_json = tmp_path / "reports" / "dev" / "analysis" / "reporter_analysis" / "reporter_analysis_2026-04-14.json"
    _write_json(reporter_json, {"ai_summary": "Same-day summary", "ai_run_grade": "B"})

    trade_id = single_trade_report.build_single_trade_report_id(state, root=tmp_path)
    single_trade_report.generate_single_trade_report(trade_id, state=state, root=tmp_path)

    trade_root = tmp_path / "reports" / "trades" / "2026-04-14" / trade_id
    story_input = json.loads((trade_root / "ai_trade_report_input.json").read_text(encoding="utf-8"))
    lifecycle_bundle = json.loads((trade_root / "lifecycle_bundle.json").read_text(encoding="utf-8"))

    assert story_input["section_provenance"]["scanner_reason_human"]["source"] == "canonical"
    assert story_input["section_provenance"]["monitor_reason_human"]["source"] == "canonical"
    assert story_input["section_provenance"]["reporter_status_human"]["source"] == "direct_artifact"
    assert story_input["scanner_reason_human"]["scanner_selection_trace"]["ranked_candidates"]
    assert story_input["monitor_reason_human"]["monitor_stop_policy_trace"]["hard_stop_pct"] == 0.03
    assert lifecycle_bundle["evidence_provenance"]["scanner"] == "canonical"
    assert lifecycle_bundle["artifacts"]["canonical_scanner_json"].endswith("scanner.json")
    assert lifecycle_bundle["same_day_reporter_linkage"]["status"] == "linked_day_fallback"
    assert lifecycle_bundle["same_day_reporter_linkage"]["reporter_analysis_json_path"].endswith(
        "reporter_analysis_2026-04-14.json"
    )


class _Route:
    def __init__(self, model: str) -> None:
        self.model = model


class _SingleCallRouter:
    calls = 0

    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_SingleCallRouter":
        _SingleCallRouter.calls = 0
        return _SingleCallRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        _SingleCallRouter.calls += 1
        return (
            '{"executive_summary":{"headline":"SELL 005930","action":"SELL","symbol":"005930","confidence":"high","summary":"ok"},'
            '"market_context_at_entry":{"summary":"context","bullets":["macro stable"]},'
            '"why_this_symbol_was_chosen":{"summary":"rank #1","bullets":["selected"]},'
            '"entry_decision":{"summary":"entry","bullets":[]},'
            '"holding_monitoring_story":{"summary":"hold","bullets":[]},'
            '"exit_decision":{"summary":"exit","bullets":[]},'
            '"execution_quality":{"summary":"execution","bullets":[]},'
            '"scanner_filters":{"summary":"filters","bullets":[]},'
            '"guard_approval_result":{"summary":"guard","bullets":[]},'
            '"reporter_evaluation":{"summary":"reporter","status":"pending","grade":"N/A","bullets":[]},'
            '"errors_weaknesses_improvement_points":{"summary":"none","bullets":[]},'
            '"full_timeline":[{"event":"entry","ts":"2026-04-14T01:20:00+00:00","description":"entry"}],'
            '"final_operator_conclusion":{"summary":"done","current_action":"SELL","watch_next":["watch"],"thesis_invalidation":["stop"]}}'
        )


def test_ai_trade_report_defaults_to_single_llm_call_without_separated_narrative(monkeypatch) -> None:
    monkeypatch.setattr(trade_report_ai, "LLMRouter", _SingleCallRouter)
    monkeypatch.setattr(
        "libs.reporting.fact_narrative_report.build_separated_report",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("separated narrative should be skipped by default")),
    )

    story_input = {
        "trade_id": "TRD_20260414_005930_01",
        "story_id": "TRD_20260414_005930_01",
        "run_id": "run-sell-1",
        "day": "2026-04-14",
        "symbol": "005930",
        "action": "SELL",
        "status": "closed",
        "story_type": "live_trade",
        "execution_mode_label": "live broker",
        "monitor_reason_human": {"summary": "Exit: peak_drawdown"},
    }

    report = trade_report_ai.build_ai_trade_report(story_input, enabled=True, model="free")

    assert report["generation"]["status"] == "ok"
    assert _SingleCallRouter.calls == 1
    narrative = report.get("narrative") if isinstance(report.get("narrative"), dict) else {}
    assert narrative.get("status") == "skipped"
    assert narrative.get("llm_call_skipped") is True


def test_commander_runtime_restores_intraday_bundle_helper_for_live_reports() -> None:
    source = Path("graphs/commander_runtime.py").read_text(encoding="utf-8")
    assert "from graphs.nodes.reporter_node import reporter_node" in source
    assert "state = _emit_intraday_trade_report(state)" in source
    assert "generate_single_trade_report(" not in source


def test_single_trade_report_reuses_shared_same_day_linkage_helper() -> None:
    assert single_trade_report.build_same_day_reporter_linkage is build_same_day_reporter_linkage


def test_single_trade_report_output_is_readable_by_existing_reader(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(single_trade_report, "build_ai_trade_report", _fake_ai_report)
    monkeypatch.setattr(single_trade_report, "render_trade_report_markdown", lambda report: "# report")

    state = _state()
    trade_id = single_trade_report.build_single_trade_report_id(state, root=tmp_path)
    single_trade_report.generate_single_trade_report(trade_id, state=state, root=tmp_path)

    payload = build_trade_read_model(str(tmp_path / "reports" / "trades" / "2026-04-14" / trade_id))
    assert payload["trade_id"] == trade_id
    assert payload["symbol"] == "005930"
    assert payload["data_source"] in {"lifecycle_bundle", "ai_trade_report"}


def test_single_trade_report_resolves_missing_day_from_canonical_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(single_trade_report, "build_ai_trade_report", _fake_ai_report)
    monkeypatch.setattr(single_trade_report, "render_trade_report_markdown", lambda report: "# report")

    state = _state()
    state.pop("day", None)
    state["run_id"] = "run-missing-day"
    (tmp_path / "reports" / "canonical" / "2026-04-14" / "run-missing-day").mkdir(parents=True, exist_ok=True)

    trade_id = single_trade_report.build_single_trade_report_id(state, root=tmp_path)
    out = single_trade_report.generate_single_trade_report(trade_id, state=state, root=tmp_path)

    trade_root = tmp_path / "reports" / "trades" / "2026-04-14" / trade_id
    assert trade_id == "TRD_20260414_005930_01"
    assert out["ok"] is True
    assert trade_root.exists()
    assert (trade_root / "reports" / "ai_trade_report.json").exists()
