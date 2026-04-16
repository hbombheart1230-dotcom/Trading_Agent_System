from pathlib import Path

import libs.agent.reporter as reporter_mod


def test_run_reporter_agent_returns_structured_payload(monkeypatch, tmp_path: Path) -> None:
    def _fake_read_model(_trade_dir: str):  # type: ignore[no-untyped-def]
        return {
            "trade_id": "TRD_X",
            "symbol": "005930",
            "facts": {
                "trade_id": "TRD_X",
                "symbol": "005930",
                "data_source": "lifecycle_bundle",
            },
            "provenance": {
                "schema_version": "trade_read_model.v2",
                "field_sources": {"trade_id": "lifecycle_bundle.trade_id"},
            },
            "context": {
                "scanner_selection_summary": "selected by score",
            },
        }

    def _fake_build_separated_report(*, trade_model, model=None, execution_profile=None):  # type: ignore[no-untyped-def]
        assert trade_model["facts"]["trade_id"] == "TRD_X"
        assert model is None
        assert execution_profile is None
        return {
            "fact_payload": {"trade": trade_model},
            "narrative": {"status": "skipped", "llm_call_skipped": True},
        }

    monkeypatch.setattr("libs.reporting.trade_read_model.build_trade_read_model", _fake_read_model)
    monkeypatch.setattr("libs.reporting.fact_narrative_report.build_separated_report", _fake_build_separated_report)

    out = reporter_mod.run_reporter_agent(str(tmp_path / "TRD_X"), policy={})
    assert out["status"] == "ok"
    assert out["metadata"]["trade_id"] == "TRD_X"
    assert out["metadata"]["symbol"] == "005930"
    assert out["facts"]["trade_id"] == "TRD_X"
    assert out["provenance"]["schema_version"] == "trade_read_model.v2"
    assert out["context"]["scanner_selection_summary"] == "selected by score"
    assert out["narrative"]["status"] == "skipped"


def test_run_reporter_agent_degrades_when_trade_read_model_missing_facts(monkeypatch, tmp_path: Path) -> None:
    def _invalid_read_model(_trade_dir: str):  # type: ignore[no-untyped-def]
        return {"trade_id": "TRD_BAD", "symbol": "000660"}

    monkeypatch.setattr("libs.reporting.trade_read_model.build_trade_read_model", _invalid_read_model)

    out = reporter_mod.run_reporter_agent(str(tmp_path / "TRD_BAD"), policy={})
    assert out["status"] == "degraded"
    assert out["metadata"]["trade_id"] == "TRD_BAD"
    assert out["context"] == {}
    assert out["narrative"]["status"] == "skipped"
    assert out["narrative"]["reason"] == "trade_read_model_facts_missing"
