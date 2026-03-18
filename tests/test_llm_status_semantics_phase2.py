from __future__ import annotations

import libs.reporting.reporter_ai_review as reporter_ai_review
import libs.reporting.trade_report_ai as trade_report_ai


class _Route:
    def __init__(self, model: str = "openrouter/free") -> None:
        self.model = model


class _TradeReportRouterPartial:
    client = object()

    def resolve(self, route: str, policy: dict | None = None) -> _Route:  # type: ignore[override]
        model = str((policy or {}).get("model") or "openrouter/free")
        return _Route(model=model)

    def chat(self, route: str, messages: list[dict], policy: dict | None = None) -> str:  # type: ignore[override]
        # Truncated outer JSON with a decodable inner dict fragment.
        return '{"executive_summary": {"headline": "partial", "action": "BUY", "symbol": "000660"}} trailing'


class _ReporterRouterPartial:
    client = object()

    def resolve(self, route: str, policy: dict | None = None) -> _Route:  # type: ignore[override]
        model = str((policy or {}).get("model") or "openrouter/free")
        return _Route(model=model)

    def chat(self, route: str, messages: list[dict], policy: dict | None = None) -> str:  # type: ignore[override]
        return '{"ai_summary":"partial only"} trailing'


def _story_input() -> dict:
    return {
        "day": "2026-03-18",
        "trade_id": "TRD_20260318_000660_01",
        "story_id": "TRD_20260318_000660_01",
        "run_id": "run-1",
        "symbol": "000660",
        "action": "BUY",
        "status": "open",
        "story_type": "simulation",
        "execution_mode_label": "simulation (mock broker)",
        "market_context_human": {"summary": "context", "bullets": []},
        "scanner_reason_human": {"summary": "scanner", "bullets": []},
        "filters_human": {"summary": "filters", "bullets": []},
        "monitor_reason_human": {"summary": "monitor", "bullets": []},
        "guard_reason_human": {"summary": "guard", "bullets": []},
        "execution_outcome_human": {"summary": "execution", "bullets": []},
        "reporter_status_human": {"summary": "reporter", "bullets": []},
        "operator_conclusion_human": {"summary": "conclusion", "current_action": "HOLD"},
        "timeline": [],
        "warnings": [],
    }


def test_trade_report_partial_output_is_not_marked_ok(monkeypatch) -> None:
    monkeypatch.setattr(trade_report_ai.LLMRouter, "from_env", staticmethod(lambda: _TradeReportRouterPartial()))
    report = trade_report_ai.build_ai_trade_report(_story_input(), enabled=True, model="openrouter/free")
    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    artifact = report.get("llm_response_artifact") if isinstance(report.get("llm_response_artifact"), dict) else {}

    assert str(generation.get("status") or "").lower() != "ok"
    assert str(artifact.get("status") or "").lower() != "ok"
    assert str(artifact.get("parse_mode") or "") in {"partial", "none", "full"}
    assert float(artifact.get("completeness_score") or 0.0) < 1.0


def test_reporter_review_partial_output_is_not_marked_ok(monkeypatch) -> None:
    monkeypatch.setattr(reporter_ai_review.LLMRouter, "from_env", staticmethod(lambda: _ReporterRouterPartial()))
    out = reporter_ai_review.build_ai_reporter_review(
        day="2026-03-18",
        reporter_output={},
        enabled=True,
        model="openrouter/free",
    )
    assert out["status"] == "parse_error"
    assert out["llm_status"] == "partial"
    assert out["parse_mode"] in {"partial", "none"}
