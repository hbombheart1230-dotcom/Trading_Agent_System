from __future__ import annotations

import json
from pathlib import Path

from graphs.nodes.monitor_node import monitor_node
from graphs.nodes.scanner_node import scanner_node
from graphs.nodes.strategist_node import strategist_node
from libs.reporting import reporter_ai_review as reporter_ai_review_module
from libs.reporting.reporter_ai_review import build_ai_reporter_review
from libs.research.evidence_ledger import append_evidence_record


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            obj = json.loads(s)
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def test_evidence_ledger_append_record_schema(tmp_path: Path, monkeypatch) -> None:
    ledger = tmp_path / "evidence.jsonl"
    monkeypatch.setenv("EVIDENCE_LEDGER_PATH", str(ledger))

    rec = append_evidence_record(
        run_id="r1",
        agent="strategist",
        stage="theme_selection",
        raw_input={"news": ["x"]},
        llm_prompt="prompt",
        llm_response='{"ok":true}',
        parsed_output={"themes": ["semiconductor"]},
        decision_link={"decision_chain": {"theme": "semiconductor"}},
    )

    assert rec["run_id"] == "r1"
    rows = _read_jsonl(ledger)
    assert len(rows) == 1
    row = rows[0]
    assert row["agent"] == "strategist"
    assert row["stage"] == "theme_selection"
    assert isinstance(row.get("raw_input"), dict)
    assert isinstance(row.get("parsed_output"), dict)
    assert isinstance(row.get("decision_link"), dict)


def test_strategist_trace_logging_writes_evidence_entries(tmp_path: Path, monkeypatch) -> None:
    ledger = tmp_path / "evidence_strategist.jsonl"
    monkeypatch.setenv("EVIDENCE_LEDGER_PATH", str(ledger))
    monkeypatch.setenv("TOP_N_CANDIDATES", "3")

    state = {
        "run_id": "trace-strategist",
        "themes": ["semiconductor"],
        "candidate_symbols": ["005930", "000660", "051910"],
        "policy": {
            "use_global_sentiment": False,
            "use_news_analysis": False,
            "use_universe_builder": False,
        },
    }
    strategist_node(state)

    rows = _read_jsonl(ledger)
    strategist_rows = [r for r in rows if str(r.get("agent") or "") == "strategist"]
    assert any(str(r.get("stage") or "") == "theme_selection" for r in strategist_rows)
    assert any(str(r.get("stage") or "") == "decision_bridge" for r in strategist_rows)


def test_scanner_trace_logging_writes_evidence_entries(tmp_path: Path, monkeypatch) -> None:
    ledger = tmp_path / "evidence_scanner.jsonl"
    monkeypatch.setenv("EVIDENCE_LEDGER_PATH", str(ledger))

    state = {
        "run_id": "trace-scanner",
        "themes": ["semiconductor"],
        "theme_map": {"semiconductor": ["005930", "000660"]},
        "mock_top_value_symbols": ["005930", "000660", "051910"],
        "mock_top_volume_symbols": ["005930", "000660", "051910"],
        "mock_condition_symbols": ["005930", "000660"],
        "mock_scan_results": {
            "005930": {"score": 0.91, "risk_score": 0.2, "confidence": 0.9},
            "000660": {"score": 0.82, "risk_score": 0.25, "confidence": 0.85},
        },
        "policy": {},
        "strategist_output": {
            "themes": ["semiconductor"],
            "avoid_themes": [],
            "playbook": "breakout",
            "scanner_bias": "leader",
            "scanner_priority": ["momentum", "trend_strength"],
            "trade_aggressiveness": "medium",
            "risk_tone": "normal",
        },
    }
    out = scanner_node(state)
    assert str(out.get("top_stock") or "") != ""

    rows = _read_jsonl(ledger)
    scanner_rows = [r for r in rows if str(r.get("agent") or "") == "scanner"]
    assert any(str(r.get("stage") or "") == "symbol_selection" for r in scanner_rows)
    assert any(str(r.get("stage") or "") == "decision_bridge" for r in scanner_rows)


def test_monitor_trace_logging_writes_evidence_entries(tmp_path: Path, monkeypatch) -> None:
    ledger = tmp_path / "evidence_monitor.jsonl"
    monkeypatch.setenv("EVIDENCE_LEDGER_PATH", str(ledger))
    monkeypatch.setenv("MIN_HOLD_SECONDS", "600")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "300")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "2")

    state = {
        "run_id": "trace-monitor",
        "selected": {"symbol": "005930", "score": 0.91, "risk_score": 0.2, "confidence": 0.9},
        "policy": {"use_exit_policy": False},
        "portfolio_snapshot": {"cash": 1_000_000.0, "positions": []},
        "strategist_output": {"monitor_guidance": "defensive_exit", "risk_tone": "normal", "trade_aggressiveness": "medium"},
    }
    out = monitor_node(state)
    assert isinstance(out.get("intents"), list)

    rows = _read_jsonl(ledger)
    monitor_rows = [r for r in rows if str(r.get("agent") or "") == "monitor"]
    assert any(str(r.get("stage") or "") == "entry_exit_decision" for r in monitor_rows)
    assert any(str(r.get("stage") or "") == "decision_bridge" for r in monitor_rows)


def test_reporter_trace_logging_writes_llm_prompt_and_response(tmp_path: Path, monkeypatch) -> None:
    ledger = tmp_path / "evidence_reporter.jsonl"
    monkeypatch.setenv("EVIDENCE_LEDGER_PATH", str(ledger))

    class _Route:
        model = "fake/reporter-model"

    class _FakeRouter:
        def __init__(self) -> None:
            self.client = object()

        def resolve(self, _agent: str, policy: dict | None = None):  # noqa: ANN001
            _ = policy
            return _Route()

        def chat(self, _agent: str, _messages: list[dict], policy: dict | None = None) -> str:  # noqa: ANN001
            _ = policy
            return json.dumps(
                {
                    "ai_summary": "ok",
                    "ai_findings": ["f1"],
                    "ai_root_causes": ["r1"],
                    "ai_improvement_suggestions": ["s1"],
                    "ai_run_grade": "B+",
                    "ai_agent_evaluations": {"strategist": "good"},
                }
            )

    monkeypatch.setattr(reporter_ai_review_module.LLMRouter, "from_env", staticmethod(lambda: _FakeRouter()))

    out = build_ai_reporter_review(
        day="2026-03-12",
        reporter_output={"trade_summary": {"trade_count": 1}, "decision_trace_chain_summary": {}},
        enabled=True,
        model="fake/reporter-model",
    )
    assert out["status"] == "ok"

    rows = _read_jsonl(ledger)
    reporter_rows = [r for r in rows if str(r.get("agent") or "") == "reporter"]
    assert any(str(r.get("stage") or "") == "post_run_analysis" and str(r.get("llm_prompt") or "") for r in reporter_rows)
    assert any(str(r.get("stage") or "") == "post_run_analysis" and str(r.get("llm_response") or "") for r in reporter_rows)
